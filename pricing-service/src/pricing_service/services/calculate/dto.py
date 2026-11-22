from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class PricingStrategy(StrEnum):
    MATCH_COMPETITOR = "match_competitor"
    UNDERCUT_COMPETITOR = "undercut_competitor"
    MIN_MARGIN_ONLY = "min_margin_only"
    MARKET_AVERAGE = "market_average"


class PricingParameters(BaseModel):
    variable_costs: Decimal = Field(ge=0)
    allocated_fixed_costs: Decimal = Field(ge=0)
    target_profit: Decimal = Field(ge=0)
    percent_fees: Decimal = Field(ge=0, lt=1)
    strategy: PricingStrategy
    undercut_amount: Decimal = Field(default=Decimal("1.00"), ge=0)


class MarketSnapshot(BaseModel):
    competitor_prices: list[Decimal]


class CalculationResult(BaseModel):
    min_price: Decimal
    recommended_price: Decimal
    expected_profit: Decimal
    warning: str | None
    explanation: str