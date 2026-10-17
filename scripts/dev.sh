#!/usr/bin/env bash
# 一键启动本地开发环境：数据库 + 后端 + 前端。按 Ctrl+C 同时停止前后端（数据库保持运行）。
# 用法（在仓库根目录）：./scripts/dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

[ -f .env ] || { echo "✗ 缺少 .env：请先执行 cp .env.example .env 并填写 LLM_API_KEY"; exit 1; }
docker info >/dev/null 2>&1 || { echo "✗ Docker 未运行：请先打开 Docker Desktop"; exit 1; }
for port in 8000 3000; do
  if lsof -ti tcp:$port >/dev/null 2>&1; then
    echo "✗ 端口 $port 已被占用：可能已有前端或后端在运行，请先在原终端按 Ctrl+C 停止"
    exit 1
  fi
done

echo "▶ 启动数据库"
docker compose up -d db >/dev/null
until docker compose exec -T db pg_isready -U wealthpilot >/dev/null 2>&1; do sleep 1; done

echo "▶ 同步依赖与数据库迁移"
(cd backend && uv sync -q && uv run alembic upgrade head)
[ -d frontend/node_modules ] || (cd frontend && npm install)

# 退出时结束本脚本启动的所有子进程
trap 'trap - EXIT; kill 0' INT TERM EXIT

echo "▶ 后端 http://localhost:8000（接口文档 /docs）"
(cd backend && uv run uvicorn app.main:app --reload --port 8000) &
echo "▶ 前端 http://localhost:3000"
(cd frontend && npm run dev -- --port 3000) &

wait
