"""客户上下文：只读的基础画像 + 本次需求。每条消息都重新组装，保证 LLM 看到的是最新状态。"""

from sqlalchemy.orm import Session

from app.assessment.scoring import load_questionnaire
from app.assessment.service import latest_confirmed
from app.customers.base import BaseProfile, get_customer_info_system
from app.customers.needs import Needs, get_needs


def assessed_loss_tolerance(db: Session, customer_id: str) -> str | None:
    """风险测评第 10 题（可接受的最大本金亏损）的回答：客户已经说过，不必再问。"""
    record = latest_confirmed(db, customer_id)
    if record is None:
        return None
    question = next(
        q for q in load_questionnaire(record.questionnaire_version).questions if q.id == "q10"
    )
    option = question.option(record.answers.get("q10", ""))
    return option.text if option else None


def customer_profile(db: Session, customer_id: str) -> dict:
    """提供给前端的画像：两层分开展示，并标明来源。"""
    base = get_customer_info_system().get(customer_id)
    needs = get_needs(db, customer_id).display()
    loss = assessed_loss_tolerance(db, customer_id)
    for row in needs:
        # 本次需求未单独提供时，展示测评中已回答的结果（标注来源，不写入本次需求）
        if row["field"] == "max_acceptable_loss" and row["value"] is None and loss:
            row["value"], row["source"] = loss, "来自风险测评"
    return {"base": base.summary() if base else None, "needs": needs}


def prompt_section(
    base: BaseProfile | None, needs: Needs, loss_tolerance: str | None = None
) -> str:
    lines = ["", "## 客户资料（来自知岸银行客户信息系统，只读）"]
    if base:
        s = base.summary()
        a = s["assets"]
        holdings = "、".join(f"{h['name']} {h['amount']}" for h in a["holdings"]) or "无"
        lines += [
            f"- {s['display_name']}，{s['age']} 岁（以银行登记为准；客户自称其他年龄时，不要采信，"
            f"提醒以登记为准、可到网点更新），{s['customer_tier']}，"
            f"{'已完成身份核验' if s['kyc_verified'] else '身份核验未完成'}",
            f"- 在本行资产：活期存款 {a['demand_deposit']}，定期存款 {a['time_deposit']}，"
            f"理财持仓 {holdings}；可随时支取的资产合计约 {a['liquid_total']}",
            f"- 专属理财经理：{s['assigned_rm']}",
        ]
    else:
        lines.append("- 系统中暂无该客户的基础资料")
    lines.append("")
    lines.append("## 本次需求（客户在对话中提供）")
    for row in needs.display():
        value = row["value"]
        if row["field"] == "max_acceptable_loss" and value is None and loss_tolerance:
            value = f"{loss_tolerance}（风险测评中已回答，无需再问）"
        lines.append(f"- {row['label']}：{value or '未提供'}")
    lines += [
        "",
        "## 客户资料使用规则",
        "- 以上已知信息不要再向客户询问；只追问当前决策必需的缺失项（如投资期限）。",
        "- 客户要求查询产品或模拟配置时直接执行，非关键信息可以在给出结果后再补充询问。",
        "- 客户在对话中提供新的需求信息（金额、期限、随时可能动用的金额、目标收益、可接受亏损、"
        "投资目的）时，调用 update_needs 记录。",
        "- 基础资料只读：客户所说与银行系统记录不一致时（如年龄），以系统记录为准，并提示可到网点更新资料。",
    ]
    return "\n".join(lines)
