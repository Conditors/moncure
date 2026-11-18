"""add own product import invariants

Revision ID: a90ae4f1899a
Revises: e0663fe559fe
Create Date: 2026-11-18 22:41:09.456550

"""

from collections.abc import Sequence
from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a90ae4f1899a"
down_revision: str | Sequence[str] | None = "e0663fe559fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_MAX_NORMALIZED_URL_BYTES = 2000
_ACTIVE_OWN_IMPORT_PREDICATE = sa.text(
    "job_type = 'own_product_import' "
    "AND status IN ('pending', 'processing', 'ready_for_review')"
)


def _normalize_url_v1(value: str) -> str:
    """Frozen URL normalization used only by this migration."""
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
            normalized_host = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as error:
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

    if len(normalized_url.encode("utf-8")) > _MAX_NORMALIZED_URL_BYTES:
        raise ValueError("normalized URL exceeds 2000 bytes")
    return normalized_url


def _backfill_normalized_urls(connection: Connection) -> None:
    product_rows = connection.execute(
        sa.text("SELECT id, url FROM products WHERE url IS NOT NULL ORDER BY id")
    ).mappings()
    for row in product_rows:
        try:
            normalized_url = _normalize_url_v1(row["url"])
        except ValueError as error:
            raise RuntimeError(
                f"cannot normalize products.url for product {row['id']}: {error}"
            ) from error
        connection.execute(
            sa.text(
                "UPDATE products SET normalized_url = :normalized_url WHERE id = :id"
            ),
            {"id": row["id"], "normalized_url": normalized_url},
        )

    import_rows = connection.execute(
        sa.text("SELECT id, url FROM import_jobs ORDER BY id")
    ).mappings()
    for row in import_rows:
        try:
            normalized_url = _normalize_url_v1(row["url"])
        except ValueError as error:
            raise RuntimeError(
                f"cannot normalize import_jobs.url for import job {row['id']}: {error}"
            ) from error
        connection.execute(
            sa.text(
                "UPDATE import_jobs SET normalized_url = :normalized_url WHERE id = :id"
            ),
            {"id": row["id"], "normalized_url": normalized_url},
        )


def _raise_for_incompatible_legacy_data(connection: Connection) -> None:
    completed_own_import = connection.execute(
        sa.text(
            "SELECT id FROM import_jobs "
            "WHERE job_type = 'own_product_import' AND status = 'completed' "
            "LIMIT 1"
        )
    ).scalar_one_or_none()
    if completed_own_import is not None:
        raise RuntimeError(
            "cannot infer created_product_id for completed own-product import job "
            f"{completed_own_import}"
        )

    duplicate_product = (
        connection.execute(
            sa.text(
                "SELECT organization_id, normalized_url, array_agg(id ORDER BY id) AS ids "
                "FROM products WHERE normalized_url IS NOT NULL "
                "GROUP BY organization_id, normalized_url HAVING count(*) > 1 LIMIT 1"
            )
        )
        .mappings()
        .first()
    )
    if duplicate_product is not None:
        raise RuntimeError(
            "duplicate normalized product URL found for organization "
            f"{duplicate_product['organization_id']}: {duplicate_product['ids']}"
        )

    duplicate_active_import = (
        connection.execute(
            sa.text(
                "SELECT organization_id, normalized_url, array_agg(id ORDER BY id) AS ids "
                "FROM import_jobs "
                "WHERE job_type = 'own_product_import' "
                "AND status IN ('pending', 'processing', 'ready_for_review') "
                "GROUP BY organization_id, normalized_url HAVING count(*) > 1 LIMIT 1"
            )
        )
        .mappings()
        .first()
    )
    if duplicate_active_import is not None:
        raise RuntimeError(
            "duplicate active own-product imports found for organization "
            f"{duplicate_active_import['organization_id']}: "
            f"{duplicate_active_import['ids']}"
        )

    product_import_conflict = (
        connection.execute(
            sa.text(
                "SELECT p.id AS product_id, j.id AS import_job_id "
                "FROM products AS p JOIN import_jobs AS j "
                "ON j.organization_id = p.organization_id "
                "AND j.normalized_url = p.normalized_url "
                "WHERE j.job_type = 'own_product_import' "
                "AND j.status IN ('pending', 'processing', 'ready_for_review') "
                "LIMIT 1"
            )
        )
        .mappings()
        .first()
    )
    if product_import_conflict is not None:
        raise RuntimeError(
            "active own-product import already has a matching product: "
            f"product={product_import_conflict['product_id']}, "
            f"import_job={product_import_conflict['import_job_id']}"
        )


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "import_jobs",
        sa.Column("created_product_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "import_jobs",
        sa.Column("result_observed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("normalized_url", sa.Text(), nullable=True),
    )

    connection = op.get_bind()
    _backfill_normalized_urls(connection)
    _raise_for_incompatible_legacy_data(connection)

    op.create_check_constraint(
        "ck_import_jobs_created_product",
        "import_jobs",
        """
        (
            job_type = 'own_product_import'
            AND (
                (status = 'completed' AND created_product_id IS NOT NULL)
                OR
                (status <> 'completed' AND created_product_id IS NULL)
            )
        )
        OR
        (
            job_type = 'competitor_offer_import'
            AND created_product_id IS NULL
        )
        """,
    )
    op.create_check_constraint(
        "ck_import_jobs_normalized_url_length",
        "import_jobs",
        "octet_length(normalized_url) <= 2000",
    )
    op.create_unique_constraint(
        "uq_import_jobs_created_product",
        "import_jobs",
        ["organization_id", "created_product_id"],
    )
    op.create_foreign_key(
        "fk_import_jobs_created_product",
        "import_jobs",
        "products",
        ["organization_id", "created_product_id"],
        ["organization_id", "id"],
    )
    op.create_index(
        "uq_import_jobs_active_own_url",
        "import_jobs",
        ["organization_id", "normalized_url"],
        unique=True,
        postgresql_where=_ACTIVE_OWN_IMPORT_PREDICATE,
    )

    op.create_check_constraint(
        "ck_products_url_normalized_url",
        "products",
        "(url IS NULL) = (normalized_url IS NULL)",
    )
    op.create_check_constraint(
        "ck_products_normalized_url_length",
        "products",
        "normalized_url IS NULL OR octet_length(normalized_url) <= 2000",
    )
    op.create_index(
        "uq_products_organization_normalized_url",
        "products",
        ["organization_id", "normalized_url"],
        unique=True,
        postgresql_where=sa.text("normalized_url IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_products_organization_normalized_url",
        table_name="products",
        postgresql_where=sa.text("normalized_url IS NOT NULL"),
    )
    op.drop_constraint(
        "ck_products_normalized_url_length",
        "products",
        type_="check",
    )
    op.drop_constraint(
        "ck_products_url_normalized_url",
        "products",
        type_="check",
    )
    op.drop_column("products", "normalized_url")

    op.drop_index(
        "uq_import_jobs_active_own_url",
        table_name="import_jobs",
        postgresql_where=_ACTIVE_OWN_IMPORT_PREDICATE,
    )
    op.drop_constraint(
        "fk_import_jobs_created_product",
        "import_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_import_jobs_created_product",
        "import_jobs",
        type_="unique",
    )
    op.drop_constraint(
        "ck_import_jobs_normalized_url_length",
        "import_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_import_jobs_created_product",
        "import_jobs",
        type_="check",
    )
    op.drop_column("import_jobs", "result_observed_at")
    op.drop_column("import_jobs", "created_product_id")
