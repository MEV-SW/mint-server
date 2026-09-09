"""Add nullable category_id FK on sources, linking to news_categories.

Revision ID: 015
Revises: 014
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("category_id", UUID, sa.ForeignKey("news_categories.id"), nullable=True),
    )
    op.create_index("ix_sources_category_id", "sources", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_sources_category_id", table_name="sources")
    op.drop_column("sources", "category_id")
