package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"
	"unicode/utf8"
)

const (
	articleBaselineReportFilename       = "article-baseline-report.json"
	articleBaselineReportSchemaVersion  = 2
	articleBaselineMinimumSchemaVersion = 1
	articleBaselineDatasetContract      = "crisispulse_native_article_reviews_v2"
	maxArticleBaselineReportBytes       = 512 << 10
	maxArticleBaselineMapLocations      = 250
	articleBaselineMapMeaning           = "article_mentioned_locations_not_verified_events"
	articleBaselineMapSource            = "gdelt_primary_location_from_permanent_article_archive"
)

var articleBaselineClassLabels = []string{
	"reported_flooding",
	"flood_risk_warning",
	"heavy_rain_only",
	"not_flood_related",
}

var articleBaselineExclusionReasons = map[string]struct{}{
	"legacy_schema":               {},
	"uncertain":                   {},
	"unsupported_schema_or_label": {},
	"missing_archive_row":         {},
	"missing_seen_at":             {},
	"missing_publisher_group":     {},
	"missing_story_group":         {},
	"missing_inference_text":      {},
}

type articleBaselineGate struct {
	Name    string `json:"name"`
	Actual  any    `json:"actual"`
	Minimum any    `json:"minimum"`
	Passed  bool   `json:"passed"`
}

type articleBaselineReadinessFile struct {
	Ready             bool                      `json:"ready"`
	Gates             []articleBaselineGate     `json:"gates"`
	UsableClassCounts map[string]int            `json:"usable_class_counts"`
	SplitClassCounts  map[string]map[string]int `json:"split_class_counts"`
}

type articleBaselineSplitFile struct {
	Computable                          *bool  `json:"computable,omitempty"`
	Reason                              string `json:"reason,omitempty"`
	Method                              string `json:"method,omitempty"`
	TimeField                           string `json:"time_field,omitempty"`
	ValidationBoundary                  string `json:"validation_boundary,omitempty"`
	TestBoundary                        string `json:"test_boundary,omitempty"`
	StoryRowsPromoted                   int    `json:"story_rows_promoted_to_newer_split,omitempty"`
	EarlierRowsPurgedForFinalPublishers int    `json:"earlier_rows_purged_for_final_publishers,omitempty"`
	StoryOverlapAfterPurge              bool   `json:"story_overlap_after_purge,omitempty"`
	FinalPublisherOverlapAfterPurge     bool   `json:"final_publisher_overlap_after_purge,omitempty"`
	TrainingRows                        int    `json:"training_rows,omitempty"`
	ValidationRows                      int    `json:"validation_rows,omitempty"`
	TestRows                            int    `json:"test_rows,omitempty"`
}

type articleBaselineMapLocation struct {
	LocationName string         `json:"location_name"`
	CountryCode  string         `json:"country_code"`
	Latitude     float64        `json:"latitude"`
	Longitude    float64        `json:"longitude"`
	ArticleCount int            `json:"article_count"`
	ClassCounts  map[string]int `json:"class_counts"`
}

type articleBaselineGeographySummary struct {
	Meaning           string                       `json:"meaning"`
	Source            string                       `json:"source"`
	UsableRows        int                          `json:"usable_rows"`
	MappableRows      int                          `json:"mappable_rows"`
	UnmappableRows    int                          `json:"unmappable_rows"`
	UniqueLocations   int                          `json:"unique_locations"`
	LocationsReturned int                          `json:"locations_returned"`
	Truncated         bool                         `json:"truncated"`
	Locations         []articleBaselineMapLocation `json:"locations"`
}

