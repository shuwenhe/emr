package handler

import "github.com/gin-gonic/gin"

func (h *Handler) PlatformSummary(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] PlatformSummary", "req_id", rid)
	c.JSON(501, gin.H{"detail": "todo: implement PlatformSummary in Gin"})
}

func (h *Handler) PlatformRecords(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] PlatformRecords",
		"req_id", rid, "patient_id", c.Query("patient_id"), "limit", c.DefaultQuery("limit", "50"))
	c.JSON(501, gin.H{"detail": "todo: implement PlatformRecords in Gin"})
}

func (h *Handler) PlatformEMRs(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] PlatformEMRs",
		"req_id", rid, "patient_id", c.Query("patient_id"))
	c.JSON(501, gin.H{"detail": "todo: implement PlatformEMRs in Gin"})
}
