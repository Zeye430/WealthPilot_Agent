"""客户基础画像：来自银行客户信息系统，WealthPilot 只读。

演示环境用 YAML 模拟该系统；生产环境替换 CustomerInfoSystem 的实现（如调用 CRM 接口）即可，
上层代码不受影响。基础画像的修改应走银行自身的 KYC 流程，不能通过对话改写。
"""

from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import yaml
from pydantic import BaseModel

from app.products.catalog import load_catalog
from app.products.presenter import format_money

BASE_PROFILES_PATH = Path(__file__).resolve().parents[3] / "data/customers/base_profiles.yaml"


class Holding(BaseModel):
    code: str
    amount: Decimal


class AssetsAtBank(BaseModel):
    demand_deposit: Decimal
    time_deposit: Decimal
    wealth_products: list[Holding]

    @property
    def total(self) -> Decimal:
        return (
            self.demand_deposit
            + self.time_deposit
            + sum((h.amount for h in self.wealth_products), Decimal(0))
        )

    def liquid_total(self) -> Decimal:
        """可随时支取的资产：活期存款 + 每日开放的理财持仓。"""
        catalog = load_catalog()
        liquid_products = sum(
            (
                h.amount
                for h in self.wealth_products
                if (p := catalog.get(h.code)) is not None and p.lockup_days == 0
            ),
            Decimal(0),
        )
        return self.demand_deposit + liquid_products


class RelationshipManager(BaseModel):
    id: str
    name: str


class BaseProfile(BaseModel):
    customer_id: str
    display_name: str
    age: int
    customer_tier: str
    occupation: str
    customer_since: date
    kyc_verified: bool
    assigned_rm: RelationshipManager
    assets_at_bank: AssetsAtBank

    def summary(self) -> dict:
        """提供给前端与 LLM 的摘要：只含理财服务需要的信息。"""
        catalog = load_catalog()
        holdings = [
            {
                "code": h.code,
                "name": p.name if (p := catalog.get(h.code)) else h.code,
                "amount": format_money(h.amount),
            }
            for h in self.assets_at_bank.wealth_products
        ]
        return {
            "display_name": self.display_name,
            "age": self.age,
            "customer_tier": self.customer_tier,
            "kyc_verified": self.kyc_verified,
            "assigned_rm": self.assigned_rm.name,
            "assets": {
                "demand_deposit": format_money(self.assets_at_bank.demand_deposit),
                "time_deposit": format_money(self.assets_at_bank.time_deposit),
                "holdings": holdings,
                "liquid_total": format_money(self.assets_at_bank.liquid_total()),
                "total": format_money(self.assets_at_bank.total),
            },
            "source": "知岸银行客户信息系统（模拟）",
        }


class CustomerInfoSystem(Protocol):
    def get(self, customer_id: str) -> BaseProfile | None: ...


class YamlCustomerInfoSystem:
    """演示用：从 YAML 读取虚构客户的基础画像。"""

    def __init__(self, path: Path = BASE_PROFILES_PATH):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self._profiles = {
            cid: BaseProfile(customer_id=cid, **fields) for cid, fields in data["customers"].items()
        }

    def get(self, customer_id: str) -> BaseProfile | None:
        return self._profiles.get(customer_id)


@lru_cache
def get_customer_info_system() -> CustomerInfoSystem:
    return YamlCustomerInfoSystem()


AGE_OPTION_BOUNDS = [(30, "A"), (45, "B"), (55, "C"), (65, "D")]


def age_option(age: int) -> str:
    """问卷第 1 题（年龄）的选项：基础画像已有年龄，测评时预选，客户确认即可。"""
    return next((opt for bound, opt in AGE_OPTION_BOUNDS if age <= bound), "E")
