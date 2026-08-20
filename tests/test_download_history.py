from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from pipelines.download_history import (
    download_one,
    download_window,
    gkg_window_urls,
    latest_gkg_url,
)


class _Handler(BaseHTTPRequestHandler):
    payload = b"small-gkg-zip-placeholder"

    def do_GET(self) -> None:
        if self.path == "/lastupdate.txt":
            body = (
                b"10 hash http://example.test/20260820120000.export.CSV.zip\n"
                + f"{len(self.payload)} hash http://{self.headers['Host']}/20260820120000.gkg.csv.zip\n".encode()
            )
        else:
            body = self.payload
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        pass


def _server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def test_latest_url_and_window_are_oldest_to_newest() -> None:
    server, base_url = _server()
    try:
        latest = latest_gkg_url(f"{base_url}/lastupdate.txt")
    finally:
        server.shutdown()

    assert latest == f"{base_url}/20260820120000.gkg.csv.zip"
    assert gkg_window_urls(latest, 3) == [
        f"{base_url}/20260820113000.gkg.csv.zip",
        f"{base_url}/20260820114500.gkg.csv.zip",
        f"{base_url}/20260820120000.gkg.csv.zip",
    ]


def test_download_is_atomic_and_idempotent(tmp_path: Path) -> None:
    server, base_url = _server()
    source_url = f"{base_url}/20260820120000.gkg.csv.zip"
    try:
        first = download_one(source_url, tmp_path)
        second = download_one(source_url, tmp_path)
    finally:
        server.shutdown()

    assert first.processing_status == "downloaded"
    assert second.processing_status == "already_present"
    assert first.checksum_sha256 == second.checksum_sha256
    assert not list(tmp_path.glob("*.partial"))


def test_window_manifest_records_only_new_downloads(tmp_path: Path) -> None:
    server, base_url = _server()
    urls = [
        f"{base_url}/20260820114500.gkg.csv.zip",
        f"{base_url}/20260820120000.gkg.csv.zip",
    ]
    try:
        first = download_window(urls, tmp_path, workers=2, progress_every=0)
        second = download_window(urls, tmp_path, workers=2, progress_every=0)
    finally:
        server.shutdown()

    assert first == {
        "requested_files": 2,
        "downloaded_files": 2,
        "already_present_files": 0,
    }
    assert second == {
        "requested_files": 2,
        "downloaded_files": 0,
        "already_present_files": 2,
    }
    assert len((tmp_path / "manifest.jsonl").read_text().splitlines()) == 2
