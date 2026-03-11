package handler

import (
	"log/slog"

	"report-file-service/cache"
	"report-file-service/config"
	"report-file-service/repository"
	"report-file-service/service"
)

type Handler struct {
	cfg         config.Config
	log         *slog.Logger
	svc         *service.ReportService
	platformSvc *service.PlatformService
}

func New(cfg config.Config) *Handler {
	repo, err := repository.NewFSRepository(cfg.ReportsDir)
	if err != nil {
		slog.ErrorContext(nil, "failed to create FSRepository", "error", err)
		// Continue with nil repo, handlers will return 500
	}

	ttlCache := cache.NewTTLCache(cfg.CacheTTL)
	svc := service.NewReportService(repo, ttlCache)

	var platformSvc *service.PlatformService
	platformRepo, err := repository.NewPlatformRepository(cfg.MySQLConfigPath, cfg.MySQLDSN)
	if err != nil {
		slog.ErrorContext(nil, "failed to create PlatformRepository", "error", err)
	} else {
		platformSvc = service.NewPlatformService(platformRepo)
	}

	return &Handler{
		cfg:         cfg,
		log:         slog.Default().With("component", "go-handler"),
		svc:         svc,
		platformSvc: platformSvc,
	}
}
