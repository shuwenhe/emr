# report-file-service

Go implementation of report file APIs for EMR.

## Features
- `GET /healthz`
- `GET /v1/reports?date=YYYY-MM-DD`
- `GET /v1/reports/trash`
- `GET /v1/reports/{date}/{filename}`
- `GET /v1/reports/trash/{date}/{filename}`
- `POST /v1/reports/archive`

## Run locally

```bash
cd go-services/report-file-service
go run ./cmd/server
```

Environment variables:
- `RFS_ADDR` (default `:8088`)
- `RFS_REPORTS_DIR` (default `reports`)
- `RFS_CACHE_TTL_SECONDS` (default `300`)

## Archive API

Request:

```json
{
  "date": "2026-03-11",
  "filename": "张三_20260311_101530.docx",
  "archived": true
}
```

Response:

```json
{
  "status": "archived",
  "date": "2026-03-11",
  "filename": "张三_20260311_101530.docx"
}
```
