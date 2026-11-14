"""widen api key prefix

Revision ID: eaa84550efb0
Revises: 7524363447e0
Create Date: 2026-11-14 07:33:29.921284
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'eaa84550efb0'
down_revision: str | None = '7524363447e0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # API keys are stored with a 16-character prefix ("ak_live_" + 8 hex). SQLite never enforced the old
    # VARCHAR(12); PostgreSQL rejects the insert, so creating an API key failed there.
    with op.batch_alter_table("api_keys") as batch:
        batch.alter_column("key_prefix", existing_type=sa.String(12), type_=sa.String(24), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("api_keys") as batch:
        batch.alter_column("key_prefix", existing_type=sa.String(24), type_=sa.String(12), existing_nullable=False)
