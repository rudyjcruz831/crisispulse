package main

import (
	"context"
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
	"syscall"
	"time"
)

const maxDashboardBytes = 2 << 20

type config struct {
	address       string
	dataPath      string
	reviewPath    string
	allowedOrigin string
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

type api struct {
	dataPath string
	reviews  *reviewStore
	logger   *log.Logger
}

func main() {
	cfg := parseFlags()
	logger := log.New(os.Stdout, "crisispulse-api ", log.LstdFlags|log.LUTC)
	server := &http.Server{
		Addr:              cfg.address,
		Handler:           newHandler(cfg.dataPath, cfg.reviewPath, cfg.allowedOrigin, logger),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       60 * time.Second,
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
	flag.StringVar(&cfg.allowedOrigin, "allowed-origin", "http://localhost:3000", "allowed dashboard origin")
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

func newHandler(dataPath, reviewPath, allowedOrigin string, logger *log.Logger) http.Handler {
	service := &api{
		dataPath: dataPath,
		reviews:  newReviewStore(reviewPath),
		logger:   logger,
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", service.health)
	mux.HandleFunc("/api/v1/snapshot", service.snapshot)
	mux.HandleFunc("/api/v1/signals", service.signals)
	mux.HandleFunc("/api/v1/reviews", service.reviewDecisions)
	return withCORS(mux, allowedOrigin)
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

func withCORS(next http.Handler, allowedOrigin string) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		origin := request.Header.Get("Origin")
		if origin != "" && origin != allowedOrigin {
			writeError(writer, http.StatusForbidden, "origin not allowed")
			return
		}
		if origin != "" {
			writer.Header().Set("Access-Control-Allow-Origin", allowedOrigin)
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

func writeError(writer http.ResponseWriter, status int, message string) {
	writeJSON(writer, status, map[string]string{"error": message})
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(value)
}
