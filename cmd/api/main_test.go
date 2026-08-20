package main

import (
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const testDashboard = `{
  "snapshot": {"updated_label": "Aug 20, 19:00 UTC", "candidates": 1},
  "parameters": {"minimum_history_hours": 168},
  "status_counts": {"candidate_anomaly": 1},
  "signals": [{"code": "US:USHI", "status": "candidate_anomaly"}]
}`

func testHandler(t *testing.T, content string) http.Handler {
	t.Helper()
	dataPath := filepath.Join(t.TempDir(), "dashboard.json")
	if err := os.WriteFile(dataPath, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	return newHandler(dataPath, "http://localhost:3000", log.New(io.Discard, "", 0))
}

func TestHealth(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	response := httptest.NewRecorder()
	testHandler(t, testDashboard).ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusOK)
	}
	if !strings.Contains(response.Body.String(), `"status":"ok"`) {
		t.Fatalf("body = %q", response.Body.String())
	}
}

func TestSnapshotReturnsCurrentFileAndCORS(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "/api/v1/snapshot", nil)
	request.Header.Set("Origin", "http://localhost:3000")
	response := httptest.NewRecorder()
	testHandler(t, testDashboard).ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusOK)
	}
	if got := response.Header().Get("Access-Control-Allow-Origin"); got != "http://localhost:3000" {
		t.Fatalf("Access-Control-Allow-Origin = %q", got)
	}
	var body map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if _, ok := body["parameters"]; !ok {
		t.Fatal("snapshot response omitted parameters")
	}
}

func TestSignalsReturnsProjection(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "/api/v1/signals", nil)
	response := httptest.NewRecorder()
	testHandler(t, testDashboard).ServeHTTP(response, request)

	var body signalsResponse
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if response.Code != http.StatusOK || body.CandidateAnomalies != 1 || len(body.Signals) != 1 {
		t.Fatalf("status = %d, response = %+v", response.Code, body)
	}
}

func TestMissingSnapshotIsUnavailableWithoutLeakingPath(t *testing.T) {
	dataPath := filepath.Join(t.TempDir(), "missing.json")
	handler := newHandler(dataPath, "http://localhost:3000", log.New(io.Discard, "", 0))
	request := httptest.NewRequest(http.MethodGet, "/api/v1/snapshot", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusServiceUnavailable)
	}
	if strings.Contains(response.Body.String(), dataPath) {
		t.Fatal("public error leaked the local data path")
	}
}

func TestRejectsUnsupportedMethodAndOrigin(t *testing.T) {
	handler := testHandler(t, testDashboard)
	postRequest := httptest.NewRequest(http.MethodPost, "/health", nil)
	postResponse := httptest.NewRecorder()
	handler.ServeHTTP(postResponse, postRequest)
	if postResponse.Code != http.StatusMethodNotAllowed {
		t.Fatalf("POST status = %d", postResponse.Code)
	}

	optionsRequest := httptest.NewRequest(http.MethodOptions, "/api/v1/snapshot", nil)
	optionsRequest.Header.Set("Origin", "https://untrusted.example")
	optionsResponse := httptest.NewRecorder()
	handler.ServeHTTP(optionsResponse, optionsRequest)
	if optionsResponse.Code != http.StatusForbidden {
		t.Fatalf("OPTIONS status = %d", optionsResponse.Code)
	}
}