type articleBaselineReportFile struct {
	ReportSchemaVersion         int                              `json:"report_schema_version"`
	DatasetContract             string                           `json:"dataset_contract"`
	DatasetFingerprint          string                           `json:"dataset_fingerprint"`
	CreatedAt                   string                           `json:"created_at"`
	Inputs                      json.RawMessage                  `json:"inputs"`
	Status                      string                           `json:"status"`
	TrainingPerformed           bool                             `json:"training_performed"`
	EvaluationTier              string                           `json:"evaluation_tier,omitempty"`
	LatestReviewCount           int                              `json:"latest_review_count"`
	LatestReviewedAt            string                           `json:"latest_reviewed_at,omitempty"`
	ResolvedSchemaV2Count       int                              `json:"resolved_schema_v2_count"`
	UsableTrainingRows          int                              `json:"usable_training_rows"`
	GeographySummary            *articleBaselineGeographySummary `json:"geography_summary,omitempty"`
	LabelCountsBeforeTextFilter map[string]int                   `json:"label_counts_before_text_filter"`
	ExclusionCounts             map[string]int                   `json:"exclusion_counts"`
	Safeguards                  json.RawMessage                  `json:"safeguards"`
	Split                       articleBaselineSplitFile         `json:"split"`
	ProductionReadiness         articleBaselineReadinessFile     `json:"production_readiness"`
	SmokeTestReadiness          articleBaselineReadinessFile     `json:"smoke_test_readiness"`
	Interpretation              json.RawMessage                  `json:"interpretation"`
	BlockedReason               string                           `json:"blocked_reason,omitempty"`
	Metrics                     json.RawMessage                  `json:"metrics,omitempty"`
	RawPredictions              string                           `json:"raw_predictions,omitempty"`
	Runtime                     json.RawMessage                  `json:"runtime,omitempty"`
}

type articleBaselineSplitSummary struct {
	Computable                          bool                      `json:"computable"`
	Reason                              string                    `json:"reason,omitempty"`
	Method                              string                    `json:"method,omitempty"`
	TimeField                           string                    `json:"time_field,omitempty"`
	ValidationBoundary                  string                    `json:"validation_boundary,omitempty"`
	TestBoundary                        string                    `json:"test_boundary,omitempty"`
	StoryRowsPromoted                   int                       `json:"story_rows_promoted_to_newer_split"`
	EarlierRowsPurgedForFinalPublishers int                       `json:"earlier_rows_purged_for_final_publishers"`
	StoryOverlapAfterPurge              bool                      `json:"story_overlap_after_purge"`
	FinalPublisherOverlapAfterPurge     bool                      `json:"final_publisher_overlap_after_purge"`
	TrainingRows                        int                       `json:"training_rows"`
	ValidationRows                      int                       `json:"validation_rows"`
	TestRows                            int                       `json:"test_rows"`
	ClassCounts                         map[string]map[string]int `json:"class_counts"`
}

type articleBaselineReadinessSummary struct {
	Ready bool                  `json:"ready"`
	Gates []articleBaselineGate `json:"gates"`
}

type articleBaselineStatusResponse struct {
	ReportSchemaVersion         int                              `json:"report_schema_version"`
	Status                      string                           `json:"status"`
	TrainingPerformed           bool                             `json:"training_performed"`
	EvaluationTier              string                           `json:"evaluation_tier,omitempty"`
	CreatedAt                   string                           `json:"created_at"`
	LatestReviewCount           int                              `json:"latest_review_count"`
	LatestReviewedAt            string                           `json:"latest_reviewed_at,omitempty"`
	DatasetFingerprint          string                           `json:"dataset_fingerprint"`
	ResolvedSchemaV2Count       int                              `json:"resolved_schema_v2_count"`
	UsableTrainingRows          int                              `json:"usable_training_rows"`
	GeographySummary            *articleBaselineGeographySummary `json:"geography_summary,omitempty"`
	ExclusionCounts             map[string]int                   `json:"exclusion_counts"`
	ClassCountsBeforeTextFilter map[string]int                   `json:"class_counts_before_text_filter"`
	ClassCountsAfterTextFilter  map[string]int                   `json:"class_counts_after_text_filter"`
	Split                       articleBaselineSplitSummary      `json:"split"`
	ProductionReadiness         articleBaselineReadinessSummary  `json:"production_readiness"`
	SmokeTestReadiness          articleBaselineReadinessSummary  `json:"smoke_test_readiness"`
	BlockedReason               string                           `json:"blocked_reason,omitempty"`
}

func (service *api) trainingStatus(writer http.ResponseWriter, request *http.Request) {
	if !requireGet(writer, request) {
		return
	}
	response, err := loadArticleBaselineStatus(service.trainingStatusPath)
	if errors.Is(err, os.ErrNotExist) {
		writeError(writer, http.StatusNotFound, "training status report not found")
		return
	}
	if err != nil {
		service.logger.Printf("training status unavailable: %v", err)
		writeError(writer, http.StatusServiceUnavailable, "training status report unavailable")
		return
	}
	writer.Header().Set("Cache-Control", "no-store")
	writeJSON(writer, http.StatusOK, response)
}

