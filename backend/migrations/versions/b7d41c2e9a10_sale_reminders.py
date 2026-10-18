"""sale reminders

Revision ID: b7d41c2e9a10
Revises: ac2f568ef723
Create Date: 2026-10-18 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7d41c2e9a10'
down_revision: Union[str, Sequence[str], None] = 'ac2f568ef723'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('sale_reminders',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('customer_id', sa.String(length=64), nullable=False),
    sa.Column('product_code', sa.String(length=16), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sale_reminders_customer_id'), 'sale_reminders', ['customer_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sale_reminders_customer_id'), table_name='sale_reminders')
    op.drop_table('sale_reminders')
