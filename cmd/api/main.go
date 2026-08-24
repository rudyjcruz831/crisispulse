package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

const (
	maxDashboardBytes     = 2 << 20
	maxRefreshStatusBytes = 256 << 10
	maxBackupStatusBytes  = 16 << 10
	refreshStaleAfter     = 30 * time.Minute
	runningStaleAfter     = 15 * time.Minute
	backupStaleAfter      = 26 * time.Hour
	pilotSoakTargetHours  = 48
	pilotSoakInterval     = 15
	pilotSoakCoverage     = 95.0
	statusFutureTolerance = time.Minute
	refreshStatusVersion  = 3
	backupStatusVersion   = 2
)

type config struct {
	address          string
	dataPath         string
	reviewPath       string
	backupStatusPath string
	allowedOrigin    string
}

type dashboardData struct {
	Snapshot struct {
		UpdatedLabel string `json:"updated_label"`
		Candidates   int    `json:"candidates"`
	} `json:"snapshot"`
	Signals []json.RawMessage `json:"signals"`
}

type signalsResponse struct {
	UpdatedLabel       string            `json:"updated_label"`
	CandidateAnomalies int               `json:"candidate_anomalies"`
	Signals            []json.RawMessage `json:"signals"`
}

type refreshStatusFile struct {
	SchemaVersion int    `json:"schema_version"`
	Status        string `json:"status"`
	StartedAt     string `json:"started_at"`
	FinishedAt    string `json:"finished_at"`
	LastSuccessAt string `json:"last_success_at"`
	Message       string `json:"message"`
	Soak          struct {
		Status           string  `json:"status"`
		StartedAt        string  `json:"started_at"`
		LastObservedAt   string  `json:"last_observed_at"`
		CompletedAt      string  `json:"completed_at"`
		TargetHours      int     `json:"target_hours"`
		IntervalMinutes  int     `json:"interval_minutes"`
		ObservedMinutes  int     `json:"observed_minutes"`
		RemainingMinutes int     `json:"remaining_minutes"`
		SuccessfulRuns   int     `json:"successful_runs"`
		ExpectedRuns     int     `json:"expected_runs"`
		FailedRuns       int     `json:"failed_runs"`
		MissedRuns       int     `json:"missed_runs"`
		InterruptedRuns  int     `json:"interrupted_runs"`
		CoveragePercent  float64 `json:"coverage_percent"`
		ProgressPercent  float64 `json:"progress_percent"`
		LastFailureAt    string  `json:"last_failure_at"`
		LastResetAt      string  `json:"last_reset_at"`
		ResetReason      string  `json:"reset_reason"`
	} `json:"soak"`
	Details struct {
		ProcessedFiles          int   `json:"processed_files"`
		DownloadedFiles         int   `json:"downloaded_files"`
		AlreadyPresentFiles     int   `json:"already_present_files"`
		RetainedRawFiles        int   `json:"retained_raw_files"`
		RetainedRawBytes        int64 `json:"retained_raw_bytes"`
		RawStorageLimitBytes    int64 `json:"raw_storage_limit_bytes"`
		PrunedRawFiles          int   `json:"pruned_raw_files"`
		ArchivedArticles        int   `json:"archived_articles"`
		NewArchivedArticles     int   `json:"new_archived_articles"`
		ArticleArchiveBytes     int64 `json:"article_archive_bytes"`
		TitleBackfillAttempted  int   `json:"title_backfill_attempted_articles"`
		TitleBackfillUpdated    int   `json:"title_backfill_updated_articles"`
		TitleBackfillRemaining  int   `json:"title_backfill_remaining_articles"`
		TitleBackfillDowngraded int   `json:"title_backfill_downgraded_articles"`
	} `json:"details"`
}

type backupStatusFile struct {
	SchemaVersion           int    `json:"schema_version"`
	Status                  string `json:"status"`
	ApplicationDataVerified bool   `json:"application_data_verified"`
	VerifiedAt              string `json:"verified_at"`
	ArchiveBytes            int64  `json:"archive_bytes"`
	ArchiveName             string `json:"archive_name"`
	Checksum                string `json:"checksum"`
}

