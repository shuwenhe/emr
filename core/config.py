"""
Core configuration management for EMR system.

Supports multiple environments (development, test, production) with environment variable overrides.
Follows 12-factor app methodology.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application environment."""
    
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings with environment-based configuration."""
    
    # ==================== Application ====================
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Application environment"
    )
    APP_NAME: str = Field(default="EMR System", description="Application name")
    API_VERSION: str = Field(default="v1", description="API version")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # ==================== Server ====================
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=8000, description="Server port")
    WORKERS: int = Field(default=4, description="Number of worker processes")
    
    # ==================== Database ====================
    # MySQL
    MYSQL_HOST: str = Field(default="localhost", description="MySQL host")
    MYSQL_PORT: int = Field(default=3306, description="MySQL port")
    MYSQL_USER: str = Field(default="emr_user", description="MySQL user")
    MYSQL_PASSWORD: str = Field(default="", description="MySQL password")
    MYSQL_DATABASE: str = Field(default="emr_db", description="MySQL database")
    
    @property
    def mysql_url(self) -> str:
        """Get MySQL connection URL."""
        return f"mysql+mysqlconnector://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
    
    # ClickHouse
    CLICKHOUSE_HOST: str = Field(default="localhost", description="ClickHouse host")
    CLICKHOUSE_PORT: int = Field(default=9000, description="ClickHouse port")
    CLICKHOUSE_USER: str = Field(default="default", description="ClickHouse user")
    CLICKHOUSE_PASSWORD: str = Field(default="", description="ClickHouse password")
    CLICKHOUSE_DATABASE: str = Field(default="emr", description="ClickHouse database")
    
    # ==================== Storage ====================
    STORAGE_ROOT: Path = Field(
        default=Path("storage"),
        description="Root directory for all runtime data"
    )
    
    @property
    def DATA_DIR(self) -> Path:
        """Patient data directory (legacy location for compatibility)."""
        project_root = Path(__file__).resolve().parents[1]
        return project_root / "data"
    
    @property
    def REPORTS_DIR(self) -> Path:
        """Generated reports directory (legacy location for compatibility)."""
        return self.STORAGE_ROOT / "reports"
    
    @property
    def LOGS_DIR(self) -> Path:
        """Application logs directory."""
        return self.STORAGE_ROOT / "logs"
    
    @property
    def CACHE_DIR(self) -> Path:
        """Cache directory."""
        return self.STORAGE_ROOT / "cache"
    
    @property
    def UPLOADS_DIR(self) -> Path:
        """User uploads directory."""
        return self.STORAGE_ROOT / "uploads"
    
    @property
    def EMR_DIR(self) -> Path:
        """EMR records directory."""
        return self.DATA_DIR / "emr"
    
    @property
    def TEMPLATE_DIR(self) -> Path:
        """Report templates directory."""
        return Path("template")
    
    # ==================== AI / LLM ====================
    LLM_ENABLED: bool = Field(default=False, description="Enable LLM features")
    LLM_PROVIDER: str = Field(default="ollama", description="LLM provider (ollama/openai/azure)")
    LLM_MODEL: str = Field(default="qwen2.5:14b", description="LLM model name")
    LLM_BASE_URL: str = Field(default="", description="LLM API base URL")
    LLM_API_KEY: str = Field(default="", description="LLM API key")
    LLM_TEMPERATURE: float = Field(default=0.7, description="LLM temperature")
    LLM_MAX_TOKENS: int = Field(default=2000, description="LLM max tokens")
    
    # RAG (Retrieval-Augmented Generation)
    RAG_KB_DIR: Path = Field(default=Path("rag/kb"), description="RAG knowledge base directory")
    RAG_DATASET_DIR: Path = Field(default=Path("rag/dataset"), description="RAG dataset directory")
    RAG_EMBED_MODEL: str = Field(default="bge-m3:latest", description="Embedding model")
    RAG_CHUNK_SIZE: int = Field(default=800, description="Chunk size for text splitting")
    RAG_CHUNK_OVERLAP: int = Field(default=100, description="Chunk overlap")
    
    # ==================== Report Generation ====================
    DEFAULT_REPORT_TEMPLATE: str = Field(
        default="56474CC8AB1E4E79A4220605F8770FFA.tpl",
        description="Default FastReport template file"
    )
    FASTREPORT_ASSEMBLY: Optional[str] = Field(
        default=None,
        description="Path to FastReport assembly file"
    )
    
    # ==================== Treatment Rules ====================
    TREATMENT_RULES_FILE: Path = Field(
        default=Path("config/treatment_rules.yaml"),
        description="Treatment rules configuration file"
    )
    
    # ==================== Logging ====================
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format"
    )
    LOG_TO_FILE: bool = Field(default=True, description="Write logs to file")
    LOG_RETENTION_DAYS: int = Field(default=30, description="Log file retention days")
    
    # ==================== Security ====================
    SECRET_KEY: str = Field(default="change-me-in-production", description="Secret key for sessions/JWT")
    ALLOWED_HOSTS: list[str] = Field(default=["*"], description="Allowed hosts")
    CORS_ORIGINS: list[str] = Field(default=["*"], description="CORS allowed origins")
    
    # ==================== Performance ====================
    REDIS_ENABLED: bool = Field(default=False, description="Enable Redis for caching")
    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_DB: int = Field(default=0, description="Redis database")

    # ==================== Go Service Gateway ====================
    ENABLE_GO_REPORT_PROXY: bool = Field(
        default=False,
        description="Enable proxying /reports APIs to Go report-file-service",
    )
    GO_REPORT_SERVICE_URL: str = Field(
        default="http://report-file-service:8088",
        description="Base URL of report-file-service",
    )
    GO_REPORT_HEALTH_PATH: str = Field(
        default="/healthz",
        description="Health check path for report-file-service",
    )
    GO_REPORT_PROXY_FAIL_OPEN: bool = Field(
        default=True,
        description="Fallback to local Python reports implementation when Go proxy is unavailable",
    )
    ENABLE_GO_PLATFORM_PROXY: bool = Field(
        default=False,
        description="Enable proxying /platform/summary API to Go service",
    )
    GO_PLATFORM_SERVICE_URL: str = Field(
        default="http://report-file-service:8088",
        description="Base URL of Go platform service",
    )
    GO_PLATFORM_HEALTH_PATH: str = Field(
        default="/healthz",
        description="Health check path for Go platform service",
    )
    GO_PLATFORM_PROXY_FAIL_OPEN: bool = Field(
        default=True,
        description="Fallback to local Python platform implementation when Go proxy is unavailable",
    )
    
    # Pydantic Settings Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
    
    @field_validator("STORAGE_ROOT", mode="before")
    @classmethod
    def resolve_storage_root(cls, v: str | Path) -> Path:
        """Resolve storage root to absolute path."""
        path = Path(v)
        if not path.is_absolute():
            # Relative to project root (core/config.py is one level deep)
            project_root = Path(__file__).resolve().parents[1]
            path = project_root / path
        return path
    
    def ensure_directories(self) -> None:
        """Create all necessary directories if they don't exist."""
        directories = [
            self.DATA_DIR,
            self.REPORTS_DIR,
            self.LOGS_DIR,
            self.CACHE_DIR,
            self.UPLOADS_DIR,
            self.EMR_DIR,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENVIRONMENT == Environment.DEVELOPMENT
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT == Environment.PRODUCTION
    
    @property
    def is_test(self) -> bool:
        """Check if running in test mode."""
        return self.ENVIRONMENT == Environment.TEST


@lru_cache()
def get_settings() -> Settings:
    """
    Get application settings (singleton pattern).
    
    Returns:
        Settings instance configured for current environment.
    """
    settings = Settings()
    settings.ensure_directories()
    return settings


# Convenience exports
settings = get_settings()

__all__ = ["Settings", "Environment", "get_settings", "settings"]
