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
KB_CASE_IMPORT_FILE ?= $(CURDIR)/rag/kb/incoming_case.txt
KB_CASE_IMPORT_SOURCE ?= 病例原文导入
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

.PHONY: help install service-setup service service-fg service-start service-stop service-status service-restart service-precheck service-build-watch service-build-watch-start service-build-watch-stop service-build-watch-status runtime-selfcheck web web-dev-start web-dev-stop web-dev-status web-build web-prod db-check report kb-build kb-build-markdown kb-build-structured kb-validate kb-export-json kb-export-jsonl kb-json-watch-start kb-json-watch-stop kb-json-watch-status kb-import-docs kb-import-docs-build kb-import-md kb-import-md-build kb-import-case kb-rebuild kb-clean kb-build-tcm tcm-stage1 tcm-pipeline tcm-docx roi-build roi-benchmark go-embedder-build simhash-build text-ops-build public-domain-up public-domain-down auto-commit-start auto-commit-stop auto-commit-status auto-deploy-install auto-deploy-start auto-deploy-stop auto-deploy-status logs logs-backend logs-frontend logs-auto-git-push logs-auto-deploy logs-all logs-file-backend logs-file-frontend clean

help:
	@echo "Available targets:"
	@echo "  make help             # list available commands"
	@echo "  make install          # install dependencies"
	@echo "  make service          # run backend service in foreground (Ctrl+C to stop)"
	@echo "  make service-setup    # bootstrap/update backend dependencies"
	@echo "  make service-start    # start backend service in background (PID-managed)"
	@echo "  make service-stop     # stop backend service (PID-managed)"
	@echo "  make service-status   # show backend service status"
	@echo "  make service-restart  # restart backend service (PID-managed)"
	@echo "  make service-build-watch # watch backend code and auto run go build ./..."
	@echo "  make service-build-watch-start # start backend auto-build watcher in background"
	@echo "  make service-build-watch-stop  # stop backend auto-build watcher"
	@echo "  make service-build-watch-status # show backend auto-build watcher status"
	@echo "  make runtime-selfcheck # auto-detect runtime python/model and run minimal inference check"
	@echo "  make web              # run Next.js web app in foreground with hot reload"
	@echo "  make web-dev-start    # start Next.js dev server in background with hot reload"
	@echo "  make web-dev-stop     # stop background Next.js dev server"
	@echo "  make web-dev-status   # show background Next.js dev server status"
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
	@echo "  make kb-validate       # validate rag/kb/knowledge_base.jsonl schema/integrity"
	@echo "  make kb-export-json    # generate rag/kb/knowledge_base.json from jsonl"
	@echo "  make kb-export-jsonl   # generate rag/kb/knowledge_base.jsonl from json"
	@echo "  make kb-json-watch-start  # start watcher: auto sync + rebuild structured KB"
	@echo "  make kb-json-watch-fg     # run watcher in foreground"
	@echo "  make kb-json-watch-stop   # stop local KB watcher"
	@echo "  make kb-json-watch-status # show local KB watcher status"
	@echo "  make kb-import-docs    # batch import .docx/.pdf into knowledge_base.jsonl (upsert by id)"
	@echo "  make kb-import-docs-build # import docs then rebuild structured vector KB"
	@echo "  make kb-import-md      # batch import .md into knowledge_base.jsonl (upsert by id)"
	@echo "  make kb-import-md-build # import markdown then rebuild structured vector KB"
	@echo "  make kb-import-case KB_CASE_IMPORT_FILE=rag/kb/incoming_case.txt # split one pasted case into 3 rows + sync"
	@echo "  make kb-rebuild       # alias of kb-build"
	@echo "  make kb-clean         # remove generated KB artifacts"
	@echo "  make tcm-docx         # convert TCM corpus JSON → .docx files (direct path)"
	@echo "  make tcm-stage1       # Stage 1: TCM raw JSON → docs JSONL"
	@echo "  make tcm-pipeline     # Stages 1.5-2: dedup + sweep + chunk (needs TCM_DOCS_JSONL)"
	@echo "  make kb-build-tcm     # Stage 3: embed chunks → FAISS KB  (needs TCM_CHUNKS_JSONL)"
	@echo "  make roi-build        # build ROI C++ library under roi/cpp"
	@echo "  make roi-benchmark    # run ROI Python/C++ benchmark"
	@echo "  make auto-commit-start  # start watcher (includes code + Makefile/Dockerfile/.env.example)"
	@echo "    env: AUTO_COMMIT_PUSH=1 AUTO_COMMIT_PUSH_REMOTE=origin AUTO_COMMIT_PUSH_BRANCH=main"
	@echo "    env: AUTO_COMMIT_TYPE=feat|fix (commit type is restricted to feat/fix)"
	@echo "  make auto-commit-stop   # stop background auto-commit watcher"
	@echo "  make auto-commit-status # show watcher status"
	@echo "  make auto-deploy-install # install+enable user service: emr-auto-deploy"
	@echo "  make auto-deploy-start   # start auto-deploy service"
	@echo "  make auto-deploy-stop    # stop auto-deploy service"
	@echo "  make auto-deploy-status  # show auto-deploy service status"
	@echo "  make logs             # follow backend + frontend logs"
	@echo "  make logs-backend     # follow backend service log file"
	@echo "  make logs-frontend    # tail frontend log files"
	@echo "  make logs-auto-git-push # follow auto git push logs (systemd journal)"
	@echo "  make logs-auto-deploy # follow auto deploy logs (systemd journal)"
	@echo "  make logs-all         # follow backend + frontend logs"
	@echo "  make logs-file-backend  # tail backend log files"
	@echo "  make logs-file-frontend # tail frontend log files"
	@echo "  make clean            # remove generated files"

