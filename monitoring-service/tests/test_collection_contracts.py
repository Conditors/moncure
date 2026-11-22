import json
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from monitoring_service.contracts.collection import (
    CollectionCompletedV1,
    CollectionFailedV1,
    CollectionRequestedV1,
    CollectionSucceededV1,
)

result_adapter = TypeAdapter[CollectionCompletedV1](CollectionCompletedV1)


def result_message() -> dict[str, object]:
    return {
        "message_id": str(uuid4()),
        "contract_version": 1,
        "job_id": str(uuid4()),
        "job_kind": "IMPORT_JOB",
        "completed_at": "2026-11-10T17:00:10Z",
    }


def product_data(**changes: object) -> dict[str, object]:
    return {
        "name": "iPhone 16",
        "price": "74990.00",
        "currency": "RUB",
        "availability_status": "AVAILABLE",
        **changes,
    }


def test_collection_request_stays_flat_on_wire() -> None:
    message = result_message()
    message["requested_at"] = message.pop("completed_at")
    message["url"] = "https://example.com/product"
    request = CollectionRequestedV1.model_validate(message)
    assert request.model_dump(mode="json") == message


def test_parse_success_and_failure_by_status() -> None:
    success = result_adapter.validate_json(
        json.dumps(
            dict(result_message(), status="SUCCESS", data=product_data(), error=None)
        )
    )
    assert isinstance(success, CollectionSucceededV1)
    assert success.data.price == Decimal("74990.00")
    assert success.model_dump(mode="json")["data"]["price"] == "74990.00"

    failure = result_adapter.validate_python(
        dict(
            result_message(),
            status="FAILED",
            data=None,
            error={"code": "PRICE_NOT_FOUND", "message": "Price not found"},
        )
    )
    assert isinstance(failure, CollectionFailedV1)
    assert failure.error.code == "PRICE_NOT_FOUND"


@pytest.mark.parametrize("availability", ["OUT_OF_STOCK", "UNAVAILABLE"])
def test_unavailable_product_can_have_no_price(availability: str) -> None:
    result = result_adapter.validate_python(
        dict(
            result_message(),
            status="SUCCESS",
            data=product_data(
                price=None, currency=None, availability_status=availability
            ),
            error=None,
        )
    )
    assert isinstance(result, CollectionSucceededV1)
    assert result.data.price is None


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "OTHER"},
        {"contract_version": 2},
        {"contract_version": True},
        {"contract_version": 1.0},
        {"job_kind": "UNKNOWN"},
        {"completed_at": "2026-11-10T17:00:10"},
        {"completed_at": 1},
        {"completed_at": "1"},
        {"error": {"code": "BROKEN", "message": "Unexpected error"}},
        {"data": None},
        {"data": product_data(price=None, currency=None)},
        {"data": product_data(currency=None)},
        {"data": product_data(price=12.34)},
        {"data": product_data(price="0")},
        {"data": product_data(price="1.00001")},
        {"data": product_data(price="1000000000000000")},
        {"data": product_data(currency="rub")},
        {"data": product_data(article="IP16")},
        {"data": product_data(name=" ")},
    ],
)
def test_reject_invalid_collection_result(changes: dict[str, object]) -> None:
    message = dict(result_message(), status="SUCCESS", data=product_data(), error=None)
    message.update(changes)
    with pytest.raises(ValidationError):
        result_adapter.validate_python(message)


def test_failed_message_requires_nonempty_error_and_null_data() -> None:
    message = dict(result_message(), status="FAILED", error=None, data=None)
    for changes in (
        {},
        {"error": {"code": " ", "message": "Price not found"}},
        {"error": {"code": "X" * 51, "message": "Price not found"}},
        {
            "error": {"code": "PRICE_NOT_FOUND", "message": "Price not found"},
            "data": product_data(),
        },
    ):
        with pytest.raises(ValidationError):
            result_adapter.validate_python({**message, **changes})


@pytest.mark.parametrize(
    ("status", "field"),
    [
        ("SUCCESS", "name"),
        ("SUCCESS", "article"),
        ("SUCCESS", "source"),
        ("FAILED", "code"),
        ("FAILED", "message"),
    ],
)
def test_reject_nul_in_persisted_text(status: str, field: str) -> None:
    invalid = {field: "before\x00after"}
    if status == "SUCCESS":
        data = product_data(**({"source": "Store"} | invalid))
        message = dict(result_message(), status="SUCCESS", data=data, error=None)
    else:
        error = {"code": "TIMEOUT", "message": "Timed out"} | invalid
        message = dict(result_message(), status="FAILED", data=None, error=error)

    with pytest.raises(ValidationError, match="NUL"):
        result_adapter.validate_python(message)
