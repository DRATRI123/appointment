"""privacy: session reauth and lock, signed audit rows, encrypted payer details

Revision ID: 73128aa5cd2f
Revises: 5ab13cfee58d
Create Date: 2026-11-16 03:31:25.987076

* user_sessions.reauthenticated_at / locked_at: re-authentication window and server-enforced screen lock.
* audit_logs.signature: HMAC of each row (tamper evidence; python -m app.ops.verify_audit). On PostgreSQL a trigger also
  refuses UPDATE and DELETE on audit_logs, so even the application cannot change history.
* payment_submissions.payer_upi_id / payer_name widened to TEXT: they now hold AES-256-GCM ciphertext (widening only;
  existing values are encrypted by the one-time step in app.ops.setup / python -m app.ops.rotate_keys).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '73128aa5cd2f'
down_revision: Union[str, None] = '5ab13cfee58d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPEND_ONLY = """
CREATE OR REPLACE FUNCTION audit_logs_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: history cannot be changed or deleted' USING ERRCODE = 'insufficient_privilege';
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs;
CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only();
"""


def upgrade() -> None:
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('signature', sa.String(length=64), nullable=True))

    with op.batch_alter_table('payment_submissions', schema=None) as batch_op:
        batch_op.alter_column('payer_upi_id', existing_type=sa.VARCHAR(length=120), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column('payer_name', existing_type=sa.VARCHAR(length=120), type_=sa.Text(), existing_nullable=True)

    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reauthenticated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True))

    if op.get_bind().dialect.name == "postgresql":
        op.execute(APPEND_ONLY)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs; DROP FUNCTION IF EXISTS audit_logs_append_only();")

    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_column('locked_at')
        batch_op.drop_column('reauthenticated_at')

    # payer_upi_id / payer_name stay TEXT: encrypted values do not fit the old 120 characters (no data is lost).

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_column('signature')