install:
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PY) -m pip install -U pip
	$(VENV_PY) -m pip install -r requirements/base.txt
	@bash -c 'cd "$(CURDIR)/web"; if [ -s "$$HOME/.nvm/nvm.sh" ]; then . "$$HOME/.nvm/nvm.sh" && nvm install 20 && nvm use 20; fi; npm install'


service-precheck:
	@bash -c 'set -e; ENABLE_RAW="$${ENABLE_GO_REPORT_PROXY:-}"; if [ -z "$$ENABLE_RAW" ] && [ -f "$(CURDIR)/.env" ]; then ENABLE_RAW="$$(grep -E "^ENABLE_GO_REPORT_PROXY=" "$(CURDIR)/.env" | tail -n1 | cut -d= -f2- | tr -d "\r\"\047" | xargs)"; fi; ENABLE="$$(printf "%s" "$$ENABLE_RAW" | tr "[:upper:]" "[:lower:]")"; if [ "$$ENABLE" = "true" ] || [ "$$ENABLE" = "1" ] || [ "$$ENABLE" = "yes" ] || [ "$$ENABLE" = "on" ]; then GO_URL="$${GO_REPORT_SERVICE_URL:-}"; if [ -z "$$GO_URL" ] && [ -f "$(CURDIR)/.env" ]; then GO_URL="$$(grep -E "^GO_REPORT_SERVICE_URL=" "$(CURDIR)/.env" | tail -n1 | cut -d= -f2- | tr -d "\r\"\047" | xargs)"; fi; if [ -z "$$GO_URL" ]; then GO_URL="http://127.0.0.1:8088"; fi; HEALTH_URL="$${GO_URL%/}/healthz"; if ! command -v curl >/dev/null 2>&1; then echo "[warn] curl 不可用，跳过 Go 服务健康检查: $$HEALTH_URL"; exit 0; fi; if ! curl -fsS "$$HEALTH_URL" >/dev/null 2>&1; then echo "[error] Go 代理开关已开启但 Go 服务未启动: $$HEALTH_URL"; echo "        请先启动 Go 服务（例如: cd reports/go && make run），或关闭 ENABLE_GO_REPORT_PROXY。"; exit 1; fi; echo "[ok] Go report 服务可用: $$HEALTH_URL"; fi'

service-setup: install

