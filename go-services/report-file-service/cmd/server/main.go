package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"report-file-service/internal/cache"
	"report-file-service/internal/config"
	"report-file-service/internal/handler"
	"report-file-service/internal/repository"
	"report-file-service/internal/service"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("load config failed: %v", err)
	}

	repo, err := repository.NewFSRepository(cfg.ReportsDir)
	if err != nil {
		log.Fatalf("init repository failed: %v", err)
	}

	cacheStore := cache.NewTTLCache(cfg.CacheTTL)
	reportService := service.NewReportService(repo, cacheStore)
	reportHandler := handler.NewHandler(reportService)

	mux := http.NewServeMux()
	reportHandler.RegisterRoutes(mux)

	server := &http.Server{
		Addr:              cfg.Addr,
		Handler:           loggingMiddleware(mux),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	go func() {
		log.Printf("report-file-service listening on %s (reports_dir=%s)", cfg.Addr, cfg.ReportsDir)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server failed: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(ctx); err != nil {
		log.Printf("graceful shutdown failed: %v", err)
	}
	log.Println("report-file-service stopped")
}

func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		log.Printf("%s %s %s", r.Method, r.URL.Path, time.Since(start))
	})
}
