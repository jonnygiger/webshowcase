"""add_shared_post_table

Revision ID: 920040377a14
Revises: 37d84462ae65
Create Date: 2025-06-19 17:18:04.858746

"""

from alembic import op
import sqlalchemy as sa


revision = "920040377a14"
down_revision = "37d84462ae65"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shared_post",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("original_post_id", sa.Integer(), nullable=False),
        sa.Column("shared_by_user_id", sa.Integer(), nullable=False),
        sa.Column("shared_at", sa.DateTime(), nullable=False),
        sa.Column("sharing_user_comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["original_post_id"],
            ["post.id"],
        ),
        sa.ForeignKeyConstraint(
            ["shared_by_user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("shared_post")