SERVICE_PORT ?= 8000
SERVICE_PID_FILE ?= $(CURDIR)/.run/service.pid
SERVICE_LOG_FILE ?= $(CURDIR)/.run/service.log
WEB_PORT ?= 3000
WEB_PID_FILE ?= $(CURDIR)/.run/web-dev.pid
WEB_STDOUT_LOG_FILE ?= $(CURDIR)/logs/emr-frontend.out.log
WEB_STDERR_LOG_FILE ?= $(CURDIR)/logs/emr-frontend.err.log
LLM_PROVIDER ?= auto
LLM_VL_PROVIDER ?= local
LLM_VL_MODEL_PATH ?= /app/Qwen
LLM_VL_ENABLED ?= 1
LLM_RUNTIME_MODEL_PATH ?= $(shell bash -c 'set -e; for p in "$${LLM_RUNTIME_MODEL_PATH}" "$${MODEL_PATH}" /app/Qwen /home/test/models/Qwen /data/models/Qwen3-1.7B-Instruct /data/models/Qwen2.5-1.5B-Instruct /data/models/Qwen2.5-7B-Instruct /data/models/Qwen2.5-14B-Instruct; do if [ -n "$$p" ] && [ -f "$$p/config.json" ]; then printf "%s" "$$p"; exit 0; fi; done; for root in /app /data/models /home/test/models /home/huawei/models; do if [ -d "$$root" ]; then cfg="$$(find "$$root" -maxdepth 3 -type f -name config.json 2>/dev/null | grep -i qwen | head -n 1)"; if [ -n "$$cfg" ]; then printf "%s" "$${cfg%/config.json}"; exit 0; fi; fi; done; printf "%s" ""')
LLM_RUNTIME_BACKEND ?= auto
LLM_RUNTIME_PYTHON ?= $(shell bash -c 'set -e; for py in "$${LLM_RUNTIME_PYTHON}" "$(VENV_PY)" /home/test/conda/envs/Qwen/bin/python "$${HOME}/venv/bin/python" "$${HOME}/.venv/bin/python" /home/huawei/venv/bin/python /home/huawei/.venv/bin/python python3; do if [ -n "$$py" ] && ( [ -x "$$py" ] || command -v "$$py" >/dev/null 2>&1 ); then if "$$py" -c "import importlib.util,sys; sys.exit(0 if (importlib.util.find_spec(\"torch\") and importlib.util.find_spec(\"torch_npu\")) else 1)" >/dev/null 2>&1; then if [ -x "$$py" ]; then printf "%s" "$$py"; else command -v "$$py"; fi; exit 0; fi; fi; done; printf "%s" "$(VENV_PY)"')
RUNTIME_SELFCHECK_BACKEND ?= cann
UVICORN_RELOAD_DIR_FLAGS ?= --reload-dir "$(CURDIR)/route" --reload-dir "$(CURDIR)/service" --reload-dir "$(CURDIR)/repository" --reload-dir "$(CURDIR)/core"
KB_JSON_WATCH_PID_FILE ?= $(CURDIR)/.git/.kb_json_watch.pid
KB_JSON_WATCH_LOG_FILE ?= $(CURDIR)/.git/kb_json_watch.log
KB_JSON_WATCH_INTERVAL ?= 2
KB_JSON_WATCH_REBUILD_COMMAND ?= make kb-build-structured
KB_JSON_WATCH_SCRIPT ?= $(CURDIR)/scripts/watch_kb_sync.py
SERVICE_BUILD_WATCH_PID_FILE ?= $(CURDIR)/.run/service_build_watch.pid
SERVICE_BUILD_WATCH_LOG_FILE ?= $(CURDIR)/.run/service_build_watch.log
SERVICE_BUILD_WATCH_SCRIPT ?= $(CURDIR)/scripts/watch_backend_build.sh


service-build-watch:
	@bash "$(SERVICE_BUILD_WATCH_SCRIPT)"

service-build-watch-start:
	@bash -c 'set -e; PID_FILE="$(SERVICE_BUILD_WATCH_PID_FILE)"; LOG_FILE="$(SERVICE_BUILD_WATCH_LOG_FILE)"; mkdir -p "$$(dirname "$$PID_FILE")"; mkdir -p "$$(dirname "$$LOG_FILE")"; if [ -f "$$PID_FILE" ] && kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[service-build-watch] already running pid=$$(cat "$$PID_FILE")"; exit 0; fi; nohup bash "$(SERVICE_BUILD_WATCH_SCRIPT)" > "$$LOG_FILE" 2>&1 & echo $$! > "$$PID_FILE"; sleep 1; if kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[service-build-watch] started pid=$$(cat "$$PID_FILE") log=$$LOG_FILE"; else echo "[service-build-watch] failed to start"; tail -n 40 "$$LOG_FILE" || true; rm -f "$$PID_FILE"; exit 1; fi'

service-build-watch-stop:
	@bash -c 'set -e; PID_FILE="$(SERVICE_BUILD_WATCH_PID_FILE)"; if [ ! -f "$$PID_FILE" ]; then echo "[service-build-watch] not running"; exit 0; fi; PID="$$(cat "$$PID_FILE")"; if kill -0 "$$PID" 2>/dev/null; then echo "[service-build-watch] stopping pid=$$PID"; kill "$$PID" || true; sleep 1; if kill -0 "$$PID" 2>/dev/null; then kill -9 "$$PID" || true; fi; else echo "[service-build-watch] stale pid file removed"; fi; rm -f "$$PID_FILE"'

service-build-watch-status:
	@bash -c 'set -e; PID_FILE="$(SERVICE_BUILD_WATCH_PID_FILE)"; if [ -f "$$PID_FILE" ] && kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[service-build-watch] running pid=$$(cat "$$PID_FILE")"; else echo "[service-build-watch] not running"; exit 1; fi'


