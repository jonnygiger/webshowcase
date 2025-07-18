"""Add Series and SeriesPost models and relationships

Revision ID: 696972611f5b
Revises: 62737c3cc70c
Create Date: 2025-06-20 05:52:20.558678

"""

from alembic import op
import sqlalchemy as sa


revision = "696972611f5b"
down_revision = "62737c3cc70c"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_activity", schema=None) as batch_op:
        batch_op.add_column(sa.Column("target_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_user_activity_target_user_id_user", "user", ["target_user_id"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("user_activity", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_user_activity_target_user_id_user", type_="foreignkey"
        )
        batch_op.drop_column("target_user_id")
