import os
import random
from functools import wraps
from datetime import datetime, timezone
from flask import current_app, flash, redirect, url_for, session
from flask_login import current_user

from .. import db # Assuming db is in social_app's __init__.py
# Models are likely needed by some utils, e.g., get_featured_post, moderator_required
from ..models.db_models import User, Post, Notification, Event, Poll # Add other models if needed by utils

# Helper function to check allowed file extensions for general uploads (e.g., gallery)
def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[0] != "" # Ensure filename is not just ".ext"
        and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]
    )

# Helper function to check allowed file extensions for shared files
def allowed_shared_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[0] != "" # Ensure filename is not just ".ext"
        and filename.rsplit(".", 1)[1].lower() in current_app.config["SHARED_FILES_ALLOWED_EXTENSIONS"]
    )

# Decorator for requiring login (adapted for Flask-Login's current_user)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("You need to be logged in to access this page.", "danger")
            # Store the intended destination in the session.
            # This is useful if your login page then redirects back to the originally requested page.
            # session['next'] = request.url # Requires `from flask import request`
            return redirect(url_for("core.login")) # Assuming login route is core.login
        return f(*args, **kwargs)
    return decorated_function

# Decorator for requiring moderator role (adapted for Flask-Login's current_user)
def moderator_required(f):
    @wraps(f)
    @login_required # Ensures user is logged in first
    def decorated_function(*args, **kwargs):
        # current_user is already authenticated due to @login_required
        if not hasattr(current_user, 'role') or current_user.role != "moderator":
            flash("You do not have permission to access this page. Moderator access required.", "danger")
            # Redirect to home or a more appropriate page if not login.
            # If login_required already handles unauthenticated users, this will primarily catch logged-in non-moderators.
            return redirect(url_for("core.hello_world")) # Or where non-privileged users should go
        return f(*args, **kwargs)
    return decorated_function

# Function to get or set a featured post
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

        random_post_selected = random.choice(all_posts) # Renamed to avoid conflict
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

# Custom Jinja2 filter for nl2br (function part, registration happens in app setup)
def nl2br(value):
    """Converts newlines in a string to HTML <br> tags."""
    if not isinstance(value, str):
        return value
    return value.replace("\n", "<br>\n")


# Function to generate activity summary (intended for scheduler)
# This function needs app context to run if called by scheduler outside of one.
def generate_activity_summary():
    """
    Checks for new posts, events, and polls since the last check
    and creates notifications for them.
    This function MUST be run within an application context.
    """
    # Ensure this function is called within an app context if run by scheduler.
    # The run.py or scheduler setup should handle this.
    # Example: with app.app_context(): generate_activity_summary()

    # `current_app.last_activity_check_time` needs to be initialized on app creation
    # and updated by this function.
    if not hasattr(current_app, 'last_activity_check_time'):
        current_app.logger.error("generate_activity_summary: current_app.last_activity_check_time not set.")
        # Initialize it to now to prevent error on first run, or handle this more robustly.
        current_app.last_activity_check_time = datetime.now(timezone.utc)


    last_check_time = current_app.last_activity_check_time
    current_check_time = datetime.now(timezone.utc)
    new_notifications_added = False
    notifications_created_count = 0

    # Check for new blog posts
    new_posts = Post.query.filter(Post.timestamp > last_check_time).all()
    for post in new_posts:
        notification = Notification(
            message=f"New blog post: '{post.title}'",
            type="new_post",
            related_id=post.id,
            timestamp=post.timestamp, # Use post's timestamp
            # user_id field in Notification model should be considered if these are user-specific
        )
        db.session.add(notification)
        new_notifications_added = True
        notifications_created_count += 1

    # Check for new events
    new_events = Event.query.filter(Event.created_at > last_check_time).all()
    for event in new_events:
        notification = Notification(
            message=f"New event: '{event.title}'",
            type="new_event",
            related_id=event.id,
            timestamp=event.created_at, # Use event's creation time
        )
        db.session.add(notification)
        new_notifications_added = True
        notifications_created_count += 1

    # Check for new polls
    new_polls = Poll.query.filter(Poll.created_at > last_check_time).all()
    for poll in new_polls:
        notification = Notification(
            message=f"New poll: '{poll.question}'",
            type="new_poll",
            related_id=poll.id,
            timestamp=poll.created_at, # Use poll's creation time
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
            current_app.logger.error(f"Error committing new notifications during activity summary: {e}")
    else:
        current_app.logger.info("Activity summary generated. No new notifications.")

    current_app.last_activity_check_time = current_check_time


# seed_achievements_command was a CLI command, it will be moved to run.py.
# It needs app context and imports for Achievement model and db.

# Other helper functions from app.py that were not routes or SocketIO handlers
# would go here. For example, if there were complex data processing functions
# used by multiple routes, they could be candidates for utils.py.

# Make sure all imports are relative if within the same package (e.g., `from .. import db`)
# or direct if standard library/third-party.
# Functions here will need `current_app` for config/logging, or have `app` passed to them if used outside app context.
# `url_for` typically needs blueprint context if routes are within blueprints e.g. `url_for('core.login')`.
# `login_required` and `moderator_required` use `current_user` from `flask_login`.
# `get_featured_post` uses `db`, `Post`, `random`, `datetime`, `timezone`, `current_app.logger`.
# `nl2br` is a simple string manipulation.
# `generate_activity_summary` uses `db`, `Post`, `Event`, `Poll`, `Notification`, `datetime`, `timezone`, `current_app.logger`, `current_app.last_activity_check_time`.
# `allowed_file` and `allowed_shared_file` use `current_app.config`.
# Ensure `current_app` is available, which it should be if these utils are called from within Flask request contexts or from app-context-aware scripts.
# For `generate_activity_summary` called by a scheduler, the scheduler setup must ensure it runs within an app context.
# Example (in run.py or scheduler setup):
# def scheduled_task():
#     with app.app_context():
#         generate_activity_summary()
# scheduler.add_job(func=scheduled_task, ...)

# `session` might be needed by some utils if they interact with it directly, imported from flask.
# `flash`, `redirect` also from flask.
# `wraps` from functools for decorators.
# `os` and `random` are standard library imports.
# `User` model imported for `moderator_required` and potentially others if they evolve.
# `Notification`, `Event`, `Poll` models imported for `generate_activity_summary`.```python
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
        and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]
    )

