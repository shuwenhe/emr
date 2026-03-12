package handler

import (
	"mime"
	"net/http"
	"path/filepath"

	"github.com/gin-gonic/gin"

	"report-file-service/model"
)

// ListReports gets all reports (current) or reports from specific date
func (h *Handler) ListReports(c *gin.Context) {
	rid, _ := c.Get("request_id")
	date := c.Query("date")

	h.log.InfoContext(c.Request.Context(), "[go-handler] ListReports", "req_id", rid, "date", date)

	if h.svc == nil {
		h.log.ErrorContext(c.Request.Context(), "service not initialized")
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "internal_error"})
		return
	}

	reports, err := h.svc.ListReports(date, false)
	if err != nil {
		h.log.ErrorContext(c.Request.Context(), "list reports failed", "error", err, "req_id", rid)
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "list_reports_failed"})
		return
	}

	c.Header("X-Report-Service", "report-file-service")
	c.JSON(http.StatusOK, reports)
}

// ListTrashReports gets all archived (trash) reports
func (h *Handler) ListTrashReports(c *gin.Context) {
	rid, _ := c.Get("request_id")

	h.log.InfoContext(c.Request.Context(), "[go-handler] ListTrashReports", "req_id", rid)

	if h.svc == nil {
		h.log.ErrorContext(c.Request.Context(), "service not initialized")
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "internal_error"})
		return
	}

	reports, err := h.svc.ListReports("", true)
	if err != nil {
		h.log.ErrorContext(c.Request.Context(), "list trash reports failed", "error", err, "req_id", rid)
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "list_reports_failed"})
		return
	}

	c.Header("X-Report-Service", "report-file-service")
	c.JSON(http.StatusOK, reports)
}

// DownloadReport downloads a report file from active reports directory
func (h *Handler) DownloadReport(c *gin.Context) {
	rid, _ := c.Get("request_id")
	date := c.Param("date")
	filename := c.Param("filename")
	inline := c.Query("inline") == "true"

	h.log.InfoContext(c.Request.Context(), "[go-handler] DownloadReport",
		"req_id", rid, "date", date, "filename", filename, "inline", inline)

	if h.svc == nil {
		h.log.ErrorContext(c.Request.Context(), "service not initialized")
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "internal_error"})
		return
	}

	if date == "" || filename == "" {
		h.log.WarnContext(c.Request.Context(), "invalid report path params", "req_id", rid)
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_report_path"})
		return
	}

	filePath, err := h.svc.ResolveReportPath(date, filename, false)
	if err != nil {
		h.log.WarnContext(c.Request.Context(), "resolve report path failed", "error", err, "req_id", rid)
		mapError(c, err, rid)
		return
	}

	disposition := "attachment"
	if inline {
		disposition = "inline"
	}

	contentType := mime.TypeByExtension(filepath.Ext(filename))
	if contentType == "" {
		contentType = "application/octet-stream"
	}

	c.Header("X-Report-Service", "report-file-service")
	c.Header("Content-Type", contentType)
	c.Header("Content-Disposition", disposition+`; filename="`+filepath.Base(filename)+`"`)
	c.File(filePath)
}

// DownloadTrashReport downloads a report file from trash (archived) directory
func (h *Handler) DownloadTrashReport(c *gin.Context) {
	rid, _ := c.Get("request_id")
	date := c.Param("date")
	filename := c.Param("filename")

	h.log.InfoContext(c.Request.Context(), "[go-handler] DownloadTrashReport",
		"req_id", rid, "date", date, "filename", filename)

	if h.svc == nil {
		h.log.ErrorContext(c.Request.Context(), "service not initialized")
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "internal_error"})
		return
	}

	if date == "" || filename == "" {
		h.log.WarnContext(c.Request.Context(), "invalid report path params", "req_id", rid)
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_report_path"})
		return
	}

	filePath, err := h.svc.ResolveReportPath(date, filename, true)
	if err != nil {
		h.log.WarnContext(c.Request.Context(), "resolve trash report path failed", "error", err, "req_id", rid)
		mapError(c, err, rid)
		return
	}

	contentType := mime.TypeByExtension(filepath.Ext(filename))
	if contentType == "" {
		contentType = "application/octet-stream"
	}

	c.Header("X-Report-Service", "report-file-service")
	c.Header("Content-Type", contentType)
	c.Header("Content-Disposition", `inline; filename="`+filepath.Base(filename)+`"`)
	c.File(filePath)
}

