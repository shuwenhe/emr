package handler

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"report-file-service/model"
	"report-file-service/service"
)

func (h *Handler) DeletePatient(c *gin.Context) {
	rid, _ := c.Get("request_id")
	patientID := c.Param("patient_id")
	if patientID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_patient_id"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] DeletePatient", "req_id", rid, "patient_id", patientID)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	deleted, err := h.platformSvc.DeletePatient(patientID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "delete_patient_failed"})
		return
	}
	if !deleted {
		c.JSON(http.StatusNotFound, gin.H{"detail": "patient_not_found"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "patient_deleted", "patient_id": patientID})
}

func (h *Handler) BatchDeletePatients(c *gin.Context) {
	rid, _ := c.Get("request_id")
	var req model.PatientDeleteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_json"})
		return
	}
	if len(req.PatientIDs) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "patient_ids_required"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] BatchDeletePatients", "req_id", rid, "count", len(req.PatientIDs))
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	results, err := h.platformSvc.BatchDeletePatients(req.PatientIDs)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "batch_delete_failed"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"results": results})
}

func (h *Handler) RegisterPatient(c *gin.Context) {
	rid, _ := c.Get("request_id")
	var payload map[string]any
	if err := c.ShouldBindJSON(&payload); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_json"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] RegisterPatient", "req_id", rid)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.RegisterPatient(payload)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "register_patient_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}

func (h *Handler) ListPatients(c *gin.Context) {
	rid, _ := c.Get("request_id")
	pageRaw := c.DefaultQuery("page", "1")
	limitRaw := c.DefaultQuery("limit", "20")
	includeArchived := c.DefaultQuery("include_archived", "false") == "true"

	page, err := strconv.Atoi(pageRaw)
	if err != nil || page <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_page"})
		return
	}
	limit, err := strconv.Atoi(limitRaw)
	if err != nil || limit <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_limit"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] ListPatients",
		"req_id", rid,
		"page", page,
		"limit", limit,
		"include_archived", includeArchived,
	)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.ListPatients(page, limit, includeArchived)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "list_patients_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}

func (h *Handler) GetPatient(c *gin.Context) {
	rid, _ := c.Get("request_id")
	patientID := c.Param("patient_id")
	if patientID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_patient_id"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] GetPatient", "req_id", rid, "patient_id", patientID)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.GetPatient(patientID)
	if err != nil {
		if err == service.ErrPatientNotFound {
			c.JSON(http.StatusNotFound, gin.H{"detail": "patient_not_found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "get_patient_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}

func (h *Handler) UpdatePatient(c *gin.Context) {
	rid, _ := c.Get("request_id")
	patientID := c.Param("patient_id")
	if patientID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_patient_id"})
		return
	}

	var updates map[string]any
	if err := c.ShouldBindJSON(&updates); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_json"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] UpdatePatient", "req_id", rid, "patient_id", patientID)
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.UpdatePatient(patientID, updates)
	if err != nil {
		if err == service.ErrPatientNotFound {
			c.JSON(http.StatusNotFound, gin.H{"detail": "patient_not_found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "update_patient_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}

func (h *Handler) ArchivePatient(c *gin.Context) {
	rid, _ := c.Get("request_id")
	patientID := c.Param("patient_id")
	if patientID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_patient_id"})
		return
	}

	var req model.PatientArchiveRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_json"})
		return
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] ArchivePatient", "req_id", rid, "patient_id", patientID, "archived", req.ArchivedValue())
	if h.platformSvc == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "platform_service_unavailable"})
		return
	}
	out, err := h.platformSvc.ArchivePatient(patientID, req.ArchivedValue())
	if err != nil {
		if err == service.ErrPatientNotFound {
			c.JSON(http.StatusNotFound, gin.H{"detail": "patient_not_found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "archive_patient_failed"})
		return
	}
	c.JSON(http.StatusOK, out)
}
