package main

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const externalDatasetAuditSchemaVersion = 1

//go:embed data/external-dataset-audit.v1.json
var embeddedExternalDatasetAudit []byte

type externalDatasetAuditPolicy struct {
	UnknownLicenseAction      string   `json:"unknown_license_action"`
	ExternalLabelsGroundTruth bool     `json:"external_labels_are_ground_truth"`
	NativeHoldoutRequired     bool     `json:"native_holdout_required"`
	Notes                     []string `json:"notes"`
}

type externalDatasetCompatibilityMapping struct {
	SourceLabel      string `json:"source_label"`
	CrisisPulseLabel string `json:"crisispulse_label"`
	Use              string `json:"use"`
}

type externalDatasetEvidence struct {
	URL      string `json:"url"`
	Supports string `json:"supports"`
}

type externalDatasetAuditEntry struct {
	ID                      string                                `json:"id"`
	SourceName              string                                `json:"source_name"`
	SourceURL               string                                `json:"source_url"`
	DOI                     string                                `json:"doi"`
	AccessState             string                                `json:"access_state"`
	LicenseState            string                                `json:"license_state"`
	LicenseTrainingApproved bool                                  `json:"license_training_approved"`
	ArticleTextAvailability string                                `json:"article_text_availability"`
	LabelType               string                                `json:"label_type"`
	CompatibilityStatus     string                                `json:"compatibility_status"`
	CompatibilityMapping    []externalDatasetCompatibilityMapping `json:"compatibility_mapping"`
	ImportDecision          string                                `json:"import_decision"`
	TrainingDecision        string                                `json:"training_decision"`
	Evidence                []externalDatasetEvidence             `json:"evidence"`
	Notes                   []string                              `json:"notes"`
	LastChecked             string                                `json:"last_checked"`
}

type externalDatasetAuditRegistry struct {
	SchemaVersion int                         `json:"schema_version"`
	LastChecked   string                      `json:"last_checked"`
	Policy        externalDatasetAuditPolicy  `json:"policy"`
	Datasets      []externalDatasetAuditEntry `json:"datasets"`
}

func loadExternalDatasetAudit(raw []byte) (externalDatasetAuditRegistry, error) {
	var registry externalDatasetAuditRegistry
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&registry); err != nil {
		return registry, fmt.Errorf("decode external dataset audit: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return registry, errors.New("decode external dataset audit: trailing JSON value")
	}
	if err := validateExternalDatasetAudit(registry); err != nil {
		return registry, err
	}
	return registry, nil
}

func validateExternalDatasetAudit(registry externalDatasetAuditRegistry) error {
	if registry.SchemaVersion != externalDatasetAuditSchemaVersion {
		return fmt.Errorf("external dataset audit schema_version must be %d", externalDatasetAuditSchemaVersion)
	}
	if !validAuditDate(registry.LastChecked) {
		return errors.New("external dataset audit last_checked must be an ISO date")
	}
	if registry.Policy.UnknownLicenseAction != "block_training" || registry.Policy.ExternalLabelsGroundTruth || !registry.Policy.NativeHoldoutRequired {
		return errors.New("external dataset audit policy must fail closed and require a native holdout")
	}
	if len(registry.Policy.Notes) == 0 || len(registry.Datasets) == 0 {
		return errors.New("external dataset audit policy notes and datasets are required")
	}

	seenIDs := make(map[string]struct{}, len(registry.Datasets))
	for index, dataset := range registry.Datasets {
		if err := validateExternalDatasetAuditEntry(dataset, registry.LastChecked); err != nil {
			return fmt.Errorf("external dataset audit datasets[%d]: %w", index, err)
		}
		if _, exists := seenIDs[dataset.ID]; exists {
			return fmt.Errorf("external dataset audit datasets[%d]: duplicate id %q", index, dataset.ID)
		}
		seenIDs[dataset.ID] = struct{}{}
	}
	return nil
}

