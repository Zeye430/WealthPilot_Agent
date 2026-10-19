"""客户上下文：只读的基础画像 + 本次需求。每条消息都重新组装，保证 LLM 看到的是最新状态。"""

import re

from sqlalchemy.orm import Session

from app.assessment.scoring import load_questionnaire
from app.assessment.service import latest_confirmed
from app.benefits.service import tier_status
from app.customers.base import BaseProfile, get_customer_info_system
from app.customers.needs import Needs, get_needs
from app.products.presenter import format_money


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
    return {
        "base": base.summary() if base else None,
        "needs": needs,
        "overview": overview(base) if base else None,
    }


def overview(base: BaseProfile) -> dict:
    """「我的」页资产卡片：原始数值由前端按语言格式化；等级与升级差距由代码计算。"""
    assets = base.assets_at_bank
    status = tier_status(base)
    nxt = status.next_tier
    return {
        "total": float(assets.total),
        "liquid": float(assets.liquid_total()),
        "wealth": float(sum((h.amount for h in assets.wealth_products), start=0)),
        "tier": {"name": status.tier.name, "card_name": status.tier.card_name},
        "next_tier": {
            "name": nxt.name,
            "threshold": float(nxt.min_aum),
            "gap": float(status.gap),
            "progress": float(min(status.aum / nxt.min_aum, 1)),
        }
        if nxt
        else None,
        "rm": base.assigned_rm.contact_card(),
    }


def tier_lines(base: BaseProfile, needs: Needs) -> list[str]:
    """客户等级与「可提示升级」的时机：由代码判断，AI 只在合适时提示一次。"""
    status = tier_status(base, needs.investment_amount)
    line = (
        f"- 客户等级：{status.tier.name}（{status.tier.card_name}），"
        f"金融资产合计约 {format_money(status.aum)}"
    )
    nxt = status.next_tier
    if nxt:
        line += f"；距{nxt.name}（{format_money(nxt.min_aum)}）还差 {format_money(status.gap)}"
    lines = [line]
    if status.reaches_next_with_plan or status.near_next:
        # 主动提示的措辞必须包含前提与「以银行评定为准」，由代码统一追加（场景评估 V02）
        lines.append(
            "- 等级升级提示由系统在回答末尾自动补充，你不要主动提等级升级或权益；"
            "客户主动问奖励、权益时再调用 get_customer_benefits。"
        )
    return lines


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
            *tier_lines(base, needs),
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


SELF_REPORTED_AGE = re.compile(r"我(今年|现在|已经)?\s*(\d{2})\s*(周)?岁")


def age_conflict_note(message: str, reply: str, base: BaseProfile | None) -> str | None:
    """客户自称的年龄与银行登记不一致、而回答没有说明时，由代码补充（P7 场景评估 M02 发现）。

    年龄影响适当性判断，以银行登记（KYC）为准；对话不能改写基础画像。
    """
    match = SELF_REPORTED_AGE.search(message)
    if base is None or match is None or int(match.group(2)) == base.age:
        return None
    if f"{base.age}" in reply:  # 回答已经提到登记年龄
        return None
    return (
        f"根据银行登记信息，您的年龄为 {base.age} 岁，产品匹配以登记信息和风险测评结果为准；"
        "如信息有变化，可携带有效证件到网点更新。"
    )


def tier_upgrade_note(
    base: BaseProfile | None, needs: Needs, reply: str, history: str
) -> str | None:
    """计划资金转入后可达下一等级、而回答和此前对话都没有提到时，由代码补充一次（场景评估 V02 发现）。

    只陈述事实与前提（新转入资金、以银行评定为准），不与任何产品挂钩。
    """
    if base is None or needs.investment_amount is None:
        return None
    status = tier_status(base, needs.investment_amount)
    if not status.reaches_next_with_plan:
        return None
    target = status.projected_tier
    if target.name in reply or target.name in history:
        return None
    perks = "、".join(target.benefits[:2])
    return (
        f"另外提示：如这笔 {format_money(needs.investment_amount)} 为新转入本行的资金，"
        f"您的金融资产将达到{target.name}（{target.card_name}）标准，可享{perks}等权益；"
        "等级按月日均金融资产评定，以银行评定结果为准。"
    )
