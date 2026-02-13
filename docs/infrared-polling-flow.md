# Red Infrared Polling Flow

```mermaid
flowchart LR
  A[Server polling: infrared thermal imaging IP address] --> B[Pull realtime temperature data + images]
  B --> C[Persist to disk (record folder + metadata)]
  C --> D[Write temperature pixel coordinates to time-series DB (ClickHouse)]
  D --> E[Run analysis pipeline]
  E --> F[Generate EMR + report + thermal image]
```
