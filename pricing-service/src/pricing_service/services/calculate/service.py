from decimal import ROUND_HALF_UP, Decimal

from pricing_service.services.calculate.dto import CalculationResult, MarketSnapshot, PricingParameters, PricingStrategy
from statistics import median


def calculate_price(params: PricingParameters, market: MarketSnapshot) -> CalculationResult:
    quant = Decimal("0.01")

    total_required = params.variable_costs + params.allocated_fixed_costs + params.target_profit
    min_price = (total_required / (Decimal("1") - params.percent_fees)).quantize(
        quant, rounding=ROUND_HALF_UP
    )

    valid_prices = [price for price in market.competitor_prices if price >= Decimal("0")]

    if not valid_prices or params.strategy == PricingStrategy.MIN_MARGIN_ONLY:
        recommended_price = min_price
        warning = "NO_COMPETITOR_DATA" if not valid_prices else None
        explanation = (
            "Нет актуальных цен конкурентов, цена рассчитана по экономике товара."
            if not valid_prices
            else "Выбрана стратегия расчёта только от минимальной допустимой маржи."
        )
    else:
        if params.strategy == PricingStrategy.MATCH_COMPETITOR:
            target_price = min(valid_prices).quantize(quant, rounding=ROUND_HALF_UP)
        elif params.strategy == PricingStrategy.UNDERCUT_COMPETITOR:
            target_price = (min(valid_prices) - params.undercut_amount).quantize(
                quant, rounding=ROUND_HALF_UP
            )
        elif params.strategy == PricingStrategy.MARKET_AVERAGE:
            target_price = Decimal(str(median(valid_prices))).quantize(
                quant, rounding=ROUND_HALF_UP
            )
        else:
            target_price = min_price

        if target_price < min_price:
            recommended_price = min_price
            warning = "COMPETITOR_BELOW_MIN_PRICE"
            explanation = (
                f"Рыночный ориентир ({target_price}) ниже безопасного порога ({min_price}). "
                "Установлена минимально допустимая цена."
            )
        else:
            recommended_price = target_price
            warning = None
            explanation = f"Цена установлена согласно стратегии {params.strategy.value}."

    expected_profit = (
        recommended_price * (Decimal("1") - params.percent_fees)
        - params.variable_costs
        - params.allocated_fixed_costs
    ).quantize(quant, rounding=ROUND_HALF_UP)

    return CalculationResult(
        min_price=min_price,
        recommended_price=recommended_price,
        expected_profit=expected_profit,
        warning=warning,
        explanation=explanation,
    )