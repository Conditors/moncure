from decimal import Decimal
import pytest
from pydantic import ValidationError

from pricing_service.services.calculate.dto import (
    MarketSnapshot,
    PricingParameters,
    PricingStrategy,    
)
from pricing_service.services.calculate.service import calculate_price


@pytest.fixture
def base_params() -> PricingParameters:
    return PricingParameters(
        variable_costs=Decimal("100.00"),
        allocated_fixed_costs=Decimal("20.00"),
        target_profit=Decimal("30.00"),
        percent_fees=Decimal("0.25"),
        strategy=PricingStrategy.MATCH_COMPETITOR,
        undercut_amount=Decimal("5.00"),
    )


def test_calculate_price_no_competitors(base_params: PricingParameters):
    market = MarketSnapshot(competitor_prices=[])

    result = calculate_price(params=base_params, market=market)

    assert result.min_price == Decimal("200.00")
    assert result.recommended_price == Decimal("200.00")
    assert result.expected_profit == Decimal("30.00")
    assert result.warning == "NO_COMPETITOR_DATA"


def test_calculate_price_competitor_below_min(base_params: PricingParameters):
    market = MarketSnapshot(competitor_prices=[Decimal("180.00"), Decimal("210.00")])

    result = calculate_price(params=base_params, market=market)

    assert result.min_price == Decimal("200.00")
    assert result.recommended_price == Decimal("200.00")
    assert result.expected_profit == Decimal("30.00")
    assert result.warning == "COMPETITOR_BELOW_MIN_PRICE"


@pytest.mark.parametrize(
    ("strategy", "prices", "expected_price", "expected_profit"),
    [
        (
            PricingStrategy.MATCH_COMPETITOR,
            [Decimal("220.00"), Decimal("260.00")],
            Decimal("220.00"),
            Decimal("45.00"),
        ),
        (
            PricingStrategy.UNDERCUT_COMPETITOR,
            [Decimal("220.00"), Decimal("260.00")],
            Decimal("215.00"),
            Decimal("41.25"),
        ),
        (
            PricingStrategy.MARKET_AVERAGE,
            [Decimal("210.00"), Decimal("240.00"), Decimal("999.00")],
            Decimal("240.00"),
            Decimal("60.00"),
        ),
        (
            PricingStrategy.MIN_MARGIN_ONLY,
            [Decimal("250.00")],
            Decimal("200.00"),
            Decimal("30.00"),
        ),
    ],
)
def test_calculate_price_strategies(
    base_params: PricingParameters,
    strategy: PricingStrategy,
    prices: list[Decimal],
    expected_price: Decimal,
    expected_profit: Decimal,
):
    params = base_params.model_copy(update={"strategy": strategy})
    market = MarketSnapshot(competitor_prices=prices)

    result = calculate_price(params=params, market=market)

    assert result.recommended_price == expected_price
    assert result.expected_profit == expected_profit
    assert result.warning is None


def test_calculate_price_rounding():
    params = PricingParameters(
        variable_costs=Decimal("100.00"),
        allocated_fixed_costs=Decimal("0.00"),
        target_profit=Decimal("0.00"),
        percent_fees=Decimal("0.30"),
        strategy=PricingStrategy.MIN_MARGIN_ONLY,
    )
    result = calculate_price(params=params, market=MarketSnapshot(competitor_prices=[]))

    assert result.min_price == Decimal("142.86")

@pytest.mark.parametrize(
    "invalid_field",
    [
        {"variable_costs": Decimal("-1.00")},
        {"percent_fees": Decimal("1.00")},
        {"percent_fees": Decimal("-0.05")},
    ],
)
def test_invalid_pricing_parameters(invalid_field: dict):
    valid_data = {
        "variable_costs": Decimal("10.00"),
        "allocated_fixed_costs": Decimal("5.00"),
        "target_profit": Decimal("3.00"),
        "percent_fees": Decimal("0.05"),
        "strategy": PricingStrategy.MIN_MARGIN_ONLY,
    }
    valid_data.update(invalid_field)

    with pytest.raises(ValidationError):
        PricingParameters(**valid_data)