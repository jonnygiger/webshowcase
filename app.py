import os
from flask import Flask, render_template, request, session, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from collections import Counter # Added for reaction counts
from flask_socketio import SocketIO, emit, join_room
from apscheduler.schedulers.background import BackgroundScheduler
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_ # Added for inbox query
from flask_migrate import Migrate
from flask_restful import Api
from flask_jwt_extended import JWTManager, create_access_token
import uuid # For generating unique filenames

db = SQLAlchemy()
migrate = Migrate()

# Import models after db and migrate are created, but before app context is needed for them usually
# and definitely before db.init_app
from models import User, Post, Comment, Like, Review, Message, Poll, PollOption, PollVote, Event, EventRSVP, Notification, TodoItem, Group, Reaction, Bookmark, Friendship, SharedPost, UserActivity, FlaggedContent # Add UserActivity, FlaggedContent
from api import UserListResource, UserResource, PostListResource, PostResource, EventListResource, EventResource
from recommendations import (
    suggest_users_to_follow, suggest_posts_to_read, suggest_groups_to_join,
    suggest_events_to_attend, suggest_polls_to_vote, suggest_hashtags,
    get_trending_hashtags, suggest_trending_posts # Added suggest_trending_posts
)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
migrate.init_app(app, db)
socketio = SocketIO(app)
api = Api(app)
jwt = JWTManager(app)

api.add_resource(UserListResource, '/api/users')
api.add_resource(UserResource, '/api/users/<int:user_id>')
api.add_resource(PostListResource, '/api/posts')
api.add_resource(PostResource, '/api/posts/<int:post_id>')
api.add_resource(EventListResource, '/api/events')
api.add_resource(EventResource, '/api/events/<int:event_id>')

# Scheduler for periodic tasks
scheduler = BackgroundScheduler()
# generate_activity_summary will be defined later in this file
# For testing, use a short interval like 1 minute.
# In production, this might be 5, 10, or 15 minutes.

app.config['SECRET_KEY'] = 'supersecretkey'
app.config['JWT_SECRET_KEY'] = 'your-jwt-secret-key' # Choose a strong, unique key
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads') # For general gallery
app.config['PROFILE_PICS_FOLDER'] = os.path.join(app.root_path, 'static', 'profile_pics')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

app.last_activity_check_time = datetime.utcnow() # Changed to utcnow for consistency

# Ensure the upload folder exists
# Note: In-memory data structures (users, blog_posts, comments, post_likes, private_messages,
# polls, poll_votes, events, event_rsvps, blog_reviews, app.notifications and their counters)
# are removed as they will be replaced by SQLAlchemy models.
# Their definitions and initialization are deleted from this section.

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

