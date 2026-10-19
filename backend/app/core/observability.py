"""可观测性基础：请求编号、结构化日志、进程内指标（Prometheus 文本格式）。

- 每个请求一个编号（X-Request-ID）：日志、对话指标、响应头都带上它，
  客户反馈问题时凭编号即可定位整条链路。
  上游（负载均衡）传入合法编号时沿用，否则新生成。
- 日志：本地开发为可读文本；部署时 LOG_FORMAT=json，每行一个 JSON，便于云平台检索与告警。
- 指标：不引入第三方依赖，按 Prometheus 文本格式输出计数器、直方图、仪表；单进程内存保存，
  重启清零（长期趋势看数据库中的 turn_metrics，见 app/ops/）。
  多实例部署时由 Prometheus 分别抓取各实例。
"""

import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return _request_id.get()


# ---------- 指标 ----------

LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120)

METRICS_HELP = {
    "wealthpilot_http_requests_total": ("counter", "HTTP 请求数"),
    "wealthpilot_http_request_duration_seconds": ("histogram", "HTTP 请求耗时"),
    "wealthpilot_chat_turns_total": ("counter", "对话轮次，按结果分类"),
    "wealthpilot_chat_turn_duration_seconds": ("histogram", "单轮对话耗时"),
    "wealthpilot_llm_calls_total": ("counter", "模型调用次数，按用途与结果分类"),
    "wealthpilot_llm_call_duration_seconds": ("histogram", "单次模型调用耗时"),
    "wealthpilot_llm_tokens_total": ("counter", "模型 token 用量"),
    "wealthpilot_llm_cost_usd_total": ("counter", "模型费用估算（美元，按配置单价）"),
    "wealthpilot_tool_calls_total": ("counter", "工具调用次数"),
    "wealthpilot_guard_decisions_total": ("counter", "输出审查结论"),
    "wealthpilot_guard_violations_total": ("counter", "输出审查命中的规则"),
    "wealthpilot_llm_circuit_state": ("gauge", "模型熔断状态：0 关闭 / 1 半开 / 2 打开"),
}


def _key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((k, str(v)) for k, v in labels.items()))


class Metrics:
    """线程安全的进程内指标。接口与 prometheus_client 相近，需要时可直接替换。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, dict[tuple, float]] = defaultdict(dict)
        self._hist: dict[str, dict[tuple, list[float]]] = defaultdict(dict)

    def inc(self, name: str, labels: dict[str, str] | None = None, value: float = 1) -> None:
        key = _key(labels or {})
        with self._lock:
            self._values[name][key] = self._values[name].get(key, 0) + value

    def set(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._values[name][_key(labels or {})] = value

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = _key(labels or {})
        with self._lock:
            # 每个桶的累计计数 + 总和 + 总数
            hist = self._hist[name].setdefault(key, [0.0] * (len(LATENCY_BUCKETS) + 2))
            for i, bound in enumerate(LATENCY_BUCKETS):
                if value <= bound:
                    hist[i] += 1
            hist[-2] += value
            hist[-1] += 1

    def value(self, name: str, labels: dict[str, str] | None = None) -> float:
        with self._lock:
            return self._values[name].get(_key(labels or {}), 0)

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, (kind, help_text) in METRICS_HELP.items():
                lines += [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}"]
                for key, v in sorted(self._values.get(name, {}).items()):
                    lines.append(f"{name}{_fmt(key)} {v:g}")
                for key, h in sorted(self._hist.get(name, {}).items()):
                    for bound, count in zip(LATENCY_BUCKETS, h, strict=False):
                        lines.append(f"{name}_bucket{_fmt(key, le=f'{bound:g}')} {count:g}")
                    lines.append(f"{name}_bucket{_fmt(key, le='+Inf')} {h[-1]:g}")
                    lines.append(f"{name}_sum{_fmt(key)} {h[-2]:.6f}")
                    lines.append(f"{name}_count{_fmt(key)} {h[-1]:g}")
        return "\n".join(lines) + "\n"


def _fmt(key: tuple, **extra: str) -> str:
    pairs = [*key, *extra.items()]
    if not pairs:
        return ""
    inner = ",".join(f'{k}="{str(v).replace(chr(34), "")}"' for k, v in pairs)
    return "{" + inner + "}"


METRICS = Metrics()


# ---------- 请求编号中间件 ----------

access_logger = logging.getLogger("wealthpilot.access")


class RequestContextMiddleware:
    """纯 ASGI 中间件：分配请求编号、记录访问日志与 HTTP 指标。

    指标按路由模板（/api/v1/products/{code}）而不是实际路径归类，避免产品代码等把标签数量撑爆。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(REQUEST_ID_HEADER.lower().encode())
        candidate = incoming.decode(errors="ignore") if incoming else ""
        request_id = candidate if _VALID_ID.match(candidate) else uuid.uuid4().hex
        token = _request_id.set(request_id)
        start = time.perf_counter()
        status = 500

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            elapsed = time.perf_counter() - start
            route = getattr(scope.get("route"), "path", None) or "unmatched"
            method = scope.get("method", "")
            METRICS.inc(
                "wealthpilot_http_requests_total",
                {"method": method, "route": route, "status": str(status)},
            )
            METRICS.observe("wealthpilot_http_request_duration_seconds", elapsed, {"route": route})
            if route != "/health":
                access_logger.info(
                    "%s %s %s %.0fms",
                    method,
                    route,
                    status,
                    elapsed * 1000,
                    extra={"status": status, "duration_ms": round(elapsed * 1000)},
                )
            _request_id.reset(token)


# ---------- 日志 ----------

_STANDARD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """每行一个 JSON：时间、级别、来源、消息、请求编号，以及 extra 中的业务字段。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload |= {k: v for k, v in record.__dict__.items() if k not in _STANDARD}
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


TEXT_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s %(message)s"


def configure_logging(log_format: str, filters: list[logging.Filter]) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter() if log_format == "json" else logging.Formatter(TEXT_FORMAT)
    )
    handler.addFilter(RequestIdFilter())
    for f in filters:
        handler.addFilter(f)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
