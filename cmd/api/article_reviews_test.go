package main

import (
	"bytes"
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

func testQualityHandler(t *testing.T) http.Handler {
	t.Helper()
	root := t.TempDir()
	dataPath := filepath.Join(root, "dashboard.json")
	if err := os.WriteFile(dataPath, []byte(testDashboard), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "quality-review-sample.json"), []byte(testQualitySample), 0o600); err != nil {
		t.Fatal(err)
	}
	return newHandler(dataPath, filepath.Join(root, "reviews.jsonl"), "http://localhost:3000", log.New(io.Discard, "", 0))
}

func TestQualityArticleReviewFlow(t *testing.T) {
	handler := testQualityHandler(t)

	listRequest := httptest.NewRequest(http.MethodGet, "/api/v1/quality/articles", nil)
	listResponse := httptest.NewRecorder()
	handler.ServeHTTP(listResponse, listRequest)
	if listResponse.Code != http.StatusOK || !strings.Contains(listResponse.Body.String(), `"archive_articles":13224`) || !strings.Contains(listResponse.Body.String(), `"title_source":"manual_override"`) {
		t.Fatalf("list response = %d %s", listResponse.Code, listResponse.Body.String())
	}

	body := `{"article_id":"0000000000000000000000000000000000000000000000000000000000000000","decision":"relevant"}`
	postRequest := httptest.NewRequest(http.MethodPost, "/api/v1/quality/articles", bytes.NewBufferString(body))
	postRequest.Header.Set("Content-Type", "application/json")
	postRequest.Header.Set("Origin", "http://localhost:3000")
	postResponse := httptest.NewRecorder()
	handler.ServeHTTP(postResponse, postRequest)
	if postResponse.Code != http.StatusCreated || !strings.Contains(postResponse.Body.String(), `"decision":"relevant"`) {
		t.Fatalf("post response = %d %s", postResponse.Code, postResponse.Body.String())
	}

	listResponse = httptest.NewRecorder()
	handler.ServeHTTP(listResponse, listRequest)
	if !strings.Contains(listResponse.Body.String(), `"decision":"relevant"`) {
		t.Fatalf("saved review missing from list: %s", listResponse.Body.String())
	}

	summaryRequest := httptest.NewRequest(http.MethodGet, "/api/v1/quality/articles/summary", nil)
	summaryResponse := httptest.NewRecorder()
	handler.ServeHTTP(summaryResponse, summaryRequest)
	var summary articleReviewSummaryResponse
	if err := json.Unmarshal(summaryResponse.Body.Bytes(), &summary); err != nil {
		t.Fatal(err)
	}
	if summary.ResolvedReviews != 1 || summary.HighRelevant != 1 || summary.Status != "collecting_labels" {
		t.Fatalf("summary = %+v", summary)
	}
}

func TestQualityReviewRejectsArticleOutsideCurrentSample(t *testing.T) {
	handler := testQualityHandler(t)
	body := `{"article_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","decision":"relevant"}`
	request := httptest.NewRequest(http.MethodPost, "/api/v1/quality/articles", bytes.NewBufferString(body))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestArticleQualityRatesStayLockedUntilBalancedMinimum(t *testing.T) {
	reviews := make([]articleReviewRecord, 0, 20)
	for index := 0; index < 20; index++ {
		strength := "high"
		decision := "relevant"
		if index >= 10 {
			strength = "weak"
			if index%2 == 0 {
				decision = "not_relevant"
			}
		}
		reviews = append(reviews, articleReviewRecord{MatchStrength: strength, Decision: decision})
	}

	locked := summarizeArticleReviews(reviews[:19])
	ready := summarizeArticleReviews(reviews)
	if locked.Status != "collecting_labels" || locked.HighMatchPrecision != nil {
		t.Fatalf("locked summary = %+v", locked)
	}
	if ready.Status != "sample_ready" || ready.HighMatchPrecision == nil || *ready.HighMatchPrecision != 1 || ready.WeakMatchRelevantRate == nil || *ready.WeakMatchRelevantRate != 0.5 {
		t.Fatalf("ready summary = %+v", ready)
	}
}
