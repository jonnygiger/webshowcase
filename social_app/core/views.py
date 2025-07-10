import os
import uuid
import json
from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_from_directory,
    jsonify,
    Response,
    Blueprint,
    current_app
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timezone
from collections import Counter
from flask_login import (
    current_user,
    login_user,
    logout_user,
)
from sqlalchemy import or_

from .. import db, login_manager
from ..models.db_models import (
    User, Post, Comment, Like, Review, Message, Poll, PollOption, PollVote, Event, EventRSVP,
    Notification, TodoItem, Group, Reaction, Bookmark, Friendship, SharedPost, UserActivity,
    FlaggedContent, FriendPostNotification, TrendingHashtag, SharedFile, UserStatus,
    UserAchievement, Achievement, Series, SeriesPost, UserBlock, ChatRoom, ChatMessage
)
from .utils import (
    allowed_file, login_required, moderator_required, get_featured_post, nl2br,
    generate_activity_summary, allowed_shared_file
)
from ..services.achievements import check_and_award_achievements
from ..services.recommendations_service import (
    suggest_users_to_follow, suggest_posts_to_read, suggest_groups_to_join,
    suggest_events_to_attend, suggest_hashtags, get_trending_hashtags,
    suggest_trending_posts, update_trending_hashtags, get_personalized_feed_posts,
    get_on_this_day_content
)
import queue


core_bp = Blueprint('core', __name__, template_folder='../../templates', static_folder='../../static')

@core_bp.app_template_filter()
def nl2br_filter(value):
    return nl2br(value)

def emit_new_activity_event(activity_log):
    if not activity_log or not activity_log.user:
        current_app.logger.error(
            f"Invalid activity_log or missing user for activity ID {activity_log.id if activity_log else 'Unknown'}"
        )
        return

    actor = activity_log.user
    payload = {
        "activity_id": activity_log.id,
        "user_id": actor.id,
        "username": actor.username,
        "profile_picture": (
            actor.profile_picture
            if actor.profile_picture
            else url_for("static", filename="profile_pics/default.png", _external=True)
        ),
        "activity_type": activity_log.activity_type,
        "related_id": activity_log.related_id,
        "content_preview": activity_log.content_preview,
        "link": activity_log.link,
        "timestamp": (
            activity_log.timestamp.isoformat()
            if activity_log.timestamp
            else datetime.now(timezone.utc).isoformat()
        ),
        "target_user_id": None,
        "target_username": None,
    }

    if activity_log.activity_type == "new_follow" and activity_log.target_user_id:
        target_user = getattr(activity_log, "target_user", None)
        if not target_user and activity_log.target_user_id:
            target_user = db.session.get(User, activity_log.target_user_id)
        if target_user:
            payload["target_user_id"] = target_user.id
            payload["target_username"] = target_user.username
        else:
            current_app.logger.warning(
                f"Target user not found for new_follow activity ID {activity_log.id}"
            )

    friends_of_actor = actor.get_friends()
    if friends_of_actor:
        for friend in friends_of_actor:
            if friend.id != actor.id: # Don't send to self
                if friend.id in current_app.user_notification_queues:
                    queues_for_friend = current_app.user_notification_queues[friend.id]
                    if queues_for_friend:
                        sse_event_data = {"type": "new_activity", "payload": payload}
                        for q_item in queues_for_friend:
                            try:
                                q_item.put_nowait(sse_event_data)
                                current_app.logger.info(f"Dispatched new_activity_event (SSE) to user {friend.id} for activity {activity_log.id}")
                            except queue.Full:
                                current_app.logger.error(f"SSE queue full for user {friend.id} (new_activity_event).")
                            except Exception as e:
                                current_app.logger.error(f"Error putting new_activity_event to SSE queue for user {friend.id}: {e}")
                    else:
                        current_app.logger.info(f"No active SSE queues for user {friend.id} (new_activity_event).")
                else:
                    current_app.logger.info(f"User {friend.id} not in user_notification_queues (new_activity_event).")
    else:
        current_app.logger.info(
            f"No friends found for actor {actor.username} to emit activity {activity_log.id}"
        )

@core_bp.route("/")
def hello_world():
    featured_post = get_featured_post()
    return render_template("index.html", featured_post=featured_post)

@core_bp.route("/child")
def child():
    return render_template("child_template.html")

@core_bp.route("/user/<username>")
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    user_posts = (
        Post.query.filter_by(user_id=user.id).order_by(Post.timestamp.desc()).all()
    )
    user_gallery_images_str = user.uploaded_images if user.uploaded_images else ""
    user_gallery_images_list = [
        img.strip() for img in user_gallery_images_str.split(",") if img.strip()
    ]
    organized_events = (
        Event.query.filter_by(user_id=user.id).order_by(Event.created_at.desc()).all()
    )

    for post_item in user_posts:
        post_item.review_count = len(post_item.reviews)
        if post_item.reviews:
            post_item.average_rating = sum(r.rating for r in post_item.reviews) / len(
                post_item.reviews
            )
        else:
            post_item.average_rating = 0

    bookmarked_post_ids = set()
    current_user_id_val = current_user.id if current_user.is_authenticated else None

    if current_user_id_val:
        bookmarks = Bookmark.query.filter_by(user_id=current_user_id_val).all()
        bookmarked_post_ids = {bookmark.post_id for bookmark in bookmarks}

    friendship_status = None
    pending_request_id = None
    if current_user_id_val and current_user_id_val != user.id:
        existing_friendship = Friendship.query.filter(
            or_(
                (Friendship.user_id == current_user_id_val)
                & (Friendship.friend_id == user.id),
                (Friendship.user_id == user.id)
                & (Friendship.friend_id == current_user_id_val),
            )
        ).first()
        if existing_friendship:
            if existing_friendship.status == "accepted":
                friendship_status = "friends"
            elif existing_friendship.status == "pending":
                if (
                    existing_friendship.user_id == current_user_id_val
                ):
                    friendship_status = "pending_sent"
                else:
                    friendship_status = "pending_received"
                    pending_request_id = existing_friendship.id
            elif existing_friendship.status == "rejected":
                if (
                    existing_friendship.user_id == current_user_id_val
                ):
                    friendship_status = "rejected_sent"
                else:
                    friendship_status = "rejected_received"
        else:
            friendship_status = "not_friends"

    shared_posts_by_user = (
        SharedPost.query.filter_by(shared_by_user_id=user.id)
        .order_by(SharedPost.shared_at.desc())
        .all()
    )
    user_achievements = (
        UserAchievement.query.filter_by(user_id=user.id)
        .order_by(UserAchievement.awarded_at.desc())
        .all()
    )
    user_series = (
        Series.query.filter_by(user_id=user.id).order_by(Series.created_at.desc()).all()
    )

    is_viewing_own_profile = current_user_id_val == user.id
    viewer_has_blocked_profile_owner = False
    profile_owner_has_blocked_viewer = False
    effective_block = False

    if not is_viewing_own_profile and current_user_id_val:
        viewer_has_blocked_profile_owner = (
            UserBlock.query.filter_by(
                blocker_id=current_user_id_val, blocked_id=user.id
            ).first()
            is not None
        )
        profile_owner_has_blocked_viewer = (
            UserBlock.query.filter_by(
                blocker_id=user.id, blocked_id=current_user_id_val
            ).first()
            is not None
        )
    effective_block = (
        viewer_has_blocked_profile_owner or profile_owner_has_blocked_viewer
    )

    if effective_block:
        user_posts = []
        shared_posts_by_user = []

    return render_template(
        "user.html",
        user=user,
        username=username,
        posts=user_posts,
        user_gallery_images=user_gallery_images_list,
        organized_events=organized_events,
        shared_posts_by_user=shared_posts_by_user,
        bookmarked_post_ids=bookmarked_post_ids,
        friendship_status=friendship_status,
        pending_request_id=pending_request_id,
        user_achievements=user_achievements,
        user_series=user_series,
        is_viewing_own_profile=is_viewing_own_profile,
        viewer_has_blocked_profile_owner=viewer_has_blocked_profile_owner,
        profile_owner_has_blocked_viewer=profile_owner_has_blocked_viewer,
        effective_block=effective_block,
    )

@core_bp.route("/todo", methods=["GET", "POST"])
@login_required
def todo():
    user_id = current_user.id
    if request.method == "POST":
        task_id = request.form.get("task_id")
        task_content = request.form.get("task")
        due_date_str = request.form.get("due_date")
        priority = request.form.get("priority")

        if not task_content or not task_content.strip():
            flash("Task content cannot be empty.", "warning")
            return redirect(url_for("core.todo"))

        due_date_obj = None
        if due_date_str:
            try:
                due_date_obj = datetime.strptime(due_date_str, "%Y-%m-%d")
            except ValueError:
                flash("Invalid due date format. Please use YYYY-MM-DD.", "warning")
                return redirect(url_for("core.todo"))

        if task_id:
            item_to_edit = TodoItem.query.filter_by(id=task_id, user_id=user_id).first()
            if item_to_edit:
                item_to_edit.task = task_content.strip()
                item_to_edit.due_date = due_date_obj
                item_to_edit.priority = (
                    priority if priority and priority.strip() else None
                )
                db.session.commit()
                flash("To-Do item updated!", "success")
            else:
                flash("Task not found or you don't have permission to edit it.", "danger")
        else:
            new_todo = TodoItem(
                task=task_content.strip(),
                user_id=user_id,
                due_date=due_date_obj,
                priority=priority if priority and priority.strip() else None,
            )
            db.session.add(new_todo)
            db.session.commit()
            flash("To-Do item added!", "success")
        return redirect(url_for("core.todo"))

    sort_by = request.args.get("sort_by", "timestamp")
    order = request.args.get("order", "asc")
    query = TodoItem.query.filter_by(user_id=user_id)

    if sort_by == "due_date":
        if order == "desc":
            query = query.order_by(db.nullslast(TodoItem.due_date.desc()))
        else:
            query = query.order_by(db.nullsfirst(TodoItem.due_date.asc()))
    elif sort_by == "priority":
        priority_order = db.case(
            {_prio: i for i, _prio in enumerate(["High", "Medium", "Low"])},
            value=TodoItem.priority,
            else_=-1,
        )
        if order == "desc":
            query = query.order_by(priority_order.asc())
        else:
            query = query.order_by(priority_order.desc())
    elif sort_by == "status":
        if order == "desc":
            query = query.order_by(TodoItem.is_done.desc())
        else:
            query = query.order_by(TodoItem.is_done.asc())
    else:
        if order == "desc":
            query = query.order_by(TodoItem.timestamp.desc())
        else:
            query = query.order_by(TodoItem.timestamp.asc())

    user_todos = query.all()
    return render_template("todo.html", todos=user_todos)

@core_bp.route("/todo/update_status/<int:item_id>", methods=["POST"])
@login_required
def update_todo_status(item_id):
    user_id = current_user.id
    item_to_update = TodoItem.query.filter_by(id=item_id, user_id=user_id).first()
    if item_to_update:
        item_to_update.is_done = not item_to_update.is_done
        db.session.commit()
        flash(f"Task status updated!", "success")
    else:
        flash("Task not found or permission denied.", "danger")
    return redirect(url_for("core.todo"))

