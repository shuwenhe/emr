// go_embedder: concurrent embedding batch worker
//
// Protocol (stdin → stdout, all newline-delimited JSON):
//
//   Input  (one JSON object per line):
//     {"id": <int>, "texts": ["text1", "text2", ...]}
//
//   Output (one JSON object per line, order may differ from input):
//     {"id": <int>, "vectors": [[0.1, ...], ...]}
//     {"id": <int>, "error": "reason string"}
//
// The Python caller writes batches to stdin and reads results from stdout.
// A single blank line signals end-of-input; the worker flushes and exits.
//
// Environment variables:
//   OLLAMA_BASE_URL      default: http://localhost:11434
//   OPENAI_BASE_URL      used when provider=openai-compatible
//   OPENAI_API_KEY
//   EMBED_PROVIDER       ollama | openai-compatible   (default: ollama)
//   EMBED_MODEL          default: bge-m3:latest
//   EMBED_CONCURRENCY    max parallel requests        (default: 8)
//   EMBED_TIMEOUT_SEC    per-request timeout seconds  (default: 120)
//   EMBED_MAX_RETRIES    per-batch retry count        (default: 3)

package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"sync"
	"sync/atomic"
	"time"
)

// ── config ────────────────────────────────────────────────────────────────────

type config struct {
	provider    string
	model       string
	ollamaURL   string
	openaiURL   string
	openaiKey   string
	concurrency int
	timeoutSec  int
	maxRetries  int
	metricsSec  int
	connLog     bool
}

func loadConfig() config {
	c := config{
		provider:    getEnv("EMBED_PROVIDER", "ollama"),
		model:       getEnv("EMBED_MODEL", "bge-m3:latest"),
		ollamaURL:   getEnv("OLLAMA_BASE_URL", "http://localhost:11434"),
		openaiURL:   getEnv("OPENAI_BASE_URL", ""),
		openaiKey:   getEnv("OPENAI_API_KEY", ""),
		concurrency: getEnvInt("EMBED_CONCURRENCY", 8),
		timeoutSec:  getEnvInt("EMBED_TIMEOUT_SEC", 120),
		maxRetries:  getEnvInt("EMBED_MAX_RETRIES", 3),
		metricsSec:  getEnvInt("EMBED_METRICS_SEC", 5),
		connLog:     getEnvBool("EMBED_CONN_LOG", true),
	}
	return c
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getEnvInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return def
}

func getEnvBool(key string, def bool) bool {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	switch v {
	case "1", "true", "TRUE", "True", "yes", "YES", "on", "ON":
		return true
	case "0", "false", "FALSE", "False", "no", "NO", "off", "OFF":
		return false
	default:
		return def
	}
}

// ── I/O types ─────────────────────────────────────────────────────────────────

type inputBatch struct {
	ID    int      `json:"id"`
	Texts []string `json:"texts"`
}

type outputBatch struct {
	ID      int         `json:"id"`
	Vectors [][]float32 `json:"vectors,omitempty"`
	Error   string      `json:"error,omitempty"`
}

type runtimeMetrics struct {
	submittedBatches int64
	completedBatches int64
	failedBatches    int64
	submittedTexts   int64
	completedTexts   int64
	failedTexts      int64
	runningBatches   int64
	totalLatencyNs   int64
	lastLatencyNs    int64
}

type cpuBatchCounters struct {
	start sync.Map // map[int]*int64
	done  sync.Map // map[int]*int64
	err   sync.Map // map[int]*int64
}

func (c *cpuBatchCounters) add(counter *sync.Map, cpu int, delta int64) {
	if cpu < 0 {
		return
	}
	if ptr, ok := counter.Load(cpu); ok {
		atomic.AddInt64(ptr.(*int64), delta)
		return
	}
	initVal := new(int64)
	*initVal = delta
	actual, loaded := counter.LoadOrStore(cpu, initVal)
	if loaded {
		atomic.AddInt64(actual.(*int64), delta)
	}
}

func (c *cpuBatchCounters) addStart(cpu int) {
	c.add(&c.start, cpu, 1)
}

func (c *cpuBatchCounters) addDone(cpu int) {
	c.add(&c.done, cpu, 1)
}

func (c *cpuBatchCounters) addErr(cpu int) {
	c.add(&c.err, cpu, 1)
}

