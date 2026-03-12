package route

import (
	"fmt"
	"log/slog"
	"time"

	"github.com/gin-gonic/gin"

	"report-file-service/config"
	ginhandler "report-file-service/handler"
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
		emr := v1.Group("/emr")
		{
			emr.POST("/generate", h.GenerateEMR)
			emr.GET("", h.ListEMR)
			emr.GET("/:emr_id", h.GetEMR)
			emr.PUT("/:emr_id", h.UpdateEMR)
			emr.POST("/:emr_id/archive", h.ArchiveEMR)
		}

		patients := v1.Group("/patients")
		{
			patients.DELETE("/:patient_id", h.DeletePatient)
			patients.POST("/batch-delete", h.BatchDeletePatients)
			patients.POST("", h.RegisterPatient)
			patients.GET("", h.ListPatients)
			patients.GET("/:patient_id", h.GetPatient)
			patients.PUT("/:patient_id", h.UpdatePatient)
			patients.POST("/:patient_id/archive", h.ArchivePatient)
		}

		reports := v1.Group("/reports")
		{
			reports.GET("", h.ListReports)
			reports.GET("/trash", h.ListTrashReports)
			reports.GET("/preview", h.PreviewReport)
			reports.GET("/proxy-health", h.ReportsProxyHealth)
			reports.GET("/:date/:filename", h.DownloadReport)
			reports.GET("/trash/:date/:filename", h.DownloadTrashReport)
			reports.POST("/archive", h.ArchiveReport)
		}

		platform := v1.Group("/platform")
		{
			platform.GET("/summary", h.PlatformSummary)
			platform.GET("/records", h.PlatformRecords)
			platform.GET("/emrs", h.PlatformEMRs)
			platform.GET("/proxy-health", h.PlatformProxyHealth)
		}

		v1.POST("/import/history", h.ImportHistory)

		v1.POST("/ingest", h.Ingest)
		v1.POST("/device/ingest", h.DeviceIngest)
		v1.POST("/analyze", h.Analyze)
		v1.POST("/dispatch", h.Dispatch)
	}

	return router
}