@core_bp.route("/todo/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_todo_item(item_id):
    user_id = current_user.id
    item_to_delete = TodoItem.query.filter_by(id=item_id, user_id=user_id).first()
    if item_to_delete:
        db.session.delete(item_to_delete)
        db.session.commit()
        flash("To-Do item deleted!", "success")
    else:
        flash("Task not found or permission denied.", "danger")
    return redirect(url_for("core.todo"))

@core_bp.route("/todo/clear")
@login_required
def clear_todos():
    user_id = current_user.id
    TodoItem.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    flash("All To-Do items cleared.", "success")
    return redirect(url_for("core.todo"))

@core_bp.route("/gallery/upload", methods=["GET", "POST"])
@login_required
def upload_image():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part", "error")
            return redirect(request.url)
        file = request.files["file"]
        if file.filename == "":
            flash("No selected file", "error")
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))

            user_id = current_user.id
            user = db.session.get(User, user_id)
            if user:
                current_images_str = user.uploaded_images if user.uploaded_images else ""
                image_list = [img.strip() for img in current_images_str.split(",") if img.strip()]
                if filename not in image_list:
                    image_list.append(filename)
                user.uploaded_images = ",".join(image_list)
                db.session.commit()
            flash("Image successfully uploaded!", "success")
            return redirect(url_for("core.gallery"))
        else:
            flash("Allowed image types are png, jpg, jpeg, gif", "error")
            return redirect(request.url)
    return render_template("upload_image.html")

@core_bp.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)

@core_bp.route("/gallery")
def gallery():
    image_files = []
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    if os.path.exists(upload_folder):
        for filename in os.listdir(upload_folder):
            if allowed_file(filename):
                image_files.append(filename)
    return render_template("gallery.html", images=image_files)

@core_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('core.hello_world'))
    if request.method == "POST":
        username = request.form["username"]
        password_candidate = request.form["password"]
        user_obj = User.query.filter_by(username=username).first()
        if user_obj and check_password_hash(user_obj.password_hash, password_candidate):
            login_user(user_obj)
            flash("You are now logged in!", "success")
            next_page = request.args.get('next')
            return redirect(next_page or url_for("core.hello_world"))
        else:
            flash("Invalid login.", "danger")
            return render_template("login.html")
    return render_template("login.html")

@core_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You are now logged out.", "success")
    return redirect(url_for("core.login"))

@core_bp.route("/upload_profile_picture", methods=["GET", "POST"])
@login_required
def upload_profile_picture():
    if request.method == "POST":
        if "profile_pic" not in request.files:
            flash("No file part selected.", "warning")
            return redirect(request.url)
        file = request.files["profile_pic"]
        if file.filename == "":
            flash("No file selected.", "warning")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = uuid.uuid4().hex + "_" + filename
            file_path = os.path.join(current_app.config["PROFILE_PICS_FOLDER"], unique_filename)
            try:
                file.save(file_path)
                user = db.session.get(User, current_user.id)
                if user:
                    user.profile_picture = url_for("static", filename=f"profile_pics/{unique_filename}")
                    db.session.commit()
                    try:
                        activity = UserActivity(
                            user_id=user.id,
                            activity_type="updated_profile_picture",
                            link=url_for("core.user_profile", username=user.username, _external=True),
                        )
                        db.session.add(activity)
                        db.session.commit()
                        emit_new_activity_event(activity)
                    except Exception as e:
                        db.session.rollback()
                        current_app.logger.error(f"Error creating UserActivity for profile pic update: {e}")
                    flash("Profile picture uploaded successfully!", "success")
                    return redirect(url_for("core.user_profile", username=user.username))
            except Exception as e:
                current_app.logger.error(f"Error saving profile picture: {e}")
                flash("An error occurred while uploading. Please try again.", "danger")
                return redirect(request.url)
        else:
            flash("Invalid file type. Allowed types are png, jpg, jpeg, gif.", "danger")
            return redirect(request.url)
    return render_template("upload_profile_picture.html")

@core_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    user = User.query.get_or_404(current_user.id)
    if request.method == "POST":
        new_username = request.form.get("username", "").strip()
        new_email = request.form.get("email", "").strip()
        new_bio = request.form.get("bio", "").strip()

        if not new_username:
            flash("Username cannot be empty.", "danger")
            return render_template("edit_profile.html", user=user)
        if new_username != user.username:
            existing_user = User.query.filter(User.username == new_username, User.id != user.id).first()
            if existing_user:
                flash("That username is already taken.", "danger")
                return render_template("edit_profile.html", user=user)
            user.username = new_username
        if not new_email:
            flash("Email cannot be empty.", "danger")
            return render_template("edit_profile.html", user={"username": new_username, "email": user.email, "bio": new_bio})
        if new_email != user.email:
            existing_email_user = User.query.filter(User.email == new_email, User.id != user.id).first()
            if existing_email_user:
                flash("That email is already registered.", "danger")
                return render_template("edit_profile.html", user={"username": new_username, "email": user.email, "bio": new_bio})
            user.email = new_email
        user.bio = new_bio
        try:
            db.session.commit()
            flash("Profile updated successfully!", "success")
            return redirect(url_for("core.user_profile", username=user.username))
        except Exception as e:
            db.session.rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error updating profile for user {user.id}: {e}")
    return render_template("edit_profile.html", user=user)

@core_bp.context_processor
def inject_user_into_templates():
    return dict(current_user=current_user)

@core_bp.route("/discover")
@login_required
def discover_feed():
    user_id = current_user.id
    final_posts_with_reasons = get_personalized_feed_posts(user_id, limit=15)
    recommended_groups_raw = suggest_groups_to_join(user_id, limit=5)
    recommended_events_raw = suggest_events_to_attend(user_id, limit=5)
    groups_with_reasons = [(g, "Recommended group") for g in recommended_groups_raw if g]
    events_with_reasons = [(e, "Recommended event") for e in recommended_events_raw if e]
    return render_template(
        "discover.html",
        recommended_posts=final_posts_with_reasons,
        recommended_groups=groups_with_reasons,
        recommended_events=events_with_reasons,
    )

@core_bp.route("/trending")
def trending_posts_page():
    user_id = current_user.id if current_user.is_authenticated else None
    trending_posts_list = suggest_trending_posts(user_id=user_id, limit=20, since_days=7)
    bookmarked_post_ids = set()
    if user_id:
        bookmarks = Bookmark.query.filter_by(user_id=user_id).all()
        bookmarked_post_ids = {bookmark.post_id for bookmark in bookmarks}
    return render_template(
        "trending.html",
        posts=trending_posts_list,
        bookmarked_post_ids=bookmarked_post_ids,
    )

@core_bp.route("/blog/create", methods=["GET", "POST"])
@login_required
def create_post():
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        hashtags = request.form.get("hashtags", "")
        user_id = current_user.id
        new_post_db = Post(title=title, content=content, user_id=user_id, hashtags=hashtags)
        db.session.add(new_post_db)
        db.session.commit()
        try:
            activity = UserActivity(
                user_id=user_id,
                activity_type="new_post",
                related_id=new_post_db.id,
                content_preview=(new_post_db.content[:100] if new_post_db.content else ""),
                link=url_for("core.view_post", post_id=new_post_db.id, _external=True),
            )
            db.session.add(activity)
            db.session.commit()
            emit_new_activity_event(activity)
        except Exception as e:
            current_app.logger.error(f"Error creating UserActivity for new_post: {e}")
            db.session.rollback()

        post_author = new_post_db.author
        if post_author:
            if new_post_db.user_id:
                check_and_award_achievements(new_post_db.user_id)
            friends = post_author.get_friends()
            if friends:
                notifications_to_send = []
                for friend in friends:
                    if friend.id == post_author.id: continue
                    is_blocked = UserBlock.query.filter_by(blocker_id=friend.id, blocked_id=post_author.id).first()
                    if is_blocked: continue
                    new_friend_notification = FriendPostNotification(user_id=friend.id, post_id=new_post_db.id, poster_id=post_author.id)
                    notifications_to_send.append(new_friend_notification)
                if notifications_to_send:
                    try:
                        db.session.add_all(notifications_to_send)
                        db.session.commit()
                        for notification_instance in notifications_to_send:
                            if notification_instance.id and notification_instance.timestamp:
                                friend_id_for_notification = notification_instance.user_id
                                if friend_id_for_notification in current_app.user_notification_queues:
                                    queues_for_friend = current_app.user_notification_queues[friend_id_for_notification]
                                    if queues_for_friend:
                                        sse_payload = {
                                            "notification_id": notification_instance.id,
                                            "post_id": new_post_db.id,
                                            "post_title": new_post_db.title,
                                            "poster_username": post_author.username,
                                            "timestamp": notification_instance.timestamp.isoformat(),
                                        }
                                        sse_event_data = {"type": "new_friend_post", "payload": sse_payload}
                                        for q_item in queues_for_friend:
                                            try:
                                                q_item.put_nowait(sse_event_data)
                                                current_app.logger.info(f"Dispatched new_friend_post (SSE) to user {friend_id_for_notification} for post {new_post_db.id}")
                                            except queue.Full:
                                                current_app.logger.error(f"SSE queue full for user {friend_id_for_notification} (new_friend_post).")
                                            except Exception as e_sse:
                                                current_app.logger.error(f"Error putting new_friend_post to SSE queue for user {friend_id_for_notification}: {e_sse}")
                                    else:
                                        current_app.logger.info(f"No active SSE queues for user {friend_id_for_notification} (new_friend_post).")
                                else:
                                    current_app.logger.info(f"User {friend_id_for_notification} not in user_notification_queues (new_friend_post).")
                    except Exception as e:
                        db.session.rollback()
                        current_app.logger.error(f"Error creating/sending friend post notifications: {e}")
                        flash("Post created, but could not send friend notifications.", "warning")
        flash("Blog post created successfully!", "success")
        return redirect(url_for("core.blog"))
    return render_template("create_post.html")

@core_bp.route("/blog")
def blog():
    all_posts = Post.query.order_by(Post.timestamp.desc()).all()
    bookmarked_post_ids = set()
    suggested_users_snippet = []
    if current_user.is_authenticated:
        user_id = current_user.id
        bookmarks = Bookmark.query.filter_by(user_id=user_id).all()
        bookmarked_post_ids = {bookmark.post_id for bookmark in bookmarks}
        suggested_users_snippet = suggest_users_to_follow(user_id, limit=3)
    for post_item in all_posts:
        post_item.review_count = len(post_item.reviews)
        post_item.average_rating = (sum(r.rating for r in post_item.reviews) / len(post_item.reviews)) if post_item.reviews else 0
    trending_hashtags_list = get_trending_hashtags(top_n=10)
    return render_template("blog.html", posts=all_posts, bookmarked_post_ids=bookmarked_post_ids, suggested_users_snippet=suggested_users_snippet, trending_hashtags=trending_hashtags_list)

@core_bp.route("/blog/post/<int:post_id>")
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    post_comments = Comment.query.with_parent(post).order_by(Comment.timestamp.asc()).all()
    post_reactions = Reaction.query.filter_by(post_id=post_id).all()
    reaction_counts = Counter(r.emoji for r in post_reactions)
    user_has_liked = False
    current_user_id_val = current_user.id if current_user.is_authenticated else None
    if current_user_id_val:
        user_has_liked = Like.query.filter_by(user_id=current_user_id_val, post_id=post.id).count() > 0
    post_reviews = Review.query.with_parent(post).order_by(Review.timestamp.desc()).all()
    average_rating = (sum(r.rating for r in post_reviews) / len(post_reviews)) if post_reviews else 0
    can_submit_review = False
    if current_user_id_val:
        is_author = post.user_id == current_user_id_val
        has_reviewed = Review.query.filter_by(user_id=current_user_id_val, post_id=post.id).count() > 0
        if not is_author and not has_reviewed:
            can_submit_review = True
    user_has_bookmarked = False
    if current_user_id_val:
        user_has_bookmarked = Bookmark.query.filter_by(user_id=current_user_id_val, post_id=post.id).first() is not None

    current_series_id = request.args.get("series_id", type=int)
    previous_post_in_series = None
    next_post_in_series = None
    if current_series_id:
        current_series = db.session.get(Series, current_series_id)
        if current_series:
            current_series_post_entry = SeriesPost.query.filter_by(series_id=current_series_id, post_id=post.id).first()
            if current_series_post_entry:
                current_order = current_series_post_entry.order
                prev_assoc = SeriesPost.query.filter_by(series_id=current_series_id, order=current_order - 1).first()
                if prev_assoc: previous_post_in_series = db.session.get(Post, prev_assoc.post_id)
                next_assoc = SeriesPost.query.filter_by(series_id=current_series_id, order=current_order + 1).first()
                if next_assoc: next_post_in_series = db.session.get(Post, next_assoc.post_id)
            else: current_series_id = None
        else: current_series_id = None

    return render_template("view_post.html", post=post, comments=post_comments, user_has_liked=user_has_liked,
                           post_reviews=post_reviews, average_rating=average_rating, can_submit_review=can_submit_review,
                           reactions=post_reactions, reaction_counts=dict(reaction_counts),
                           user_has_bookmarked=user_has_bookmarked, current_series_id=current_series_id,
                           previous_post_in_series=previous_post_in_series, next_post_in_series=next_post_in_series)

