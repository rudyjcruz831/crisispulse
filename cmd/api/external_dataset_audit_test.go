package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestEmbeddedExternalDatasetAuditIsValidAndFailClosed(t *testing.T) {
	registry, err := loadExternalDatasetAudit(embeddedExternalDatasetAudit)
	if err != nil {
		t.Fatal(err)
	}
	if registry.SchemaVersion != externalDatasetAuditSchemaVersion || registry.LastChecked != "2026-08-25" {
		t.Fatalf("registry metadata = %+v", registry)
	}
	if len(registry.Datasets) < 2 {
		t.Fatalf("datasets = %+v", registry.Datasets)
	}
	for _, dataset := range registry.Datasets {
		if dataset.LicenseState == "unknown" && (dataset.LicenseTrainingApproved || dataset.TrainingDecision != "blocked") {
			t.Fatalf("unknown license did not block training: %+v", dataset)
		}
	}
}

func TestExternalDatasetAuditEndpointReturnsMachineReadableRegistry(t *testing.T) {
	handler := testQualityHandler(t)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/training/external-datasets", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if response.Header().Get("Cache-Control") != "no-store" || response.Header().Get("Content-Type") != "application/json; charset=utf-8" {
		t.Fatalf("headers = %#v", response.Header())
	}
	var registry externalDatasetAuditRegistry
	if err := json.Unmarshal(response.Body.Bytes(), &registry); err != nil {
		t.Fatal(err)
	}
	byID := make(map[string]externalDatasetAuditEntry, len(registry.Datasets))
	for _, dataset := range registry.Datasets {
		byID[dataset.ID] = dataset
	}
	groundsource, ok := byID["groundsource"]
	if !ok || groundsource.SourceURL == "" || groundsource.DOI == "" || groundsource.AccessState == "" || groundsource.ArticleTextAvailability == "" || groundsource.LabelType == "" || len(groundsource.CompatibilityMapping) == 0 || len(groundsource.Evidence) == 0 || groundsource.LastChecked == "" {
		t.Fatalf("groundsource audit is incomplete: %+v", groundsource)
	}
	if groundsource.LicenseState != "verified_permissive" || !groundsource.LicenseTrainingApproved || groundsource.ArticleTextAvailability != "not_available" || groundsource.TrainingDecision != "not_recommended" {
		t.Fatalf("groundsource audit decision is incorrect: %+v", groundsource)
	}
	bangladesh, ok := byID["bangladesh-flood-news"]
	if !ok || bangladesh.ImportDecision == "" || bangladesh.TrainingDecision != "blocked" || len(bangladesh.CompatibilityMapping) != 2 {
		t.Fatalf("Bangladesh audit is incomplete: %+v", bangladesh)
	}
}

func TestExternalDatasetAuditRejectsUnknownLicenseTrainingApproval(t *testing.T) {
	invalid := strings.Replace(
		string(embeddedExternalDatasetAudit),
		`"license_training_approved": false`,
		`"license_training_approved": true`,
		1,
	)
	if _, err := loadExternalDatasetAudit([]byte(invalid)); err == nil || !strings.Contains(err.Error(), "unknown license cannot be approved") {
		t.Fatalf("error = %v", err)
	}
}

func TestExternalDatasetAuditRejectsWrites(t *testing.T) {
	handler := testQualityHandler(t)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/training/external-datasets", strings.NewReader(`{}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusMethodNotAllowed || response.Header().Get("Allow") != "GET, HEAD" {
		t.Fatalf("status = %d, Allow = %q, body = %s", response.Code, response.Header().Get("Allow"), response.Body.String())
	}
}

func TestExternalDatasetAuditRejectsUnknownFields(t *testing.T) {
	invalid := strings.Replace(string(embeddedExternalDatasetAudit), `"schema_version": 1`, `"schema_version": 1, "training_ready": true`, 1)
	if _, err := loadExternalDatasetAudit([]byte(invalid)); err == nil || !strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("error = %v", err)
	}
}

func TestExternalDatasetAuditRejectsUnrecognizedLicenseState(t *testing.T) {
	invalid := strings.Replace(string(embeddedExternalDatasetAudit), `"license_state": "unknown"`, `"license_state": "probably_open"`, 1)
	if _, err := loadExternalDatasetAudit([]byte(invalid)); err == nil || !strings.Contains(err.Error(), "license_state is not recognized") {
		t.Fatalf("error = %v", err)
	}
}

func TestExternalDatasetAuditRejectsUnknownLicenseUnlessTrainingIsBlocked(t *testing.T) {
	registry, err := loadExternalDatasetAudit(embeddedExternalDatasetAudit)
	if err != nil {
		t.Fatal(err)
	}
	registry.Datasets[1].TrainingDecision = "not_recommended"
	if err := validateExternalDatasetAudit(registry); err == nil || !strings.Contains(err.Error(), "unknown license must block training") {
		t.Fatalf("error = %v", err)
	}
}

func TestExternalDatasetAuditRejectsUnrecognizedDecisionAndMappingCodes(t *testing.T) {
	registry, err := loadExternalDatasetAudit(embeddedExternalDatasetAudit)
	if err != nil {
		t.Fatal(err)
	}
	tests := []struct {
		name    string
		mutate  func(*externalDatasetAuditRegistry)
		message string
	}{
		{
			name: "import decision",
			mutate: func(candidate *externalDatasetAuditRegistry) {
				candidate.Datasets[0].ImportDecision = "download_it"
			},
			message: "import_decision is not recognized",
		},
		{
			name: "CrisisPulse label",
			mutate: func(candidate *externalDatasetAuditRegistry) {
				candidate.Datasets[0].CompatibilityMapping[0].CrisisPulseLabel = "floodish"
			},
			message: "crisispulse_label is not recognized",
		},
		{
			name: "mapping use",
			mutate: func(candidate *externalDatasetAuditRegistry) {
				candidate.Datasets[0].CompatibilityMapping[0].Use = "train_immediately"
			},
			message: "use is not recognized",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			candidate := registry
			candidate.Datasets = append([]externalDatasetAuditEntry(nil), registry.Datasets...)
			candidate.Datasets[0].CompatibilityMapping = append([]externalDatasetCompatibilityMapping(nil), registry.Datasets[0].CompatibilityMapping...)
			test.mutate(&candidate)
			if err := validateExternalDatasetAudit(candidate); err == nil || !strings.Contains(err.Error(), test.message) {
				t.Fatalf("error = %v", err)
			}
		})
	}
}
