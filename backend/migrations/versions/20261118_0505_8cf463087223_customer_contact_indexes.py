"""customer contact indexes

Revision ID: 8cf463087223
Revises: 9f076a3ea829
Create Date: 2026-11-18 05:05:26.117487

customers.mobile / customers.email indexes: a patient signing in with a one-time code finds the bookings made with
that mobile number or email at every clinic (app/services/customer_link.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = '8cf463087223'
down_revision: Union[str, None] = '9f076a3ea829'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.create_index('ix_customers_email', ['email'], unique=False)
        batch_op.create_index('ix_customers_mobile', ['mobile'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.drop_index('ix_customers_mobile')
        batch_op.drop_index('ix_customers_email')
