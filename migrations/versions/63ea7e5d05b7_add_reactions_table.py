"""add reactions table

Revision ID: 63ea7e5d05b7
Revises: 4f7e54fbdfeb
Create Date: 2025-06-19 16:46:33.043987

"""

from alembic import op
import sqlalchemy as sa


revision = "63ea7e5d05b7"
down_revision = "4f7e54fbdfeb"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reaction",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("emoji", sa.String(length=10), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["post.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("reaction")
