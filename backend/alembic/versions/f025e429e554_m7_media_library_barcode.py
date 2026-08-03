"""m7_media_library_barcode

Revision ID: f025e429e554
Revises: 90d84fa6a884
Create Date: 2026-08-03 17:16:33.305960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f025e429e554'
down_revision: Union[str, None] = '90d84fa6a884'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('media_files',
    sa.Column('entity_type', sa.String(length=30), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('folder', sa.Enum('drawings', 'contracts', 'permits', 'photos', 'reports', 'other', name='media_folder'), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('file_path', sa.String(length=500), nullable=False),
    sa.Column('thumb_path', sa.String(length=500), nullable=True),
    sa.Column('file_sha256', sa.String(length=64), nullable=False),
    sa.Column('media_type', sa.String(length=100), nullable=False),
    sa.Column('file_size', sa.Integer(), nullable=False),
    sa.Column('caption', sa.String(length=255), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_media_files_created_by_users'), ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media_files'))
    )
    op.create_index('ix_media_files_entity', 'media_files', ['entity_type', 'entity_id'], unique=False)
    op.create_index('ix_media_files_sha256', 'media_files', ['file_sha256'], unique=False)
    op.add_column('stock_items', sa.Column('barcode', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_stock_items_barcode'), 'stock_items', ['barcode'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_stock_items_barcode'), table_name='stock_items')
    op.drop_column('stock_items', 'barcode')
    op.drop_index('ix_media_files_sha256', table_name='media_files')
    op.drop_index('ix_media_files_entity', table_name='media_files')
    op.drop_table('media_files')
    sa.Enum(name='media_folder').drop(op.get_bind(), checkfirst=True)
