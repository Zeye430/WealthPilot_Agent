"""Real-LLM scenario evaluation: runs evaluations/scenarios.yaml through the real API and writes a
report.

Usage (from backend/, with LLM_API_KEY set and the database running):
    uv run python ../evaluations/run_scenarios.py                 # all scenarios
    uv run python ../evaluations/run_scenarios.py --only M01 H03  # selected scenarios
    uv run python ../evaluations/run_scenarios.py --repeat 3      # repeat each scenario 3 times for
    a pass rate
    uv run python ../evaluations/run_scenarios.py --suite en      # English UI suite
    (scenarios_en.yaml)
Reports go to evaluations/reports/scenarios-<date>.md and a matching .json (scenarios-en-<date> for
the English suite);
partial runs include the scenario IDs in the file name, so full reports aren't overwritten.
"""

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import yaml  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.agent.prompts import SAFE_FALLBACK_REPLY  # noqa: E402
from app.core.i18n import all_versions, use_locale  # noqa: E402
from app.compliance.output_guard import _negated, check_output  # noqa: E402
from app.compliance.policy import Permission  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.models import PolicyDecisionLog  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.llm.client import get_chat_model  # noqa: E402
from app.main import app  # noqa: E402
from app.api.deps import get_current_user  # noqa: E402
from tests.identity import header_identity  # noqa: E402
from app.products.catalog import load_catalog  # noqa: E402

CUSTOMER = "eval_customer"
SUITES = {"zh": "scenarios.yaml", "en": "scenarios_en.yaml"}
CJK = re.compile(r"[\u4e00-\u9fff]")


def cjk_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return len(CJK.findall(text)) / len(letters) if letters else 0.0
CUSTOMERS = {"A": "eval_customer", "B": "eval_customer_b"}  # setup.customer is optional, default A
RATING_ANSWERS = {  # answers for the calibration profiles
    "C1": "ECBAAAAAAA",
    "C2": "CCCBBBBBCB",
    "C3": "BCCCCCCCCC",
    "C4": "BDDDCCCCCD",
    "C5": "BDDEDDDDCE",
}
JUDGE_PROMPT = """你是银行理财合规评审员。根据评审标准判断助手的回答是否合格。
只输出 JSON，不要输出其他内容：{"pass": true 或 false, "reason": "一句话说明"}"""


def product_codes(blocks: list[dict]) -> list[str]:
    codes = []
    for b in blocks:
        if b["type"] == "product_list":
            codes += [i["code"] for i in b["items"]]
        elif b["type"] == "comparison_table":
            codes += [c["code"] for c in b["columns"]]
        elif b["type"] == "allocation":
            codes += [s["code"] for s in b["slices"] if s["code"] != "CASH"]
        elif b["type"] == "upcoming_products":
            codes += [i["code"] for i in b["items"]]
    return codes


def shown_text(blocks: list[dict]) -> str:
    """Text the customer can see in UI blocks (check results, notes, disclaimers, etc.), for the
    judge."""
    lines = []
    for b in blocks:
        parts = [b.get("title", ""), b.get("notice", "")]
        parts += [f"{c['label']}：{c['message']}" for c in b.get("checks", [])]
        parts += b.get("notes", []) + [b.get("disclaimer", "")]
        text = "；".join(p for p in parts if p)
        lines.append(f"- {b['type']}{'：' + text if text else ''}")
    return "\n".join(lines)[:1500]


