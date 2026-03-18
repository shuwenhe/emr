PYTHON ?= python3.12
VENV_DIR := .venv
VENV_PY := $(VENV_DIR)/bin/python
KB_PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),$(PYTHON))

# For KB/embedding targets that require faiss + langchain, prefer ~/.venv if it
# has those packages; otherwise fall back to KB_PY.
HOME_VENV_PY := $(HOME)/.venv/bin/python
TCM_PY := $(shell \
  if [ -x "$(HOME_VENV_PY)" ] && "$(HOME_VENV_PY)" -c "import faiss" 2>/dev/null; then \
    echo "$(HOME_VENV_PY)"; \
  else \
    echo "$(KB_PY)"; \
  fi)

KB_SOURCE_DIR ?= $(CURDIR)/rag/dataset
KB_OUT_DIR ?= $(CURDIR)/rag/kb
KB_PROVIDER ?= ollama
KB_EMBED_MODEL ?= bge-m3:latest
KB_BASE_URL ?=
KB_API_KEY ?=
KB_MAX_LEN ?= 800
KB_OVERLAP ?= 100
KB_BATCH_SIZE ?= 32
STRUCTURED_KB_JSONL ?= $(CURDIR)/rag/kb/knowledge_base.jsonl
STRUCTURED_KB_OUT_DIR ?= $(CURDIR)/rag/kb/current_partial
KB_DOC_IMPORT_DIR ?= $(CURDIR)/docs/guidelines
KB_DOC_ID_PREFIX ?= KB-DOC
KB_DOC_MAX_CHARS ?= 700
KB_DOC_MIN_CHARS ?= 80
KB_MD_IMPORT_DIR ?= $(CURDIR)/docs
KB_MD_ID_PREFIX ?= KB-MD
KB_MD_MAX_CHARS ?= 700
KB_MD_MIN_CHARS ?= 80
KB_MD_INCLUDE_REGEX ?=
KB_MD_EXCLUDE_REGEX ?=
RAG_USE_GO_EMBEDDER ?= 1
RAG_GO_EMBED_CONCURRENCY ?= 8
RAG_EMBED_METRICS_EVERY ?= 20
RAG_EMBED_PIPELINE_WORKERS ?= 8
RAG_EMBED_PIPELINE_INFLIGHT ?=
RAG_RESOURCE_METRICS_SEC ?= 5
RAG_RESOURCE_LOG_GPU ?= 1
ROI_DIR ?= $(CURDIR)/roi

# TCM corpus pipeline settings
TCM_RAW_JSON  ?= $(CURDIR)/rag/dataset/TCM_pretrain_book_corpus.json
TCM_DOCS_JSONL  ?= $(CURDIR)/rag/dataset/TCM_pretrain_book_docs.jsonl
TCM_CHUNKS_JSONL ?= $(CURDIR)/rag/dataset/TCM_pretrain_book_chunks.jsonl
TCM_PIPELINE_DIR ?= $(CURDIR)/rag/dataset/pipeline_out
TCM_MIN_LEN  ?= 80
TCM_CHUNK_SIZE ?= 600
TCM_WORKERS  ?= 4

TCM_DOCX_DIR  ?= $(CURDIR)/rag/dataset/docx_corpus
TCM_DOCX_RPF  ?= 500   # records per docx file

.PHONY: help install service service-precheck web web-build web-prod db-check report kb-build kb-build-markdown kb-build-structured kb-import-docs kb-import-docs-build kb-import-md kb-import-md-build kb-rebuild kb-clean kb-build-tcm tcm-stage1 tcm-pipeline tcm-docx roi-build roi-benchmark go-embedder-build simhash-build text-ops-build public-domain-up public-domain-down clean

