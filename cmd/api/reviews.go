package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	maxReviewRequestBytes = 16 << 10
	maxReviewLogBytes     = 4 << 20
)

var regionCodePattern = regexp.MustCompile(`^[A-Za-z0-9:_-]{1,64}$`)

type reviewRequest struct {
	RegionCode  string `json:"region_code"`
	WindowStart string `json:"window_start"`
	Decision    string `json:"decision"`
}

type reviewRecord struct {
	SignalID    string `json:"signal_id"`
	RegionCode  string `json:"region_code"`
	WindowStart string `json:"window_start"`
	Decision    string `json:"decision"`
	ReviewedAt  string `json:"reviewed_at"`
}

type reviewsResponse struct {
	Reviews []reviewRecord `json:"reviews"`
}

type reviewResponse struct {
	Review reviewRecord `json:"review"`
}

type reviewStore struct {
	path string
	now  func() time.Time
	mu   sync.Mutex
}

func newReviewStore(path string) *reviewStore {
	return &reviewStore{path: path, now: time.Now}
}

func (service *api) reviewDecisions(writer http.ResponseWriter, request *http.Request) {
	switch request.Method {
	case http.MethodGet, http.MethodHead:
		reviews, err := service.reviews.list()
		if err != nil {
			service.logger.Printf("reviews unavailable: %v", err)
			writeError(writer, http.StatusInternalServerError, "review decisions unavailable")
			return
		}
		writer.Header().Set("Cache-Control", "no-store")
		writeJSON(writer, http.StatusOK, reviewsResponse{Reviews: reviews})
	case http.MethodPost:
		mediaType, _, err := mime.ParseMediaType(request.Header.Get("Content-Type"))
		if err != nil || mediaType != "application/json" {
			writeError(writer, http.StatusUnsupportedMediaType, "Content-Type must be application/json")
			return
		}
		request.Body = http.MaxBytesReader(writer, request.Body, maxReviewRequestBytes)
		decoder := json.NewDecoder(request.Body)
		decoder.DisallowUnknownFields()
		var input reviewRequest
		if err := decoder.Decode(&input); err != nil {
			writeError(writer, http.StatusBadRequest, "invalid review decision")
			return
		}
		if err := requireJSONEnd(decoder); err != nil {
			writeError(writer, http.StatusBadRequest, "invalid review decision")
			return
		}
		review, err := service.reviews.save(input)
		if err != nil {
			if errors.Is(err, errInvalidReview) {
				writeError(writer, http.StatusBadRequest, err.Error())
				return
			}
			service.logger.Printf("review save failed: %v", err)
			writeError(writer, http.StatusInternalServerError, "review decision could not be saved")
			return
		}
		writer.Header().Set("Cache-Control", "no-store")
		writeJSON(writer, http.StatusCreated, reviewResponse{Review: review})
	default:
		writer.Header().Set("Allow", "GET, HEAD, POST")
		writeError(writer, http.StatusMethodNotAllowed, "method not allowed")
	}
}

var errInvalidReview = errors.New("invalid review decision")

func validateReview(input reviewRequest) error {
	if !regionCodePattern.MatchString(input.RegionCode) {
		return fmt.Errorf("%w: invalid region code", errInvalidReview)
	}
	if !validWindowStart(input.WindowStart) {
		return fmt.Errorf("%w: invalid window start", errInvalidReview)
	}
	switch input.Decision {
	case "confirmed_event", "irrelevant_news", "uncertain":
		return nil
	default:
		return fmt.Errorf("%w: decision must be confirmed_event, irrelevant_news, or uncertain", errInvalidReview)
	}
}

func validWindowStart(value string) bool {
	if len(value) < len("2006-01-02T15:04:05") || len(value) > 40 {
		return false
	}
	formats := []string{
		time.RFC3339Nano,
		"2006-01-02T15:04:05.999999999",
		"2006-01-02T15:04:05",
	}
	for _, format := range formats {
		if _, err := time.Parse(format, value); err == nil {
			return true
		}
	}
	return false
}

func signalID(regionCode, windowStart string) string {
	return regionCode + "|" + windowStart
}

func (store *reviewStore) save(input reviewRequest) (reviewRecord, error) {
	if err := validateReview(input); err != nil {
		return reviewRecord{}, err
	}
	record := reviewRecord{
		SignalID:    signalID(input.RegionCode, input.WindowStart),
		RegionCode:  input.RegionCode,
		WindowStart: input.WindowStart,
		Decision:    input.Decision,
		ReviewedAt:  store.now().UTC().Format(time.RFC3339Nano),
	}
	line, err := json.Marshal(record)
	if err != nil {
		return reviewRecord{}, err
	}
	line = append(line, '\n')

	store.mu.Lock()
	defer store.mu.Unlock()
	if info, err := os.Stat(store.path); err == nil && info.Size()+int64(len(line)) > maxReviewLogBytes {
		return reviewRecord{}, errors.New("review log size limit reached")
	} else if err != nil && !os.IsNotExist(err) {
		return reviewRecord{}, err
	}
	if err := os.MkdirAll(filepath.Dir(store.path), 0o750); err != nil {
		return reviewRecord{}, err
	}
	file, err := os.OpenFile(store.path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return reviewRecord{}, err
	}
	defer file.Close()
	if _, err := file.Write(line); err != nil {
		return reviewRecord{}, err
	}
	if err := file.Sync(); err != nil {
		return reviewRecord{}, err
	}
	return record, nil
}

func (store *reviewStore) list() ([]reviewRecord, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	file, err := os.Open(store.path)
	if os.IsNotExist(err) {
		return []reviewRecord{}, nil
	}
	if err != nil {
		return nil, err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return nil, err
	}
	if info.Size() > maxReviewLogBytes {
		return nil, fmt.Errorf("review log exceeds %d bytes", maxReviewLogBytes)
	}

	latest := make(map[string]reviewRecord)
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 1024), maxReviewRequestBytes)
	for scanner.Scan() {
		line := bytes.TrimSpace(scanner.Bytes())
		if len(line) == 0 {
			continue
		}
		var record reviewRecord
		if err := json.Unmarshal(line, &record); err != nil {
			return nil, fmt.Errorf("invalid review log entry: %w", err)
		}
		latest[record.SignalID] = record
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}

	reviews := make([]reviewRecord, 0, len(latest))
	for _, record := range latest {
		reviews = append(reviews, record)
	}
	sort.Slice(reviews, func(left, right int) bool {
		return strings.Compare(reviews[left].ReviewedAt, reviews[right].ReviewedAt) > 0
	})
	return reviews, nil
}

func requireJSONEnd(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return errors.New("request must contain one JSON object")
	}
	return nil
}
