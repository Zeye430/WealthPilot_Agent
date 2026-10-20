"""Turn metrics: written to turn_metrics every turn and aggregated for the ops dashboard.

A failed write is only logged and never affects the customer's reply: observability must not become
a new point of failure.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.observability import METRICS, current_request_id
from app.db.models import TurnMetric
from app.db.session import get_engine
from app.llm.telemetry import TurnTelemetry

logger = logging.getLogger(__name__)

# What each outcome means for the customer: the first three are normal completions; the rest need
# attention
NORMAL_OUTCOMES = ("ANSWERED", "OUT_OF_SCOPE", "ASSESSMENT_REQUIRED")
DEGRADED_OUTCOMES = ("FALLBACK", "TOOL_LIMIT", "TIMEOUT")
FAILED_OUTCOMES = ("ERROR", "BREAKER_OPEN")


@dataclass
class TurnRecord:
    outcome: str
    latency_s: float
    locale: str
    conversation_id: str | None = None
    permission: str | None = None
    intent: str | None = None
    guard_decision: str | None = None
    violation_codes: list[str] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)  # [{"name", "status"}]


def record_turn(record: TurnRecord, telemetry: TurnTelemetry | None = None) -> None:
    telemetry = telemetry or TurnTelemetry()
    _publish_metrics(record, telemetry)
    try:
        with sessionmaker(bind=get_engine())() as db:
            db.add(
                TurnMetric(
                    request_id=current_request_id(),
                    conversation_id=record.conversation_id,
                    locale=record.locale,
                    permission=record.permission,
                    intent=record.intent,
                    outcome=record.outcome,
                    guard_decision=record.guard_decision,
                    violation_codes=record.violation_codes,
                    latency_ms=round(record.latency_s * 1000),
                    llm_ms=round(telemetry.llm_seconds * 1000),
                    llm_calls=len(telemetry.calls),
                    llm_errors=telemetry.errors,
                    prompt_tokens=telemetry.prompt_tokens,
                    completion_tokens=telemetry.completion_tokens,
                    cost_usd=telemetry.cost_usd(),
                    tool_calls=len(record.tools),
                    tool_errors=sum(t["status"] != "success" for t in record.tools),
                    tools=record.tools,
                    model=telemetry.model,
                )
            )
            db.commit()
    except Exception:
        logger.warning("failed to record turn metrics", exc_info=True)


def _publish_metrics(record: TurnRecord, telemetry: TurnTelemetry) -> None:
    METRICS.inc("wealthpilot_chat_turns_total", {"outcome": record.outcome})
    METRICS.observe("wealthpilot_chat_turn_duration_seconds", record.latency_s)
    for call in telemetry.calls:
        outcome = "error" if call.error else "ok"
        METRICS.inc("wealthpilot_llm_calls_total", {"role": call.role, "outcome": outcome})
        METRICS.observe(
            "wealthpilot_llm_call_duration_seconds", call.latency_s, {"role": call.role}
        )
        METRICS.inc(
            "wealthpilot_llm_tokens_total",
            {"role": call.role, "kind": "prompt"},
            call.prompt_tokens,
        )
        METRICS.inc(
            "wealthpilot_llm_tokens_total",
            {"role": call.role, "kind": "completion"},
            call.completion_tokens,
        )
    METRICS.inc("wealthpilot_llm_cost_usd_total", value=float(telemetry.cost_usd()))
    for t in record.tools:
        METRICS.inc("wealthpilot_tool_calls_total", {"tool": t["name"], "status": t["status"]})
    if record.guard_decision:
        METRICS.inc("wealthpilot_guard_decisions_total", {"decision": record.guard_decision})
    for code in record.violation_codes:
        METRICS.inc("wealthpilot_guard_violations_total", {"code": code})


# ---------- Dashboard aggregates ----------


def _rate(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def bucket_seconds(hours: int) -> int:
    """Trend chart granularity: every 5 minutes for the last hour, hourly for 24 hours, every 6
    hours for longer."""
    if hours <= 1:
        return 300
    if hours <= 24:
        return 3600
    return 6 * 3600


def overview(db: Session, now: datetime, hours: int) -> dict:
    since = now - timedelta(hours=hours)
    window = TurnMetric.created_at >= since

    p50 = func.percentile_cont(0.5).within_group(TurnMetric.latency_ms)
    p95 = func.percentile_cont(0.95).within_group(TurnMetric.latency_ms)
    row = db.execute(
        select(
            func.count(),
            p50,
            p95,
            func.max(TurnMetric.latency_ms),
            func.coalesce(func.sum(TurnMetric.prompt_tokens), 0),
            func.coalesce(func.sum(TurnMetric.completion_tokens), 0),
            func.coalesce(func.sum(TurnMetric.cost_usd), 0),
            func.coalesce(func.sum(TurnMetric.llm_calls), 0),
            func.coalesce(func.sum(TurnMetric.llm_errors), 0),
            func.coalesce(func.sum(TurnMetric.tool_calls), 0),
            func.coalesce(func.sum(TurnMetric.tool_errors), 0),
        ).where(window)
    ).one()
    (
        turns,
        lat50,
        lat95,
        lat_max,
        prompt,
        completion,
        cost,
        llm_calls,
        llm_errors,
        tools,
        tool_errors,
    ) = row

    outcomes = dict(
        db.execute(
            select(TurnMetric.outcome, func.count()).where(window).group_by(TurnMetric.outcome)
        ).all()
    )
    intents = dict(
        db.execute(
            select(TurnMetric.intent, func.count())
            .where(window, TurnMetric.intent.is_not(None))
            .group_by(TurnMetric.intent)
        ).all()
    )
    decisions = dict(
        db.execute(
            select(TurnMetric.guard_decision, func.count())
            .where(window, TurnMetric.guard_decision.is_not(None))
            .group_by(TurnMetric.guard_decision)
        ).all()
    )
    rules: Counter[str] = Counter()
    tool_stats: dict[str, Counter[str]] = {}
    for codes, used in db.execute(
        select(TurnMetric.violation_codes, TurnMetric.tools).where(window)
    ).all():
        rules.update(codes or [])
        for t in used or []:
            tool_stats.setdefault(t["name"], Counter())[t["status"]] += 1

    step = bucket_seconds(hours)
    origin = datetime(2000, 1, 1, tzinfo=UTC)
    bucket = func.date_bin(timedelta(seconds=step), TurnMetric.created_at, origin)
    rows = {
        start: (n, s50, s95, problems)
        for start, n, s50, s95, problems in db.execute(
            select(
                bucket,
                func.count(),
                p50,
                p95,
                func.count().filter(TurnMetric.outcome.not_in(NORMAL_OUTCOMES)),
            )
            .where(window)
            .group_by(bucket)
        ).all()
    }
    # Fill periods with no conversations: volume is 0 and latency is left empty (a gap in the chart
    # rather than 0 s)
    first = origin + timedelta(seconds=((since - origin).total_seconds() // step) * step)
    series = []
    start = first
    while start <= now:
        n, s50, s95, problems = rows.get(start, (0, None, None, 0))
        series.append(
            {
                "start": start.isoformat(),
                "turns": n,
                "p50_ms": round(s50) if s50 is not None else None,
                "p95_ms": round(s95) if s95 is not None else None,
                "problems": problems,
            }
        )
        start += timedelta(seconds=step)
    recent = [
        {
            "at": m.created_at.isoformat(),
            "request_id": m.request_id,
            "conversation_id": m.conversation_id,
            "locale": m.locale,
            "intent": m.intent,
            "outcome": m.outcome,
            "guard_decision": m.guard_decision,
            "violation_codes": m.violation_codes,
            "latency_ms": m.latency_ms,
            "llm_calls": m.llm_calls,
            "tokens": m.prompt_tokens + m.completion_tokens,
            "tool_errors": m.tool_errors,
        }
        for m in db.scalars(
            select(TurnMetric).where(window).order_by(TurnMetric.created_at.desc()).limit(50)
        )
    ]
    degraded = sum(outcomes.get(o, 0) for o in DEGRADED_OUTCOMES)
    failed = sum(outcomes.get(o, 0) for o in FAILED_OUTCOMES)
    cost = Decimal(cost)
    return {
        "window_hours": hours,
        "bucket_seconds": step,
        "kpis": {
            "turns": turns,
            "p50_ms": round(lat50 or 0),
            "p95_ms": round(lat95 or 0),
            "max_ms": lat_max or 0,
            "fallback_rate": _rate(outcomes.get("FALLBACK", 0), turns),
            "degraded_rate": _rate(degraded, turns),
            "error_rate": _rate(failed, turns),
            "rewrite_rate": _rate(decisions.get("REWRITE", 0) + decisions.get("REDACT", 0), turns),
            "llm_error_rate": _rate(llm_errors, llm_calls),
            "tool_error_rate": _rate(tool_errors, tools),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cost_usd": float(cost),
            "cost_per_turn_usd": float(cost / turns) if turns else 0.0,
        },
        "outcomes": outcomes,
        "intents": intents,
        "guard": {"decisions": decisions, "rules": dict(rules.most_common())},
        "tools": {name: dict(c) for name, c in sorted(tool_stats.items())},
        "series": series,
        "recent": recent,
    }
