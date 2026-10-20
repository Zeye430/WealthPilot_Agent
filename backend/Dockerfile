# 构建上下文为仓库根目录（docker compose 中 context: ..），以便把 data/ 一起打进镜像：
# 产品目录、知识库、权益与客户演示数据都在 data/ 下，代码按「仓库根目录/data」读取（容器内为 /data）。
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./
COPY data/ /data/
EXPOSE 8000
# 访问日志由应用自己输出（带请求编号；生产中为 JSON 格式），关闭 uvicorn 的纯文本访问日志避免重复
CMD ["sh", "-c", "uv run --no-dev alembic upgrade head && uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
