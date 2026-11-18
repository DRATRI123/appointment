"""patient help desk

Revision ID: 4bc67cb6ee71
Revises: 8cf463087223
Create Date: 2026-11-18 06:32:12.643388

support_tickets / support_messages: patients' questions to their clinic and the conversation (message text encrypted
at rest; app/services/helpdesk_service.py).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '4bc67cb6ee71'
down_revision: Union[str, None] = '8cf463087223'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('support_tickets',
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('requester_user_id', sa.Integer(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('appointment_id', sa.Integer(), nullable=True),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('subject', sa.String(length=160), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('priority', sa.String(length=16), nullable=False),
    sa.Column('assigned_to_user_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('first_response_due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_response_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_customer_message_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_staff_message_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('unread_by_customer', sa.Boolean(), nullable=False),
    sa.Column('unread_by_staff', sa.Boolean(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('public_id', sa.String(length=36), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], name=op.f('fk_support_tickets_appointment_id_appointments'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['assigned_to_user_id'], ['users.id'], name=op.f('fk_support_tickets_assigned_to_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], name=op.f('fk_support_tickets_branch_id_branches'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_support_tickets_customer_id_customers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_support_tickets_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requester_user_id'], ['users.id'], name=op.f('fk_support_tickets_requester_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_support_tickets')),
    sa.UniqueConstraint('organization_id', 'number', name='uq_support_tickets_org_number')
    )
    with op.batch_alter_table('support_tickets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_support_tickets_assigned_to_user_id'), ['assigned_to_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_tickets_branch_id'), ['branch_id'], unique=False)
        batch_op.create_index('ix_support_tickets_org_customer', ['organization_id', 'customer_id'], unique=False)
        batch_op.create_index('ix_support_tickets_org_status_activity', ['organization_id', 'status', 'last_activity_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_tickets_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_tickets_public_id'), ['public_id'], unique=True)

    op.create_table('support_messages',
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('author_user_id', sa.Integer(), nullable=True),
    sa.Column('author_kind', sa.String(length=16), nullable=False),
    sa.Column('internal', sa.Boolean(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('attachment_key', sa.String(length=500), nullable=True),
    sa.Column('attachment_name', sa.String(length=160), nullable=True),
    sa.Column('attachment_mime', sa.String(length=80), nullable=True),
    sa.Column('attachment_size', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('public_id', sa.String(length=36), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], name=op.f('fk_support_messages_author_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_support_messages_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], name=op.f('fk_support_messages_ticket_id_support_tickets'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_support_messages'))
    )
    with op.batch_alter_table('support_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_support_messages_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_messages_public_id'), ['public_id'], unique=True)
        batch_op.create_index('ix_support_messages_ticket_created', ['ticket_id', 'created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('support_messages', schema=None) as batch_op:
        batch_op.drop_index('ix_support_messages_ticket_created')
        batch_op.drop_index(batch_op.f('ix_support_messages_public_id'))
        batch_op.drop_index(batch_op.f('ix_support_messages_organization_id'))

    op.drop_table('support_messages')
    with op.batch_alter_table('support_tickets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_support_tickets_public_id'))
        batch_op.drop_index(batch_op.f('ix_support_tickets_organization_id'))
        batch_op.drop_index('ix_support_tickets_org_status_activity')
        batch_op.drop_index('ix_support_tickets_org_customer')
        batch_op.drop_index(batch_op.f('ix_support_tickets_branch_id'))
        batch_op.drop_index(batch_op.f('ix_support_tickets_assigned_to_user_id'))

    op.drop_table('support_tickets')