部署步骤（systemd）

1. 在服务器上准备 Python 环境：

```bash
cd /app/ai/emr/ingestion
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 将单元文件复制并启用 systemd：

```bash
sudo cp /app/ai/emr/deploy/emr.service /etc/systemd/system/emr.service
sudo systemctl daemon-reload
sudo systemctl enable --now emr.service
sudo journalctl -u emr -f
```

部署步骤（使用 docker-compose）

```bash
cd /app/ai/emr/deploy
sudo docker-compose up -d --build
```

配置 nginx（将我添加的配置文件部署到 nginx）：

```bash
# 将配置文件移动到 nginx sites-available
sudo cp /app/ai/config/nginx-emr.conf /etc/nginx/sites-available/emr
sudo ln -sf /etc/nginx/sites-available/emr /etc/nginx/sites-enabled/emr
sudo nginx -t
sudo systemctl reload nginx
```

要点：
- 上述 nginx 配置会把 `/fto/` 路由转发到 `http://127.0.0.1:8080/fto/`（不改变现有 fto 服务）。
- 将根路径 `/` 转发到 `http://127.0.0.1:8000/`，假定 `emr` 在本地 8000 端口运行。

验证命令：

```bash
# 检查 emr（应返回首页或健康检查）
curl -I http://8.140.241.141/

# 检查 fto（应返回 200）
curl -I http://8.140.241.141/fto/

# 更详细健康检查（如果存在）
curl -sS http://8.140.241.141/fto/api/health
curl -sS http://8.140.241.141/api/health
```

故障排查提示：
- 如果 `/fto` 返回 502，请确保 fto 服务在本机的 8080 端口运行并监听 `127.0.0.1` 或 `0.0.0.0`。
- 如果根路径返回 502，请检查 `emr` 是否在 8000 端口运行。