help:
	@echo "Available targets:"
	@echo "  make help             # list available commands"
	@echo "  make install          # install dependencies"
	@echo "  make service          # run backend service"
	@echo "  make web              # run Next.js web app (dev, slow)"
	@echo "  make web-build        # compile Next.js for production (run once)"
	@echo "  make web-prod         # start production Next.js server (fast, use after web-build)"
	@echo "  make public-domain-up DOMAIN=example.com   # deploy fixed domain + Caddy HTTPS"
	@echo "  make public-domain-down                    # stop fixed domain stack"
	@echo "  make db-check         # verify MySQL connectivity and privileges"
	@echo "  make report           # generate docx reports"
	@echo "  make kb-build         # build vector KB from docx files"
	@echo "    env: RAG_USE_GO_EMBEDDER=0/1, RAG_GO_EMBED_CONCURRENCY=8"
	@echo "    env: RAG_RESOURCE_METRICS_SEC=5, RAG_RESOURCE_LOG_GPU=0/1"
	@echo "  make go-embedder-build # compile Go concurrent embedder (speeds up kb-build)"
	@echo "  make simhash-build    # compile C++ SimHash extension (speeds up dedup)" 
	@echo "  make text-ops-build   # compile C++ text ops extension (chunk_text + low-signal)"
	@echo "  make kb-build-markdown # build KB and print markdown/chunk debug"
	@echo "  make kb-build-structured # build vector KB from rag/kb/knowledge_base.jsonl"
	@echo "  make kb-import-docs    # batch import .docx/.pdf into knowledge_base.jsonl (upsert by id)"
	@echo "  make kb-import-docs-build # import docs then rebuild structured vector KB"
	@echo "  make kb-import-md      # batch import .md into knowledge_base.jsonl (upsert by id)"
	@echo "  make kb-import-md-build # import markdown then rebuild structured vector KB"
	@echo "  make kb-rebuild       # alias of kb-build"
	@echo "  make kb-clean         # remove generated KB artifacts"
	@echo "  make tcm-docx         # convert TCM corpus JSON → .docx files (direct path)"
	@echo "  make tcm-stage1       # Stage 1: TCM raw JSON → docs JSONL"
	@echo "  make tcm-pipeline     # Stages 1.5-2: dedup + sweep + chunk (needs TCM_DOCS_JSONL)"
	@echo "  make kb-build-tcm     # Stage 3: embed chunks → FAISS KB  (needs TCM_CHUNKS_JSONL)"
	@echo "  make roi-build        # build ROI C++ library under roi/cpp"
	@echo "  make roi-benchmark    # run ROI Python/C++ benchmark"
	@echo "  make clean            # remove generated files"

install:
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PY) -m pip install -U pip
	$(VENV_PY) -m pip install -r requirements/base.txt
	@bash -c 'cd "$(CURDIR)/web"; if [ -s "$$HOME/.nvm/nvm.sh" ]; then . "$$HOME/.nvm/nvm.sh" && nvm install 20 && nvm use 20; fi; npm install'


service-precheck:
	@bash -c 'set -e; ENABLE_RAW="$${ENABLE_GO_REPORT_PROXY:-}"; if [ -z "$$ENABLE_RAW" ] && [ -f "$(CURDIR)/.env" ]; then ENABLE_RAW="$$(grep -E "^ENABLE_GO_REPORT_PROXY=" "$(CURDIR)/.env" | tail -n1 | cut -d= -f2- | tr -d "\r\"\047" | xargs)"; fi; ENABLE="$$(printf "%s" "$$ENABLE_RAW" | tr "[:upper:]" "[:lower:]")"; if [ "$$ENABLE" = "true" ] || [ "$$ENABLE" = "1" ] || [ "$$ENABLE" = "yes" ] || [ "$$ENABLE" = "on" ]; then GO_URL="$${GO_REPORT_SERVICE_URL:-}"; if [ -z "$$GO_URL" ] && [ -f "$(CURDIR)/.env" ]; then GO_URL="$$(grep -E "^GO_REPORT_SERVICE_URL=" "$(CURDIR)/.env" | tail -n1 | cut -d= -f2- | tr -d "\r\"\047" | xargs)"; fi; if [ -z "$$GO_URL" ]; then GO_URL="http://127.0.0.1:8088"; fi; HEALTH_URL="$${GO_URL%/}/healthz"; if ! command -v curl >/dev/null 2>&1; then echo "[warn] curl 不可用，跳过 Go 服务健康检查: $$HEALTH_URL"; exit 0; fi; if ! curl -fsS "$$HEALTH_URL" >/dev/null 2>&1; then echo "[error] Go 代理开关已开启但 Go 服务未启动: $$HEALTH_URL"; echo "        请先启动 Go 服务（例如: cd reports/go && make run），或关闭 ENABLE_GO_REPORT_PROXY。"; exit 1; fi; echo "[ok] Go report 服务可用: $$HEALTH_URL"; fi'

SERVICE_PORT ?= 8000

service: install service-precheck
	@bash -c 'set -e; PORT="$(SERVICE_PORT)"; if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$PORT" | grep -q LISTEN; then echo "[error] Port $$PORT is already in use."; echo "        Run: make service-stop   (or use: make SERVICE_PORT=8001 service)"; exit 1; fi; exec "$(VENV_PY)" -m uvicorn route.main:app --host 0.0.0.0 --port "$$PORT" --reload'

