"""indexes for history queries

Revision ID: 00980d4f32e1
Revises: eaa84550efb0
Create Date: 2026-11-14 08:18:13.007644
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '00980d4f32e1'
down_revision: Union[str, None] = 'eaa84550efb0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _concurrently() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # On PostgreSQL, build without locking the tables against writes (a live clinic keeps taking bookings).
    # CONCURRENTLY cannot run inside a transaction, hence the autocommit block.
    if _concurrently():
        with op.get_context().autocommit_block():
            op.create_index("ix_appointments_org_customer_start", "appointments", ["organization_id", "customer_id", "start_at"],
                            postgresql_include=["status"], postgresql_concurrently=True, if_not_exists=True)
            op.create_index("ix_payments_org_verified", "payments", ["organization_id", "verified_at"], postgresql_concurrently=True, if_not_exists=True)
    else:
        op.create_index("ix_appointments_org_customer_start", "appointments", ["organization_id", "customer_id", "start_at"])
        op.create_index("ix_payments_org_verified", "payments", ["organization_id", "verified_at"])


def downgrade() -> None:
    if _concurrently():
        with op.get_context().autocommit_block():
            op.drop_index("ix_payments_org_verified", table_name="payments", postgresql_concurrently=True, if_exists=True)
            op.drop_index("ix_appointments_org_customer_start", table_name="appointments", postgresql_concurrently=True, if_exists=True)
    else:
        op.drop_index("ix_payments_org_verified", table_name="payments")
        op.drop_index("ix_appointments_org_customer_start", table_name="appointments")
