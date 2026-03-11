# 医院热成像系统 - 优化建议

基于代码审查和问题追踪，以下是项目的优化建议，按**优先级**排序。

---

## 🔴 高优先级（紧急）

### 1. 数据完整性问题

**问题**：41条EMR记录的 `patient_id` 为NULL，影响查询功能

```bash
# 当前状态
- 79条EMR记录总数
- 41条patient_id为NULL (52%)
- 影响31个患者的数据查询

# 修复方法
cd /home/shuwen/emr/ingestion
mysql -u hospital -phospital hospital << 'EOF'
UPDATE emrs e
INNER JOIN patients p ON JSON_UNQUOTE(JSON_EXTRACT(e.emr_json, '$.patient.name')) = p.name
SET e.patient_id = p.patient_id
WHERE e.patient_id IS NULL AND JSON_EXTRACT(e.emr_json, '$.patient.name') IS NOT NULL;
EOF
```

**预防措施**：
- 在 `save_emr()` 函数中添加断言
- 数据导入前验证patient_id必须存在
- 添加数据库约束：`ALTER TABLE emrs ADD CONSTRAINT fk_emrs_patient FOREIGN KEY (patient_id) REFERENCES patients(patient_id)`

---

### 2. MySQL索引优化

**当前问题**：
- 已创建 `idx_emrs_patient_archived_created` 但未验证是否被使用
- 没有对 `record_id` 的单独索引优化

**建议**：
```sql
-- 验证索引使用情况
EXPLAIN SELECT emr_id, created_at 
FROM emrs 
WHERE patient_id = 'P036A91B77191' AND archived = 0 
ORDER BY created_at DESC LIMIT 50;

-- 如果未使用covering index，添加：
CREATE INDEX idx_emrs_patient_created_id 
ON emrs (patient_id, archived, created_at DESC, emr_id);

-- 为频繁的record_id查询添加索引
CREATE INDEX idx_emrs_record ON emrs (record_id);
```

**性能提升预期**：
- 大患者（>10条记录）查询速度：5-10s → 100-300ms
- 减少 sort_buffer 使用

---

### 3. 前端TypeScript类型安全

**当前问题**：
- 多处使用 `any` 类型
- 未使用的变量和函数
- 缺少类型定义

**修复**：

```typescript
// comparison/page.tsx - 定义类型
type ComparisonResult = {
  temperature_change: {
    before_avg: number;
    after_avg: number;
    change_pct: number;
  };
  risk_change: {
    before: string;
    after: string;
    improved: boolean;
  };
  // ... 其他字段
};

// 替换 any
const [comparison, setComparison] = useState<ComparisonResult | null>(null);

// 移除未使用的变量
- const [recordIdFromUrl, setRecordIdFromUrl] = useState<string | null>(null);
```

---

## 🟡 中优先级（重要）

### 4. 代码结构重构

**问题**：部分文件过大，职责不清晰

```
app/analysis.py      31KB  - 分析逻辑
app/llm_report.py    26KB  - LLM集成
app/data_platform.py 24KB  - 数据库操作
app/main.py          18KB  - API路由
```

**建议重构**：

#### 4.1 拆分 data_platform.py
```python
# 当前: data_platform.py (24KB, 707行)
# 建议拆分为:

app/db/
  ├── __init__.py
  ├── connection.py      # 连接管理、重试逻辑
  ├── patients.py        # 患者相关操作
  ├── emrs.py           # EMR相关操作
  ├── reports.py        # 报告相关操作
  └── compression.py    # 数据压缩/解压
```

#### 4.2 拆分 main.py
```python
# 当前: main.py (18KB, 514行)
# 建议拆分为:

app/api/
  ├── __init__.py
  ├── emr_routes.py     # EMR相关路由
  ├── patient_routes.py # 患者相关路由
  ├── report_routes.py  # 报告相关路由
  └── upload_routes.py  # 数据上传路由
```

---

### 5. 性能优化 - 数据库连接池

**当前问题**：每个请求创建新连接