func _snapshotSyncMapInt64(m *sync.Map) map[int]int64 {
	out := map[int]int64{}
	m.Range(func(k, v any) bool {
		cpu, ok1 := k.(int)
		ptr, ok2 := v.(*int64)
		if ok1 && ok2 {
			out[cpu] = atomic.LoadInt64(ptr)
		}
		return true
	})
	return out
}

func (c *cpuBatchCounters) summaryLines() []string {
	starts := _snapshotSyncMapInt64(&c.start)
	dones := _snapshotSyncMapInt64(&c.done)
	errs := _snapshotSyncMapInt64(&c.err)

	cpuSet := map[int]struct{}{}
	for cpu := range starts {
		cpuSet[cpu] = struct{}{}
	}
	for cpu := range dones {
		cpuSet[cpu] = struct{}{}
	}
	for cpu := range errs {
		cpuSet[cpu] = struct{}{}
	}

	cpus := make([]int, 0, len(cpuSet))
	for cpu := range cpuSet {
		cpus = append(cpus, cpu)
	}
	sort.Ints(cpus)

	lines := make([]string, 0, len(cpus))
	for _, cpu := range cpus {
		lines = append(lines,
			fmt.Sprintf("[GO_EMBED_CPU_SUMMARY] cpu=%d start=%d done=%d error=%d",
				cpu, starts[cpu], dones[cpu], errs[cpu]),
		)
	}
	if len(lines) == 0 {
		lines = append(lines, "[GO_EMBED_CPU_SUMMARY] no_cpu_samples")
	}
	return lines
}

func (m *runtimeMetrics) onStart(textCount int) {
	atomic.AddInt64(&m.submittedBatches, 1)
	atomic.AddInt64(&m.submittedTexts, int64(textCount))
	atomic.AddInt64(&m.runningBatches, 1)
}

func (m *runtimeMetrics) onFinish(textCount int, elapsed time.Duration, failed bool) {
	atomic.AddInt64(&m.completedBatches, 1)
	atomic.AddInt64(&m.completedTexts, int64(textCount))
	if failed {
		atomic.AddInt64(&m.failedBatches, 1)
		atomic.AddInt64(&m.failedTexts, int64(textCount))
	}
	atomic.StoreInt64(&m.lastLatencyNs, elapsed.Nanoseconds())
	atomic.AddInt64(&m.totalLatencyNs, elapsed.Nanoseconds())
	atomic.AddInt64(&m.runningBatches, -1)
}

func (m *runtimeMetrics) snapshot() map[string]any {
	submittedBatches := atomic.LoadInt64(&m.submittedBatches)
	completedBatches := atomic.LoadInt64(&m.completedBatches)
	failedBatches := atomic.LoadInt64(&m.failedBatches)
	submittedTexts := atomic.LoadInt64(&m.submittedTexts)
	completedTexts := atomic.LoadInt64(&m.completedTexts)
	failedTexts := atomic.LoadInt64(&m.failedTexts)
	runningBatches := atomic.LoadInt64(&m.runningBatches)
	totalLatencyNs := atomic.LoadInt64(&m.totalLatencyNs)
	lastLatencyNs := atomic.LoadInt64(&m.lastLatencyNs)
	pendingBatches := submittedBatches - completedBatches
	queuedBatches := pendingBatches - runningBatches
	if queuedBatches < 0 {
		queuedBatches = 0
	}
	avgLatencyMs := 0.0
	if completedBatches > 0 {
		avgLatencyMs = float64(totalLatencyNs) / float64(completedBatches) / float64(time.Millisecond)
	}
	errorRatePct := 0.0
	if completedBatches > 0 {
		errorRatePct = float64(failedBatches) * 100.0 / float64(completedBatches)
	}
	textErrorRatePct := 0.0
	if completedTexts > 0 {
		textErrorRatePct = float64(failedTexts) * 100.0 / float64(completedTexts)
	}
	return map[string]any{
		"submitted_batches":    submittedBatches,
		"completed_batches":    completedBatches,
		"failed_batches":       failedBatches,
		"submitted_texts":      submittedTexts,
		"completed_texts":      completedTexts,
		"failed_texts":         failedTexts,
		"running_batches":      runningBatches,
		"pending_batches":      pendingBatches,
		"queued_batches":       queuedBatches,
		"avg_latency_ms":       avgLatencyMs,
		"last_latency_ms":      float64(lastLatencyNs) / float64(time.Millisecond),
		"batch_error_rate_pct": errorRatePct,
		"text_error_rate_pct":  textErrorRatePct,
	}
}

