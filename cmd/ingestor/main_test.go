package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLatestGKGURL(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		io.WriteString(writer, "10 hash https://example.test/20260819120000.export.CSV.zip\n")
		io.WriteString(writer, "20 hash https://example.test/20260819120000.gkg.csv.zip\n")
	}))
	defer server.Close()

	client := &http.Client{Timeout: time.Second}
	got, err := latestGKGURL(context.Background(), client, server.URL)
	if err != nil {
		t.Fatal(err)
	}
	want := "https://example.test/20260819120000.gkg.csv.zip"
	if got != want {
		t.Fatalf("latestGKGURL() = %q, want %q", got, want)
	}
}

func TestLatestAvailableGKGURLBacktracksPastAdvertised404(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/20260819120000.gkg.csv.zip" {
			writer.WriteHeader(http.StatusNotFound)
			return
		}
		writer.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	client := &http.Client{Timeout: time.Second}
	got, err := latestAvailableGKGURL(
		context.Background(),
		client,
		server.URL+"/20260819120000.gkg.csv.zip",
		3,
	)
	if err != nil {
		t.Fatal(err)
	}
	want := server.URL + "/20260819114500.gkg.csv.zip"
	if got != want {
		t.Fatalf("latestAvailableGKGURL() = %q, want %q", got, want)
	}
}

func TestDownloadIsIdempotent(t *testing.T) {
	payload := []byte("small-gkg-zip-placeholder")
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Write(payload)
	}))
	defer server.Close()

	outputDir := t.TempDir()
	client := &http.Client{Timeout: time.Second}
	sourceURL := server.URL + "/20260819120000.gkg.csv.zip"

	first, alreadyPresent, err := download(context.Background(), client, sourceURL, outputDir)
	if err != nil {
		t.Fatal(err)
	}
	if alreadyPresent || first.ProcessingStatus != "downloaded" {
		t.Fatalf("first download status = %q, alreadyPresent = %v", first.ProcessingStatus, alreadyPresent)
	}

	second, alreadyPresent, err := download(context.Background(), client, sourceURL, outputDir)
	if err != nil {
		t.Fatal(err)
	}
	if !alreadyPresent || second.ProcessingStatus != "already_present" {
		t.Fatalf("second download status = %q, alreadyPresent = %v", second.ProcessingStatus, alreadyPresent)
	}
	if first.ChecksumSHA256 != second.ChecksumSHA256 {
		t.Fatal("checksums differ between first and second download")
	}

	stored, err := os.ReadFile(filepath.Join(outputDir, "20260819120000.gkg.csv.zip"))
	if err != nil {
		t.Fatal(err)
	}
	if string(stored) != string(payload) {
		t.Fatal("stored content differs from downloaded content")
	}
}

func TestGKGWindowURLsReturnsOldestToNewest(t *testing.T) {
	urls, err := gkgWindowURLs(
		"http://data.gdeltproject.org/gdeltv2/20260820144500.gkg.csv.zip",
		3,
	)
	if err != nil {
		t.Fatal(err)
	}
	want := []string{
		"https://data.gdeltproject.org/gdeltv2/20260820141500.gkg.csv.zip",
		"https://data.gdeltproject.org/gdeltv2/20260820143000.gkg.csv.zip",
		"https://data.gdeltproject.org/gdeltv2/20260820144500.gkg.csv.zip",
	}
	if len(urls) != len(want) {
		t.Fatalf("got %d URLs, want %d", len(urls), len(want))
	}
	for index := range want {
		if urls[index] != want[index] {
			t.Fatalf("URL %d = %q, want %q", index, urls[index], want[index])
		}
	}
}

func TestGKGWindowURLsSupportsSevenDaysAndRejectsMore(t *testing.T) {
	latest := "https://data.gdeltproject.org/gdeltv2/20260820144500.gkg.csv.zip"
	urls, err := gkgWindowURLs(latest, maxIntervals)
	if err != nil {
		t.Fatal(err)
	}
	if len(urls) != 672 {
		t.Fatalf("got %d URLs, want 672", len(urls))
	}
	if urls[len(urls)-1] != latest {
		t.Fatalf("last URL = %q, want %q", urls[len(urls)-1], latest)
	}
	if _, err := gkgWindowURLs(latest, maxIntervals+1); err == nil {
		t.Fatal("expected an error above the seven-day limit")
	}
}

func TestValidatedRemoteURLRejectsUnsafeSchemesAndCredentials(t *testing.T) {
	for _, raw := range []string{
		"file:///etc/passwd",
		"http://example.test/file.gkg.csv.zip",
		"https://user:password@example.test/file.gkg.csv.zip",
	} {
		if _, err := validatedRemoteURL(raw); err == nil {
			t.Fatalf("validatedRemoteURL(%q) unexpectedly succeeded", raw)
		}
	}
	parsed, err := validatedRemoteURL("http://data.gdeltproject.org/gdeltv2/file.gkg.csv.zip")
	if err != nil {
		t.Fatal(err)
	}
	if parsed.Scheme != "https" {
		t.Fatalf("GDELT URL scheme = %q", parsed.Scheme)
	}
}

func TestDownloadRejectsOversizedResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Length", fmt.Sprint(maxGKGBytes+1))
		writer.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	_, _, err := download(
		context.Background(),
		&http.Client{Timeout: time.Second},
		server.URL+"/20260819120000.gkg.csv.zip",
		t.TempDir(),
	)
	if err == nil {
		t.Fatal("expected oversized download to be rejected")
	}
}