type soakStatusResponse struct {
	Status           string  `json:"status"`
	StartedAt        string  `json:"started_at"`
	LastObservedAt   string  `json:"last_observed_at"`
	CompletedAt      string  `json:"completed_at"`
	TargetHours      int     `json:"target_hours"`
	IntervalMinutes  int     `json:"interval_minutes"`
	ObservedMinutes  int     `json:"observed_minutes"`
	RemainingMinutes int     `json:"remaining_minutes"`
	SuccessfulRuns   int     `json:"successful_runs"`
	ExpectedRuns     int     `json:"expected_runs"`
	FailedRuns       int     `json:"failed_runs"`
	MissedRuns       int     `json:"missed_runs"`
	InterruptedRuns  int     `json:"interrupted_runs"`
	CurrentStale     bool    `json:"current_stale"`
	CoveragePercent  float64 `json:"coverage_percent"`
	ProgressPercent  float64 `json:"progress_percent"`
	LastFailureAt    string  `json:"last_failure_at"`
	LastResetAt      string  `json:"last_reset_at"`
	ResetReason      string  `json:"reset_reason"`
}

type backupStatusResponse struct {
	Status     string `json:"status"`
	VerifiedAt string `json:"verified_at"`
	AgeHours   int    `json:"age_hours"`
}

type pilotReadinessResponse struct {
	Status                 string   `json:"status"`
	LocalReliabilityPassed bool     `json:"local_reliability_passed"`
	BackupVerified         bool     `json:"backup_verified"`
	Blockers               []string `json:"blockers"`
}

type adminStatusResponse struct {
	Service struct {
		Name   string `json:"name"`
		Status string `json:"status"`
	} `json:"service"`
	Refresh struct {
		Status                  string             `json:"status"`
		Health                  string             `json:"health"`
		StartedAt               string             `json:"started_at"`
		FinishedAt              string             `json:"finished_at"`
		LastSuccessAt           string             `json:"last_success_at"`
		ExpectedNextRefreshAt   string             `json:"expected_next_refresh_at"`
		AgeMinutes              int                `json:"age_minutes"`
		Message                 string             `json:"message"`
		ProcessedFiles          int                `json:"processed_files"`
		DownloadedFiles         int                `json:"downloaded_files"`
		AlreadyPresentFiles     int                `json:"already_present_files"`
		RetainedRawFiles        int                `json:"retained_raw_files"`
		RetainedRawBytes        int64              `json:"retained_raw_bytes"`
		RawStorageLimitBytes    int64              `json:"raw_storage_limit_bytes"`
		PrunedRawFiles          int                `json:"pruned_raw_files"`
		ArchivedArticles        int                `json:"archived_articles"`
		NewArchivedArticles     int                `json:"new_archived_articles"`
		ArticleArchiveBytes     int64              `json:"article_archive_bytes"`
		TitleBackfillAttempted  int                `json:"title_backfill_attempted_articles"`
		TitleBackfillUpdated    int                `json:"title_backfill_updated_articles"`
		TitleBackfillRemaining  int                `json:"title_backfill_remaining_articles"`
		TitleBackfillDowngraded int                `json:"title_backfill_downgraded_articles"`
		Soak                    soakStatusResponse `json:"soak"`
	} `json:"refresh"`
	Backup         backupStatusResponse   `json:"backup"`
	PilotReadiness pilotReadinessResponse `json:"pilot_readiness"`
}

type api struct {
	dataPath          string
	statusPath        string
	backupStatusPath  string
	qualitySamplePath string
	reviews           *reviewStore
	articleReviews    *articleReviewStore
	logger            *log.Logger
	backupVerifyMu    sync.Mutex
	backupVerifyCache backupVerificationCache
	backupHasher      func(string) (string, int64, error)
}

type backupVerificationCache struct {
	archivePath        string
	checksum           string
	archiveBytes       int64
	archiveModifiedAt  time.Time
	archiveMode        os.FileMode
	sidecarModifiedAt  time.Time
	sidecarBytes       int64
	sidecarMode        os.FileMode
	applicationChecked bool
}