service-fg: service-precheck
	@bash -c 'set -e; PORT="$(SERVICE_PORT)"; if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$PORT" | grep -q LISTEN; then echo "[error] Port $$PORT is already in use."; echo "        Run: make service-stop   (or use: make SERVICE_PORT=8001 service)"; exit 1; fi; LLM_PROVIDER="$(LLM_PROVIDER)" LLM_VL_PROVIDER="$(LLM_VL_PROVIDER)" LLM_VL_MODEL_PATH="$(LLM_VL_MODEL_PATH)" LLM_VL_ENABLED="$(LLM_VL_ENABLED)" LLM_RUNTIME_MODEL_PATH="$(LLM_RUNTIME_MODEL_PATH)" LLM_RUNTIME_PYTHON="$(LLM_RUNTIME_PYTHON)" LLM_RUNTIME_BACKEND="$(LLM_RUNTIME_BACKEND)" exec "$(VENV_PY)" -m uvicorn route.main:app --host 0.0.0.0 --port "$$PORT" --reload $(UVICORN_RELOAD_DIR_FLAGS)'

service: service-fg

service-start: service-precheck
	@bash -c 'set -e; PORT="$(SERVICE_PORT)"; PID_FILE="$(SERVICE_PID_FILE)"; LOG_FILE="$(SERVICE_LOG_FILE)"; mkdir -p "$$(dirname "$$PID_FILE")"; mkdir -p "$$(dirname "$$LOG_FILE")"; if [ -f "$$PID_FILE" ] && kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[service] already running pid=$$(cat "$$PID_FILE")"; exit 0; fi; if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$PORT" | grep -q LISTEN; then echo "[error] Port $$PORT is already in use."; echo "        Run: make service-stop   (or use: make SERVICE_PORT=8001 service-start)"; exit 1; fi; nohup env LLM_PROVIDER="$(LLM_PROVIDER)" LLM_VL_PROVIDER="$(LLM_VL_PROVIDER)" LLM_VL_MODEL_PATH="$(LLM_VL_MODEL_PATH)" LLM_VL_ENABLED="$(LLM_VL_ENABLED)" LLM_RUNTIME_MODEL_PATH="$(LLM_RUNTIME_MODEL_PATH)" LLM_RUNTIME_PYTHON="$(LLM_RUNTIME_PYTHON)" LLM_RUNTIME_BACKEND="$(LLM_RUNTIME_BACKEND)" "$(VENV_PY)" -m uvicorn route.main:app --host 0.0.0.0 --port "$$PORT" > "$$LOG_FILE" 2>&1 & echo $$! > "$$PID_FILE"; sleep 1; if kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[service] started pid=$$(cat "$$PID_FILE") port=$$PORT log=$$LOG_FILE"; else echo "[service] failed to start; last log:"; tail -n 40 "$$LOG_FILE" || true; rm -f "$$PID_FILE"; exit 1; fi'

service-dev: service-precheck
	@bash -c 'set -e; PORT="$(SERVICE_PORT)"; if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$PORT" | grep -q LISTEN; then echo "[error] Port $$PORT is already in use."; echo "        Run: make service-stop   (or use: make SERVICE_PORT=8001 service-dev)"; exit 1; fi; LLM_PROVIDER="$(LLM_PROVIDER)" LLM_VL_PROVIDER="$(LLM_VL_PROVIDER)" LLM_VL_MODEL_PATH="$(LLM_VL_MODEL_PATH)" LLM_VL_ENABLED="$(LLM_VL_ENABLED)" LLM_RUNTIME_MODEL_PATH="$(LLM_RUNTIME_MODEL_PATH)" LLM_RUNTIME_PYTHON="$(LLM_RUNTIME_PYTHON)" LLM_RUNTIME_BACKEND="$(LLM_RUNTIME_BACKEND)" exec "$(VENV_PY)" -m uvicorn route.main:app --host 0.0.0.0 --port "$$PORT" --reload $(UVICORN_RELOAD_DIR_FLAGS)'

