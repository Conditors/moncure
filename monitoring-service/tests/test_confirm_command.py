from decimal import Decimal

import pytest

from monitoring_service.services.product_import import ConfirmOwnProductCommand


@pytest.mark.parametrize(
    "price",
    ["0", "-1", "0.00001", "1000000000000000", "NaN", "Infinity"],
)
def test_reject_invalid_confirmation_price(price: str) -> None:
    with pytest.raises(ValueError):
        ConfirmOwnProductCommand(name="Item", price=Decimal(price))


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"name": "я" * 129},
        {"article": "a" * 56, "source": "Store"},
        {"source": "s" * 51},
        {"article": "SKU"},
        {"article": "SKU", "source": " "},
        {"article": " ", "source": "Store"},
        {"name": "Item\x00name"},
        {"article": "SKU\x00", "source": "Store"},
        {"source": "Store\x00"},
    ],
)
def test_reject_invalid_confirmation_text(changes: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        ConfirmOwnProductCommand(
            name=changes.get("name", "Item"),
            price=Decimal(1),
            article=changes.get("article"),
            source=changes.get("source"),
        )


def test_accept_values_at_database_limits() -> None:
    command = ConfirmOwnProductCommand(
        name="я" * 128,
        price=Decimal("999999999999999.9999"),
        article="a" * 55,
        source="s" * 50,
    )
    assert command.price == Decimal("999999999999999.9999")
