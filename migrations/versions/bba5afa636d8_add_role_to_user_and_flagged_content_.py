"""add role to user and flagged_content table

Revision ID: bba5afa636d8
Revises: cadd_email_manually_to_user
Create Date: 2025-06-19 18:39:27.302394

"""

from alembic import op
import sqlalchemy as sa


revision = "bba5afa636d8"
down_revision = "cadd_email_manually_to_user"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "flagged_content",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("flagged_by_user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("moderator_id", sa.Integer(), nullable=True),
        sa.Column("moderator_comment", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["flagged_by_user_id"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["moderator_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_activity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("activity_type", sa.String(length=50), nullable=False),
        sa.Column("related_id", sa.Integer(), nullable=True),
        sa.Column("content_preview", sa.Text(), nullable=True),
        sa.Column("link", sa.String(length=255), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("post", schema=None) as batch_op:
        batch_op.add_column(sa.Column("hashtags", sa.Text(), nullable=True))

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("role", sa.String(length=80), nullable=False))


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("role")

    with op.batch_alter_table("post", schema=None) as batch_op:
        batch_op.drop_column("hashtags")

    op.drop_table("user_activity")
    op.drop_table("flagged_content")