service-stop:
	@bash -c 'set -e; PORT="$(SERVICE_PORT)"; PID_FILE="$(SERVICE_PID_FILE)"; if [ -f "$$PID_FILE" ]; then PID="$$(cat "$$PID_FILE")"; if kill -0 "$$PID" 2>/dev/null; then echo "[service] stopping pid=$$PID"; kill "$$PID" || true; sleep 1; if kill -0 "$$PID" 2>/dev/null; then echo "[service] force stopping pid=$$PID"; kill -9 "$$PID" || true; fi; else echo "[service] stale pid file removed"; fi; rm -f "$$PID_FILE"; fi; PIDS="$$(fuser -n tcp $$PORT 2>/dev/null || true)"; if [ -n "$$PIDS" ]; then echo "[service] cleanup by port $$PORT pids: $$PIDS"; echo "$$PIDS" | xargs -r kill || true; sleep 1; REMAIN="$$(fuser -n tcp $$PORT 2>/dev/null || true)"; if [ -n "$$REMAIN" ]; then echo "[service] force cleanup by port $$PORT pids: $$REMAIN"; echo "$$REMAIN" | xargs -r kill -9 || true; fi; fi; if command -v ss >/dev/null 2>&1; then ss -ltnp | grep ":$$PORT" || true; fi'

service-status:
	@bash -c 'set -e; PORT="$(SERVICE_PORT)"; PID_FILE="$(SERVICE_PID_FILE)"; if [ -f "$$PID_FILE" ]; then PID="$$(cat "$$PID_FILE")"; if kill -0 "$$PID" 2>/dev/null; then echo "[service] running pid=$$PID port=$$PORT"; if command -v ss >/dev/null 2>&1; then ss -ltnp | grep ":$$PORT" || true; fi; exit 0; fi; echo "[service] pid file exists but process not running: $$PID_FILE"; exit 1; fi; if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$PORT" | grep -q LISTEN; then echo "[service] running on port $$PORT but pid file missing"; ss -ltnp | grep ":$$PORT" || true; exit 0; fi; echo "[service] not running"; exit 1'

service-restart: service-stop service-start

service-prod: service-precheck
	@bash -c 'set -e; PORT="$(SERVICE_PORT)"; if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$PORT" | grep -q LISTEN; then echo "[error] Port $$PORT is already in use."; echo "        Run: make service-stop   (or use: make SERVICE_PORT=8001 service-prod)"; exit 1; fi; LLM_PROVIDER="$(LLM_PROVIDER)" LLM_VL_PROVIDER="$(LLM_VL_PROVIDER)" LLM_VL_MODEL_PATH="$(LLM_VL_MODEL_PATH)" LLM_VL_ENABLED="$(LLM_VL_ENABLED)" LLM_RUNTIME_MODEL_PATH="$(LLM_RUNTIME_MODEL_PATH)" LLM_RUNTIME_PYTHON="$(LLM_RUNTIME_PYTHON)" LLM_RUNTIME_BACKEND="$(LLM_RUNTIME_BACKEND)" exec "$(VENV_PY)" -m uvicorn route.main:app --host 0.0.0.0 --port "$$PORT"'

runtime-selfcheck:
	@set -e; \
	mkdir -p "$(CURDIR)/.run"; \
	IN_FILE="$(CURDIR)/.run/runtime_selfcheck_input.jsonl"; \
	OUT_FILE="$(CURDIR)/.run/runtime_selfcheck_output.jsonl"; \
	SCRIPT_FILE="$(CURDIR)/runtime/infer_qwen_8card.py"; \
	echo '{"id":"selfcheck-1","prompt":"Reply exactly: runtime-selfcheck-ok"}' > "$$IN_FILE"; \
	echo "[runtime-selfcheck] model_path=$(LLM_RUNTIME_MODEL_PATH)"; \
	echo "[runtime-selfcheck] runtime_python=$(LLM_RUNTIME_PYTHON)"; \
	echo "[runtime-selfcheck] backend=$(RUNTIME_SELFCHECK_BACKEND)"; \
	if [ -z "$(LLM_RUNTIME_MODEL_PATH)" ] || [ ! -f "$(LLM_RUNTIME_MODEL_PATH)/config.json" ]; then \
		echo "[runtime-selfcheck][error] invalid model path: $(LLM_RUNTIME_MODEL_PATH)"; \
		exit 1; \
	fi; \
	if ! ( [ -x "$(LLM_RUNTIME_PYTHON)" ] || command -v "$(LLM_RUNTIME_PYTHON)" >/dev/null 2>&1 ); then \
		echo "[runtime-selfcheck][error] runtime python not found: $(LLM_RUNTIME_PYTHON)"; \
		exit 1; \
	fi; \
	if grep -qi 'qwen2_5_vl\|"model_type"[[:space:]]*:[[:space:]]*".*vl' "$(LLM_RUNTIME_MODEL_PATH)/config.json"; then \
		SCRIPT_FILE="$(CURDIR)/runtime/infer_qwen_vl_8card.py"; \
	fi; \
	echo "[runtime-selfcheck] script=$$SCRIPT_FILE"; \
	"$(LLM_RUNTIME_PYTHON)" "$$SCRIPT_FILE" \
		--model-path "$(LLM_RUNTIME_MODEL_PATH)" \
		--input-file "$$IN_FILE" \
		--output-file "$$OUT_FILE" \
		--runtime-backend "$(RUNTIME_SELFCHECK_BACKEND)" \
		--batch-size 1 \
		--max-new-tokens 8 \
		--temperature 0 \
		--top-p 0.9 \
		--dtype float16 \
		--trust-remote-code true; \
	echo "[runtime-selfcheck] output:"; \
	cat "$$OUT_FILE"

