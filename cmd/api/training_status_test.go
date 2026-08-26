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

func testTrainingStatusHandler(t *testing.T) (http.Handler, string) {
	t.Helper()
	root := t.TempDir()
	dataPath := filepath.Join(root, "dashboard.json")
	if err := os.WriteFile(dataPath, []byte(testDashboard), 0o600); err != nil {
		t.Fatal(err)
	}
	reviewPath := filepath.Join(root, "reviews.jsonl")
	return newHandler(dataPath, reviewPath, "http://localhost:3000", log.New(io.Discard, "", 0)), filepath.Join(root, articleBaselineReportFilename)
}

func baselineCounts(each int) map[string]any {
	return map[string]any{
		"reported_flooding":  each,
		"flood_risk_warning": each,
		"heavy_rain_only":    each,
		"not_flood_related":  each,
	}
}

func baselineGate(name string, actual, minimum any) map[string]any {
	passed := false
	switch typedMinimum := minimum.(type) {
	case bool:
		passed = actual == typedMinimum
	case int:
		passed = actual.(int) >= typedMinimum
	case float64:
		passed = actual.(float64) >= typedMinimum
	}
	return map[string]any{"name": name, "actual": actual, "minimum": minimum, "passed": passed}
}

func baselineGates(smoke, computed bool) []any {
	totalMinimum, classMinimum, dateMinimum, publisherMinimum := 500, 100, 30, 100
	trainingMinimum, validationMinimum, testMinimum := 60, 15, 20
	totalActual, classActual, dateActual, publisherActual := 4, 1, 1, 4
	if smoke {
		totalMinimum, classMinimum, dateMinimum, publisherMinimum = 16, 4, 3, 12
		trainingMinimum, validationMinimum, testMinimum = 2, 1, 1
	}
	if computed {
		totalActual, classActual, dateActual, publisherActual = 16, 4, 16, 16
	}
	gates := []any{
		baselineGate("total_usable_rows", totalActual, totalMinimum),
		baselineGate("minimum_rows_in_each_class", classActual, classMinimum),
		baselineGate("distinct_article_dates", dateActual, dateMinimum),
		baselineGate("publisher_groups", publisherActual, publisherMinimum),
		baselineGate("inference_text_coverage", 1.0, map[bool]float64{true: 1.0, false: 0.95}[smoke]),
	}
	if !computed {
		return append(gates, baselineGate("leakage_safe_split_computable", false, true))
	}
	return append(gates,
		baselineGate("training_rows_in_each_class_after_purge", 2, trainingMinimum),
		baselineGate("validation_rows_in_each_class_after_purge", 1, validationMinimum),
		baselineGate("test_rows_in_each_class_after_purge", 1, testMinimum),
	)
}

func baselineReadiness(smoke, computed bool) map[string]any {
	classCounts := baselineCounts(1)
	if computed {
		classCounts = baselineCounts(4)
	}
	splitCounts := map[string]any{}
	if computed {
		splitCounts = map[string]any{
			"training":   baselineCounts(2),
			"validation": baselineCounts(1),
			"test":       baselineCounts(1),
		}
	}
	ready := smoke && computed
	return map[string]any{
		"ready":               ready,
		"gates":               baselineGates(smoke, computed),
		"usable_class_counts": classCounts,
		"split_class_counts":  splitCounts,
	}
}