func loadArticleBaselineStatus(path string) (articleBaselineStatusResponse, error) {
	var response articleBaselineStatusResponse
	file, err := os.Open(path)
	if err != nil {
		return response, err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return response, err
	}
	if !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > maxArticleBaselineReportBytes {
		return response, errors.New("invalid article baseline report file")
	}
	raw, err := io.ReadAll(io.LimitReader(file, maxArticleBaselineReportBytes+1))
	if err != nil {
		return response, err
	}
	if len(raw) > maxArticleBaselineReportBytes {
		return response, errors.New("article baseline report exceeds size limit")
	}
	if err := requireArticleBaselineReportFields(raw); err != nil {
		return response, err
	}

	var report articleBaselineReportFile
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	decoder.UseNumber()
	if err := decoder.Decode(&report); err != nil {
		return response, errors.New("invalid article baseline report")
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return response, errors.New("invalid article baseline report")
	}
	return sanitizeArticleBaselineReport(report)
}

func sanitizeArticleBaselineReport(report articleBaselineReportFile) (articleBaselineStatusResponse, error) {
	var response articleBaselineStatusResponse
	if report.ReportSchemaVersion < articleBaselineMinimumSchemaVersion || report.ReportSchemaVersion > articleBaselineReportSchemaVersion || report.DatasetContract != articleBaselineDatasetContract {
		return response, errors.New("unsupported article baseline report contract")
	}
	fingerprint, found := strings.CutPrefix(report.DatasetFingerprint, "sha256:")
	if !found || !validSHA256(fingerprint) || fingerprint != strings.ToLower(fingerprint) {
		return response, errors.New("invalid article baseline dataset fingerprint")
	}
	if _, err := time.Parse(time.RFC3339Nano, report.CreatedAt); err != nil {
		return response, errors.New("invalid article baseline report timestamp")
	}
	if report.ReportSchemaVersion >= 2 {
		if report.GeographySummary == nil {
			return response, errors.New("article baseline report is missing geography summary")
		}
		if report.LatestReviewCount > 0 {
			if _, err := time.Parse(time.RFC3339Nano, report.LatestReviewedAt); err != nil {
				return response, errors.New("invalid article baseline latest review timestamp")
			}
		} else if report.LatestReviewedAt != "" {
			return response, errors.New("unexpected article baseline latest review timestamp")
		}
	} else if report.GeographySummary != nil || report.LatestReviewedAt != "" {
		return response, errors.New("schema-v1 article baseline report contains schema-v2 fields")
	}
	if report.LatestReviewCount < 0 || report.ResolvedSchemaV2Count < 0 || report.UsableTrainingRows < 0 || report.ResolvedSchemaV2Count > report.LatestReviewCount || report.UsableTrainingRows > report.ResolvedSchemaV2Count {
		return response, errors.New("invalid article baseline report counts")
	}
	if err := validateArticleBaselineClassCounts(report.LabelCountsBeforeTextFilter, false); err != nil {
		return response, fmt.Errorf("invalid class counts before text filter: %w", err)
	}
	if err := validateArticleBaselineExclusions(report.ExclusionCounts); err != nil {
		return response, err
	}
	if sumArticleBaselineCounts(report.LabelCountsBeforeTextFilter) != report.ResolvedSchemaV2Count || report.UsableTrainingRows+sumArticleBaselineCounts(report.ExclusionCounts) != report.LatestReviewCount {
		return response, errors.New("inconsistent article baseline report counts")
	}

	computedSplit, splitSummary, err := sanitizeArticleBaselineSplit(report.Split, report.UsableTrainingRows)
	if err != nil {
		return response, err
	}
	productionMinimums := map[string]any{
		"total_usable_rows":                         int64(500),
		"minimum_rows_in_each_class":                int64(100),
		"distinct_article_dates":                    int64(30),
		"publisher_groups":                          int64(100),
		"inference_text_coverage":                   0.95,
		"training_rows_in_each_class_after_purge":   int64(60),
		"validation_rows_in_each_class_after_purge": int64(15),
		"test_rows_in_each_class_after_purge":       int64(20),
	}
	smokeMinimums := map[string]any{
		"total_usable_rows":                         int64(16),
		"minimum_rows_in_each_class":                int64(4),
		"distinct_article_dates":                    int64(3),
		"publisher_groups":                          int64(12),
		"inference_text_coverage":                   1.0,
		"training_rows_in_each_class_after_purge":   int64(2),
		"validation_rows_in_each_class_after_purge": int64(1),
		"test_rows_in_each_class_after_purge":       int64(1),
	}
	production, err := sanitizeArticleBaselineReadiness(report.ProductionReadiness, productionMinimums, computedSplit)
	if err != nil {
		return response, fmt.Errorf("invalid production readiness: %w", err)
	}
	smoke, err := sanitizeArticleBaselineReadiness(report.SmokeTestReadiness, smokeMinimums, computedSplit)
	if err != nil {
		return response, fmt.Errorf("invalid smoke-test readiness: %w", err)
	}
	if !equalArticleBaselineClassCounts(report.ProductionReadiness.UsableClassCounts, report.SmokeTestReadiness.UsableClassCounts) || sumArticleBaselineCounts(report.ProductionReadiness.UsableClassCounts) != report.UsableTrainingRows {
		return response, errors.New("inconsistent usable class counts")
	}
	if !equalArticleBaselineSplitCounts(report.ProductionReadiness.SplitClassCounts, report.SmokeTestReadiness.SplitClassCounts) {
		return response, errors.New("inconsistent split class counts")
	}
	if err := validateArticleBaselineReadinessActuals(report.ProductionReadiness, report.UsableTrainingRows, report.ResolvedSchemaV2Count, computedSplit); err != nil {
		return response, fmt.Errorf("inconsistent production gate values: %w", err)
	}
	if err := validateArticleBaselineReadinessActuals(report.SmokeTestReadiness, report.UsableTrainingRows, report.ResolvedSchemaV2Count, computedSplit); err != nil {
		return response, fmt.Errorf("inconsistent smoke-test gate values: %w", err)
	}
	if computedSplit {
		if sumArticleBaselineCounts(report.ProductionReadiness.SplitClassCounts["training"]) != splitSummary.TrainingRows ||
			sumArticleBaselineCounts(report.ProductionReadiness.SplitClassCounts["validation"]) != splitSummary.ValidationRows ||
			sumArticleBaselineCounts(report.ProductionReadiness.SplitClassCounts["test"]) != splitSummary.TestRows {
			return response, errors.New("split row counts do not match split class counts")
		}
	}
	if err := validateArticleBaselineStatus(report, production.Ready, smoke.Ready); err != nil {
		return response, err
	}
	geography, err := sanitizeArticleBaselineGeography(report.GeographySummary, report.UsableTrainingRows)
	if err != nil {
		return response, err
	}

	splitSummary.ClassCounts = cloneArticleBaselineSplitCounts(report.ProductionReadiness.SplitClassCounts)
	blockedReason := report.BlockedReason
	if report.Status == "not_ready" && blockedReason == "" {
		blockedReason = "readiness_gates_not_met"
	}
	return articleBaselineStatusResponse{
		ReportSchemaVersion:         report.ReportSchemaVersion,
		Status:                      report.Status,
		TrainingPerformed:           report.TrainingPerformed,
		EvaluationTier:              report.EvaluationTier,
		CreatedAt:                   report.CreatedAt,
		LatestReviewCount:           report.LatestReviewCount,
		LatestReviewedAt:            report.LatestReviewedAt,
		DatasetFingerprint:          report.DatasetFingerprint,
		ResolvedSchemaV2Count:       report.ResolvedSchemaV2Count,
		UsableTrainingRows:          report.UsableTrainingRows,
		GeographySummary:            geography,
		ExclusionCounts:             cloneArticleBaselineCounts(report.ExclusionCounts),
		ClassCountsBeforeTextFilter: cloneArticleBaselineCounts(report.LabelCountsBeforeTextFilter),
		ClassCountsAfterTextFilter:  cloneArticleBaselineCounts(report.ProductionReadiness.UsableClassCounts),
		Split:                       splitSummary,
		ProductionReadiness:         production,
		SmokeTestReadiness:          smoke,
		BlockedReason:               blockedReason,
	}, nil
}