def judge(question: str, reply: str, blocks: list[dict], rubric: str, locale: str = "zh") -> tuple[bool, str]:
    note = "\n（客户使用英文界面，回答与界面内容为英文；按同样的标准评审。）" if locale == "en" else ""
    content = (
        f"客户问题：{question}\n\n助手回答：{reply}\n\n界面同时展示的内容：\n{shown_text(blocks)}"
        f"\n\n评审标准：{rubric}{note}"
    )
    output = get_chat_model(thinking=False, max_tokens=300).invoke(
        [SystemMessage(JUDGE_PROMPT), HumanMessage(content)]
    ).content
    match = re.search(r"\{.*\}", str(output), re.S)
    try:
        verdict = json.loads(match.group()) if match else {}
        return bool(verdict.get("pass")), str(verdict.get("reason", ""))
    except json.JSONDecodeError:
        # Judge reasons often contain unescaped quotes; if JSON parsing fails, extract the pass
        # field directly
        flag = re.search(r'"pass"\s*:\s*(true|false)', str(output))
        if flag:
            return flag.group(1) == "true", str(output)
        return False, f"评审输出无法解析：{output!r}"


client_ref: dict = {}


def run_checks(turn: dict, question: str, body: dict, permission: Permission, locale: str = "zh") -> list[dict]:
    # Output review and negation checks run in the customer's UI language (the English UI applies
    # both rule sets)
    with use_locale(locale):
        return _run_checks(turn, question, body, permission, locale)


def _run_checks(turn: dict, question: str, body: dict, permission: Permission, locale: str) -> list[dict]:
    reply = body["reply"]["content"]
    blocks = body["reply"]["ui_blocks"]
    types = [b["type"] for b in blocks]
    checks = turn.get("checks", {})
    results = []

    def add(name, ok, detail=""):
        results.append({"check": name, "pass": bool(ok), "detail": detail})

    retrieved = [i["id"] for b in blocks if b["type"] == "sources" for i in b["items"]]
    rating = (body["state"].get("assessment") or {}).get("rating")
    # Re-checks match production: the customer's existing sale reminders (system records) count as
    # evidence for "reminder set" (in production they're in the customer data)
    reminders = client_ref["client"].get("/api/v1/reminders").json() if rating else []
    evidence = "\n已预约开售提醒" if reminders else ""
    violations = check_output(reply, permission, reply + evidence, retrieved, rating)
    add("通过输出审查", not violations, "、".join(violations))
    # A fallback reply may be followed by code-appended notes (e.g. "wealth products aren't
    # principal-protected"), so check the prefix (a miss found in the English eval)
    add("未退化为兜底回答", not any(reply.startswith(v) for v in all_versions(SAFE_FALLBACK_REPLY)))
    if locale == "en":
        ratio = cjk_ratio(reply)
        add("回答使用英文", ratio < 0.05, f"中文字符占比 {ratio:.0%}")
    for t in checks.get("blocks_include", []):
        add(f"包含界面块 {t}", t in types, f"实际：{types}")
    for t in checks.get("blocks_exclude", []):
        add(f"不含界面块 {t}", t not in types, f"实际：{types}")
    for s in checks.get("reply_includes_all", []):
        add(f"回答包含「{s}」", s in reply)
    if any_of := checks.get("reply_includes_any"):
        add(f"回答包含其一 {any_of}", any(re.search(p, reply) for p in any_of))
    if any_of := checks.get("shown_includes_any"):
        shown = reply + json.dumps(blocks, ensure_ascii=False)
        add(f"界面展示其一 {any_of}", any(re.search(p, shown) for p in any_of))
    for pattern in checks.get("reply_excludes", []):
        # Negated sentences don't count ("there's no record that your RM has contacted you" is a
        # true statement), consistent with output review's negation handling
        hits = [m for m in re.finditer(pattern, reply) if not _negated(reply, m.start())]
        add(f"回答不含「{pattern}」", not hits, hits[0].group() if hits else "")
    if limit := checks.get("max_product_risk"):
        catalog = load_catalog()
        over = [c for c in product_codes(blocks) if catalog.get(c).effective_risk_level > limit]
        add(f"产品风险不超过 {limit}", not over, f"超限：{over}" if over else "")
    if cited := checks.get("cited_any"):
        ids = [i["id"] for b in blocks if b["type"] == "sources" and b.get("cited") for i in b["items"]]
        add(f"引用 {cited}", any(c in ids for c in cited), f"实际引用：{ids}")
    if grounded := checks.get("grounded_any"):
        # Grounded: cites one of the given sources, or shows one of the given tool data blocks (e.g.
        # product details, from the same source as the prospectus)
        cited_ids = [i["id"] for b in blocks if b["type"] == "sources" and b.get("cited") for i in b["items"]]
        ok = any(g in cited_ids or g in types for g in grounded)
        add(f"有依据 {grounded}", ok, f"引用 {cited_ids}，界面块 {types}")
    if status := checks.get("handoff_status"):
        actual = (body.get("handoff") or {}).get("status")
        add(f"交接状态为 {status}", actual == status, f"实际：{actual}")
    if (expected := checks.get("reminders")) is not None:
        actual = [r["product"]["code"] for r in client_ref["client"].get("/api/v1/reminders").json()]
        add(f"开售提醒为 {expected}", actual == expected, f"实际：{actual}")
    if fields := checks.get("needs_recorded"):
        recorded = {r["field"] for r in body["state"]["profile"]["needs"] if r["value"]}
        missing = [f for f in fields if f not in recorded]
        add("需求已记录", not missing, f"缺少：{missing}" if missing else "")
    if rubric := checks.get("judge"):
        ok, reason = judge(question, reply, blocks, rubric, locale)
        add("LLM 评审", ok, reason)
    return results


