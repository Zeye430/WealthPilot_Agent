#!/usr/bin/env bash
# One command to start local development: database + backend + frontend. Ctrl+C stops backend and frontend (the database keeps running).
# Usage (from the repo root): ./scripts/dev.sh
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

echo "▶ 同步检索索引（只重新计算有变化的内容）"
(cd backend && uv run python -W ignore ../scripts/build_index.py)

echo "▶ 检查语音识别模型（首次约下载 240MB；失败不影响启动，只是不显示麦克风按钮）"
(cd backend && uv run python -W ignore ../scripts/download_asr_model.py) || echo "  ⚠ 语音模型下载失败，可稍后运行 scripts/download_asr_model.py"
[ -d frontend/node_modules ] || (cd frontend && npm install)

# On exit, stop every child process this script started
trap 'trap - EXIT; kill 0' INT TERM EXIT

echo "▶ 后端 http://localhost:8000（接口文档 /docs）"
(cd backend && uv run uvicorn app.main:app --reload --port 8000) &
echo "▶ 前端 http://localhost:3000"
(cd frontend && npm run dev -- --port 3000) &

wait
