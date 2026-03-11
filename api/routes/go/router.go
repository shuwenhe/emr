package ginroutes

import (
	"time"

	"github.com/gin-gonic/gin"

	ginhandler "report-file-service/api/routes/go/handler"
	"report-file-service/internal/config"
)

func NewRouter(cfg config.Config) *gin.Engine {
	router := gin.New()
	router.Use(gin.LoggerWithFormatter(func(param gin.LogFormatterParams) string {
		return param.TimeStamp.Format(time.RFC3339) + " " + param.Method + " " + param.Path + " " + param.Latency.String() + "\n"
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