```python
# 当前实现
def _connect():
    return pymysql.connect(...)  # 每次新建连接

# 建议改为连接池
from dbutils.pooled_db import PooledDB

_pool = PooledDB(
    creator=pymysql,
    maxconnections=20,
    mincached=2,
    maxcached=5,
    host=MYSQL_HOST,
    # ...
)

def _get_connection():
    return _pool.connection()
```

**性能提升预期**：
- 减少连接建立开销：50-100ms → 1-5ms
- 提高并发处理能力

---

### 6. API缓存策略

**当前问题**：患者列表、EMR列表频繁查询但很少变化

**建议**：
```python
from functools import lru_cache
from datetime import datetime, timedelta

# 1. 内存缓存（短期）
@lru_cache(maxsize=128)
def get_patient_cached(patient_id: str, cache_key: str):
    return get_patient(patient_id)

# 2. Redis缓存（推荐）
import redis
cache = redis.Redis(host='localhost', port=6379)

def get_patients_list_cached():
    key = 'patients:list:all'
    cached = cache.get(key)
    if cached:
        return json.loads(cached)
    
    data = list_patients()
    cache.setex(key, 300, json.dumps(data))  # 5分钟TTL
    return data
```

---

### 7. 前端性能优化

#### 7.1 图片优化
```typescript
// 当前: 使用原生 <img>
<img src={buildThermalImageUrl(image)} />

// 建议: 使用 Next.js Image 组件
import Image from 'next/image';

<Image
  src={buildThermalImageUrl(image)}
  alt="热成像图"
  width={800}
  height={600}
  loading="lazy"
  quality={85}
/>
```

#### 7.2 组件懒加载
```typescript
// 对大型可视化组件使用动态导入
const ThermalChart = dynamic(() => import('./ThermalChart'), {
  loading: () => <div>加载中...</div>,
  ssr: false
});
```

#### 7.3 API请求去重和防抖
```typescript
// 使用 SWR 或 React Query
import useSWR from 'swr';

function usePatients() {
  const { data, error } = useSWR(
    '/patients',
    fetcher,
    { revalidateOnFocus: false }
  );
  return { patients: data, isLoading: !error && !data };
}
```

---

## 🟢 低优先级（优化）

### 8. 日志和监控增强

**建议添加**：
```python
# 1. 结构化日志
import structlog
logger = structlog.get_logger()

logger.info(
    "emr_created",
    emr_id=emr_id,
    patient_id=patient_id,
    duration_ms=duration
)

# 2. 性能监控
import time
from functools import wraps

def monitor_performance(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = (time.time() - start) * 1000
        logger.info(f"{func.__name__} took {duration:.2f}ms")
        return result
    return wrapper

# 3. 错误追踪（Sentry）
import sentry_sdk
sentry_sdk.init(dsn="your-dsn")
```

---

### 9. 数据压缩优化

**当前实现**：10MB阈值，压缩率约40-60%

**优化建议**：
```python
# 1. 动态调整压缩级别
def _compress_data_optimized(data: str, size_mb: float) -> str:
    if size_mb < 5:
        return data  # 小数据不压缩
    elif size_mb < 20:
        level = 6  # 当前级别
    else:
        level = 9  # 大数据使用最高压缩
    
    compressed = zlib.compress(data.encode('utf-8'), level=level)
    # ...

# 2. 考虑使用更高效的压缩算法
import lz4.frame
compressed = lz4.frame.compress(data.encode('utf-8'))
# LZ4: 压缩速度快5-10倍，压缩率稍低
```

---

### 10. 安全性增强

#### 10.1 API认证
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.get("/emr/{emr_id}")
async def get_emr_endpoint(
    emr_id: str,
    credentials: HTTPBearer = Depends(security)
):
    # 验证token
    verify_token(credentials.credentials)
    # ...
```

#### 10.2 SQL注入防护验证
```python
# 当前代码已使用参数化查询，但建议添加额外验证

def validate_patient_id(patient_id: str) -> str:
    """验证patient_id格式，防止注入"""
    if not re.match(r'^P[A-Z0-9]{12}$', patient_id):
        raise ValueError("Invalid patient_id format")
    return patient_id
