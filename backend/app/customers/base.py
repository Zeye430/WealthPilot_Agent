"""Customer base profile: from the bank's customer information system; read-only for WealthPilot.

The demo simulates that system with YAML; in production, swap the CustomerInfoSystem implementation
(e.g. call the CRM API)
and code above it is unaffected. Base-profile changes go through the bank's own KYC process and
can't be made in chat.
"""

from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import yaml
from pydantic import BaseModel

from app.core.i18n import L
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
        """Assets available any time: checking balance + wealth holdings that open daily."""
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
    name_en: str | None = None
    title: str = "理财经理"
    title_en: str = "Relationship Manager"
    # Contact details come from the bank's staff system; demo data has none, so the UI shows a demo
    # note instead of dialing a real number
    phone: str | None = None
    wecom_url: str | None = None

    @property
    def display_name(self) -> str:
        return L(self.name, self.name_en or self.name)

    @property
    def display_title(self) -> str:
        return L(self.title, self.title_en)

    def contact_card(self) -> dict:
        return {
            "rm_name": self.display_name,
            "rm_title": self.display_title,
            "phone": self.phone,
            "wecom_url": self.wecom_url,
        }


class BaseProfile(BaseModel):
    customer_id: str
    display_name: str
    display_name_en: str | None = None
    age: int
    customer_tier: str
    occupation: str
    occupation_en: str | None = None
    customer_since: date
    kyc_verified: bool
    assigned_rm: RelationshipManager
    assets_at_bank: AssetsAtBank

    @property
    def localized_name(self) -> str:
        return L(self.display_name, self.display_name_en or self.display_name)

    @property
    def localized_tier(self) -> str:
        from app.benefits.service import tier_label

        return tier_label(self.customer_tier)

    def summary(self) -> dict:
        """Summary for the frontend and the LLM: only what wealth services need."""
        catalog = load_catalog()
        holdings = [
            {
                "code": h.code,
                "name": p.display_name if (p := catalog.get(h.code)) else h.code,
                "amount": format_money(h.amount),
            }
            for h in self.assets_at_bank.wealth_products
        ]
        return {
            "display_name": self.localized_name,
            "age": self.age,
            "customer_tier": self.localized_tier,
            "kyc_verified": self.kyc_verified,
            "assigned_rm": self.assigned_rm.display_name,
            "assets": {
                "demand_deposit": format_money(self.assets_at_bank.demand_deposit),
                "time_deposit": format_money(self.assets_at_bank.time_deposit),
                "holdings": holdings,
                "liquid_total": format_money(self.assets_at_bank.liquid_total()),
                "total": format_money(self.assets_at_bank.total),
            },
            "source": L("知岸银行客户信息系统（模拟）", "Zhian Bank customer system (simulated)"),
        }


class CustomerInfoSystem(Protocol):
    def get(self, customer_id: str) -> BaseProfile | None: ...


class YamlCustomerInfoSystem:
    """Demo: read fictional customers' base profiles from YAML."""

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
    """Options for question 1 (age): the base profile already has the age, so it's preselected
    for the customer to confirm."""
    return next((opt for bound, opt in AGE_OPTION_BOUNDS if age <= bound), "E")
