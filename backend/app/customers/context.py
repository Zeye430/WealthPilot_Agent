"""客户上下文：只读的基础画像 + 本次需求。每条消息都重新组装，保证 LLM 看到的是最新状态。"""

from sqlalchemy.orm import Session

from app.customers.base import BaseProfile, get_customer_info_system
from app.customers.needs import Needs, get_needs


def customer_profile(db: Session, customer_id: str) -> dict:
    """提供给前端的画像：两层分开展示，并标明来源。"""
    base = get_customer_info_system().get(customer_id)
    return {
        "base": base.summary() if base else None,
        "needs": get_needs(db, customer_id).display(),
    }


def prompt_section(base: BaseProfile | None, needs: Needs) -> str:
    lines = ["", "## 客户资料（来自知岸银行客户信息系统，只读）"]
    if base:
        s = base.summary()
        a = s["assets"]
        holdings = "、".join(f"{h['name']} {h['amount']}" for h in a["holdings"]) or "无"
        lines += [
            f"- {s['display_name']}，{s['age']} 岁，{s['customer_tier']}，"
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
        lines.append(f"- {row['label']}：{row['value'] or '未提供'}")
    lines += [
        "",
        "## 客户资料使用规则",
        "- 以上已知信息不要再向客户询问；只追问当前决策必需的缺失项（如投资期限、可接受的最大亏损）。",
        "- 客户在对话中提供新的需求信息（金额、期限、随时可能动用的金额、目标收益、可接受亏损、"
        "投资目的）时，调用 update_needs 记录。",
        "- 基础资料只读：客户所说与银行系统记录不一致时（如年龄），以系统记录为准，并提示可到网点更新资料。",
    ]
    return "\n".join(lines)