def allowed_shared_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[0] != ""
        and filename.rsplit(".", 1)[1].lower() in current_app.config["SHARED_FILES_ALLOWED_EXTENSIONS"]
    )

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("You need to be logged in to access this page.", "danger")
            # Store the intended destination in the session.
            session['next_url'] = request.url # Changed 'next' to 'next_url' to avoid conflict with request.args.get('next')
            return redirect(url_for("core.login", next=request.url)) # Pass next to login if needed by login view
        return f(*args, **kwargs)
    return decorated_function

def moderator_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not hasattr(current_user, 'role') or current_user.role != "moderator":
            flash("You do not have permission to access this page. Moderator access required.", "danger")
            return redirect(url_for("core.hello_world"))
        return f(*args, **kwargs)
    return decorated_function

def get_featured_post():
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
    if not isinstance(value, str):
        return value
    return value.replace("\n", "<br>\n")

def generate_activity_summary():
    if not hasattr(current_app, 'last_activity_check_time'):
        current_app.logger.warning("generate_activity_summary: current_app.last_activity_check_time not set. Initializing to now.")
        current_app.last_activity_check_time = datetime.now(timezone.utc) - timezone.timedelta(minutes=5) # Start by checking last 5 mins to avoid missing much

    last_check_time = current_app.last_activity_check_time
    current_check_time = datetime.now(timezone.utc)
    new_notifications_added = False
    notifications_created_count = 0

    new_posts = Post.query.filter(Post.timestamp > last_check_time, Post.timestamp <= current_check_time).all()
    for post in new_posts:
        notification = Notification(
            message=f"New blog post: '{post.title}'", type="new_post",
            related_id=post.id, timestamp=post.timestamp,
        )
        db.session.add(notification)
        new_notifications_added = True
        notifications_created_count += 1

    new_events = Event.query.filter(Event.created_at > last_check_time, Event.created_at <= current_check_time).all()
    for event in new_events:
        notification = Notification(
            message=f"New event: '{event.title}'", type="new_event",
            related_id=event.id, timestamp=event.created_at,
        )
        db.session.add(notification)
        new_notifications_added = True
        notifications_created_count += 1

    new_polls = Poll.query.filter(Poll.created_at > last_check_time, Poll.created_at <= current_check_time).all()
    for poll in new_polls:
        notification = Notification(
            message=f"New poll: '{poll.question}'", type="new_poll",
            related_id=poll.id, timestamp=poll.created_at,
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
            current_app.logger.error(f"Error committing new notifications during activity summary: {e}")
    else:
        current_app.logger.info("Activity summary generated. No new notifications.")
    current_app.last_activity_check_time = current_check_time
```
