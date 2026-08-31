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
	"unicode"
	"unicode/utf8"
)

const (
	maxQualitySampleBytes      = 512 << 10
	maxArticleReviewLogBytes   = 4 << 20
	minimumArticleReviewSample = 20
	minimumStratumReviews      = 5
	articleDecisionSchemaV2    = 2
	articleReviewProtocolV1    = 1
	trainingDataSchemaVersion  = 2
	maximumArticleReviewTags   = 8
	maximumArticleTagRunes     = 32
	articleReviewLockTimeout   = 5 * time.Second
	articleReviewLockStaleAge  = time.Hour
)

var articleIDPattern = regexp.MustCompile(`^[a-f0-9]{64}$`)

var articleReviewBases = map[string]struct{}{
	"full_article":      {},
	"publisher_summary": {},
	"headline_only":     {},
	"unavailable":       {},
}

var articleHeadlineSupportValues = map[string]struct{}{
	"sufficient":          {},
	"body_required":       {},
	"conflicts_with_body": {},
}

var articleNoSignalReasons = map[string]struct{}{
	"flood_context_analysis":  {},
	"other_weather_non_flood": {},
	"unrelated_false_match":   {},
}

var articleUncertaintyReasons = map[string]struct{}{
	"access_blocked":              {},
	"page_unavailable":            {},
	"wrong_or_junk_page":          {},
	"multi_story_page":            {},
	"language_barrier":            {},
	"insufficient_or_conflicting": {},
}

var articleImpactFlags = map[string]struct{}{
	"fatality":                {},
	"injury":                  {},
	"evacuation_displacement": {},
	"rescue_search":           {},
	"property_crop_damage":    {},
	"transport_disruption":    {},
	"utility_disruption":      {},
}

var articleContextFlags = map[string]struct{}{
	"aftermath_recovery":    {},
	"climate_background":    {},
	"historical_background": {},
	"policy_preparedness":   {},
}

type qualityArticle struct {
	ArticleID             string                         `json:"article_id"`
	SeenAt                string                         `json:"seen_at"`
	Title                 string                         `json:"title"`
	TitleSource           string                         `json:"title_source,omitempty"`
	URL                   string                         `json:"url"`
	SourceDomain          string                         `json:"source_domain"`
	LocationName          string                         `json:"location_name"`
	MatchStrength         string                         `json:"match_strength"`
	ReviewBucket          string                         `json:"review_bucket"`
	ReviewReason          string                         `json:"review_reason"`
	Themes                []string                       `json:"themes"`
	QualityFlags          []string                       `json:"quality_flags"`
	Decision              string                         `json:"decision,omitempty"`
	DecisionSchemaVersion int                            `json:"decision_schema_version,omitempty"`
	Tags                  []string                       `json:"tags,omitempty"`
	ReviewProtocolVersion int                            `json:"review_protocol_version,omitempty"`
	ReviewBasis           string                         `json:"review_basis,omitempty"`
	HeadlineSupport       string                         `json:"headline_support,omitempty"`
	NoSignalReason        string                         `json:"no_signal_reason,omitempty"`
	UncertaintyReason     string                         `json:"uncertainty_reason,omitempty"`
	ImpactFlags           []string                       `json:"impact_flags,omitempty"`
	ContextFlags          []string                       `json:"context_flags,omitempty"`
	ReviewedAt            string                         `json:"reviewed_at,omitempty"`
	SelectionIntent       *qualityArticleSelectionIntent `json:"selection_intent,omitempty"`
}

type qualitySampleFile struct {
	Version                int                           `json:"version"`
	SampleDate             string                        `json:"sample_date"`
	ArchiveArticles        int                           `json:"archive_articles"`
	EligibleArticles       int                           `json:"eligible_articles"`
	QueueCandidateArticles int                           `json:"queue_candidate_articles,omitempty"`
	SelectionIntent        *qualitySampleSelectionIntent `json:"selection_intent,omitempty"`
	Articles               []qualityArticle              `json:"articles"`
}

type qualityArticleSelectionIntent struct {
	Rank          int      `json:"rank"`
	SamplingSplit string   `json:"sampling_split,omitempty"`
	Reasons       []string `json:"reasons"`
}