func main() {
	cfg := parseFlags()
	logger := log.New(os.Stdout, "crisispulse-api ", log.LstdFlags|log.LUTC)
	server := &http.Server{
		Addr:              cfg.address,
		Handler:           newHandlerWithBackup(cfg.dataPath, cfg.reviewPath, cfg.backupStatusPath, cfg.allowedOrigin, logger),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    64 << 10,
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	errCh := make(chan error, 1)
	go func() {
		logger.Printf("listening on http://%s", cfg.address)
		errCh <- server.ListenAndServe()
	}()

	select {
	case err := <-errCh:
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Fatal(err)
		}
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			logger.Printf("shutdown error: %v", err)
		}
	}
}

func parseFlags() config {
	var cfg config
	flag.StringVar(&cfg.address, "addr", "127.0.0.1:8080", "HTTP listen address")
	flag.StringVar(&cfg.dataPath, "data", defaultDashboardPath(), "dashboard snapshot JSON")
	flag.StringVar(&cfg.reviewPath, "reviews", defaultReviewPath(), "review decision log")
	flag.StringVar(&cfg.backupStatusPath, "backup-status", defaultBackupStatusPath(), "verified backup status JSON")
	flag.StringVar(&cfg.allowedOrigin, "allowed-origin", "http://localhost:3000", "comma-separated allowed dashboard origins")
	flag.Parse()
	return cfg
}

func defaultDashboardPath() string {
	homeRoot, err := os.UserHomeDir()
	if err != nil {
		return "dashboard/data/dashboard.json"
	}
	return filepath.Join(homeRoot, ".crisispulse", "dashboard.json")
}

func defaultReviewPath() string {
	homeRoot, err := os.UserHomeDir()
	if err != nil {
		return "data/review/reviews.jsonl"
	}
	return filepath.Join(homeRoot, ".crisispulse", "reviews.jsonl")
}

func defaultBackupStatusPath() string {
	return filepath.Join(filepath.Dir(defaultDashboardPath()), "backup-status.json")
}

func newHandler(dataPath, reviewPath, allowedOrigin string, logger *log.Logger) http.Handler {
	return newHandlerWithBackup(
		dataPath,
		reviewPath,
		filepath.Join(filepath.Dir(dataPath), "backup-status.json"),
		allowedOrigin,
		logger,
	)
}

