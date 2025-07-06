"""Add is_featured and featured_at to Post model

Revision ID: 92d11e6c7699
Revises: bba5afa636d8
Create Date: 2025-06-19 19:30:10.033217

"""

from alembic import op
import sqlalchemy as sa


revision = "92d11e6c7699"
down_revision = "bba5afa636d8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("post", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_featured", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("featured_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("post", schema=None) as batch_op:
        batch_op.drop_column("featured_at")
        batch_op.drop_column("is_featured")
