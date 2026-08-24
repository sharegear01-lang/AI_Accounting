"""initial tables: users, transactions

Revision ID: 9625f83c3ddd
Revises: 
Create Date: 2026-08-24 22:01:08.331778

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9625f83c3ddd'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    """检查表是否已存在（兼容历史 create_all 建的旧库，避免重复建表报错）"""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return insp.has_table(name)


def _index_exists(table: str, index: str) -> bool:
    """检查索引是否已存在（旧库由 create_all 一并创建）"""
    insp = sa.inspect(op.get_bind())
    return index in [i["name"] for i in insp.get_indexes(table)]


def upgrade() -> None:
    """Upgrade schema.

    幂等：表/索引已存在（旧库经 create_all 创建）时跳过，只登记 alembic_version。
    """
    if not _table_exists('transactions'):
        op.create_table('transactions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('merchant', sa.String(length=200), nullable=False),
    sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.Column('transaction_date', sa.Date(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('raw_ocr_text', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    if not _index_exists('transactions', 'ix_transactions_user_date'):
        op.create_index('ix_transactions_user_date', 'transactions', ['user_id', 'transaction_date'], unique=False)
    if not _index_exists('transactions', 'ix_transactions_user_id'):
        op.create_index('ix_transactions_user_id', 'transactions', ['user_id'], unique=False)
    if not _table_exists('users'):
        op.create_table('users',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('hashed_password', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    if not _index_exists('users', 'ix_users_username'):
        op.create_index('ix_users_username', 'users', ['username'], unique=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    if _table_exists('users'):
        op.drop_index('ix_users_username', table_name='users')
        op.drop_table('users')
    if _table_exists('transactions'):
        op.drop_index('ix_transactions_user_id', table_name='transactions')
        op.drop_index('ix_transactions_user_date', table_name='transactions')
        op.drop_table('transactions')
    # ### end Alembic commands ###
