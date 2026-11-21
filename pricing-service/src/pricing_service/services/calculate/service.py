from decimal import Decimal

from pricing_service.services.calculate.dto import CalculationResult, MarketSnapshot, PricingParameters


def calculate_price(params: PricingParameters, market: MarketSnapshot) -> CalculationResult:
    pass