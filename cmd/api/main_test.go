package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
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
	for _, path := range []string{"/health", "/api/v1/health"} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		response := httptest.NewRecorder()
		testHandler(t, testDashboard).ServeHTTP(response, request)

		if response.Code != http.StatusOK {
			t.Fatalf("%s status = %d, want %d", path, response.Code, http.StatusOK)
		}
		if !strings.Contains(response.Body.String(), `"status":"ok"`) {
			t.Fatalf("%s body = %q", path, response.Body.String())
		}
		if got := response.Header().Get("X-Content-Type-Options"); got != "nosniff" {
			t.Fatalf("%s X-Content-Type-Options = %q", path, got)
		}
	}
}

func TestAdminStatusReturnsSanitizedRefreshHealth(t *testing.T) {
	temporaryRoot := t.TempDir()
	dataPath := filepath.Join(temporaryRoot, "dashboard.json")
	if err := os.WriteFile(dataPath, []byte(testDashboard), 0o600); err != nil {
		t.Fatal(err)
	}
	lastSuccess := time.Now().UTC().Add(-5 * time.Minute).Format(time.RFC3339Nano)
	status := fmt.Sprintf(`{
  "status":"success",
  "started_at":"%s",
  "finished_at":"%s",
  "last_success_at":"%s",
  "message":"refresh completed",
  "details":{
    "dashboard_output":"C:\\private\\dashboard.json",
    "processed_files":5,
    "downloaded_files":1,
    "already_present_files":7,
    "retained_raw_files":21,
    "retained_raw_bytes":2825177750,
    "raw_storage_limit_bytes":10000000000,
    "pruned_raw_files":0,
    "archived_articles":4321,
    "new_archived_articles":17,
    "article_archive_bytes":1876543,
    "title_backfill_attempted_articles":12,
    "title_backfill_updated_articles":9,
    "title_backfill_remaining_articles":3810,
    "title_backfill_downgraded_articles":2
  }
}`, lastSuccess, lastSuccess, lastSuccess)
	if err := os.WriteFile(
		filepath.Join(temporaryRoot, "refresh-status.json"), []byte(status), 0o600,
	); err != nil {
		t.Fatal(err)
	}
	handler := newHandler(
		dataPath,
		filepath.Join(temporaryRoot, "reviews.jsonl"),
		"http://localhost:3000",
		log.New(io.Discard, "", 0),
	)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/admin/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var body adminStatusResponse
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Refresh.Health != "healthy" || body.Refresh.ProcessedFiles != 5 {
		t.Fatalf("response = %+v", body)
	}
	if body.Refresh.RetainedRawBytes != 2825177750 || body.Refresh.RawStorageLimitBytes != 10000000000 {
		t.Fatalf("storage response = %+v", body.Refresh)
	}
	if body.Refresh.ArchivedArticles != 4321 || body.Refresh.NewArchivedArticles != 17 || body.Refresh.ArticleArchiveBytes != 1876543 {
		t.Fatalf("article archive response = %+v", body.Refresh)
	}
	if body.Refresh.TitleBackfillAttempted != 12 || body.Refresh.TitleBackfillUpdated != 9 || body.Refresh.TitleBackfillRemaining != 3810 || body.Refresh.TitleBackfillDowngraded != 2 {
		t.Fatalf("title backfill response = %+v", body.Refresh)
	}
	if strings.Contains(response.Body.String(), "dashboard_output") || strings.Contains(response.Body.String(), "private") {
		t.Fatal("admin status leaked a local path")
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

func TestSnapshotAllowsEachConfiguredDashboardOrigin(t *testing.T) {
	temporaryRoot := t.TempDir()
	dataPath := filepath.Join(temporaryRoot, "dashboard.json")
	if err := os.WriteFile(dataPath, []byte(testDashboard), 0o600); err != nil {
		t.Fatal(err)
	}
	handler := newHandler(
		dataPath,
		filepath.Join(temporaryRoot, "reviews.jsonl"),
		"http://localhost:8088, http://localhost:3000",
		log.New(io.Discard, "", 0),
	)

	for _, origin := range []string{"http://localhost:8088", "http://localhost:3000"} {
		request := httptest.NewRequest(http.MethodGet, "/api/v1/snapshot", nil)
		request.Header.Set("Origin", origin)
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)

		if response.Code != http.StatusOK {
			t.Fatalf("origin %q status = %d, want %d", origin, response.Code, http.StatusOK)
		}
		if got := response.Header().Get("Access-Control-Allow-Origin"); got != origin {
			t.Fatalf("origin %q Access-Control-Allow-Origin = %q", origin, got)
		}
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
			name:        "spreadsheet formula region",
			contentType: "application/json",
			body:        `{"region_code":"-SUM","window_start":"2026-08-20T19:00:00","decision":"uncertain"}`,
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

func saveTestReview(
	t *testing.T,
	handler http.Handler,
	regionCode string,
	windowStart string,
	decision string,
) {
	t.Helper()
	body := fmt.Sprintf(
		`{"region_code":%q,"window_start":%q,"decision":%q}`,
		regionCode,
		windowStart,
		decision,
	)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/reviews", strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusCreated {
		t.Fatalf("save status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestReviewSummaryWaitsForMinimumResolvedSample(t *testing.T) {
	handler := testHandler(t, testDashboard)
	readSummary := func() reviewSummaryResponse {
		request := httptest.NewRequest(http.MethodGet, "/api/v1/reviews/summary", nil)
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		var summary reviewSummaryResponse
		if err := json.Unmarshal(response.Body.Bytes(), &summary); err != nil {
			t.Fatal(err)
		}
		if response.Code != http.StatusOK {
			t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
		}
		return summary
	}
	for index := 0; index < minimumReviewSample-1; index++ {
		decision := "confirmed_event"
		if index >= 15 {
			decision = "irrelevant_news"
		}
		saveTestReview(
			t,
			handler,
			fmt.Sprintf("TEST%02d", index),
			"2026-08-20T19:00:00",
			decision,
		)
	}
	collecting := readSummary()
	if collecting.Status != "collecting_labels" || collecting.RemainingToSample != 1 {
		t.Fatalf("collecting summary = %+v", collecting)
	}
	if collecting.ConfirmedEventRate != nil || collecting.IrrelevantNewsRate != nil {
		t.Fatalf("rates must be withheld before the minimum: %+v", collecting)
	}
	saveTestReview(t, handler, "TEST19", "2026-08-20T19:00:00", "irrelevant_news")
	saveTestReview(t, handler, "UNCERTAIN", "2026-08-20T19:00:00", "uncertain")

	summary := readSummary()
	if summary.TotalReviews != 21 || summary.ResolvedReviews != 20 || summary.Uncertain != 1 {
		t.Fatalf("summary counts = %+v", summary)
	}
	if summary.Status != "sample_ready" || summary.RemainingToSample != 0 {
		t.Fatalf("summary readiness = %+v", summary)
	}
	if summary.ConfirmedEventRate == nil || *summary.ConfirmedEventRate != 0.75 {
		t.Fatalf("confirmed event rate = %v", summary.ConfirmedEventRate)
	}
	if summary.IrrelevantNewsRate == nil || *summary.IrrelevantNewsRate != 0.25 {
		t.Fatalf("irrelevant news rate = %v", summary.IrrelevantNewsRate)
	}
}

func TestReviewExportReturnsLatestLabelsAsCSV(t *testing.T) {
	handler := testHandler(t, testDashboard)
	saveTestReview(t, handler, "US:USHI", "2026-08-20T19:00:00", "confirmed_event")
	saveTestReview(t, handler, "US:USMN", "2026-08-20T20:00:00", "irrelevant_news")

	request := httptest.NewRequest(http.MethodGet, "/api/v1/reviews/export.csv", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if got := response.Header().Get("Content-Disposition"); !strings.Contains(got, "crisispulse-reviews.csv") {
		t.Fatalf("Content-Disposition = %q", got)
	}
	rows, err := csv.NewReader(strings.NewReader(response.Body.String())).ReadAll()
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 3 || rows[0][0] != "signal_id" {
		t.Fatalf("CSV rows = %+v", rows)
	}
}

func TestSpreadsheetSafeNeutralizesFormulaPrefixes(t *testing.T) {
	for _, value := range []string{"=1+1", "+cmd", "-2", "@SUM(A1:A2)", "  =1+1"} {
		if got := spreadsheetSafe(value); !strings.HasPrefix(got, "'") {
			t.Fatalf("spreadsheetSafe(%q) = %q", value, got)
		}
	}
	if got := spreadsheetSafe("US:USHI"); got != "US:USHI" {
		t.Fatalf("safe value changed to %q", got)
	}
}
