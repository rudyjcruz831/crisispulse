package main

import (
	"bufio"
	"bytes"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	maxQualitySampleBytes      = 512 << 10
	maxArticleReviewLogBytes   = 4 << 20
	minimumArticleReviewSample = 20
	minimumStratumReviews      = 5
)

var articleIDPattern = regexp.MustCompile(`^[a-f0-9]{64}$`)

type qualityArticle struct {
	ArticleID     string   `json:"article_id"`
	SeenAt        string   `json:"seen_at"`
	Title         string   `json:"title"`
	TitleSource   string   `json:"title_source,omitempty"`
	URL           string   `json:"url"`
	SourceDomain  string   `json:"source_domain"`
	LocationName  string   `json:"location_name"`
	MatchStrength string   `json:"match_strength"`
	ReviewBucket  string   `json:"review_bucket"`
	ReviewReason  string   `json:"review_reason"`
	Themes        []string `json:"themes"`
	QualityFlags  []string `json:"quality_flags"`
	Decision      string   `json:"decision,omitempty"`
	ReviewedAt    string   `json:"reviewed_at,omitempty"`
}

type qualitySampleFile struct {
	Version          int              `json:"version"`
	SampleDate       string           `json:"sample_date"`
	ArchiveArticles  int              `json:"archive_articles"`
	EligibleArticles int              `json:"eligible_articles"`
	Articles         []qualityArticle `json:"articles"`
}

type articleReviewRequest struct {
	ArticleID string `json:"article_id"`
	Decision  string `json:"decision"`
}

type articleReviewRecord struct {
	ArticleID     string `json:"article_id"`
	Title         string `json:"title"`
	URL           string `json:"url"`
	SourceDomain  string `json:"source_domain"`
	MatchStrength string `json:"match_strength"`
	ReviewBucket  string `json:"review_bucket"`
	Decision      string `json:"decision"`
	ReviewedAt    string `json:"reviewed_at"`
}

type articleReviewResponse struct {
	Review articleReviewRecord `json:"review"`
}

type articleReviewSummaryResponse struct {
	TotalReviews          int      `json:"total_reviews"`
	RelevantArticles      int      `json:"relevant_articles"`
	NotRelevantArticles   int      `json:"not_relevant_articles"`
	Uncertain             int      `json:"uncertain"`
	ResolvedReviews       int      `json:"resolved_reviews"`
	MinimumSample         int      `json:"minimum_sample"`
	RemainingToSample     int      `json:"remaining_to_sample"`
	HighResolved          int      `json:"high_resolved"`
	HighRelevant          int      `json:"high_relevant"`
	WeakResolved          int      `json:"weak_resolved"`
	WeakRelevant          int      `json:"weak_relevant"`
	HighMatchPrecision    *float64 `json:"high_match_precision"`
	WeakMatchRelevantRate *float64 `json:"weak_match_relevant_rate"`
	Status                string   `json:"status"`
}

type articleReviewStore struct {
	path string
	now  func() time.Time
	mu   sync.Mutex
}

func newArticleReviewStore(path string) *articleReviewStore {
	return &articleReviewStore{path: path, now: time.Now}
}

