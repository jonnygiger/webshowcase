"""add profile_picture to user

Revision ID: 4f7e54fbdfeb
Revises: 2b3e91311123
Create Date: 2025-06-19 16:36:39.002135

"""

from alembic import op
import sqlalchemy as sa


revision = "4f7e54fbdfeb"
down_revision = "2b3e91311123"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("profile_picture", sa.String(length=255), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("profile_picture")
