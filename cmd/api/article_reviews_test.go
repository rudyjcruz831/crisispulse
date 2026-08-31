package main

import (
	"bytes"
	"encoding/csv"
	"encoding/json"
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

const testSmartQualitySample = `{
  "version": 2,
  "sample_date": "2026-08-28",
  "archive_articles": 31700,
  "eligible_articles": 20449,
  "queue_candidate_articles": 20385,
  "selection_intent": {
    "strategy": "training_readiness_v1",
    "target": "cpu_smoke",
    "usable_rows": 62,
    "usable_rows_minimum": 16,
    "class_counts": {
      "reported_flooding": 25,
      "flood_risk_warning": 4,
      "heavy_rain_only": 3,
      "not_flood_related": 30
    },
    "class_minimum": 4,
    "distinct_article_dates": 9,
    "article_date_minimum": 3,
    "publisher_groups": 59,
    "publisher_group_minimum": 12,
    "inference_text_coverage": 0.96875,
    "inference_text_minimum": 1.0,
    "split_class_counts": {
      "training": {"reported_flooding": 18, "flood_risk_warning": 4, "heavy_rain_only": 2, "not_flood_related": 19},
      "validation": {"reported_flooding": 3, "flood_risk_warning": 0, "heavy_rain_only": 0, "not_flood_related": 6},
      "test": {"reported_flooding": 4, "flood_risk_warning": 0, "heavy_rain_only": 1, "not_flood_related": 4}
    },
    "split_class_minimums": {"training": 2, "validation": 1, "test": 1},
    "readiness_status": "computed",
    "production_minimums": {
      "total_usable_rows": 500,
      "class_minimum": 100,
      "article_dates": 30,
      "publisher_groups": 100,
      "inference_text_coverage": 0.95,
      "split_class_minimums": {"training": 60, "validation": 15, "test": 20}
    }
  },
  "articles": [
    {
      "article_id": "0000000000000000000000000000000000000000000000000000000000000000",
      "seen_at": "2026-08-28T10:00:00Z",
      "title": "Heavy rain closes roads across the county",
      "title_source": "publisher_metadata",
      "url": "https://news.example/heavy-rain-closes-roads",
      "source_domain": "news.example",
      "location_name": "New Jersey",
      "match_strength": "weak",
      "review_bucket": "ambiguous_match",
      "review_reason": "Ambiguous flood tag; retained for audit but blocked from alerts",
      "themes": ["NATURAL_DISASTER_FLOODING"],
      "quality_flags": [],
      "selection_intent": {
        "rank": 1,
        "sampling_split": "validation",
        "reasons": ["underrepresented_class", "underrepresented_split", "inference_text_available"]
      }
    },
    {
      "article_id": "1111111111111111111111111111111111111111111111111111111111111111",
      "seen_at": "2026-08-28T11:00:00Z",
      "title": "Flood watch issued for the weekend",
      "title_source": "url_path",
      "url": "https://weather.example/flood-watch-weekend",
      "source_domain": "weather.example",
      "location_name": "Pennsylvania",
      "match_strength": "high",
      "review_bucket": "high_match",
      "review_reason": "Explicit flood theme; allowed to contribute to alerts",
      "themes": ["NATURAL_DISASTER_FLOODING"],
      "quality_flags": [],
      "selection_intent": {
        "rank": 2,
        "reasons": ["underrepresented_split", "new_publisher_group"]
      }
    }
  ]
}`

func testQualityHandlerWithReviewPath(t *testing.T) (http.Handler, string) {
	return testQualityHandlerWithSample(t, testQualitySample)
}

func testQualityHandlerWithSample(t *testing.T, sample string) (http.Handler, string) {
	t.Helper()
	root := t.TempDir()
	dataPath := filepath.Join(root, "dashboard.json")
	if err := os.WriteFile(dataPath, []byte(testDashboard), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "quality-review-sample.json"), []byte(sample), 0o600); err != nil {
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
	return postQualityReview(t, handler, newProtocolArticleReviewRequest(articleID, decision))
}

func newProtocolArticleReviewRequest(articleID, decision string) articleReviewRequest {
	input := articleReviewRequest{
		ArticleID:             articleID,
		Decision:              decision,
		ReviewProtocolVersion: articleReviewProtocolV1,
		ReviewBasis:           "headline_only",
		HeadlineSupport:       "sufficient",
	}
	if decision == "not_flood_related" {
		input.NoSignalReason = "unrelated_false_match"
	}
	if decision == "uncertain" {
		input.ReviewBasis = "unavailable"
		input.HeadlineSupport = ""
		input.UncertaintyReason = "page_unavailable"
	}
	return input
}

func postQualityReview(t *testing.T, handler http.Handler, input articleReviewRequest) *httptest.ResponseRecorder {
	t.Helper()
	body, err := json.Marshal(input)
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

func TestQualityArticleReviewPersistsProtocolEvidence(t *testing.T) {
	handler := testQualityHandler(t)
	input := newProtocolArticleReviewRequest(strings.Repeat("0", 64), "reported_flooding")
	input.ReviewBasis = "full_article"
	input.ImpactFlags = []string{"fatality", "evacuation_displacement"}
	input.ContextFlags = []string{"aftermath_recovery", "climate_background"}
	response := postQualityReview(t, handler, input)
	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var result articleReviewResponse
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.Review.ReviewProtocolVersion != articleReviewProtocolV1 || result.Review.ReviewBasis != "full_article" || result.Review.HeadlineSupport != "sufficient" {
		t.Fatalf("response protocol = %+v", result.Review)
	}
	if got := strings.Join(result.Review.ImpactFlags, ","); got != "fatality,evacuation_displacement" {
		t.Fatalf("response impact flags = %q", got)
	}
	if got := strings.Join(result.Review.ContextFlags, ","); got != "aftermath_recovery,climate_background" {
		t.Fatalf("response context flags = %q", got)
	}
	if result.Review.TitleSource != "manual_override" {
		t.Fatalf("response title source = %q", result.Review.TitleSource)
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
	if len(sample.Articles) == 0 || sample.Articles[0].ReviewProtocolVersion != articleReviewProtocolV1 || strings.Join(sample.Articles[0].ImpactFlags, ",") != "fatality,evacuation_displacement" {
		t.Fatalf("quality article protocol = %#v", sample.Articles)
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

func TestQualityArticleReviewFlowPreservesSmartQueueIntent(t *testing.T) {
	handler, _ := testQualityHandlerWithSample(t, testSmartQualitySample)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/quality/articles", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var sample qualitySampleFile
	if err := json.Unmarshal(response.Body.Bytes(), &sample); err != nil {
		t.Fatal(err)
	}
	if sample.Version != 2 || sample.SelectionIntent == nil || sample.SelectionIntent.Target != "cpu_smoke" || sample.SelectionIntent.UsableRows != 62 {
		t.Fatalf("selection intent = %+v", sample.SelectionIntent)
	}
	if len(sample.Articles) != 2 || sample.Articles[0].SelectionIntent == nil || sample.Articles[0].SelectionIntent.Rank != 1 || sample.Articles[0].SelectionIntent.SamplingSplit != "validation" {
		t.Fatalf("smart queue articles = %+v", sample.Articles)
	}

	postResponse := postQualityDecision(t, handler, strings.Repeat("0", 64), "heavy_rain_only")
	if postResponse.Code != http.StatusCreated {
		t.Fatalf("post status = %d, body = %s", postResponse.Code, postResponse.Body.String())
	}
}

func TestQualityArticleReviewTreatsCompletedSmartQueueAsHealthy(t *testing.T) {
	var sample qualitySampleFile
	if err := json.Unmarshal([]byte(testSmartQualitySample), &sample); err != nil {
		t.Fatal(err)
	}
	sample.Articles = []qualityArticle{}
	sample.QueueCandidateArticles = 0
	encoded, err := json.Marshal(sample)
	if err != nil {
		t.Fatal(err)
	}
	handler, _ := testQualityHandlerWithSample(t, string(encoded))
	request := httptest.NewRequest(http.MethodGet, "/api/v1/quality/articles", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"articles":[]`) {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestQualityArticleReviewRejectsInvalidSmartQueueRank(t *testing.T) {
	invalid := strings.Replace(testSmartQualitySample, `"rank": 2`, `"rank": 1`, 1)
	handler, _ := testQualityHandlerWithSample(t, invalid)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/quality/articles", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
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

func TestQualityArticleReviewRejectsInvalidProtocolCombinations(t *testing.T) {
	tests := map[string]func(*articleReviewRequest){
		"missing protocol":                  func(input *articleReviewRequest) { input.ReviewProtocolVersion = 0 },
		"invalid basis":                     func(input *articleReviewRequest) { input.ReviewBasis = "browser_guess" },
		"resolved missing headline support": func(input *articleReviewRequest) { input.HeadlineSupport = "" },
		"headline only body required":       func(input *articleReviewRequest) { input.HeadlineSupport = "body_required" },
		"resolved unavailable":              func(input *articleReviewRequest) { input.ReviewBasis = "unavailable" },
		"not flood missing reason": func(input *articleReviewRequest) {
			input.Decision = "not_flood_related"
			input.NoSignalReason = ""
		},
		"other class with no signal reason": func(input *articleReviewRequest) { input.NoSignalReason = "unrelated_false_match" },
		"uncertain missing reason": func(input *articleReviewRequest) {
			input.Decision = "uncertain"
			input.ReviewBasis = "unavailable"
			input.HeadlineSupport = ""
		},
		"uncertain with headline support": func(input *articleReviewRequest) {
			input.Decision = "uncertain"
			input.ReviewBasis = "full_article"
			input.UncertaintyReason = "insufficient_or_conflicting"
		},
		"unknown impact":   func(input *articleReviewRequest) { input.ImpactFlags = []string{"business_loss"} },
		"duplicate impact": func(input *articleReviewRequest) { input.ImpactFlags = []string{"fatality", "fatality"} },
		"unknown context":  func(input *articleReviewRequest) { input.ContextFlags = []string{"breaking_news"} },
		"duplicate context": func(input *articleReviewRequest) {
			input.ContextFlags = []string{"climate_background", "climate_background"}
		},
	}
	for name, mutate := range tests {
		t.Run(name, func(t *testing.T) {
			handler := testQualityHandler(t)
			input := newProtocolArticleReviewRequest(strings.Repeat("0", 64), "reported_flooding")
			mutate(&input)
			response := postQualityReview(t, handler, input)
			if response.Code != http.StatusBadRequest {
				t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
			}
		})
	}
}

func TestQualityArticleReviewRejectsFreeFormTags(t *testing.T) {
	for _, tags := range [][]string{{}, {"fatality"}} {
		handler := testQualityHandler(t)
		input := newProtocolArticleReviewRequest(strings.Repeat("0", 64), "reported_flooding")
		input.Tags = &tags
		response := postQualityReview(t, handler, input)
		if response.Code != http.StatusBadRequest {
			t.Fatalf("tags %#v status = %d, body = %s", tags, response.Code, response.Body.String())
		}
	}
}

func TestQualityReviewRejectsArticleOutsideCurrentSample(t *testing.T) {
	handler := testQualityHandler(t)
	body := `{"article_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","decision":"reported_flooding","review_protocol_version":1,"review_basis":"headline_only","headline_support":"sufficient"}`
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
		TitleSource:   "publisher_metadata",
		URL:           "https://news.example/legacy-flood",
		SourceDomain:  "news.example",
		MatchStrength: "high",
		ReviewBucket:  "high_match",
	}
	riskInput := newProtocolArticleReviewRequest(article.ArticleID, "flood_risk_warning")
	riskInput.ImpactFlags = []string{"fatality"}
	if _, err := store.save(article, riskInput); err != nil {
		t.Fatal(err)
	}
	reportedInput := newProtocolArticleReviewRequest(article.ArticleID, "reported_flooding")
	reportedInput.ImpactFlags = []string{"fatality", "property_crop_damage"}
	if _, err := store.save(article, reportedInput); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(reviewPath)
	if err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(string(raw)), "\n")
	if len(lines) != 3 || !strings.Contains(lines[0], `"decision":"relevant"`) || !strings.Contains(lines[1], `"title_source":"publisher_metadata"`) || !strings.Contains(lines[1], `"review_protocol_version":1`) || !strings.Contains(lines[2], `"impact_flags":["fatality","property_crop_damage"]`) {
		t.Fatalf("audit log = %s", raw)
	}
	reviews, err := store.list()
	if err != nil {
		t.Fatal(err)
	}
	if len(reviews) != 1 || reviews[0].Decision != "reported_flooding" || reviews[0].DecisionSchemaVersion != 2 || reviews[0].ReviewProtocolVersion != 1 || reviews[0].TitleSource != "publisher_metadata" || strings.Join(reviews[0].ImpactFlags, ",") != "fatality,property_crop_damage" {
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
	for _, source := range []string{"manual_override", "publisher_metadata", "url_path", "unavailable"} {
		record := base
		record.TitleSource = source
		if err := validateStoredArticleReview(record); err != nil {
			t.Fatalf("valid title source %q rejected: %v", source, err)
		}
	}
	base.TitleSource = "browser_supplied"
	if err := validateStoredArticleReview(base); err == nil {
		t.Fatal("invalid title source was accepted")
	}
	base.TitleSource = ""
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
	input := newProtocolArticleReviewRequest(strings.Repeat("0", 64), "heavy_rain_only")
	input.ReviewBasis = "full_article"
	input.ImpactFlags = []string{"transport_disruption"}
	input.ContextFlags = []string{"climate_background"}
	response := postQualityReview(t, handler, input)
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
	if len(rows) != 2 || len(rows[0]) != 18 || rows[0][2] != "title_source" || rows[0][8] != "decision_schema_version" || rows[0][10] != "tags" || rows[0][11] != "review_protocol_version" || rows[1][2] != "manual_override" || rows[1][7] != "heavy_rain_only" || rows[1][8] != "2" || rows[1][11] != "1" || rows[1][12] != "full_article" || rows[1][16] != "transport_disruption" || rows[1][17] != "climate_background" {
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
	reviews[0].TitleSource = "publisher_metadata"
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
	if got := byDecision["reported_flooding"].TitleSource; got != "publisher_metadata" {
		t.Fatalf("eligible title source = %q", got)
	}
}

func TestTrainingArticlesExcludeProtocolReviewsWithoutHeadlineSupport(t *testing.T) {
	handler, reviewPath := testQualityHandlerWithReviewPath(t)
	makeProtocolRecord := func(idCharacter, headlineSupport string) articleReviewRecord {
		record := trainingReviewFixture(idCharacter, "reported_flooding", articleDecisionSchemaV2, "2026-08-24T10:00:00Z")
		record.ReviewProtocolVersion = articleReviewProtocolV1
		record.ReviewBasis = "full_article"
		record.HeadlineSupport = headlineSupport
		return record
	}
	writeTrainingReviewFixtures(t, reviewPath, []articleReviewRecord{
		makeProtocolRecord("0", "sufficient"),
		makeProtocolRecord("1", "body_required"),
		makeProtocolRecord("2", "conflicts_with_body"),
	})

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
	if result.Summary.TrainingEligible != 1 || result.Summary.Excluded != 2 || result.Summary.ExclusionReasonCounts["headline_not_sufficient"] != 2 {
		t.Fatalf("summary = %+v", result.Summary)
	}
	for _, article := range result.Articles {
		if article.HeadlineSupport == "sufficient" {
			if !article.TrainingEligible || article.ExclusionReason != "" {
				t.Fatalf("sufficient article = %+v", article)
			}
			continue
		}
		if article.TrainingEligible || article.ExclusionReason != "headline_not_sufficient" {
			t.Fatalf("headline-insufficient article = %+v", article)
		}
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
	if len(result.Summary.ClassCounts) != 4 || len(result.Summary.ExclusionReasonCounts) != 3 {
		t.Fatalf("stable count keys are missing: %+v", result.Summary)
	}
}

func TestTrainingArticlesCorrectionUsesLatestWhileHistoryRemainsAppendOnly(t *testing.T) {
	handler, reviewPath := testQualityHandlerWithReviewPath(t)
	articleID := strings.Repeat("0", 64)
	first := postQualityReview(t, handler, newProtocolArticleReviewRequest(articleID, "reported_flooding"))
	if first.Code != http.StatusCreated {
		t.Fatalf("first review = %d %s", first.Code, first.Body.String())
	}
	correction := postQualityReview(t, handler, newProtocolArticleReviewRequest(articleID, "uncertain"))
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
	if article.Decision != "uncertain" || article.TrainingEligible || article.ExclusionReason != "uncertain" || article.ReviewProtocolVersion != articleReviewProtocolV1 || article.UncertaintyReason != "page_unavailable" {
		t.Fatalf("latest correction = %+v", article)
	}
}

func TestTrainingArticleCSVIsExcelCompatibleAudit(t *testing.T) {
	handler, reviewPath := testQualityHandlerWithReviewPath(t)
	eligible := trainingReviewFixture("0", "reported_flooding", articleDecisionSchemaV2, "2026-08-24T10:00:00Z")
	eligible.Title = `=HYPERLINK("https://malicious.example","click")`
	eligible.SourceDomain = "\tnews.example"
	eligible.TitleSource = "publisher_metadata"
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
	if len(rows) != 3 || len(rows[0]) != 20 || rows[0][2] != "title_source" || rows[0][11] != "training_eligible" || rows[0][12] != "exclusion_reason" || rows[0][13] != "review_protocol_version" || rows[0][19] != "context_flags" {
		t.Fatalf("CSV rows = %#v", rows)
	}
	byDecision := make(map[string][]string, 2)
	for _, row := range rows[1:] {
		byDecision[row[7]] = row
	}
	if row := byDecision["reported_flooding"]; row[1] != `'=HYPERLINK("https://malicious.example","click")` || row[2] != "publisher_metadata" || row[4] != "'\tnews.example" || row[10] != "flash-flood|fatality" || row[11] != "true" || row[12] != "" {
		t.Fatalf("eligible CSV row = %#v", row)
	}
	if row := byDecision["not_relevant"]; row[11] != "false" || row[12] != "legacy_schema" {
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
