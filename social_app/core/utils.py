import os
import random
from functools import wraps
from datetime import datetime, timezone
from flask import current_app, flash, redirect, url_for, session, request
from flask_login import current_user

from .. import db
from ..models.db_models import User, Post, Notification, Event, Poll


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[0] != ""
        and filename.rsplit(".", 1)[1].lower()
        in current_app.config["ALLOWED_EXTENSIONS"]
    )


def allowed_shared_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[0] != ""
        and filename.rsplit(".", 1)[1].lower()
        in current_app.config["SHARED_FILES_ALLOWED_EXTENSIONS"]
    )


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("You need to be logged in to access this page.", "danger")
            session["next_url"] = request.url
            return redirect(url_for("core.login", next=request.url))
        return f(*args, **kwargs)

    return decorated_function


def moderator_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not hasattr(current_user, "role") or current_user.role != "moderator":
            flash(
                "You do not have permission to access this page. Moderator access required.",
                "danger",
            )
            return redirect(url_for("core.hello_world"))
        return f(*args, **kwargs)

    return decorated_function


def get_featured_post():
    """
    Retrieves or sets a featured post.
    - If multiple featured posts exist, picks the one with the most recent featured_at.
    - If no post is featured, selects a random post, features it, and sets featured_at.
    - Returns None if no posts exist in the database.
    """
    featured_post = (
        Post.query.filter_by(is_featured=True).order_by(Post.featured_at.desc()).first()
    )

    if featured_post:
        return featured_post
    else:
        all_posts = Post.query.all()
        if not all_posts:
            return None

        random_post_selected = random.choice(all_posts)
        random_post_selected.is_featured = True
        random_post_selected.featured_at = datetime.now(timezone.utc)
        db.session.add(random_post_selected)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error setting random post as featured: {e}")
            return None
        return random_post_selected


def nl2br(value):
    """Converts newlines in a string to HTML <br> tags."""
    if not isinstance(value, str):
        return value
    return value.replace("\n", "<br>\n")


def generate_activity_summary():
    """
    Checks for new posts, events, and polls since the last check
    and creates notifications for them.
    This function MUST be run within an application context.
    """
    if not hasattr(current_app, "last_activity_check_time"):
        current_app.logger.warning(
            "generate_activity_summary: current_app.last_activity_check_time not set. Initializing to 5 minutes ago."
        )
        current_app.last_activity_check_time = datetime.now(
            timezone.utc
        ) - timezone.timedelta(minutes=5)

    last_check_time = current_app.last_activity_check_time
    current_check_time = datetime.now(timezone.utc)
    new_notifications_added = False
    notifications_created_count = 0

    new_posts = Post.query.filter(
        Post.timestamp > last_check_time, Post.timestamp <= current_check_time
    ).all()
    for post in new_posts:
        notification = Notification(
            message=f"New blog post: '{post.title}'",
            type="new_post",
            related_id=post.id,
            timestamp=post.timestamp,
        )
        db.session.add(notification)
        new_notifications_added = True
        notifications_created_count += 1

    new_events = Event.query.filter(
        Event.created_at > last_check_time, Event.created_at <= current_check_time
    ).all()
    for event in new_events:
        notification = Notification(
            message=f"New event: '{event.title}'",
            type="new_event",
            related_id=event.id,
            timestamp=event.created_at,
        )
        db.session.add(notification)
        new_notifications_added = True
        notifications_created_count += 1

    new_polls = Poll.query.filter(
        Poll.created_at > last_check_time, Poll.created_at <= current_check_time
    ).all()
    for poll in new_polls:
        notification = Notification(
            message=f"New poll: '{poll.question}'",
            type="new_poll",
            related_id=poll.id,
            timestamp=poll.created_at,
        )
        db.session.add(notification)
        new_notifications_added = True
        notifications_created_count += 1

    if new_notifications_added:
        try:
            db.session.commit()
            current_app.logger.info(
                f"Activity summary generated. {notifications_created_count} new notifications created."
            )
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(
                f"Error committing new notifications during activity summary: {e}"
            )
    else:
        current_app.logger.info("Activity summary generated. No new notifications.")

    current_app.last_activity_check_time = current_check_time


def custom_url_for_assets(endpoint, **values):
    """Custom URL helper for assets. Currently a passthrough to flask.url_for."""
    return url_for(endpoint, **values)


def custom_url_for_primary(endpoint, **values):
    """Custom URL helper for primary application links. Currently a passthrough to flask.url_for."""
    return url_for(endpoint, **values)


def is_armstrong_number(n):
    """
    Checks if a number is an Armstrong number.
    An Armstrong number is a number that is the sum of its own digits each raised to the power of the number of digits.
    """
    if not isinstance(n, int) or n < 0:
        return False
    s = str(n)
    num_digits = len(s)
    return n == sum(int(digit) ** num_digits for digit in s)
