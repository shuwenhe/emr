package handler

import "github.com/gin-gonic/gin"

func (h *Handler) ListReports(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] ListReports", "req_id", rid)
	c.JSON(501, gin.H{"detail": "todo: implement ListReports in Gin"})
}

func (h *Handler) ListTrashReports(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] ListTrashReports", "req_id", rid)
	c.JSON(501, gin.H{"detail": "todo: implement ListTrashReports in Gin"})
}

func (h *Handler) DownloadReport(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] DownloadReport",
		"req_id", rid, "date", c.Param("date"), "filename", c.Param("filename"))
	c.JSON(501, gin.H{"detail": "todo: implement DownloadReport in Gin"})
}

func (h *Handler) DownloadTrashReport(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] DownloadTrashReport",
		"req_id", rid, "date", c.Param("date"), "filename", c.Param("filename"))
	c.JSON(501, gin.H{"detail": "todo: implement DownloadTrashReport in Gin"})
}

func (h *Handler) ArchiveReport(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] ArchiveReport", "req_id", rid)
	c.JSON(501, gin.H{"detail": "todo: implement ArchiveReport in Gin"})
}
