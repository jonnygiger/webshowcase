"""Add email field to User model

Revision ID: cadd_email_manually_to_user
Revises: 045daf2768b5
Create Date: 2025-06-19 18:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "cadd_email_manually_to_user"
down_revision = "045daf2768b5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=120), nullable=True))
        batch_op.create_unique_constraint("uq_user_email", ["email"])


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_constraint("uq_user_email", type_="unique")
        batch_op.drop_column("email")
