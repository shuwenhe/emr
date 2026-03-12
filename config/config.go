package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

type Config struct {
	Addr             string
	ReportsDir       string
	CacheTTL         time.Duration
	MySQLConfigPath  string
	MySQLDSN         string
	PythonBackendURL string
}

func Load() (Config, error) {
	cfg := Config{
		Addr:             getEnv("RFS_ADDR", ":8088"),
		ReportsDir:       getEnv("RFS_REPORTS_DIR", "../../storage/reports"),
		CacheTTL:         5 * time.Minute,
		MySQLConfigPath:  getEnv("RFS_MYSQL_CONFIG_PATH", "config/mysql.yaml"),
		MySQLDSN:         getEnv("RFS_MYSQL_DSN", ""),
		PythonBackendURL: getEnv("RFS_PYTHON_BACKEND_URL", ""),
	}

	if ttlRaw := os.Getenv("RFS_CACHE_TTL_SECONDS"); ttlRaw != "" {
		ttlSeconds, err := strconv.Atoi(ttlRaw)
		if err != nil || ttlSeconds <= 0 {
			return Config{}, fmt.Errorf("invalid RFS_CACHE_TTL_SECONDS: %q", ttlRaw)
		}
		cfg.CacheTTL = time.Duration(ttlSeconds) * time.Second
	}

	return cfg, nil
}

func getEnv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