if not os.path.exists(app.config['PROFILE_PICS_FOLDER']):
    os.makedirs(app.config['PROFILE_PICS_FOLDER'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[0] != "" and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generate_activity_summary():
    """
    Checks for new posts, events, and polls since the last check
    and creates notifications for them.
    """
    # This function will need to be completely rewritten to use SQLAlchemy queries
    # against the Post, Event, and Poll models.
    # app.last_activity_check_time is a naive datetime, convert to aware if needed, or ensure consistency
    # For this implementation, assuming naive datetime comparison is sufficient if DB stores naive UTC.
    # Models use default=datetime.utcnow, which is naive.

    # It's crucial this function runs within an app context if it's called by the scheduler
    # and the scheduler is initialized outside of one.
    # However, if called from within a request or app startup (like current test endpoint), context is usually present.
    # For APScheduler BackgroundScheduler, it's better to ensure context.
    with app.app_context():
        current_check_time = datetime.utcnow() # Use UTC now
        new_notifications_added = False
        notifications_created_count = 0

        # Check for new blog posts
        # Ensure app.last_activity_check_time is also UTC if not already
        # If app.last_activity_check_time was from datetime.now() it might be local timezone.
        # For simplicity, let's assume app.last_activity_check_time is comparable to UTC.
        # A more robust solution would involve timezone awareness for these timestamps.
        new_posts = Post.query.filter(Post.timestamp > app.last_activity_check_time).all()
        for post in new_posts:
            notification = Notification(
                message=f"New blog post: '{post.title}'",
                type="new_post",
                related_id=post.id,
                timestamp=post.timestamp
            )
            db.session.add(notification)
            new_notifications_added = True
            notifications_created_count +=1

        # Check for new events
        new_events = Event.query.filter(Event.created_at > app.last_activity_check_time).all()
        for event in new_events:
            notification = Notification(
                message=f"New event: '{event.title}'",
                type="new_event",
                related_id=event.id,
                timestamp=event.created_at
            )
            db.session.add(notification)
            new_notifications_added = True
            notifications_created_count +=1

        # Check for new polls
        new_polls = Poll.query.filter(Poll.created_at > app.last_activity_check_time).all()
        for poll in new_polls:
            notification = Notification(
                message=f"New poll: '{poll.question}'",
                type="new_poll",
                related_id=poll.id,
                timestamp=poll.created_at
            )
            db.session.add(notification)
            new_notifications_added = True
            notifications_created_count +=1

        if new_notifications_added:
            db.session.commit()
            print(f"Activity summary generated. {notifications_created_count} new notifications created and saved to DB.")
        else:
            print("Activity summary generated. No new notifications.")

        app.last_activity_check_time = current_check_time

# Decorator for requiring login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Debug print inside the decorator to see session state
        print(f"login_required: session content before check: {dict(session)}")
        if 'user_id' not in session: # Changed from 'logged_in' to 'user_id'
            flash('You need to be logged in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator for requiring moderator role
def moderator_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: # Should be caught by @login_required first
            flash('You need to be logged in to access this page.', 'danger')
            return redirect(url_for('login'))

        user = User.query.get(session['user_id'])
        if not user:
            flash('User not found. Please log in again.', 'danger')
            session.pop('user_id', None) # Clear potentially invalid session
            session.pop('username', None)
            session.pop('logged_in', None)
            return redirect(url_for('login'))

        if user.role != 'moderator':
            flash('You do not have permission to access this page. Moderator access required.', 'danger')
            return redirect(url_for('hello_world')) # Redirect to home or another appropriate page
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def hello_world():
    return render_template('index.html')

@app.route('/child')
def child():
    return render_template('child_template.html')

@app.route('/user/<username>')
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    # Fetch posts by this user
    user_posts = Post.query.filter_by(user_id=user.id).order_by(Post.timestamp.desc()).all()
    # User gallery images from comma-separated string
    user_gallery_images_str = user.uploaded_images if user.uploaded_images else ""
    user_gallery_images_list = [img.strip() for img in user_gallery_images_str.split(',') if img.strip()]
    # Profile picture path is directly user.profile_picture from the User object
    # Fetch events organized by this user
    organized_events = Event.query.filter_by(user_id=user.id).order_by(Event.created_at.desc()).all()

    # The following logic for reviews and ratings on posts should be done similarly to the /blog route
    # or by adding properties/methods to the Post model.
    for post_item in user_posts:
        post_item.review_count = len(post_item.reviews)
        if post_item.reviews:
            post_item.average_rating = sum(r.rating for r in post_item.reviews) / len(post_item.reviews)
        else:
            post_item.average_rating = 0

    bookmarked_post_ids = set()
    current_user_id = session.get('user_id') # Get current_user_id for friendship status
    if current_user_id:
        bookmarks = Bookmark.query.filter_by(user_id=current_user_id).all()
        bookmarked_post_ids = {bookmark.post_id for bookmark in bookmarks}

    friendship_status = None
    pending_request_id = None
    if current_user_id and current_user_id != user.id:
        existing_friendship = Friendship.query.filter(
            or_(
                (Friendship.user_id == current_user_id) & (Friendship.friend_id == user.id),
                (Friendship.user_id == user.id) & (Friendship.friend_id == current_user_id)
            )
        ).first()
        if existing_friendship:
            if existing_friendship.status == 'accepted':
                friendship_status = 'friends'
            elif existing_friendship.status == 'pending':
                if existing_friendship.user_id == current_user_id: # Current user sent the request
                    friendship_status = 'pending_sent'
                else: # Current user received the request
                    friendship_status = 'pending_received'
                    pending_request_id = existing_friendship.id
            elif existing_friendship.status == 'rejected':
                if existing_friendship.user_id == current_user_id: # Current user's request was rejected by 'user'
                    friendship_status = 'rejected_sent'
                else: # Current user rejected a request from 'user'
                    friendship_status = 'rejected_received'
        else:
            friendship_status = 'not_friends'

    # Fetch posts shared by this user
    shared_posts_by_user = SharedPost.query.filter_by(shared_by_user_id=user.id).order_by(SharedPost.shared_at.desc()).all()

    # Pass the whole user object to the template, which includes user.profile_picture
    return render_template('user.html',
                           user=user,
                           username=username, # username is still useful for display
                           posts=user_posts,
                           user_gallery_images=user_gallery_images_list, # Clarified variable name
                           organized_events=organized_events,
                           shared_posts_by_user=shared_posts_by_user, # Add shared posts to context
                           bookmarked_post_ids=bookmarked_post_ids,
                           friendship_status=friendship_status,
                           pending_request_id=pending_request_id)

@app.route('/todo', methods=['GET', 'POST'])
@login_required
def todo():
    user_id = session.get('user_id')
    if not user_id: # Should be caught by @login_required
        flash("Please log in to manage your To-Do list.", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        task_id = request.form.get('task_id')
        task_content = request.form.get('task')
        due_date_str = request.form.get('due_date')
        priority = request.form.get('priority')

        if not task_content or not task_content.strip():
            flash("Task content cannot be empty.", "warning")
            return redirect(url_for('todo'))

        due_date_obj = None
        if due_date_str:
            try:
                due_date_obj = datetime.strptime(due_date_str, '%Y-%m-%d')
            except ValueError:
                flash("Invalid due date format. Please use YYYY-MM-DD.", "warning")
                return redirect(url_for('todo'))

        if task_id: # Editing existing task
            item_to_edit = TodoItem.query.filter_by(id=task_id, user_id=user_id).first()
            if item_to_edit:
                item_to_edit.task = task_content.strip()
                item_to_edit.due_date = due_date_obj
                item_to_edit.priority = priority if priority and priority.strip() else None
                db.session.commit()
                flash("To-Do item updated!", "success")
            else:
                flash("Task not found or you don't have permission to edit it.", "danger")
        else: # Adding new task
            new_todo = TodoItem(
                task=task_content.strip(),
                user_id=user_id,
                due_date=due_date_obj,
                priority=priority if priority and priority.strip() else None
            )
            db.session.add(new_todo)
            db.session.commit()
            flash("To-Do item added!", "success")

        return redirect(url_for('todo'))

    # GET request
    sort_by = request.args.get('sort_by', 'timestamp')
    order = request.args.get('order', 'asc')

    query = TodoItem.query.filter_by(user_id=user_id)

    if sort_by == 'due_date':
        if order == 'desc':
            query = query.order_by(db.nullslast(TodoItem.due_date.desc()))
        else:
            query = query.order_by(db.nullsfirst(TodoItem.due_date.asc()))
    elif sort_by == 'priority':
        priority_order = db.case(
            {_prio: i for i, _prio in enumerate(['High', 'Medium', 'Low'])},
            value=TodoItem.priority,
            else_=-1 # For None or other values, sort them as lowest
        )
        if order == 'desc': # High -> Low
            query = query.order_by(priority_order.asc()) # Lower number = higher priority
        else: # Low -> High
            query = query.order_by(priority_order.desc()) # Higher number = lower priority
    elif sort_by == 'status':
        if order == 'desc':
            query = query.order_by(TodoItem.is_done.desc())
        else:
            query = query.order_by(TodoItem.is_done.asc())
    else: # Default sort by timestamp
        if order == 'desc':
            query = query.order_by(TodoItem.timestamp.desc())
        else:
            query = query.order_by(TodoItem.timestamp.asc())

    user_todos = query.all()
    return render_template('todo.html', todos=user_todos)


@app.route('/todo/update_status/<int:item_id>', methods=['POST'])
@login_required
def update_todo_status(item_id):
    user_id = session.get('user_id')
    item_to_update = TodoItem.query.filter_by(id=item_id, user_id=user_id).first()
    if item_to_update:
        item_to_update.is_done = not item_to_update.is_done
        db.session.commit()
        flash(f"Task status updated!", "success")
    else:
        flash("Task not found or permission denied.", "danger")
    return redirect(url_for('todo'))


@app.route('/todo/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_todo_item(item_id):
    user_id = session.get('user_id')
    item_to_delete = TodoItem.query.filter_by(id=item_id, user_id=user_id).first()
    if item_to_delete:
        db.session.delete(item_to_delete)
        db.session.commit()
        flash("To-Do item deleted!", "success")
    else:
        flash("Task not found or permission denied.", "danger")
    return redirect(url_for('todo'))


@app.route('/todo/clear')
@login_required
def clear_todos():
    user_id = session.get('user_id')
    if not user_id: # Should be caught by @login_required
        flash("Please log in.", "danger")
        return redirect(url_for('login'))

    TodoItem.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    flash("All To-Do items cleared.", "success")
    return redirect(url_for('todo'))

@app.route('/gallery/upload', methods=['GET', 'POST'])
@login_required
def upload_image():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            user_id = session.get('user_id')
            if user_id:
                user = User.query.get(user_id)
                if user:
                    current_images_str = user.uploaded_images if user.uploaded_images else ""
                    image_list = [img.strip() for img in current_images_str.split(',') if img.strip()]
                    if filename not in image_list: # Avoid duplicates if re-uploading same name
                        image_list.append(filename)
                    user.uploaded_images = ','.join(image_list)
                    db.session.commit()

            flash('Image successfully uploaded!', 'success')
            return redirect(url_for('gallery'))
        else:
            flash('Allowed image types are png, jpg, jpeg, gif', 'error')
            return redirect(request.url)
    return render_template('upload_image.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/gallery')
def gallery():
    image_files = []
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if allowed_file(filename): # Use the existing allowed_file function
                image_files.append(filename)
    return render_template('gallery.html', images=image_files)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_candidate = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password_candidate):
            session['logged_in'] = True # Can keep for compatibility or remove if only user_id is used
            session['user_id'] = user.id
            session['username'] = user.username # Keep for convenience
            flash('You are now logged in!', 'success')
            return redirect(url_for('hello_world')) # Or a dashboard page if you create one
        else:
            flash('Invalid login.', 'danger')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    session.pop('username', None)
    flash('You are now logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/upload_profile_picture', methods=['GET', 'POST'])
@login_required
def upload_profile_picture():
    if request.method == 'POST':
        if 'profile_pic' not in request.files:
            flash('No file part selected.', 'warning')
            return redirect(request.url)

        file = request.files['profile_pic']

        if file.filename == '':
            flash('No file selected.', 'warning')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            # Generate a unique filename to prevent overwrites and ensure URL safety
            filename = secure_filename(file.filename)
            unique_filename = uuid.uuid4().hex + "_" + filename
            file_path = os.path.join(app.config['PROFILE_PICS_FOLDER'], unique_filename)

            try:
                file.save(file_path)

                # Update user's profile picture path in DB
                user = User.query.get(session['user_id']) # or current_user from context
                if user:
                    user.profile_picture = url_for('static', filename=f'profile_pics/{unique_filename}')
                    db.session.commit()
                    flash('Profile picture uploaded successfully!', 'success')
                    return redirect(url_for('user_profile', username=user.username))
                else:
                    flash('User not found. Please log in again.', 'danger')
                    return redirect(url_for('login'))
            except Exception as e:
                app.logger.error(f"Error saving profile picture: {e}")
                flash('An error occurred while uploading the picture. Please try again.', 'danger')
                return redirect(request.url)
        else:
            flash('Invalid file type. Allowed types are png, jpg, jpeg, gif.', 'danger')
            return redirect(request.url)

    return render_template('upload_profile_picture.html')

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user_id = session.get('user_id')
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_email = request.form.get('email', '').strip()
        new_bio = request.form.get('bio', '').strip()

        # Validate username
        if not new_username:
            flash('Username cannot be empty.', 'danger')
            return render_template('edit_profile.html', user=user)

        if new_username != user.username:
            existing_user = User.query.filter(User.username == new_username, User.id != user_id).first()
            if existing_user:
                flash('That username is already taken. Please choose a different one.', 'danger')
                return render_template('edit_profile.html', user=user)
            user.username = new_username
            session['username'] = new_username # Update session username if it changed

        # Validate email
        if not new_email: # Basic check, more complex validation (e.g., regex) could be added
            flash('Email cannot be empty.', 'danger')
            # Pass the potentially changed username back to the form
            current_form_data = {'username': new_username, 'email': user.email}
            return render_template('edit_profile.html', user=current_form_data)

        if new_email != user.email:
            existing_email_user = User.query.filter(User.email == new_email, User.id != user_id).first()
            if existing_email_user:
                flash('That email is already registered by another user. Please use a different one.', 'danger')
                current_form_data = {'username': new_username, 'email': user.email} # Keep current email if new one is bad
                return render_template('edit_profile.html', user=current_form_data)
            user.email = new_email

        user.bio = new_bio # Update bio, no complex validation for now, just strip whitespace

        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('user_profile', username=user.username))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating your profile. Please try again.', 'danger')
            app.logger.error(f"Error updating profile for user {user_id}: {e}")

    return render_template('edit_profile.html', user=user)

# Context processor to make current_user available to all templates
@app.context_processor
def inject_user():
    if 'user_id' in session:
        # Use .get() on session to avoid KeyError if 'user_id' isn't set
        user = User.query.get(session.get('user_id'))
        return dict(current_user=user)
    return dict(current_user=None)

@app.route('/discover')
@login_required
def discover_feed():
    user_id = session.get('user_id')
    if not user_id: # Should be caught by @login_required, but as a safeguard
        flash('User ID not found in session. Please log in again.', 'danger')
        return redirect(url_for('login'))

    # 1. Fetch recommendations
    recommended_posts_personalized = suggest_posts_to_read(user_id, limit=10) # Returns [(Post, "reason_string"), ...]
    trending_posts_raw = suggest_trending_posts(user_id, limit=10, since_days=7) # Returns [Post, ...]
    recommended_groups_raw = suggest_groups_to_join(user_id, limit=5) # Returns [Group, ...]
    recommended_events_raw = suggest_events_to_attend(user_id, limit=5) # Returns [Event, ...]

    # 2. Prepare data for template

    # Posts: Combine and deduplicate, preferring personalized reasons
    final_posts_map = {} # Using dict for deduplication: post.id -> (Post, "reason")

    # Add personalized posts first
    for post_obj, reason_str in recommended_posts_personalized:
        if post_obj: # Ensure post_obj is not None
            final_posts_map[post_obj.id] = (post_obj, reason_str)

    # Add trending posts, giving a generic reason if not already present with a specific one
    for post_obj in trending_posts_raw:
        if post_obj: # Ensure post_obj is not None
            if post_obj.id not in final_posts_map:
                final_posts_map[post_obj.id] = (post_obj, "Trending post")

    final_posts_with_reasons = list(final_posts_map.values())
    # Optionally, sort or limit the final_posts_with_reasons further if needed
    # For now, order is based on personalized first, then trending. Could shuffle or sort by a combined score later.

    # Groups: Add generic reasons
    groups_with_reasons = []
    for group_obj in recommended_groups_raw:
        if group_obj: # Ensure group_obj is not None
            groups_with_reasons.append((group_obj, "Recommended group"))

    # Events: Add generic reasons
    events_with_reasons = []
    for event_obj in recommended_events_raw:
        if event_obj: # Ensure event_obj is not None
            events_with_reasons.append((event_obj, "Recommended event"))

    return render_template('discover.html',
                           recommended_posts=final_posts_with_reasons,
                           recommended_groups=groups_with_reasons,
                           recommended_events=events_with_reasons)


@app.route('/blog/create', methods=['GET', 'POST'])
@login_required # This order was already correct
def create_post():
    #global blog_post_id_counter # No longer global like this
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        hashtags = request.form.get('hashtags', '') # Get hashtags
        user_id = session.get('user_id')

        if not user_id:
            flash('You must be logged in to create a post.', 'danger')
            return redirect(url_for('login'))

        new_post_db = Post(title=title, content=content, user_id=user_id, hashtags=hashtags) # Add hashtags
        db.session.add(new_post_db)
        db.session.commit() # new_post_db now has an ID

        # Log new_post activity
        try:
            activity = UserActivity(
                user_id=user_id, # Assuming user_id is current_user.id from session
                activity_type="new_post",
                related_id=new_post_db.id,
                content_preview=new_post_db.content[:100] if new_post_db.content else "",
                link=url_for('view_post', post_id=new_post_db.id, _external=True) # Use _external=True for full URL
            )
            db.session.add(activity)
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Error creating UserActivity for new_post: {e}")
            # Decide if you want to flash a message to the user or just log
            # flash('Could not log activity due to an internal error.', 'warning')
            db.session.rollback() # Rollback activity commit if it fails

        flash('Blog post created successfully!', 'success')
        return redirect(url_for('blog'))
    return render_template('create_post.html')

@app.route('/blog')
def blog():
    all_posts_query = Post.query.order_by(Post.timestamp.desc())
    all_posts = all_posts_query.all()

    bookmarked_post_ids = set()
    suggested_users_snippet = [] # Initialize as empty list

    if 'user_id' in session:
        user_id = session['user_id']
        bookmarks = Bookmark.query.filter_by(user_id=user_id).all()
        bookmarked_post_ids = {bookmark.post_id for bookmark in bookmarks}

        # Fetch user suggestions for the snippet
        suggested_users_snippet = suggest_users_to_follow(user_id, limit=3) # Get 3 suggestions

    for post_item in all_posts:
        post_item.review_count = len(post_item.reviews)
        if post_item.reviews:
            post_item.average_rating = sum(r.rating for r in post_item.reviews) / len(post_item.reviews)
        else:
            post_item.average_rating = 0
        # The number of likes will be len(post_item.likes) in the template

    trending_hashtags_list = get_trending_hashtags(top_n=10)

    return render_template('blog.html',
                           posts=all_posts,
                           bookmarked_post_ids=bookmarked_post_ids,
                           suggested_users_snippet=suggested_users_snippet,
                           trending_hashtags=trending_hashtags_list) # Pass snippet to template

@app.route('/blog/post/<int:post_id>')
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    # Use relationship for comments, ensure ordering if not default in model
    post_comments = Comment.query.with_parent(post).order_by(Comment.timestamp.asc()).all()

    # Reaction data
    post_reactions = Reaction.query.filter_by(post_id=post_id).all()
    reaction_counts = Counter(r.emoji for r in post_reactions)
    # Example: reaction_counts will be {'👍': 2, '❤️': 1}

    user_has_liked = False
    current_user_id = session.get('user_id')
    if current_user_id:
        user_has_liked = Like.query.filter_by(user_id=current_user_id, post_id=post.id).count() > 0

    # Use relationship for reviews, ensure ordering
    post_reviews = Review.query.with_parent(post).order_by(Review.timestamp.desc()).all()

    average_rating = 0
    if post_reviews:
        average_rating = sum(r.rating for r in post_reviews) / len(post_reviews)

    can_submit_review = False
    if current_user_id:
        if post.user_id == current_user_id: # Author cannot review their own post
             is_author = True
        else:
             is_author = False
        has_reviewed = Review.query.filter_by(user_id=current_user_id, post_id=post.id).count() > 0
        if not is_author and not has_reviewed:
            can_submit_review = True

    # Check if current user has bookmarked this post
    user_has_bookmarked = False
    if current_user_id: # current_user_id is already defined in this function
        db.session.expire_all() # Force refresh from DB for the session
        user_has_bookmarked = Bookmark.query.filter_by(user_id=current_user_id, post_id=post.id).first() is not None

    return render_template('view_post.html',
                           post=post,
                           comments=post_comments,
                           user_has_liked=user_has_liked,
                           post_reviews=post_reviews,
                           average_rating=average_rating,
                           can_submit_review=can_submit_review,
                           reactions=post_reactions, # Pass all reactions for detailed display if needed
                           reaction_counts=dict(reaction_counts), # Pass emoji counts
                           user_has_bookmarked=user_has_bookmarked) # Pass bookmark status

@app.route('/blog/edit/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    current_user_id = session.get('user_id')

    if post.user_id != current_user_id:
        flash('You are not authorized to edit this post.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    if request.method == 'POST':
        post.title = request.form['title']
        post.content = request.form['content']
        post.hashtags = request.form.get('hashtags', '') # Get and update hashtags
        post.last_edited = datetime.utcnow()
        db.session.commit()
        flash('Post updated successfully!', 'success')
        return redirect(url_for('view_post', post_id=post_id))

    return render_template('edit_post.html', post=post)

@app.route('/blog/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post_to_delete = Post.query.get_or_404(post_id)
    current_user_id = session.get('user_id')

    if post_to_delete.user_id != current_user_id:
        flash('You are not authorized to delete this post.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    # Cascading deletes for comments, likes, reviews are handled by the database
    # due to `cascade="all, delete-orphan"` in model definitions.
    db.session.delete(post_to_delete)
    db.session.commit()
    flash('Post deleted successfully!', 'success')
    return redirect(url_for('blog'))

@app.route('/hashtag/<tag>')
def view_hashtag_posts(tag):
    potential_posts = Post.query.filter(Post.hashtags.contains(tag)).order_by(Post.timestamp.desc()).all()

    actual_posts = []
    for post_item in potential_posts:
        if post_item.hashtags:
            tags_list = [t.strip() for t in post_item.hashtags.split(',') if t.strip()]
            if tag in tags_list:
                actual_posts.append(post_item)

    bookmarked_post_ids = set()
    if 'user_id' in session:
        user_id = session['user_id']
        bookmarks = Bookmark.query.filter_by(user_id=user_id).all()
        bookmarked_post_ids = {bookmark.post_id for bookmark in bookmarks}

    for post_item in actual_posts:
        post_item.review_count = len(post_item.reviews)
        if post_item.reviews:
            post_item.average_rating = sum(r.rating for r in post_item.reviews) / len(post_item.reviews)
        else:
            post_item.average_rating = 0

    return render_template('hashtag_posts.html', posts=actual_posts, tag=tag, bookmarked_post_ids=bookmarked_post_ids)

@app.route('/blog/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    comment_content = request.form.get('comment_content')
    user_id = session.get('user_id')

    if not user_id: # Should be caught by @login_required, but defensive check
        flash('You must be logged in to comment.', 'danger')
        return redirect(url_for('login'))

    if not comment_content or not comment_content.strip():
        flash('Comment content cannot be empty!', 'warning')
        return redirect(url_for('view_post', post_id=post_id))

    new_comment_db = Comment(content=comment_content, user_id=user_id, post_id=post.id)
    db.session.add(new_comment_db)
    db.session.commit() # new_comment_db now has an ID

    # Log new_comment activity
    try:
        activity = UserActivity(
            user_id=user_id, # user_id of the commenter
            activity_type="new_comment",
            related_id=post.id, # id of the post being commented on
            content_preview=new_comment_db.content[:100] if new_comment_db.content else "",
            link=url_for('view_post', post_id=post.id, _external=True) # Link to the post
            # Optionally, could try to append #comment-<comment_id> if view_post supports it
            # link=url_for('view_post', post_id=post.id, _anchor=f'comment-{new_comment_db.id}', _external=True)
        )
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        app.logger.error(f"Error creating UserActivity for new_comment: {e}")
        db.session.rollback()

    # Prepare data for SocketIO emission (ensure it's serializable)
    new_comment_data_for_post_room = {
        "id": new_comment_db.id,
        "post_id": new_comment_db.post_id,
        "author_username": new_comment_db.author.username, # Assumes Comment.author relationship gives User
        "content": new_comment_db.content,
        "timestamp": new_comment_db.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    }
    socketio.emit('new_comment_event', new_comment_data_for_post_room, room=f'post_{post_id}')

    # Notification for post author
    post_author_id = post.user_id
    commenter_id = session.get('user_id') # This is the current user who is commenting

    if post_author_id != commenter_id:
        # Ensure commenter's User object is available for username
        commenter_user = User.query.get(commenter_id)
        if commenter_user: # Should always be true if user_id in session is valid
            notification_data = {
                'post_id': post.id,
                'commenter_username': commenter_user.username,
                'comment_content': new_comment_db.content,
                'post_title': post.title
            }
            socketio.emit('new_comment_notification', notification_data, room=f'user_{post_author_id}')
            app.logger.info(f"Sent new_comment_notification to user_{post_author_id} for post {post.id}")
        else:
            app.logger.error(f"Could not find commenter user object for ID {commenter_id} when sending notification.")

    flash('Comment added successfully!', 'success')
    return redirect(url_for('view_post', post_id=post_id))


@app.route('/blog/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = session.get('user_id')

    if not user_id: # Should be caught by @login_required
        flash('You must be logged in to like posts.', 'danger')
        return redirect(url_for('login'))

    existing_like = Like.query.filter_by(user_id=user_id, post_id=post.id).first()
    if not existing_like:
        new_like = Like(user_id=user_id, post_id=post.id)
        db.session.add(new_like)
        # Try to commit the like first
        try:
            db.session.commit()
            flash('Post liked!', 'success')

            # After successfully liking, create UserActivity
            try:
                activity = UserActivity(
                    user_id=user_id,
                    activity_type="new_like",
                    related_id=post.id,
                    content_preview=post.content[:100] if post.content else "",
                    link=url_for('view_post', post_id=post.id, _external=True)
                )
                db.session.add(activity)
                db.session.commit()
            except Exception as e:
                app.logger.error(f"Error creating UserActivity for new_like: {e}")
                # Rollback the UserActivity commit, but not the Like commit
                db.session.rollback()
                # Optionally, flash a less critical message or just log
                # flash('Activity could not be logged, but your like was successful.', 'warning')

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error liking post or creating UserActivity: {e}")
            flash('An error occurred while liking the post.', 'danger')

    else:
        flash('You have already liked this post.', 'info')

    return redirect(url_for('view_post', post_id=post_id))

@app.route('/blog/post/<int:post_id>/unlike', methods=['POST'])
@login_required
def unlike_post(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = session.get('user_id')

    if not user_id: # Should be caught by @login_required
        flash('You must be logged in to unlike posts.', 'danger')
        return redirect(url_for('login'))

    like_to_delete = Like.query.filter_by(user_id=user_id, post_id=post.id).first()
    if like_to_delete:
        db.session.delete(like_to_delete)
        db.session.commit()
        flash('Post unliked!', 'success')
    else:
        flash('You have not liked this post yet.', 'info')

    return redirect(url_for('view_post', post_id=post_id))


@app.route('/blog/post/<int:post_id>/review', methods=['POST'])
@login_required
def add_review(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = session.get('user_id')

    if not user_id: # Should be caught by @login_required
        flash('You must be logged in to review posts.', 'danger')
        return redirect(url_for('login'))

    if post.user_id == user_id:
        flash('You cannot review your own post.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    existing_review = Review.query.filter_by(user_id=user_id, post_id=post.id).first()
    if existing_review:
        flash('You have already reviewed this post.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    rating_str = request.form.get('rating')
    review_text = request.form.get('review_text')

    if not rating_str:
        flash('Rating is required.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))
    try:
        rating = int(rating_str)
        if not (1 <= rating <= 5): raise ValueError
    except ValueError:
        flash('Rating must be an integer between 1 and 5 stars.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    if not review_text or not review_text.strip():
        flash('Review text cannot be empty.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    new_review_db = Review(rating=rating, review_text=review_text.strip(), user_id=user_id, post_id=post.id)
    db.session.add(new_review_db)
    db.session.commit()
    flash('Review submitted successfully!', 'success')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/post/<int:post_id>/react', methods=['POST'])
@login_required
def react_to_post(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = session.get('user_id') # Assuming current_user.id from session
    emoji = request.form.get('emoji')

    if not emoji:
        flash('No emoji provided for reaction.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    # Check if user has already reacted with this specific emoji
    existing_reaction_same_emoji = Reaction.query.filter_by(
        user_id=user_id,
        post_id=post_id,
        emoji=emoji
    ).first()

    if existing_reaction_same_emoji:
        # User clicked the same emoji again - remove reaction (toggle off)
        db.session.delete(existing_reaction_same_emoji)
        flash('Reaction removed.', 'success')
    else:
        # User clicked a new emoji or has no reaction yet.
        # Check if the user has reacted with any other emoji on this post
        existing_reaction_any_emoji = Reaction.query.filter_by(
            user_id=user_id,
            post_id=post_id
        ).first()

        if existing_reaction_any_emoji:
            # User is changing their reaction
            existing_reaction_any_emoji.emoji = emoji
            existing_reaction_any_emoji.timestamp = datetime.utcnow() # Update timestamp
            flash('Reaction updated.', 'success')
        else:
            # New reaction
            new_reaction = Reaction(user_id=user_id, post_id=post_id, emoji=emoji)
            db.session.add(new_reaction)
            flash('Reaction added.', 'success')

    db.session.commit()
    return redirect(url_for('view_post', post_id=post_id))


@app.route('/bookmark/<int:post_id>', methods=['POST'])
@login_required
def bookmark_post(post_id):
    post = Post.query.get_or_404(post_id)
    # current_user is made available to templates by context_processor,
    # but in view functions, it's better to rely on session or flask_login's current_user proxy.
    # flask_login.current_user would be the most robust way if Flask-Login is fully configured.
    # For now, using session.get('user_id') as it's consistently used in this file.
    user_id = session.get('user_id')

    if not user_id: # This check is technically redundant due to @login_required
        flash('You must be logged in to bookmark posts.', 'danger')
        # abort(401) # Or redirect to login
        return redirect(url_for('login'))

    existing_bookmark = Bookmark.query.filter_by(user_id=user_id, post_id=post.id).first()

    if existing_bookmark:
        db.session.delete(existing_bookmark)
        db.session.commit()
        flash('Post unbookmarked.', 'success')
    else:
        new_bookmark = Bookmark(user_id=user_id, post_id=post.id)
        db.session.add(new_bookmark)
        db.session.commit()
        flash('Post bookmarked!', 'success')

    return redirect(url_for('view_post', post_id=post_id))


@app.route('/post/<int:post_id>/share', methods=['POST'])
@login_required
def share_post(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = session.get('user_id')

    if not user_id: # Should be caught by @login_required, but as a safeguard
        flash('You must be logged in to share posts.', 'danger')
        return redirect(url_for('login'))

    # Check if the user is trying to share their own post - allow this
    # if post.user_id == user_id:
    #     flash("You cannot share your own post.", 'warning')
    #     return redirect(url_for('view_post', post_id=post_id))

    # Check if this user has already shared this specific post
    existing_share = SharedPost.query.filter_by(
        original_post_id=post.id,
        shared_by_user_id=user_id
    ).first()

    if existing_share:
        flash('You have already shared this post.', 'info')
        return redirect(url_for('view_post', post_id=post_id))

    sharing_comment = request.form.get('sharing_comment') # Optional comment

    new_share = SharedPost(
        original_post_id=post.id,
        shared_by_user_id=user_id,
        sharing_user_comment=sharing_comment
    )
    db.session.add(new_share)
    db.session.commit()

    flash('Post shared successfully!', 'success')
    return redirect(url_for('view_post', post_id=post_id))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return render_template('register.html')

        # Create new User object and add to DB
        new_user_db = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(new_user_db)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/messages/send/<receiver_username>', methods=['GET', 'POST'])
@login_required
def send_message(receiver_username):
    receiver_user = User.query.filter_by(username=receiver_username).first()
    if not receiver_user:
        flash('User not found.', 'danger')
        return redirect(url_for('hello_world'))

    sender_id = session.get('user_id')
    if not sender_id:
        flash('You must be logged in to send messages.', 'danger')
        return redirect(url_for('login'))

    receiver = User.query.filter_by(username=receiver_username).first()
    if not receiver:
        flash('Recipient user not found.', 'danger')
        return redirect(url_for('hello_world')) # Or an appropriate redirect

    if request.method == 'POST':
        content = request.form.get('content')
        if not content or not content.strip():
            flash('Message content cannot be empty.', 'warning')
            return render_template('send_message.html', receiver_username=receiver_username)

        new_message_db = Message(sender_id=sender_id, receiver_id=receiver.id, content=content)
        db.session.add(new_message_db)
        db.session.commit()
        flash('Message sent successfully!', 'success')
        return redirect(url_for('view_conversation', username=receiver_username))

    return render_template('send_message.html', receiver_username=receiver_username)


@app.route('/messages/conversation/<username>')
@login_required
def view_conversation(username):
    current_user_id = session.get('user_id')
    if not current_user_id:
        flash('Please log in to view conversations.', 'danger')
        return redirect(url_for('login'))

    conversation_partner = User.query.filter_by(username=username).first()
    if not conversation_partner:
        flash('User not found.', 'danger')
        return redirect(url_for('hello_world')) # Or inbox

    other_user_id = conversation_partner.id

    relevant_messages = Message.query.filter(
        or_(
            (Message.sender_id == current_user_id) & (Message.receiver_id == other_user_id),
            (Message.sender_id == other_user_id) & (Message.receiver_id == current_user_id)
        )
    ).order_by(Message.timestamp.asc()).all()

    # Mark messages as read
    updated = False
    for msg in relevant_messages:
        if msg.receiver_id == current_user_id and not msg.is_read:
            msg.is_read = True
            updated = True
    if updated:
        db.session.commit()

    return render_template('conversation.html', conversation_partner=username, messages_list=relevant_messages)


@app.route('/messages/inbox')
@login_required
def inbox():
    current_user_id = session.get('user_id')
    if not current_user_id: # Should be caught by @login_required
        flash('Please log in to view your inbox.', 'danger')
        return redirect(url_for('login'))

    # Get all unique user IDs the current user has had conversations with
    sent_to_users = db.session.query(Message.receiver_id).filter(Message.sender_id == current_user_id).distinct()
    received_from_users = db.session.query(Message.sender_id).filter(Message.receiver_id == current_user_id).distinct()

    other_user_ids = set()
    for user_tuple in sent_to_users:
        other_user_ids.add(user_tuple[0])
    for user_tuple in received_from_users:
        other_user_ids.add(user_tuple[0])

    inbox_items = []
    for other_id in other_user_ids:
        other_user = User.query.get(other_id)
        if not other_user:
            continue # Should not happen if DB is consistent

        last_message = Message.query.filter(
            or_(
                (Message.sender_id == current_user_id) & (Message.receiver_id == other_id),
                (Message.sender_id == other_id) & (Message.receiver_id == current_user_id)
            )
        ).order_by(Message.timestamp.desc()).first()

        unread_count = Message.query.filter_by(
            sender_id=other_id,
            receiver_id=current_user_id,
            is_read=False
        ).count()

        if last_message: # Should always be true if other_id was found via messages
            snippet = last_message.content[:50] + "..." if len(last_message.content) > 50 else last_message.content
            inbox_items.append({
                'username': other_user.username,
                'last_message_snippet': snippet,
                'last_message_display_timestamp': last_message.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                'last_message_datetime': last_message.timestamp, # For sorting
                'unread_count': unread_count
            })

    # Sort inbox items by the actual datetime of the last message, newest first
    inbox_items.sort(key=lambda x: x['last_message_datetime'], reverse=True)

    return render_template('inbox.html', inbox_items=inbox_items)


@app.route('/notifications')
@login_required
def view_notifications():
    # For now, show all notifications, newest first.
    # Later, this can be filtered by user, read status, etc.
    # Also, consider pagination for many notifications.

    # Sort notifications by timestamp, newest first
    # Assuming timestamp is stored as string: "YYYY-MM-DD HH:MM:S"
    # Need to convert to datetime objects for sorting if not already.
    # The notification timestamp is set by current_check_time.strftime, so it's a string.

    # TODO: Implement user-specific notifications by filtering by Notification.user_id
    # For now, shows all notifications system-wide.
    notifications_to_display = Notification.query.order_by(Notification.timestamp.desc()).all()
    # Logic for marking as read could be:
    # - When user visits /notifications, mark all their unread notifications as read.
    # - When user visits a specific item (e.g., post, event), mark related notification as read.
    # This is not implemented in this step.
    return render_template('notifications.html', notifications=notifications_to_display)

@socketio.on('join_room')
def handle_join_room_event(data):
    app.logger.info(f"User {session.get('username', 'Anonymous')} joined room: {data['room']}")
    join_room(data['room'])

# with app.app_context():
#     if not os.path.exists(os.path.join(app.root_path, 'site.db')):  # Check if db file exists in instance folder
#         db.create_all()
#         print("Database created!")
#         # Try to create demo user only if DB was just created
#         demo_user = User.query.filter_by(username="demo").first()
#         if not demo_user:
#             hashed_password = generate_password_hash("password123")
#             new_demo_user = User(username="demo", password_hash=hashed_password)
#             db.session.add(new_demo_user)
#             db.session.commit()
#             print("Demo user created.")
#         else:
#             print("Demo user already exists.")
#     else:
#         print("Database already exists.")
#         # Check and create demo user if DB exists but demo user might be missing (e.g. manual DB deletion)
#         demo_user = User.query.filter_by(username="demo").first()
#         if not demo_user:
#             hashed_password = generate_password_hash("password123")
#             new_demo_user = User(username="demo", password_hash=hashed_password)
#             db.session.add(new_demo_user)
#             db.session.commit()
#             print("Demo user created as it was missing from existing DB.")
#         else:
#             print("Demo user confirmed to exist in existing DB.")

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return {'message': 'Username and password are required'}, 400

    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password_hash, password):
        access_token = create_access_token(identity=user.id) # Use user.id as identity
        return {'access_token': access_token}, 200
    else:
        return {'message': 'Invalid credentials'}, 401


if __name__ == '__main__':
    # Start the scheduler only once, even with Flask reloader
    # The os.environ.get('WERKZEUG_RUN_MAIN') check ensures this runs in the main Flask process,
    # not the reloader's process.
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        if not scheduler.running: # Ensure scheduler is not started more than once
            # Add the job before starting the scheduler
            scheduler.add_job(func=generate_activity_summary, trigger="interval", minutes=1)
            scheduler.start()
            print("Scheduler started.")
            # It's good practice to shut down the scheduler when the app exits
            import atexit
            atexit.register(lambda: scheduler.shutdown())
            print("Scheduler shutdown registered.")
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)


@app.route('/polls/create', methods=['GET', 'POST'])
@login_required
def create_poll():
    if request.method == 'POST':
        question = request.form.get('question')
        options_texts = request.form.getlist('options[]')
        user_id = session.get('user_id')

        if not user_id: # Should be caught by @login_required
            flash('You must be logged in to create a poll.', 'danger')
            return redirect(url_for('login'))

        if not question or not question.strip():
            flash('Poll question cannot be empty.', 'danger')
            return render_template('create_poll.html')

        valid_options_texts = [opt.strip() for opt in options_texts if opt and opt.strip()]
        if len(valid_options_texts) < 2:
            flash('Please provide at least two valid options for the poll.', 'danger')
            return render_template('create_poll.html')

        new_poll_db = Poll(question=question.strip(), user_id=user_id)

        for option_text in valid_options_texts:
            # SQLAlchemy will handle associating poll_id if 'poll' backref is used
            new_poll_db.options.append(PollOption(text=option_text))
            # Or, less commonly for one-to-many from parent:
            # poll_option = PollOption(text=option_text, poll_id=new_poll_db.id)
            # db.session.add(poll_option)

        db.session.add(new_poll_db) # Add parent, children are cascaded if configured
        db.session.commit()

        flash('Poll created successfully!', 'success')
        return redirect(url_for('polls_list')) # Redirect to polls list

    return render_template('create_poll.html')


@app.route('/polls')
def polls_list():
    all_polls = Poll.query.order_by(Poll.created_at.desc()).all()
    return render_template('polls.html', polls=all_polls)


@app.route('/events/create', methods=['GET', 'POST'])
@login_required
def create_event():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        event_date_str = request.form.get('event_date') # Stored as string in model
        event_time_str = request.form.get('event_time') # Stored as string
        location = request.form.get('location')

        if not title or not title.strip():
            flash('Event title is required.', 'danger')
            return render_template('create_event.html')
        if not event_date_str: # Basic validation
            flash('Event date is required.', 'danger')
            return render_template('create_event.html')

        # Datetime conversion/validation could be added here if desired before saving
        # For now, saving as strings as per model definition.
        user_id = session.get('user_id')
        if not user_id: # Should be caught by @login_required
            flash('You must be logged in to create an event.', 'danger')
            return redirect(url_for('login'))

        new_event_db = Event(
            title=title.strip(),
            description=description.strip() if description else "",
            date=event_date_str,
            time=event_time_str if event_time_str else "",
            location=location.strip() if location else "",
            user_id=user_id
        )
        db.session.add(new_event_db)
        db.session.commit() # new_event_db now has an ID

        # Log new_event activity
        try:
            activity = UserActivity(
                user_id=user_id, # user_id of the event creator
                activity_type="new_event",
                related_id=new_event_db.id,
                content_preview=new_event_db.title[:100] if new_event_db.title else "", # Preview is event title
                link=url_for('view_event', event_id=new_event_db.id, _external=True)
            )
            db.session.add(activity)
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Error creating UserActivity for new_event: {e}")
            db.session.rollback()

        flash('Event created successfully!', 'success')
        return redirect(url_for('events_list'))

    return render_template('create_event.html')


@app.route('/poll/<int:poll_id>')
def view_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)

    user_has_voted = False
    user_vote_option_id = None
    total_votes_for_poll = 0
    current_user_id = session.get('user_id')

    if current_user_id:
        existing_vote = PollVote.query.filter_by(user_id=current_user_id, poll_id=poll.id).first()
        if existing_vote:
            user_has_voted = True
            user_vote_option_id = existing_vote.poll_option_id

    options_display_data = []
    for option in poll.options:
        vote_count = len(option.votes) # Use relationship for count
        options_display_data.append({
            "id": option.id,
            "text": option.text,
            "vote_count": vote_count
        })
        total_votes_for_poll += vote_count

    # Attach the processed options data to the poll object for the template
    poll.options_display = options_display_data

    return render_template('view_poll.html', poll=poll, user_has_voted=user_has_voted, user_vote=user_vote_option_id, total_votes=total_votes_for_poll)


@app.route('/poll/<int:poll_id>/vote', methods=['POST'])
@login_required
def vote_on_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    selected_option_id_str = request.form.get('option_id')
    user_id = session.get('user_id')

    if not user_id: # Should be caught by @login_required
        flash('You must be logged in to vote.', 'danger')
        return redirect(url_for('login'))

    if not selected_option_id_str:
        flash('No option selected.', 'danger')
        return redirect(url_for('view_poll', poll_id=poll_id))

    try:
        selected_option_id = int(selected_option_id_str)
    except ValueError:
        flash('Invalid option ID.', 'danger')
        return redirect(url_for('view_poll', poll_id=poll_id))

    option_to_vote = PollOption.query.filter_by(id=selected_option_id, poll_id=poll.id).first()
    if not option_to_vote:
        flash('Invalid option selected for this poll.', 'danger')
        return redirect(url_for('view_poll', poll_id=poll_id))

    existing_vote = PollVote.query.filter_by(user_id=user_id, poll_id=poll.id).first()
    if existing_vote:
        flash('You have already voted on this poll.', 'warning')
        return redirect(url_for('view_poll', poll_id=poll_id))

    new_vote = PollVote(user_id=user_id, poll_option_id=selected_option_id, poll_id=poll.id)
    db.session.add(new_vote)
    db.session.commit()

    flash('Vote cast successfully!', 'success')
    return redirect(url_for('view_poll', poll_id=poll_id))


@app.route('/poll/<int:poll_id>/delete', methods=['POST'])
@login_required
def delete_poll(poll_id):
    poll_to_delete = Poll.query.get_or_404(poll_id)
    user_id = session.get('user_id')

    if not user_id: # Should be caught by @login_required
        flash('You must be logged in to delete polls.', 'danger')
        return redirect(url_for('login'))

    if poll_to_delete.user_id != user_id:
        flash('You are not authorized to delete this poll.', 'danger')
        return redirect(url_for('view_poll', poll_id=poll_id))

    # Cascading deletes for PollOption and PollVote are handled by the DB relationships
    db.session.delete(poll_to_delete)
    db.session.commit()

    flash('Poll deleted successfully!', 'success')
    return redirect(url_for('polls_list'))


@app.route('/events')
@login_required
def events_list():
    # TODO: Add proper date sorting for string dates, or change model to use DateTime
    # For now, sorting by ID or creation date as a proxy
    all_events = Event.query.order_by(Event.created_at.desc()).all()
    # If Event.date was a DateTime field, you'd use:
    # all_events = Event.query.order_by(Event.date.asc()).all()

    return render_template('events.html', events=all_events)


@app.route('/event/<int:event_id>')
def view_event(event_id):
    event = Event.query.get_or_404(event_id)

    rsvp_counts = {"Attending": 0, "Maybe": 0, "Not Attending": 0}
    user_rsvp_status = None
    current_user_id = session.get('user_id')

    if current_user_id:
        user_rsvp = EventRSVP.query.filter_by(user_id=current_user_id, event_id=event.id).first()
        if user_rsvp:
            user_rsvp_status = user_rsvp.status

    # Calculate RSVP counts using the relationship
    for rsvp_entry in event.rsvps:
        if rsvp_entry.status in rsvp_counts:
            rsvp_counts[rsvp_entry.status] += 1

    is_organizer = (current_user_id == event.user_id)

    return render_template('view_event.html',
                           event=event,
                           rsvp_counts=rsvp_counts,
                           user_rsvp_status=user_rsvp_status,
                           is_organizer=is_organizer)


@app.route('/event/<int:event_id>/rsvp', methods=['POST'])
@login_required
def rsvp_event(event_id):
    event = Event.query.get_or_404(event_id)
    rsvp_status = request.form.get('rsvp_status')
    valid_statuses = ["Attending", "Maybe", "Not Attending"]

    if not rsvp_status or rsvp_status not in valid_statuses:
        flash('Invalid RSVP status submitted.', 'danger')
        return redirect(url_for('view_event', event_id=event_id))

    user_id = session.get('user_id')
    if not user_id: # Should be caught by @login_required
        flash('You must be logged in to RSVP.', 'danger')
        return redirect(url_for('login'))

    existing_rsvp = EventRSVP.query.filter_by(user_id=user_id, event_id=event.id).first()
    if existing_rsvp:
        existing_rsvp.status = rsvp_status
    else:
        new_rsvp = EventRSVP(status=rsvp_status, user_id=user_id, event_id=event.id)
        db.session.add(new_rsvp)

    db.session.commit()
    flash(f'Your RSVP ("{rsvp_status}") has been recorded!', 'success')
    return redirect(url_for('view_event', event_id=event_id))


@app.route('/event/<int:event_id>/delete', methods=['POST'])
@login_required
def delete_event(event_id):
    event_to_delete = Event.query.get_or_404(event_id)
    user_id = session.get('user_id')

    if not user_id: # Should be caught by @login_required
        flash('You must be logged in to delete events.', 'danger')
        return redirect(url_for('login'))

    if event_to_delete.user_id != user_id:
        flash('You are not authorized to delete this event.', 'danger')
        return redirect(url_for('view_event', event_id=event_id))

    # Cascading deletes for EventRSVP are handled by the DB relationships
    db.session.delete(event_to_delete)
    db.session.commit()

    flash('Event deleted successfully.', 'success')
    return redirect(url_for('events_list'))

@app.route('/trigger_notifications_test_only')
@login_required # Or some other protection if desired
def trigger_notifications_test_only():
    if app.debug: # Only allow in debug mode for safety
        generate_activity_summary()
        flash('Notification generation triggered for test.', 'info')
        return redirect(url_for('view_notifications'))
    else:
        flash('This endpoint is for testing only and disabled in production.', 'danger')
        return redirect(url_for('hello_world'))

@app.route('/groups')
def groups_list():
    all_groups = Group.query.order_by(Group.created_at.desc()).all()
    return render_template('groups_list.html', groups=all_groups)

@app.route('/group/<int:group_id>')
def view_group(group_id):
    group = Group.query.get_or_404(group_id)
    current_user_is_member = False
    if 'user_id' in session:
        user_id = session['user_id']
        # Check if the user is a member. group.members is a dynamic query.
        current_user_is_member = group.members.filter(User.id == user_id).count() > 0

    return render_template('group_detail.html', group=group, current_user_is_member=current_user_is_member)

@app.route('/groups/create', methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        user_id = session.get('user_id')

        if not name or not name.strip():
            flash('Group name is required.', 'danger')
            return render_template('create_group.html')

        existing_group = Group.query.filter_by(name=name.strip()).first()
        if existing_group:
            flash('A group with this name already exists. Please choose a different name.', 'danger')
            return render_template('create_group.html')

        current_user = User.query.get(user_id)
        if not current_user: # Should not happen if @login_required works
            flash('User not found. Please log in again.', 'danger')
            return redirect(url_for('login'))

        new_group = Group(name=name.strip(), description=description.strip(), creator_id=user_id)
        # Add the creator as the first member
        new_group.members.append(current_user) # SQLAlchemy handles the association table

        db.session.add(new_group)
        db.session.commit()

        flash(f'Group "{new_group.name}" created successfully!', 'success')
        # Eventually, redirect to url_for('view_group', group_id=new_group.id)
        # For now, let's redirect to a placeholder or the future groups list
        return redirect(url_for('groups_list')) # Assumes 'groups_list' will be created

    return render_template('create_group.html')

@app.route('/group/<int:group_id>/join', methods=['POST'])
@login_required
def join_group(group_id):
    group = Group.query.get_or_404(group_id)
    user_id = session.get('user_id')
    current_user = User.query.get(user_id)

    if not current_user: # Should be caught by @login_required
        flash('User not found. Please log in again.', 'danger')
        return redirect(url_for('login'))

    # Check if already a member
    if group.members.filter(User.id == user_id).count() > 0:
        flash('You are already a member of this group.', 'info')
    else:
        group.members.append(current_user)
        db.session.commit()
        flash(f'You have successfully joined the group: {group.name}!', 'success')

    return redirect(url_for('view_group', group_id=group_id))


@app.route('/bookmarks')
@login_required
def bookmarked_posts():
    user_id = session.get('user_id')
    # Query for bookmarks by the current user, ordering by when they were bookmarked (newest first)
    bookmarks = Bookmark.query.filter_by(user_id=user_id).order_by(Bookmark.timestamp.desc()).all()

    # Extract the Post objects from the bookmarks
    # This will result in N+1 queries if not careful.
    # A more optimized way would be to join Post table in the initial query if displaying post details directly.
    # For now, let's get posts one by one, or selectinload if we assume post object is needed.
    # posts = [bookmark.post for bookmark in bookmarks]
    # However, if bookmark.post relationship is well defined, SQLAlchemy might handle it efficiently.
    # Let's try with a join to be more explicit and efficient.

    bookmarked_posts_query = Post.query.join(Bookmark, Post.id == Bookmark.post_id)\
                                   .filter(Bookmark.user_id == user_id)\
                                   .order_by(Bookmark.timestamp.desc())

    # Add review and like counts, similar to the main blog page
    posts_to_display = []
    for post_item in bookmarked_posts_query.all():
        post_item.review_count = len(post_item.reviews)
        if post_item.reviews:
            post_item.average_rating = sum(r.rating for r in post_item.reviews) / len(post_item.reviews)
        else:
            post_item.average_rating = 0
        # The number of likes will be len(post_item.likes) in the template
        posts_to_display.append(post_item)

    return render_template('bookmarks.html', posts=posts_to_display)

# @app.route('/api/login', methods=['POST'])
# def api_login():
#     data = request.get_json()
#     username = data.get('username')
#     password = data.get('password')
#
#     if not username or not password:
#         return {'message': 'Username and password are required'}, 400
#
#     user = User.query.filter_by(username=username).first()
#
#     if user and check_password_hash(user.password_hash, password):
#         access_token = create_access_token(identity=user.id) # Use user.id as identity
#         return {'access_token': access_token}, 200
#     else:
#         return {'message': 'Invalid credentials'}, 401

@app.route('/group/<int:group_id>/leave', methods=['POST'])
@login_required
def leave_group(group_id):
    group = Group.query.get_or_404(group_id)
    user_id = session.get('user_id')
    current_user = User.query.get(user_id)

    if not current_user: # Should be caught by @login_required
        flash('User not found. Please log in again.', 'danger')
        return redirect(url_for('login'))

    # Check if the user is the creator; prevent leaving if so (optional rule)
    # For this implementation, let's assume creators can leave, but they'd lose creator status visibility
    # A more complex system might prevent creator from leaving or require transferring ownership.
    # For now, we allow it.

    member_to_remove = group.members.filter(User.id == user_id).first()
    if member_to_remove:
        group.members.remove(member_to_remove)
        db.session.commit()
        flash(f'You have successfully left the group: {group.name}.', 'success')
    else:
        flash('You are not a member of this group.', 'info')

    return redirect(url_for('view_group', group_id=group_id))


@app.route('/user/<int:target_user_id>/send_friend_request', methods=['POST'])
@login_required
def send_friend_request(target_user_id):
    current_user_id = session.get('user_id')
    if not current_user_id: # Should be caught by @login_required
        flash('Please log in to send friend requests.', 'danger')
        return redirect(url_for('login'))

    target_user = User.query.get(target_user_id)
    if not target_user:
        flash('Target user not found.', 'danger')
        return redirect(request.referrer or url_for('hello_world'))

    if current_user_id == target_user_id:
        flash('You cannot send a friend request to yourself.', 'warning')
        return redirect(url_for('user_profile', username=target_user.username))

    # Check if a friendship request already exists or they are already friends
    existing_friendship = Friendship.query.filter(
        or_(
            (Friendship.user_id == current_user_id) & (Friendship.friend_id == target_user_id),
            (Friendship.user_id == target_user_id) & (Friendship.friend_id == current_user_id)
        )
    ).first()

    if existing_friendship:
        if existing_friendship.status == 'pending':
            # If the current user is the one who received the pending request, they can't send another one.
            # If the current user is the one who sent it, this also applies.
            flash('Friend request already sent or received and pending.', 'info')
        elif existing_friendship.status == 'accepted':
            flash('You are already friends with this user.', 'info')
        elif existing_friendship.status == 'rejected':
             # Allow sending a new request if a previous one was rejected by the target_user
            if existing_friendship.friend_id == current_user_id: # If current user rejected it
                flash('You previously rejected a friend request from this user. You can accept it from your requests page if still valid, or they can send a new one.', 'info')
            else: # target_user rejected it, so current_user can send a new one
                db.session.delete(existing_friendship) # Remove old rejected request
                new_request = Friendship(user_id=current_user_id, friend_id=target_user_id, status='pending')
                db.session.add(new_request)
                db.session.commit()
                flash('Friend request sent successfully. (Previous rejection overridden)', 'success')
        return redirect(url_for('user_profile', username=target_user.username))

    # If no existing friendship or a previous one was rejected by target_user and now deleted
    new_request = Friendship(user_id=current_user_id, friend_id=target_user_id, status='pending')
    db.session.add(new_request)
    db.session.commit()

    flash('Friend request sent successfully.', 'success')
    return redirect(url_for('user_profile', username=target_user.username))


@app.route('/friend_requests')
@login_required
def view_friend_requests():
    current_user_id = session.get('user_id')
    if not current_user_id: # Should be caught by @login_required
        flash('Please log in to view friend requests.', 'danger')
        return redirect(url_for('login'))

    # Incoming friend requests for the current user that are pending
    # The backref 'requester' on Friendship model (linked to Friendship.user_id)
    # will give us the User object of who sent the request.
    pending_requests = Friendship.query.filter_by(friend_id=current_user_id, status='pending').all()

    # For each Friendship object in pending_requests, `item.requester` will be the User who sent it.
    return render_template('friend_requests.html', pending_requests=pending_requests)


@app.route('/user/<username>/friends')
def view_friends_list(username):
    user = User.query.filter_by(username=username).first_or_404()
    friends_list = user.get_friends() # This method should return a list of User objects
    return render_template('friends_list.html', user=user, friends_list=friends_list)


@app.route('/friend_request/<int:request_id>/accept', methods=['POST'])
@login_required
def accept_friend_request(request_id):
    current_user_id = session.get('user_id')
    friend_request = Friendship.query.get(request_id)

    if not friend_request:
        flash('Friend request not found.', 'danger')
        return redirect(url_for('view_friend_requests'))

    if friend_request.friend_id != current_user_id:
        flash('You are not authorized to respond to this friend request.', 'danger')
        return redirect(url_for('view_friend_requests'))

    if friend_request.status == 'pending':
        friend_request.status = 'accepted'
        db.session.commit()
        flash('Friend request accepted successfully!', 'success')
        # Redirect to the profile of the user who sent the request
        return redirect(url_for('user_profile', username=friend_request.requester.username))
    elif friend_request.status == 'accepted':
        flash('You are already friends with this user.', 'info')
    else: # 'rejected' or other statuses
        flash('This friend request is no longer pending or cannot be accepted.', 'warning')

    return redirect(url_for('view_friend_requests'))


@app.route('/friend_request/<int:request_id>/reject', methods=['POST'])
@login_required
def reject_friend_request(request_id):
    current_user_id = session.get('user_id')
    friend_request = Friendship.query.get(request_id)

    if not friend_request:
        flash('Friend request not found.', 'danger')
        return redirect(url_for('view_friend_requests'))

    if friend_request.friend_id != current_user_id:
        flash('You are not authorized to respond to this friend request.', 'danger')
        return redirect(url_for('view_friend_requests'))

    if friend_request.status == 'pending':
        friend_request.status = 'rejected' # Or db.session.delete(friend_request)
        db.session.commit()
        flash('Friend request rejected.', 'success')
    elif friend_request.status == 'rejected':
        flash('This friend request has already been rejected.', 'info')
    else: # 'accepted' or other statuses
        flash('This friend request is no longer pending or cannot be rejected.', 'warning')

    return redirect(url_for('view_friend_requests'))


@app.route('/user/<int:friend_user_id>/remove_friend', methods=['POST'])
@login_required
def remove_friend(friend_user_id):
    current_user_id = session.get('user_id')
    friend_user = User.query.get(friend_user_id)

    if not friend_user:
        flash('User not found.', 'danger')
        # Redirect to a sensible default, like the user's own profile or homepage
        current_user_obj = User.query.get(current_user_id)
        if current_user_obj:
             return redirect(url_for('user_profile', username=current_user_obj.username))
        return redirect(url_for('hello_world'))


    if current_user_id == friend_user_id:
        flash('You cannot remove yourself as a friend.', 'warning')
        return redirect(url_for('user_profile', username=friend_user.username))

    friendship_to_remove = Friendship.query.filter(
        Friendship.status == 'accepted',
        or_(
            (Friendship.user_id == current_user_id) & (Friendship.friend_id == friend_user_id),
            (Friendship.user_id == friend_user_id) & (Friendship.friend_id == current_user_id)
        )
    ).first()

    if friendship_to_remove:
        db.session.delete(friendship_to_remove)
        db.session.commit()
        flash(f'You are no longer friends with {friend_user.username}.', 'success')
    else:
        flash(f'You are not currently friends with {friend_user.username}.', 'info')

    return redirect(url_for('user_profile', username=friend_user.username))


@app.route('/user/<username>/activity')
@login_required
def user_activity_feed(username):
    user = User.query.filter_by(username=username).first_or_404()
    activities = UserActivity.query.filter_by(user_id=user.id)\
                                   .order_by(UserActivity.timestamp.desc())\
                                   .all()
    return render_template('user_activity.html', user=user, activities=activities)


@app.route('/recommendations')
@login_required
def recommendations_view():
    user_id = session.get('user_id')
    # user_id will exist due to @login_required, but defensive check is good practice
    if not user_id:
        flash('Please log in to see recommendations.', 'info')
        return redirect(url_for('login'))

    suggested_users = suggest_users_to_follow(user_id, limit=5)
    suggested_posts = suggest_posts_to_read(user_id, limit=5)
    suggested_groups = suggest_groups_to_join(user_id, limit=5)
    suggested_events = suggest_events_to_attend(user_id, limit=5)
    suggested_polls = suggest_polls_to_vote(user_id, limit=5)
    suggested_hashtags = suggest_hashtags(user_id, limit=5)

    return render_template('recommendations.html',
                           suggested_users=suggested_users,
                           suggested_posts=suggested_posts,
                           suggested_groups=suggested_groups,
                           suggested_events=suggested_events,
                           suggested_polls=suggested_polls,
                           suggested_hashtags=suggested_hashtags)


@app.route('/post/<int:post_id>/flag', methods=['POST'])
@login_required
def flag_post(post_id):
    post = Post.query.get_or_404(post_id)
    user_id = session.get('user_id')

    if not user_id: # Should be caught by @login_required
        flash('You must be logged in to flag content.', 'danger')
        return redirect(url_for('login'))

    if post.user_id == user_id:
        flash('You cannot flag your own post.', 'warning')
        return redirect(url_for('view_post', post_id=post_id))

    reason = request.form.get('reason')
    existing_flag = FlaggedContent.query.filter_by(
        content_type='post',
        content_id=post_id,
        flagged_by_user_id=user_id
    ).first()

    if existing_flag:
        flash('You have already flagged this post.', 'info')
    else:
        new_flag = FlaggedContent(
            content_type='post',
            content_id=post_id,
            flagged_by_user_id=user_id,
            reason=reason
        )
        db.session.add(new_flag)
        db.session.commit()
        flash('Post has been flagged for review.', 'success')
    return redirect(url_for('view_post', post_id=post_id))


@app.route('/comment/<int:comment_id>/flag', methods=['POST'])
@login_required
def flag_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    user_id = session.get('user_id')

    if not user_id: # Should be caught by @login_required
        flash('You must be logged in to flag content.', 'danger')
        return redirect(url_for('login'))

    if comment.user_id == user_id:
        flash('You cannot flag your own comment.', 'warning')
        return redirect(url_for('view_post', post_id=comment.post_id))

    reason = request.form.get('reason')
    existing_flag = FlaggedContent.query.filter_by(
        content_type='comment',
        content_id=comment_id,
        flagged_by_user_id=user_id
    ).first()

    if existing_flag:
        flash('You have already flagged this comment.', 'info')
    else:
        new_flag = FlaggedContent(
            content_type='comment',
            content_id=comment_id,
            flagged_by_user_id=user_id,
            reason=reason
        )
        db.session.add(new_flag)
        db.session.commit()
        flash('Comment has been flagged for review.', 'success')
    return redirect(url_for('view_post', post_id=comment.post_id))


@app.route('/moderation')
@login_required
@moderator_required
def moderation_dashboard():
    pending_flags_query = FlaggedContent.query.filter_by(status='pending').order_by(FlaggedContent.timestamp.asc()).all()

    processed_flags = []
    for flag in pending_flags_query:
        flag_data = {
            'id': flag.id,
            'content_type': flag.content_type,
            'content_id': flag.content_id,
            'reason': flag.reason,
            'flagged_by_user': flag.flagged_by_user, # Pass the user object
            'timestamp': flag.timestamp,
            'comment_post_id': None # Initialize
        }
        if flag.content_type == 'comment':
            comment = Comment.query.get(flag.content_id)
            if comment:
                flag_data['comment_post_id'] = comment.post_id
        processed_flags.append(flag_data)

    return render_template('moderation_dashboard.html', flagged_items=processed_flags)

@app.route('/flagged_content/<int:flag_id>/approve', methods=['POST'])
@login_required
@moderator_required
def approve_flagged_content(flag_id):
    flag = FlaggedContent.query.get_or_404(flag_id)
    if flag.status != 'pending':
        flash('This flag has already been processed.', 'warning')
        return redirect(url_for('moderation_dashboard'))

    flag.status = 'approved'
    flag.moderator_id = session['user_id']
    flag.moderator_comment = request.form.get('moderator_comment')
    flag.resolved_at = datetime.utcnow()
    db.session.commit()
    flash(f'Flag ID {flag.id} has been approved.', 'success')
    return redirect(url_for('moderation_dashboard'))

@app.route('/flagged_content/<int:flag_id>/reject', methods=['POST'])
@login_required
@moderator_required
def reject_flagged_content(flag_id):
    flag = FlaggedContent.query.get_or_404(flag_id)
    if flag.status != 'pending':
        flash('This flag has already been processed.', 'warning')
        return redirect(url_for('moderation_dashboard'))

    flag.status = 'rejected'
    flag.moderator_id = session['user_id']
    flag.moderator_comment = request.form.get('moderator_comment')
    flag.resolved_at = datetime.utcnow()
    db.session.commit()
    flash(f'Flag ID {flag.id} has been rejected.', 'success')
    return redirect(url_for('moderation_dashboard'))

@app.route('/flagged_content/<int:flag_id>/remove_content_and_reject', methods=['POST'])
@login_required
@moderator_required
def remove_content_and_reject_flag(flag_id):
    flag = FlaggedContent.query.get_or_404(flag_id)
    if flag.status != 'pending':
        flash('This flag has already been processed.', 'warning')
        return redirect(url_for('moderation_dashboard'))

    content_removed = False
    if flag.content_type == 'post':
        post_to_delete = Post.query.get(flag.content_id)
        if post_to_delete:
            # Cascading deletes for comments, likes, reviews, etc., associated with the post
            # are assumed to be handled by the database relationships (e.g., cascade="all, delete-orphan")
            db.session.delete(post_to_delete)
            content_removed = True
            flash(f'Post ID {flag.content_id} has been deleted.', 'info')
        else:
            flash(f'Post ID {flag.content_id} not found for deletion.', 'error')
    elif flag.content_type == 'comment':
        comment_to_delete = Comment.query.get(flag.content_id)
        if comment_to_delete:
            db.session.delete(comment_to_delete)
            content_removed = True
            flash(f'Comment ID {flag.content_id} has been deleted.', 'info')
        else:
            flash(f'Comment ID {flag.content_id} not found for deletion.', 'error')
    else:
        flash(f'Unsupported content type "{flag.content_type}" for removal.', 'error')

    if content_removed:
        flag.status = 'content_removed_and_rejected'
        flash_message = f'Content ({flag.content_type} ID {flag.content_id}) removed and flag rejected.'
    else:
        # If content was not removed (e.g. not found, or unsupported type), still reject the flag.
        # Or, one might choose to leave the flag as pending if content removal failed unexpectedly.
        # For this implementation, we will mark the flag as 'rejected' if content removal failed,
        # as the primary action (removal) was not completed as intended.
        # A more nuanced status like 'rejection_failed_content_not_found' could be used.
        # However, the problem asks to update flag status to 'content_removed_and_rejected' *if content is successfully deleted*.
        # If content is not successfully deleted, we should not update the flag status this way.
        # Let's adjust: only update flag status if content_removed is true. Otherwise, it's just an error.
        # The problem statement implies if content removal fails, it's an error and then redirect.
        # It doesn't explicitly say what to do with the flag status in that case.
        # Let's assume if content removal fails, the flag remains 'pending' and moderator can re-evaluate.
        return redirect(url_for('moderation_dashboard')) # Redirect after flashing error if content not removed

    flag.moderator_id = session['user_id']
    flag.moderator_comment = request.form.get('moderator_comment')
    flag.resolved_at = datetime.utcnow()
    db.session.commit()
    flash(flash_message, 'success')
    return redirect(url_for('moderation_dashboard'))
