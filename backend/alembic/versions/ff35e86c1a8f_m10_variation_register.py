"""m10_variation_register

Revision ID: ff35e86c1a8f
Revises: fce3d69adadb
Create Date: 2026-08-04 07:23:45.597826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ff35e86c1a8f'
down_revision: Union[str, None] = 'fce3d69adadb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # add_column does not emit CREATE TYPE, so the enum is created explicitly
    variation_status = sa.Enum(
        'proposed', 'approved', 'rejected', name='variation_status'
    )
    variation_status.create(op.get_bind(), checkfirst=True)
    # server_default lets the NOT NULL column land on a table that already has
    # rows; the model supplies the default for new inserts.
    op.add_column(
        'boq_items',
        sa.Column(
            'variation_status',
            variation_status,
            nullable=False,
            server_default='proposed',
        ),
    )
    op.add_column('boq_items', sa.Column('variation_approved_date', sa.Date(), nullable=True))

    # Variations recorded before the register existed were already counting
    # toward the certifiable contract value — approving them preserves every
    # existing project's ceiling instead of silently shrinking it.
    op.execute(
        "UPDATE boq_items SET variation_status = 'approved' "
        "WHERE item_type IN ('variation', 'omission')"
    )


def downgrade() -> None:
    op.drop_column('boq_items', 'variation_approved_date')
    op.drop_column('boq_items', 'variation_status')
    sa.Enum(name='variation_status').drop(op.get_bind(), checkfirst=True)