func startMetricsReporter(cfg config, metrics *runtimeMetrics) func() {
	if cfg.metricsSec <= 0 {
		return func() {}
	}
	interval := time.Duration(cfg.metricsSec) * time.Second
	stop := make(chan struct{})
	reporterDone := make(chan struct{})
	go func() {
		defer close(reporterDone)
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				payload, _ := json.Marshal(metrics.snapshot())
				fmt.Fprintf(os.Stderr, "[GO_EMBED_METRIC] provider=%s model=%s concurrency=%d %s\n",
					cfg.provider, cfg.model, cfg.concurrency, string(payload))
			case <-stop:
				payload, _ := json.Marshal(metrics.snapshot())
				fmt.Fprintf(os.Stderr, "[GO_EMBED_SUMMARY] provider=%s model=%s concurrency=%d %s\n",
					cfg.provider, cfg.model, cfg.concurrency, string(payload))
				return
			}
		}
	}()
	return func() {
		close(stop)
		<-reporterDone
	}
}

// ── embedding providers ───────────────────────────────────────────────────────

func embedOllama(ctx context.Context, client *http.Client, cfg config, texts []string) ([][]float32, error) {
	body, _ := json.Marshal(map[string]any{
		"model": cfg.model,
		"input": texts,
	})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		cfg.ollamaURL+"/api/embed", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("ollama status %d: %s", resp.StatusCode, truncate(string(raw), 200))
	}

	var result struct {
		Embeddings [][]float32 `json:"embeddings"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("ollama decode: %w", err)
	}
	return result.Embeddings, nil
}

func embedOpenAI(ctx context.Context, client *http.Client, cfg config, texts []string) ([][]float32, error) {
	baseURL := cfg.openaiURL
	if baseURL == "" {
		baseURL = "https://api.openai.com/v1"
	}
	body, _ := json.Marshal(map[string]any{
		"model": cfg.model,
		"input": texts,
	})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+"/embeddings", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if cfg.openaiKey != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.openaiKey)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("openai status %d: %s", resp.StatusCode, truncate(string(raw), 200))
	}

	var result struct {
		Data []struct {
			Embedding []float32 `json:"embedding"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("openai decode: %w", err)
	}
	vecs := make([][]float32, len(result.Data))
	for i, d := range result.Data {
		vecs[i] = d.Embedding
	}
	return vecs, nil
}

func embedWithRetry(cfg config, client *http.Client, texts []string) ([][]float32, error) {
	var lastErr error
	delay := 500 * time.Millisecond
	for attempt := 0; attempt <= cfg.maxRetries; attempt++ {
		if attempt > 0 {
			time.Sleep(delay)
			delay *= 2
		}
		ctx, cancel := context.WithTimeout(context.Background(),
			time.Duration(cfg.timeoutSec)*time.Second)
		var vecs [][]float32
		var err error
		switch cfg.provider {
		case "openai-compatible":
			vecs, err = embedOpenAI(ctx, client, cfg, texts)
		default:
			vecs, err = embedOllama(ctx, client, cfg, texts)
		}
		cancel()
		if err != nil {
			lastErr = err
			continue
		}
		if err := validateVectors(vecs, len(texts)); err != nil {
			lastErr = err
			continue
		}
		return vecs, nil
	}
	return nil, fmt.Errorf("embedding failed after %d retries: %w", cfg.maxRetries, lastErr)
}

func validateVectors(vecs [][]float32, want int) error {
	if len(vecs) != want {
		return fmt.Errorf("vector count mismatch: got %d want %d", len(vecs), want)
	}
	for i, v := range vecs {
		if len(v) == 0 {
			return fmt.Errorf("empty vector at index %d", i)
		}
		for _, f := range v {
			if math.IsNaN(float64(f)) || math.IsInf(float64(f), 0) {
				return fmt.Errorf("NaN/Inf in vector at index %d", i)
			}
		}
	}
	return nil
}

func currentCPUForTID(tid int) int {
	path := fmt.Sprintf("/proc/self/task/%d/stat", tid)
	raw, err := os.ReadFile(path)
	if err != nil {
		return -1
	}
	line := strings.TrimSpace(string(raw))
	idx := strings.LastIndex(line, ")")
	if idx < 0 || idx+1 >= len(line) {
		return -1
	}
	fields := strings.Fields(strings.TrimSpace(line[idx+1:]))
	// In /proc/[pid]/stat, processor is field 39 (1-based).
	// fields here start from original field 3 (state), so index is 39-3=36.
	if len(fields) <= 36 {
		return -1
	}
	cpu, err := strconv.Atoi(fields[36])
	if err != nil {
		return -1
	}
	return cpu
}

