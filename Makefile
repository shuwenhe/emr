SERVICE_DIR := device-ingestion
PYTHON ?= python3.12
VENV_DIR := .venv
VENV_PY := $(VENV_DIR)/bin/python

.PHONY: help venv install run report clean

help:
	@echo "Available targets:"
	@echo "  make help     # list available commands"
	@echo "  make venv     # create local virtual environment"
	@echo "  make install  # install dependencies for device-ingestion"
	@echo "  make run      # run device-ingestion service"
	@echo "  make report   # generate docx reports"
	@echo "  make clean    # remove generated files"

venv:
	$(PYTHON) -m venv $(VENV_DIR)

install: venv
	$(VENV_PY) -m pip install -U pip
	$(VENV_PY) -m pip install -r $(SERVICE_DIR)/requirements.txt

run: venv
	$(VENV_PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir $(SERVICE_DIR)

report: venv
	$(VENV_PY) -m pip install -q python-docx
	$(VENV_PY) scripts/generate_reports.py --name "张三" --datasets normal_face fever_face hand_normal low_temp

clean:
	@rm -rf $(VENV_DIR)
	@rm -rf $(SERVICE_DIR)/data
	@rm -rf $(SERVICE_DIR)/__pycache__
	@find $(SERVICE_DIR) -name "*.pyc" -delete

default: help
