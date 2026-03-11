package handler

import "github.com/gin-gonic/gin"

func (h *Handler) Healthz(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] Healthz", "req_id", rid)
	c.JSON(200, gin.H{
		"status":      "ok",
		"service":     "report-file-service-gin",
		"reports_dir": h.cfg.ReportsDir,
	})
}
