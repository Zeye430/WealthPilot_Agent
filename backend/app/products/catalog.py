"""虚构产品目录：从 data/products/products.yaml 加载并校验。

产品要素只在 YAML 中维护（单一数据源），本模块负责解析、校验与只读查询。
校验在启动时执行：费率缺失却标为已核实、现金管理类没有七日年化等配置错误，会直接报错。
"""

import re
from datetime import date
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator, model_validator

from app.assessment.scoring import PRODUCT_RISK_ORDER
from app.core.i18n import L

CATALOG_PATH = Path(__file__).resolve().parents[3] / "data/products/products.yaml"
ISSUER_PREFIX = {"知岸理财": "ZA", "鸿屿理财": "HY"}
ISSUER_EN = {"知岸理财": "Zhian Wealth Management", "鸿屿理财": "Hongyu Wealth Management"}
DISTRIBUTOR = "知岸银行"
DISTRIBUTOR_EN = "Zhian Bank"
MAX_ANNUAL_FEE = Decimal("0.03")


def parse_rate(value: object) -> Decimal | None:
    """「0.10%」→ Decimal("0.0010")。YAML 中费率与收益率统一写成百分数，便于人工审核。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text.endswith("%"):
        raise ValueError(f"比率应写成百分数（如 0.10%），收到 {value!r}")
    return Decimal(text[:-1]) / 100


class ProductType(StrEnum):
    CASH_MANAGEMENT = "CASH_MANAGEMENT"
    FIXED_INCOME = "FIXED_INCOME"
    FIXED_INCOME_PLUS = "FIXED_INCOME_PLUS"
    MIXED = "MIXED"
    EQUITY = "EQUITY"


PRODUCT_TYPE_LABELS = {
    ProductType.CASH_MANAGEMENT: "现金管理类",
    ProductType.FIXED_INCOME: "固定收益类",
    ProductType.FIXED_INCOME_PLUS: "固收+",
    ProductType.MIXED: "混合类",
    ProductType.EQUITY: "权益类",
}
PRODUCT_TYPE_LABELS_EN = {
    ProductType.CASH_MANAGEMENT: "Cash management",
    ProductType.FIXED_INCOME: "Fixed income",
    ProductType.FIXED_INCOME_PLUS: "Fixed income plus",
    ProductType.MIXED: "Mixed assets",
    ProductType.EQUITY: "Equity",
}


class OperationMode(StrEnum):
    OPEN = "OPEN"
    MIN_HOLDING = "MIN_HOLDING"
    CLOSED = "CLOSED"
    PERIODIC_OPEN = "PERIODIC_OPEN"


class ProductStatus(StrEnum):
    ON_SALE = "ON_SALE"
    ENDED = "ENDED"
    UPCOMING = "UPCOMING"  # 已公告、尚未开始募集的新发产品，可预约开售提醒，不能买入


class DataQuality(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class MetricType(StrEnum):
    SEVEN_DAY_ANNUALIZED = "SEVEN_DAY_ANNUALIZED"
    TEN_THOUSAND_UNIT_INCOME = "TEN_THOUSAND_UNIT_INCOME"
    PERFORMANCE_BENCHMARK = "PERFORMANCE_BENCHMARK"
    ANNUAL_PERFORMANCE = "ANNUAL_PERFORMANCE"


METRIC_LABELS = {
    MetricType.SEVEN_DAY_ANNUALIZED: "七日年化收益率",
    MetricType.TEN_THOUSAND_UNIT_INCOME: "每万份收益",
    MetricType.PERFORMANCE_BENCHMARK: "业绩比较基准",
    MetricType.ANNUAL_PERFORMANCE: "过往年度业绩",
}
METRIC_LABELS_EN = {
    MetricType.SEVEN_DAY_ANNUALIZED: "7-day annualized yield",
    MetricType.TEN_THOUSAND_UNIT_INCOME: "Income per 10,000 units",
    MetricType.PERFORMANCE_BENCHMARK: "Performance benchmark",
    MetricType.ANNUAL_PERFORMANCE: "Past annual performance",
}


def metric_label(metric_type: MetricType) -> str:
    return L(METRIC_LABELS[metric_type], METRIC_LABELS_EN[metric_type])


def issuer_label(issuer: str) -> str:
    return L(issuer, ISSUER_EN.get(issuer, issuer))


class RedemptionTier(BaseModel):
    max_days: int | None  # 持有不足 max_days 天适用该费率；None 表示无上限
    rate: Decimal

    _rate = field_validator("rate", mode="before")(parse_rate)


class PerformanceFee(BaseModel):
    rate: Decimal
    condition: str
    condition_en: str | None = None

    @property
    def display_condition(self) -> str:
        return L(self.condition, self.condition_en or self.condition)

    _rate = field_validator("rate", mode="before")(parse_rate)


class Fees(BaseModel):
    management: Decimal | None
    custody: Decimal | None
    sales_service: Decimal | None
    subscription: Decimal | None
    redemption: list[RedemptionTier]
    performance_fee: PerformanceFee | None = None

    _rates = field_validator(
        "management", "custody", "sales_service", "subscription", mode="before"
    )(parse_rate)

    @model_validator(mode="after")
    def _check(self):
        for name in ("management", "custody", "sales_service"):
            value = getattr(self, name)
            if value is not None and not Decimal(0) <= value <= MAX_ANNUAL_FEE:
                raise ValueError(f"{name} 年化费率 {value} 超出合理范围（0–3%）")
        if not self.redemption or self.redemption[-1].max_days is not None:
            raise ValueError("赎回费最后一档的 max_days 必须为 null")
        return self

    @property
    def missing(self) -> list[str]:
        return [n for n in ("management", "custody", "sales_service") if getattr(self, n) is None]

    @property
    def annual_total(self) -> Decimal | None:
        """固定年化费用合计（管理 + 托管 + 销售服务）；有缺失时返回 None，不猜测。"""
        if self.missing:
            return None
        return self.management + self.custody + self.sales_service


class PerformancePeriod(BaseModel):
    label: str
    label_en: str | None = None
    start: date
    end: date
    value: Decimal

    _value = field_validator("value", mode="before")(parse_rate)

    @property
    def display_label(self) -> str:
        return L(self.label, self.label_en or self.label)


class Metric(BaseModel):
    type: MetricType
    value: Decimal | None = None  # 七日年化
    value_yuan: Decimal | None = None  # 每万份收益（元）
    as_of: date | None = None
    low: Decimal | None = None  # 业绩比较基准区间
    high: Decimal | None = None
    formula: str | None = None  # 指数组合型业绩比较基准
    formula_en: str | None = None
    basis: str | None = None  # 业绩比较基准的测算依据（信披办法第十三条要求说明）
    basis_en: str | None = None
    periods: list[PerformancePeriod] | None = None

    @property
    def display_formula(self) -> str | None:
        return L(self.formula, self.formula_en or self.formula) if self.formula else None

    @property
    def display_basis(self) -> str | None:
        return L(self.basis, self.basis_en or self.basis) if self.basis else None

    _rates = field_validator("value", "low", "high", mode="before")(parse_rate)

    @model_validator(mode="after")
    def _check(self):
        match self.type:
            case MetricType.SEVEN_DAY_ANNUALIZED:
                ok = self.value is not None and self.as_of is not None
            case MetricType.TEN_THOUSAND_UNIT_INCOME:
                ok = self.value_yuan is not None and self.as_of is not None
            case MetricType.PERFORMANCE_BENCHMARK:
                has_range = self.low is not None and self.high is not None and self.low <= self.high
                ok = bool(self.basis) and (has_range or bool(self.formula))
            case MetricType.ANNUAL_PERFORMANCE:
                ok = bool(self.periods)
        if not ok:
            raise ValueError(f"收益指标 {self.type} 字段不完整")
        return self


class Product(BaseModel):
    code: str
    name: str
    name_en: str  # 英文界面使用的直译名称（虚构）
    issuer: str
    product_type: ProductType
    operation_mode: OperationMode
    lockup_days: int
    redemption_settlement: str
    issuer_risk_level: str
    distributor_risk_level: str | None = None
    minimum_investment: Decimal
    status: ProductStatus
    data_quality: DataQuality
    inception_date: date
    maturity_date: date | None = None
    # 新发产品的募集期与募集规模上限（说明书披露的事实，额满提前结束募集）
    sale_start: date | None = None
    sale_end: date | None = None
    raise_limit: Decimal | None = None
    investment_scope: str
    investment_scope_en: str
    strategy: str
    strategy_en: str
    fees: Fees
    metrics: list[Metric]
    data_origin: str = "SYNTHETIC"

    @model_validator(mode="after")
    def _check(self):
        prefix = ISSUER_PREFIX.get(self.issuer)
        if prefix is None or not self.code.startswith(prefix + "-"):
            raise ValueError(f"{self.code}：代码前缀与发行机构 {self.issuer} 不符")
        if self.issuer_risk_level not in PRODUCT_RISK_ORDER:
            raise ValueError(f"{self.code}：发行评级应为 PR1–PR5")
        if self.distributor_risk_level and self.distributor_risk_level[1:] not in "12345":
            raise ValueError(f"{self.code}：销售评级应为 R1–R5")
        if (self.lockup_days == 0) != (self.operation_mode is OperationMode.OPEN):
            raise ValueError(f"{self.code}：仅每日开放产品的 lockup_days 为 0")
        if self.fees.missing and self.data_quality is DataQuality.VERIFIED:
            raise ValueError(
                f"{self.code}：费率缺失 {self.fees.missing}，data_quality 不能为 VERIFIED"
            )
        types = {m.type for m in self.metrics}
        is_cash = self.product_type is ProductType.CASH_MANAGEMENT
        if is_cash and MetricType.SEVEN_DAY_ANNUALIZED not in types:
            raise ValueError(f"{self.code}：现金管理类产品必须有七日年化收益率")
        if not is_cash and MetricType.SEVEN_DAY_ANNUALIZED in types:
            raise ValueError(f"{self.code}：七日年化收益率只适用于现金管理类产品")
        if not is_cash and MetricType.PERFORMANCE_BENCHMARK not in types:
            raise ValueError(f"{self.code}：净值型产品必须披露业绩比较基准")
        if self.status is ProductStatus.UPCOMING:
            if not (self.sale_start and self.sale_end and self.sale_start <= self.sale_end):
                raise ValueError(f"{self.code}：新发产品必须填写募集期 sale_start / sale_end")
            if self.inception_date <= self.sale_end:
                raise ValueError(f"{self.code}：成立日应晚于募集结束日")
        return self

    @property
    def effective_risk_level(self) -> str:
        """发行评级与销售评级不一致时取较高者（PR3 与 R3 视为同级）。"""
        levels = [int(self.issuer_risk_level[2:])]
        if self.distributor_risk_level:
            levels.append(int(self.distributor_risk_level[1:]))
        return f"PR{max(levels)}"

    @property
    def type_label(self) -> str:
        return L(PRODUCT_TYPE_LABELS[self.product_type], PRODUCT_TYPE_LABELS_EN[self.product_type])

    @property
    def display_name(self) -> str:
        return L(self.name, self.name_en)

    @property
    def display_issuer(self) -> str:
        return issuer_label(self.issuer)

    @property
    def display_scope(self) -> str:
        return L(self.investment_scope, self.investment_scope_en)

    @property
    def display_strategy(self) -> str:
        return L(self.strategy, self.strategy_en)

    def metric(self, metric_type: MetricType) -> Metric | None:
        return next((m for m in self.metrics if m.type is metric_type), None)


class Catalog(BaseModel):
    catalog_version: str
    as_of: date
    products: list[Product]

    @model_validator(mode="after")
    def _unique(self):
        codes = [p.code for p in self.products]
        if len(codes) != len(set(codes)):
            raise ValueError("产品代码重复")
        return self

    def get(self, code: str) -> Product | None:
        code = code.strip().upper()
        return next((p for p in self.products if p.code == code), None)

    def find_by_name(self, text: str) -> Product | None:
        """按名称或代码模糊匹配（客户常说「活钱宝」而不是完整名称）。"""
        if product := self.get(text):
            return product
        compact = text.replace(" ", "")
        # 英文名忽略大小写、空格与标点：模型常写成「Zhian Steady 1 Year Holding」（评估 R02）
        # 只在输入含英文字母时按英文名匹配：中文名去掉汉字后只剩数字（如「30」），会误配其他产品
        alnum = _alnum(text) if re.search(r"[A-Za-z]", text) else ""
        return next(
            (
                p
                for p in self.products
                if compact
                and (compact in p.name.replace(" ", "") or (alnum and alnum in _alnum(p.name_en)))
            ),
            None,
        )


def _alnum(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.lower())


@lru_cache
def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    return Catalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