func (service *api) qualityArticles(writer http.ResponseWriter, request *http.Request) {
	switch request.Method {
	case http.MethodGet, http.MethodHead:
		sample, err := service.loadQualitySample()
		if err != nil {
			service.logger.Printf("quality sample unavailable: %v", err)
			writeError(writer, http.StatusServiceUnavailable, "quality sample unavailable")
			return
		}
		reviews, err := service.articleReviews.list()
		if err != nil {
			service.logger.Printf("article reviews unavailable: %v", err)
			writeError(writer, http.StatusInternalServerError, "article reviews unavailable")
			return
		}
		latest := make(map[string]articleReviewRecord, len(reviews))
		for _, review := range reviews {
			latest[review.ArticleID] = review
		}
		for index := range sample.Articles {
			if review, ok := latest[sample.Articles[index].ArticleID]; ok {
				sample.Articles[index].Decision = review.Decision
				sample.Articles[index].ReviewedAt = review.ReviewedAt
			}
		}
		writer.Header().Set("Cache-Control", "no-store")
		writeJSON(writer, http.StatusOK, sample)
	case http.MethodPost:
		mediaType, _, err := mime.ParseMediaType(request.Header.Get("Content-Type"))
		if err != nil || mediaType != "application/json" {
			writeError(writer, http.StatusUnsupportedMediaType, "Content-Type must be application/json")
			return
		}
		request.Body = http.MaxBytesReader(writer, request.Body, maxReviewRequestBytes)
		decoder := json.NewDecoder(request.Body)
		decoder.DisallowUnknownFields()
		var input articleReviewRequest
		if err := decoder.Decode(&input); err != nil || requireJSONEnd(decoder) != nil {
			writeError(writer, http.StatusBadRequest, "invalid article review")
			return
		}
		if err := validateArticleReviewInput(input); err != nil {
			writeError(writer, http.StatusBadRequest, err.Error())
			return
		}
		sample, err := service.loadQualitySample()
		if err != nil {
			writeError(writer, http.StatusServiceUnavailable, "quality sample unavailable")
			return
		}
		var selected *qualityArticle
		for index := range sample.Articles {
			if sample.Articles[index].ArticleID == input.ArticleID {
				selected = &sample.Articles[index]
				break
			}
		}
		if selected == nil {
			writeError(writer, http.StatusBadRequest, "article is not in the current quality sample")
			return
		}
		review, err := service.articleReviews.save(*selected, input.Decision)
		if err != nil {
			service.logger.Printf("article review save failed: %v", err)
			writeError(writer, http.StatusInternalServerError, "article review could not be saved")
			return
		}
		writer.Header().Set("Cache-Control", "no-store")
		writeJSON(writer, http.StatusCreated, articleReviewResponse{Review: review})
	default:
		writer.Header().Set("Allow", "GET, HEAD, POST")
		writeError(writer, http.StatusMethodNotAllowed, "method not allowed")
	}
}

func (service *api) qualityArticleSummary(writer http.ResponseWriter, request *http.Request) {
	if !requireGet(writer, request) {
		return
	}
	reviews, err := service.articleReviews.list()
	if err != nil {
		service.logger.Printf("article review summary unavailable: %v", err)
		writeError(writer, http.StatusInternalServerError, "article review summary unavailable")
		return
	}
	writer.Header().Set("Cache-Control", "no-store")
	writeJSON(writer, http.StatusOK, summarizeArticleReviews(reviews))
}

func summarizeArticleReviews(reviews []articleReviewRecord) articleReviewSummaryResponse {
	summary := articleReviewSummaryResponse{
		TotalReviews:  len(reviews),
		MinimumSample: minimumArticleReviewSample,
		Status:        "collecting_labels",
	}
	for _, review := range reviews {
		switch review.Decision {
		case "relevant":
			summary.RelevantArticles++
		case "not_relevant":
			summary.NotRelevantArticles++
		case "uncertain":
			summary.Uncertain++
		}
		if review.Decision == "uncertain" {
			continue
		}
		if review.MatchStrength == "high" {
			summary.HighResolved++
			if review.Decision == "relevant" {
				summary.HighRelevant++
			}
		} else {
			summary.WeakResolved++
			if review.Decision == "relevant" {
				summary.WeakRelevant++
			}
		}
	}
	summary.ResolvedReviews = summary.RelevantArticles + summary.NotRelevantArticles
	summary.RemainingToSample = max(0, minimumArticleReviewSample-summary.ResolvedReviews)
	if summary.ResolvedReviews >= minimumArticleReviewSample && summary.HighResolved >= minimumStratumReviews && summary.WeakResolved >= minimumStratumReviews {
		highPrecision := float64(summary.HighRelevant) / float64(summary.HighResolved)
		weakRelevantRate := float64(summary.WeakRelevant) / float64(summary.WeakResolved)
		summary.HighMatchPrecision = &highPrecision
		summary.WeakMatchRelevantRate = &weakRelevantRate
		summary.Status = "sample_ready"
	}
	return summary
}

