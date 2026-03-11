package model

// EmrGenerateRequest is the request payload for generating EMR from record.
type EmrGenerateRequest struct {
	RecordID string `json:"record_id" binding:"required"`
	Force    bool   `json:"force"`
}

// EmrUpdateRequest is the partial update payload for EMR.
type EmrUpdateRequest struct {
	Diagnosis     *string         `json:"diagnosis,omitempty"`
	DoctorOpinion *string         `json:"doctor_opinion,omitempty"`
	Clinical      map[string]any  `json:"clinical,omitempty"`
	TreatmentPlan map[string]any  `json:"treatment_plan,omitempty"`
	Report        map[string]any  `json:"report,omitempty"`
}

// EmrArchiveRequest toggles archive status.
type EmrArchiveRequest struct {
	Archived *bool `json:"archived,omitempty"`
}

// ArchivedValue returns true by default when field is omitted.
func (r EmrArchiveRequest) ArchivedValue() bool {
	if r.Archived == nil {
		return true
	}
	return *r.Archived
}