type qualitySampleSelectionIntent struct {
	Strategy              string                    `json:"strategy"`
	Target                string                    `json:"target"`
	UsableRows            int                       `json:"usable_rows"`
	UsableRowsMinimum     int                       `json:"usable_rows_minimum"`
	ClassCounts           map[string]int            `json:"class_counts"`
	ClassMinimum          int                       `json:"class_minimum"`
	DistinctArticleDates  int                       `json:"distinct_article_dates"`
	ArticleDateMinimum    int                       `json:"article_date_minimum"`
	PublisherGroups       int                       `json:"publisher_groups"`
	PublisherGroupMinimum int                       `json:"publisher_group_minimum"`
	InferenceTextCoverage float64                   `json:"inference_text_coverage"`
	InferenceTextMinimum  float64                   `json:"inference_text_minimum"`
	SplitClassCounts      map[string]map[string]int `json:"split_class_counts"`
	SplitClassMinimums    map[string]int            `json:"split_class_minimums"`
	ReadinessStatus       string                    `json:"readiness_status"`
	ProductionMinimums    qualityProductionMinimums `json:"production_minimums"`
}

type qualityProductionMinimums struct {
	TotalUsableRows       int            `json:"total_usable_rows"`
	ClassMinimum          int            `json:"class_minimum"`
	ArticleDates          int            `json:"article_dates"`
	PublisherGroups       int            `json:"publisher_groups"`
	InferenceTextCoverage float64        `json:"inference_text_coverage"`
	SplitClassMinimums    map[string]int `json:"split_class_minimums"`
}

type articleReviewRequest struct {
	ArticleID             string    `json:"article_id"`
	Decision              string    `json:"decision"`
	Tags                  *[]string `json:"tags,omitempty"`
	ReviewProtocolVersion int       `json:"review_protocol_version"`
	ReviewBasis           string    `json:"review_basis"`
	HeadlineSupport       string    `json:"headline_support,omitempty"`
	NoSignalReason        string    `json:"no_signal_reason,omitempty"`
	UncertaintyReason     string    `json:"uncertainty_reason,omitempty"`
	ImpactFlags           []string  `json:"impact_flags,omitempty"`
	ContextFlags          []string  `json:"context_flags,omitempty"`
}

type articleReviewRecord struct {
	ArticleID             string   `json:"article_id"`
	Title                 string   `json:"title"`
	TitleSource           string   `json:"title_source,omitempty"`
	URL                   string   `json:"url"`
	SourceDomain          string   `json:"source_domain"`
	MatchStrength         string   `json:"match_strength"`
	ReviewBucket          string   `json:"review_bucket"`
	Decision              string   `json:"decision"`
	DecisionSchemaVersion int      `json:"decision_schema_version"`
	Tags                  []string `json:"tags,omitempty"`
	ReviewProtocolVersion int      `json:"review_protocol_version,omitempty"`
	ReviewBasis           string   `json:"review_basis,omitempty"`
	HeadlineSupport       string   `json:"headline_support,omitempty"`
	NoSignalReason        string   `json:"no_signal_reason,omitempty"`
	UncertaintyReason     string   `json:"uncertainty_reason,omitempty"`
	ImpactFlags           []string `json:"impact_flags,omitempty"`
	ContextFlags          []string `json:"context_flags,omitempty"`
	ReviewedAt            string   `json:"reviewed_at"`
}

type articleReviewResponse struct {
	Review articleReviewRecord `json:"review"`
}

type articleReviewSummaryResponse struct {
	TotalReviews              int      `json:"total_reviews"`
	LegacyReviews             int      `json:"legacy_reviews"`
	ReportedFloodingArticles  int      `json:"reported_flooding_articles"`
	FloodRiskWarningArticles  int      `json:"flood_risk_warning_articles"`
	HeavyRainOnlyArticles     int      `json:"heavy_rain_only_articles"`
	NotFloodRelatedArticles   int      `json:"not_flood_related_articles"`
	Uncertain                 int      `json:"uncertain"`
	ResolvedReviews           int      `json:"resolved_reviews"`
	MinimumSample             int      `json:"minimum_sample"`
	RemainingToSample         int      `json:"remaining_to_sample"`
	HighResolved              int      `json:"high_resolved"`
	HighFloodRelated          int      `json:"high_flood_related"`
	WeakResolved              int      `json:"weak_resolved"`
	WeakFloodRelated          int      `json:"weak_flood_related"`
	HighMatchFloodRelatedRate *float64 `json:"high_match_flood_related_rate"`
	WeakMatchFloodRelatedRate *float64 `json:"weak_match_flood_related_rate"`
	Status                    string   `json:"status"`
}

