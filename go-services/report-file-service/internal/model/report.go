package model

type ReportFile struct {
	Date      string `json:"date"`
	Name      string `json:"name"`
	SizeBytes int64  `json:"size_bytes"`
	URL       string `json:"url"`
	UpdatedAt int64  `json:"updated_at"`
}

type ArchiveRequest struct {
	Date     string `json:"date"`
	Filename string `json:"filename"`
	Archived bool   `json:"archived"`
}

type ArchiveResponse struct {
	Status   string `json:"status"`
	Date     string `json:"date"`
	Filename string `json:"filename"`
}