service-dev: install service-precheck
	@bash -c 'set -e; PORT="$(SERVICE_PORT)"; if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$PORT" | grep -q LISTEN; then echo "[error] Port $$PORT is already in use."; echo "        Run: make service-stop   (or use: make SERVICE_PORT=8001 service-dev)"; exit 1; fi; exec "$(VENV_PY)" -m uvicorn route.main:app --host 0.0.0.0 --port "$$PORT" --reload'

service-stop:
	@bash -c 'set -e; PORT="$(SERVICE_PORT)"; PIDS="$$(fuser -n tcp $$PORT 2>/dev/null || true)"; if [ -n "$$PIDS" ]; then echo "Stopping port $$PORT pids: $$PIDS"; echo "$$PIDS" | xargs -r kill; sleep 1; REMAIN="$$(fuser -n tcp $$PORT 2>/dev/null || true)"; if [ -n "$$REMAIN" ]; then echo "Force stopping port $$PORT pids: $$REMAIN"; echo "$$REMAIN" | xargs -r kill -9; fi; fi; if command -v ss >/dev/null 2>&1; then ss -ltnp | grep ":$$PORT" || true; fi'

service-restart: service-stop service

service-prod: install service-precheck
	@bash -c 'set -e; PORT="$(SERVICE_PORT)"; if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$PORT" | grep -q LISTEN; then echo "[error] Port $$PORT is already in use."; echo "        Run: make service-stop   (or use: make SERVICE_PORT=8001 service-prod)"; exit 1; fi; exec "$(VENV_PY)" -m uvicorn route.main:app --host 0.0.0.0 --port "$$PORT"'

web:
	@bash -c 'set -e; WEB_DIR="$(CURDIR)/web"; LOCK_FILE="$$WEB_DIR/.next/dev/lock"; if [ -f "$$LOCK_FILE" ]; then echo "Removing stale lock: $$LOCK_FILE"; rm -f "$$LOCK_FILE"; fi; cd "$$WEB_DIR"; if [ -s "$$HOME/.nvm/nvm.sh" ]; then . "$$HOME/.nvm/nvm.sh" && nvm use 20; fi; npm run dev'

web-build:
	@bash -c 'set -e; cd "$(CURDIR)/web"; if [ -s "$$HOME/.nvm/nvm.sh" ]; then . "$$HOME/.nvm/nvm.sh" && nvm use 20; fi; npm run build'

web-prod:
	@bash -c 'set -e; cd "$(CURDIR)/web"; if [ -s "$$HOME/.nvm/nvm.sh" ]; then . "$$HOME/.nvm/nvm.sh" && nvm use 20; fi; npm run start'

DOMAIN ?=

public-domain-up:
	@bash -c 'set -e; if [ -z "$(DOMAIN)" ]; then echo "[ERROR] DOMAIN is required. Example: make public-domain-up DOMAIN=clinic.example.com"; exit 1; fi; bash "$(CURDIR)/scripts/deployment/deploy_public_domain.sh" "$(DOMAIN)"'

public-domain-down:
	@bash "$(CURDIR)/scripts/deployment/stop_public_domain.sh"

db-check:
	$(VENV_PY) scripts/db_check.py

report: install
	$(VENV_PY) -m pip install -q python-docx
	$(VENV_PY) scripts/generate_reports.py --name "张三" --datasets normal_face fever_face hand_normal low_temp

go-embedder-build:
	@echo "Building Go concurrent embedder..."
	@echo "构建 Go 并发 Embedder 二进制..."
	cd "$(CURDIR)/rag" && rm -rf go_embedder && go build -o go_embedder embedder.go
	@echo "Built: rag/go_embedder"

simhash-build:
	@echo "Building C++ SimHash extension..."
	@echo "构建 C++ SimHash 扩展..."
	@if [ -f "$(CURDIR)/rag/build_simhash.sh" ]; then \
		VENV_PY="$(KB_PY)" bash "$(CURDIR)/rag/build_simhash.sh"; \
	else \
		VENV_PY="$(KB_PY)" bash "$(CURDIR)/rag/simhash/build.sh"; \
	fi
	@echo "Done: rag/so/_simhash*.so"

text-ops-build:
	@echo "Building C++ text ops extension..."
	@echo "构建 C++ 文本处理扩展..."
	@VENV_PY="$(KB_PY)" bash "$(CURDIR)/rag/build_text_ops.sh"
	@echo "Done: rag/so/_text_ops*.so"

