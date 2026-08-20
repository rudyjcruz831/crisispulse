package main

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// GDELT currently publishes this data endpoint over HTTP. The downloaded file
// receives a SHA-256 checksum in the local manifest for reproducible processing.
const defaultIndexURL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

type config struct {
	indexURL  string
	sourceURL string
	outputDir string
	timeout   time.Duration
}

type manifestEntry struct {
	SourceURL        string    `json:"source_url"`
	DownloadedAt     time.Time `json:"downloaded_at"`
	FileTimestamp    string    `json:"file_timestamp"`
	ChecksumSHA256   string    `json:"checksum_sha256"`
	FileSize         int64     `json:"file_size"`
	ProcessingStatus string    `json:"processing_status"`
	LocalPath        string    `json:"local_path"`
}

func main() {
	cfg := parseFlags()
	if err := run(context.Background(), cfg); err != nil {
		fmt.Fprintln(os.Stderr, "ingestion failed:", err)
		os.Exit(1)
	}
}

func parseFlags() config {
	var cfg config
	flag.StringVar(&cfg.indexURL, "index-url", defaultIndexURL, "GDELT last-update index URL")
	flag.StringVar(&cfg.sourceURL, "source-url", "", "download this GKG ZIP directly instead of reading the index")
	flag.StringVar(&cfg.outputDir, "output-dir", "data/raw", "directory for immutable source files")
	flag.DurationVar(&cfg.timeout, "timeout", 2*time.Minute, "HTTP request timeout")
	flag.Parse()
	return cfg
}

func run(ctx context.Context, cfg config) error {
	client := &http.Client{Timeout: cfg.timeout}
	sourceURL := cfg.sourceURL
	if sourceURL == "" {
		var err error
		sourceURL, err = latestGKGURL(ctx, client, cfg.indexURL)
		if err != nil {
			return err
		}
	}

	entry, alreadyPresent, err := download(ctx, client, sourceURL, cfg.outputDir)
	if err != nil {
		return err
	}
	if !alreadyPresent {
		if err := appendManifest(filepath.Join(cfg.outputDir, "manifest.jsonl"), entry); err != nil {
			return err
		}
	}

	result := map[string]any{
		"status":     entry.ProcessingStatus,
		"source_url": entry.SourceURL,
		"local_path": entry.LocalPath,
		"sha256":     entry.ChecksumSHA256,
		"file_size":  entry.FileSize,
	}
	return json.NewEncoder(os.Stdout).Encode(result)
}

func latestGKGURL(ctx context.Context, client *http.Client, indexURL string) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, indexURL, nil)
	if err != nil {
		return "", fmt.Errorf("create index request: %w", err)
	}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("fetch GDELT index: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("fetch GDELT index: HTTP %s", resp.Status)
	}

	scanner := bufio.NewScanner(resp.Body)
	for scanner.Scan() {
		fields := strings.Fields(scanner.Text())
		if len(fields) == 0 {
			continue
		}
		candidate := fields[len(fields)-1]
		if strings.HasSuffix(candidate, ".gkg.csv.zip") {
			return candidate, nil
		}
	}
	if err := scanner.Err(); err != nil {
		return "", fmt.Errorf("read GDELT index: %w", err)
	}
	return "", errors.New("GDELT index did not contain a GKG ZIP URL")
}

func download(ctx context.Context, client *http.Client, sourceURL, outputDir string) (manifestEntry, bool, error) {
	parsed, err := url.Parse(sourceURL)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return manifestEntry{}, false, fmt.Errorf("invalid source URL %q", sourceURL)
	}
	filename := filepath.Base(parsed.Path)
	if filename == "." || filename == string(filepath.Separator) || filename == "" {
		return manifestEntry{}, false, fmt.Errorf("source URL has no filename: %q", sourceURL)
	}
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return manifestEntry{}, false, fmt.Errorf("create output directory: %w", err)
	}

	destination := filepath.Join(outputDir, filename)
	if info, err := os.Stat(destination); err == nil {
		checksum, hashErr := checksumFile(destination)
		if hashErr != nil {
			return manifestEntry{}, false, hashErr
		}
		return newManifestEntry(sourceURL, destination, checksum, info.Size(), "already_present"), true, nil
	} else if !errors.Is(err, os.ErrNotExist) {
		return manifestEntry{}, false, fmt.Errorf("inspect destination: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, sourceURL, nil)
	if err != nil {
		return manifestEntry{}, false, fmt.Errorf("create download request: %w", err)
	}
	resp, err := client.Do(req)
	if err != nil {
		return manifestEntry{}, false, fmt.Errorf("download GKG file: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return manifestEntry{}, false, fmt.Errorf("download GKG file: HTTP %s", resp.Status)
	}

	temporary, err := os.CreateTemp(outputDir, filename+".*.partial")
	if err != nil {
		return manifestEntry{}, false, fmt.Errorf("create temporary file: %w", err)
	}
	temporaryName := temporary.Name()
	defer os.Remove(temporaryName)

	hash := sha256.New()
	written, copyErr := io.Copy(io.MultiWriter(temporary, hash), resp.Body)
	closeErr := temporary.Close()
	if copyErr != nil {
		return manifestEntry{}, false, fmt.Errorf("write download: %w", copyErr)
	}
	if closeErr != nil {
		return manifestEntry{}, false, fmt.Errorf("close download: %w", closeErr)
	}
	if err := os.Rename(temporaryName, destination); err != nil {
		return manifestEntry{}, false, fmt.Errorf("finalize download: %w", err)
	}

	checksum := hex.EncodeToString(hash.Sum(nil))
	return newManifestEntry(sourceURL, destination, checksum, written, "downloaded"), false, nil
}

func checksumFile(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", fmt.Errorf("open existing file: %w", err)
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", fmt.Errorf("hash existing file: %w", err)
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func newManifestEntry(sourceURL, localPath, checksum string, size int64, status string) manifestEntry {
	filename := filepath.Base(localPath)
	fileTimestamp := strings.TrimSuffix(filename, ".gkg.csv.zip")
	return manifestEntry{
		SourceURL:        sourceURL,
		DownloadedAt:     time.Now().UTC(),
		FileTimestamp:    fileTimestamp,
		ChecksumSHA256:   checksum,
		FileSize:         size,
		ProcessingStatus: status,
		LocalPath:        filepath.ToSlash(localPath),
	}
}

func appendManifest(path string, entry manifestEntry) error {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return fmt.Errorf("open manifest: %w", err)
	}
	defer file.Close()
	if err := json.NewEncoder(file).Encode(entry); err != nil {
		return fmt.Errorf("write manifest: %w", err)
	}
	return nil
}