func (service *api) qualityArticleExport(writer http.ResponseWriter, request *http.Request) {
	if !requireGet(writer, request) {
		return
	}
	reviews, err := service.articleReviews.list()
	if err != nil {
		writeError(writer, http.StatusInternalServerError, "article review export unavailable")
		return
	}
	var output bytes.Buffer
	csvWriter := csv.NewWriter(&output)
	columns := []string{"article_id", "title", "url", "source_domain", "match_strength", "review_bucket", "decision", "reviewed_at"}
	if err := csvWriter.Write(columns); err != nil {
		writeError(writer, http.StatusInternalServerError, "article review export unavailable")
		return
	}
	for _, review := range reviews {
		row := []string{review.ArticleID, review.Title, review.URL, review.SourceDomain, review.MatchStrength, review.ReviewBucket, review.Decision, review.ReviewedAt}
		for index := range row {
			row[index] = spreadsheetSafe(row[index])
		}
		if err := csvWriter.Write(row); err != nil {
			writeError(writer, http.StatusInternalServerError, "article review export unavailable")
			return
		}
	}
	csvWriter.Flush()
	if csvWriter.Error() != nil {
		writeError(writer, http.StatusInternalServerError, "article review export unavailable")
		return
	}
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Content-Disposition", `attachment; filename="crisispulse-article-quality-reviews.csv"`)
	writer.Header().Set("Content-Type", "text/csv; charset=utf-8")
	writer.WriteHeader(http.StatusOK)
	if request.Method != http.MethodHead {
		_, _ = writer.Write(output.Bytes())
	}
}

func (service *api) loadQualitySample() (qualitySampleFile, error) {
	file, err := os.Open(service.qualitySamplePath)
	if err != nil {
		return qualitySampleFile{}, err
	}
	defer file.Close()
	raw, err := io.ReadAll(io.LimitReader(file, maxQualitySampleBytes+1))
	if err != nil || len(raw) > maxQualitySampleBytes {
		return qualitySampleFile{}, errors.New("quality sample exceeds size limit")
	}
	var sample qualitySampleFile
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&sample); err != nil || requireJSONEnd(decoder) != nil {
		return qualitySampleFile{}, errors.New("invalid quality sample")
	}
	if sample.Version != 1 || sample.ArchiveArticles < 0 || sample.EligibleArticles < 0 || len(sample.Articles) == 0 || len(sample.Articles) > 40 {
		return qualitySampleFile{}, errors.New("invalid quality sample metadata")
	}
	if _, err := time.Parse("2006-01-02", sample.SampleDate); err != nil {
		return qualitySampleFile{}, errors.New("invalid quality sample date")
	}
	seen := make(map[string]bool, len(sample.Articles))
	for _, article := range sample.Articles {
		if err := validateQualityArticle(article); err != nil {
			return qualitySampleFile{}, err
		}
		if seen[article.ArticleID] {
			return qualitySampleFile{}, errors.New("duplicate quality sample article")
		}
		seen[article.ArticleID] = true
	}
	return sample, nil
}

func validateQualityArticle(article qualityArticle) error {
	if !articleIDPattern.MatchString(article.ArticleID) {
		return errors.New("invalid quality article ID")
	}
	if _, err := time.Parse(time.RFC3339Nano, article.SeenAt); err != nil {
		return errors.New("invalid quality article timestamp")
	}
	if len(article.Title) < 1 || len(article.Title) > 1024 || len(article.SourceDomain) > 255 || len(article.LocationName) > 1024 || len(article.ReviewReason) > 512 {
		return errors.New("invalid quality article text")
	}
	if article.TitleSource != "" && article.TitleSource != "manual_override" && article.TitleSource != "publisher_metadata" && article.TitleSource != "url_path" && article.TitleSource != "unavailable" {
		return errors.New("invalid quality article title source")
	}
	if article.MatchStrength != "high" && article.MatchStrength != "weak" {
		return errors.New("invalid quality article strength")
	}
	if article.ReviewBucket != "high_match" && article.ReviewBucket != "headline_conflict" && article.ReviewBucket != "ambiguous_match" {
		return errors.New("invalid quality article bucket")
	}
	if !safeExternalArticleURL(article.URL) || len(article.Themes) > 6 || len(article.QualityFlags) > 8 {
		return errors.New("invalid quality article evidence")
	}
	for _, value := range append(append([]string{}, article.Themes...), article.QualityFlags...) {
		if len(value) > 120 {
			return errors.New("invalid quality article evidence")
		}
	}
	return nil
}

func safeExternalArticleURL(value string) bool {
	if len(value) < 1 || len(value) > 2048 {
		return false
	}
	parsed, err := url.Parse(value)
	if err != nil || parsed.Hostname() == "" || parsed.User != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") {
		return false
	}
	port := parsed.Port()
	if port != "" && !((parsed.Scheme == "http" && port == "80") || (parsed.Scheme == "https" && port == "443")) {
		return false
	}
	hostname := strings.ToLower(strings.TrimSuffix(parsed.Hostname(), "."))
	if hostname == "localhost" || strings.HasSuffix(hostname, ".local") || strings.HasSuffix(hostname, ".internal") {
		return false
	}
	if address := net.ParseIP(hostname); address != nil && (address.IsLoopback() || address.IsPrivate() || address.IsLinkLocalUnicast() || address.IsUnspecified()) {
		return false
	}
	return true
}

