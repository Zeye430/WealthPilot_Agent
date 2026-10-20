"""Load test: send concurrent chat requests to a running backend and measure throughput, latency
percentiles and errors.

Two modes (both should use a separate database, never the development / demo database):
1. System only (do this first): start the backend with LLM_PROVIDER=fake and a fixed model latency
(1.5 s by default);
   it measures system overhead (thread pool, DB pool, review, writes) with no model calls or cost.
2. Real model, low concurrency: the backend uses the real model; keep concurrency and request counts
small (it costs money and the provider rate-limits).

The backend needs rate limiting off (RATE_LIMIT_ENABLED=false) and a customer account that can sign
in.
Each request carries X-Request-ID=load-<n>, so turn_metrics can be filtered or cleaned up by prefix
afterwards.

Usage (from backend/):
    uv run python ../scripts/load_test.py --base http://localhost:8100 --levels 1 5 10 20 40 \\
        --requests 40 --username load --label fake-1.5s
Reports go to evaluations/reports/load-<date>-<label>.md and .json.
"""

import argparse
import asyncio
import json
import statistics
import time
import uuid
from collections import Counter
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = {
    "mixed": [
        "什么是业绩比较基准？",
        "100万按每年5%复利10年是多少？",
        "理财产品会亏本金吗？",
        "七日年化收益率是什么意思？",
    ],
    # For real-model load tests: only the calculator tool, no knowledge index needed (the separate
    # test database has none)
    "calc": [
        "100万按每年5%复利10年是多少？",
        "50万按每年3%复利5年是多少？",
        "20万每年4%单利3年后是多少？",
    ],
}


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


async def login(client: httpx.AsyncClient, username: str, password: str) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    resp.raise_for_status()


async def run_level(
    base: str,
    cookies: httpx.Cookies,
    concurrency: int,
    total: int,
    timeout: float,
    questions: list[str],
) -> dict:
    """concurrency virtual users send total requests in all; each user keeps its own conversation
    (history grows turn by turn)."""
    latencies: list[float] = []
    statuses: Counter[str] = Counter()
    queue: asyncio.Queue[int] = asyncio.Queue()
    for i in range(total):
        queue.put_nowait(i)

    async def user(n: int) -> None:
        conversation_id = None
        async with httpx.AsyncClient(base_url=base, cookies=cookies, timeout=timeout) as client:
            while True:
                try:
                    i = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                start = time.perf_counter()
                try:
                    resp = await client.post(
                        "/api/v1/chat",
                        json={"message": questions[i % len(questions)], "conversation_id": conversation_id},
                        headers={"X-Request-ID": f"load-{uuid.uuid4().hex[:20]}"},
                    )
                    statuses[str(resp.status_code)] += 1
                    if resp.status_code == 200:
                        conversation_id = resp.json()["conversation_id"]
                        latencies.append(time.perf_counter() - start)
                except httpx.TimeoutException:
                    statuses["timeout"] += 1
                except httpx.HTTPError as exc:
                    statuses[type(exc).__name__] += 1

    started = time.perf_counter()
    await asyncio.gather(*(user(n) for n in range(concurrency)))
    elapsed = time.perf_counter() - started
    ok = statuses.get("200", 0)
    return {
        "concurrency": concurrency,
        "requests": total,
        "ok": ok,
        "errors": {k: v for k, v in statuses.items() if k != "200"},
        "error_rate": round(1 - ok / total, 4) if total else 0,
        "throughput_rps": round(ok / elapsed, 2) if elapsed else 0,
        "p50_s": round(percentile(latencies, 0.5), 2),
        "p95_s": round(percentile(latencies, 0.95), 2),
        "p99_s": round(percentile(latencies, 0.99), 2),
        "max_s": round(max(latencies), 2) if latencies else 0,
        "mean_s": round(statistics.mean(latencies), 2) if latencies else 0,
        "elapsed_s": round(elapsed, 1),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8100")
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 5, 10, 20, 40])
    parser.add_argument("--requests", type=int, default=40, help="每个并发级别的请求总数")
    parser.add_argument("--username", default="load")
    parser.add_argument("--password", default="wealthpilot-demo")
    parser.add_argument("--timeout", type=float, default=130, help="客户端超时，略大于前端代理的 120 秒")
    parser.add_argument("--label", default="run")
    parser.add_argument("--note", default="", help="写入报告的测试条件说明")
    parser.add_argument("--questions", choices=sorted(QUESTIONS), default="mixed")
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base, timeout=30) as client:
        await login(client, args.username, args.password)
        await client.post("/api/v1/demo/reset")
        ready = (await client.get("/health/ready")).json()
        cookies = client.cookies

    results = []
    for level in args.levels:
        r = await run_level(
            args.base, cookies, level, max(args.requests, level), args.timeout, QUESTIONS[args.questions]
        )
        results.append(r)
        print(
            f"并发 {level:>3}：成功 {r['ok']}/{r['requests']}，吞吐 {r['throughput_rps']} 次/秒，"
            f"P50 {r['p50_s']}s，P95 {r['p95_s']}s，最大 {r['max_s']}s，错误 {r['errors'] or '无'}",
            flush=True,
        )

    async with httpx.AsyncClient(base_url=args.base, cookies=cookies, timeout=30) as client:
        await client.post("/api/v1/demo/reset")

    out = ROOT / "evaluations/reports"
    stem = out / f"load-{date.today()}-{args.label}"
    payload = {"label": args.label, "note": args.note, "server": ready, "results": results}
    stem.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# 压测报告：{args.label}（{date.today()}）",
        "",
        f"- 条件：{args.note or '—'}",
        f"- 后端：模型 {ready['checks']['llm'].get('model')}（provider={ready['checks']['llm'].get('provider')}），"
        f"版本 {ready.get('version')}（{ready.get('git_sha')}）",
        f"- 每个并发级别 {args.requests} 个请求；虚拟用户沿用各自的会话，历史逐轮增长",
        "",
        "| 并发 | 成功 / 请求 | 错误 | 吞吐（次/秒） | P50 | P95 | P99 | 最大 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['concurrency']} | {r['ok']}/{r['requests']} | {r['errors'] or '—'} | {r['throughput_rps']} "
            f"| {r['p50_s']}s | {r['p95_s']}s | {r['p99_s']}s | {r['max_s']}s |"
        )
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告：{stem.with_suffix('.md').relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
