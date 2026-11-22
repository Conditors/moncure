from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit

import idna

MAX_NORMALIZED_URL_BYTES = 2000


def normalize_product_url(value: str) -> str:
    """Normalize HTTP(S) URLs using IDNA 2008 for DNS hosts."""
    if not value or value != value.strip():
        raise ValueError(
            "URL must be non-empty and must not contain surrounding whitespace"
        )
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError("URL must not contain whitespace or control characters")
    if "\\" in value:
        raise ValueError("URL must not contain backslashes")

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("URL scheme must be HTTP or HTTPS")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URL credentials are not allowed")

    hostname = parts.hostname
    if hostname is None:
        raise ValueError("URL hostname is required")

    try:
        port = parts.port
    except ValueError as error:
        raise ValueError("URL port is invalid") from error

    try:
        address = ip_address(hostname)
    except ValueError:
        try:
            normalized_host = idna.encode(hostname, uts46=True, std3_rules=True).decode(
                "ascii"
            )
        except idna.IDNAError as error:
            raise ValueError("URL hostname is invalid") from error
    else:
        normalized_host = address.compressed.lower()
        if address.version == 6:
            normalized_host = f"[{normalized_host}]"

    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    netloc = (
        normalized_host if port is None or default_port else f"{normalized_host}:{port}"
    )
    normalized_url = urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))

    if len(normalized_url.encode("utf-8")) > MAX_NORMALIZED_URL_BYTES:
        raise ValueError("normalized URL exceeds 2000 bytes")
    return normalized_url