// ArchiveReport moves a report between active and trash directories
func (h *Handler) ArchiveReport(c *gin.Context) {
	rid, _ := c.Get("request_id")

	h.log.InfoContext(c.Request.Context(), "[go-handler] ArchiveReport", "req_id", rid)

	if h.svc == nil {
		h.log.ErrorContext(c.Request.Context(), "service not initialized")
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "internal_error"})
		return
	}

	var req model.ArchiveRequest
	if err := c.BindJSON(&req); err != nil {
		h.log.WarnContext(c.Request.Context(), "invalid archive request", "error", err, "req_id", rid)
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_json"})
		return
	}

	if req.Date == "" || req.Filename == "" {
		h.log.WarnContext(c.Request.Context(), "missing date or filename", "req_id", rid)
		c.JSON(http.StatusBadRequest, gin.H{"detail": "date_and_filename_required"})
		return
	}

	resp, err := h.svc.ArchiveReport(req)
	if err != nil {
		h.log.WarnContext(c.Request.Context(), "archive report failed", "error", err, "req_id", rid)
		mapError(c, err, rid)
		return
	}

	c.Header("X-Report-Service", "report-file-service")
	c.JSON(http.StatusOK, resp)
}

// PreviewReport serves a report file inline (for browser preview).
// Query params: date, filename
func (h *Handler) PreviewReport(c *gin.Context) {
	rid, _ := c.Get("request_id")
	date := c.Query("date")
	filename := c.Query("filename")

	h.log.InfoContext(c.Request.Context(), "[go-handler] PreviewReport",
		"req_id", rid, "date", date, "filename", filename)

	if h.svc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "internal_error"})
		return
	}

	if date == "" || filename == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "date_and_filename_required"})
		return
	}

	filePath, err := h.svc.ResolveReportPath(date, filename, false)
	if err != nil {
		h.log.WarnContext(c.Request.Context(), "resolve report path failed", "error", err, "req_id", rid)
		mapError(c, err, rid)
		return
	}

	contentType := mime.TypeByExtension(filepath.Ext(filename))
	if contentType == "" {
		contentType = "application/octet-stream"
	}

	c.Header("X-Report-Service", "report-file-service")
	c.Header("Content-Type", contentType)
	c.Header("Content-Disposition", `inline; filename="`+filepath.Base(filename)+`"`)
	c.File(filePath)
}

// ReportsProxyHealth reports health status of the Go report service.
func (h *Handler) ReportsProxyHealth(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] ReportsProxyHealth", "req_id", rid)

	healthy := h.svc != nil
	detail := "ok"
	if !healthy {
		detail = "report_service_unavailable"
	}

	c.Header("X-Report-Service", "report-file-service")
	c.JSON(http.StatusOK, gin.H{
		"enabled":     true,
		"using_proxy": false,
		"healthy":     healthy,
		"detail":      detail,
		"service":     "report-file-service",
		"reports_dir": h.cfg.ReportsDir,
	})
}

// mapError maps service errors to HTTP status codes and detail strings
func mapError(c *gin.Context, err error, rid interface{}) {
	switch err.Error() {
	case "report_not_found", "report_not_archived":
		c.Header("X-Report-Service", "report-file-service")
		c.JSON(http.StatusNotFound, gin.H{"detail": err.Error()})
	case "invalid_report_path":
		c.Header("X-Report-Service", "report-file-service")
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
	case "report_already_exists":
		c.Header("X-Report-Service", "report-file-service")
		c.JSON(http.StatusConflict, gin.H{"detail": err.Error()})
	default:
		c.Header("X-Report-Service", "report-file-service")
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "internal_error"})
	}
}
