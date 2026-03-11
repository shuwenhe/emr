package handler

import (
	"encoding/json"
	"log"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"report-file-service/internal/model"
	"report-file-service/internal/service"
)

type Handler struct {
	svc *service.ReportService
}

func NewHandler(svc *service.ReportService) *Handler {
	return &Handler{svc: svc}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/healthz", h.handleHealth)
	mux.HandleFunc("/v1/reports", h.handleListReports)
	mux.HandleFunc("/v1/reports/", h.handleReportRoutes)
}

func (h *Handler) handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("X-Report-Service", "report-file-service")
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (h *Handler) handleListReports(w http.ResponseWriter, r *http.Request) {
	log.Printf("[go-reports] list reports date=%q", r.URL.Query().Get("date"))
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed")
		return
	}

	date := r.URL.Query().Get("date")
	reports, err := h.svc.ListReports(date, false)
	if err != nil {
		log.Printf("list reports error: %v", err)
		writeError(w, http.StatusInternalServerError, "list_reports_failed")
		return
	}
	writeJSON(w, http.StatusOK, reports)
}

func (h *Handler) handleReportRoutes(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/v1/reports/")
	if path == "archive" {
		h.handleArchiveReport(w, r)
		return
	}
	if path == "trash" {
		h.handleListTrashReports(w, r)
		return
	}
	if strings.HasPrefix(path, "trash/") {
		h.handleDownloadReport(w, r, true)
		return
	}
	h.handleDownloadReport(w, r, false)
}

func (h *Handler) handleListTrashReports(w http.ResponseWriter, r *http.Request) {
	log.Printf("[go-reports] list trash reports")
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed")
		return
	}

	reports, err := h.svc.ListReports("", true)
	if err != nil {
		log.Printf("list trash reports error: %v", err)
		writeError(w, http.StatusInternalServerError, "list_reports_failed")
		return
	}
	writeJSON(w, http.StatusOK, reports)
}

func (h *Handler) handleArchiveReport(w http.ResponseWriter, r *http.Request) {
	log.Printf("[go-reports] archive request")
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed")
		return
	}

	var req model.ArchiveRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	if req.Date == "" || req.Filename == "" {
		writeError(w, http.StatusBadRequest, "date_and_filename_required")
		return
	}

	resp, err := h.svc.ArchiveReport(req)
	if err != nil {
		h.writeMappedError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) handleDownloadReport(w http.ResponseWriter, r *http.Request, trash bool) {
	log.Printf("[go-reports] download report path=%q trash=%t", r.URL.Path, trash)
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed")
		return
	}

	path := strings.TrimPrefix(r.URL.Path, "/v1/reports/")
	if trash {
		path = strings.TrimPrefix(path, "trash/")
	}
	parts := strings.SplitN(path, "/", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		writeError(w, http.StatusBadRequest, "invalid_report_path")
		return
	}

	date := parts[0]
	filename := parts[1]

	filePath, err := h.svc.ResolveReportPath(date, filename, trash)
	if err != nil {
		h.writeMappedError(w, err)
		return
	}
	if _, err := filepath.Abs(filePath); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_report_path")
		return
	}
	if _, err := os.Stat(filePath); err != nil {
		if os.IsNotExist(err) {
			writeError(w, http.StatusNotFound, "report_not_found")
			return
		}
		writeError(w, http.StatusInternalServerError, "internal_error")
		return
	}

	inline := r.URL.Query().Get("inline") == "true"
	disposition := "attachment"
	if inline {
		disposition = "inline"
	}

	contentType := mime.TypeByExtension(filepath.Ext(filename))
	if contentType == "" {
		contentType = "application/octet-stream"
	}
	w.Header().Set("X-Report-Service", "report-file-service")
	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Content-Disposition", disposition+`; filename="`+filepath.Base(filename)+`"`)
	http.ServeFile(w, r, filePath)
}

func (h *Handler) writeMappedError(w http.ResponseWriter, err error) {
	switch err.Error() {
	case "report_not_found", "report_not_archived":
		writeError(w, http.StatusNotFound, err.Error())
	case "invalid_report_path":
		writeError(w, http.StatusBadRequest, err.Error())
	case "report_already_exists":
		writeError(w, http.StatusConflict, err.Error())
	default:
		log.Printf("unmapped error: %v", err)
		writeError(w, http.StatusInternalServerError, "internal_error")
	}
}

func writeError(w http.ResponseWriter, code int, detail string) {
	writeJSON(w, code, map[string]string{"detail": detail})
}

func writeJSON(w http.ResponseWriter, code int, payload any) {
	w.Header().Set("X-Report-Service", "report-file-service")
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(payload)
}
