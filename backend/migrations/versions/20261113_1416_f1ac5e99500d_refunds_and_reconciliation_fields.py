"""refunds and reconciliation fields

Revision ID: f1ac5e99500d
Revises: 1fecdb0d7492
Create Date: 2026-11-13 14:16:25.007636
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f1ac5e99500d'
down_revision: str | None = '1fecdb0d7492'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    
    with op.batch_alter_table('bank_statement_imports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('duplicate_rows', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('skipped_rows', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('skipped', sa.JSON(), nullable=True))

    with op.batch_alter_table('bank_transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))

    with op.batch_alter_table('payment_refunds', schema=None) as batch_op:
        batch_op.add_column(sa.Column('destination', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True))

    


def downgrade() -> None:
    
    with op.batch_alter_table('payment_refunds', schema=None) as batch_op:
        batch_op.drop_column('rejected_at')
        batch_op.drop_column('destination')

    with op.batch_alter_table('bank_transactions', schema=None) as batch_op:
        batch_op.drop_column('notes')

    with op.batch_alter_table('bank_statement_imports', schema=None) as batch_op:
        batch_op.drop_column('skipped')
        batch_op.drop_column('skipped_rows')
        batch_op.drop_column('duplicate_rows')

    