web:
	@bash -c 'set -e; WEB_DIR="$(CURDIR)/web"; LOCK_FILE="$$WEB_DIR/.next/dev/lock"; if [ -f "$$LOCK_FILE" ]; then echo "Removing stale lock: $$LOCK_FILE"; rm -f "$$LOCK_FILE"; fi; cd "$$WEB_DIR"; if [ -s "$$HOME/.nvm/nvm.sh" ]; then . "$$HOME/.nvm/nvm.sh" && nvm use 20; fi; npm run dev'

web-dev-start:
	@bash -c 'set -e; PORT="$(WEB_PORT)"; PID_FILE="$(WEB_PID_FILE)"; OUT_LOG="$(WEB_STDOUT_LOG_FILE)"; ERR_LOG="$(WEB_STDERR_LOG_FILE)"; WEB_DIR="$(CURDIR)/web"; mkdir -p "$$(dirname "$$PID_FILE")" "$$(dirname "$$OUT_LOG")" "$$(dirname "$$ERR_LOG")"; if [ -f "$$PID_FILE" ] && kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[web-dev] already running pid=$$(cat "$$PID_FILE") port=$$PORT"; exit 0; fi; if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$PORT" | grep -q LISTEN; then echo "[error] Frontend port $$PORT is already in use."; echo "        Run: make web-dev-stop   (or use: make WEB_PORT=3001 web-dev-start)"; exit 1; fi; LOCK_FILE="$$WEB_DIR/.next/dev/lock"; if [ -f "$$LOCK_FILE" ]; then rm -f "$$LOCK_FILE"; fi; nohup bash -lc "set -e; cd \"$$WEB_DIR\"; if [ -s \"$$HOME/.nvm/nvm.sh\" ]; then . \"$$HOME/.nvm/nvm.sh\" && nvm use 20 >/dev/null; fi; exec npm run dev -- --hostname 0.0.0.0 --port $$PORT" > "$$OUT_LOG" 2> "$$ERR_LOG" & echo $$! > "$$PID_FILE"; sleep 2; if kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[web-dev] started pid=$$(cat "$$PID_FILE") port=$$PORT"; echo "[web-dev] logs: $$OUT_LOG $$ERR_LOG"; else echo "[web-dev] failed to start"; tail -n 40 "$$ERR_LOG" || true; tail -n 40 "$$OUT_LOG" || true; rm -f "$$PID_FILE"; exit 1; fi'

web-dev-stop:
	@bash -c 'set -e; PORT="$(WEB_PORT)"; PID_FILE="$(WEB_PID_FILE)"; if [ -f "$$PID_FILE" ]; then PID="$$(cat "$$PID_FILE")"; if kill -0 "$$PID" 2>/dev/null; then echo "[web-dev] stopping pid=$$PID"; kill "$$PID" || true; sleep 1; if kill -0 "$$PID" 2>/dev/null; then kill -9 "$$PID" || true; fi; else echo "[web-dev] stale pid file removed"; fi; rm -f "$$PID_FILE"; fi; PIDS="$$(fuser -n tcp $$PORT 2>/dev/null || true)"; if [ -n "$$PIDS" ]; then echo "[web-dev] cleanup by port $$PORT pids: $$PIDS"; echo "$$PIDS" | xargs -r kill || true; sleep 1; REMAIN="$$(fuser -n tcp $$PORT 2>/dev/null || true)"; if [ -n "$$REMAIN" ]; then echo "$$REMAIN" | xargs -r kill -9 || true; fi; fi'

web-dev-status:
	@bash -c 'set -e; PORT="$(WEB_PORT)"; PID_FILE="$(WEB_PID_FILE)"; if [ -f "$$PID_FILE" ]; then PID="$$(cat "$$PID_FILE")"; if kill -0 "$$PID" 2>/dev/null; then echo "[web-dev] running pid=$$PID port=$$PORT"; if command -v ss >/dev/null 2>&1; then ss -ltnp | grep ":$$PORT" || true; fi; exit 0; fi; echo "[web-dev] pid file exists but process not running: $$PID_FILE"; exit 1; fi; if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$PORT" | grep -q LISTEN; then echo "[web-dev] running on port $$PORT but pid file missing"; ss -ltnp | grep ":$$PORT" || true; exit 0; fi; echo "[web-dev] not running"; exit 1'

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