type trainingArticle struct {
	articleReviewRecord
	TrainingEligible bool   `json:"training_eligible"`
	ExclusionReason  string `json:"exclusion_reason"`
}

type trainingArticleSummary struct {
	TotalArticles         int            `json:"total_articles"`
	LatestReviewedAt      string         `json:"latest_reviewed_at,omitempty"`
	TrainingEligible      int            `json:"training_eligible"`
	Excluded              int            `json:"excluded"`
	ClassCounts           map[string]int `json:"class_counts"`
	ExclusionReasonCounts map[string]int `json:"exclusion_reason_counts"`
}

type trainingArticlesResponse struct {
	SchemaVersion int                    `json:"schema_version"`
	Summary       trainingArticleSummary `json:"summary"`
	Articles      []trainingArticle      `json:"articles"`
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
				sample.Articles[index].DecisionSchemaVersion = review.DecisionSchemaVersion
				sample.Articles[index].Tags = append([]string(nil), review.Tags...)
				sample.Articles[index].ReviewProtocolVersion = review.ReviewProtocolVersion
				sample.Articles[index].ReviewBasis = review.ReviewBasis
				sample.Articles[index].HeadlineSupport = review.HeadlineSupport
				sample.Articles[index].NoSignalReason = review.NoSignalReason
				sample.Articles[index].UncertaintyReason = review.UncertaintyReason
				sample.Articles[index].ImpactFlags = append([]string(nil), review.ImpactFlags...)
				sample.Articles[index].ContextFlags = append([]string(nil), review.ContextFlags...)
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
		if err := validateArticleReviewInput(&input); err != nil {
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
		review, err := service.articleReviews.save(*selected, input)
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
		if review.DecisionSchemaVersion == 0 || review.DecisionSchemaVersion == 1 {
			summary.LegacyReviews++
			continue
		}
		if review.DecisionSchemaVersion != articleDecisionSchemaV2 {
			continue
		}
		floodRelated := false
		switch review.Decision {
		case "reported_flooding":
			summary.ReportedFloodingArticles++
			floodRelated = true
		case "flood_risk_warning":
			summary.FloodRiskWarningArticles++
			floodRelated = true
		case "heavy_rain_only":
			summary.HeavyRainOnlyArticles++
		case "not_flood_related":
			summary.NotFloodRelatedArticles++
		case "uncertain":
			summary.Uncertain++
			continue
		default:
			continue
		}
		if review.MatchStrength == "high" {
			summary.HighResolved++
			if floodRelated {
				summary.HighFloodRelated++
			}
		} else {
			summary.WeakResolved++
			if floodRelated {
				summary.WeakFloodRelated++
			}
		}
	}
	summary.ResolvedReviews = summary.ReportedFloodingArticles + summary.FloodRiskWarningArticles + summary.HeavyRainOnlyArticles + summary.NotFloodRelatedArticles
	summary.RemainingToSample = max(0, minimumArticleReviewSample-summary.ResolvedReviews)
	if summary.ResolvedReviews >= minimumArticleReviewSample && summary.HighResolved >= minimumStratumReviews && summary.WeakResolved >= minimumStratumReviews {
		highFloodRelatedRate := float64(summary.HighFloodRelated) / float64(summary.HighResolved)
		weakFloodRelatedRate := float64(summary.WeakFloodRelated) / float64(summary.WeakResolved)
		summary.HighMatchFloodRelatedRate = &highFloodRelatedRate
		summary.WeakMatchFloodRelatedRate = &weakFloodRelatedRate
		summary.Status = "sample_ready"
	}
	return summary
}

func (service *api) trainingArticles(writer http.ResponseWriter, request *http.Request) {
	if !requireGet(writer, request) {
		return
	}
	reviews, err := service.articleReviews.list()
	if err != nil {
		service.logger.Printf("training articles unavailable: %v", err)
		writeError(writer, http.StatusInternalServerError, "training articles unavailable")
		return
	}
	writer.Header().Set("Cache-Control", "no-store")
	writeJSON(writer, http.StatusOK, buildTrainingArticlesResponse(reviews))
}

