package service

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"strconv"
	"strings"
	"time"

	"report-file-service/repository"
)

var (
	ErrPatientNotFound = errors.New("patient_not_found")
	ErrEMRNotFound     = errors.New("emr_not_found")
	ErrRecordNotFound  = errors.New("record_not_found")
)

type PlatformService struct {
	repo *repository.PlatformRepository
}

func NewPlatformService(repo *repository.PlatformRepository) *PlatformService {
	return &PlatformService{repo: repo}
}

func (s *PlatformService) RegisterPatient(payload map[string]any) (map[string]any, error) {
	if _, ok := payload["patient_id"]; !ok || strings.TrimSpace(toString(payload["patient_id"])) == "" {
		payload["patient_id"] = "P" + randomHex(12)
	}
	if payload["age"] == nil {
		if birth := strings.TrimSpace(toString(payload["birth_date"])); birth != "" {
			if t, err := parseISODate(birth); err == nil {
				payload["age"] = time.Now().Year() - t.Year()
			}
		}
	}
	patientID, err := s.repo.UpsertPatient(payload)
	if err != nil {
		return nil, err
	}
	return map[string]any{"patient_id": patientID, "message": "patient_registered_successfully"}, nil
}

func (s *PlatformService) ListPatients(page, limit int, includeArchived bool) ([]map[string]any, error) {
	offset := (page - 1) * limit
	return s.repo.ListPatients(limit, offset, includeArchived)
}

func (s *PlatformService) GetPatient(patientID string) (map[string]any, error) {
	item, ok, err := s.repo.GetPatient(patientID)
	if err != nil {
		return nil, err
	}
	if !ok {
		return nil, ErrPatientNotFound
	}
	return item, nil
}

func (s *PlatformService) UpdatePatient(patientID string, updates map[string]any) (map[string]any, error) {
	current, ok, err := s.repo.GetPatient(patientID)
	if err != nil {
		return nil, err
	}
	if !ok {
		return nil, ErrPatientNotFound
	}
	for k, v := range updates {
		if v != nil {
			current[k] = v
		}
	}
	current["patient_id"] = patientID
	if _, err := s.repo.UpsertPatient(current); err != nil {
		return nil, err
	}
	return s.GetPatient(patientID)
}

func (s *PlatformService) ArchivePatient(patientID string, archived bool) (map[string]any, error) {
	item, ok, err := s.repo.ArchivePatient(patientID, archived)
	if err != nil {
		return nil, err
	}
	if !ok {
		return nil, ErrPatientNotFound
	}
	return item, nil
}

func (s *PlatformService) DeletePatient(patientID string) (bool, error) {
	return s.repo.DeletePatient(patientID)
}

func (s *PlatformService) BatchDeletePatients(patientIDs []string) ([]map[string]any, error) {
	results := make([]map[string]any, 0, len(patientIDs))
	for _, id := range patientIDs {
		deleted, err := s.DeletePatient(id)
		if err != nil {
			return nil, err
		}
		results = append(results, map[string]any{"patient_id": id, "deleted": deleted})
	}
	return results, nil
}

func (s *PlatformService) GenerateEMR(recordID string, force bool) (map[string]any, error) {
	if !force {
		if existing, ok, err := s.repo.GetEMRByRecordID(recordID); err != nil {
			return nil, err
		} else if ok {
			return existing, nil
		}
	}

	recordMeta, ok, err := s.repo.GetRecord(recordID)
	if err != nil {
		return nil, err
	}
	if !ok {
		return nil, ErrRecordNotFound
	}

	report, _, err := s.repo.GetReport(recordID)
	if err != nil {
		return nil, err
	}
	plan, _, err := s.repo.GetPlan(recordID)
	if err != nil {
		return nil, err
	}

	patient := map[string]any{}
	if p, ok := recordMeta["patient"].(map[string]any); ok {
		patient = p
	}
	if pid, ok := recordMeta["patient_id"].(string); ok && pid != "" {
		patient["patient_id"] = pid
	}
	clinical := map[string]any{}
	if c, ok := recordMeta["clinical"].(map[string]any); ok {
		clinical = c
	}

	emr := map[string]any{
		"emr_id":         "EMR-" + randomHex(16),
		"record_id":      recordID,
		"created_at":     time.Now().Format("2006-01-02T15:04:05"),
		"archived":       false,
		"patient":        patient,
		"clinical":       clinical,
		"diagnosis":      report["diagnosis"],
		"doctor_opinion": report["doctor_opinion"],
		"report":         report,
		"treatment_plan": plan,
	}
	if analysis, ok := report["analysis"].(map[string]any); ok {
		if risk := analysis["risk_level"]; risk != nil {
			emr["risk_level"] = risk
		}
		if metrics, ok := analysis["temperature_metrics"].(map[string]any); ok {
			if bodyAvg := analysis["body_avg_temp_c"]; bodyAvg != nil {
				metrics["body_avg_temp_c"] = bodyAvg
			}
			emr["temperature_metrics"] = metrics
		}
	}
	if v := report["thermal_images"]; v != nil {
		emr["thermal_images"] = v
	}
	if v := report["thermal_roi_labeled_image"]; v != nil {
		emr["thermal_roi_labeled_image"] = v
	}
	if v := report["thermal_marked_image"]; v != nil {
		emr["thermal_marked_image"] = v
	}

	if err := s.repo.SaveEMR(emr); err != nil {
		return nil, err
	}
	return emr, nil
}

