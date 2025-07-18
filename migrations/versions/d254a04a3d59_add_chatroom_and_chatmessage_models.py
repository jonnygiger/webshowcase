"""add chatroom and chatmessage models

Revision ID: d254a04a3d59
Revises: 696972611f5b
Create Date: 2025-06-22 13:22:46.469683

"""

from alembic import op
import sqlalchemy as sa


revision = "d254a04a3d59"
down_revision = "696972611f5b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "achievement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon_url", sa.String(length=255), nullable=True),
        sa.Column("criteria_type", sa.String(length=50), nullable=False),
        sa.Column("criteria_value", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "chat_room",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("creator_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "shared_file",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("receiver_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("saved_filename", sa.String(length=255), nullable=False),
        sa.Column("upload_timestamp", sa.DateTime(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["receiver_id"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("saved_filename"),
    )
    op.create_table(
        "user_achievement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("achievement_id", sa.Integer(), nullable=False),
        sa.Column("awarded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["achievement_id"],
            ["achievement.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "achievement_id", name="_user_achievement_uc"),
    )
    op.create_table(
        "user_block",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False),
        sa.Column("blocked_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "blocker_id != blocked_id", name="ck_blocker_not_blocked_self"
        ),
        sa.ForeignKeyConstraint(
            ["blocked_id"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["blocker_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_blocker_blocked"),
    )
    op.create_table(
        "chat_message",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["chat_room.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "post_lock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["post.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id"),
    )
    op.create_table(
        "series_posts",
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["post.id"],
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.PrimaryKeyConstraint("series_id", "post_id"),
    )
    with op.batch_alter_table("event", schema=None) as batch_op:
        batch_op.alter_column(
            "date",
            existing_type=sa.VARCHAR(length=50),
            type_=sa.DateTime(),
            existing_nullable=False,
        )
        batch_op.drop_column("time")

    with op.batch_alter_table("event_rsvp", schema=None) as batch_op:
        batch_op.add_column(sa.Column("timestamp", sa.DateTime(), nullable=False))

    with op.batch_alter_table("like", schema=None) as batch_op:
        batch_op.add_column(sa.Column("timestamp", sa.DateTime(), nullable=False))

    with op.batch_alter_table("poll_vote", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=False))

    with op.batch_alter_table("post", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("image_url", sa.String(length=255), nullable=True)
        )

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.VARCHAR(length=128),
            type_=sa.String(length=255),
            existing_nullable=False,
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=255),
            type_=sa.VARCHAR(length=128),
            existing_nullable=False,
        )

    with op.batch_alter_table("post", schema=None) as batch_op:
        batch_op.drop_column("image_url")

    with op.batch_alter_table("poll_vote", schema=None) as batch_op:
        batch_op.drop_column("created_at")

    with op.batch_alter_table("like", schema=None) as batch_op:
        batch_op.drop_column("timestamp")

    with op.batch_alter_table("event_rsvp", schema=None) as batch_op:
        batch_op.drop_column("timestamp")

    with op.batch_alter_table("event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("time", sa.VARCHAR(length=50), nullable=True))
        batch_op.alter_column(
            "date",
            existing_type=sa.DateTime(),
            type_=sa.VARCHAR(length=50),
            existing_nullable=False,
        )

    op.drop_table("series_posts")
    op.drop_table("post_lock")
    op.drop_table("chat_message")
    op.drop_table("user_block")
    op.drop_table("user_achievement")
    op.drop_table("shared_file")
    op.drop_table("series")
    op.drop_table("chat_room")
    op.drop_table("achievement")