@core_bp.route("/blog/edit/<int:post_id>", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        flash("You are not authorized to edit this post.", "danger")
        return redirect(url_for("core.view_post", post_id=post_id))
    if request.method == "POST":
        post.title = request.form["title"]
        post.content = request.form["content"]
        post.hashtags = request.form.get("hashtags", "")
        post.last_edited = datetime.now(timezone.utc)
        db.session.commit()

        # Dispatch post_content_updated event to SSE listeners
        post_data_for_sse = {
            "post_id": post.id,
            "title": post.title,
            "content": post.content, # This is the updated content
            "last_edited": post.last_edited.isoformat() if post.last_edited else None,
            "edited_by_user_id": current_user.id, # current_user is available here
            "edited_by_username": current_user.username
        }
        if post.id in current_app.post_event_listeners:
            listeners = list(current_app.post_event_listeners[post.id]) # Iterate over a copy
            current_app.logger.debug(f"Dispatching post_content_updated from edit_post view to {len(listeners)} listeners for post {post.id}")
            for q_item in listeners:
                try:
                    sse_data = {"type": "post_content_updated", "payload": post_data_for_sse}
                    q_item.put_nowait(sse_data)
                except Exception as e: # queue.Full or other errors
                    current_app.logger.error(f"Error putting post_content_updated to SSE queue from edit_post view for post {post.id}: {e}")
        else:
            current_app.logger.debug(f"No active SSE listeners in post_event_listeners for post {post.id} to dispatch post_content_updated from edit_post view.")

        flash("Post updated successfully!", "success")
        return redirect(url_for("core.view_post", post_id=post_id))
    return render_template("edit_post.html", post=post)

@core_bp.route("/blog/delete/<int:post_id>", methods=["POST"])
@login_required
def delete_post(post_id):
    post_to_delete = Post.query.get_or_404(post_id)
    if post_to_delete.user_id != current_user.id:
        flash("You are not authorized to delete this post.", "danger")
        return redirect(url_for("core.view_post", post_id=post_id))
    db.session.delete(post_to_delete)
    db.session.commit()
    flash("Post deleted successfully!", "success")
    return redirect(url_for("core.blog"))

@core_bp.route("/admin/feature_post/<int:post_id>", methods=["POST"])
@login_required
@moderator_required
def admin_feature_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.is_featured:
        post.is_featured = False
        post.featured_at = None
        flash(f'Post "{post.title}" is no longer featured.', "success")
    else:
        post.is_featured = True
        post.featured_at = datetime.now(timezone.utc)
        flash(f'Post "{post.title}" has been featured.', "success")
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling feature status for post {post_id}: {e}")
        flash("Failed to update feature status.", "danger")
    return redirect(url_for("core.view_post", post_id=post.id))

@core_bp.route("/hashtag/<tag>")
def view_hashtag_posts(tag):
    potential_posts = Post.query.filter(Post.hashtags.contains(tag)).order_by(Post.timestamp.desc()).all()
    actual_posts = []
    for post_item in potential_posts:
        if post_item.hashtags:
            tags_list = [t.strip() for t in post_item.hashtags.split(",") if t.strip()]
            if tag in tags_list:
                actual_posts.append(post_item)
    bookmarked_post_ids = set()
    if current_user.is_authenticated:
        user_id = current_user.id
        bookmarks = Bookmark.query.filter_by(user_id=user_id).all()
        bookmarked_post_ids = {bookmark.post_id for bookmark in bookmarks}
    for post_item in actual_posts:
        post_item.review_count = len(post_item.reviews)
        post_item.average_rating = (sum(r.rating for r in post_item.reviews) / len(post_item.reviews)) if post_item.reviews else 0
    return render_template("hashtag_posts.html", posts=actual_posts, tag=tag, bookmarked_post_ids=bookmarked_post_ids)

@core_bp.route("/blog/post/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    comment_content = request.form.get("comment_content")
    user_id = current_user.id
    if not comment_content or not comment_content.strip():
        flash("Comment content cannot be empty!", "warning")
        return redirect(url_for("core.view_post", post_id=post_id))
    new_comment_db = Comment(content=comment_content, user_id=user_id, post_id=post.id)
    db.session.add(new_comment_db)
    db.session.commit()
    try:
        activity = UserActivity(
            user_id=user_id, activity_type="new_comment", related_id=post.id,
            content_preview=(new_comment_db.content[:100] if new_comment_db.content else ""),
            link=url_for("core.view_post", post_id=post.id, _external=True),
        )
        db.session.add(activity)
        db.session.commit()
        emit_new_activity_event(activity)
    except Exception as e:
        current_app.logger.error(f"Error creating UserActivity for new_comment: {e}")
        db.session.rollback()

    new_comment_data_for_post_room = {
        "id": new_comment_db.id, "post_id": new_comment_db.post_id,
        "author_username": new_comment_db.author.username, "content": new_comment_db.content,
        "timestamp": new_comment_db.timestamp.isoformat(), # Use isoformat
    }
    # Dispatch to post-specific SSE stream (replaces old socketio.emit to post_X room)
    if post_id in current_app.post_event_listeners:
        comment_data_for_post_stream = {
            "id": new_comment_db.id,
            "author_username": new_comment_db.author.username,
            "content": new_comment_db.content,
            "timestamp": new_comment_db.timestamp.isoformat(),
            "post_id": post_id
        }
        sse_event_for_post_stream = {"type": "new_comment", "payload": comment_data_for_post_stream}
        listeners = list(current_app.post_event_listeners[post_id])
        for q_item in listeners:
            try:
                q_item.put_nowait(sse_event_for_post_stream)
                current_app.logger.info(f"Dispatched new_comment (SSE) to post_event_listeners for post {post_id}")
            except queue.Full:
                current_app.logger.error(f"SSE queue full for post {post_id} (new_comment on post stream).")
            except Exception as e:
                current_app.logger.error(f"Error putting new_comment to post SSE queue for post {post_id}: {e}")
    else:
        current_app.logger.debug(f"No active post_event_listeners for post {post_id} for new_comment event.")


    if new_comment_db.user_id: check_and_award_achievements(new_comment_db.user_id)
    post_author_id = post.user_id
    commenter_id = current_user.id
    if post_author_id != commenter_id:
        commenter_user = db.session.get(User, commenter_id)
        if commenter_user:
            # Notification to post author via user-specific SSE queue
            if post_author_id in current_app.user_notification_queues:
                queues_for_author = current_app.user_notification_queues[post_author_id]
                if queues_for_author:
                    notification_payload = {
                        "post_id": post.id,
                        "commenter_username": commenter_user.username,
                        "comment_content": new_comment_db.content,
                        "post_title": post.title
                    }
                    sse_event_data = {"type": "new_comment_on_post", "payload": notification_payload}
                    for q_item in queues_for_author:
                        try:
                            q_item.put_nowait(sse_event_data)
                            current_app.logger.info(f"Dispatched new_comment_on_post (SSE) to user {post_author_id} for post {post.id}")
                        except queue.Full:
                            current_app.logger.error(f"SSE queue full for user {post_author_id} (new_comment_on_post).")
                        except Exception as e:
                            current_app.logger.error(f"Error putting new_comment_on_post to SSE queue for user {post_author_id}: {e}")
                else:
                    current_app.logger.info(f"No active SSE queues for user {post_author_id} (new_comment_on_post).")
            else:
                current_app.logger.info(f"User {post_author_id} not in user_notification_queues (new_comment_on_post).")

    flash("Comment added successfully!", "success")
    return redirect(url_for("core.view_post", post_id=post_id))

@core_bp.route("/blog/post/<int:post_id>/like", methods=["POST"])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = current_user.id
    existing_like = Like.query.filter_by(user_id=user_id, post_id=post.id).first()
    if not existing_like:
        new_like = Like(user_id=user_id, post_id=post.id)
        db.session.add(new_like)
        try:
            db.session.commit()
            flash("Post liked!", "success")
            if user_id != post.user_id:
                liker = db.session.get(User, user_id)
                if liker and post.author:
                    notification_message = f"{liker.username} liked your post: '{post.title}'"
                    new_notification = Notification(user_id=post.author.id, message=notification_message, type="like", related_id=post.id)
                    try:
                        db.session.add(new_notification)
                        db.session.commit()
                        # SSE Notification to post author
                        if post.author.id in current_app.user_notification_queues:
                            queues_for_author = current_app.user_notification_queues[post.author.id]
                            if queues_for_author:
                                sse_payload = {
                                    "liker_username": liker.username,
                                    "post_id": post.id,
                                    "post_title": post.title,
                                    "message": notification_message,
                                    "notification_id": new_notification.id
                                }
                                sse_event_data = {"type": "new_like", "payload": sse_payload}
                                for q_item in queues_for_author:
                                    try:
                                        q_item.put_nowait(sse_event_data)
                                        current_app.logger.info(f"Dispatched new_like (SSE) to user {post.author.id} for post {post.id}")
                                    except queue.Full:
                                        current_app.logger.error(f"SSE queue full for user {post.author.id} (new_like).")
                                    except Exception as e_sse:
                                        current_app.logger.error(f"Error putting new_like to SSE queue for user {post.author.id}: {e_sse}")
                            else:
                                current_app.logger.info(f"No active SSE queues for user {post.author.id} (new_like).")
                        else:
                            current_app.logger.info(f"User {post.author.id} not in user_notification_queues (new_like).")
                    except Exception as e_notify:
                        db.session.rollback()
                        current_app.logger.error(f"Error creating like notification DB entry: {e_notify}")
            try:
                activity = UserActivity(user_id=user_id, activity_type="new_like", related_id=post.id,
                                        content_preview=post.content[:100] if post.content else "",
                                        link=url_for("core.view_post", post_id=post.id, _external=True))
                db.session.add(activity)
                db.session.commit()
                emit_new_activity_event(activity)
            except Exception as e_activity:
                db.session.rollback()
                current_app.logger.error(f"Error creating UserActivity for new_like: {e_activity}")
        except Exception as e_like:
            db.session.rollback()
            current_app.logger.error(f"Error liking post or related actions: {e_like}")
            flash("An error occurred while liking the post.", "danger")
    else:
        flash("You have already liked this post.", "info")
    return redirect(url_for("core.view_post", post_id=post_id))

@core_bp.route("/blog/post/<int:post_id>/unlike", methods=["POST"])
@login_required
def unlike_post(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = current_user.id
    like_to_delete = Like.query.filter_by(user_id=user_id, post_id=post.id).first()
    if like_to_delete:
        db.session.delete(like_to_delete)
        db.session.commit()
        flash("Post unliked!", "success")
    else:
        flash("You have not liked this post yet.", "info")
    return redirect(url_for("core.view_post", post_id=post_id))

@core_bp.route("/blog/post/<int:post_id>/review", methods=["POST"])
@login_required
def add_review(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = current_user.id
    if post.user_id == user_id:
        flash("You cannot review your own post.", "danger")
        return redirect(url_for("core.view_post", post_id=post_id))
    existing_review = Review.query.filter_by(user_id=user_id, post_id=post.id).first()
    if existing_review:
        flash("You have already reviewed this post.", "danger")
        return redirect(url_for("core.view_post", post_id=post_id))
    rating_str = request.form.get("rating")
    review_text = request.form.get("review_text")
    if not rating_str:
        flash("Rating is required.", "danger")
        return redirect(url_for("core.view_post", post_id=post_id))
    try:
        rating = int(rating_str)
        if not (1 <= rating <= 5): raise ValueError
    except ValueError:
        flash("Rating must be an integer between 1 and 5 stars.", "danger")
        return redirect(url_for("core.view_post", post_id=post_id))
    if not review_text or not review_text.strip():
        flash("Review text cannot be empty.", "danger")
        return redirect(url_for("core.view_post", post_id=post_id))
    new_review_db = Review(rating=rating, review_text=review_text.strip(), user_id=user_id, post_id=post.id)
    db.session.add(new_review_db)
    db.session.commit()
    flash("Review submitted successfully!", "success")
    return redirect(url_for("core.view_post", post_id=post_id))

@core_bp.route("/blog/post/<int:post_id>/stream")
def post_stream(post_id):
    def event_stream():
        q_local = queue.Queue()
        if post_id not in current_app.sse_listeners:
            current_app.sse_listeners[post_id] = []
        current_app.sse_listeners[post_id].append(q_local)
        try:
            while True:
                try:
                    data = q_local.get(timeout=1)
                    event_type = data.get("type", "message")
                    payload = data.get("payload", {})
                    yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
                except queue.Empty:
                    pass
        except GeneratorExit:
            pass
        finally:
            if post_id in current_app.sse_listeners and q_local in current_app.sse_listeners[post_id]:
                current_app.sse_listeners[post_id].remove(q_local)
                if not current_app.sse_listeners[post_id]:
                    del current_app.sse_listeners[post_id]
    return Response(event_stream(), mimetype="text/event-stream")


@core_bp.route("/post-stream/<int:post_id>")
def post_event_stream(post_id):
    # Optional: Validate post_id exists
    # post = Post.query.get(post_id)
    # if not post:
    #     # Return an empty response or an error if preferred for non-existent posts
    #     return Response(mimetype="text/event-stream", status=404)

    q_local = queue.Queue()
    if post_id not in current_app.post_event_listeners:
        current_app.post_event_listeners[post_id] = []

    current_app.post_event_listeners[post_id].append(q_local)
    # Use a generic term like 'client' for logging if user is not authenticated for this stream
    client_id_for_log = current_user.id if current_user.is_authenticated else request.remote_addr
    current_app.logger.info(f"Client {client_id_for_log} connected to post event stream for post {post_id}. Active listeners: {len(current_app.post_event_listeners[post_id])}")

    def event_generator():
        try:
            while True:
                data = q_local.get() # Blocks until an item is available
                if data is None:
                    current_app.logger.info(f"Post event stream for post {post_id}, client {client_id_for_log} received None, closing.")
                    break

                event_type = data.get("type", "message")
                payload = data.get("payload", {})

                sse_message = f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
                yield sse_message
                current_app.logger.debug(f"Sent SSE event '{event_type}' for post {post_id} to client {client_id_for_log}")

        except GeneratorExit:
            current_app.logger.info(f"Post event stream for post {post_id}, client {client_id_for_log} disconnected (GeneratorExit).")
        except Exception as e:
            current_app.logger.error(f"Error in post event_generator for post {post_id}, client {client_id_for_log}: {e}", exc_info=True)
        finally:
            current_app.logger.info(f"Cleaning up queue for post {post_id}, client {client_id_for_log}.")
            if post_id in current_app.post_event_listeners and q_local in current_app.post_event_listeners[post_id]:
                current_app.post_event_listeners[post_id].remove(q_local)
                if not current_app.post_event_listeners[post_id]:
                    del current_app.post_event_listeners[post_id]
                    current_app.logger.info(f"Removed post {post_id} from post_event_listeners as it's empty.")

    return Response(event_generator(), mimetype="text/event-stream")

@core_bp.route("/chat-stream/<int:room_id>")
@login_required
def chat_stream(room_id):
    # Ensure the room exists (optional, but good practice)
    # room = ChatRoom.query.get_or_404(room_id)
    # Simplified: directly use room_id for listeners

    q_local = queue.Queue()
    if room_id not in current_app.chat_room_listeners:
        current_app.chat_room_listeners[room_id] = []

    # Check if user is authorized to join this chat room (e.g., member of a private group chat)
    # For now, assume public rooms or authorization handled elsewhere if needed.
    # Add user specific details if needed, e.g. current_user.id for logging

    current_app.chat_room_listeners[room_id].append(q_local)
    current_app.logger.info(f"User {current_user.id if current_user.is_authenticated else 'Unknown'} connected to chat stream for room {room_id}. Active listeners: {len(current_app.chat_room_listeners[room_id])}")

    def event_generator():
        try:
            while True:
                data = q_local.get() # Blocks until an item is available
                if data is None: # Sentinel for closing the stream for this client
                    current_app.logger.info(f"SSE stream for room {room_id}, user {current_user.id if current_user.is_authenticated else 'Unknown'} received None, closing.")
                    break

                # Assuming data is already a dict like {"type": "new_chat_message", "payload": message_dict}
                event_type = data.get("type", "message")
                payload = data.get("payload", {})

                sse_message = f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
                yield sse_message
                current_app.logger.debug(f"Sent SSE event '{event_type}' to room {room_id} for user {current_user.id if current_user.is_authenticated else 'Unknown'}")

        except GeneratorExit:
            current_app.logger.info(f"SSE stream for room {room_id}, user {current_user.id if current_user.is_authenticated else 'Unknown'} disconnected (GeneratorExit).")
        except Exception as e:
            current_app.logger.error(f"Error in SSE event_generator for room {room_id}, user {current_user.id if current_user.is_authenticated else 'Unknown'}: {e}", exc_info=True)
        finally:
            current_app.logger.info(f"Cleaning up queue for room {room_id}, user {current_user.id if current_user.is_authenticated else 'Unknown'}.")
            if room_id in current_app.chat_room_listeners and q_local in current_app.chat_room_listeners[room_id]:
                current_app.chat_room_listeners[room_id].remove(q_local)
                if not current_app.chat_room_listeners[room_id]: # If list is empty, remove key
                    del current_app.chat_room_listeners[room_id]
                    current_app.logger.info(f"Removed room {room_id} from chat_room_listeners as it's empty.")

    return Response(event_generator(), mimetype="text/event-stream")

@core_bp.route("/chat")
@login_required
def chat_page():
    return render_template("chat.html")

@core_bp.route("/post/<int:post_id>/react", methods=["POST"])
@login_required
def react_to_post(post_id):
    post = db.session.get(Post, post_id)
    if not post:
        flash("Post not found.", "danger")
        return redirect(request.referrer or url_for("core.hello_world"))
    user_id = current_user.id
    emoji = request.form.get("emoji")
    if not emoji:
        flash("No emoji provided for reaction.", "danger")
        return redirect(url_for("core.view_post", post_id=post_id))
    existing_reaction_same_emoji = Reaction.query.filter_by(user_id=user_id, post_id=post_id, emoji=emoji).first()
    if existing_reaction_same_emoji:
        db.session.delete(existing_reaction_same_emoji)
        flash("Reaction removed.", "success")
    else:
        existing_reaction_any_emoji = Reaction.query.filter_by(user_id=user_id, post_id=post_id).first()
        if existing_reaction_any_emoji:
            existing_reaction_any_emoji.emoji = emoji
            existing_reaction_any_emoji.timestamp = datetime.now(timezone.utc)
            flash("Reaction updated.", "success")
        else:
            new_reaction = Reaction(user_id=user_id, post_id=post_id, emoji=emoji)
            db.session.add(new_reaction)
            flash("Reaction added.", "success")
    db.session.commit()
    return redirect(url_for("core.view_post", post_id=post_id))

@core_bp.route("/bookmark/<int:post_id>", methods=["POST"])
@login_required
def bookmark_post(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = current_user.id
    existing_bookmark = Bookmark.query.filter_by(user_id=user_id, post_id=post.id).first()
    if existing_bookmark:
        db.session.delete(existing_bookmark)
        db.session.commit()
        flash("Post unbookmarked.", "success")
    else:
        new_bookmark = Bookmark(user_id=user_id, post_id=post.id)
        db.session.add(new_bookmark)
        db.session.commit()
        if user_id and new_bookmark:
            check_and_award_achievements(user_id)
        flash("Post bookmarked!", "success")
    return redirect(url_for("core.view_post", post_id=post_id))

@core_bp.route("/post/<int:post_id>/share", methods=["POST"])
@login_required
def share_post(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = current_user.id
    existing_share = SharedPost.query.filter_by(original_post_id=post.id, shared_by_user_id=user_id).first()
    if existing_share:
        flash("You have already shared this post.", "info")
        return redirect(url_for("core.view_post", post_id=post_id))
    sharing_comment = request.form.get("sharing_comment")
    new_share = SharedPost(original_post_id=post.id, shared_by_user_id=user_id, sharing_user_comment=sharing_comment)
    db.session.add(new_share)
    db.session.commit()
    try:
        activity = UserActivity(
            user_id=user_id, activity_type="shared_a_post", related_id=post.id,
            content_preview=(new_share.sharing_user_comment[:100] if new_share.sharing_user_comment else (post.title[:100] if post.title else "Shared a post")),
            link=url_for("core.view_post", post_id=post.id, _external=True))
        db.session.add(activity)
        db.session.commit()
        emit_new_activity_event(activity)
    except Exception as e:
        current_app.logger.error(f"Error creating UserActivity for shared_a_post: {e}")
        db.session.rollback()
    flash("Post shared successfully!", "success")
    return redirect(url_for("core.view_post", post_id=post_id))

@core_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('core.hello_world'))
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username already exists.", "danger")
            return render_template("register.html")
        new_user_db = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(new_user_db)
        db.session.commit()
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("core.login"))
    return render_template("register.html")

@core_bp.route("/messages/send/<receiver_username>", methods=["GET", "POST"])
@login_required
def send_message(receiver_username):
    receiver_user = User.query.filter_by(username=receiver_username).first_or_404()
    sender_id = current_user.id
    if request.method == "POST":
        content = request.form.get("content")
        if not content or not content.strip():
            flash("Message content cannot be empty.", "warning")
            return render_template("send_message.html", receiver_username=receiver_username)
        new_message_db = Message(sender_id=sender_id, receiver_id=receiver_user.id, content=content)
        db.session.add(new_message_db)
        db.session.commit()
        message_payload = {
            "id": new_message_db.id, "sender_id": new_message_db.sender_id, "receiver_id": new_message_db.receiver_id,
            "content": new_message_db.content, "timestamp": new_message_db.timestamp.isoformat(), # Use isoformat
            "sender_username": new_message_db.sender.username,
        }
        # SSE for new_direct_message
        if new_message_db.receiver_id in current_app.user_notification_queues:
            queues_for_receiver = current_app.user_notification_queues[new_message_db.receiver_id]
            if queues_for_receiver:
                sse_event_dm = {"type": "new_direct_message", "payload": message_payload}
                for q_item in queues_for_receiver:
                    try: q_item.put_nowait(sse_event_dm)
                    except Exception as e: current_app.logger.error(f"SSE: Error putting new_direct_message for user {new_message_db.receiver_id}: {e}")

        unread_count = db.session.query(Message).filter(Message.sender_id == new_message_db.sender_id, Message.receiver_id == new_message_db.receiver_id, Message.is_read == False).count()
        inbox_update_payload = {
            "sender_id": new_message_db.sender_id, "sender_username": new_message_db.sender.username,
            "message_snippet": (new_message_db.content[:30] + "...") if len(new_message_db.content) > 30 else new_message_db.content,
            "timestamp": new_message_db.timestamp.isoformat(), "unread_count": unread_count, # Use isoformat
            "conversation_partner_id": new_message_db.sender_id,
            "conversation_partner_username": new_message_db.sender.username,
        }
        # SSE for update_inbox_notification
        if new_message_db.receiver_id in current_app.user_notification_queues:
            queues_for_receiver_inbox = current_app.user_notification_queues[new_message_db.receiver_id]
            if queues_for_receiver_inbox:
                sse_event_inbox = {"type": "update_inbox", "payload": inbox_update_payload}
                for q_item in queues_for_receiver_inbox:
                    try: q_item.put_nowait(sse_event_inbox)
                    except Exception as e: current_app.logger.error(f"SSE: Error putting update_inbox for user {new_message_db.receiver_id}: {e}")

        flash("Message sent successfully!", "success")
        return redirect(url_for("core.view_conversation", username=receiver_user.username))
    return render_template("send_message.html", receiver_username=receiver_user.username)

@core_bp.route("/messages/conversation/<username>")
@login_required
def view_conversation(username):
    current_user_id_val = current_user.id
    conversation_partner = User.query.filter_by(username=username).first_or_404()
    other_user_id = conversation_partner.id
    relevant_messages = (Message.query.filter(or_((Message.sender_id == current_user_id_val) & (Message.receiver_id == other_user_id),
                                                 (Message.sender_id == other_user_id) & (Message.receiver_id == current_user_id_val)))
                         .order_by(Message.timestamp.asc()).all())
    updated = False
    for msg in relevant_messages:
        if msg.receiver_id == current_user_id_val and not msg.is_read:
            msg.is_read = True
            updated = True
    if updated: db.session.commit()
    return render_template("conversation.html", conversation_partner=conversation_partner, messages_list=relevant_messages)

@core_bp.route("/messages/inbox")
@login_required
def inbox():
    current_user_id_val = current_user.id
    sent_to_users = db.session.query(Message.receiver_id).filter(Message.sender_id == current_user_id_val).distinct()
    received_from_users = db.session.query(Message.sender_id).filter(Message.receiver_id == current_user_id_val).distinct()
    other_user_ids = {user_tuple[0] for user_tuple in sent_to_users}.union({user_tuple[0] for user_tuple in received_from_users})
    inbox_items = []
    for other_id in other_user_ids:
        other_user = User.query.get(other_id)
        if not other_user: continue
        last_message = (Message.query.filter(or_((Message.sender_id == current_user_id_val) & (Message.receiver_id == other_id),
                                                 (Message.sender_id == other_id) & (Message.receiver_id == current_user_id_val)))
                        .order_by(Message.timestamp.desc()).first())
        unread_count = Message.query.filter_by(sender_id=other_id, receiver_id=current_user_id_val, is_read=False).count()
        if last_message:
            snippet = (last_message.content[:50] + "...") if len(last_message.content) > 50 else last_message.content
            inbox_items.append({"username": other_user.username, "last_message_snippet": snippet,
                                "last_message_display_timestamp": last_message.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                                "last_message_datetime": last_message.timestamp, "unread_count": unread_count, "partner_id": other_id})
    inbox_items.sort(key=lambda x: x["last_message_datetime"], reverse=True)
    return render_template("inbox.html", inbox_items=inbox_items)

@core_bp.route("/notifications")
@login_required
def view_notifications():
    notifications_to_display = Notification.query.order_by(Notification.timestamp.desc()).all()
    return render_template("notifications.html", notifications=notifications_to_display)

@core_bp.route("/polls/create", methods=["GET", "POST"])
@login_required
def create_poll():
    if request.method == "POST":
        question = request.form.get("question")
        options_texts = request.form.getlist("options[]")
        user_id = current_user.id
        if not question or not question.strip():
            flash("Poll question cannot be empty.", "danger")
            return render_template("create_poll.html")
        valid_options_texts = [opt.strip() for opt in options_texts if opt and opt.strip()]
        if len(valid_options_texts) < 2:
            flash("Please provide at least two valid options.", "danger")
            return render_template("create_poll.html")
        new_poll_db = Poll(question=question.strip(), user_id=user_id)
        for option_text in valid_options_texts:
            new_poll_db.options.append(PollOption(text=option_text))
        db.session.add(new_poll_db)
        db.session.commit()
        if new_poll_db.user_id: check_and_award_achievements(new_poll_db.user_id)
        flash("Poll created successfully!", "success")
        return redirect(url_for("core.polls_list"))
    return render_template("create_poll.html")

@core_bp.route("/polls")
def polls_list():
    all_polls = Poll.query.order_by(Poll.created_at.desc()).all()
    return render_template("polls.html", polls=all_polls)

@core_bp.route("/events/create", methods=["GET", "POST"])
@login_required
def create_event():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        event_date_str = request.form.get("event_date")
        event_time_str = request.form.get("event_time", "00:00")
        location = request.form.get("location")
        if not title or not title.strip(): flash("Event title is required.", "danger"); return render_template("create_event.html")
        if not event_date_str: flash("Event date is required.", "danger"); return render_template("create_event.html")
        try:
            event_datetime_obj = datetime.strptime(f"{event_date_str} {event_time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            flash("Invalid date/time format.", "danger"); return render_template("create_event.html")
        user_id = current_user.id
        new_event_db = Event(title=title.strip(), description=description.strip() if description else "", date=event_datetime_obj,
                             location=location.strip() if location else "", user_id=user_id)
        db.session.add(new_event_db)
        db.session.commit()
        if new_event_db.user_id: check_and_award_achievements(new_event_db.user_id)
        try:
            activity = UserActivity(user_id=user_id, activity_type="new_event", related_id=new_event_db.id,
                                    content_preview=(new_event_db.title[:100] if new_event_db.title else ""),
                                    link=url_for("core.view_event", event_id=new_event_db.id, _external=True))
            db.session.add(activity)
            db.session.commit()
            emit_new_activity_event(activity)
        except Exception as e: current_app.logger.error(f"Error creating UserActivity for new_event: {e}"); db.session.rollback()
        flash("Event created successfully!", "success")
        return redirect(url_for("core.events_list"))
    return render_template("create_event.html")

@core_bp.route("/poll/<int:poll_id>")
def view_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    user_has_voted = False
    user_vote_option_id = None
    total_votes_for_poll = 0
    current_user_id_val = current_user.id if current_user.is_authenticated else None
    if current_user_id_val:
        existing_vote = PollVote.query.filter_by(user_id=current_user_id_val, poll_id=poll.id).first()
        if existing_vote: user_has_voted = True; user_vote_option_id = existing_vote.poll_option_id
    options_display_data = []
    for option in poll.options:
        vote_count = len(option.votes)
        options_display_data.append({"id": option.id, "text": option.text, "vote_count": vote_count})
        total_votes_for_poll += vote_count
    poll.options_display = options_display_data
    return render_template("view_poll.html", poll=poll, user_has_voted=user_has_voted, user_vote=user_vote_option_id, total_votes=total_votes_for_poll)

@core_bp.route("/poll/<int:poll_id>/vote", methods=["POST"])
@login_required
def vote_on_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    selected_option_id_str = request.form.get("option_id")
    user_id = current_user.id
    if not selected_option_id_str: flash("No option selected.", "danger"); return redirect(url_for("core.view_poll", poll_id=poll_id))
    try: selected_option_id = int(selected_option_id_str)
    except ValueError: flash("Invalid option ID.", "danger"); return redirect(url_for("core.view_poll", poll_id=poll_id))
    option_to_vote = PollOption.query.filter_by(id=selected_option_id, poll_id=poll.id).first()
    if not option_to_vote: flash("Invalid option for this poll.", "danger"); return redirect(url_for("core.view_poll", poll_id=poll_id))
    existing_vote = PollVote.query.filter_by(user_id=user_id, poll_id=poll.id).first()
    if existing_vote: flash("You have already voted on this poll.", "warning"); return redirect(url_for("core.view_poll", poll_id=poll_id))
    new_vote = PollVote(user_id=user_id, poll_option_id=selected_option_id, poll_id=poll.id)
    db.session.add(new_vote)
    db.session.commit()
    if user_id: check_and_award_achievements(user_id)
    flash("Vote cast successfully!", "success")
    return redirect(url_for("core.view_poll", poll_id=poll_id))

@core_bp.route("/poll/<int:poll_id>/delete", methods=["POST"])
@login_required
def delete_poll(poll_id):
    poll_to_delete = Poll.query.get_or_404(poll_id)
    user_id = current_user.id
    if poll_to_delete.user_id != user_id: flash("Not authorized to delete this poll.", "danger"); return redirect(url_for("core.view_poll", poll_id=poll_id))
    db.session.delete(poll_to_delete)
    db.session.commit()
    flash("Poll deleted successfully!", "success")
    return redirect(url_for("core.polls_list"))

@core_bp.route("/events")
@login_required
def events_list():
    all_events = Event.query.order_by(Event.created_at.desc()).all()
    return render_template("events.html", events=all_events)

@core_bp.route("/event/<int:event_id>")
def view_event(event_id):
    event = Event.query.get_or_404(event_id)
    rsvp_counts = {"Attending": 0, "Maybe": 0, "Not Attending": 0}
    user_rsvp_status = None
    current_user_id_val = current_user.id if current_user.is_authenticated else None
    if current_user_id_val:
        user_rsvp = EventRSVP.query.filter_by(user_id=current_user_id_val, event_id=event.id).first()
        if user_rsvp: user_rsvp_status = user_rsvp.status
    for rsvp_entry in event.rsvps:
        if rsvp_entry.status in rsvp_counts: rsvp_counts[rsvp_entry.status] += 1
    is_organizer = current_user_id_val == event.user_id if current_user_id_val else False
    return render_template("view_event.html", event=event, rsvp_counts=rsvp_counts, user_rsvp_status=user_rsvp_status, is_organizer=is_organizer)

@core_bp.route("/event/<int:event_id>/rsvp", methods=["POST"])
@login_required
def rsvp_event(event_id):
    event = Event.query.get_or_404(event_id)
    rsvp_status = request.form.get("rsvp_status")
    valid_statuses = ["Attending", "Maybe", "Not Attending"]
    if not rsvp_status or rsvp_status not in valid_statuses: flash("Invalid RSVP status.", "danger"); return redirect(url_for("core.view_event", event_id=event_id))
    user_id = current_user.id
    existing_rsvp = EventRSVP.query.filter_by(user_id=user_id, event_id=event.id).first()
    if existing_rsvp: existing_rsvp.status = rsvp_status
    else: new_rsvp = EventRSVP(status=rsvp_status, user_id=user_id, event_id=event.id); db.session.add(new_rsvp)
    db.session.commit()
    flash(f'Your RSVP ("{rsvp_status}") has been recorded!', "success")
    return redirect(url_for("core.view_event", event_id=event_id))

@core_bp.route("/event/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(event_id):
    event_to_delete = Event.query.get_or_404(event_id)
    user_id = current_user.id
    if event_to_delete.user_id != user_id: flash("Not authorized to delete this event.", "danger"); return redirect(url_for("core.view_event", event_id=event_id))
    db.session.delete(event_to_delete)
    db.session.commit()
    flash("Event deleted successfully.", "success")
    return redirect(url_for("core.events_list"))

@core_bp.route("/trigger_notifications_test_only")
@login_required
def trigger_notifications_test_only():
    if current_app.debug:
        generate_activity_summary()
        flash("Notification generation triggered for test.", "info")
        return redirect(url_for("core.view_notifications"))
    else:
        flash("This endpoint is for testing only and disabled in production.", "danger")
        return redirect(url_for("core.hello_world"))

@core_bp.route("/groups")
def groups_list():
    all_groups = Group.query.order_by(Group.created_at.desc()).all()
    return render_template("groups_list.html", groups=all_groups)

@core_bp.route("/group/<int:group_id>")
def view_group(group_id):
    group = Group.query.get_or_404(group_id)
    current_user_is_member = False
    if current_user.is_authenticated:
        user_id = current_user.id
        current_user_is_member = group.members.filter(User.id == user_id).count() > 0
    chat_messages = []
    return render_template("group_detail.html", group=group, current_user_is_member=current_user_is_member, chat_messages=chat_messages)

@core_bp.route("/groups/create", methods=["GET", "POST"])
@login_required
def create_group():
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        user_id = current_user.id
        if not name or not name.strip(): flash("Group name is required.", "danger"); return render_template("create_group.html")
        existing_group = Group.query.filter_by(name=name.strip()).first()
        if existing_group: flash("A group with this name already exists.", "danger"); return render_template("create_group.html")
        user_obj = db.session.get(User, user_id)
        new_group = Group(name=name.strip(), description=description.strip(), creator_id=user_id)
        new_group.members.append(user_obj)
        db.session.add(new_group)
        db.session.commit()
        flash(f'Group "{new_group.name}" created successfully!', "success")
        return redirect(url_for("core.groups_list"))
    return render_template("create_group.html")

@core_bp.route("/group/<int:group_id>/join", methods=["POST"])
@login_required
def join_group(group_id):
    group = Group.query.get_or_404(group_id)
    user_id = current_user.id
    user_obj = db.session.get(User, user_id)
    if group.members.filter(User.id == user_id).count() > 0:
        flash("You are already a member of this group.", "info")
    else:
        group.members.append(user_obj)
        db.session.commit()
        if user_id: check_and_award_achievements(user_id)
        flash(f"You have successfully joined the group: {group.name}!", "success")
    return redirect(url_for("core.view_group", group_id=group_id))

@core_bp.route("/bookmarks")
@login_required
def bookmarked_posts():
    user_id = current_user.id
    bookmarked_posts_query = (Post.query.join(Bookmark, Post.id == Bookmark.post_id)
                              .filter(Bookmark.user_id == user_id).order_by(Bookmark.timestamp.desc()))
    posts_to_display = []
    for post_item in bookmarked_posts_query.all():
        post_item.review_count = len(post_item.reviews)
        post_item.average_rating = (sum(r.rating for r in post_item.reviews) / len(post_item.reviews)) if post_item.reviews else 0
        posts_to_display.append(post_item)
    return render_template("bookmarks.html", posts=posts_to_display)

@core_bp.route("/group/<int:group_id>/leave", methods=["POST"])
@login_required
def leave_group(group_id):
    group = Group.query.get_or_404(group_id)
    user_id = current_user.id
    user_obj = db.session.get(User, user_id)
    member_to_remove = group.members.filter(User.id == user_id).first()
    if member_to_remove:
        group.members.remove(member_to_remove)
        db.session.commit()
        flash(f"You have successfully left the group: {group.name}.", "success")
    else:
        flash("You are not a member of this group.", "info")
    return redirect(url_for("core.view_group", group_id=group_id))

@core_bp.route("/user/<int:target_user_id>/send_friend_request", methods=["POST"])
@login_required
def send_friend_request(target_user_id):
    current_user_id_val = current_user.id
    target_user = db.session.get(User, target_user_id)
    if not target_user: flash("Target user not found.", "danger"); return redirect(request.referrer or url_for("core.hello_world"))
    if current_user_id_val == target_user_id: flash("You cannot send a friend request to yourself.", "warning"); return redirect(url_for("core.user_profile", username=target_user.username))

    is_blocked_by_current_user = UserBlock.query.filter_by(blocker_id=current_user_id_val, blocked_id=target_user_id).first()
    is_blocked_by_target_user = UserBlock.query.filter_by(blocker_id=target_user_id, blocked_id=current_user_id_val).first()
    if is_blocked_by_current_user or is_blocked_by_target_user:
        flash("Cannot send friend request due to a block.", "warning")
        return redirect(url_for("core.user_profile", username=target_user.username))

    existing_friendship = Friendship.query.filter(or_((Friendship.user_id == current_user_id_val) & (Friendship.friend_id == target_user_id),
                                                     (Friendship.user_id == target_user_id) & (Friendship.friend_id == current_user_id_val))).first()
    if existing_friendship:
        if existing_friendship.status == "pending": flash("Friend request already sent or received and pending.", "info")
        elif existing_friendship.status == "accepted": flash("You are already friends with this user.", "info")
        elif existing_friendship.status == "rejected":
            if existing_friendship.friend_id == current_user_id_val: flash("You previously rejected a request from this user.", "info")
            else:
                db.session.delete(existing_friendship)
                new_request = Friendship(user_id=current_user_id_val, friend_id=target_user_id, status="pending")
                db.session.add(new_request); db.session.commit()
                flash("Friend request sent successfully. (Previous rejection overridden)", "success")
        return redirect(url_for("core.user_profile", username=target_user.username))

    new_request = Friendship(user_id=current_user_id_val, friend_id=target_user_id, status="pending")
    db.session.add(new_request); db.session.commit()
    flash("Friend request sent successfully.", "success")

    sender_user_obj = db.session.get(User, current_user_id_val)
    if sender_user_obj:
        notification_payload = {"type": "friend_request_received", "payload": {"message": f"{sender_user_obj.username} sent you a friend request.",
                               "sender_username": sender_user_obj.username, "profile_link": url_for("core.user_profile", username=sender_user_obj.username, _external=True)}}
        if target_user_id in current_app.user_notification_queues:
            user_queues = current_app.user_notification_queues[target_user_id]
            if user_queues:
                for q_item in user_queues:
                    try: q_item.put_nowait(notification_payload); current_app.logger.info(f"Dispatched 'friend_request_received' SSE for user {target_user_id}")
                    except queue.Full: current_app.logger.error(f"SSE queue full for user {target_user_id} for 'friend_request_received'.")
                    except Exception as e: current_app.logger.error(f"Error putting 'friend_request_received' SSE for user {target_user_id}: {e}")
    return redirect(url_for("core.user_profile", username=target_user.username))

@core_bp.route("/friend_requests")
@login_required
def view_friend_requests():
    current_user_id_val = current_user.id
    pending_requests = Friendship.query.filter_by(friend_id=current_user_id_val, status="pending").all()
    return render_template("friend_requests.html", pending_requests=pending_requests)

@core_bp.route("/user/<username>/friends")
def view_friends_list(username):
    user = User.query.filter_by(username=username).first_or_404()
    friends_list = user.get_friends()
    return render_template("friends_list.html", user=user, friends_list=friends_list)

@core_bp.route("/friend_request/<int:request_id>/accept", methods=["POST"])
@login_required
def accept_friend_request(request_id):
    current_user_id_val = current_user.id
    friend_request = db.session.get(Friendship, request_id)
    if not friend_request: flash("Friend request not found.", "danger"); return redirect(url_for("core.view_friend_requests"))
    if friend_request.friend_id != current_user_id_val: flash("Not authorized for this request.", "danger"); return redirect(url_for("core.view_friend_requests"))

    if friend_request.status == "pending":
        friend_request.status = "accepted"
        db.session.commit()
        check_and_award_achievements(current_user_id_val)
        if friend_request.requester: check_and_award_achievements(friend_request.requester.id)
        flash("Friend request accepted!", "success")

        accepting_user_obj = db.session.get(User, current_user_id_val)
        original_sender_id = friend_request.user_id
        if accepting_user_obj:
            notification_payload = {"type": "new_follower", "payload": {"message": f"{accepting_user_obj.username} accepted your friend request.",
                                   "follower_username": accepting_user_obj.username, "profile_link": url_for("core.user_profile", username=accepting_user_obj.username, _external=True)}}
            if original_sender_id in current_app.user_notification_queues:
                user_queues = current_app.user_notification_queues[original_sender_id]
                if user_queues:
                    for q_item in user_queues:
                        try: q_item.put_nowait(notification_payload); current_app.logger.info(f"Dispatched 'new_follower' SSE for user {original_sender_id}")
                        except queue.Full: current_app.logger.error(f"SSE queue full for user {original_sender_id} for 'new_follower'.")
                        except Exception as e: current_app.logger.error(f"Error putting 'new_follower' SSE for user {original_sender_id}: {e}")
        try:
            activity = UserActivity(user_id=current_user_id_val, activity_type="new_follow", target_user_id=friend_request.requester.id,
                                    link=url_for("core.user_profile", username=friend_request.requester.username, _external=True))
            db.session.add(activity); db.session.commit(); emit_new_activity_event(activity)
        except Exception as e: current_app.logger.error(f"Error creating UserActivity for new_follow: {e}"); db.session.rollback()
        return redirect(url_for("core.user_profile", username=friend_request.requester.username))
    elif friend_request.status == "accepted": flash("You are already friends.", "info")
    else: flash("Request no longer pending.", "warning")
    return redirect(url_for("core.view_friend_requests"))

@core_bp.route("/friend_request/<int:request_id>/reject", methods=["POST"])
@login_required
def reject_friend_request(request_id):
    current_user_id_val = current_user.id
    friend_request = db.session.get(Friendship, request_id)
    if not friend_request: flash("Friend request not found.", "danger"); return redirect(url_for("core.view_friend_requests"))
    if friend_request.friend_id != current_user_id_val: flash("Not authorized for this request.", "danger"); return redirect(url_for("core.view_friend_requests"))
    if friend_request.status == "pending": friend_request.status = "rejected"; db.session.commit(); flash("Friend request rejected.", "success")
    elif friend_request.status == "rejected": flash("Request already rejected.", "info")
    else: flash("Request no longer pending.", "warning")
    return redirect(url_for("core.view_friend_requests"))

@core_bp.route("/user/<int:friend_user_id>/remove_friend", methods=["POST"])
@login_required
def remove_friend(friend_user_id):
    current_user_id_val = current_user.id
    friend_user = db.session.get(User, friend_user_id)
    if not friend_user:
        flash("User not found.", "danger")
        current_user_obj_for_redirect = db.session.get(User, current_user_id_val)
        return redirect(url_for("core.user_profile", username=current_user_obj_for_redirect.username) if current_user_obj_for_redirect else url_for("core.hello_world"))
    if current_user_id_val == friend_user_id: flash("You cannot remove yourself.", "warning"); return redirect(url_for("core.user_profile", username=friend_user.username))
    friendship_to_remove = Friendship.query.filter(Friendship.status == "accepted",
                                                   or_((Friendship.user_id == current_user_id_val) & (Friendship.friend_id == friend_user_id),
                                                       (Friendship.user_id == friend_user_id) & (Friendship.friend_id == current_user_id_val))).first()
    if friendship_to_remove: db.session.delete(friendship_to_remove); db.session.commit(); flash(f"No longer friends with {friend_user.username}.", "success")
    else: flash(f"Not currently friends with {friend_user.username}.", "info")
    return redirect(url_for("core.user_profile", username=friend_user.username))

@core_bp.route("/user/<string:username_to_unblock>/unblock", methods=["POST"])
@login_required
def unblock_user(username_to_unblock):
    current_user_id_val = current_user.id
    user_to_unblock = User.query.filter_by(username=username_to_unblock).first()
    if not user_to_unblock: flash("User not found.", "danger"); return redirect(request.referrer or url_for("core.hello_world"))
    if current_user_id_val == user_to_unblock.id: flash("Cannot unblock yourself.", "warning"); return redirect(url_for("core.user_profile", username=username_to_unblock))
    block_instance = UserBlock.query.filter_by(blocker_id=current_user_id_val, blocked_id=user_to_unblock.id).first()
    if block_instance: db.session.delete(block_instance); db.session.commit(); flash(f"Unblocked {username_to_unblock}.", "success")
    else: flash(f"You had not blocked {username_to_unblock}.", "info")
    return redirect(url_for("core.user_profile", username=username_to_unblock))

@core_bp.route("/user/<string:username_to_block>/block", methods=["POST"])
@login_required
def block_user_route(username_to_block):
    current_user_id_val = current_user.id
    user_to_block = User.query.filter_by(username=username_to_block).first()
    if not user_to_block: flash("User not found.", "danger"); return redirect(request.referrer or url_for("core.hello_world"))
    if current_user_id_val == user_to_block.id: flash("Cannot block yourself.", "warning"); return redirect(url_for("core.user_profile", username=username_to_block))
    existing_block = UserBlock.query.filter_by(blocker_id=current_user_id_val, blocked_id=user_to_block.id).first()
    if existing_block: flash(f"Already blocked {username_to_block}.", "info")
    else:
        friendship_to_remove = Friendship.query.filter(or_((Friendship.user_id == current_user_id_val) & (Friendship.friend_id == user_to_block.id),
                                                         (Friendship.user_id == user_to_block.id) & (Friendship.friend_id == current_user_id_val))).first()
        if friendship_to_remove: db.session.delete(friendship_to_remove)
        new_block = UserBlock(blocker_id=current_user_id_val, blocked_id=user_to_block.id)
        db.session.add(new_block); db.session.commit()
        flash(f"Blocked {username_to_block}. Existing friendship removed.", "success")
    return redirect(url_for("core.user_profile", username=username_to_block))

@core_bp.route("/user/<username>/activity")
@login_required
def user_activity_feed(username):
    user = User.query.filter_by(username=username).first_or_404()
    activities = UserActivity.query.filter_by(user_id=user.id).order_by(UserActivity.timestamp.desc()).all()
    return render_template("user_activity.html", user=user, activities=activities)

@core_bp.route("/series/create", methods=["GET", "POST"])
@login_required
def create_series():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        user_id = current_user.id
        if not title or not title.strip(): flash("Series title cannot be empty.", "danger"); return render_template("create_series.html")
        new_series = Series(title=title.strip(), description=description.strip() if description else None, user_id=user_id)
        db.session.add(new_series); db.session.commit()
        flash("Series created successfully!", "success")
        return redirect(url_for("core.view_series", series_id=new_series.id))
    return render_template("create_series.html")

@core_bp.route("/series/<int:series_id>")
def view_series(series_id):
    series = Series.query.get_or_404(series_id)
    return render_template("view_series.html", series=series)

@core_bp.route("/series/<int:series_id>/edit", methods=["GET", "POST"])
@login_required
def edit_series(series_id):
    series = Series.query.get_or_404(series_id)
    if series.user_id != current_user.id: flash("Not authorized to edit this series.", "danger"); return redirect(url_for("core.view_series", series_id=series.id))
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        if not title or not title.strip():
            flash("Series title cannot be empty.", "danger")
            user_posts = Post.query.filter_by(user_id=series.user_id).order_by(Post.timestamp.desc()).all()
            posts_in_series_ids = {sp.post_id for sp in series.series_post_associations}
            available_posts = [post for post in user_posts if post.id not in posts_in_series_ids]
            return render_template("edit_series.html", series=series, available_posts=available_posts, posts_in_series=series.posts)
        series.title = title.strip()
        series.description = description.strip() if description else None
        series.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Series details updated!", "success")
        return redirect(url_for("core.edit_series", series_id=series.id))
    user_posts = Post.query.filter_by(user_id=series.user_id).order_by(Post.timestamp.desc()).all()
    posts_in_series_ids = {p.id for p in series.posts}
    available_posts = [post for post in user_posts if post.id not in posts_in_series_ids]
    return render_template("edit_series.html", series=series, available_posts=available_posts, posts_in_series=series.posts)

@core_bp.route("/series/<int:series_id>/add_post/<int:post_id>", methods=["POST"])
@login_required
def add_post_to_series(series_id, post_id):
    series = Series.query.get_or_404(series_id)
    if series.user_id != current_user.id: flash("Not authorized.", "danger"); return redirect(url_for("core.view_series", series_id=series.id))
    post_to_add = Post.query.get_or_404(post_id)
    if post_to_add.user_id != series.user_id: flash("Can only add your own posts.", "warning"); return redirect(url_for("core.edit_series", series_id=series.id))
    existing_entry = SeriesPost.query.filter_by(series_id=series_id, post_id=post_id).first()
    if existing_entry: flash("Post already in series.", "info"); return redirect(url_for("core.edit_series", series_id=series.id))
    max_order = db.session.query(db.func.max(SeriesPost.order)).filter_by(series_id=series_id).scalar()
    next_order_num = (max_order or 0) + 1
    new_series_post = SeriesPost(series_id=series_id, post_id=post_id, order=next_order_num)
    db.session.add(new_series_post); db.session.commit()
    flash(f"Post '{post_to_add.title}' added to series '{series.title}'.", "success")
    return redirect(url_for("core.edit_series", series_id=series.id))

@core_bp.route("/series/<int:series_id>/remove_post/<int:post_id>", methods=["POST"])
@login_required
def remove_post_from_series(series_id, post_id):
    series = Series.query.get_or_404(series_id)
    if series.user_id != current_user.id: flash("Not authorized.", "danger"); return redirect(url_for("core.view_series", series_id=series.id))
    post_to_remove = Post.query.get_or_404(post_id)
    series_post_entry = SeriesPost.query.filter_by(series_id=series_id, post_id=post_id).first()
    if not series_post_entry: flash("Post not in series.", "info"); return redirect(url_for("core.edit_series", series_id=series.id))
    db.session.delete(series_post_entry); db.session.commit()
    remaining_associations = SeriesPost.query.filter_by(series_id=series_id).order_by(SeriesPost.order).all()
    for index, assoc in enumerate(remaining_associations): assoc.order = index + 1
    db.session.commit()
    flash(f"Post '{post_to_remove.title}' removed from series '{series.title}'.", "success")
    return redirect(url_for("core.edit_series", series_id=series.id))

@core_bp.route("/series/<int:series_id>/delete", methods=["POST"])
@login_required
def delete_series(series_id):
    series = Series.query.get_or_404(series_id)
    if series.user_id != current_user.id: flash("Not authorized.", "danger"); return redirect(url_for("core.view_series", series_id=series.id))
    db.session.delete(series); db.session.commit()
    flash("Series deleted.", "success")
    return redirect(url_for("core.user_profile", username=series.author.username))

@core_bp.route("/series/<int:series_id>/reorder_posts", methods=["POST"])
@login_required
def reorder_series_posts(series_id):
    series = Series.query.get_or_404(series_id)
    if series.user_id != current_user.id: return jsonify({"status": "error", "message": "Forbidden"}), 403
    data = request.get_json()
    if not data or "post_ids" not in data or not isinstance(data["post_ids"], list): return jsonify({"status": "error", "message": "Malformed request"}), 400
    new_post_ids_order = data["post_ids"]
    current_series_posts_assoc = SeriesPost.query.filter_by(series_id=series.id).all()
    current_post_ids_in_series = {sp.post_id for sp in current_series_posts_assoc}
    if set(new_post_ids_order) != current_post_ids_in_series: return jsonify({"status": "error", "message": "Post IDs mismatch."}), 400
    try:
        series_posts_map = {sp.post_id: sp for sp in current_series_posts_assoc}
        for index, post_id in enumerate(new_post_ids_order):
            series_post_entry = series_posts_map.get(post_id)
            if series_post_entry: series_post_entry.order = index
            else: db.session.rollback(); return jsonify({"status": "error", "message": f"Error finding post ID {post_id}."}), 500
        series.updated_at = datetime.now(timezone.utc)
        db.session.add(series); db.session.commit()
        return jsonify({"status": "success", "message": "Posts reordered."})
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"Error reordering posts for series {series_id}: {e}")
        return jsonify({"status": "error", "message": "Internal error."}), 500

@core_bp.route("/live_feed")
@login_required
def live_feed():
    user_obj = db.session.get(User, current_user.id)
    friends = user_obj.get_friends()
    friend_ids = [friend.id for friend in friends]
    activities = []
    if friend_ids:
        activities = UserActivity.query.filter(UserActivity.user_id.in_(friend_ids)).order_by(UserActivity.timestamp.desc()).limit(30).all()
    return render_template("live_feed.html", activities=activities)

@core_bp.route("/recommendations")
@login_required
def recommendations_view():
    user_id = current_user.id
    suggested_users = suggest_users_to_follow(user_id, limit=5)
    suggested_posts = suggest_posts_to_read(user_id, limit=5)
    suggested_groups = suggest_groups_to_join(user_id, limit=5)
    suggested_events = suggest_events_to_attend(user_id, limit=5)
    suggested_hashtags_list = suggest_hashtags(user_id, limit=5)
    return render_template("recommendations.html", suggested_users=suggested_users, suggested_posts=suggested_posts,
                           suggested_groups=suggested_groups, suggested_events=suggested_events, suggested_hashtags=suggested_hashtags_list)

@core_bp.route("/onthisday")
@login_required
def on_this_day_page():
    user_id = current_user.id
    content = get_on_this_day_content(user_id)
    return render_template("on_this_day.html", posts=content.get("posts", []), events=content.get("events", []))

@core_bp.route("/post/<int:post_id>/flag", methods=["POST"])
@login_required
def flag_post(post_id):
    post = db.session.get(Post, post_id)
    if not post: return jsonify({"message": "Post not found"}), 404
    user_id = current_user.id
    if post.user_id == user_id: flash("Cannot flag your own post.", "warning"); return redirect(url_for("core.view_post", post_id=post_id))
    reason = request.form.get("reason")
    existing_flag = FlaggedContent.query.filter_by(content_type="post", content_id=post_id, flagged_by_user_id=user_id).first()
    if existing_flag: flash("Already flagged this post.", "info")
    else:
        new_flag = FlaggedContent(content_type="post", content_id=post_id, flagged_by_user_id=user_id, reason=reason)
        db.session.add(new_flag); db.session.commit()
        flash("Post flagged for review.", "success")
    return redirect(url_for("core.view_post", post_id=post_id))

@core_bp.route("/comment/<int:comment_id>/flag", methods=["POST"])
@login_required
def flag_comment(comment_id):
    comment = db.session.get(Comment, comment_id)
    if not comment: return jsonify({"message": "Comment not found"}), 404
    user_id = current_user.id
    if comment.user_id == user_id: flash("Cannot flag your own comment.", "warning"); return redirect(url_for("core.view_post", post_id=comment.post_id))
    reason = request.form.get("reason")
    existing_flag = FlaggedContent.query.filter_by(content_type="comment", content_id=comment_id, flagged_by_user_id=user_id).first()
    if existing_flag: flash("Already flagged this comment.", "info")
    else:
        new_flag = FlaggedContent(content_type="comment", content_id=comment_id, flagged_by_user_id=user_id, reason=reason)
        db.session.add(new_flag); db.session.commit()
        flash("Comment flagged for review.", "success")
    return redirect(url_for("core.view_post", post_id=comment.post_id))

@core_bp.route("/moderation")
@login_required
@moderator_required
def moderation_dashboard():
    pending_flags_query = FlaggedContent.query.filter_by(status="pending").order_by(FlaggedContent.timestamp.asc()).all()
    processed_flags = []
    for flag in pending_flags_query:
        flag_data = {"id": flag.id, "content_type": flag.content_type, "content_id": flag.content_id, "reason": flag.reason,
                     "flagged_by_user": flag.flagged_by_user, "timestamp": flag.timestamp, "comment_post_id": None}
        if flag.content_type == "comment":
            comment = db.session.get(Comment, flag.content_id)
            if comment: flag_data["comment_post_id"] = comment.post_id
        processed_flags.append(flag_data)
    return render_template("moderation_dashboard.html", flagged_items=processed_flags)

@core_bp.route("/flagged_content/<int:flag_id>/approve", methods=["POST"])
@login_required
@moderator_required
def approve_flagged_content(flag_id):
    flag = FlaggedContent.query.get_or_404(flag_id)
    if flag.status != "pending": flash("Flag already processed.", "warning"); return redirect(url_for("core.moderation_dashboard"))
    flag.status = "approved"; flag.moderator_id = current_user.id; flag.moderator_comment = request.form.get("moderator_comment")
    flag.resolved_at = datetime.now(timezone.utc); db.session.commit()
    flash(f"Flag ID {flag.id} approved.", "success"); return redirect(url_for("core.moderation_dashboard"))

@core_bp.route("/flagged_content/<int:flag_id>/reject", methods=["POST"])
@login_required
@moderator_required
def reject_flagged_content(flag_id):
    flag = FlaggedContent.query.get_or_404(flag_id)
    if flag.status != "pending": flash("Flag already processed.", "warning"); return redirect(url_for("core.moderation_dashboard"))
    flag.status = "rejected"; flag.moderator_id = current_user.id; flag.moderator_comment = request.form.get("moderator_comment")
    flag.resolved_at = datetime.now(timezone.utc); db.session.commit()
    flash(f"Flag ID {flag.id} rejected.", "success"); return redirect(url_for("core.moderation_dashboard"))

@core_bp.route("/flagged_content/<int:flag_id>/remove_content_and_reject", methods=["POST"])
@login_required
@moderator_required
def remove_content_and_reject_flag(flag_id):
    flag = FlaggedContent.query.get_or_404(flag_id)
    if flag.status != "pending": flash("Flag already processed.", "warning"); return redirect(url_for("core.moderation_dashboard"))
    content_removed = False
    if flag.content_type == "post":
        post_to_delete = db.session.get(Post, flag.content_id)
        if post_to_delete: db.session.delete(post_to_delete); content_removed = True; flash(f"Post ID {flag.content_id} deleted.", "info")
        else: flash(f"Post ID {flag.content_id} not found.", "error")
    elif flag.content_type == "comment":
        comment_to_delete = db.session.get(Comment, flag.content_id)
        if comment_to_delete: db.session.delete(comment_to_delete); content_removed = True; flash(f"Comment ID {flag.content_id} deleted.", "info")
        else: flash(f"Comment ID {flag.content_id} not found.", "error")
    else: flash(f"Unsupported content type '{flag.content_type}'.", "error")

    if content_removed:
        flag.status = "content_removed_and_rejected"; flash_message = f"Content ({flag.content_type} ID {flag.content_id}) removed and flag rejected."
    else: return redirect(url_for("core.moderation_dashboard"))

    flag.moderator_id = current_user.id; flag.moderator_comment = request.form.get("moderator_comment")
    flag.resolved_at = datetime.now(timezone.utc); db.session.commit()
    flash(flash_message, "success"); return redirect(url_for("core.moderation_dashboard"))

@core_bp.route("/friend_post_notifications", methods=["GET"])
@login_required
def view_friend_post_notifications():
    user_id = current_user.id
    notifications = FriendPostNotification.query.filter_by(user_id=user_id).order_by(FriendPostNotification.timestamp.desc()).all()
    return render_template("friend_post_notifications.html", notifications=notifications)

@core_bp.route("/friend_post_notifications/mark_as_read/<int:notification_id>", methods=["POST"])
@login_required
def mark_friend_post_notification_as_read(notification_id):
    user_id = current_user.id
    notification = db.session.get(FriendPostNotification, notification_id)
    if not notification: return jsonify({"status": "error", "message": "Not found."}), 404
    if notification.user_id != user_id: return jsonify({"status": "error", "message": "Unauthorized."}), 403
    try: notification.is_read = True; db.session.commit(); return jsonify({"status": "success", "message": "Marked as read."})
    except Exception as e: db.session.rollback(); current_app.logger.error(f"Error marking friend post notification as read: {e}"); return jsonify({"status": "error", "message": "Could not mark as read."}), 500

@core_bp.route("/friend_post_notifications/mark_all_as_read", methods=["POST"])
@login_required
def mark_all_friend_post_notifications_as_read():
    user_id = current_user.id
    try:
        unread_notifications = FriendPostNotification.query.filter_by(user_id=user_id, is_read=False).all()
        if not unread_notifications: return jsonify({"status": "success", "message": "No unread notifications."})
        for notification in unread_notifications: notification.is_read = True
        db.session.commit()
        return jsonify({"status": "success", "message": "All marked as read."})
    except Exception as e: db.session.rollback(); current_app.logger.error(f"Error marking all friend post notifications as read: {e}"); return jsonify({"status": "error", "message": "Could not mark all as read."}), 500

@core_bp.route("/files/share/<receiver_username>", methods=["GET", "POST"])
@login_required
def share_file_route(receiver_username):
    receiver_user = User.query.filter_by(username=receiver_username).first_or_404()
    if request.method == "POST":
        if "file" not in request.files: flash("No file part.", "danger"); return redirect(request.url)
        file = request.files["file"]
        if file.filename == "": flash("No selected file.", "danger"); return redirect(request.url)

        file.seek(0, os.SEEK_END); file_length = file.tell(); file.seek(0)
        if file_length > current_app.config["SHARED_FILES_MAX_SIZE"]:
            flash(f"File too large. Max size {current_app.config['SHARED_FILES_MAX_SIZE']//(1024*1024)}MB.", "danger"); return redirect(request.url)

        if file and allowed_shared_file(file.filename):
            true_original_filename = file.filename
            secured_filename_for_ext = secure_filename(file.filename)
            extension = secured_filename_for_ext.rsplit(".", 1)[1].lower() if "." in secured_filename_for_ext else ""
            if not extension and "." in true_original_filename:
                _original_ext_candidate = true_original_filename.rsplit(".", 1)[1].lower()
                if _original_ext_candidate in current_app.config["SHARED_FILES_ALLOWED_EXTENSIONS"]: extension = _original_ext_candidate

            saved_filename_on_disk = f"{uuid.uuid4().hex}.{extension}" if extension else f"{uuid.uuid4().hex}"
            file_path = os.path.join(current_app.config["SHARED_FILES_UPLOAD_FOLDER"], saved_filename_on_disk)
            try:
                file.save(file_path)
                message_text = request.form.get("message")
                new_shared_file = SharedFile(sender_id=current_user.id, receiver_id=receiver_user.id,
                                             original_filename=true_original_filename, saved_filename=saved_filename_on_disk, message=message_text)
                db.session.add(new_shared_file); db.session.commit()
                flash("File shared!", "success"); return redirect(url_for("core.files_inbox"))
            except Exception as e:
                db.session.rollback(); current_app.logger.error(f"Error saving/sharing file: {e}"); flash("Error sharing file.", "danger")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError as ose:
                        current_app.logger.error(f"Error removing orphaned file: {ose}")
                return redirect(request.url)
        else: flash("File type not allowed or no file.", "danger"); return redirect(request.url)
    return render_template("share_file.html", receiver_user=receiver_user)

@core_bp.route("/files/inbox")
@login_required
def files_inbox():
    received_files = SharedFile.query.filter_by(receiver_id=current_user.id).order_by(SharedFile.upload_timestamp.desc()).all()
    return render_template("files_inbox.html", received_files=received_files)

@core_bp.route("/files/download/<int:shared_file_id>", methods=["GET"])
@login_required
def download_shared_file(shared_file_id):
    shared_file = SharedFile.query.get_or_404(shared_file_id)
    current_user_id_val = current_user.id
    if shared_file.receiver_id != current_user_id_val and shared_file.sender_id != current_user_id_val:
        flash("Not authorized to download this file.", "danger"); return redirect(url_for("core.files_inbox"))
    try:
        if shared_file.receiver_id == current_user_id_val and not shared_file.is_read:
            shared_file.is_read = True; db.session.commit()
        return send_from_directory(current_app.config["SHARED_FILES_UPLOAD_FOLDER"], shared_file.saved_filename,
                                   as_attachment=True, download_name=shared_file.original_filename)
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"Error downloading file/marking read: {e}"); flash("Error downloading file.", "danger")
        return redirect(url_for("core.files_inbox"))

@core_bp.route("/files/delete/<int:shared_file_id>", methods=["POST"])
@login_required
def delete_shared_file(shared_file_id):
    shared_file = SharedFile.query.get_or_404(shared_file_id)
    current_user_id_val = current_user.id
    if shared_file.receiver_id != current_user_id_val and shared_file.sender_id != current_user_id_val:
        flash("Not authorized to delete this file.", "danger"); return redirect(url_for("core.files_inbox"))
    file_path = os.path.join(current_app.config["SHARED_FILES_UPLOAD_FOLDER"], shared_file.saved_filename)
    try:
        if os.path.exists(file_path): os.remove(file_path)
        db.session.delete(shared_file); db.session.commit()
        flash("File deleted.", "success")
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"Error deleting shared file: {e}"); flash("Error deleting file.", "danger")
    return redirect(url_for("core.files_inbox"))

@core_bp.route("/set_status", methods=["POST"])
@login_required
def set_status():
    user_obj = db.session.get(User, current_user.id)
    status_text = request.form.get("status_text", "").strip()
    emoji = request.form.get("emoji", "").strip()
    if not status_text and not emoji: flash("Status text or emoji must be provided.", "warning"); return redirect(url_for("core.user_profile", username=user_obj.username))
    new_status = UserStatus(user_id=user_obj.id, status_text=status_text if status_text else None, emoji=emoji if emoji else None)
    try:
        db.session.add(new_status); db.session.commit()
        flash("Status updated!", "success")
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"Error setting status for {user_obj.username}: {e}"); flash("Error setting status.", "danger")
    return redirect(url_for("core.user_profile", username=user_obj.username))

@core_bp.route("/user/<username>/achievements")
@login_required
def view_user_achievements(username):
    user = User.query.filter_by(username=username).first_or_404()
    all_system_achievements = Achievement.query.order_by(Achievement.name).all()
    earned_achievement_ids = {ua.achievement_id for ua in UserAchievement.query.filter_by(user_id=user.id).all()}
    user_earned_achievements_details = (UserAchievement.query.filter_by(user_id=user.id)
                                        .join(Achievement, UserAchievement.achievement_id == Achievement.id)
                                        .order_by(Achievement.name).all())
    return render_template("achievements.html", profile_user=user, all_system_achievements=all_system_achievements,
                           earned_achievement_ids=earned_achievement_ids, user_earned_achievements_details=user_earned_achievements_details)

@core_bp.route("/user/notifications/stream")
@login_required
def user_notification_stream():
    current_user_id_val = current_user.id
    q_local = queue.Queue()
    if current_user_id_val not in current_app.user_notification_queues:
        current_app.user_notification_queues[current_user_id_val] = []
    current_app.user_notification_queues[current_user_id_val].append(q_local)
    current_app.logger.info(f"User {current_user_id_val} connected to notification stream. Queues: {len(current_app.user_notification_queues[current_user_id_val])}")

    def event_stream():
        try:
            while True:
                data = q_local.get()
                if data is None: current_app.logger.info(f"Stream for user {current_user_id_val} closing."); break
                event_type = data.get("type", "message")
                payload = data.get("payload", {})
                sse_message = f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
                yield sse_message
                current_app.logger.debug(f"Sent event {event_type} to user {current_user_id_val}")
        except GeneratorExit: current_app.logger.info(f"User {current_user_id_val} disconnected (GeneratorExit).")
        except Exception as e: current_app.logger.error(f"Error in event stream for user {current_user_id_val}: {e}")
        finally:
            current_app.logger.info(f"Cleaning up queue for user {current_user_id_val}.")
            if current_user_id_val in current_app.user_notification_queues:
                if q_local in current_app.user_notification_queues[current_user_id_val]:
                    current_app.user_notification_queues[current_user_id_val].remove(q_local)
                if not current_app.user_notification_queues[current_user_id_val]:
                    del current_app.user_notification_queues[current_user_id_val]
    return Response(event_stream(), mimetype="text/event-stream")
