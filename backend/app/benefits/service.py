"""客户等级与营销活动：从 data/benefits/benefits.yaml 加载，按金融资产总额计算等级与升级差距。

等级只与资产总额挂钩（存款也计入），不与某款产品挂钩；计算由代码完成，AI 只转述结果。
"""

from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.core.i18n import L, is_en
from app.customers.base import BaseProfile
from app.products.presenter import format_money

BENEFITS_PATH = Path(__file__).resolve().parents[3] / "data/benefits/benefits.yaml"
# 距下一等级不足门槛的 20% 时视为「接近」，可主动提示一次
NEAR_RATIO = Decimal("0.2")


class Tier(BaseModel):
    code: str
    name: str
    name_en: str
    card_name: str
    card_name_en: str
    min_aum: Decimal
    benefits: list[str]
    benefits_en: list[str]

    @property
    def display_name(self) -> str:
        return L(self.name, self.name_en)

    @property
    def display_card(self) -> str:
        return L(self.card_name, self.card_name_en)

    @property
    def display_benefits(self) -> list[str]:
        return self.benefits_en if is_en() else self.benefits


class Campaign(BaseModel):
    id: str
    name: str
    name_en: str
    start: date
    end: date
    reward: str
    reward_en: str
    rule: str
    rule_en: str
    eligible_tiers: list[str]

    @property
    def display_name(self) -> str:
        return L(self.name, self.name_en)


class BenefitsConfig(BaseModel):
    as_of: date
    evaluation_rule: str
    evaluation_rule_en: str
    tiers: list[Tier]
    campaigns: list[Campaign]

    def tier_for(self, aum: Decimal) -> Tier:
        return [t for t in self.tiers if aum >= t.min_aum][-1]

    def next_tier(self, tier: Tier) -> Tier | None:
        later = [t for t in self.tiers if t.min_aum > tier.min_aum]
        return later[0] if later else None


@lru_cache
def load_benefits(path: Path = BENEFITS_PATH) -> BenefitsConfig:
    config = BenefitsConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    config.tiers.sort(key=lambda t: t.min_aum)
    return config


def tier_label(name: str) -> str:
    """银行系统里的等级名称（如「财富客户」）按当前语言显示。"""
    tier = next((t for t in load_benefits().tiers if t.name == name), None)
    return tier.display_name if tier else name


class TierStatus(BaseModel):
    aum: Decimal
    tier: Tier
    next_tier: Tier | None
    gap: Decimal | None  # 距下一等级还差多少
    near_next: bool
    projected_aum: Decimal | None = None  # 计划新增资金转入后
    projected_tier: Tier | None = None

    @property
    def reaches_next_with_plan(self) -> bool:
        return bool(self.projected_tier and self.projected_tier.min_aum > self.tier.min_aum)


def tier_status(base: BaseProfile, planned_amount: Decimal | None = None) -> TierStatus:
    config = load_benefits()
    aum = base.assets_at_bank.total
    tier = config.tier_for(aum)
    nxt = config.next_tier(tier)
    gap = nxt.min_aum - aum if nxt else None
    status = TierStatus(
        aum=aum,
        tier=tier,
        next_tier=nxt,
        gap=gap,
        near_next=bool(nxt and gap <= nxt.min_aum * NEAR_RATIO),
    )
    if planned_amount:
        status.projected_aum = aum + planned_amount
        status.projected_tier = config.tier_for(status.projected_aum)
    return status


def active_campaigns(tier: Tier, today: date) -> list[Campaign]:
    return [
        c
        for c in load_benefits().campaigns
        if c.start <= today <= c.end and tier.code in c.eligible_tiers
    ]


def benefits_block(status: TierStatus, today: date) -> dict:
    """界面卡片：当前等级、升级进度、权益与可参与的活动。"""
    config = load_benefits()
    nxt = status.next_tier
    return {
        "type": "tier_benefits",
        "tier": {"name": status.tier.display_name, "card_name": status.tier.display_card},
        "aum": format_money(status.aum),
        "benefits": status.tier.display_benefits,
        "next_tier": {
            "name": nxt.display_name,
            "card_name": nxt.display_card,
            "threshold": format_money(nxt.min_aum),
            "gap": format_money(status.gap),
            "progress": float(min(status.aum / nxt.min_aum, Decimal(1))),
            "benefits": nxt.display_benefits,
        }
        if nxt
        else None,
        "projection": {
            "aum": format_money(status.projected_aum),
            "tier_name": status.projected_tier.display_name,
            "reaches_next": status.reaches_next_with_plan,
        }
        if status.projected_aum is not None
        else None,
        "campaigns": [
            {
                "name": c.display_name,
                "period": L(
                    f"{c.start:%Y-%m-%d} 至 {c.end:%Y-%m-%d}",
                    f"{c.start:%b} {c.start.day} – {c.end:%b} {c.end.day}, {c.end.year}",
                ),
                "reward": L(c.reward, c.reward_en),
                "rule": L(c.rule, c.rule_en),
            }
            for c in active_campaigns(status.tier, today)
        ],
        "evaluation_rule": L(config.evaluation_rule, config.evaluation_rule_en),
    }
