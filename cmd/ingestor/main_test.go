package main

import (
	"context"
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