```

#### 10.3 敏感数据脱敏
```python
# 日志中隐藏敏感信息
def sanitize_for_log(patient_data: dict) -> dict:
    sensitive_fields = ['phone', 'id_card', 'address']
    sanitized = patient_data.copy()
    for field in sensitive_fields:
        if field in sanitized:
            sanitized[field] = '***'
    return sanitized
```

---

### 11. 测试覆盖率

**当前状态**：缺少自动化测试

**建议添加**：

```python
# tests/test_emr.py
import pytest
from app.emr import generate_emr

def test_generate_emr_with_valid_record():
    emr = generate_emr("test-record-id")
    assert emr['emr_id'] is not None
    assert emr['patient']['patient_id'] is not None

def test_generate_emr_idempotent():
    """测试幂等性：重复调用返回相同结果"""
    emr1 = generate_emr("test-record", force=False)
    emr2 = generate_emr("test-record", force=False)
    assert emr1['emr_id'] == emr2['emr_id']

# tests/test_data_platform.py
def test_list_emrs_performance():
    """测试大数据量查询性能"""
    import time
    start = time.time()
    emrs = list_emrs(patient_id="P036A91B77191")
    duration = time.time() - start
    assert duration < 0.5  # 应在500ms内完成
```

**CI/CD集成**：
```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        run: |
          pip install pytest pytest-cov
          pytest --cov=app tests/
```

---

### 12. 部署优化

#### 12.1 Docker化
```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 12.2 环境配置管理
```python
# 使用 pydantic-settings
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mysql_host: str
    mysql_port: int = 3306
    mysql_user: str
    mysql_password: str
    redis_url: str = "redis://localhost:6379"
    debug: bool = False
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 📊 优化效果预期

| 优化项 | 当前性能 | 优化后 | 提升 |
|--------|---------|--------|------|
| EMR列表查询（大患者） | 5-10s | 100-300ms | **30-100x** |
| 患者数据查询 | 数据缺失 | 100%完整 | **✓** |
| API并发处理 | 10 req/s | 50+ req/s | **5x** |
| 前端首屏加载 | 2-3s | 1s以内 | **2-3x** |
| 代码可维护性 | 中 | 高 | **✓** |

---

## 🚀 实施路线图

### Phase 1: 紧急修复（1-2天）
- [ ] 修复所有NULL patient_id记录
- [ ] 验证MySQL索引使用情况
- [ ] 修复TypeScript类型错误

### Phase 2: 性能优化（3-5天）
- [ ] 实施数据库连接池
- [ ] 添加Redis缓存
- [ ] 前端图片优化

### Phase 3: 代码重构（1-2周）
- [ ] 拆分大文件
- [ ] 添加单元测试
- [ ] 增强日志监控

### Phase 4: 长期改进（持续）
- [ ] 完善安全机制
- [ ] Docker容器化
- [ ] CI/CD流水线

---

## 📝 维护检查清单

**每周检查**：
```bash
# 1. 数据完整性
mysql -u hospital -phospital hospital -e "
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN patient_id IS NULL THEN 1 ELSE 0 END) as null_count
FROM emrs;
"

# 2. 性能指标
mysql -u hospital -phospital hospital -e "
SELECT 
    table_name,
    ROUND(data_length/1024/1024, 2) as data_mb,
    ROUND(index_length/1024/1024, 2) as index_mb
FROM information_schema.tables
WHERE table_schema = 'hospital';
"

# 3. 慢查询日志
mysql -u hospital -phospital hospital -e "
SELECT * FROM mysql.slow_log 
WHERE start_time > DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY query_time DESC LIMIT 10;
"
```

**每月检查**：
- 数据库备份验证
- 磁盘空间使用
- 依赖包更新
- 安全补丁应用

---

## 💡 其他建议

1. **文档化**：为所有API端点添加OpenAPI文档
2. **国际化**：考虑支持多语言（i18n）
3. **移动端适配**：优化前端响应式设计
4. **数据导出**：支持批量导出EMR数据（CSV/Excel）
5. **审计日志**：记录所有数据修改操作

---

**优先实施顺序**：
1. 修复NULL patient_id（立即）
2. 验证索引优化（本周）
3. TypeScript类型安全（本周）
4. 连接池+缓存（下周）
5. 代码重构（后续迭代）
