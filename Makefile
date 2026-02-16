SERVICE_DIR := backend/device-ingestion
PYTHON ?= python3.12
VENV_DIR := .venv
VENV_PY := $(VENV_DIR)/bin/python

.PHONY: help install run-backend run-frontend db-check report clean

help:
	@echo "Available targets:"
	@echo "  make help     # list available commands"
	@echo "  make install  # install dependencies for device-ingestion"
	@echo "  make run-backend   # run device-ingestion service"
	@echo "  make run-frontend  # run Next.js frontend (dev)"
	@echo "  make db-check # verify MySQL connectivity and privileges"
	@echo "  make report   # generate docx reports"
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

clean:
	@rm -rf $(VENV_DIR)
	@rm -rf $(SERVICE_DIR)/data
	@rm -rf $(SERVICE_DIR)/__pycache__
	@find $(SERVICE_DIR) -name "*.pyc" -delete

default: help
