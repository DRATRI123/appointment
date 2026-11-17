"""embedded panel sessions

Revision ID: 9f076a3ea829
Revises: 09efabf3a653
Create Date: 2026-11-17 04:50:55.934954

user_sessions.panel_organization_id: a sign-in made inside a clinic's embedded admin panel (its own app shows the panel
in an iframe) works only for that clinic. Existing sessions are ordinary ones (NULL).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '9f076a3ea829'
down_revision: Union[str, None] = '09efabf3a653'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('panel_organization_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_user_sessions_panel_organization_id'), ['panel_organization_id'], unique=False)
        batch_op.create_foreign_key(batch_op.f('fk_user_sessions_panel_organization_id_organizations'), 'organizations', ['panel_organization_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_user_sessions_panel_organization_id_organizations'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_user_sessions_panel_organization_id'))
        batch_op.drop_column('panel_organization_id')
