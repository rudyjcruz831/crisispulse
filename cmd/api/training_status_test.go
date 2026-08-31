package main

import (
	"encoding/json"
	"io"
	"log"
	"math"
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

func baselineEvaluation(matrix [][]int) map[string]any {
	columns := make([]int, len(articleBaselineClassLabels))
	rows := make([]int, len(articleBaselineClassLabels))
	diagonal := 0
	for rowIndex, row := range matrix {
		for columnIndex, count := range row {
			rows[rowIndex] += count
			columns[columnIndex] += count
			if rowIndex == columnIndex {
				diagonal += count
			}
		}
	}
	round := func(value float64) float64 {
		return math.Round(value*1_000_000) / 1_000_000
	}
	ratio := func(numerator, denominator int) float64 {
		if denominator == 0 {
			return 0
		}
		return float64(numerator) / float64(denominator)
	}
	perClass := make(map[string]any, len(articleBaselineClassLabels))
	macroF1 := 0.0
	for index, label := range articleBaselineClassLabels {
		precision := ratio(matrix[index][index], columns[index])
		recall := ratio(matrix[index][index], rows[index])
		f1 := 0.0
		if precision+recall > 0 {
			f1 = 2 * precision * recall / (precision + recall)
		}
		macroF1 += f1
		perClass[label] = map[string]any{
			"precision": round(precision),
			"recall":    round(recall),
			"f1":        round(f1),
			"support":   rows[index],
		}
	}
	total := 0
	for _, count := range rows {
		total += count
	}
	return map[string]any{
		"accuracy":                     round(ratio(diagonal, total)),
		"macro_f1":                     round(macroF1 / float64(len(articleBaselineClassLabels))),
		"per_class":                    perClass,
		"confusion_matrix":             matrix,
		"confusion_matrix_label_order": articleBaselineClassLabels,
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
		perfect := baselineEvaluation([][]int{{1, 0, 0, 0}, {0, 1, 0, 0}, {0, 0, 1, 0}, {0, 0, 0, 1}})
		swapped := baselineEvaluation([][]int{{0, 1, 0, 0}, {1, 0, 0, 0}, {0, 0, 1, 0}, {0, 0, 0, 1}})
		report["status"] = "non_evaluative_smoke_test_completed"
		report["evaluation_tier"] = "NON_EVALUATIVE_SMOKE_TEST"
		report["metrics"] = map[string]any{
			"model": map[string]any{
				"type":       articleBaselineModelType,
				"validation": perfect,
				"test":       swapped,
			},
			"comparators": map[string]any{
				"dummy_prior_test":          swapped,
				"frozen_keyword_rules_test": perfect,
			},
			"test_slices": map[string]any{"private_detail": "not exposed"},
			"abstention": map[string]any{
				"threshold":                   0.55,
				"abstained_rows":              4,
				"covered_rows":                0,
				"coverage":                    0.0,
				"covered_test_metrics":        nil,
				"threshold_was_tuned_on_test": false,
			},
			"feature_dimensions": 64,
		}
		report["raw_predictions"] = `C:\private\predictions.parquet`
		report["runtime"] = map[string]any{
			"scikit_learn_version": "1.9.0",
			"random_seed":          42,
			"execution_device":     "CPU",
		}
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
	if result.Results != nil {
		t.Fatalf("untrained response exposed results: %+v", result.Results)
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
	if result.Results == nil || result.Results.ModelType != articleBaselineModelType || result.Results.FeatureDimensions != 64 || result.Results.Runtime.ExecutionDevice != "CPU" || result.Results.Runtime.Library != "scikit-learn" || result.Results.Runtime.LibraryVersion != "1.9.0" || result.Results.Runtime.RandomSeed != 42 {
		t.Fatalf("results = %+v", result.Results)
	}
	if result.Results.Validation.Accuracy != 1 || result.Results.Test.Accuracy != 0.5 || result.Results.Baselines.FrozenKeywordRulesTest.Accuracy != 1 || result.Results.Abstention.AbstainedRows != 4 || result.Results.Abstention.CoveredRows != 0 || len(result.Results.RepresentativeMistakes) != 2 {
		t.Fatalf("results = %+v", result.Results)
	}
	firstMistake := result.Results.RepresentativeMistakes[0]
	secondMistake := result.Results.RepresentativeMistakes[1]
	if firstMistake.ActualLabel != "reported_flooding" || firstMistake.PredictedLabel != "flood_risk_warning" || firstMistake.Count != 1 || secondMistake.ActualLabel != "flood_risk_warning" || secondMistake.PredictedLabel != "reported_flooding" || secondMistake.Count != 1 {
		t.Fatalf("representative mistakes = %+v", result.Results.RepresentativeMistakes)
	}
	for _, privateField := range []string{"raw_predictions", "test_slices", "covered_test_metrics", `C:\\private`} {
		if strings.Contains(response.Body.String(), privateField) {
			t.Fatalf("response exposed %q: %s", privateField, response.Body.String())
		}
	}
}

func TestTrainingStatusRejectsInconsistentTrainingMetrics(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	report := baselineReportFixture(true, true)
	metrics := report["metrics"].(map[string]any)
	model := metrics["model"].(map[string]any)
	testMetrics := model["test"].(map[string]any)
	testMetrics["accuracy"] = 0.75
	writeBaselineReport(t, path, report)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable || response.Body.String() != "{\"error\":\"training status report unavailable\"}\n" {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestTrainingStatusRejectsUnsafeTrainingRuntime(t *testing.T) {
	handler, path := testTrainingStatusHandler(t)
	report := baselineReportFixture(true, true)
	runtime := report["runtime"].(map[string]any)
	runtime["scikit_learn_version"] = "<script>"
	writeBaselineReport(t, path, report)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/status", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
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