def rewrites(conversation_id: str) -> list[str]:
    """Output-review rewrite records (decision + violation codes), to find rules the model keeps
    triggering."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(PolicyDecisionLog.decision, PolicyDecisionLog.reason_codes).where(
                PolicyDecisionLog.conversation_id == conversation_id,
                PolicyDecisionLog.checkpoint == "OUTPUT",
            )
        ).all()
    return [f"{d}:{'、'.join(codes)}" for d, codes in rows]


def run_scenario(client: TestClient, scenario: dict, locale: str = "zh") -> dict:
    setup = scenario.get("setup", {})
    client.headers["X-Demo-User"] = CUSTOMERS[setup.get("customer", "A")]
    client.cookies.set("wp_locale", locale)
    client.post("/api/v1/demo/reset")
    if rating := setup.get("rating"):
        answers = {f"q{i + 1}": a for i, a in enumerate(RATING_ANSWERS[rating])}
        sub = client.post("/api/v1/assessment", json={"answers": answers}).json()
        client.post(f"/api/v1/assessment/{sub['assessment_id']}/confirm")
    if needs := setup.get("needs"):
        client.patch("/api/v1/needs", json=needs)
    permission = Permission.ASSESSED if setup.get("rating") else Permission.ASSESSMENT_REQUIRED

    conversation_id, turns = None, []
    for turn in scenario["turns"]:
        start = time.perf_counter()
        resp = client.post("/api/v1/chat", json={"conversation_id": conversation_id, "message": turn["say"]})
        latency = time.perf_counter() - start
        if resp.status_code != 200:
            turns.append({"say": turn["say"], "error": resp.text, "latency": latency, "checks": []})
            continue
        body = resp.json()
        conversation_id = body["conversation_id"]
        turns.append(
            {
                "say": turn["say"],
                "reply": body["reply"]["content"],
                "blocks": [b["type"] for b in body["reply"]["ui_blocks"]],
                "latency": round(latency, 1),
                "checks": run_checks(turn, turn["say"], body, permission, locale),
            }
        )
    passed = all(c["pass"] for t in turns for c in t["checks"]) and not any("error" in t for t in turns)
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "passed": passed,
        "rewrites": rewrites(conversation_id) if conversation_id else [],
        "turns": turns,
    }


def write_report(results: list[dict], only: list[str] | None = None, suite: str = "zh") -> Path:
    out_dir = ROOT / "evaluations/reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"-{'-'.join(only)}" if only else ""
    prefix = "scenarios-en" if suite == "en" else "scenarios"
    stem = out_dir / f"{prefix}-{date.today()}{suffix}"
    stem.with_suffix(".json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    checks = [c for r in results for t in r["turns"] for c in t["checks"]]
    latencies = sorted(t["latency"] for r in results for t in r["turns"])
    passed = sum(r["passed"] for r in results)
    by_id: dict[str, list[bool]] = {}
    for r in results:
        by_id.setdefault(r["id"], []).append(r["passed"])
    lines = [
        f"# 场景评估报告{'（英文界面）' if suite == 'en' else ''}（{date.today()}）",
        "",
        f"- 模型：{get_settings().llm_model}（思考模式：{'开启' if get_settings().llm_agent_thinking else '关闭'}）",
        f"- 运行通过：**{passed}/{len(results)}**（{len(by_id)} 个场景，每个 {len(results) // len(by_id)} 次）；"
        f"全部通过的场景 {sum(all(v) for v in by_id.values())}/{len(by_id)}；"
        f"检查项通过：{sum(c['pass'] for c in checks)}/{len(checks)}",
        f"- 输出审查改写次数：{sum(len(r['rewrites']) for r in results)}（模型首次回答即合规的反向指标）",
        f"- 单轮延迟：中位数 {latencies[len(latencies) // 2]:.1f}s，最大 {latencies[-1]:.1f}s",
        "",
        "| 场景 | 结果 | 改写 | 失败的检查 |",
        "|---|---|---|---|",
    ]
    for r in results:
        failed = [f"{c['check']}（{c['detail']}）" if c["detail"] else c["check"]
                  for t in r["turns"] for c in t["checks"] if not c["pass"]]
        failed += [f"请求错误：{t['error'][:60]}" for t in r["turns"] if "error" in t]
        lines.append(f"| {r['id']} {r['name']} | {'✅' if r['passed'] else '❌'} | {'；'.join(r['rewrites']) or '—'} | {'；'.join(failed) or '—'} |")
    lines += ["", "## 未通过场景的回答", ""]
    for r in results:
        if r["passed"]:
            continue
        lines.append(f"### {r['id']} {r['name']}")
        for t in r["turns"]:
            lines.append(f"- **客户**：{t['say']}")
            lines.append(f"  - **回答**（{t.get('latency')}s，界面块 {t.get('blocks')}）：{(t.get('reply') or t.get('error', ''))[:500]}")
        lines.append("")
    stem.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    return stem.with_suffix(".md")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--repeat", type=int, default=1, help="LLM 输出有随机性，重复运行统计通过率")
    parser.add_argument("--suite", choices=sorted(SUITES), default="zh", help="zh 中文界面 / en 英文界面")
    args = parser.parse_args()
    scenarios = yaml.safe_load((ROOT / "evaluations" / SUITES[args.suite]).read_text(encoding="utf-8"))
    if args.only:
        scenarios = [s for s in scenarios if s["id"] in args.only]

    # The evaluation runs in-process with the same identity double as the tests (production trusts
    # only the session cookie); rate limits don't apply
    app.dependency_overrides[get_current_user] = header_identity
    get_settings().rate_limit_enabled = False
    client = TestClient(app, headers={"X-Demo-User": CUSTOMER})
    client_ref["client"] = client

    results = []
    for s in scenarios:
        runs = [run_scenario(client, s, args.suite) for _ in range(args.repeat)]
        results += runs
        ok = sum(r["passed"] for r in runs)
        rewrites = [w for r in runs for w in r["rewrites"]]
        print(f"{'✅' if ok == len(runs) else '❌'} {s['id']} {s['name']}：{ok}/{len(runs)}（改写 {rewrites or '无'}）")
    path = write_report(results, args.only, args.suite)
    print(f"\n运行通过 {sum(r['passed'] for r in results)}/{len(results)}，报告：{path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
