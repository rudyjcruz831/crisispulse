"""Download a consecutive GDELT GKG window without requiring Docker or Go."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_INDEX_URL = "https://data.gdeltproject.org/gdeltv2/lastupdate.txt"
MAX_INTERVALS = 7 * 24 * 4
MAX_INDEX_BYTES = 1024 * 1024
MAX_GKG_BYTES = 64 * 1024 * 1024
MAX_AVAILABILITY_BACKTRACK = 16
GKG_SUFFIX = ".gkg.csv.zip"
USER_AGENT = "CrisisPulse/0.1 (+local research pipeline)"


@dataclass(frozen=True)
class DownloadResult:
    source_url: str
    downloaded_at: str
    file_timestamp: str
    checksum_sha256: str
    file_size: int
    processing_status: str
    local_path: str


def _validated_remote_url(value: str) -> str:
    parsed = urlparse(value)
    try:
        hostname = (parsed.hostname or "").lower()
    except ValueError as error:
        raise ValueError(f"invalid remote URL: {value!r}") from error
    if not hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError(f"invalid remote URL: {value!r}")
    if parsed.fragment:
        raise ValueError("remote URLs must not contain fragments")
    if parsed.scheme == "http" and hostname == "data.gdeltproject.org":
        parsed = parsed._replace(scheme="https")
    elif parsed.scheme == "https":
        pass
    elif parsed.scheme == "http" and hostname in {"127.0.0.1", "localhost", "::1"}:
        pass
    else:
        raise ValueError("remote URLs must use HTTPS")
    return parsed.geturl()


def latest_gkg_url(index_url: str, timeout: float = 30) -> str:
    index_url = _validated_remote_url(index_url)
    request = Request(index_url, headers={"User-Agent": USER_AGENT})
    # The URL is restricted to an allowed scheme immediately before this call.
    with urlopen(request, timeout=timeout) as response:  # nosec B310
        _validated_remote_url(response.geturl())
        body = response.read(MAX_INDEX_BYTES + 1)
    if len(body) > MAX_INDEX_BYTES:
        raise ValueError("GDELT index exceeded the size limit")
    for raw_line in body.splitlines():
        fields = raw_line.decode("utf-8", errors="replace").split()
        if fields and fields[-1].endswith(GKG_SUFFIX):
            return _validated_remote_url(fields[-1])
    raise ValueError("GDELT index did not contain a GKG ZIP URL")


def gkg_window_urls(latest_url: str, intervals: int) -> list[str]:
    if intervals < 1 or intervals > MAX_INTERVALS:
        raise ValueError(f"intervals must be between 1 and {MAX_INTERVALS}")
    parsed = urlparse(_validated_remote_url(latest_url))
    filename = Path(parsed.path).name
    if not filename.endswith(GKG_SUFFIX):
        raise ValueError(f"unexpected GKG filename: {filename!r}")
    latest = datetime.strptime(filename.removesuffix(GKG_SUFFIX), "%Y%m%d%H%M%S")
    directory = parsed.path.rsplit("/", maxsplit=1)[0]
    return [
        parsed._replace(
            path=f"{directory}/{(latest - timedelta(minutes=15 * offset)).strftime('%Y%m%d%H%M%S')}{GKG_SUFFIX}"
        ).geturl()
        for offset in range(intervals - 1, -1, -1)
    ]


def latest_available_gkg_url(
    latest_url: str,
    timeout: float = 30,
    max_backtrack: int = MAX_AVAILABILITY_BACKTRACK,
) -> str:
    """Return the newest advertised GKG file that is actually downloadable."""
    if max_backtrack < 1 or max_backtrack > MAX_AVAILABILITY_BACKTRACK:
        raise ValueError(
            f"max_backtrack must be between 1 and {MAX_AVAILABILITY_BACKTRACK}"
        )

    candidates = reversed(gkg_window_urls(latest_url, max_backtrack))
    for candidate in candidates:
        request = Request(candidate, headers={"User-Agent": USER_AGENT}, method="HEAD")
        try:
            # Each candidate is produced from a validated remote URL.
            with urlopen(request, timeout=timeout) as response:  # nosec B310
                _validated_remote_url(response.geturl())
                if response.status == 200:
                    return candidate
        except HTTPError as error:
            if error.code in {404, 410}:
                continue
            raise

    raise ValueError(
        f"no advertised GKG file was available within the last {max_backtrack * 15} minutes"
    )


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_one(source_url: str, output_dir: Path, timeout: float = 120) -> DownloadResult:
    source_url = _validated_remote_url(source_url)
    filename = Path(urlparse(source_url).path).name
    if not filename.endswith(GKG_SUFFIX):
        raise ValueError(f"unexpected GKG filename: {filename!r}")
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / filename
    downloaded_at = datetime.now(UTC).isoformat()

    if destination.exists():
        return DownloadResult(
            source_url=source_url,
            downloaded_at=downloaded_at,
            file_timestamp=filename.removesuffix(GKG_SUFFIX),
            checksum_sha256=_checksum(destination),
            file_size=destination.stat().st_size,
            processing_status="already_present",
            local_path=destination.as_posix(),
        )

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_dir,
            prefix=f"{filename}.",
            suffix=".partial",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            request = Request(source_url, headers={"User-Agent": USER_AGENT})
            digest = hashlib.sha256()
            file_size = 0
            # The URL is restricted to an allowed scheme immediately before this call.
            with urlopen(request, timeout=timeout) as response:  # nosec B310
                _validated_remote_url(response.geturl())
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) > MAX_GKG_BYTES:
                    raise ValueError("GKG download exceeded the size limit")
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
                    digest.update(chunk)
                    file_size += len(chunk)
                    if file_size > MAX_GKG_BYTES:
                        raise ValueError("GKG download exceeded the size limit")
        os.replace(temporary_path, destination)
        temporary_path = None
        return DownloadResult(
            source_url=source_url,
            downloaded_at=downloaded_at,
            file_timestamp=filename.removesuffix(GKG_SUFFIX),
            checksum_sha256=digest.hexdigest(),
            file_size=file_size,
            processing_status="downloaded",
            local_path=destination.as_posix(),
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _append_manifest(manifest_path: Path, result: DownloadResult) -> None:
    if result.processing_status != "downloaded":
        return
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def download_window(
    source_urls: list[str],
    output_dir: Path,
    *,
    workers: int = 8,
    timeout: float = 120,
    progress_every: int = 25,
) -> dict[str, int]:
    if workers < 1 or workers > 16:
        raise ValueError("workers must be between 1 and 16")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.jsonl"
    downloaded = 0
    already_present = 0
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures: dict[Future[DownloadResult], str] = {
            executor.submit(download_one, source_url, output_dir, timeout): source_url
            for source_url in source_urls
        }
        try:
            for future in as_completed(futures):
                result = future.result()
                _append_manifest(manifest_path, result)
                downloaded += int(result.processing_status == "downloaded")
                already_present += int(result.processing_status == "already_present")
                completed += 1
                if progress_every and (
                    completed % progress_every == 0 or completed == len(source_urls)
                ):
                    print(
                        json.dumps(
                            {
                                "completed_files": completed,
                                "requested_files": len(source_urls),
                                "downloaded_files": downloaded,
                                "already_present_files": already_present,
                            }
                        ),
                        flush=True,
                    )
        except Exception:
            for future in futures:
                future.cancel()
            raise

    return {
        "requested_files": len(source_urls),
        "downloaded_files": downloaded,
        "already_present_files": already_present,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    parser.add_argument("--source-url")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--intervals", type=int, default=672)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--progress-every", type=int, default=25)
    args = parser.parse_args()

    if args.source_url:
        latest_url = args.source_url
    else:
        advertised_url = latest_gkg_url(args.index_url, args.timeout)
        latest_url = latest_available_gkg_url(advertised_url, args.timeout)
    source_urls = gkg_window_urls(latest_url, args.intervals)
    result = download_window(
        source_urls,
        args.output_dir,
        workers=args.workers,
        timeout=args.timeout,
        progress_every=max(args.progress_every, 0),
    )
    print(
        json.dumps(
            {
                **result,
                "first_file": Path(urlparse(source_urls[0]).path).name,
                "last_file": Path(urlparse(source_urls[-1]).path).name,
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
