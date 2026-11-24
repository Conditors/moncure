"""Link completed competitor imports to their offers.

Revision ID: 9731dd4e572e
Revises: 6c8c7e53a48f
Create Date: 2026-11-24 11:01:19.818537

"""
import sqlalchemy as sa

from alembic import op

revision: str = "9731dd4e572e"
down_revision: str = "6c8c7e53a48f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "import_jobs",
        sa.Column("created_competitor_offer_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_import_jobs_created_competitor_offer",
        "import_jobs",
        "competitor_offers",
        ["organization_id", "target_product_id", "created_competitor_offer_id"],
        ["organization_id", "product_id", "id"],
    )
    op.create_check_constraint(
        "ck_import_jobs_created_competitor_offer",
        "import_jobs",
        """
        (job_type = 'competitor_offer_import' AND status = 'completed')
        = (created_competitor_offer_id IS NOT NULL)
        """,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_import_jobs_created_competitor_offer", "import_jobs", type_="check"
    )
    op.drop_constraint(
        "fk_import_jobs_created_competitor_offer", "import_jobs", type_="foreignkey"
    )
    op.drop_column("import_jobs", "created_competitor_offer_id")
