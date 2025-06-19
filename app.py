import os
from flask import Flask, render_template, request, session, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room
from apscheduler.schedulers.background import BackgroundScheduler
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_ # Added for inbox query
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

# Import models after db and migrate are created, but before app context is needed for them usually
# and definitely before db.init_app
from models import User, Post, Comment, Like, Review, Message, Poll, PollOption, PollVote, Event, EventRSVP, Notification, TodoItem

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
migrate.init_app(app, db)
socketio = SocketIO(app)

# Scheduler for periodic tasks
scheduler = BackgroundScheduler()
# generate_activity_summary will be defined later in this file
# For testing, use a short interval like 1 minute.
# In production, this might be 5, 10, or 15 minutes.

app.config['SECRET_KEY'] = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

app.last_activity_check_time = datetime.utcnow() # Changed to utcnow for consistency

# Ensure the upload folder exists
# Note: In-memory data structures (users, blog_posts, comments, post_likes, private_messages,
# polls, poll_votes, events, event_rsvps, blog_reviews, app.notifications and their counters)
# are removed as they will be replaced by SQLAlchemy models.
# Their definitions and initialization are deleted from this section.

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

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
    Checks for new posts, events, and polls since the last check
    and creates notifications for them.
    """
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
    # User images from comma-separated string
    user_images_str = user.uploaded_images if user.uploaded_images else ""
    user_images_list = [img.strip() for img in user_images_str.split(',') if img.strip()]
    # User images from comma-separated string
    user_images_str = user.uploaded_images if user.uploaded_images else ""
    user_images_list = [img.strip() for img in user_images_str.split(',') if img.strip()]
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

    return render_template('user.html', username=username, posts=user_posts, user_images=user_images_list, organized_events=organized_events)

@app.route('/todo', methods=['GET', 'POST'])
@login_required
def todo():
    user_id = session.get('user_id')
    if not user_id: # Should be caught by @login_required
        flash("Please log in to manage your To-Do list.", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        task_content = request.form.get('task')
        if task_content and task_content.strip():
            new_todo = TodoItem(task=task_content.strip(), user_id=user_id)
            db.session.add(new_todo)
            db.session.commit()
            flash("To-Do item added!", "success")
        else:
            flash("Task content cannot be empty.", "warning")
        return redirect(url_for('todo'))

    # GET request
    user_todos = TodoItem.query.filter_by(user_id=user_id).order_by(TodoItem.timestamp.asc()).all()
    return render_template('todo.html', todos=user_todos)

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
    session.pop('user_id', None) # Remove user_id from session
    session.pop('username', None)
    flash('You are now logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/blog/create', methods=['GET', 'POST'])
@login_required # This order was already correct
def create_post():
    #global blog_post_id_counter # No longer global like this
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        user_id = session.get('user_id')

        if not user_id:
            flash('You must be logged in to create a post.', 'danger')
            return redirect(url_for('login'))

        new_post_db = Post(title=title, content=content, user_id=user_id)
        db.session.add(new_post_db)
        db.session.commit()

        flash('Blog post created successfully!', 'success')
        return redirect(url_for('blog'))
    return render_template('create_post.html')

@app.route('/blog')
def blog():
    all_posts = Post.query.order_by(Post.timestamp.desc()).all()
    for post_item in all_posts:
        post_item.review_count = len(post_item.reviews)
        if post_item.reviews:
            post_item.average_rating = sum(r.rating for r in post_item.reviews) / len(post_item.reviews)
        else:
            post_item.average_rating = 0
        # The number of likes will be len(post_item.likes) in the template

    return render_template('blog.html', posts=all_posts)

@app.route('/blog/post/<int:post_id>')
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    # Use relationship for comments, ensure ordering if not default in model
    post_comments = Comment.query.with_parent(post).order_by(Comment.timestamp.asc()).all()

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

    return render_template('view_post.html',
                           post=post,
                           comments=post_comments,
                           user_has_liked=user_has_liked,
                           post_reviews=post_reviews,
                           average_rating=average_rating,
                           can_submit_review=can_submit_review)

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
    db.session.commit()

    # Prepare data for SocketIO emission (ensure it's serializable)
    new_comment_data = {
        "id": new_comment_db.id,
        "post_id": new_comment_db.post_id,
        "author_username": new_comment_db.author.username, # Assumes Comment.author relationship gives User
        "content": new_comment_db.content,
        "timestamp": new_comment_db.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    }
    socketio.emit('new_comment_event', new_comment_data, room=f'post_{post_id}')
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
        db.session.commit()
        flash('Post liked!', 'success')
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

with app.app_context():
    if not os.path.exists(os.path.join(app.root_path, 'site.db')):  # Check if db file exists in instance folder
        db.create_all()
        print("Database created!")
        # Try to create demo user only if DB was just created
        demo_user = User.query.filter_by(username="demo").first()
        if not demo_user:
            hashed_password = generate_password_hash("password123")
            new_demo_user = User(username="demo", password_hash=hashed_password)
            db.session.add(new_demo_user)
            db.session.commit()
            print("Demo user created.")
        else:
            print("Demo user already exists.")
    else:
        print("Database already exists.")
        # Check and create demo user if DB exists but demo user might be missing (e.g. manual DB deletion)
        demo_user = User.query.filter_by(username="demo").first()
        if not demo_user:
            hashed_password = generate_password_hash("password123")
            new_demo_user = User(username="demo", password_hash=hashed_password)
            db.session.add(new_demo_user)
            db.session.commit()
            print("Demo user created as it was missing from existing DB.")
        else:
            print("Demo user confirmed to exist in existing DB.")


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
        db.session.commit()
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
