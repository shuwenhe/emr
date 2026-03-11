# API Go 目录说明

该目录用于存放 **Go 版本 API 能力的设计与映射**。

当前状态：
- Python API 主实现：`api/python/`
- Go API 实现代码：`reports/go/`
- Gin 路由映射文档：`reports/go/docs/GIN_ROUTE_MAPPING.md`

建议演进：
1. 在 `reports/go/` 按映射表逐接口落地。
2. 在 Python 路由层通过代理开关灰度切流。
3. 稳定后再决定是否将 Go API 代码整体上提到 `api/go/`。
