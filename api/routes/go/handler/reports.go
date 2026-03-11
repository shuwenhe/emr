package handler

import "github.com/gin-gonic/gin"

func (h *Handler) ListReports(c *gin.Context) {
	c.JSON(501, gin.H{"detail": "todo: implement ListReports in Gin"})
}

func (h *Handler) ListTrashReports(c *gin.Context) {
	c.JSON(501, gin.H{"detail": "todo: implement ListTrashReports in Gin"})
}

func (h *Handler) DownloadReport(c *gin.Context) {
	c.JSON(501, gin.H{"detail": "todo: implement DownloadReport in Gin"})
}

func (h *Handler) DownloadTrashReport(c *gin.Context) {
	c.JSON(501, gin.H{"detail": "todo: implement DownloadTrashReport in Gin"})
}

func (h *Handler) ArchiveReport(c *gin.Context) {
	c.JSON(501, gin.H{"detail": "todo: implement ArchiveReport in Gin"})
}
