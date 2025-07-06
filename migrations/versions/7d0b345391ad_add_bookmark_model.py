"""Add Bookmark model

Revision ID: 7d0b345391ad
Revises: 63ea7e5d05b7
Create Date: 2025-06-19 16:54:47.694023

"""

from alembic import op
import sqlalchemy as sa


revision = "7d0b345391ad"
down_revision = "63ea7e5d05b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bookmark",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["post.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "post_id", name="_user_post_bookmark_uc"),
    )


def downgrade():
    op.drop_table("bookmark")