func baselineReportFixture(computed, trained bool) map[string]any {
	rows := 4
	status := "not_ready"
	split := map[string]any{
		"computable": false,
		"reason":     "at least three distinct collection timestamps are required",
	}
	production := baselineReadiness(false, false)
	smoke := baselineReadiness(true, false)
	if computed {
		rows = 16
		split = map[string]any{
			"method":                             "chronological_70_15_15_then_story_promotion_and_final_publisher_purge",
			"time_field":                         "seen_at",
			"validation_boundary":                "2026-01-12T00:00:00+00:00",
			"test_boundary":                      "2026-01-14T00:00:00+00:00",
			"story_rows_promoted_to_newer_split": 0,
			"earlier_rows_purged_for_final_publishers": 0,
			"story_overlap_after_purge":                false,
			"final_publisher_overlap_after_purge":      false,
			"training_rows":                            8,
			"validation_rows":                          4,
			"test_rows":                                4,
		}
		production = baselineReadiness(false, true)
		smoke = baselineReadiness(true, true)
		status = "ready_for_non_evaluative_smoke_test"
	}
	report := map[string]any{
		"report_schema_version":           1,
		"dataset_contract":                articleBaselineDatasetContract,
		"dataset_fingerprint":             "sha256:" + strings.Repeat("0", 64),
		"created_at":                      "2026-08-25T12:00:00+00:00",
		"inputs":                          map[string]any{"reviews": `C:\private\reviews.jsonl`, "archive": `C:\private\archive.parquet`},
		"status":                          status,
		"training_performed":              trained,
		"latest_review_count":             rows,
		"resolved_schema_v2_count":        rows,
		"usable_training_rows":            rows,
		"label_counts_before_text_filter": baselineCounts(rows / 4),
		"exclusion_counts":                map[string]any{},
		"safeguards":                      map[string]any{"input_contract": articleBaselineDatasetContract},
		"split":                           split,
		"production_readiness":            production,
		"smoke_test_readiness":            smoke,
		"interpretation":                  map[string]any{"production_claim": "not production ready"},
	}
	if trained {
		report["status"] = "non_evaluative_smoke_test_completed"
		report["evaluation_tier"] = "NON_EVALUATIVE_SMOKE_TEST"
		report["metrics"] = map[string]any{"private_detail": "not exposed"}
		report["raw_predictions"] = `C:\private\predictions.parquet`
		report["runtime"] = map[string]any{"execution_device": "CPU"}
	}
	return report
}

func writeBaselineReport(t *testing.T, path string, report map[string]any) {
	t.Helper()
	raw, err := json.Marshal(report)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatal(err)
	}
}

func TestTrainingStatusReturnsSanitizedReadinessReport(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	writeBaselineReport(t, path, baselineReportFixture(false, false))
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if response.Header().Get("Cache-Control") != "no-store" {
		t.Fatalf("Cache-Control = %q", response.Header().Get("Cache-Control"))
	}
	if strings.Contains(response.Body.String(), "private") || strings.Contains(response.Body.String(), "inputs") || strings.Contains(response.Body.String(), "metrics") {
		t.Fatalf("response exposed private report fields: %s", response.Body.String())
	}
	var result articleBaselineStatusResponse
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.Status != "not_ready" || result.TrainingPerformed || result.LatestReviewCount != 4 || result.ResolvedSchemaV2Count != 4 || result.UsableTrainingRows != 4 || result.BlockedReason != "readiness_gates_not_met" {
		t.Fatalf("response = %+v", result)
	}
	if result.DatasetFingerprint != "sha256:"+strings.Repeat("0", 64) {
		t.Fatalf("dataset fingerprint = %q", result.DatasetFingerprint)
	}
	if result.Split.Computable || result.Split.Reason != "insufficient_data_for_leakage_safe_split" || len(result.ClassCountsBeforeTextFilter) != 4 || len(result.ClassCountsAfterTextFilter) != 4 || len(result.ProductionReadiness.Gates) != 6 || len(result.SmokeTestReadiness.Gates) != 6 {
		t.Fatalf("response = %+v", result)
	}
}

func TestTrainingStatusReturnsCompletedSmokeTierAndSplit(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	writeBaselineReport(t, path, baselineReportFixture(true, true))
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var result articleBaselineStatusResponse
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.Status != "non_evaluative_smoke_test_completed" || !result.TrainingPerformed || result.EvaluationTier != "NON_EVALUATIVE_SMOKE_TEST" || !result.Split.Computable || result.Split.TrainingRows != 8 || result.Split.ValidationRows != 4 || result.Split.TestRows != 4 || !result.SmokeTestReadiness.Ready || result.ProductionReadiness.Ready {
		t.Fatalf("response = %+v", result)
	}
	if result.Split.ClassCounts["training"]["reported_flooding"] != 2 {
		t.Fatalf("split class counts = %+v", result.Split.ClassCounts)
	}
}