func sanitizeArticleBaselineGeography(
	geography *articleBaselineGeographySummary,
	usableRows int,
) (*articleBaselineGeographySummary, error) {
	if geography == nil {
		return nil, nil
	}
	if geography.Meaning != articleBaselineMapMeaning || geography.Source != articleBaselineMapSource ||
		geography.UsableRows != usableRows || geography.MappableRows < 0 || geography.UnmappableRows < 0 ||
		geography.MappableRows+geography.UnmappableRows != usableRows || geography.UniqueLocations < 0 ||
		geography.LocationsReturned != len(geography.Locations) || geography.LocationsReturned < 0 ||
		geography.LocationsReturned > maxArticleBaselineMapLocations || geography.UniqueLocations < geography.LocationsReturned {
		return nil, errors.New("invalid article baseline geography summary")
	}
	if geography.Truncated {
		if geography.UniqueLocations <= geography.LocationsReturned {
			return nil, errors.New("invalid truncated article baseline geography summary")
		}
	} else if geography.UniqueLocations != geography.LocationsReturned {
		return nil, errors.New("inconsistent article baseline geography locations")
	}

	locations := make([]articleBaselineMapLocation, 0, len(geography.Locations))
	seen := make(map[string]struct{}, len(geography.Locations))
	returnedRows := 0
	for index, location := range geography.Locations {
		if location.LocationName == "" || strings.TrimSpace(location.LocationName) != location.LocationName ||
			utf8.RuneCountInString(location.LocationName) > 240 || strings.TrimSpace(location.CountryCode) != location.CountryCode ||
			len(location.CountryCode) > 8 || math.IsNaN(location.Latitude) || math.IsInf(location.Latitude, 0) ||
			math.IsNaN(location.Longitude) || math.IsInf(location.Longitude, 0) ||
			location.Latitude < -90 || location.Latitude > 90 || location.Longitude < -180 || location.Longitude > 180 ||
			location.ArticleCount <= 0 {
			return nil, fmt.Errorf("invalid article baseline geography location %d", index)
		}
		if err := validateArticleBaselineClassCounts(location.ClassCounts, false); err != nil ||
			sumArticleBaselineCounts(location.ClassCounts) != location.ArticleCount {
			return nil, fmt.Errorf("invalid article baseline geography class counts at location %d", index)
		}
		key := fmt.Sprintf("%s\x00%s\x00%.5f\x00%.5f", location.LocationName, location.CountryCode, location.Latitude, location.Longitude)
		if _, duplicate := seen[key]; duplicate {
			return nil, errors.New("duplicate article baseline geography location")
		}
		seen[key] = struct{}{}
		returnedRows += location.ArticleCount
		locations = append(locations, articleBaselineMapLocation{
			LocationName: location.LocationName,
			CountryCode:  location.CountryCode,
			Latitude:     location.Latitude,
			Longitude:    location.Longitude,
			ArticleCount: location.ArticleCount,
			ClassCounts:  cloneArticleBaselineCounts(location.ClassCounts),
		})
	}
	if returnedRows > geography.MappableRows || (!geography.Truncated && returnedRows != geography.MappableRows) {
		return nil, errors.New("inconsistent article baseline geography row counts")
	}
	return &articleBaselineGeographySummary{
		Meaning:           geography.Meaning,
		Source:            geography.Source,
		UsableRows:        geography.UsableRows,
		MappableRows:      geography.MappableRows,
		UnmappableRows:    geography.UnmappableRows,
		UniqueLocations:   geography.UniqueLocations,
		LocationsReturned: geography.LocationsReturned,
		Truncated:         geography.Truncated,
		Locations:         locations,
	}, nil
}

