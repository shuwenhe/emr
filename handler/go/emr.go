package handler

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"report-file-service/model"
	"report-file-service/service"
)

func (h *Handler) GenerateEMR(c *gin.Context) {
	rid, _ := c.Get("request_id")
	var req model.EmrGenerateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_json"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] GenerateEMR", "req_id", rid, "record_id", req.RecordID, "force", req.Force)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.GenerateEMR(req.RecordID, req.Force)
	if err != nil {
		if err == service.ErrRecordNotFound {
			c.JSON(http.StatusNotFound, gin.H{"detail": "record_not_found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "generate_emr_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}

func (h *Handler) GetEMR(c *gin.Context) {
	rid, _ := c.Get("request_id")
	emrID := c.Param("emr_id")
	if emrID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_emr_id"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] GetEMR", "req_id", rid, "emr_id", emrID)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.GetEMR(emrID)
	if err != nil {
		if err == service.ErrEMRNotFound {
			c.JSON(http.StatusNotFound, gin.H{"detail": "emr_not_found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "get_emr_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}

func (h *Handler) ListEMR(c *gin.Context) {
	rid, _ := c.Get("request_id")
	patientID := c.Query("patient_id")
	recordID := c.Query("record_id")
	includeArchived := c.DefaultQuery("include_archived", "false") == "true"
	limitRaw := c.DefaultQuery("limit", "100")

	limit, err := strconv.Atoi(limitRaw)
	if err != nil || limit <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_limit"})
		return
	}
	if limit > 1000 {
		limit = 1000
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] ListEMR",
		"req_id", rid,
		"patient_id", patientID,
		"record_id", recordID,
		"include_archived", includeArchived,
		"limit", limit,
	)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.ListEMRs(patientID, recordID, limit, includeArchived)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "list_emr_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}

func (h *Handler) UpdateEMR(c *gin.Context) {
	rid, _ := c.Get("request_id")
	emrID := c.Param("emr_id")
	if emrID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_emr_id"})
		return
	}

	var req model.EmrUpdateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_json"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] UpdateEMR", "req_id", rid, "emr_id", emrID)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	updates := map[string]any{}
	if req.Diagnosis != nil {
		updates["diagnosis"] = *req.Diagnosis
	}
	if req.DoctorOpinion != nil {
		updates["doctor_opinion"] = *req.DoctorOpinion
	}
	if req.Clinical != nil {
		updates["clinical"] = req.Clinical
	}
	if req.TreatmentPlan != nil {
		updates["treatment_plan"] = req.TreatmentPlan
	}
	if req.Report != nil {
		updates["report"] = req.Report
	}
	out, err := h.platformSvc.UpdateEMR(emrID, updates)
	if err != nil {
		if err == service.ErrEMRNotFound {
			c.JSON(http.StatusNotFound, gin.H{"detail": "emr_not_found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "update_emr_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}

func (h *Handler) ArchiveEMR(c *gin.Context) {
	rid, _ := c.Get("request_id")
	emrID := c.Param("emr_id")
	if emrID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_emr_id"})
		return
	}

	var req model.EmrArchiveRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_json"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] ArchiveEMR", "req_id", rid, "emr_id", emrID, "archived", req.ArchivedValue())
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.ArchiveEMR(emrID, req.ArchivedValue())
	if err != nil {
		if err == service.ErrEMRNotFound {
			c.JSON(http.StatusNotFound, gin.H{"detail": "emr_not_found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "archive_emr_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}
