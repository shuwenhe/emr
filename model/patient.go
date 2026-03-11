package model

// PatientUpsertRequest maps the Python patient upsert payload.
type PatientUpsertRequest struct {
	PatientID        *string        `json:"patient_id,omitempty"`
	Name             *string        `json:"name,omitempty"`
	Gender           *string        `json:"gender,omitempty"`
	Age              *int           `json:"age,omitempty"`
	BirthDate        *string        `json:"birth_date,omitempty"`
	IDCard           *string        `json:"id_card,omitempty"`
	Phone            *string        `json:"phone,omitempty"`
	Address          *string        `json:"address,omitempty"`
	EmergencyContact *string        `json:"emergency_contact,omitempty"`
	EmergencyPhone   *string        `json:"emergency_phone,omitempty"`
	Allergies        *string        `json:"allergies,omitempty"`
	MedicalHistory   *string        `json:"medical_history,omitempty"`
	Department       *string        `json:"department,omitempty"`
	ChiefComplaint   *string        `json:"chief_complaint,omitempty"`
	Extra            map[string]any `json:"extra,omitempty"`
}

// PatientArchiveRequest toggles archive status.
type PatientArchiveRequest struct {
	Archived *bool `json:"archived,omitempty"`
}

// ArchivedValue returns true by default when field is omitted.
func (r PatientArchiveRequest) ArchivedValue() bool {
	if r.Archived == nil {
		return true
	}
	return *r.Archived
}

// PatientDeleteRequest supports batch deletion.
type PatientDeleteRequest struct {
	PatientIDs []string `json:"patient_ids" binding:"required"`
}
