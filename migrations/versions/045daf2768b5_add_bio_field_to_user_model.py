"""Add bio field to User model

Revision ID: 045daf2768b5
Revises: 920040377a14
Create Date: 2025-06-19 17:35:45.336291

"""

from alembic import op
import sqlalchemy as sa


revision = "045daf2768b5"
down_revision = "920040377a14"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("bio", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("bio")