// ── main loop ─────────────────────────────────────────────────────────────────

func main() {
	cfg := loadConfig()
	client := &http.Client{
		Timeout: time.Duration(cfg.timeoutSec+10) * time.Second,
	}
	metrics := &runtimeMetrics{}
	cpuCounters := &cpuBatchCounters{}
	stopMetricsReporter := startMetricsReporter(cfg, metrics)
	defer stopMetricsReporter()
	if cfg.connLog {
		fmt.Fprintf(os.Stderr, "go_embedder start pid=%d concurrency=%d\n", os.Getpid(), cfg.concurrency)
	}

	sem := make(chan struct{}, cfg.concurrency)
	slots := make(chan int, cfg.concurrency)
	for i := 1; i <= cfg.concurrency; i++ {
		slots <- i
	}
	var wg sync.WaitGroup

	out := bufio.NewWriter(os.Stdout)
	var outMu sync.Mutex

	writeLine := func(v any) {
		b, _ := json.Marshal(v)
		outMu.Lock()
		out.Write(b)
		out.WriteByte('\n')
		out.Flush()
		outMu.Unlock()
	}

	scanner := bufio.NewScanner(os.Stdin)
	// allow large lines (up to 16 MB per batch)
	scanner.Buffer(make([]byte, 16*1024*1024), 16*1024*1024)

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(bytes.TrimSpace(line)) == 0 {
			break // empty line = end of input
		}

		var batch inputBatch
		if err := json.Unmarshal(line, &batch); err != nil {
			writeLine(outputBatch{ID: -1, Error: fmt.Sprintf("parse error: %v", err)})
			continue
		}

		wg.Add(1)
		sem <- struct{}{}
		slotID := <-slots
		go func(b inputBatch) {
			defer wg.Done()
			defer func() {
				slots <- slotID
				<-sem
			}()
			metrics.onStart(len(b.Texts))
			startedAt := time.Now()
			if cfg.connLog {
				tid := syscall.Gettid()
				cpu := currentCPUForTID(tid)
				cpuCounters.addStart(cpu)
				fmt.Fprintf(os.Stderr, "go_embedder slot=%d event=start batch_id=%d texts=%d pid=%d tid=%d cpu=%d\n", slotID, b.ID, len(b.Texts), os.Getpid(), tid, cpu)
			}

			vecs, err := embedWithRetry(cfg, client, b.Texts)
			if err != nil {
				metrics.onFinish(len(b.Texts), time.Since(startedAt), true)
				if cfg.connLog {
					tid := syscall.Gettid()
					cpu := currentCPUForTID(tid)
					cpuCounters.addErr(cpu)
					fmt.Fprintf(os.Stderr, "go_embedder slot=%d event=error batch_id=%d elapsed_ms=%.1f pid=%d tid=%d cpu=%d\n", slotID, b.ID, float64(time.Since(startedAt))/float64(time.Millisecond), os.Getpid(), tid, cpu)
				}
				writeLine(outputBatch{ID: b.ID, Error: err.Error()})
				return
			}
			metrics.onFinish(len(b.Texts), time.Since(startedAt), false)
			if cfg.connLog {
				tid := syscall.Gettid()
				cpu := currentCPUForTID(tid)
				cpuCounters.addDone(cpu)
				fmt.Fprintf(os.Stderr, "go_embedder slot=%d event=done batch_id=%d elapsed_ms=%.1f pid=%d tid=%d cpu=%d\n", slotID, b.ID, float64(time.Since(startedAt))/float64(time.Millisecond), os.Getpid(), tid, cpu)
			}
			writeLine(outputBatch{ID: b.ID, Vectors: vecs})
		}(batch)
	}

	wg.Wait()
	if cfg.connLog {
		for _, line := range cpuCounters.summaryLines() {
			fmt.Fprintln(os.Stderr, line)
		}
	}

	if err := scanner.Err(); err != nil {
		fmt.Fprintf(os.Stderr, "stdin read error: %v\n", err)
		os.Exit(1)
	}
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
