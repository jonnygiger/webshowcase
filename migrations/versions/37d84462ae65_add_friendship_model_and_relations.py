"""add_friendship_model_and_relations

Revision ID: 37d84462ae65
Revises: 7d0b345391ad
Create Date: 2025-06-19 17:07:21.386761

"""

from alembic import op
import sqlalchemy as sa


revision = "37d84462ae65"
down_revision = "7d0b345391ad"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "friendship",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("friend_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.CheckConstraint("user_id != friend_id", name="ck_user_not_friend_self"),
        sa.ForeignKeyConstraint(
            ["friend_id"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "friend_id", name="uq_user_friend"),
    )


def downgrade():
    op.drop_table("friendship")