kb-validate:
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	"$(KB_PY)" scripts/validate_kb_jsonl.py \
		--kb "$(STRUCTURED_KB_JSONL)"

kb-export-json:
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	"$(KB_PY)" scripts/kb_jsonl_to_json.py \
		--input-jsonl "$(STRUCTURED_KB_JSONL)" \
		--output-json "$(CURDIR)/rag/kb/knowledge_base.json"

kb-export-jsonl:
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	"$(KB_PY)" scripts/kb_json_to_jsonl.py \
		--input-json "$(CURDIR)/rag/kb/knowledge_base.json" \
		--output-jsonl "$(STRUCTURED_KB_JSONL)"

kb-json-watch-fg:
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	"$(KB_PY)" "$(KB_JSON_WATCH_SCRIPT)" \
		--repo-dir "$(CURDIR)" \
		--kb-json "$(CURDIR)/rag/kb/knowledge_base.json" \
		--kb-jsonl "$(STRUCTURED_KB_JSONL)" \
		--interval "$(KB_JSON_WATCH_INTERVAL)" \
		--python "$(KB_PY)" \
		--rebuild-command '$(KB_JSON_WATCH_REBUILD_COMMAND)'

kb-json-watch-start:
	@bash -c 'set -e; PID_FILE="$(KB_JSON_WATCH_PID_FILE)"; LOG_FILE="$(KB_JSON_WATCH_LOG_FILE)"; if [ -f "$$PID_FILE" ] && kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[kb-watch] already running (pid=$$(cat "$$PID_FILE"))"; exit 0; fi; mkdir -p "$$(dirname "$$LOG_FILE")"; setsid nohup env PYTHONPATH="$(CURDIR):$$PYTHONPATH" "$(KB_PY)" "$(KB_JSON_WATCH_SCRIPT)" --repo-dir "$(CURDIR)" --kb-json "$(CURDIR)/rag/kb/knowledge_base.json" --kb-jsonl "$(STRUCTURED_KB_JSONL)" --interval "$(KB_JSON_WATCH_INTERVAL)" --python "$(KB_PY)" --rebuild-command '"'"'$(KB_JSON_WATCH_REBUILD_COMMAND)'"'"' > "$$LOG_FILE" 2>&1 < /dev/null & PID="$$!"; echo "$$PID" > "$$PID_FILE"; sleep 1; if kill -0 "$$PID" 2>/dev/null; then echo "[kb-watch] started pid=$$PID log=$$LOG_FILE rebuild=$(KB_JSON_WATCH_REBUILD_COMMAND)"; else echo "[kb-watch] failed to stay running; check $$LOG_FILE"; rm -f "$$PID_FILE"; exit 1; fi'

kb-json-watch-stop:
	@bash -c 'set -e; PID_FILE="$(KB_JSON_WATCH_PID_FILE)"; if [ ! -f "$$PID_FILE" ]; then echo "[kb-watch] not running"; exit 0; fi; PID="$$(cat "$$PID_FILE")"; if kill -0 "$$PID" 2>/dev/null; then kill "$$PID"; echo "[kb-watch] stopped pid=$$PID"; else echo "[kb-watch] stale pid file removed"; fi; rm -f "$$PID_FILE"'

kb-json-watch-status:
	@bash -c 'set -e; PID_FILE="$(KB_JSON_WATCH_PID_FILE)"; LOG_FILE="$(KB_JSON_WATCH_LOG_FILE)"; if [ -f "$$PID_FILE" ] && kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[kb-watch] running pid=$$(cat "$$PID_FILE")"; else echo "[kb-watch] not running"; fi; if [ -f "$$LOG_FILE" ]; then echo "[kb-watch] recent log:"; tail -n 10 "$$LOG_FILE"; fi'

kb-build-structured: kb-validate
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
	@$(MAKE) kb-validate
	@$(MAKE) kb-export-json

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
	@$(MAKE) kb-validate
	@$(MAKE) kb-export-json

kb-import-md-build: kb-import-md kb-build-structured

kb-import-case:
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" \
	"$(KB_PY)" scripts/import_case_to_kb.py \
		--case-file "$(KB_CASE_IMPORT_FILE)" \
		--kb-jsonl "$(STRUCTURED_KB_JSONL)" \
		--kb-json "$(CURDIR)/rag/kb/knowledge_base.json" \
		--source-name "$(KB_CASE_IMPORT_SOURCE)"
	@$(MAKE) kb-validate

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

