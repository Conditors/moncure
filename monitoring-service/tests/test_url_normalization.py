from uuid import uuid4

import pytest

from monitoring_service.contracts.collection import CollectionRequestedPayloadV1
from monitoring_service.url_normalization import normalize_product_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "HTTPS://Shop.Example:443/item?x=2&x=1#reviews",
            "https://shop.example/item?x=2&x=1",
        ),
        ("http://Example.COM:80", "http://example.com/"),
        ("https://пример.рф:8443/Товар", "https://xn--e1afmkfd.xn--p1ai:8443/Товар"),
        ("https://[2001:0db8::1]:443", "https://[2001:db8::1]/"),
        ("https://Shop-1.Example./a%20b", "https://shop-1.example./a%20b"),
        ("http://127.0.0.1:8080", "http://127.0.0.1:8080/"),
    ],
)
def test_normalize_product_url(url: str, expected: str) -> None:
    assert normalize_product_url(url) == expected


def test_unicode_hostname_matches_its_ascii_form_without_merging_distinct_sites() -> (
    None
):
    unicode_url = normalize_product_url("https://faß.de/product")
    ascii_url = normalize_product_url("https://xn--fa-hia.de/product")
    other_url = normalize_product_url("https://fass.de/product")

    assert unicode_url == ascii_url == "https://xn--fa-hia.de/product"
    assert other_url == "https://fass.de/product"


@pytest.mark.parametrize(
    "url",
    [
        "",
        " https://example.com",
        "https://example.com/a b",
        "https://example.com/a\x00",
        "https://example.com/a\\b",
        "ftp://example.com/item",
        "https:///item",
        "https://user:secret@example.com/",
        "https://example.com:99999/",
    ],
)
def test_reject_invalid_product_url(url: str) -> None:
    with pytest.raises(ValueError):
        normalize_product_url(url)


@pytest.mark.parametrize(
    "hostname",
    [
        "exam%zzple.com",
        "bad_host.example",
        "-example.com",
        "example-.com",
        "example..com",
        ".".join(["a" * 63] * 4),
    ],
)
def test_reject_invalid_dns_hostname(hostname: str) -> None:
    with pytest.raises(ValueError, match="URL hostname is invalid"):
        normalize_product_url(f"https://{hostname}/")


def test_normalized_url_byte_limit_and_outbox_payload() -> None:
    url = "https://example.com/" + "я" * 990
    assert len(url.encode("utf-8")) == 2000
    payload = CollectionRequestedPayloadV1(
        job_id=uuid4(), job_kind="IMPORT_JOB", url=normalize_product_url(url)
    )
    assert payload.model_dump(mode="json")["url"] == url

    with pytest.raises(ValueError, match="2000 bytes"):
        normalize_product_url(url + "a")
