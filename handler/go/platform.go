package handler

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
)

func (h *Handler) PlatformSummary(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] PlatformSummary", "req_id", rid)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.Summary()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_summary_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}

func (h *Handler) PlatformRecords(c *gin.Context) {
	rid, _ := c.Get("request_id")
	patientID := c.Query("patient_id")
	limitRaw := c.DefaultQuery("limit", "50")
	limit, err := strconv.Atoi(limitRaw)
	if err != nil || limit <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_limit"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] PlatformRecords",
		"req_id", rid, "patient_id", patientID, "limit", limit)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.ListRecords(patientID, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_records_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}

// PlatformProxyHealth reports health status of the Go platform service.
func (h *Handler) PlatformProxyHealth(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] PlatformProxyHealth", "req_id", rid)

	healthy := h.platformSvc != nil
	detail := "ok"
	if !healthy {
		detail = "platform_service_unavailable"
	}

	c.JSON(http.StatusOK, gin.H{
		"enabled":     true,
		"using_proxy": false,
		"healthy":     healthy,
		"detail":      detail,
		"service":     "report-file-service",
	})
}

// ImportHistory proxies the request to the Python backend which performs
// legacy directory ingestion and optional ML analysis.
// Requires RFS_PYTHON_BACKEND_URL to be configured; returns 501 otherwise.
// ImportHistory proxies legacy directory ingestion + optional ML analysis to the Python backend.
// POST /v1/import/history  →  JSON(root_path, analyze?)  →  Python POST /import/history
func (h *Handler) ImportHistory(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] ImportHistory", "req_id", rid)
	h.proxyToPython(c, http.MethodPost, "/import/history")
}

func (h *Handler) PlatformEMRs(c *gin.Context) {
	rid, _ := c.Get("request_id")
	patientID := c.Query("patient_id")
	limitRaw := c.DefaultQuery("limit", "50")
	limit, err := strconv.Atoi(limitRaw)
	if err != nil || limit <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_limit"})
		return
	}
	includeArchived := c.DefaultQuery("include_archived", "false") == "true"

	h.log.InfoContext(c.Request.Context(), "[go-handler] PlatformEMRs",
		"req_id", rid, "patient_id", patientID, "limit", limit, "include_archived", includeArchived)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.ListEMRs(patientID, "", limit, includeArchived)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_emrs_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}