func requireArticleBaselineReportFields(raw []byte) error {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil || fields == nil {
		return errors.New("invalid article baseline report")
	}
	for _, name := range []string{
		"report_schema_version",
		"dataset_contract",
		"dataset_fingerprint",
		"created_at",
		"inputs",
		"status",
		"training_performed",
		"latest_review_count",
		"resolved_schema_v2_count",
		"usable_training_rows",
		"label_counts_before_text_filter",
		"exclusion_counts",
		"safeguards",
		"split",
		"production_readiness",
		"smoke_test_readiness",
		"interpretation",
	} {
		if _, ok := fields[name]; !ok {
			return errors.New("article baseline report is missing required fields")
		}
	}
	var version int
	if err := json.Unmarshal(fields["report_schema_version"], &version); err != nil {
		return errors.New("invalid article baseline report schema version")
	}
	if version >= 2 {
		for _, name := range []string{"latest_reviewed_at", "geography_summary"} {
			if _, ok := fields[name]; !ok {
				return errors.New("article baseline report is missing schema-v2 fields")
			}
		}
	}
	return nil
}

func sanitizeArticleBaselineSplit(split articleBaselineSplitFile, usableRows int) (bool, articleBaselineSplitSummary, error) {
	computed := split.Computable == nil || *split.Computable
	if !computed {
		if split.Reason != "at least three distinct collection timestamps are required" ||
			split.Method != "" || split.TimeField != "" || split.ValidationBoundary != "" || split.TestBoundary != "" ||
			split.StoryRowsPromoted != 0 || split.EarlierRowsPurgedForFinalPublishers != 0 ||
			split.StoryOverlapAfterPurge || split.FinalPublisherOverlapAfterPurge ||
			split.TrainingRows != 0 || split.ValidationRows != 0 || split.TestRows != 0 {
			return false, articleBaselineSplitSummary{}, errors.New("invalid non-computable article baseline split")
		}
		return false, articleBaselineSplitSummary{
			Computable:  false,
			Reason:      "insufficient_data_for_leakage_safe_split",
			ClassCounts: map[string]map[string]int{},
		}, nil
	}
	if split.Method != "chronological_70_15_15_then_story_promotion_and_final_publisher_purge" || split.TimeField != "seen_at" || split.Reason != "" || split.StoryOverlapAfterPurge || split.FinalPublisherOverlapAfterPurge || split.StoryRowsPromoted < 0 || split.EarlierRowsPurgedForFinalPublishers < 0 || split.TrainingRows < 0 || split.ValidationRows < 0 || split.TestRows < 0 {
		return false, articleBaselineSplitSummary{}, errors.New("invalid computable article baseline split")
	}
	validationBoundary, validationErr := time.Parse(time.RFC3339Nano, split.ValidationBoundary)
	testBoundary, testErr := time.Parse(time.RFC3339Nano, split.TestBoundary)
	if validationErr != nil || testErr != nil || testBoundary.Before(validationBoundary) {
		return false, articleBaselineSplitSummary{}, errors.New("invalid article baseline split boundaries")
	}
	if split.TrainingRows+split.ValidationRows+split.TestRows+split.EarlierRowsPurgedForFinalPublishers != usableRows {
		return false, articleBaselineSplitSummary{}, errors.New("inconsistent article baseline split row counts")
	}
	return true, articleBaselineSplitSummary{
		Computable:                          true,
		Method:                              split.Method,
		TimeField:                           split.TimeField,
		ValidationBoundary:                  split.ValidationBoundary,
		TestBoundary:                        split.TestBoundary,
		StoryRowsPromoted:                   split.StoryRowsPromoted,
		EarlierRowsPurgedForFinalPublishers: split.EarlierRowsPurgedForFinalPublishers,
		StoryOverlapAfterPurge:              split.StoryOverlapAfterPurge,
		FinalPublisherOverlapAfterPurge:     split.FinalPublisherOverlapAfterPurge,
		TrainingRows:                        split.TrainingRows,
		ValidationRows:                      split.ValidationRows,
		TestRows:                            split.TestRows,
	}, nil
}

