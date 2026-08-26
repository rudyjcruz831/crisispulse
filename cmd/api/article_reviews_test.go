package main

import (
	"bytes"
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

const testQualitySample = `{
  "version": 1,
  "sample_date": "2026-08-23",
  "archive_articles": 13224,
  "eligible_articles": 12000,
  "articles": [
    {
      "article_id": "0000000000000000000000000000000000000000000000000000000000000000",
      "seen_at": "2026-08-23T10:00:00Z",
      "title": "Flood closes local road",
      "title_source": "manual_override",
      "url": "https://news.example/flood-closes-road",
      "source_domain": "news.example",
      "location_name": "New Jersey",
      "match_strength": "high",
      "review_bucket": "high_match",
      "review_reason": "Explicit flood theme; allowed to contribute to alerts",
      "themes": ["NATURAL_DISASTER_FLOODING"],
      "quality_flags": []
    },
    {
      "article_id": "1111111111111111111111111111111111111111111111111111111111111111",
      "seen_at": "2026-08-23T11:00:00Z",
      "title": "Company flooded with applications",
      "title_source": "url_path",
      "url": "https://business.example/flooded-with-applications",
      "source_domain": "business.example",
      "location_name": "",
      "match_strength": "weak",
      "review_bucket": "headline_conflict",
      "review_reason": "Headline conflicts with the flood tag; blocked from alerts",
      "themes": ["FLOOD"],
      "quality_flags": ["url_topic_mismatch"]
    }
  ]
}`

func testQualityHandlerWithReviewPath(t *testing.T) (http.Handler, string) {
	t.Helper()
	root := t.TempDir()
	dataPath := filepath.Join(root, "dashboard.json")
	if err := os.WriteFile(dataPath, []byte(testDashboard), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "quality-review-sample.json"), []byte(testQualitySample), 0o600); err != nil {
		t.Fatal(err)
	}
	reviewPath := filepath.Join(root, "reviews.jsonl")
	articleReviewPath := filepath.Join(root, "article-reviews.jsonl")
	return newHandler(dataPath, reviewPath, "http://localhost:3000", log.New(io.Discard, "", 0)), articleReviewPath
}

func testQualityHandler(t *testing.T) http.Handler {
	t.Helper()
	handler, _ := testQualityHandlerWithReviewPath(t)
	return handler
}

func postQualityDecision(t *testing.T, handler http.Handler, articleID, decision string) *httptest.ResponseRecorder {
	t.Helper()
	return postQualityReview(t, handler, articleID, decision, nil)
}

func postQualityReview(t *testing.T, handler http.Handler, articleID, decision string, tags []string) *httptest.ResponseRecorder {
	t.Helper()
	body, err := json.Marshal(articleReviewRequest{ArticleID: articleID, Decision: decision, Tags: tags})
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/api/v1/quality/articles", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Origin", "http://localhost:3000")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func TestQualityArticleReviewNormalizesDeduplicatesAndPersistsTags(t *testing.T) {
	handler := testQualityHandler(t)
	tags := []string{" Hawaii Rain ", "HAWAII---RAIN", "Woman’s Death", " ÉVACUATION / 東京 "}
	response := postQualityReview(t, handler, strings.Repeat("0", 64), "reported_flooding", tags)
	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var result articleReviewResponse
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	wantTags := "hawaii-rain,woman-s-death,évacuation-東京"
	if got := strings.Join(result.Review.Tags, ","); got != wantTags {
		t.Fatalf("response tags = %q, want %q", got, wantTags)
	}

	request := httptest.NewRequest(http.MethodGet, "/api/v1/quality/articles", nil)
	listResponse := httptest.NewRecorder()
	handler.ServeHTTP(listResponse, request)
	if listResponse.Code != http.StatusOK {
		t.Fatalf("list status = %d, body = %s", listResponse.Code, listResponse.Body.String())
	}
	var sample qualitySampleFile
	if err := json.Unmarshal(listResponse.Body.Bytes(), &sample); err != nil {
		t.Fatal(err)
	}
	if len(sample.Articles) == 0 || strings.Join(sample.Articles[0].Tags, ",") != wantTags {
		t.Fatalf("quality article tags = %#v", sample.Articles)
	}
}

