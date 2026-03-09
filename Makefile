SERVICE_DIR := backend/device-ingestion
PYTHON ?= python3.12
VENV_DIR := .venv
VENV_PY := $(VENV_DIR)/bin/python
KB_PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),$(PYTHON))

KB_SOURCE_DIR ?= $(CURDIR)/rag/dataset
KB_OUT_DIR ?= $(CURDIR)/rag/kb
KB_PROVIDER ?= ollama
KB_EMBED_MODEL ?= bge-m3:latest
KB_BASE_URL ?=
KB_API_KEY ?=
KB_MAX_LEN ?= 800
KB_OVERLAP ?= 100
KB_BATCH_SIZE ?= 32

.PHONY: help install run-backend run-frontend db-check report kb-build kb-build-markdown kb-rebuild kb-clean clean

help:
	@echo "Available targets:"
	@echo "  make help     # list available commands"
	@echo "  make install  # install dependencies for device-ingestion"
	@echo "  make run-backend   # run device-ingestion service"
	@echo "  make run-frontend  # run Next.js frontend (dev)"
	@echo "  make db-check # verify MySQL connectivity and privileges"
	@echo "  make report   # generate docx reports"
	@echo "  make kb-build # build vector KB"
	@echo "  make kb-build-markdown # build KB and print markdown/chunk debug"
	@echo "  make kb-rebuild # alias of kb-build"
	@echo "  make kb-clean # remove generated KB artifacts"
	@echo "  make clean    # remove generated files"

install:
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PY) -m pip install -U pip
	$(VENV_PY) -m pip install -r $(SERVICE_DIR)/requirements.txt
	@bash -c 'cd "$(CURDIR)/frontend"; if [ -s "$$HOME/.nvm/nvm.sh" ]; then . "$$HOME/.nvm/nvm.sh" && nvm install 20 && nvm use 20; fi; npm install'


run-backend: install
	$(VENV_PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir $(SERVICE_DIR)

run-frontend:
	@bash -c 'cd "$(CURDIR)/frontend"; if [ -s "$$HOME/.nvm/nvm.sh" ]; then . "$$HOME/.nvm/nvm.sh" && nvm use 20; fi; npm run dev'

db-check:
	$(VENV_PY) backend/scripts/db_check.py

report: install
	$(VENV_PY) -m pip install -q python-docx
	$(VENV_PY) backend/scripts/generate_reports.py --name "张三" --datasets normal_face fever_face hand_normal low_temp

kb-build:
	@mkdir -p "$(KB_OUT_DIR)"
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" "$(KB_PY)" -c "from rag.kb_builder import build_kb; build_kb(source_dir='$(KB_SOURCE_DIR)', out_dir='$(KB_OUT_DIR)', provider='$(KB_PROVIDER)', embed_model='$(KB_EMBED_MODEL)', base_url='$(KB_BASE_URL)' or None, api_key='$(KB_API_KEY)' or None, max_len=int('$(KB_MAX_LEN)'), overlap=int('$(KB_OVERLAP)'), batch_size=int('$(KB_BATCH_SIZE)'), show_markdown=False)"

kb-build-markdown:
	@mkdir -p "$(KB_OUT_DIR)"
	@PYTHONPATH="$(CURDIR):$$PYTHONPATH" "$(KB_PY)" -c "from rag.kb_builder import build_kb; build_kb(source_dir='$(KB_SOURCE_DIR)', out_dir='$(KB_OUT_DIR)', provider='$(KB_PROVIDER)', embed_model='$(KB_EMBED_MODEL)', base_url='$(KB_BASE_URL)' or None, api_key='$(KB_API_KEY)' or None, max_len=int('$(KB_MAX_LEN)'), overlap=int('$(KB_OVERLAP)'), batch_size=int('$(KB_BATCH_SIZE)'), show_markdown=True)"

kb-rebuild: kb-build

kb-clean:
	@rm -rf "$(KB_OUT_DIR)/current" "$(KB_OUT_DIR)/versions"
	@echo "Removed $(KB_OUT_DIR)/current and $(KB_OUT_DIR)/versions"

clean:
	@rm -rf $(VENV_DIR)
	@rm -rf $(SERVICE_DIR)/data
	@rm -rf $(SERVICE_DIR)/__pycache__
	@find $(SERVICE_DIR) -name "*.pyc" -delete

default: help
