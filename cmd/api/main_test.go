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
	temporaryRoot := t.TempDir()
	dataPath := filepath.Join(temporaryRoot, "dashboard.json")
	if err := os.WriteFile(dataPath, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	return newHandler(
		dataPath,
		filepath.Join(temporaryRoot, "reviews.jsonl"),
		"http://localhost:3000",
		log.New(io.Discard, "", 0),
	)
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
	handler := newHandler(
		dataPath,
		filepath.Join(t.TempDir(), "reviews.jsonl"),
		"http://localhost:3000",
		log.New(io.Discard, "", 0),
	)
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

func TestReviewsSavesAndReturnsLatestDecision(t *testing.T) {
	handler := testHandler(t, testDashboard)
	saveReview := func(decision string) reviewRecord {
		request := httptest.NewRequest(
			http.MethodPost,
			"/api/v1/reviews",
			strings.NewReader(`{"region_code":"US:USHI","window_start":"2026-08-20T19:00:00","decision":"`+decision+`"}`),
		)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("Origin", "http://localhost:3000")
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusCreated {
			t.Fatalf("save status = %d, body = %s", response.Code, response.Body.String())
		}
		if got := response.Header().Get("Access-Control-Allow-Origin"); got != "http://localhost:3000" {
			t.Fatalf("Access-Control-Allow-Origin = %q", got)
		}
		var body reviewResponse
		if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
			t.Fatal(err)
		}
		return body.Review
	}

	first := saveReview("confirmed_event")
	if first.SignalID != "US:USHI|2026-08-20T19:00:00" {
		t.Fatalf("signal id = %q", first.SignalID)
	}
	saveReview("uncertain")

	request := httptest.NewRequest(http.MethodGet, "/api/v1/reviews", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	var body reviewsResponse
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if response.Code != http.StatusOK || len(body.Reviews) != 1 {
		t.Fatalf("status = %d, reviews = %+v", response.Code, body.Reviews)
	}
	if body.Reviews[0].Decision != "uncertain" {
		t.Fatalf("latest decision = %q", body.Reviews[0].Decision)
	}
}

func TestReviewsRejectsInvalidInputAndUntrustedOrigin(t *testing.T) {
	handler := testHandler(t, testDashboard)
	tests := []struct {
		name        string
		contentType string
		body        string
		origin      string
		wantStatus  int
	}{
		{
			name:        "invalid decision",
			contentType: "application/json",
			body:        `{"region_code":"US:USHI","window_start":"2026-08-20T19:00:00","decision":"maybe"}`,
			wantStatus:  http.StatusBadRequest,
		},
		{
			name:        "unknown field",
			contentType: "application/json",
			body:        `{"region_code":"US:USHI","window_start":"2026-08-20T19:00:00","decision":"uncertain","extra":true}`,
			wantStatus:  http.StatusBadRequest,
		},
		{
			name:        "wrong content type",
			contentType: "text/plain",
			body:        `{}`,
			wantStatus:  http.StatusUnsupportedMediaType,
		},
		{
			name:        "untrusted origin",
			contentType: "application/json",
			body:        `{"region_code":"US:USHI","window_start":"2026-08-20T19:00:00","decision":"uncertain"}`,
			origin:      "https://untrusted.example",
			wantStatus:  http.StatusForbidden,
		},
	}
	for _, item := range tests {
		t.Run(item.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodPost, "/api/v1/reviews", strings.NewReader(item.body))
			request.Header.Set("Content-Type", item.contentType)
			if item.origin != "" {
				request.Header.Set("Origin", item.origin)
			}
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != item.wantStatus {
				t.Fatalf("status = %d, want %d, body = %s", response.Code, item.wantStatus, response.Body.String())
			}
		})
	}
}

func TestReviewPreflightAllowsPost(t *testing.T) {
	request := httptest.NewRequest(http.MethodOptions, "/api/v1/reviews", nil)
	request.Header.Set("Origin", "http://localhost:3000")
	response := httptest.NewRecorder()
	testHandler(t, testDashboard).ServeHTTP(response, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf("status = %d", response.Code)
	}
	if methods := response.Header().Get("Access-Control-Allow-Methods"); !strings.Contains(methods, "POST") {
		t.Fatalf("allowed methods = %q", methods)
	}
}
