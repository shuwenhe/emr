package handler

import "github.com/gin-gonic/gin"

func (h *Handler) Healthz(c *gin.Context) {
	c.JSON(200, gin.H{
		"status":      "ok",
		"service":     "report-file-service-gin",
		"reports_dir": h.cfg.ReportsDir,
	})
}
