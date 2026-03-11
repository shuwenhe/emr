package handler

import "report-file-service/internal/config"

type Handler struct {
	cfg config.Config
}

func New(cfg config.Config) *Handler {
	return &Handler{cfg: cfg}
}