func sanitizeArticleBaselineReadiness(readiness articleBaselineReadinessFile, expectedMinimums map[string]any, splitComputable bool) (articleBaselineReadinessSummary, error) {
	if err := validateArticleBaselineClassCounts(readiness.UsableClassCounts, false); err != nil {
		return articleBaselineReadinessSummary{}, err
	}
	if err := validateArticleBaselineSplitCounts(readiness.SplitClassCounts, splitComputable); err != nil {
		return articleBaselineReadinessSummary{}, err
	}
	expected := make(map[string]any, len(expectedMinimums))
	for name, minimum := range expectedMinimums {
		expected[name] = minimum
	}
	if !splitComputable {
		delete(expected, "training_rows_in_each_class_after_purge")
		delete(expected, "validation_rows_in_each_class_after_purge")
		delete(expected, "test_rows_in_each_class_after_purge")
		expected["leakage_safe_split_computable"] = true
	}
	if len(readiness.Gates) != len(expected) {
		return articleBaselineReadinessSummary{}, errors.New("unexpected readiness gate count")
	}
	seen := make(map[string]struct{}, len(readiness.Gates))
	allPassed := true
	for index, gate := range readiness.Gates {
		expectedMinimum, ok := expected[gate.Name]
		if !ok {
			return articleBaselineReadinessSummary{}, fmt.Errorf("gate[%d] name is not recognized", index)
		}
		if _, duplicate := seen[gate.Name]; duplicate {
			return articleBaselineReadinessSummary{}, fmt.Errorf("gate[%d] is duplicated", index)
		}
		seen[gate.Name] = struct{}{}
		passed, err := validateArticleBaselineGate(gate, expectedMinimum)
		if err != nil {
			return articleBaselineReadinessSummary{}, fmt.Errorf("gate[%d]: %w", index, err)
		}
		if passed != gate.Passed {
			return articleBaselineReadinessSummary{}, fmt.Errorf("gate[%d] has an inconsistent passed value", index)
		}
		allPassed = allPassed && gate.Passed
	}
	if readiness.Ready != allPassed {
		return articleBaselineReadinessSummary{}, errors.New("readiness status does not match its gates")
	}
	return articleBaselineReadinessSummary{Ready: readiness.Ready, Gates: append([]articleBaselineGate(nil), readiness.Gates...)}, nil
}

