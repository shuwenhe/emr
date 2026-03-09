# hospital-report

Infrared thermal imaging ingestion, analysis, and report generation workflow.

## Quick Start
1. Create venv and install dependencies
	- `make install`
2. Run the ingestion service
	- `make run`
3. Generate DOCX reports from test data
	- `make report`

## Services
The FastAPI service lives under [backend/device-ingestion](backend/device-ingestion).

## Frontend
Next.js app lives under [frontend](frontend). EMR page route: /emr

### Endpoints
- `POST /ingest` upload a data file and metadata JSON
- `POST /analyze` generate report + therapy plan for a stored record
- `POST /dispatch` send therapy plan to device (simulated)

API details and examples are in [docs/设备接入接口.md](docs/设备接入接口.md).
Treatment plan rules are documented in [docs/TREATMENT_RULES.md](docs/TREATMENT_RULES.md).

## Test Data
Test datasets are in [data](data):
- `normal_face`
- `fever_face`
- `hand_normal`
- `low_temp`

Each dataset includes:
- `metadata.json`
- `frame_0001.csv`

## Report Output
Reports are generated under `reports/YYYYMMDD/` with filenames:
- `<patient_name>_YYYYMMDD_HHMMSS.docx`

## Common Commands
- `make help`
- `make install`
- `make run`
- `make report`
- `make kb-build`
- `make kb-build-markdown`
- `make kb-rebuild`
- `make kb-clean`
- `make clean`

## RAG Knowledge Base
- Source documents default directory: [rag/dataset](rag/dataset)
- KB build output default directory: [rag/kb](rag/kb)
- Active runtime index path: [rag/kb/current](rag/kb/current)
- Versioned build artifacts are stored in [rag/kb/versions](rag/kb/versions)

## Documentation
- **[AI报告生成代码分析](docs/ai-analysis/)** - 完整的AI报告生成系统代码分析（6份详细文档）
  - 系统架构与流程详解
  - 代码质量审查与改进建议
  - 故障排查指南
- **[设备接入接口](docs/设备接入接口.md)** - API详细说明
- **[治疗规则说明](docs/TREATMENT_RULES.md)** - 治疗方案规则文档

## Notes
- Python 3.12 is required.
- The report template is based on [docs/红外热成像评估报告_文字提取.md](docs/红外热成像评估报告_文字提取.md).