func buildTrainingArticlesResponse(reviews []articleReviewRecord) trainingArticlesResponse {
	response := trainingArticlesResponse{
		SchemaVersion: trainingDataSchemaVersion,
		Summary: trainingArticleSummary{
			TotalArticles: len(reviews),
			ClassCounts: map[string]int{
				"reported_flooding":  0,
				"flood_risk_warning": 0,
				"heavy_rain_only":    0,
				"not_flood_related":  0,
			},
			ExclusionReasonCounts: map[string]int{
				"legacy_schema":           0,
				"uncertain":               0,
				"headline_not_sufficient": 0,
			},
		},
		Articles: make([]trainingArticle, 0, len(reviews)),
	}
	for _, review := range reviews {
		if reviewedAt, err := time.Parse(time.RFC3339Nano, review.ReviewedAt); err == nil {
			latestAt, latestErr := time.Parse(time.RFC3339Nano, response.Summary.LatestReviewedAt)
			if latestErr != nil || reviewedAt.After(latestAt) {
				response.Summary.LatestReviewedAt = reviewedAt.Format(time.RFC3339Nano)
			}
		}
		eligible, reason := articleTrainingEligibility(review)
		response.Articles = append(response.Articles, trainingArticle{
			articleReviewRecord: review,
			TrainingEligible:    eligible,
			ExclusionReason:     reason,
		})
		if eligible {
			response.Summary.TrainingEligible++
			response.Summary.ClassCounts[review.Decision]++
			continue
		}
		response.Summary.Excluded++
		response.Summary.ExclusionReasonCounts[reason]++
	}
	return response
}

func articleTrainingEligibility(review articleReviewRecord) (bool, string) {
	if review.DecisionSchemaVersion != articleDecisionSchemaV2 {
		return false, "legacy_schema"
	}
	switch review.Decision {
	case "reported_flooding", "flood_risk_warning", "heavy_rain_only", "not_flood_related":
		if review.ReviewProtocolVersion == articleReviewProtocolV1 && review.HeadlineSupport != "sufficient" {
			return false, "headline_not_sufficient"
		}
		return true, ""
	case "uncertain":
		return false, "uncertain"
	default:
		return false, "unsupported_label"
	}
}