func TestTrainingStatusReturnsOnlyValidatedAggregateGeography(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	report := baselineReportFixture(true, false)
	report["report_schema_version"] = 2
	report["latest_reviewed_at"] = "2026-08-25T11:59:00+00:00"
	report["geography_summary"] = map[string]any{
		"meaning":            articleBaselineMapMeaning,
		"source":             articleBaselineMapSource,
		"usable_rows":        16,
		"mappable_rows":      3,
		"unmappable_rows":    13,
		"unique_locations":   1,
		"locations_returned": 1,
		"truncated":          false,
		"locations": []any{map[string]any{
			"location_name": strings.Repeat("é", 240),
			"country_code":  "US",
			"latitude":      40.0583,
			"longitude":     -74.4057,
			"article_count": 3,
			"class_counts": map[string]any{
				"reported_flooding":  2,
				"flood_risk_warning": 1,
				"heavy_rain_only":    0,
				"not_flood_related":  0,
			},
		}},
	}
	writeBaselineReport(t, path, report)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var result articleBaselineStatusResponse
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.GeographySummary == nil || result.GeographySummary.MappableRows != 3 || len(result.GeographySummary.Locations) != 1 || result.GeographySummary.Locations[0].ArticleCount != 3 {
		t.Fatalf("geography = %+v", result.GeographySummary)
	}
	geographyJSON, err := json.Marshal(result.GeographySummary)
	if err != nil {
		t.Fatal(err)
	}
	for _, privateField := range []string{"article_id", "source_domain", "reviewed_at", "title", "url"} {
		if strings.Contains(string(geographyJSON), privateField) {
			t.Fatalf("geography response exposed %q: %s", privateField, geographyJSON)
		}
	}
}

func TestTrainingStatusRejectsInvalidGeography(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	report := baselineReportFixture(true, false)
	report["report_schema_version"] = 2
	report["latest_reviewed_at"] = "2026-08-25T11:59:00+00:00"
	report["geography_summary"] = map[string]any{
		"meaning":            articleBaselineMapMeaning,
		"source":             articleBaselineMapSource,
		"usable_rows":        16,
		"mappable_rows":      1,
		"unmappable_rows":    15,
		"unique_locations":   1,
		"locations_returned": 1,
		"truncated":          false,
		"locations": []any{map[string]any{
			"location_name": "Impossible",
			"country_code":  "",
			"latitude":      95.0,
			"longitude":     0.0,
			"article_count": 1,
			"class_counts": map[string]any{
				"reported_flooding":  1,
				"flood_risk_warning": 0,
				"heavy_rain_only":    0,
				"not_flood_related":  0,
			},
		}},
	}
	writeBaselineReport(t, path, report)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestTrainingStatusRejectsSchemaV2WithoutNewRequiredFields(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	report := baselineReportFixture(false, false)
	report["report_schema_version"] = 2
	writeBaselineReport(t, path, report)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestTrainingStatusMissingReportReturnsNotFound(t *testing.T) {
	handler, _ := testTrainingStatusHandler(t)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusNotFound || !strings.Contains(response.Body.String(), "training status report not found") {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestTrainingStatusMalformedReportFailsClosed(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	report := baselineReportFixture(false, false)
	report["label_counts_before_text_filter"] = map[string]any{"reported_flooding": 4}
	writeBaselineReport(t, path, report)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable || response.Body.String() != "{\"error\":\"training status report unavailable\"}\n" {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestTrainingStatusInconsistentGateFailsClosed(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	report := baselineReportFixture(false, false)
	production := report["production_readiness"].(map[string]any)
	gates := production["gates"].([]any)
	gates[0].(map[string]any)["actual"] = 5
	writeBaselineReport(t, path, report)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestTrainingStatusMissingRequiredFieldFailsClosed(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	report := baselineReportFixture(false, false)
	delete(report, "training_performed")
	writeBaselineReport(t, path, report)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestTrainingStatusOversizedReportFailsClosed(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	if err := os.WriteFile(path, bytesOfLength(maxArticleBaselineReportBytes+1), 0o600); err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func bytesOfLength(length int) []byte {
	return []byte(strings.Repeat(" ", length))
}

func TestTrainingStatusRejectsWrites(t *testing.T) {
	handler, _ := testTrainingStatusHandler(t)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/training/status", strings.NewReader(`{}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusMethodNotAllowed || response.Header().Get("Allow") != "GET, HEAD" {
		t.Fatalf("status = %d, Allow = %q, body = %s", response.Code, response.Header().Get("Allow"), response.Body.String())
	}
}
