package handler

import "github.com/gin-gonic/gin"

func (h *Handler) PlatformSummary(c *gin.Context) {
	c.JSON(501, gin.H{"detail": "todo: implement PlatformSummary in Gin"})
}

func (h *Handler) PlatformRecords(c *gin.Context) {
	c.JSON(501, gin.H{"detail": "todo: implement PlatformRecords in Gin"})
}

func (h *Handler) PlatformEMRs(c *gin.Context) {
	c.JSON(501, gin.H{"detail": "todo: implement PlatformEMRs in Gin"})
}
