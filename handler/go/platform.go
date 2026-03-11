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
