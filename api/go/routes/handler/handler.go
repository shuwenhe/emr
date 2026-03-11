package handler

import (
	"log/slog"

	"report-file-service/internal/config"
)

type Handler struct {
	cfg config.Config
	log *slog.Logger
}

func New(cfg config.Config) *Handler {
	return &Handler{
		cfg: cfg,
		log: slog.Default().With("component", "go-handler"),
	}
}
