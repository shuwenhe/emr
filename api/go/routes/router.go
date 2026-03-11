package ginroutes

import (
	"fmt"
	"log/slog"
	"time"

	"github.com/gin-gonic/gin"

	ginhandler "report-file-service/api/go/routes/handler"
	"report-file-service/internal/config"
)

// requestIDMiddleware propagates or generates a X-Request-ID for log correlation.
func requestIDMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		rid := c.GetHeader("X-Request-ID")
		if rid == "" {
			rid = fmt.Sprintf("%d", time.Now().UnixNano())
		}
		c.Set("request_id", rid)
		c.Header("X-Request-ID", rid)
		c.Next()
	}
}

func NewRouter(cfg config.Config) *gin.Engine {
	slog.Info("[go-router] initialising gin router", "addr", cfg.Addr, "reports_dir", cfg.ReportsDir)

	router := gin.New()
	router.Use(requestIDMiddleware())
	router.Use(gin.LoggerWithFormatter(func(param gin.LogFormatterParams) string {
		rid, _ := param.Keys["request_id"].(string)
		errPart := ""
		if param.ErrorMessage != "" {
			errPart = " err=" + param.ErrorMessage
		}
		return fmt.Sprintf(
			"%s [go-router] req_id=%-20s %3d | %13v | %-15s | %-6s %s%s\n",
			param.TimeStamp.Format(time.RFC3339),
			rid,
			param.StatusCode,
			param.Latency,
			param.ClientIP,
			param.Method,
			param.Path,
			errPart,
		)
	}))
	router.Use(gin.Recovery())

	h := ginhandler.New(cfg)

	router.GET("/healthz", h.Healthz)

	v1 := router.Group("/v1")
	{
		reports := v1.Group("/reports")
		{
			reports.GET("", h.ListReports)
			reports.GET("/trash", h.ListTrashReports)
			reports.GET("/:date/:filename", h.DownloadReport)
			reports.GET("/trash/:date/:filename", h.DownloadTrashReport)
			reports.POST("/archive", h.ArchiveReport)
		}

		platform := v1.Group("/platform")
		{
			platform.GET("/summary", h.PlatformSummary)
			platform.GET("/records", h.PlatformRecords)
			platform.GET("/emrs", h.PlatformEMRs)
		}
	}

	return router
}