func validateArticleReviewInput(input articleReviewRequest) error {
	if !articleIDPattern.MatchString(input.ArticleID) {
		return errors.New("invalid article ID")
	}
	if input.Decision != "relevant" && input.Decision != "not_relevant" && input.Decision != "uncertain" {
		return errors.New("decision must be relevant, not_relevant, or uncertain")
	}
	return nil
}

func (store *articleReviewStore) save(article qualityArticle, decision string) (articleReviewRecord, error) {
	record := articleReviewRecord{
		ArticleID:     article.ArticleID,
		Title:         article.Title,
		URL:           article.URL,
		SourceDomain:  article.SourceDomain,
		MatchStrength: article.MatchStrength,
		ReviewBucket:  article.ReviewBucket,
		Decision:      decision,
		ReviewedAt:    store.now().UTC().Format(time.RFC3339Nano),
	}
	if err := validateStoredArticleReview(record); err != nil {
		return articleReviewRecord{}, err
	}
	line, err := json.Marshal(record)
	if err != nil {
		return articleReviewRecord{}, err
	}
	line = append(line, '\n')
	store.mu.Lock()
	defer store.mu.Unlock()
	if info, err := os.Stat(store.path); err == nil && info.Size()+int64(len(line)) > maxArticleReviewLogBytes {
		return articleReviewRecord{}, errors.New("article review log size limit reached")
	} else if err != nil && !os.IsNotExist(err) {
		return articleReviewRecord{}, err
	}
	if err := os.MkdirAll(filepath.Dir(store.path), 0o750); err != nil {
		return articleReviewRecord{}, err
	}
	file, err := os.OpenFile(store.path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return articleReviewRecord{}, err
	}
	defer file.Close()
	if _, err := file.Write(line); err != nil {
		return articleReviewRecord{}, err
	}
	if err := file.Sync(); err != nil {
		return articleReviewRecord{}, err
	}
	return record, nil
}

func (store *articleReviewStore) list() ([]articleReviewRecord, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	file, err := os.Open(store.path)
	if os.IsNotExist(err) {
		return []articleReviewRecord{}, nil
	}
	if err != nil {
		return nil, err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return nil, err
	}
	if info.Size() > maxArticleReviewLogBytes {
		return nil, fmt.Errorf("article review log exceeds %d bytes", maxArticleReviewLogBytes)
	}
	latest := make(map[string]articleReviewRecord)
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 1024), maxReviewRequestBytes)
	for scanner.Scan() {
		line := bytes.TrimSpace(scanner.Bytes())
		if len(line) == 0 {
			continue
		}
		var record articleReviewRecord
		if err := json.Unmarshal(line, &record); err != nil || validateStoredArticleReview(record) != nil {
			return nil, errors.New("invalid article review log entry")
		}
		latest[record.ArticleID] = record
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	reviews := make([]articleReviewRecord, 0, len(latest))
	for _, record := range latest {
		reviews = append(reviews, record)
	}
	sort.Slice(reviews, func(left, right int) bool {
		return strings.Compare(reviews[left].ReviewedAt, reviews[right].ReviewedAt) > 0
	})
	return reviews, nil
}

func validateStoredArticleReview(record articleReviewRecord) error {
	if err := validateArticleReviewInput(articleReviewRequest{ArticleID: record.ArticleID, Decision: record.Decision}); err != nil {
		return err
	}
	if len(record.Title) < 1 || len(record.Title) > 1024 || len(record.SourceDomain) > 255 || !safeExternalArticleURL(record.URL) {
		return errors.New("invalid stored article evidence")
	}
	if record.MatchStrength != "high" && record.MatchStrength != "weak" {
		return errors.New("invalid stored article strength")
	}
	if record.ReviewBucket != "high_match" && record.ReviewBucket != "headline_conflict" && record.ReviewBucket != "ambiguous_match" {
		return errors.New("invalid stored article bucket")
	}
	if _, err := time.Parse(time.RFC3339Nano, record.ReviewedAt); err != nil {
		return errors.New("invalid stored article review timestamp")
	}
	return nil
}
