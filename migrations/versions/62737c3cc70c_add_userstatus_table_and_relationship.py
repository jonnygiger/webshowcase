"""add_userstatus_table_and_relationship

Revision ID: 62737c3cc70c
Revises: c5ef2f9a13b2
Create Date: 2025-06-19 21:48:46.673111

"""

from alembic import op
import sqlalchemy as sa


revision = "62737c3cc70c"
down_revision = "c5ef2f9a13b2"
branch_labels = None
depends_on = None


def upgrade():
    # op.create_table('shared_file',
    # sa.Column('id', sa.Integer(), nullable=False),
    # sa.Column('sender_id', sa.Integer(), nullable=False),
    # sa.Column('receiver_id', sa.Integer(), nullable=False),
    # sa.Column('original_filename', sa.String(length=255), nullable=False),
    # sa.Column('saved_filename', sa.String(length=255), nullable=False),
    # sa.Column('upload_timestamp', sa.DateTime(), nullable=False),
    # sa.Column('is_read', sa.Boolean(), nullable=False),
    # sa.Column('message', sa.Text(), nullable=True),
    # sa.ForeignKeyConstraint(['receiver_id'], ['user.id'], ),
    # sa.ForeignKeyConstraint(['sender_id'], ['user.id'], ),
    # sa.PrimaryKeyConstraint('id'),
    # sa.UniqueConstraint('saved_filename')
    # )
    op.create_table(
        "user_status",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status_text", sa.String(length=280), nullable=True),
        sa.Column("emoji", sa.String(length=10), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # with op.batch_alter_table('user_activity', schema=None) as batch_op:
    #     batch_op.add_column(sa.Column('target_user_id', sa.Integer(), nullable=True))
    #     batch_op.create_foreign_key('fk_user_activity_user_target_user_id', 'user', ['target_user_id'], ['id'])


def downgrade():
    # with op.batch_alter_table('user_activity', schema=None) as batch_op:
    #     batch_op.drop_constraint('fk_user_activity_user_target_user_id', type_='foreignkey')
    #     batch_op.drop_column('target_user_id')

    op.drop_table("user_status")
    # op.drop_table('shared_file')