kb-build: go-embedder-build
	@mkdir -p "$(KB_OUT_DIR)"
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	RAG_USE_GO_EMBEDDER="$(RAG_USE_GO_EMBEDDER)" \
	RAG_GO_EMBED_CONCURRENCY="$(RAG_GO_EMBED_CONCURRENCY)" \
	RAG_EMBED_METRICS_EVERY="$(RAG_EMBED_METRICS_EVERY)" \
	RAG_EMBED_PIPELINE_WORKERS="$(RAG_EMBED_PIPELINE_WORKERS)" \
	RAG_RESOURCE_METRICS_SEC="$(RAG_RESOURCE_METRICS_SEC)" \
	RAG_RESOURCE_LOG_GPU="$(RAG_RESOURCE_LOG_GPU)" \
	$(if $(RAG_EMBED_PIPELINE_INFLIGHT),RAG_EMBED_PIPELINE_INFLIGHT="$(RAG_EMBED_PIPELINE_INFLIGHT)",) \
	"$(KB_PY)" -c "from rag.kb_builder import build_kb; build_kb(source_dir='$(KB_SOURCE_DIR)', out_dir='$(KB_OUT_DIR)', provider='$(KB_PROVIDER)', embed_model='$(KB_EMBED_MODEL)', base_url='$(KB_BASE_URL)' or None, api_key='$(KB_API_KEY)' or None, max_len=int('$(KB_MAX_LEN)'), overlap=int('$(KB_OVERLAP)'), batch_size=int('$(KB_BATCH_SIZE)'), show_markdown=False)"

kb-build-markdown:
	@mkdir -p "$(KB_OUT_DIR)"
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	RAG_USE_GO_EMBEDDER="$(RAG_USE_GO_EMBEDDER)" \
	RAG_GO_EMBED_CONCURRENCY="$(RAG_GO_EMBED_CONCURRENCY)" \
	RAG_EMBED_METRICS_EVERY="$(RAG_EMBED_METRICS_EVERY)" \
	RAG_EMBED_PIPELINE_WORKERS="$(RAG_EMBED_PIPELINE_WORKERS)" \
	RAG_RESOURCE_METRICS_SEC="$(RAG_RESOURCE_METRICS_SEC)" \
	RAG_RESOURCE_LOG_GPU="$(RAG_RESOURCE_LOG_GPU)" \
	$(if $(RAG_EMBED_PIPELINE_INFLIGHT),RAG_EMBED_PIPELINE_INFLIGHT="$(RAG_EMBED_PIPELINE_INFLIGHT)",) \
	"$(KB_PY)" -c "from rag.kb_builder import build_kb; build_kb(source_dir='$(KB_SOURCE_DIR)', out_dir='$(KB_OUT_DIR)', provider='$(KB_PROVIDER)', embed_model='$(KB_EMBED_MODEL)', base_url='$(KB_BASE_URL)' or None, api_key='$(KB_API_KEY)' or None, max_len=int('$(KB_MAX_LEN)'), overlap=int('$(KB_OVERLAP)'), batch_size=int('$(KB_BATCH_SIZE)'), show_markdown=True)"

kb-build-structured:
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	"$(KB_PY)" -m rag.build_kb_from_structured \
		--kb "$(STRUCTURED_KB_JSONL)" \
		--out "$(STRUCTURED_KB_OUT_DIR)" \
		--provider "$(KB_PROVIDER)" \
		--model "$(KB_EMBED_MODEL)" \
		$(if $(KB_BASE_URL),--base-url "$(KB_BASE_URL)",)

kb-import-docs:
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	"$(KB_PY)" scripts/build_kb_from_docs.py \
		--input-dir "$(KB_DOC_IMPORT_DIR)" \
		--output-file "$(STRUCTURED_KB_JSONL)" \
		--id-prefix "$(KB_DOC_ID_PREFIX)" \
		--max-chars $(KB_DOC_MAX_CHARS) \
		--min-chars $(KB_DOC_MIN_CHARS) \
		--upsert

kb-import-docs-build: kb-import-docs kb-build-structured

kb-import-md:
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	"$(KB_PY)" scripts/build_kb_from_md.py \
		--input-dir "$(KB_MD_IMPORT_DIR)" \
		--output-file "$(STRUCTURED_KB_JSONL)" \
		--id-prefix "$(KB_MD_ID_PREFIX)" \
		--max-chars $(KB_MD_MAX_CHARS) \
		--min-chars $(KB_MD_MIN_CHARS) \
		$(if $(KB_MD_INCLUDE_REGEX),--include-regex "$(KB_MD_INCLUDE_REGEX)",) \
		$(if $(KB_MD_EXCLUDE_REGEX),--exclude-regex "$(KB_MD_EXCLUDE_REGEX)",) \
		--upsert

