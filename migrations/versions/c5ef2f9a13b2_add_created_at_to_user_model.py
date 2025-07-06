"""Add created_at to User model

Revision ID: c5ef2f9a13b2
Revises: 92d11e6c7699
Create Date: 2025-06-19 20:56:04.947033

"""

from alembic import op
import sqlalchemy as sa


revision = "c5ef2f9a13b2"
down_revision = "92d11e6c7699"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trending_hashtag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hashtag", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("calculated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hashtag"),
    )
    op.create_table(
        "friend_post_notification",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("poster_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["post.id"],
        ),
        sa.ForeignKeyConstraint(
            ["poster_id"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("created_at")

    op.drop_table("friend_post_notification")
    op.drop_table("trending_hashtag")
