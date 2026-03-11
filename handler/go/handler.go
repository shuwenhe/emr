package handler

import (
	"log/slog"

	"report-file-service/internal/cache"
	"report-file-service/internal/config"
	"report-file-service/internal/repository"
	"report-file-service/internal/service"
)

type Handler struct {
	cfg config.Config
	log *slog.Logger
	svc *service.ReportService
}

func New(cfg config.Config) *Handler {
	repo, err := repository.NewFSRepository(cfg.ReportsDir)
	if err != nil {
		slog.ErrorContext(nil, "failed to create FSRepository", "error", err)
		// Continue with nil repo, handlers will return 500
	}

	ttlCache := cache.NewTTLCache(cfg.CacheTTL)
	svc := service.NewReportService(repo, ttlCache)

	return &Handler{
		cfg: cfg,
		log: slog.Default().With("component", "go-handler"),
		svc: svc,
	}
}