func (s *PlatformService) GetEMR(emrID string) (map[string]any, error) {
	item, ok, err := s.repo.GetEMRByID(emrID)
	if err != nil {
		return nil, err
	}
	if !ok {
		return nil, ErrEMRNotFound
	}
	return item, nil
}

func (s *PlatformService) ListEMRs(patientID, recordID string, limit int, includeArchived bool) ([]map[string]any, error) {
	return s.repo.ListEMRs(patientID, recordID, limit, includeArchived)
}

func (s *PlatformService) ListRecords(patientID string, limit int) ([]map[string]any, error) {
	return s.repo.ListRecords(patientID, limit)
}

func (s *PlatformService) Summary() (map[string]any, error) {
	return s.repo.Summary()
}

func (s *PlatformService) UpdateEMR(emrID string, updates map[string]any) (map[string]any, error) {
	current, ok, err := s.repo.GetEMRByID(emrID)
	if err != nil {
		return nil, err
	}
	if !ok {
		return nil, ErrEMRNotFound
	}

	for _, key := range []string{"diagnosis", "doctor_opinion", "treatment_plan"} {
		if v, ok := updates[key]; ok && v != nil {
			current[key] = v
			if report, ok := current["report"].(map[string]any); ok && (key == "diagnosis" || key == "doctor_opinion") {
				report[key] = v
				current["report"] = report
			}
		}
	}
	if clinical, ok := updates["clinical"].(map[string]any); ok {
		base := map[string]any{}
		if old, ok := current["clinical"].(map[string]any); ok {
			base = old
		}
		for k, v := range clinical {
			if v != nil {
				base[k] = v
			}
		}
		current["clinical"] = base
	}
	if report, ok := updates["report"].(map[string]any); ok {
		current["report"] = report
	}

	if err := s.repo.SaveEMR(current); err != nil {
		return nil, err
	}
	return current, nil
}

func (s *PlatformService) ArchiveEMR(emrID string, archived bool) (map[string]any, error) {
	current, ok, err := s.repo.GetEMRByID(emrID)
	if err != nil {
		return nil, err
	}
	if !ok {
		return nil, ErrEMRNotFound
	}
	current["archived"] = archived
	if err := s.repo.SaveEMR(current); err != nil {
		return nil, err
	}
	return current, nil
}

func randomHex(n int) string {
	if n <= 0 {
		return ""
	}
	buf := make([]byte, (n+1)/2)
	_, _ = rand.Read(buf)
	out := strings.ToUpper(hex.EncodeToString(buf))
	if len(out) > n {
		return out[:n]
	}
	for len(out) < n {
		out += "0"
	}
	return out
}

func parseISODate(raw string) (time.Time, error) {
	if t, err := time.Parse(time.RFC3339, raw); err == nil {
		return t, nil
	}
	if t, err := time.Parse("2006-01-02", raw); err == nil {
		return t, nil
	}
	if strings.HasSuffix(raw, "Z") {
		if t, err := time.Parse("2006-01-02T15:04:05Z", raw); err == nil {
			return t, nil
		}
	}
	return time.Time{}, errors.New("invalid_date")
}

func toString(v any) string {
	switch x := v.(type) {
	case string:
		return x
	case int:
		return strconv.Itoa(x)
	case int64:
		return strconv.FormatInt(x, 10)
	case float64:
		return strconv.FormatFloat(x, 'f', -1, 64)
	default:
		return ""
	}
}