kb-import-md-build: kb-import-md kb-build-structured

kb-rebuild: kb-build

kb-clean:
	@rm -rf "$(KB_OUT_DIR)/current" "$(KB_OUT_DIR)/versions"
	@echo "Removed $(KB_OUT_DIR)/current and $(KB_OUT_DIR)/versions"

# ---- TCM corpus pipeline ----

# Direct path: raw JSON → .docx files → kb-build (no JSONL intermediate)
tcm-docx:
	@mkdir -p "$(TCM_DOCX_DIR)"
	PYTHONPATH="$(CURDIR):$$PYTHONPATH" "$(KB_PY)" rag/tcm_corpus_to_docx.py \
		--input           "$(TCM_RAW_JSON)" \
		--output-dir      "$(TCM_DOCX_DIR)" \
		--records-per-docx $(TCM_DOCX_RPF) \
		--min-len         $(TCM_MIN_LEN)
	@echo ""
	@echo "Docx files written to $(TCM_DOCX_DIR)."
	@echo "Next: make kb-build KB_SOURCE_DIR=$(TCM_DOCX_DIR)"

# Stage 1: raw JSON → cleaned/normalized docs JSONL
tcm-stage1:
	@mkdir -p "$(dir $(TCM_DOCS_JSONL))"
	PYTHONPATH="$(CURDIR):$$PYTHONPATH" "$(TCM_PY)" rag/tcm_to_docs_jsonl.py \
		--input  "$(TCM_RAW_JSON)" \
		--output "$(TCM_DOCS_JSONL)" \
		--min-len $(TCM_MIN_LEN)

# Stages 1.5 + 2: threshold sweep → dedup → report → chunks JSONL
tcm-pipeline:
	@mkdir -p "$(TCM_PIPELINE_DIR)"
	PYTHONPATH="$(CURDIR):$$PYTHONPATH" "$(TCM_PY)" rag/run_auto_dedup_chunk_pipeline.py \
		--docs-input    "$(TCM_DOCS_JSONL)" \
		--output-dir    "$(TCM_PIPELINE_DIR)" \
		--chunk-size    $(TCM_CHUNK_SIZE) \
		--overlap       $(KB_OVERLAP) \
		--min-len       $(TCM_MIN_LEN) \
		--parallel-workers $(TCM_WORKERS)
	@echo ""
	@echo "Chunks written to $(TCM_PIPELINE_DIR)."
	@echo "Set TCM_CHUNKS_JSONL to that file then run  make kb-build-tcm"

# Stage 3: embed chunks JSONL → FAISS knowledge base
kb-build-tcm:
	@mkdir -p "$(KB_OUT_DIR)"
	PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	RAG_USE_GO_EMBEDDER="$(RAG_USE_GO_EMBEDDER)" \
	RAG_GO_EMBED_CONCURRENCY="$(RAG_GO_EMBED_CONCURRENCY)" \
	RAG_EMBED_METRICS_EVERY="$(RAG_EMBED_METRICS_EVERY)" \
	RAG_RESOURCE_METRICS_SEC="$(RAG_RESOURCE_METRICS_SEC)" \
	RAG_RESOURCE_LOG_GPU="$(RAG_RESOURCE_LOG_GPU)" \
	"$(TCM_PY)" rag/tcm_chunks_to_kb.py \
		--chunks-input "$(TCM_CHUNKS_JSONL)" \
		--out-dir      "$(KB_OUT_DIR)" \
		--provider     "$(KB_PROVIDER)" \
		--embed-model  "$(KB_EMBED_MODEL)" \
		$(if $(KB_BASE_URL),--base-url "$(KB_BASE_URL)",) \
		$(if $(KB_API_KEY),--api-key  "$(KB_API_KEY)",) \
		--batch-size   $(KB_BATCH_SIZE)

roi-build:
	@bash "$(ROI_DIR)/build.sh"

roi-benchmark:
	@"$(KB_PY)" "$(ROI_DIR)/python/benchmark_masks.py"

clean:
	@rm -rf $(VENV_DIR)
	@rm -rf storage/data storage/reports storage/logs storage/cache storage/uploads
	@find src -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find src -name "*.pyc" -delete 2>/dev/null || true

default: help