func validateArticleBaselineGate(gate articleBaselineGate, expectedMinimum any) (bool, error) {
	switch expected := expectedMinimum.(type) {
	case bool:
		actual, actualOK := gate.Actual.(bool)
		minimum, minimumOK := gate.Minimum.(bool)
		if !actualOK || !minimumOK || minimum != expected {
			return false, errors.New("boolean gate values are invalid")
		}
		return actual == minimum, nil
	case int64:
		actual, err := articleBaselineInteger(gate.Actual)
		if err != nil {
			return false, err
		}
		minimum, err := articleBaselineInteger(gate.Minimum)
		if err != nil || minimum != expected || actual < 0 {
			return false, errors.New("integer gate values are invalid")
		}
		return actual >= minimum, nil
	case float64:
		actual, err := articleBaselineNumber(gate.Actual)
		if err != nil {
			return false, err
		}
		minimum, err := articleBaselineNumber(gate.Minimum)
		if err != nil || minimum != expected || actual < 0 || actual > 1 {
			return false, errors.New("ratio gate values are invalid")
		}
		return actual >= minimum, nil
	default:
		return false, errors.New("unsupported expected gate type")
	}
}

func articleBaselineInteger(value any) (int64, error) {
	number, ok := value.(json.Number)
	if !ok {
		return 0, errors.New("gate value must be an integer")
	}
	parsed, err := number.Int64()
	if err != nil {
		return 0, errors.New("gate value must be an integer")
	}
	return parsed, nil
}

func articleBaselineNumber(value any) (float64, error) {
	number, ok := value.(json.Number)
	if !ok {
		return 0, errors.New("gate value must be numeric")
	}
	parsed, err := number.Float64()
	if err != nil {
		return 0, errors.New("gate value must be numeric")
	}
	return parsed, nil
}

func validateArticleBaselineClassCounts(counts map[string]int, allowEmpty bool) error {
	if allowEmpty && len(counts) == 0 {
		return nil
	}
	if len(counts) != len(articleBaselineClassLabels) {
		return errors.New("class counts must contain exactly four classes")
	}
	for _, label := range articleBaselineClassLabels {
		value, ok := counts[label]
		if !ok || value < 0 {
			return fmt.Errorf("class count %q is missing or negative", label)
		}
	}
	return nil
}

func validateArticleBaselineExclusions(counts map[string]int) error {
	for reason, value := range counts {
		if _, ok := articleBaselineExclusionReasons[reason]; !ok || value < 0 {
			return errors.New("invalid article baseline exclusion counts")
		}
	}
	return nil
}

func validateArticleBaselineSplitCounts(counts map[string]map[string]int, computable bool) error {
	if !computable {
		if len(counts) != 0 {
			return errors.New("non-computable split cannot have class counts")
		}
		return nil
	}
	if len(counts) != 3 {
		return errors.New("split class counts must contain training, validation, and test")
	}
	for _, name := range []string{"training", "validation", "test"} {
		if err := validateArticleBaselineClassCounts(counts[name], false); err != nil {
			return fmt.Errorf("%s split: %w", name, err)
		}
	}
	return nil
}