func TestQualityArticleReviewFlow(t *testing.T) {
	handler := testQualityHandler(t)

	listRequest := httptest.NewRequest(http.MethodGet, "/api/v1/quality/articles", nil)
	listResponse := httptest.NewRecorder()
	handler.ServeHTTP(listResponse, listRequest)
	if listResponse.Code != http.StatusOK || !strings.Contains(listResponse.Body.String(), `"archive_articles":13224`) || !strings.Contains(listResponse.Body.String(), `"title_source":"manual_override"`) {
		t.Fatalf("list response = %d %s", listResponse.Code, listResponse.Body.String())
	}

	postResponse := postQualityDecision(t, handler, strings.Repeat("0", 64), "reported_flooding")
	if postResponse.Code != http.StatusCreated || !strings.Contains(postResponse.Body.String(), `"decision":"reported_flooding"`) || !strings.Contains(postResponse.Body.String(), `"decision_schema_version":2`) {
		t.Fatalf("post response = %d %s", postResponse.Code, postResponse.Body.String())
	}

	listResponse = httptest.NewRecorder()
	handler.ServeHTTP(listResponse, listRequest)
	if !strings.Contains(listResponse.Body.String(), `"decision":"reported_flooding"`) || !strings.Contains(listResponse.Body.String(), `"decision_schema_version":2`) {
		t.Fatalf("saved review missing from list: %s", listResponse.Body.String())
	}

	summaryRequest := httptest.NewRequest(http.MethodGet, "/api/v1/quality/articles/summary", nil)
	summaryResponse := httptest.NewRecorder()
	handler.ServeHTTP(summaryResponse, summaryRequest)
	var summary articleReviewSummaryResponse
	if err := json.Unmarshal(summaryResponse.Body.Bytes(), &summary); err != nil {
		t.Fatal(err)
	}
	if summary.TotalReviews != 1 || summary.ResolvedReviews != 1 || summary.ReportedFloodingArticles != 1 || summary.HighFloodRelated != 1 || summary.Status != "collecting_labels" {
		t.Fatalf("summary = %+v", summary)
	}
}

func TestQualityArticleReviewAcceptsEverySchemaV2Decision(t *testing.T) {
	decisions := []string{"reported_flooding", "flood_risk_warning", "heavy_rain_only", "not_flood_related", "uncertain"}
	for _, decision := range decisions {
		t.Run(decision, func(t *testing.T) {
			handler := testQualityHandler(t)
			response := postQualityDecision(t, handler, strings.Repeat("0", 64), decision)
			if response.Code != http.StatusCreated {
				t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
			}
			var result articleReviewResponse
			if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
				t.Fatal(err)
			}
			if result.Review.Decision != decision || result.Review.DecisionSchemaVersion != articleDecisionSchemaV2 {
				t.Fatalf("review = %+v", result.Review)
			}
		})
	}
}

func TestQualityArticleReviewRejectsLegacyAndInvalidDecisions(t *testing.T) {
	for _, decision := range []string{"relevant", "not_relevant", "flood", "", "REPORTED_FLOODING"} {
		t.Run(decision, func(t *testing.T) {
			handler := testQualityHandler(t)
			response := postQualityDecision(t, handler, strings.Repeat("0", 64), decision)
			if response.Code != http.StatusBadRequest {
				t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
			}
		})
	}
}