auto-commit-start:
	@bash -c 'set -e; PID_FILE="$(CURDIR)/.git/.auto_commit.pid"; LOG_FILE="$(CURDIR)/.git/auto_commit.log"; if [ -f "$$PID_FILE" ] && kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[auto-commit] already running (pid=$$(cat "$$PID_FILE"))"; exit 0; fi; nohup bash "$(CURDIR)/scripts/auto_commit_on_change.sh" > "$$LOG_FILE" 2>&1 & echo $$! > "$$PID_FILE"; echo "[auto-commit] started pid=$$(cat "$$PID_FILE") log=$$LOG_FILE"'

auto-commit-stop:
	@bash -c 'set -e; PID_FILE="$(CURDIR)/.git/.auto_commit.pid"; if [ ! -f "$$PID_FILE" ]; then echo "[auto-commit] not running"; exit 0; fi; PID="$$(cat "$$PID_FILE")"; if kill -0 "$$PID" 2>/dev/null; then kill "$$PID"; echo "[auto-commit] stopped pid=$$PID"; else echo "[auto-commit] stale pid file removed"; fi; rm -f "$$PID_FILE"'

auto-commit-status:
	@bash -c 'set -e; PID_FILE="$(CURDIR)/.git/.auto_commit.pid"; if [ -f "$$PID_FILE" ] && kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[auto-commit] running pid=$$(cat "$$PID_FILE")"; else echo "[auto-commit] not running"; fi; LOG_FILE="$(CURDIR)/.git/auto_commit.log"; if [ -f "$$LOG_FILE" ]; then echo "[auto-commit] recent log:"; tail -n 10 "$$LOG_FILE"; fi'

auto-deploy-install:
	@bash "$(CURDIR)/scripts/deployment/install_auto_deploy_user_service.sh"

auto-deploy-start:
	@systemctl --user enable --now emr-auto-deploy

auto-deploy-stop:
	@systemctl --user stop emr-auto-deploy

auto-deploy-status:
	@systemctl --user --no-pager --full status emr-auto-deploy | sed -n '1,30p'

logs: logs-backend

logs-backend:
	@bash -c 'set -e; LOG_FILE="$(SERVICE_LOG_FILE)"; PID_FILE="$(SERVICE_PID_FILE)"; mkdir -p "$$(dirname "$$LOG_FILE")"; touch "$$LOG_FILE"; if [ -f "$$PID_FILE" ] && kill -0 "$$(cat "$$PID_FILE")" 2>/dev/null; then echo "[logs-backend] following $$LOG_FILE"; else echo "[logs-backend] backend is not running; showing last log entries from $$LOG_FILE"; fi; tail -n 50 -f "$$LOG_FILE"'

logs-frontend:
	@bash -c 'tail -f "$(CURDIR)/logs/emr-frontend.out.log" "$(CURDIR)/logs/emr-frontend.err.log"'

logs-auto-git-push:
	@journalctl --user -u emr-auto-git-push -f

logs-auto-deploy:
	@bash -c 'OUT_LOG="$(CURDIR)/logs/emr-auto-deploy.out.log"; ERR_LOG="$(CURDIR)/logs/emr-auto-deploy.err.log"; mkdir -p "$(CURDIR)/logs"; touch "$$OUT_LOG" "$$ERR_LOG"; echo "[logs-auto-deploy] following $$OUT_LOG and $$ERR_LOG"; tail -n 50 -f "$$OUT_LOG" "$$ERR_LOG"'

logs-all:
	@bash -c 'mkdir -p "$(CURDIR)/logs" "$(CURDIR)/.run"; touch "$(SERVICE_LOG_FILE)" "$(CURDIR)/logs/emr-frontend.out.log" "$(CURDIR)/logs/emr-frontend.err.log"; tail -f "$(SERVICE_LOG_FILE)" "$(CURDIR)/logs/emr-frontend.out.log" "$(CURDIR)/logs/emr-frontend.err.log"'

logs-file-backend:
	@bash -c 'LOG_FILE="$(SERVICE_LOG_FILE)"; mkdir -p "$$(dirname "$$LOG_FILE")"; touch "$$LOG_FILE"; tail -n 50 -f "$$LOG_FILE"'

logs-file-frontend:
	@bash -c 'tail -f "$(CURDIR)/logs/emr-frontend.out.log" "$(CURDIR)/logs/emr-frontend.err.log"'

clean:
	@rm -rf $(VENV_DIR)
	@rm -rf storage/data storage/reports storage/logs storage/cache storage/uploads
	@find src -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find src -name "*.pyc" -delete 2>/dev/null || true

default: help
