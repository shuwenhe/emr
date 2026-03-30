FROM python:3.12-slim

LABEL maintainer="Hospital Report Team"
LABEL description="Hospital Infrared Thermal Imaging Backend API"

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements/base.txt requirements.txt

# 安装Python依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制应用代码（使用根目录布局，避免遗漏新模块）
COPY . /app

# 创建必要的目录
RUN mkdir -p /app/storage/data /app/storage/reports /app/storage/logs

# 非root用户运行
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["sh", "-c", "uvicorn route.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-4}"]