func (service *api) trainingArticleExport(writer http.ResponseWriter, request *http.Request) {
	if !requireGet(writer, request) {
		return
	}
	reviews, err := service.articleReviews.list()
	if err != nil {
		service.logger.Printf("training article export unavailable: %v", err)
		writeError(writer, http.StatusInternalServerError, "training article export unavailable")
		return
	}

	var output bytes.Buffer
	_, _ = output.Write([]byte{0xef, 0xbb, 0xbf})
	csvWriter := csv.NewWriter(&output)
	csvWriter.UseCRLF = true
	columns := []string{"article_id", "title", "title_source", "url", "source_domain", "match_strength", "review_bucket", "decision", "decision_schema_version", "reviewed_at", "tags", "training_eligible", "exclusion_reason", "review_protocol_version", "review_basis", "headline_support", "no_signal_reason", "uncertainty_reason", "impact_flags", "context_flags"}
	if err := csvWriter.Write(columns); err != nil {
		writeError(writer, http.StatusInternalServerError, "training article export unavailable")
		return
	}
	for _, article := range buildTrainingArticlesResponse(reviews).Articles {
		row := []string{
			article.ArticleID,
			article.Title,
			article.TitleSource,
			article.URL,
			article.SourceDomain,
			article.MatchStrength,
			article.ReviewBucket,
			article.Decision,
			fmt.Sprintf("%d", article.DecisionSchemaVersion),
			article.ReviewedAt,
			strings.Join(article.Tags, "|"),
			fmt.Sprintf("%t", article.TrainingEligible),
			article.ExclusionReason,
			fmt.Sprintf("%d", article.ReviewProtocolVersion),
			article.ReviewBasis,
			article.HeadlineSupport,
			article.NoSignalReason,
			article.UncertaintyReason,
			strings.Join(article.ImpactFlags, "|"),
			strings.Join(article.ContextFlags, "|"),
		}
		for index := range row {
			row[index] = articleSpreadsheetSafe(row[index])
		}
		if err := csvWriter.Write(row); err != nil {
			writeError(writer, http.StatusInternalServerError, "training article export unavailable")
			return
		}
	}
	csvWriter.Flush()
	if csvWriter.Error() != nil {
		writeError(writer, http.StatusInternalServerError, "training article export unavailable")
		return
	}
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Content-Disposition", `attachment; filename="crisispulse-training-articles.csv"`)
	writer.Header().Set("Content-Type", "text/csv; charset=utf-8")
	writer.WriteHeader(http.StatusOK)
	if request.Method != http.MethodHead {
		_, _ = writer.Write(output.Bytes())
	}
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
	columns := []string{"article_id", "title", "title_source", "url", "source_domain", "match_strength", "review_bucket", "decision", "decision_schema_version", "reviewed_at", "tags", "review_protocol_version", "review_basis", "headline_support", "no_signal_reason", "uncertainty_reason", "impact_flags", "context_flags"}
	if err := csvWriter.Write(columns); err != nil {
		writeError(writer, http.StatusInternalServerError, "article review export unavailable")
		return
	}
	for _, review := range reviews {
		row := []string{review.ArticleID, review.Title, review.TitleSource, review.URL, review.SourceDomain, review.MatchStrength, review.ReviewBucket, review.Decision, fmt.Sprintf("%d", review.DecisionSchemaVersion), review.ReviewedAt, strings.Join(review.Tags, "|"), fmt.Sprintf("%d", review.ReviewProtocolVersion), review.ReviewBasis, review.HeadlineSupport, review.NoSignalReason, review.UncertaintyReason, strings.Join(review.ImpactFlags, "|"), strings.Join(review.ContextFlags, "|")}
		for index := range row {
			row[index] = articleSpreadsheetSafe(row[index])
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

func articleSpreadsheetSafe(value string) string {
	candidate := strings.TrimLeft(value, " \n")
	if candidate != "" {
		first, _ := utf8.DecodeRuneInString(candidate)
		if strings.ContainsRune("=+-@\t\r", first) {
			return "'" + value
		}
	}
	return value
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
	if (sample.Version != 1 && sample.Version != 2) || sample.ArchiveArticles < 0 || sample.EligibleArticles < 0 || len(sample.Articles) > 40 || (sample.Version == 1 && len(sample.Articles) == 0) {
		return qualitySampleFile{}, errors.New("invalid quality sample metadata")
	}
	if sample.Version == 1 && sample.SelectionIntent != nil {
		return qualitySampleFile{}, errors.New("invalid quality sample selection intent")
	}
	if sample.Version == 2 {
		if sample.QueueCandidateArticles < 0 {
			return qualitySampleFile{}, errors.New("invalid quality sample candidate count")
		}
		if err := validateQualitySampleSelectionIntent(sample.SelectionIntent); err != nil {
			return qualitySampleFile{}, err
		}
	}
	if _, err := time.Parse("2006-01-02", sample.SampleDate); err != nil {
		return qualitySampleFile{}, errors.New("invalid quality sample date")
	}
	seen := make(map[string]bool, len(sample.Articles))
	seenRanks := make(map[int]bool, len(sample.Articles))
	for _, article := range sample.Articles {
		if err := validateQualityArticle(article); err != nil {
			return qualitySampleFile{}, err
		}
		if sample.Version == 1 && article.SelectionIntent != nil {
			return qualitySampleFile{}, errors.New("invalid quality article selection intent")
		}
		if sample.Version == 2 {
			if err := validateQualityArticleSelectionIntent(article.SelectionIntent, len(sample.Articles)); err != nil {
				return qualitySampleFile{}, err
			}
			if seenRanks[article.SelectionIntent.Rank] {
				return qualitySampleFile{}, errors.New("duplicate quality article selection rank")
			}
			seenRanks[article.SelectionIntent.Rank] = true
		}
		if seen[article.ArticleID] {
			return qualitySampleFile{}, errors.New("duplicate quality sample article")
		}
		seen[article.ArticleID] = true
	}
	return sample, nil
}

var qualitySamplingLabels = map[string]bool{
	"reported_flooding":  true,
	"flood_risk_warning": true,
	"heavy_rain_only":    true,
	"not_flood_related":  true,
}

var qualitySelectionReasons = map[string]bool{
	"underrepresented_class":   true,
	"underrepresented_split":   true,
	"new_article_date":         true,
	"new_publisher_group":      true,
	"inference_text_available": true,
	"needs_detailed_relabel":   true,
	"balanced_fallback":        true,
}

func validateQualityArticleSelectionIntent(intent *qualityArticleSelectionIntent, articleCount int) error {
	if intent == nil || intent.Rank < 1 || intent.Rank > articleCount || len(intent.Reasons) < 1 || len(intent.Reasons) > 7 {
		return errors.New("invalid quality article selection intent")
	}
	if intent.SamplingSplit != "" && intent.SamplingSplit != "training" && intent.SamplingSplit != "validation" && intent.SamplingSplit != "test" {
		return errors.New("invalid quality article sampling split")
	}
	seen := make(map[string]bool, len(intent.Reasons))
	for _, reason := range intent.Reasons {
		if !qualitySelectionReasons[reason] || seen[reason] {
			return errors.New("invalid quality article selection reason")
		}
		seen[reason] = true
	}
	return nil
}

func validateQualitySampleSelectionIntent(intent *qualitySampleSelectionIntent) error {
	if intent == nil || intent.Strategy != "training_readiness_v1" || intent.Target != "cpu_smoke" {
		return errors.New("invalid quality sample selection intent")
	}
	if intent.UsableRows < 0 || intent.UsableRowsMinimum < 1 || intent.ClassMinimum < 1 || intent.ArticleDateMinimum < 1 || intent.PublisherGroupMinimum < 1 || intent.DistinctArticleDates < 0 || intent.PublisherGroups < 0 {
		return errors.New("invalid quality sample readiness counts")
	}
	if intent.InferenceTextCoverage < 0 || intent.InferenceTextCoverage > 1 || intent.InferenceTextMinimum < 0 || intent.InferenceTextMinimum > 1 {
		return errors.New("invalid quality sample text coverage")
	}
	if intent.ReadinessStatus != "computed" && intent.ReadinessStatus != "unavailable" {
		return errors.New("invalid quality sample readiness status")
	}
	if err := validateQualityClassCounts(intent.ClassCounts); err != nil {
		return err
	}
	if err := validateQualitySplitCounts(intent.SplitClassCounts, true); err != nil {
		return err
	}
	if err := validateQualitySplitMinimums(intent.SplitClassMinimums); err != nil {
		return err
	}
	production := intent.ProductionMinimums
	if production.TotalUsableRows < 1 || production.ClassMinimum < 1 || production.ArticleDates < 1 || production.PublisherGroups < 1 || production.InferenceTextCoverage < 0 || production.InferenceTextCoverage > 1 {
		return errors.New("invalid quality sample production minimums")
	}
	return validateQualitySplitMinimums(production.SplitClassMinimums)
}

func validateQualityClassCounts(counts map[string]int) error {
	if len(counts) != len(qualitySamplingLabels) {
		return errors.New("invalid quality sample class counts")
	}
	for label := range qualitySamplingLabels {
		if count, ok := counts[label]; !ok || count < 0 {
			return errors.New("invalid quality sample class counts")
		}
	}
	return nil
}

func validateQualitySplitCounts(counts map[string]map[string]int, allowUnavailable bool) error {
	if allowUnavailable && len(counts) == 0 {
		return nil
	}
	if len(counts) != 3 {
		return errors.New("invalid quality sample split counts")
	}
	for _, split := range []string{"training", "validation", "test"} {
		if err := validateQualityClassCounts(counts[split]); err != nil {
			return errors.New("invalid quality sample split counts")
		}
	}
	return nil
}

func validateQualitySplitMinimums(minimums map[string]int) error {
	if len(minimums) != 3 {
		return errors.New("invalid quality sample split minimums")
	}
	for _, split := range []string{"training", "validation", "test"} {
		if minimum, ok := minimums[split]; !ok || minimum < 1 {
			return errors.New("invalid quality sample split minimums")
		}
	}
	return nil
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

func validateArticleReviewInput(input *articleReviewRequest) error {
	if !articleIDPattern.MatchString(input.ArticleID) {
		return errors.New("invalid article ID")
	}
	if !isArticleDecisionV2(input.Decision) {
		return errors.New("decision must be reported_flooding, flood_risk_warning, heavy_rain_only, not_flood_related, or uncertain")
	}
	return validateArticleReviewProtocol(
		input.ReviewProtocolVersion,
		input.Decision,
		input.ReviewBasis,
		input.HeadlineSupport,
		input.NoSignalReason,
		input.UncertaintyReason,
		input.ImpactFlags,
		input.ContextFlags,
		input.Tags != nil,
	)
}

func validateArticleReviewProtocol(
	protocolVersion int,
	decision string,
	reviewBasis string,
	headlineSupport string,
	noSignalReason string,
	uncertaintyReason string,
	impactFlags []string,
	contextFlags []string,
	tagsPresent bool,
) error {
	if protocolVersion != articleReviewProtocolV1 {
		return errors.New("review_protocol_version must be 1")
	}
	if tagsPresent {
		return errors.New("free-form tags are not accepted by review protocol 1")
	}
	if _, ok := articleReviewBases[reviewBasis]; !ok {
		return errors.New("invalid review_basis")
	}
	if err := validateArticleProtocolFlags("impact_flags", impactFlags, articleImpactFlags); err != nil {
		return err
	}
	if err := validateArticleProtocolFlags("context_flags", contextFlags, articleContextFlags); err != nil {
		return err
	}

	if decision == "uncertain" {
		if _, ok := articleUncertaintyReasons[uncertaintyReason]; !ok {
			return errors.New("uncertain reviews require a valid uncertainty_reason")
		}
		if headlineSupport != "" || noSignalReason != "" || len(impactFlags) > 0 || len(contextFlags) > 0 {
			return errors.New("uncertain reviews cannot include headline_support, no_signal_reason, impact_flags, or context_flags")
		}
		return nil
	}

	if reviewBasis == "unavailable" {
		return errors.New("unavailable review_basis requires an uncertain decision")
	}
	if _, ok := articleHeadlineSupportValues[headlineSupport]; !ok {
		return errors.New("resolved reviews require a valid headline_support")
	}
	if reviewBasis == "headline_only" && headlineSupport != "sufficient" {
		return errors.New("headline_only reviews require sufficient headline_support")
	}
	if uncertaintyReason != "" {
		return errors.New("resolved reviews cannot include uncertainty_reason")
	}
	if decision == "not_flood_related" {
		if _, ok := articleNoSignalReasons[noSignalReason]; !ok {
			return errors.New("not_flood_related reviews require a valid no_signal_reason")
		}
	} else if noSignalReason != "" {
		return errors.New("only not_flood_related reviews may include no_signal_reason")
	}
	return nil
}

func validateArticleProtocolFlags(name string, values []string, allowed map[string]struct{}) error {
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		if _, ok := allowed[value]; !ok {
			return fmt.Errorf("invalid %s", name)
		}
		if _, duplicate := seen[value]; duplicate {
			return fmt.Errorf("duplicate %s", name)
		}
		seen[value] = struct{}{}
	}
	return nil
}

func normalizeArticleTags(tags []string) ([]string, error) {
	normalized := make([]string, 0, len(tags))
	seen := make(map[string]struct{}, len(tags))
	for _, tag := range tags {
		canonical := normalizeArticleTag(tag)
		if canonical == "" {
			return nil, errors.New("article tags must contain at least one letter or digit")
		}
		if utf8.RuneCountInString(canonical) > maximumArticleTagRunes {
			return nil, fmt.Errorf("article tags must be at most %d characters", maximumArticleTagRunes)
		}
		if _, duplicate := seen[canonical]; duplicate {
			continue
		}
		seen[canonical] = struct{}{}
		normalized = append(normalized, canonical)
		if len(normalized) > maximumArticleReviewTags {
			return nil, fmt.Errorf("article reviews may have at most %d tags", maximumArticleReviewTags)
		}
	}
	return normalized, nil
}

func normalizeArticleTag(value string) string {
	normalized := make([]rune, 0, len(value))
	separatorPending := false
	for _, character := range value {
		if unicode.IsLetter(character) || unicode.IsDigit(character) {
			if separatorPending && len(normalized) > 0 {
				normalized = append(normalized, '-')
			}
			normalized = append(normalized, unicode.ToLower(character))
			separatorPending = false
			continue
		}
		if len(normalized) > 0 {
			separatorPending = true
		}
	}
	return string(normalized)
}

func isArticleDecisionV2(decision string) bool {
	switch decision {
	case "reported_flooding", "flood_risk_warning", "heavy_rain_only", "not_flood_related", "uncertain":
		return true
	default:
		return false
	}
}

func isArticleDecisionV1(decision string) bool {
	switch decision {
	case "relevant", "not_relevant", "uncertain":
		return true
	default:
		return false
	}
}

func acquireArticleReviewFileLock(reviewPath string) (func(), error) {
	lockPath := reviewPath + ".lock"
	deadline := time.Now().Add(articleReviewLockTimeout)
	for {
		file, err := os.OpenFile(lockPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
		if err == nil {
			if closeErr := file.Close(); closeErr != nil {
				_ = os.Remove(lockPath)
				return nil, closeErr
			}
			return func() { _ = os.Remove(lockPath) }, nil
		}
		if !os.IsExist(err) {
			return nil, err
		}
		if info, statErr := os.Stat(lockPath); statErr == nil && time.Since(info.ModTime()) > articleReviewLockStaleAge {
			if removeErr := os.Remove(lockPath); removeErr == nil || os.IsNotExist(removeErr) {
				continue
			}
		}
		if time.Now().After(deadline) {
			return nil, errors.New("article review log is busy")
		}
		time.Sleep(25 * time.Millisecond)
	}
}

func (store *articleReviewStore) save(article qualityArticle, input articleReviewRequest) (articleReviewRecord, error) {
	record := articleReviewRecord{
		ArticleID:             article.ArticleID,
		Title:                 article.Title,
		TitleSource:           article.TitleSource,
		URL:                   article.URL,
		SourceDomain:          article.SourceDomain,
		MatchStrength:         article.MatchStrength,
		ReviewBucket:          article.ReviewBucket,
		Decision:              input.Decision,
		DecisionSchemaVersion: articleDecisionSchemaV2,
		ReviewProtocolVersion: input.ReviewProtocolVersion,
		ReviewBasis:           input.ReviewBasis,
		HeadlineSupport:       input.HeadlineSupport,
		NoSignalReason:        input.NoSignalReason,
		UncertaintyReason:     input.UncertaintyReason,
		ImpactFlags:           append([]string(nil), input.ImpactFlags...),
		ContextFlags:          append([]string(nil), input.ContextFlags...),
		ReviewedAt:            store.now().UTC().Format(time.RFC3339Nano),
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
	if err := os.MkdirAll(filepath.Dir(store.path), 0o750); err != nil {
		return articleReviewRecord{}, err
	}
	releaseLock, err := acquireArticleReviewFileLock(store.path)
	if err != nil {
		return articleReviewRecord{}, err
	}
	defer releaseLock()
	if info, err := os.Stat(store.path); err == nil && info.Size()+int64(len(line)) > maxArticleReviewLogBytes {
		return articleReviewRecord{}, errors.New("article review log size limit reached")
	} else if err != nil && !os.IsNotExist(err) {
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
		if err := json.Unmarshal(line, &record); err != nil {
			return nil, errors.New("invalid article review log entry")
		}
		if record.DecisionSchemaVersion == 0 {
			record.DecisionSchemaVersion = 1
		}
		if validateStoredArticleReview(record) != nil {
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
	if !articleIDPattern.MatchString(record.ArticleID) {
		return errors.New("invalid article ID")
	}
	switch record.DecisionSchemaVersion {
	case 1:
		if !isArticleDecisionV1(record.Decision) {
			return errors.New("invalid schema v1 article decision")
		}
		if len(record.Tags) > 0 {
			return errors.New("schema v1 article reviews cannot have tags")
		}
	case articleDecisionSchemaV2:
		if !isArticleDecisionV2(record.Decision) {
			return errors.New("invalid schema v2 article decision")
		}
	default:
		return errors.New("invalid article decision schema version")
	}

	switch record.ReviewProtocolVersion {
	case 0:
		if record.ReviewBasis != "" || record.HeadlineSupport != "" || record.NoSignalReason != "" || record.UncertaintyReason != "" || len(record.ImpactFlags) > 0 || len(record.ContextFlags) > 0 {
			return errors.New("legacy article review cannot contain protocol fields")
		}
		normalizedTags, err := normalizeArticleTags(record.Tags)
		if err != nil || len(normalizedTags) != len(record.Tags) {
			return errors.New("invalid legacy article tags")
		}
		for index := range normalizedTags {
			if normalizedTags[index] != record.Tags[index] {
				return errors.New("invalid legacy article tags")
			}
		}
	case articleReviewProtocolV1:
		if record.DecisionSchemaVersion != articleDecisionSchemaV2 {
			return errors.New("review protocol 1 requires decision schema 2")
		}
		if err := validateArticleReviewProtocol(
			record.ReviewProtocolVersion,
			record.Decision,
			record.ReviewBasis,
			record.HeadlineSupport,
			record.NoSignalReason,
			record.UncertaintyReason,
			record.ImpactFlags,
			record.ContextFlags,
			record.Tags != nil,
		); err != nil {
			return err
		}
	default:
		return errors.New("invalid article review protocol version")
	}
	if len(record.Title) < 1 || len(record.Title) > 1024 || len(record.SourceDomain) > 255 || !safeExternalArticleURL(record.URL) {
		return errors.New("invalid stored article evidence")
	}
	if record.TitleSource != "" && record.TitleSource != "manual_override" && record.TitleSource != "publisher_metadata" && record.TitleSource != "url_path" && record.TitleSource != "unavailable" {
		return errors.New("invalid stored article title source")
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