func validateArticleBaselineStatus(report articleBaselineReportFile, productionReady, smokeReady bool) error {
	valid := false
	switch report.Status {
	case "not_ready":
		valid = !report.TrainingPerformed && !productionReady
	case "ready_for_cpu_baseline":
		valid = !report.TrainingPerformed && productionReady
	case "ready_for_non_evaluative_smoke_test":
		valid = !report.TrainingPerformed && smokeReady && !productionReady
	case "blocked_cpu_baseline":
		valid = !report.TrainingPerformed && !productionReady && report.BlockedReason == "one or more production readiness gates failed"
	case "blocked_non_evaluative_smoke_test":
		valid = !report.TrainingPerformed && !smokeReady && report.BlockedReason == "one or more smoke test readiness gates failed"
	case "offline_cpu_baseline_completed":
		valid = report.TrainingPerformed && productionReady && report.EvaluationTier == "PRELIMINARY_OFFLINE_BASELINE"
	case "non_evaluative_smoke_test_completed":
		valid = report.TrainingPerformed && smokeReady && report.EvaluationTier == "NON_EVALUATIVE_SMOKE_TEST"
	}
	if !valid {
		return errors.New("invalid or inconsistent article baseline status")
	}
	if !report.TrainingPerformed && report.EvaluationTier != "" {
		return errors.New("an untrained report cannot have an evaluation tier")
	}
	if report.TrainingPerformed && (!articleBaselineJSONObject(report.Metrics) || !articleBaselineJSONObject(report.Runtime) || strings.TrimSpace(report.RawPredictions) == "") {
		return errors.New("a trained report must retain metrics, runtime, and raw predictions")
	}
	if !report.TrainingPerformed && (len(report.Metrics) != 0 || len(report.Runtime) != 0 || report.RawPredictions != "") {
		return errors.New("an untrained report cannot contain training artifacts")
	}
	if report.Status != "blocked_cpu_baseline" && report.Status != "blocked_non_evaluative_smoke_test" && report.BlockedReason != "" {
		return errors.New("blocked reason is not valid for this status")
	}
	return nil
}

func articleBaselineJSONObject(raw json.RawMessage) bool {
	candidate := bytes.TrimSpace(raw)
	return len(candidate) >= 2 && candidate[0] == '{' && candidate[len(candidate)-1] == '}'
}

func validateArticleBaselineReadinessActuals(readiness articleBaselineReadinessFile, usableRows, resolvedRows int, splitComputable bool) error {
	gates := make(map[string]articleBaselineGate, len(readiness.Gates))
	for _, gate := range readiness.Gates {
		gates[gate.Name] = gate
	}
	expectedIntegers := map[string]int64{
		"total_usable_rows":          int64(usableRows),
		"minimum_rows_in_each_class": int64(minArticleBaselineCount(readiness.UsableClassCounts)),
	}
	if splitComputable {
		expectedIntegers["training_rows_in_each_class_after_purge"] = int64(minArticleBaselineCount(readiness.SplitClassCounts["training"]))
		expectedIntegers["validation_rows_in_each_class_after_purge"] = int64(minArticleBaselineCount(readiness.SplitClassCounts["validation"]))
		expectedIntegers["test_rows_in_each_class_after_purge"] = int64(minArticleBaselineCount(readiness.SplitClassCounts["test"]))
	} else {
		actual, ok := gates["leakage_safe_split_computable"].Actual.(bool)
		if !ok || actual {
			return errors.New("leakage split gate does not match split metadata")
		}
	}
	for name, expected := range expectedIntegers {
		actual, err := articleBaselineInteger(gates[name].Actual)
		if err != nil || actual != expected {
			return fmt.Errorf("%s actual does not match report counts", name)
		}
	}
	coverage := 0.0
	if resolvedRows > 0 {
		coverage = math.Round(float64(usableRows)/float64(resolvedRows)*1_000_000) / 1_000_000
	}
	actualCoverage, err := articleBaselineNumber(gates["inference_text_coverage"].Actual)
	if err != nil || actualCoverage != coverage {
		return errors.New("inference_text_coverage actual does not match report counts")
	}
	return nil
}

func minArticleBaselineCount(counts map[string]int) int {
	minimum := 0
	for index, label := range articleBaselineClassLabels {
		value := counts[label]
		if index == 0 || value < minimum {
			minimum = value
		}
	}
	return minimum
}

func sumArticleBaselineCounts(counts map[string]int) int {
	total := 0
	for _, value := range counts {
		total += value
	}
	return total
}

func equalArticleBaselineClassCounts(left, right map[string]int) bool {
	if len(left) != len(right) {
		return false
	}
	for key, value := range left {
		if right[key] != value {
			return false
		}
	}
	return true
}

func equalArticleBaselineSplitCounts(left, right map[string]map[string]int) bool {
	if len(left) != len(right) {
		return false
	}
	for key, value := range left {
		if !equalArticleBaselineClassCounts(value, right[key]) {
			return false
		}
	}
	return true
}

func cloneArticleBaselineCounts(source map[string]int) map[string]int {
	keys := make([]string, 0, len(source))
	for key := range source {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	result := make(map[string]int, len(source))
	for _, key := range keys {
		result[key] = source[key]
	}
	return result
}

func cloneArticleBaselineSplitCounts(source map[string]map[string]int) map[string]map[string]int {
	result := make(map[string]map[string]int, len(source))
	for key, value := range source {
		result[key] = cloneArticleBaselineCounts(value)
	}
	return result
}