func validateExternalDatasetAuditEntry(dataset externalDatasetAuditEntry, registryChecked string) error {
	for field, value := range map[string]string{
		"id":                        dataset.ID,
		"source_name":               dataset.SourceName,
		"access_state":              dataset.AccessState,
		"license_state":             dataset.LicenseState,
		"article_text_availability": dataset.ArticleTextAvailability,
		"label_type":                dataset.LabelType,
		"compatibility_status":      dataset.CompatibilityStatus,
		"import_decision":           dataset.ImportDecision,
		"training_decision":         dataset.TrainingDecision,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s is required", field)
		}
	}
	if !validAuditURL(dataset.SourceURL) {
		return errors.New("source_url must be an absolute HTTPS URL")
	}
	if !auditValueAllowed(dataset.AccessState,
		"public_download",
		"public_project_page",
		"paper_only_dataset_access_not_verified",
		"publication_only_dataset_access_not_verified",
	) {
		return errors.New("access_state is not recognized")
	}
	if !auditValueAllowed(dataset.LicenseState, "unknown", "verified_permissive", "verified_restricted", "incompatible") {
		return errors.New("license_state is not recognized")
	}
	if !auditValueAllowed(dataset.ArticleTextAvailability, "available", "not_verified", "not_available", "social_posts_only") {
		return errors.New("article_text_availability is not recognized")
	}
	if !auditValueAllowed(dataset.CompatibilityStatus, "direct", "partial", "low", "incompatible") {
		return errors.New("compatibility_status is not recognized")
	}
	if !auditValueAllowed(dataset.ImportDecision,
		"approved_for_event_validation_only",
		"blocked_pending_dataset_access_license_and_text_review",
		"blocked_by_research_only_terms",
		"do_not_import_for_article_classifier_yet",
	) {
		return errors.New("import_decision is not recognized")
	}
	if !auditValueAllowed(dataset.TrainingDecision, "approved", "blocked", "not_recommended") {
		return errors.New("training_decision is not recognized")
	}
	if !validAuditDate(dataset.LastChecked) || dataset.LastChecked != registryChecked {
		return errors.New("last_checked must match the registry ISO date")
	}
	if len(dataset.CompatibilityMapping) == 0 || len(dataset.Evidence) == 0 || len(dataset.Notes) == 0 {
		return errors.New("compatibility_mapping, evidence, and notes are required")
	}
	if dataset.LicenseState == "unknown" && dataset.LicenseTrainingApproved {
		return errors.New("an unknown license cannot be approved for training")
	}
	if dataset.LicenseState == "unknown" && dataset.TrainingDecision != "blocked" {
		return errors.New("an unknown license must block training")
	}
	if dataset.TrainingDecision == "approved" && !dataset.LicenseTrainingApproved {
		return errors.New("training approval requires an approved license")
	}
	if dataset.LicenseTrainingApproved && dataset.LicenseState != "verified_permissive" {
		return errors.New("license training approval requires a verified permissive license")
	}
	if dataset.TrainingDecision == "approved" && (dataset.ArticleTextAvailability != "available" || dataset.CompatibilityStatus == "low" || dataset.CompatibilityStatus == "incompatible") {
		return errors.New("training approval requires available text and compatible labels")
	}
	for index, mapping := range dataset.CompatibilityMapping {
		if strings.TrimSpace(mapping.SourceLabel) == "" || strings.TrimSpace(mapping.CrisisPulseLabel) == "" || strings.TrimSpace(mapping.Use) == "" {
			return fmt.Errorf("compatibility_mapping[%d] is incomplete", index)
		}
		if !auditValueAllowed(mapping.CrisisPulseLabel,
			"reported_flooding",
			"flood_risk_warning",
			"heavy_rain_only",
			"not_flood_related",
			"no_direct_mapping",
		) {
			return fmt.Errorf("compatibility_mapping[%d].crisispulse_label is not recognized", index)
		}
		if !auditValueAllowed(mapping.Use,
			"weak_supervision_or_event_validation",
			"candidate_supervised_label_after_manual_mapping_audit",
			"must_not_be_collapsed_into_one_crisispulse_class",
			"optional_auxiliary_crisis_language_research",
			"optional_auxiliary_multimodal_research",
			"candidate_supervised_label_after_access_and_mapping_audit",
			"requires_manual_relabeling_for_warning_rain_and_unrelated_classes",
			"possible_future_severity_or_urgency_research",
		) {
			return fmt.Errorf("compatibility_mapping[%d].use is not recognized", index)
		}
	}
	for index, evidence := range dataset.Evidence {
		if !validAuditURL(evidence.URL) || strings.TrimSpace(evidence.Supports) == "" {
			return fmt.Errorf("evidence[%d] must have an HTTPS URL and supported claim", index)
		}
	}
	return nil
}

func auditValueAllowed(value string, allowed ...string) bool {
	for _, candidate := range allowed {
		if value == candidate {
			return true
		}
	}
	return false
}

func validAuditDate(value string) bool {
	parsed, err := time.Parse("2006-01-02", value)
	return err == nil && parsed.Format("2006-01-02") == value
}

func validAuditURL(value string) bool {
	parsed, err := url.Parse(value)
	return err == nil && parsed.Scheme == "https" && parsed.Host != "" && parsed.User == nil
}

func (service *api) externalDatasetAudit(writer http.ResponseWriter, request *http.Request) {
	if !requireGet(writer, request) {
		return
	}
	registry, err := loadExternalDatasetAudit(embeddedExternalDatasetAudit)
	if err != nil {
		service.logger.Printf("invalid embedded external dataset audit: %v", err)
		writeError(writer, http.StatusInternalServerError, "external dataset audit unavailable")
		return
	}
	writer.Header().Set("Cache-Control", "no-store")
	writeJSON(writer, http.StatusOK, registry)
}