func newHandlerWithBackup(dataPath, reviewPath, backupStatusPath, allowedOrigin string, logger *log.Logger) http.Handler {
	service := &api{
		dataPath:          dataPath,
		statusPath:        filepath.Join(filepath.Dir(dataPath), "refresh-status.json"),
		backupStatusPath:  backupStatusPath,
		qualitySamplePath: filepath.Join(filepath.Dir(dataPath), "quality-review-sample.json"),
		reviews:           newReviewStore(reviewPath),
		articleReviews:    newArticleReviewStore(filepath.Join(filepath.Dir(reviewPath), "article-reviews.jsonl")),
		logger:            logger,
		backupHasher:      hashBackupArchive,
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", service.health)
	mux.HandleFunc("/api/v1/health", service.health)
	mux.HandleFunc("/api/v1/admin/status", service.adminStatus)
	mux.HandleFunc("/api/v1/snapshot", service.snapshot)
	mux.HandleFunc("/api/v1/signals", service.signals)
	mux.HandleFunc("/api/v1/reviews", service.reviewDecisions)
	mux.HandleFunc("/api/v1/reviews/summary", service.reviewSummary)
	mux.HandleFunc("/api/v1/reviews/export.csv", service.reviewExport)
	mux.HandleFunc("/api/v1/quality/articles", service.qualityArticles)
	mux.HandleFunc("/api/v1/quality/articles/summary", service.qualityArticleSummary)
	mux.HandleFunc("/api/v1/quality/articles/export.csv", service.qualityArticleExport)
	return withSecurityHeaders(withCORS(mux, allowedOrigin))
}

func (service *api) health(writer http.ResponseWriter, request *http.Request) {
	if !requireGet(writer, request) {
		return
	}
	writeJSON(writer, http.StatusOK, map[string]string{
		"service": "crisispulse-api",
		"status":  "ok",
	})
}

func elapsedMinutes(later, earlier time.Time) int {
	if !later.After(earlier) {
		return 0
	}
	return int(later.Sub(earlier).Minutes())
}

func refreshHealth(status refreshStatusFile, now, lastSuccess time.Time) string {
	if refreshIsStale(status, now, lastSuccess) {
		return "degraded"
	}
	switch status.Status {
	case "success":
		return "healthy"
	case "running":
		startedAt, err := time.Parse(time.RFC3339Nano, status.StartedAt)
		if err == nil && now.Sub(startedAt) <= runningStaleAfter {
			return "healthy"
		}
	}
	return "degraded"
}

func refreshIsStale(status refreshStatusFile, now, lastSuccess time.Time) bool {
	if now.Sub(lastSuccess) > refreshStaleAfter {
		return true
	}
	if status.Status != "running" {
		return false
	}
	startedAt, err := time.Parse(time.RFC3339Nano, status.StartedAt)
	return err != nil || now.Sub(startedAt) > runningStaleAfter
}

func safeRefreshMessage(status string) string {
	switch status {
	case "success":
		return "Refresh completed"
	case "running":
		return "Refresh in progress"
	case "failed":
		return "Refresh failed; check the private service logs"
	default:
		return "Refresh status needs attention"
	}
}

func safeTimestamp(value string) string {
	if value == "" {
		return ""
	}
	if _, err := time.Parse(time.RFC3339Nano, value); err != nil {
		return ""
	}
	return value
}

func safeResetReason(value string) string {
	switch value {
	case "failed_refresh", "interrupted_refresh", "refresh_gap":
		return value
	default:
		return "none"
	}
}

func sanitizeSoakStatus(status refreshStatusFile, currentStale bool, now time.Time) soakStatusResponse {
	response := soakStatusResponse{
		Status:          "not_started",
		TargetHours:     pilotSoakTargetHours,
		IntervalMinutes: pilotSoakInterval,
		FailedRuns:      max(0, status.Soak.FailedRuns),
		MissedRuns:      max(0, status.Soak.MissedRuns),
		InterruptedRuns: max(0, status.Soak.InterruptedRuns),
		CurrentStale:    currentStale,
		LastFailureAt:   safeTimestamp(status.Soak.LastFailureAt),
		LastResetAt:     safeTimestamp(status.Soak.LastResetAt),
		ResetReason:     safeResetReason(status.Soak.ResetReason),
	}
	response.RemainingMinutes = pilotSoakTargetHours * 60
	if status.SchemaVersion != refreshStatusVersion ||
		status.Soak.TargetHours != pilotSoakTargetHours ||
		status.Soak.IntervalMinutes != pilotSoakInterval {
		response.Status = "failed"
		return response
	}

	startedAt, startedErr := time.Parse(time.RFC3339Nano, status.Soak.StartedAt)
	lastObservedAt, observedErr := time.Parse(time.RFC3339Nano, status.Soak.LastObservedAt)
	if status.Soak.Status == "not_started" && status.Soak.StartedAt == "" {
		if response.ResetReason != "none" {
			response.Status = "failed"
		}
		return response
	}
	if startedErr != nil || observedErr != nil || lastObservedAt.Before(startedAt) ||
		startedAt.After(now.Add(statusFutureTolerance)) ||
		lastObservedAt.After(now.Add(statusFutureTolerance)) {
		response.Status = "failed"
		return response
	}

	response.StartedAt = status.Soak.StartedAt
	response.LastObservedAt = status.Soak.LastObservedAt
	response.ObservedMinutes = elapsedMinutes(lastObservedAt, startedAt)
	response.RemainingMinutes = max(0, pilotSoakTargetHours*60-response.ObservedMinutes)
	response.ExpectedRuns = response.ObservedMinutes/pilotSoakInterval + 1
	response.SuccessfulRuns = min(max(0, status.Soak.SuccessfulRuns), response.ExpectedRuns)
	if response.ExpectedRuns > 0 {
		response.CoveragePercent = min(100, float64(response.SuccessfulRuns)*100/float64(response.ExpectedRuns))
	}
	response.ProgressPercent = min(100, float64(response.ObservedMinutes)*100/float64(pilotSoakTargetHours*60))
	response.Status = "in_progress"
	if status.Soak.Status == "passed" && response.RemainingMinutes == 0 && response.CoveragePercent >= pilotSoakCoverage {
		completedAt, completedErr := time.Parse(time.RFC3339Nano, status.Soak.CompletedAt)
		if completedErr != nil || completedAt.Before(startedAt) || completedAt.After(lastObservedAt) ||
			completedAt.After(now.Add(statusFutureTolerance)) {
			response.Status = "failed"
			return response
		}
		response.Status = "passed"
		response.CompletedAt = status.Soak.CompletedAt
	}
	return response
}

func refreshTimestampsValid(status refreshStatusFile, now, lastSuccess time.Time) bool {
	if lastSuccess.After(now.Add(statusFutureTolerance)) {
		return false
	}
	startedAt, startedErr := time.Parse(time.RFC3339Nano, status.StartedAt)
	if startedErr != nil || startedAt.After(now.Add(statusFutureTolerance)) {
		return false
	}
	if status.Status == "running" {
		return status.FinishedAt == ""
	}
	if status.Status != "success" && status.Status != "failed" {
		return false
	}
	finishedAt, finishedErr := time.Parse(time.RFC3339Nano, status.FinishedAt)
	if finishedErr != nil || finishedAt.Before(startedAt) || finishedAt.After(now.Add(statusFutureTolerance)) {
		return false
	}
	if status.Status == "success" && !finishedAt.Equal(lastSuccess) {
		return false
	}
	return true
}

func (service *api) loadBackupStatus(now time.Time) backupStatusResponse {
	response := backupStatusResponse{Status: "not_checked"}
	file, err := os.Open(service.backupStatusPath)
	if errors.Is(err, os.ErrNotExist) {
		return response
	}
	if err != nil {
		service.logger.Printf("backup status unavailable: %v", err)
		response.Status = "failed"
		return response
	}
	defer file.Close()

	raw, err := io.ReadAll(io.LimitReader(file, maxBackupStatusBytes+1))
	if err != nil || len(raw) > maxBackupStatusBytes {
		response.Status = "failed"
		return response
	}
	var status backupStatusFile
	if err := json.Unmarshal(bytes.TrimPrefix(raw, []byte{0xEF, 0xBB, 0xBF}), &status); err != nil {
		service.logger.Printf("invalid backup status: %v", err)
		response.Status = "failed"
		return response
	}
	verifiedAt, err := time.Parse(time.RFC3339Nano, status.VerifiedAt)
	if status.SchemaVersion != backupStatusVersion || status.Status != "verified" ||
		!status.ApplicationDataVerified || err != nil || status.ArchiveBytes <= 0 ||
		verifiedAt.After(now.Add(statusFutureTolerance)) || !validSHA256(status.Checksum) ||
		!service.verifyBackupArchive(status) {
		response.Status = "failed"
		return response
	}
	response.Status = "verified"
	response.VerifiedAt = status.VerifiedAt
	response.AgeHours = max(0, int(now.Sub(verifiedAt).Hours()))
	return response
}

func validBackupArchiveName(value string) bool {
	const layout = "crisispulse-20060102T150405Z.tar.gz"
	if filepath.Base(value) != value || strings.ContainsAny(value, `/\\`) {
		return false
	}
	parsed, err := time.Parse(layout, value)
	return err == nil && parsed.UTC().Format(layout) == value
}

func (service *api) verifyBackupArchive(status backupStatusFile) bool {
	if !validBackupArchiveName(status.ArchiveName) || status.Checksum != strings.ToLower(status.Checksum) {
		return false
	}
	service.backupVerifyMu.Lock()
	defer service.backupVerifyMu.Unlock()
	cached := service.backupVerifyCache
	service.backupVerifyCache = backupVerificationCache{}

	archivePath := filepath.Join(filepath.Dir(service.backupStatusPath), status.ArchiveName)
	archiveInfo, err := os.Lstat(archivePath)
	if err != nil || !archiveInfo.Mode().IsRegular() || archiveInfo.Size() != status.ArchiveBytes {
		return false
	}
	sidecarPath := archivePath + ".sha256"
	sidecarInfo, err := os.Lstat(sidecarPath)
	if err != nil || !sidecarInfo.Mode().IsRegular() || sidecarInfo.Size() > 1024 {
		return false
	}
	sidecar, err := os.Open(sidecarPath)
	if err != nil {
		return false
	}
	sidecarRaw, readErr := io.ReadAll(io.LimitReader(sidecar, 1025))
	closeErr := sidecar.Close()
	expectedSidecar := fmt.Sprintf("%s  %s\n", status.Checksum, status.ArchiveName)
	if readErr != nil || closeErr != nil || string(sidecarRaw) != expectedSidecar {
		return false
	}

	if cached.applicationChecked && cached.archivePath == archivePath &&
		cached.checksum == status.Checksum && cached.archiveBytes == archiveInfo.Size() &&
		cached.archiveModifiedAt.Equal(archiveInfo.ModTime()) && cached.archiveMode == archiveInfo.Mode() &&
		cached.sidecarModifiedAt.Equal(sidecarInfo.ModTime()) && cached.sidecarBytes == sidecarInfo.Size() &&
		cached.sidecarMode == sidecarInfo.Mode() {
		service.backupVerifyCache = cached
		return true
	}
	hasher := service.backupHasher
	if hasher == nil {
		hasher = hashBackupArchive
	}
	checksum, archiveBytes, err := hasher(archivePath)
	if err != nil || archiveBytes != status.ArchiveBytes || checksum != status.Checksum {
		return false
	}
	service.backupVerifyCache = backupVerificationCache{
		archivePath:        archivePath,
		checksum:           status.Checksum,
		archiveBytes:       archiveInfo.Size(),
		archiveModifiedAt:  archiveInfo.ModTime(),
		archiveMode:        archiveInfo.Mode(),
		sidecarModifiedAt:  sidecarInfo.ModTime(),
		sidecarBytes:       sidecarInfo.Size(),
		sidecarMode:        sidecarInfo.Mode(),
		applicationChecked: true,
	}
	return true
}

func hashBackupArchive(path string) (string, int64, error) {
	archive, err := os.Open(path)
	if err != nil {
		return "", 0, err
	}
	defer archive.Close()
	hasher := sha256.New()
	written, err := io.Copy(hasher, archive)
	if err != nil {
		return "", written, err
	}
	return fmt.Sprintf("%x", hasher.Sum(nil)), written, nil
}

func validSHA256(value string) bool {
	if len(value) != 64 {
		return false
	}
	for _, character := range value {
		if (character < '0' || character > '9') &&
			(character < 'a' || character > 'f') &&
			(character < 'A' || character > 'F') {
			return false
		}
	}
	return true
}

func (service *api) adminStatus(writer http.ResponseWriter, request *http.Request) {
	if !requireGet(writer, request) {
		return
	}
	file, err := os.Open(service.statusPath)
	if err != nil {
		service.logger.Printf("refresh status unavailable: %v", err)
		writeError(writer, http.StatusServiceUnavailable, "refresh status unavailable")
		return
	}
	defer file.Close()

	raw, err := io.ReadAll(io.LimitReader(file, maxRefreshStatusBytes+1))
	if err != nil || len(raw) > maxRefreshStatusBytes {
		writeError(writer, http.StatusServiceUnavailable, "refresh status unavailable")
		return
	}
	raw = bytes.TrimPrefix(raw, []byte{0xEF, 0xBB, 0xBF})
	var status refreshStatusFile
	if err := json.Unmarshal(raw, &status); err != nil {
		service.logger.Printf("invalid refresh status: %v", err)
		writeError(writer, http.StatusServiceUnavailable, "refresh status unavailable")
		return
	}
	lastSuccess, err := time.Parse(time.RFC3339Nano, status.LastSuccessAt)
	if err != nil {
		writeError(writer, http.StatusServiceUnavailable, "refresh status unavailable")
		return
	}
	now := time.Now().UTC()
	if !refreshTimestampsValid(status, now, lastSuccess) {
		writeError(writer, http.StatusServiceUnavailable, "refresh status unavailable")
		return
	}
	ageMinutes := elapsedMinutes(now, lastSuccess)
	health := refreshHealth(status, now, lastSuccess)
	currentStale := refreshIsStale(status, now, lastSuccess)
	soak := sanitizeSoakStatus(status, currentStale, now)
	backup := service.loadBackupStatus(now)
	refreshEvidenceCurrent := status.Status == "success" || status.Status == "running"
	soakLastObserved, soakObservedErr := time.Parse(time.RFC3339Nano, soak.LastObservedAt)
	soakEvidenceMatchesRefresh := soakObservedErr == nil && soakLastObserved.Equal(lastSuccess)
	localReliabilityPassed := refreshEvidenceCurrent && health == "healthy" && soak.Status == "passed" &&
		soakEvidenceMatchesRefresh && !currentStale
	backupVerified := backup.Status == "verified" && backup.AgeHours < int(backupStaleAfter.Hours())
	blockers := make([]string, 0, 2)
	if !localReliabilityPassed {
		switch {
		case currentStale:
			blockers = append(blockers, "refresh_stale")
		case health != "healthy" || !refreshEvidenceCurrent:
			blockers = append(blockers, "refresh_unhealthy")
		case soak.Status == "passed" && !soakEvidenceMatchesRefresh:
			blockers = append(blockers, "soak_evidence_mismatch")
		case soak.Status == "not_started":
			blockers = append(blockers, "soak_not_started")
		case soak.Status == "failed":
			blockers = append(blockers, "soak_failed")
		case soak.RemainingMinutes == 0 && soak.CoveragePercent < pilotSoakCoverage:
			blockers = append(blockers, "coverage_below_target")
		default:
			blockers = append(blockers, "soak_in_progress")
		}
	}
	if !backupVerified {
		switch {
		case backup.Status == "failed":
			blockers = append(blockers, "backup_failed")
		case backup.Status == "verified":
			blockers = append(blockers, "backup_too_old")
		default:
			blockers = append(blockers, "backup_not_verified")
		}
	}

	var response adminStatusResponse
	response.Service.Name = "crisispulse-api"
	response.Service.Status = "ok"
	response.Refresh.Status = status.Status
	response.Refresh.Health = health
	response.Refresh.StartedAt = status.StartedAt
	response.Refresh.FinishedAt = status.FinishedAt
	response.Refresh.LastSuccessAt = status.LastSuccessAt
	response.Refresh.ExpectedNextRefreshAt = lastSuccess.Add(15 * time.Minute).Format(time.RFC3339)
	response.Refresh.AgeMinutes = ageMinutes
	response.Refresh.Message = safeRefreshMessage(status.Status)
	response.Refresh.ProcessedFiles = max(0, status.Details.ProcessedFiles)
	response.Refresh.DownloadedFiles = max(0, status.Details.DownloadedFiles)
	response.Refresh.AlreadyPresentFiles = max(0, status.Details.AlreadyPresentFiles)
	response.Refresh.RetainedRawFiles = max(0, status.Details.RetainedRawFiles)
	response.Refresh.RetainedRawBytes = max(int64(0), status.Details.RetainedRawBytes)
	response.Refresh.RawStorageLimitBytes = max(int64(0), status.Details.RawStorageLimitBytes)
	response.Refresh.PrunedRawFiles = max(0, status.Details.PrunedRawFiles)
	response.Refresh.ArchivedArticles = max(0, status.Details.ArchivedArticles)
	response.Refresh.NewArchivedArticles = max(0, status.Details.NewArchivedArticles)
	response.Refresh.ArticleArchiveBytes = max(int64(0), status.Details.ArticleArchiveBytes)
	response.Refresh.TitleBackfillAttempted = max(0, status.Details.TitleBackfillAttempted)
	response.Refresh.TitleBackfillUpdated = max(0, status.Details.TitleBackfillUpdated)
	response.Refresh.TitleBackfillRemaining = max(0, status.Details.TitleBackfillRemaining)
	response.Refresh.TitleBackfillDowngraded = max(0, status.Details.TitleBackfillDowngraded)
	response.Refresh.Soak = soak
	response.Backup = backup
	response.PilotReadiness.LocalReliabilityPassed = localReliabilityPassed
	response.PilotReadiness.BackupVerified = backupVerified
	response.PilotReadiness.Blockers = blockers
	response.PilotReadiness.Status = "not_ready"
	if len(blockers) == 0 {
		response.PilotReadiness.Status = "ready_for_pilot_setup"
	}
	writer.Header().Set("Cache-Control", "no-store")
	writeJSON(writer, http.StatusOK, response)
}

func (service *api) snapshot(writer http.ResponseWriter, request *http.Request) {
	if !requireGet(writer, request) {
		return
	}
	raw, _, err := service.loadDashboard()
	if err != nil {
		service.logger.Printf("snapshot unavailable: %v", err)
		writeError(writer, http.StatusServiceUnavailable, "dashboard data unavailable")
		return
	}
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(http.StatusOK)
	_, _ = writer.Write(raw)
}

func (service *api) signals(writer http.ResponseWriter, request *http.Request) {
	if !requireGet(writer, request) {
		return
	}
	_, dashboard, err := service.loadDashboard()
	if err != nil {
		service.logger.Printf("signals unavailable: %v", err)
		writeError(writer, http.StatusServiceUnavailable, "dashboard data unavailable")
		return
	}
	writer.Header().Set("Cache-Control", "no-store")
	writeJSON(writer, http.StatusOK, signalsResponse{
		UpdatedLabel:       dashboard.Snapshot.UpdatedLabel,
		CandidateAnomalies: dashboard.Snapshot.Candidates,
		Signals:            dashboard.Signals,
	})
}

func (service *api) loadDashboard() ([]byte, dashboardData, error) {
	file, err := os.Open(service.dataPath)
	if err != nil {
		return nil, dashboardData{}, err
	}
	defer file.Close()

	info, err := file.Stat()
	if err != nil {
		return nil, dashboardData{}, err
	}
	if info.Size() > maxDashboardBytes {
		return nil, dashboardData{}, fmt.Errorf("snapshot exceeds %d bytes", maxDashboardBytes)
	}

	raw, err := io.ReadAll(io.LimitReader(file, maxDashboardBytes+1))
	if err != nil {
		return nil, dashboardData{}, err
	}
	if len(raw) > maxDashboardBytes {
		return nil, dashboardData{}, fmt.Errorf("snapshot exceeds %d bytes", maxDashboardBytes)
	}

	var dashboard dashboardData
	if err := json.Unmarshal(raw, &dashboard); err != nil {
		return nil, dashboardData{}, fmt.Errorf("invalid snapshot JSON: %w", err)
	}
	if dashboard.Snapshot.UpdatedLabel == "" || dashboard.Signals == nil {
		return nil, dashboardData{}, errors.New("snapshot is missing required fields")
	}
	return raw, dashboard, nil
}

func requireGet(writer http.ResponseWriter, request *http.Request) bool {
	if request.Method == http.MethodGet || request.Method == http.MethodHead {
		return true
	}
	writer.Header().Set("Allow", "GET, HEAD")
	writeError(writer, http.StatusMethodNotAllowed, "method not allowed")
	return false
}

func withCORS(next http.Handler, configuredOrigins string) http.Handler {
	allowedOrigins := make(map[string]struct{})
	for _, configuredOrigin := range strings.Split(configuredOrigins, ",") {
		if origin := strings.TrimSpace(configuredOrigin); origin != "" {
			allowedOrigins[origin] = struct{}{}
		}
	}
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		origin := request.Header.Get("Origin")
		if origin != "" {
			if _, allowed := allowedOrigins[origin]; !allowed {
				writeError(writer, http.StatusForbidden, "origin not allowed")
				return
			}
			writer.Header().Set("Access-Control-Allow-Origin", origin)
			writer.Header().Set("Vary", "Origin")
		}
		if request.Method == http.MethodOptions {
			writer.Header().Set("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
			writer.Header().Set("Access-Control-Allow-Headers", "Content-Type")
			writer.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(writer, request)
	})
}

func withSecurityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Cross-Origin-Resource-Policy", "same-origin")
		writer.Header().Set("Referrer-Policy", "no-referrer")
		writer.Header().Set("X-Content-Type-Options", "nosniff")
		writer.Header().Set("X-Frame-Options", "DENY")
		next.ServeHTTP(writer, request)
	})
}

func writeError(writer http.ResponseWriter, status int, message string) {
	writeJSON(writer, status, map[string]string{"error": message})
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(value)
}
