package handler

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

// proxyToPython forwards the current request body and Content-Type to the
// Python backend at the given path, transparently relaying the response.
// It handles both JSON and multipart/form-data payloads.
func (h *Handler) proxyToPython(c *gin.Context, method, path string) {
	rid, _ := c.Get("request_id")

	if h.cfg.PythonBackendURL == "" {
		c.JSON(http.StatusNotImplemented, gin.H{"detail": "python_backend_not_configured"})
		return
	}

	body, err := io.ReadAll(c.Request.Body)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid_request_body"})
		return
	}

	targetURL := strings.TrimRight(h.cfg.PythonBackendURL, "/") + path
	if c.Request.URL.RawQuery != "" {
		targetURL += "?" + c.Request.URL.RawQuery
	}

	proxyReq, err := http.NewRequestWithContext(c.Request.Context(), method, targetURL, bytes.NewReader(body))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "proxy_request_failed"})
		return
	}

	// Forward Content-Type intact — critical for multipart boundaries.
	if ct := c.GetHeader("Content-Type"); ct != "" {
		proxyReq.Header.Set("Content-Type", ct)
	}
	if rid != nil {
		proxyReq.Header.Set("X-Request-ID", fmt.Sprintf("%v", rid))
	}

	h.log.InfoContext(c.Request.Context(), "[go-handler] proxy->python", "req_id", rid, "target", targetURL)

	resp, err := http.DefaultClient.Do(proxyReq)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"detail": fmt.Sprintf("python_backend_unavailable: %v", err)})
		return
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"detail": "proxy_response_read_failed"})
		return
	}

	ct := resp.Header.Get("Content-Type")
	if ct == "" {
		ct = "application/json"
	}
	c.Data(resp.StatusCode, ct, respBody)
}

// Ingest proxies multipart file upload + metadata to the Python ingestion pipeline.
// The Python backend handles validation, storage, and triggers the async
// 5-step report generation pipeline (analyze → EMR → AI → treatment plan → dispatch).
//
// POST /v1/ingest  →  multipart/form-data(file, metadata)  →  Python POST /ingest
func (h *Handler) Ingest(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] Ingest", "req_id", rid)
	h.proxyToPython(c, http.MethodPost, "/ingest")
}

// DeviceIngest proxies device-triggered capture ingestion to the Python backend.
// Accepts an optional capture_path; if omitted, processes all pending capture dirs.
//
// POST /v1/device/ingest  →  JSON(capture_path?, move_to_processed?)  →  Python POST /device/ingest
func (h *Handler) DeviceIngest(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] DeviceIngest", "req_id", rid)
	h.proxyToPython(c, http.MethodPost, "/device/ingest")
}

// Analyze proxies thermal image analysis to the Python AI backend.
//
// POST /v1/analyze  →  JSON(record_id)  →  Python POST /analyze
func (h *Handler) Analyze(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] Analyze", "req_id", rid)
	h.proxyToPython(c, http.MethodPost, "/analyze")
}

// Dispatch proxies treatment dispatch to the Python device dispatch backend.
//
// POST /v1/dispatch  →  JSON(record_id)  →  Python POST /dispatch
func (h *Handler) Dispatch(c *gin.Context) {
	rid, _ := c.Get("request_id")
	h.log.InfoContext(c.Request.Context(), "[go-handler] Dispatch", "req_id", rid)
	h.proxyToPython(c, http.MethodPost, "/dispatch")
}