func TestQualityArticleReviewRejectsInvalidTags(t *testing.T) {
	nineTags := make([]string, 9)
	for index := range nineTags {
		nineTags[index] = fmt.Sprintf("tag-%d", index)
	}
	tests := map[string][]string{
		"no letters or digits": {" -- !!! "},
		"too many":             nineTags,
		"too long":             {strings.Repeat("雨", maximumArticleTagRunes+1)},
	}
	for name, tags := range tests {
		t.Run(name, func(t *testing.T) {
			handler := testQualityHandler(t)
			response := postQualityReview(t, handler, strings.Repeat("0", 64), "reported_flooding", tags)
			if response.Code != http.StatusBadRequest {
				t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
			}
		})
	}

	handler := testQualityHandler(t)
	response := postQualityReview(t, handler, strings.Repeat("0", 64), "reported_flooding", []string{strings.Repeat("雨", maximumArticleTagRunes)})
	if response.Code != http.StatusCreated {
		t.Fatalf("32-code-point Unicode tag status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestQualityReviewRejectsArticleOutsideCurrentSample(t *testing.T) {
	handler := testQualityHandler(t)
	body := `{"article_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","decision":"reported_flooding"}`
	request := httptest.NewRequest(http.MethodPost, "/api/v1/quality/articles", bytes.NewBufferString(body))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestArticleReviewStoreLoadsHistoricalSchemaV1WithoutMapping(t *testing.T) {
	handler, reviewPath := testQualityHandlerWithReviewPath(t)
	legacyMissingVersion := `{"article_id":"0000000000000000000000000000000000000000000000000000000000000000","title":"Legacy flood label","url":"https://news.example/legacy-flood","source_domain":"news.example","match_strength":"high","review_bucket":"high_match","decision":"relevant","reviewed_at":"2026-08-23T10:00:00Z"}`
	legacyExplicitVersion := `{"article_id":"1111111111111111111111111111111111111111111111111111111111111111","title":"Legacy negative label","url":"https://news.example/legacy-negative","source_domain":"news.example","match_strength":"weak","review_bucket":"headline_conflict","decision":"not_relevant","decision_schema_version":1,"reviewed_at":"2026-08-23T11:00:00Z"}`
	legacyUncertain := `{"article_id":"2222222222222222222222222222222222222222222222222222222222222222","title":"Legacy uncertain label","url":"https://news.example/legacy-uncertain","source_domain":"news.example","match_strength":"weak","review_bucket":"ambiguous_match","decision":"uncertain","reviewed_at":"2026-08-23T12:00:00Z"}`
	if err := os.WriteFile(reviewPath, []byte(legacyMissingVersion+"\n"+legacyExplicitVersion+"\n"+legacyUncertain+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	reviews, err := newArticleReviewStore(reviewPath).list()
	if err != nil {
		t.Fatal(err)
	}
	if len(reviews) != 3 {
		t.Fatalf("reviews = %+v", reviews)
	}
	decisions := map[string]int{}
	for _, review := range reviews {
		if len(review.Tags) != 0 {
			t.Fatalf("legacy review unexpectedly has tags: %+v", review)
		}
		decisions[review.Decision] = review.DecisionSchemaVersion
	}
	if decisions["relevant"] != 1 || decisions["not_relevant"] != 1 || decisions["uncertain"] != 1 {
		t.Fatalf("legacy decisions were not preserved: %+v", reviews)
	}

	request := httptest.NewRequest(http.MethodGet, "/api/v1/quality/articles", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"decision":"relevant","decision_schema_version":1`) {
		t.Fatalf("legacy decision was not exposed as schema v1: %d %s", response.Code, response.Body.String())
	}
}

func TestArticleReviewCorrectionAppendsAuditAndLatestIsSchemaV2(t *testing.T) {
	_, reviewPath := testQualityHandlerWithReviewPath(t)
	legacy := `{"article_id":"0000000000000000000000000000000000000000000000000000000000000000","title":"Legacy flood label","url":"https://news.example/legacy-flood","source_domain":"news.example","match_strength":"high","review_bucket":"high_match","decision":"relevant","reviewed_at":"2026-08-23T10:00:00Z"}`
	if err := os.WriteFile(reviewPath, []byte(legacy+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	store := newArticleReviewStore(reviewPath)
	now := time.Date(2026, 8, 24, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time {
		current := now
		now = now.Add(time.Minute)
		return current
	}
	article := qualityArticle{
		ArticleID:     strings.Repeat("0", 64),
		Title:         "Corrected flood-risk label",
		URL:           "https://news.example/legacy-flood",
		SourceDomain:  "news.example",
		MatchStrength: "high",
		ReviewBucket:  "high_match",
	}
	if _, err := store.save(article, "flood_risk_warning", []string{"hawaii-rain", "fatality"}); err != nil {
		t.Fatal(err)
	}
	if _, err := store.save(article, "reported_flooding", []string{"fatality", "flash-flood"}); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(reviewPath)
	if err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(string(raw)), "\n")
	if len(lines) != 3 || !strings.Contains(lines[0], `"decision":"relevant"`) || !strings.Contains(lines[1], `"tags":["hawaii-rain","fatality"]`) || !strings.Contains(lines[2], `"tags":["fatality","flash-flood"]`) {
		t.Fatalf("audit log = %s", raw)
	}
	reviews, err := store.list()
	if err != nil {
		t.Fatal(err)
	}
	if len(reviews) != 1 || reviews[0].Decision != "reported_flooding" || reviews[0].DecisionSchemaVersion != 2 || strings.Join(reviews[0].Tags, ",") != "fatality,flash-flood" {
		t.Fatalf("latest reviews = %+v", reviews)
	}
}

func TestStoredArticleReviewRequiresCanonicalSchemaV2Tags(t *testing.T) {
	base := articleReviewRecord{
		ArticleID:             strings.Repeat("0", 64),
		Title:                 "Flood closes local road",
		URL:                   "https://news.example/flood-closes-road",
		SourceDomain:          "news.example",
		MatchStrength:         "high",
		ReviewBucket:          "high_match",
		Decision:              "reported_flooding",
		DecisionSchemaVersion: articleDecisionSchemaV2,
		ReviewedAt:            "2026-08-24T12:00:00Z",
	}
	for name, tags := range map[string][]string{
		"uppercase":   {"Hawaii-Rain"},
		"separator":   {"hawaii--rain"},
		"duplicate":   {"hawaii-rain", "hawaii-rain"},
		"too many":    {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine"},
		"too long":    {strings.Repeat("a", maximumArticleTagRunes+1)},
		"empty value": {""},
	} {
		t.Run(name, func(t *testing.T) {
			record := base
			record.Tags = tags
			if err := validateStoredArticleReview(record); err == nil {
				t.Fatalf("tags %#v were accepted", tags)
			}
		})
	}

	base.Tags = []string{"hawaii-rain", "fatality"}
	if err := validateStoredArticleReview(base); err != nil {
		t.Fatalf("canonical v2 tags rejected: %v", err)
	}
	base.DecisionSchemaVersion = 1
	base.Decision = "relevant"
	if err := validateStoredArticleReview(base); err == nil {
		t.Fatal("schema v1 review with tags was accepted")
	}
}

func TestArticleQualitySummaryUsesOnlyResolvedSchemaV2ForReadiness(t *testing.T) {
	reviews := make([]articleReviewRecord, 0, 24)
	highDecisions := []string{"reported_flooding", "reported_flooding", "reported_flooding", "reported_flooding", "reported_flooding", "reported_flooding", "flood_risk_warning", "heavy_rain_only", "heavy_rain_only", "not_flood_related"}
	weakDecisions := []string{"reported_flooding", "flood_risk_warning", "flood_risk_warning", "heavy_rain_only", "heavy_rain_only", "heavy_rain_only", "not_flood_related", "not_flood_related", "not_flood_related", "not_flood_related"}
	for _, decision := range highDecisions {
		reviews = append(reviews, articleReviewRecord{DecisionSchemaVersion: 2, MatchStrength: "high", Decision: decision})
	}
	for _, decision := range weakDecisions {
		reviews = append(reviews, articleReviewRecord{DecisionSchemaVersion: 2, MatchStrength: "weak", Decision: decision})
	}
	reviews = append(reviews,
		articleReviewRecord{DecisionSchemaVersion: 2, MatchStrength: "high", Decision: "uncertain"},
		articleReviewRecord{DecisionSchemaVersion: 1, MatchStrength: "high", Decision: "relevant"},
		articleReviewRecord{DecisionSchemaVersion: 1, MatchStrength: "weak", Decision: "not_relevant"},
		articleReviewRecord{MatchStrength: "weak", Decision: "uncertain"},
	)

	ready := summarizeArticleReviews(reviews)
	if ready.TotalReviews != 24 || ready.LegacyReviews != 3 || ready.Uncertain != 1 || ready.ResolvedReviews != 20 || ready.RemainingToSample != 0 {
		t.Fatalf("summary totals = %+v", ready)
	}
	if ready.ReportedFloodingArticles != 7 || ready.FloodRiskWarningArticles != 3 || ready.HeavyRainOnlyArticles != 5 || ready.NotFloodRelatedArticles != 5 {
		t.Fatalf("decision counts = %+v", ready)
	}
	if ready.HighResolved != 10 || ready.HighFloodRelated != 7 || ready.WeakResolved != 10 || ready.WeakFloodRelated != 3 {
		t.Fatalf("stratum counts = %+v", ready)
	}
	if ready.Status != "sample_ready" || ready.HighMatchFloodRelatedRate == nil || *ready.HighMatchFloodRelatedRate != 0.7 || ready.WeakMatchFloodRelatedRate == nil || *ready.WeakMatchFloodRelatedRate != 0.3 {
		t.Fatalf("ready summary = %+v", ready)
	}

	belowOverallMinimum := summarizeArticleReviews(reviews[:19])
	if belowOverallMinimum.Status != "collecting_labels" || belowOverallMinimum.RemainingToSample != 1 || belowOverallMinimum.HighMatchFloodRelatedRate != nil || belowOverallMinimum.WeakMatchFloodRelatedRate != nil {
		t.Fatalf("below-minimum summary = %+v", belowOverallMinimum)
	}

	unbalanced := make([]articleReviewRecord, 0, 20)
	for index := 0; index < 20; index++ {
		strength := "high"
		if index >= 16 {
			strength = "weak"
		}
		unbalanced = append(unbalanced, articleReviewRecord{DecisionSchemaVersion: 2, MatchStrength: strength, Decision: "reported_flooding"})
	}
	if summary := summarizeArticleReviews(unbalanced); summary.ResolvedReviews != 20 || summary.WeakResolved != 4 || summary.Status != "collecting_labels" || summary.HighMatchFloodRelatedRate != nil {
		t.Fatalf("unbalanced summary = %+v", summary)
	}
}

func TestArticleQualityCSVExportIncludesDecisionSchemaVersion(t *testing.T) {
	handler := testQualityHandler(t)
	response := postQualityReview(t, handler, strings.Repeat("0", 64), "heavy_rain_only", []string{"Storm Damage", "Hawaii/Flood"})
	if response.Code != http.StatusCreated {
		t.Fatalf("post status = %d, body = %s", response.Code, response.Body.String())
	}

	request := httptest.NewRequest(http.MethodGet, "/api/v1/quality/articles/export.csv", nil)
	export := httptest.NewRecorder()
	handler.ServeHTTP(export, request)
	if export.Code != http.StatusOK {
		t.Fatalf("export status = %d, body = %s", export.Code, export.Body.String())
	}
	rows, err := csv.NewReader(export.Body).ReadAll()
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 2 || len(rows[0]) != 10 || rows[0][7] != "decision_schema_version" || rows[0][9] != "tags" || rows[1][6] != "heavy_rain_only" || rows[1][7] != "2" || rows[1][9] != "storm-damage|hawaii-flood" {
		t.Fatalf("CSV rows = %#v", rows)
	}
}

func trainingReviewFixture(idCharacter, decision string, schemaVersion int, reviewedAt string) articleReviewRecord {
	return articleReviewRecord{
		ArticleID:             strings.Repeat(idCharacter, 64),
		Title:                 "Training article " + idCharacter,
		URL:                   "https://news.example/training-article-" + idCharacter,
		SourceDomain:          "news.example",
		MatchStrength:         "high",
		ReviewBucket:          "high_match",
		Decision:              decision,
		DecisionSchemaVersion: schemaVersion,
		ReviewedAt:            reviewedAt,
	}
}

func writeTrainingReviewFixtures(t *testing.T, reviewPath string, reviews []articleReviewRecord) {
	t.Helper()
	var contents bytes.Buffer
	encoder := json.NewEncoder(&contents)
	for _, review := range reviews {
		if err := encoder.Encode(review); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(reviewPath, contents.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}
}

func TestTrainingArticlesReturnsLatestLabelsWithEligibilitySummary(t *testing.T) {
	handler, reviewPath := testQualityHandlerWithReviewPath(t)
	reviews := []articleReviewRecord{
		trainingReviewFixture("0", "reported_flooding", articleDecisionSchemaV2, "2026-08-24T10:00:00Z"),
		trainingReviewFixture("1", "flood_risk_warning", articleDecisionSchemaV2, "2026-08-24T11:00:00Z"),
		trainingReviewFixture("2", "heavy_rain_only", articleDecisionSchemaV2, "2026-08-24T12:00:00Z"),
		trainingReviewFixture("3", "not_flood_related", articleDecisionSchemaV2, "2026-08-24T13:00:00Z"),
		trainingReviewFixture("4", "uncertain", articleDecisionSchemaV2, "2026-08-24T14:00:00Z"),
		trainingReviewFixture("5", "relevant", 1, "2026-08-24T15:00:00Z"),
	}
	reviews[0].Tags = []string{"flash-flood", "fatality"}
	writeTrainingReviewFixtures(t, reviewPath, reviews)

	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/articles", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if response.Header().Get("Cache-Control") != "no-store" {
		t.Fatalf("Cache-Control = %q", response.Header().Get("Cache-Control"))
	}
	if !strings.Contains(response.Body.String(), `"exclusion_reason":""`) {
		t.Fatalf("eligible article did not expose an explicit exclusion reason: %s", response.Body.String())
	}

	var result trainingArticlesResponse
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.SchemaVersion != trainingDataSchemaVersion || result.Summary.TotalArticles != 6 || result.Summary.TrainingEligible != 4 || result.Summary.Excluded != 2 {
		t.Fatalf("summary = %+v", result)
	}
	for _, decision := range []string{"reported_flooding", "flood_risk_warning", "heavy_rain_only", "not_flood_related"} {
		if result.Summary.ClassCounts[decision] != 1 {
			t.Fatalf("class counts = %#v", result.Summary.ClassCounts)
		}
	}
	if result.Summary.ExclusionReasonCounts["uncertain"] != 1 || result.Summary.ExclusionReasonCounts["legacy_schema"] != 1 {
		t.Fatalf("exclusion counts = %#v", result.Summary.ExclusionReasonCounts)
	}
	if len(result.Articles) != 6 {
		t.Fatalf("articles = %+v", result.Articles)
	}
	byDecision := make(map[string]trainingArticle, len(result.Articles))
	for _, article := range result.Articles {
		byDecision[article.Decision] = article
	}
	for _, decision := range []string{"reported_flooding", "flood_risk_warning", "heavy_rain_only", "not_flood_related"} {
		if article := byDecision[decision]; !article.TrainingEligible || article.ExclusionReason != "" {
			t.Fatalf("eligible article %q = %+v", decision, article)
		}
	}
	if article := byDecision["uncertain"]; article.TrainingEligible || article.ExclusionReason != "uncertain" {
		t.Fatalf("uncertain article = %+v", article)
	}
	if article := byDecision["relevant"]; article.TrainingEligible || article.ExclusionReason != "legacy_schema" {
		t.Fatalf("legacy article = %+v", article)
	}
	if got := strings.Join(byDecision["reported_flooding"].Tags, ","); got != "flash-flood,fatality" {
		t.Fatalf("eligible tags = %q", got)
	}
}

func TestTrainingArticlesEmptyStoreHasStableZeroCounts(t *testing.T) {
	handler := testQualityHandler(t)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/articles", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var result trainingArticlesResponse
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.Summary.TotalArticles != 0 || result.Summary.TrainingEligible != 0 || result.Summary.Excluded != 0 || len(result.Articles) != 0 {
		t.Fatalf("response = %+v", result)
	}
	if len(result.Summary.ClassCounts) != 4 || len(result.Summary.ExclusionReasonCounts) != 2 {
		t.Fatalf("stable count keys are missing: %+v", result.Summary)
	}
}

func TestTrainingArticlesCorrectionUsesLatestWhileHistoryRemainsAppendOnly(t *testing.T) {
	handler, reviewPath := testQualityHandlerWithReviewPath(t)
	articleID := strings.Repeat("0", 64)
	first := postQualityReview(t, handler, articleID, "reported_flooding", []string{"flash-flood"})
	if first.Code != http.StatusCreated {
		t.Fatalf("first review = %d %s", first.Code, first.Body.String())
	}
	correction := postQualityReview(t, handler, articleID, "uncertain", []string{"needs-context"})
	if correction.Code != http.StatusCreated {
		t.Fatalf("correction = %d %s", correction.Code, correction.Body.String())
	}
	raw, err := os.ReadFile(reviewPath)
	if err != nil {
		t.Fatal(err)
	}
	if lines := strings.Split(strings.TrimSpace(string(raw)), "\n"); len(lines) != 2 {
		t.Fatalf("append-only history has %d entries: %s", len(lines), raw)
	}

	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/articles", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	var result trainingArticlesResponse
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if len(result.Articles) != 1 || result.Summary.TrainingEligible != 0 || result.Summary.Excluded != 1 {
		t.Fatalf("response = %+v", result)
	}
	article := result.Articles[0]
	if article.Decision != "uncertain" || article.TrainingEligible || article.ExclusionReason != "uncertain" || strings.Join(article.Tags, ",") != "needs-context" {
		t.Fatalf("latest correction = %+v", article)
	}
}

func TestTrainingArticleCSVIsExcelCompatibleAudit(t *testing.T) {
	handler, reviewPath := testQualityHandlerWithReviewPath(t)
	eligible := trainingReviewFixture("0", "reported_flooding", articleDecisionSchemaV2, "2026-08-24T10:00:00Z")
	eligible.Title = `=HYPERLINK("https://malicious.example","click")`
	eligible.SourceDomain = "\tnews.example"
	eligible.Tags = []string{"flash-flood", "fatality"}
	legacy := trainingReviewFixture("1", "not_relevant", 1, "2026-08-24T11:00:00Z")
	writeTrainingReviewFixtures(t, reviewPath, []articleReviewRecord{eligible, legacy})

	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/articles/export.csv", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if got := response.Header().Get("Content-Disposition"); !strings.Contains(got, "crisispulse-training-articles.csv") {
		t.Fatalf("Content-Disposition = %q", got)
	}
	raw := response.Body.Bytes()
	if !bytes.HasPrefix(raw, []byte{0xef, 0xbb, 0xbf}) || !bytes.Contains(raw, []byte("\r\n")) {
		t.Fatalf("CSV lacks UTF-8 BOM or CRLF rows: %q", raw)
	}
	rows, err := csv.NewReader(bytes.NewReader(bytes.TrimPrefix(raw, []byte{0xef, 0xbb, 0xbf}))).ReadAll()
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 3 || len(rows[0]) != 12 || rows[0][10] != "training_eligible" || rows[0][11] != "exclusion_reason" {
		t.Fatalf("CSV rows = %#v", rows)
	}
	byDecision := make(map[string][]string, 2)
	for _, row := range rows[1:] {
		byDecision[row[6]] = row
	}
	if row := byDecision["reported_flooding"]; row[1] != `'=HYPERLINK("https://malicious.example","click")` || row[3] != "'\tnews.example" || row[9] != "flash-flood|fatality" || row[10] != "true" || row[11] != "" {
		t.Fatalf("eligible CSV row = %#v", row)
	}
	if row := byDecision["not_relevant"]; row[10] != "false" || row[11] != "legacy_schema" {
		t.Fatalf("legacy CSV row = %#v", row)
	}
}

func TestArticleSpreadsheetSafeNeutralizesEveryDangerousPrefix(t *testing.T) {
	tests := []string{
		"=formula",
		"+formula",
		"-formula",
		"@formula",
		"\tplain text",
		"\rplain text",
		"  =formula",
		"  \tplain text",
	}
	for _, value := range tests {
		if got := articleSpreadsheetSafe(value); got != "'"+value {
			t.Errorf("articleSpreadsheetSafe(%q) = %q", value, got)
		}
	}
	for _, value := range []string{"plain text", "https://news.example/story", "2", "", "\nplain text"} {
		if got := articleSpreadsheetSafe(value); got != value {
			t.Errorf("articleSpreadsheetSafe(%q) = %q", value, got)
		}
	}
}

func TestTrainingArticleEndpointsRejectWrites(t *testing.T) {
	handler := testQualityHandler(t)
	for _, path := range []string{"/api/v1/training/articles", "/api/v1/training/articles/export.csv"} {
		t.Run(path, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodPost, path, strings.NewReader(`{}`))
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusMethodNotAllowed || response.Header().Get("Allow") != "GET, HEAD" {
				t.Fatalf("status = %d, Allow = %q, body = %s", response.Code, response.Header().Get("Allow"), response.Body.String())
			}
		})
	}
}
