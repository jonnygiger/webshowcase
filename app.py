import os
from flask import Flask, render_template, request, session, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
socketio = SocketIO(app)

# Scheduler for periodic tasks
scheduler = BackgroundScheduler()
# generate_activity_summary will be defined later in this file
# For testing, use a short interval like 1 minute.
# In production, this might be 5, 10, or 15 minutes.

app.config['SECRET_KEY'] = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

app.last_activity_check_time = datetime.now()

# User storage
users = {
    "demo": {
        "password": generate_password_hash("password123"),
        "uploaded_images": [],
        "blog_post_ids": []
    }
}
blog_posts = []
#blog_post_id_counter = 0 # Will be app attribute
app.blog_post_id_counter = 0 # Initialize as app attribute
comments = []
app.comment_id_counter = 0
post_likes = {} # To track likes: {post_id: {user_id1, user_id2, ...}}
private_messages = []
app.private_message_id_counter = 0

# Polls data structures
polls = []  # List of poll dictionaries
poll_votes = {}  # {poll_id: {option_id: {user1, user2}}}
app.poll_id_counter = 0
app.poll_option_id_counter = 0

# Event Management data structures
events = []  # List of event dictionaries
event_rsvps = {}  # {event_id: {username: rsvp_status}}
app.event_id_counter = 0

# Blog Reviews data structure
# blog_reviews = []
# app.blog_review_id_counter = 0
# Review object structure:
# {
#     "review_id": int,
#     "post_id": int,
#     "reviewer_username": str,
#     "rating": int,  # e.g., 1-5
#     "review_text": str,
#     "timestamp": str # datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# }
blog_reviews = []
app.blog_review_id_counter = 0

# Notification data structures
app.notifications = []
app.notification_id_counter = 0
# Notification object structure:
# {
#     "id": int,
#     "message": str,  # e.g., "New blog post: 'My Great Adventure'"
#     "timestamp": str, # datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     "type": str,      # e.g., 'new_post', 'new_event', 'new_poll'
#     "related_id": int, # e.g., post_id, event_id, poll_id
#     "is_read": bool,   # Default: False
#     # "target_username": str # For user-specific notifications (future)
# }

# Ensure the upload folder exists
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
    current_check_time = datetime.now()
    new_notifications_count = 0

    # Check for new blog posts
    for post in blog_posts: # Assuming blog_posts is globally accessible or app.blog_posts
        post_time = datetime.strptime(post['timestamp'], "%Y-%m-%d %H:%M:%S")
        if post_time > app.last_activity_check_time:
            app.notification_id_counter += 1
            notification = {
                "id": app.notification_id_counter,
                "message": f"New blog post: '{post['title']}'",
                "timestamp": current_check_time.strftime("%Y-%m-%d %H:%M:%S"),
                "type": "new_post",
                "related_id": post['id'],
                "is_read": False
            }
            app.notifications.append(notification)
            new_notifications_count += 1

    # Check for new events
    for event in events: # Assuming events is globally accessible or app.events
        event_creation_time = datetime.strptime(event['created_at'], "%Y-%m-%d %H:%M:%S")
        if event_creation_time > app.last_activity_check_time:
            app.notification_id_counter += 1
            notification = {
                "id": app.notification_id_counter,
                "message": f"New event: '{event['title']}'",
                "timestamp": current_check_time.strftime("%Y-%m-%d %H:%M:%S"),
                "type": "new_event",
                "related_id": event['id'],
                "is_read": False
            }
            app.notifications.append(notification)
            new_notifications_count += 1

    # Check for new polls
    for poll in polls: # Assuming polls is globally accessible or app.polls
        poll_creation_time = datetime.strptime(poll['created_at'], "%Y-%m-%d %H:%M:%S")
        if poll_creation_time > app.last_activity_check_time:
            app.notification_id_counter += 1
            notification = {
                "id": app.notification_id_counter,
                "message": f"New poll: '{poll['question']}'",
                "timestamp": current_check_time.strftime("%Y-%m-%d %H:%M:%S"),
                "type": "new_poll",
                "related_id": poll['id'],
                "is_read": False
            }
            app.notifications.append(notification)
            new_notifications_count += 1

    app.last_activity_check_time = current_check_time
    if new_notifications_count > 0:
        print(f"Activity summary generated. {new_notifications_count} new notifications.")
    else:
        print("Activity summary generated. No new notifications.")

# Decorator for requiring login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Debug print inside the decorator to see session state
        print(f"login_required: session content before check: {dict(session)}")
        if 'logged_in' not in session:
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
    # Filter blog posts for the given username
    user_posts = [post for post in blog_posts if post['author_username'] == username]

    # Retrieve user's uploaded images
    user_images = []
    if username in users:
        user_images = users[username].get('uploaded_images', [])
        # Optionally, you could also filter posts using users[username]['blog_post_ids']
        # but the current author_username filter is likely sufficient and simpler.

    # Retrieve events organized by the user
    organized_events = [event for event in events if event['organizer_username'] == username]
    # Sort events, e.g., by creation date or event date. Let's use creation date for now.
    organized_events = sorted(organized_events, key=lambda x: x['created_at'], reverse=True)

    return render_template('user.html', username=username, posts=user_posts, user_images=user_images, organized_events=organized_events)

@app.route('/todo', methods=['GET', 'POST'])
@login_required
def todo():
    if 'todos' not in session:
        session['todos'] = []

    if request.method == 'POST':
        task = request.form['task']
        session['todos'].append(task)
        session.modified = True
        return redirect(url_for('todo'))

    return render_template('todo.html', todos=session.get('todos', []))

@app.route('/todo/clear')
@login_required
def clear_todos():
    session.pop('todos', None)
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
            # Associate image with user
            if 'username' in session and session['username'] in users:
                users[session['username']]['uploaded_images'].append(filename)
            flash('Image successfully uploaded!', 'success')
            return redirect(url_for('gallery')) # Redirect to gallery page
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

        user_data = users.get(username)
        if user_data and check_password_hash(user_data['password'], password_candidate):
            session['logged_in'] = True
            session['username'] = username
            flash('You are now logged in!', 'success')
            return redirect(url_for('hello_world')) # Or a dashboard page if you create one
        else:
            flash('Invalid login.', 'danger')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
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
        app.blog_post_id_counter += 1
        new_post = {
            "id": app.blog_post_id_counter,
            "title": title,
            "content": content,
            "author_username": session['username'],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "likes": 0  # Initialize likes for new posts
        }
        blog_posts.append(new_post)
        # Associate post ID with user
        if 'username' in session and session['username'] in users:
            users[session['username']]['blog_post_ids'].append(new_post['id'])
        flash('Blog post created successfully!', 'success')
        return redirect(url_for('blog')) # This route will be created later
    return render_template('create_post.html')

@app.route('/blog')
def blog():
    # Sort posts by timestamp, newest first (optional, but good practice)
    sorted_posts = sorted(blog_posts, key=lambda x: x['timestamp'], reverse=True)

    for post in sorted_posts:
        post_specific_reviews = [review for review in blog_reviews if review['post_id'] == post['id']]
        post['review_count'] = len(post_specific_reviews)
        if post_specific_reviews:
            post['average_rating'] = sum(r['rating'] for r in post_specific_reviews) / len(post_specific_reviews)
        else:
            post['average_rating'] = 0

    return render_template('blog.html', posts=sorted_posts)

@app.route('/blog/post/<int:post_id>')
def view_post(post_id):
    post = next((post for post in blog_posts if post['id'] == post_id), None)
    if post:
        post_comments = [comment for comment in comments if comment['post_id'] == post_id]
        # Sort comments by timestamp, oldest first
        post_comments = sorted(post_comments, key=lambda x: x['timestamp'])

        user_has_liked = False
        if 'username' in session and post['id'] in post_likes and session['username'] in post_likes[post['id']]:
            user_has_liked = True

        # Reviews
        post_reviews = [review for review in blog_reviews if review['post_id'] == post_id]
        post_reviews = sorted(post_reviews, key=lambda x: x['timestamp'], reverse=True) # Newest first

        average_rating = 0
        if post_reviews:
            average_rating = sum(r['rating'] for r in post_reviews) / len(post_reviews)

        can_submit_review = False
        if 'username' in session:
            is_author = post['author_username'] == session['username']
            has_reviewed = any(r['reviewer_username'] == session['username'] for r in post_reviews)
            if not is_author and not has_reviewed:
                can_submit_review = True

        return render_template('view_post.html',
                               post=post,
                               comments=post_comments,
                               user_has_liked=user_has_liked,
                               post_reviews=post_reviews,
                               average_rating=average_rating,
                               can_submit_review=can_submit_review)
    else:
        flash('Post not found!', 'danger')
        return redirect(url_for('blog'))

@app.route('/blog/edit/<int:post_id>', methods=['GET', 'POST'])
@login_required # This order was already correct
def edit_post(post_id):
    post = next((p for p in blog_posts if p['id'] == post_id), None)

    if post is None:
        flash('Post not found!', 'danger')
        return redirect(url_for('blog'))

    if post['author_username'] != session['username']:
        flash('You are not authorized to edit this post.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    if request.method == 'POST':
        post['title'] = request.form['title']
        post['content'] = request.form['content']
        post['last_edited'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        flash('Post updated successfully!', 'success')
        return redirect(url_for('view_post', post_id=post_id))

    return render_template('edit_post.html', post=post)

@app.route('/blog/delete/<int:post_id>', methods=['POST'])
@login_required # This order was already correct
def delete_post(post_id):
    post_to_delete = next((p for p in blog_posts if p['id'] == post_id), None)

    if post_to_delete is None:
        flash('Post not found or already deleted!', 'danger')
        return redirect(url_for('blog'))

    if post_to_delete['author_username'] != session['username']:
        flash('You are not authorized to delete this post.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    blog_posts[:] = [p for p in blog_posts if p['id'] != post_id]
    flash('Post deleted successfully!', 'success')
    return redirect(url_for('blog'))

@app.route('/blog/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    # Check if the post_id exists in blog_posts
    post_exists = any(post['id'] == post_id for post in blog_posts)
    if not post_exists:
        flash('Post not found!', 'danger')
        return redirect(url_for('blog'))

    comment_content = request.form.get('comment_content')
    if not comment_content or not comment_content.strip():
        flash('Comment content cannot be empty!', 'warning')
        return redirect(url_for('view_post', post_id=post_id))

    app.comment_id_counter += 1
    new_comment = {
        "id": app.comment_id_counter,
        "post_id": post_id,
        "author_username": session['username'],
        "content": comment_content,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    comments.append(new_comment)
    socketio.emit('new_comment_event', new_comment, room=f'post_{post_id}')
    flash('Comment added successfully!', 'success')
    return redirect(url_for('view_post', post_id=post_id))


@app.route('/blog/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    post = next((p for p in blog_posts if p['id'] == post_id), None)
    if not post:
        flash('Post not found!', 'danger')
        return redirect(url_for('blog'))

    username = session['username']

    if post_id not in post_likes or username not in post_likes[post_id]:
        post['likes'] += 1
        post_likes.setdefault(post_id, set()).add(username)
        flash('Post liked!', 'success')
    else:
        flash('You have already liked this post.', 'info')

    return redirect(url_for('view_post', post_id=post_id))

@app.route('/blog/post/<int:post_id>/unlike', methods=['POST'])
@login_required
def unlike_post(post_id):
    post = next((p for p in blog_posts if p['id'] == post_id), None)
    if not post:
        flash('Post not found!', 'danger')
        return redirect(url_for('blog'))

    username = session['username']

    if post_id in post_likes and username in post_likes[post_id]:
        post['likes'] -= 1
        post_likes[post_id].remove(username)
        if not post_likes[post_id]: # Optional: remove post_id from dict if no likes remain
            del post_likes[post_id]
        flash('Post unliked!', 'success')
    else:
        flash('You have not liked this post yet.', 'info')

    return redirect(url_for('view_post', post_id=post_id))


@app.route('/blog/post/<int:post_id>/review', methods=['POST'])
@login_required
def add_review(post_id):
    post = next((p for p in blog_posts if p['id'] == post_id), None)
    if not post:
        flash('Post not found!', 'danger')
        return redirect(url_for('blog')) # Or perhaps a more general error page or back

    # Check for self-review
    if post['author_username'] == session['username']:
        flash('You cannot review your own post.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    # Check for existing review by the same user for the same post
    existing_review = next((r for r in blog_reviews if r['post_id'] == post_id and r['reviewer_username'] == session['username']), None)
    if existing_review:
        flash('You have already reviewed this post.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    rating_str = request.form.get('rating')
    review_text = request.form.get('review_text')

    # Validate rating
    if not rating_str:
        flash('Rating is required.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))
    try:
        rating = int(rating_str)
        if not (1 <= rating <= 5):
            raise ValueError
    except ValueError:
        flash('Rating must be an integer between 1 and 5 stars.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    # Validate review text
    if not review_text or not review_text.strip():
        flash('Review text cannot be empty.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))

    # Create and store review
    app.blog_review_id_counter += 1
    new_review = {
        "review_id": app.blog_review_id_counter,
        "post_id": post_id,
        "reviewer_username": session['username'],
        "rating": rating,
        "review_text": review_text.strip(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    blog_reviews.append(new_review)
    flash('Review submitted successfully!', 'success')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username in users:
            flash('Username already exists. Please choose a different one.', 'danger')
            return render_template('register.html')
        else:
            users[username] = {
                "password": generate_password_hash(password),
                "uploaded_images": [],
                "blog_post_ids": []
            }
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/messages/send/<receiver_username>', methods=['GET', 'POST'])
@login_required
def send_message(receiver_username):
    if receiver_username not in users:
        flash('User not found.', 'danger')
        return redirect(url_for('hello_world'))  # Or perhaps an inbox page later

    if request.method == 'POST':
        content = request.form.get('content')

        if not content or not content.strip():
            flash('Message content cannot be empty.', 'warning')
            return render_template('send_message.html', receiver_username=receiver_username)

        app.private_message_id_counter += 1
        new_message = {
            "message_id": app.private_message_id_counter,
            "sender_username": session['username'],
            "receiver_username": receiver_username,
            "content": content,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_read": False
        }
        private_messages.append(new_message)
        flash('Message sent successfully!', 'success')
        # Assuming 'view_conversation' will be created, which shows messages with a user
        return redirect(url_for('view_conversation', username=receiver_username))

    # GET request
    return render_template('send_message.html', receiver_username=receiver_username)


@app.route('/messages/conversation/<username>')
@login_required
def view_conversation(username):
    if username not in users:
        flash('User not found.', 'danger')
        return redirect(url_for('hello_world')) # Or an inbox page if it exists

    current_user_username = session['username']

    relevant_messages = []
    for msg in private_messages:
        is_sender = msg['sender_username'] == current_user_username and msg['receiver_username'] == username
        is_receiver = msg['sender_username'] == username and msg['receiver_username'] == current_user_username

        if is_sender or is_receiver:
            relevant_messages.append(msg)
            if is_receiver and not msg['is_read']:
                msg['is_read'] = True # Mark as read

    # Sort messages by timestamp (oldest first)
    relevant_messages.sort(key=lambda msg: datetime.strptime(msg['timestamp'], "%Y-%m-%d %H:%M:%S"))

    return render_template('conversation.html', conversation_partner=username, messages_list=relevant_messages)


@app.route('/messages/inbox')
@login_required
def inbox():
    current_user = session['username']
    conversations = {}

    for msg in private_messages:
        other_party = None
        if msg['sender_username'] == current_user:
            other_party = msg['receiver_username']
        elif msg['receiver_username'] == current_user:
            other_party = msg['sender_username']

        if other_party:
            if other_party not in conversations:
                conversations[other_party] = {
                    'last_message_timestamp': datetime.min, # Use datetime.min for easier comparison
                    'unread_count': 0,
                    'last_message_snippet': "No messages yet.",
                    'last_message_actual_timestamp': None # Store the string form for display
                }

            msg_timestamp = datetime.strptime(msg['timestamp'], "%Y-%m-%d %H:%M:%S")

            if msg_timestamp > conversations[other_party]['last_message_timestamp']:
                conversations[other_party]['last_message_timestamp'] = msg_timestamp
                conversations[other_party]['last_message_actual_timestamp'] = msg['timestamp']
                snippet = msg['content'][:50]
                if len(msg['content']) > 50:
                    snippet += "..."
                conversations[other_party]['last_message_snippet'] = snippet

            if msg['receiver_username'] == current_user and not msg['is_read']:
                conversations[other_party]['unread_count'] += 1

    inbox_items = [{'username': key, **value} for key, value in conversations.items()]

    # Sort by the datetime object, then convert timestamp to string for template if needed or use actual_timestamp
    inbox_items.sort(key=lambda x: x['last_message_timestamp'], reverse=True)

    # Replace datetime object with string version for template if preferred
    for item in inbox_items:
        if item['last_message_actual_timestamp']: # if there were messages
             item['last_message_display_timestamp'] = item['last_message_actual_timestamp']
        else: # No messages with this user
            item['last_message_display_timestamp'] = "N/A"
        del item['last_message_timestamp'] # remove datetime object before passing to template


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

    try:
        # Create a mutable copy for sorting
        notifications_to_display = list(app.notifications)
        notifications_to_display.sort(key=lambda x: datetime.strptime(x['timestamp'], "%Y-%m-%d %H:%M:%S"), reverse=True)
    except Exception as e:
        print(f"Error sorting notifications: {e}") # Or flash a message
        notifications_to_display = [] # Default to empty list on error
        flash("Error loading notifications.", "danger")

    return render_template('notifications.html', notifications=notifications_to_display)

@socketio.on('join_room')
def handle_join_room_event(data):
    app.logger.info(f"User {session.get('username', 'Anonymous')} joined room: {data['room']}")
    join_room(data['room'])

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

        # Validate question
        if not question or not question.strip():
            flash('Poll question cannot be empty.', 'danger')
            return render_template('create_poll.html')

        # Filter out empty option strings and validate
        valid_options_texts = [opt.strip() for opt in options_texts if opt and opt.strip()]
        if len(valid_options_texts) < 2:
            flash('Please provide at least two valid options for the poll.', 'danger')
            return render_template('create_poll.html')

        app.poll_id_counter += 1
        new_poll_id = app.poll_id_counter

        new_poll = {
            "id": new_poll_id,
            "question": question.strip(),
            "author_username": session['username'],
            "options": [],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        for option_text in valid_options_texts:
            app.poll_option_id_counter += 1
            new_poll['options'].append({
                "id": app.poll_option_id_counter,
                "text": option_text,
                "votes": 0 # Initialize votes count for the option
            })

        polls.append(new_poll)
        poll_votes[new_poll_id] = {} # Initialize vote storage for this poll

        flash('Poll created successfully!', 'success')
        # Redirect to view_poll or polls_list later. For now, placeholder:
        return redirect(url_for('hello_world')) # Placeholder redirect

    # GET request
    return render_template('create_poll.html')


@app.route('/polls')
def polls_list():
    # Sort polls by creation date, newest first (optional, but good practice)
    sorted_polls = sorted(polls, key=lambda x: x['created_at'], reverse=True)
    return render_template('polls.html', polls=sorted_polls)


@app.route('/events/create', methods=['GET', 'POST'])
@login_required
def create_event():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        event_date = request.form.get('event_date')
        event_time = request.form.get('event_time')
        location = request.form.get('location')

        if not title or not title.strip():
            flash('Event title is required.', 'danger')
            return render_template('create_event.html')
        if not event_date:
            flash('Event date is required.', 'danger')
            return render_template('create_event.html')

        app.event_id_counter += 1
        new_event = {
            "id": app.event_id_counter,
            "title": title.strip(),
            "description": description.strip() if description else "",
            "date": event_date,
            "time": event_time if event_time else "",
            "location": location.strip() if location else "",
            "organizer_username": session['username'],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        events.append(new_event)
        flash('Event created successfully!', 'success')
        # Redirecting to a future 'events_list' or specific event view
        # For now, let's assume 'events_list' will be created.
        # If 'view_event' was available: return redirect(url_for('view_event', event_id=new_event['id']))
        return redirect(url_for('events_list')) # Assuming 'events_list' will exist

    # GET request
    return render_template('create_event.html')


@app.route('/poll/<int:poll_id>')
def view_poll(poll_id):
    poll = next((p for p in polls if p['id'] == poll_id), None)
    if not poll:
        flash('Poll not found!', 'danger')
        return redirect(url_for('polls_list'))

    user_has_voted = False
    user_vote = None # Option ID the user voted for
    total_votes = 0

    if 'username' in session:
        current_user = session['username']
        if poll_id in poll_votes:
            for option_id_key, voters_set in poll_votes[poll_id].items():
                if current_user in voters_set:
                    user_has_voted = True
                    user_vote = option_id_key # Store the option_id the user voted for
                    break

    # Calculate vote counts for each option and total votes
    # This needs to be done regardless of whether the current user has voted or is logged in
    for option in poll['options']:
        # poll_votes keys for options are integers
        current_option_votes = len(poll_votes.get(poll_id, {}).get(option['id'], set()))
        option['vote_count'] = current_option_votes
        total_votes += current_option_votes

    # user_vote (option_id) should be an int if found
    if user_vote is not None: # It might have been read as a string key from poll_votes if keys were mixed
         user_vote = int(user_vote)


    return render_template('view_poll.html', poll=poll, user_has_voted=user_has_voted, user_vote=user_vote, total_votes=total_votes)


@app.route('/poll/<int:poll_id>/vote', methods=['POST'])
@login_required
def vote_on_poll(poll_id):
    poll = next((p for p in polls if p['id'] == poll_id), None)
    if not poll:
        flash('Poll not found!', 'danger')
        return redirect(url_for('polls_list'))

    option_id_str = request.form.get('option_id')
    if not option_id_str:
        flash('No option selected.', 'danger')
        return redirect(url_for('view_poll', poll_id=poll_id))

    try:
        selected_option_id = int(option_id_str)
    except ValueError:
        flash('Invalid option ID.', 'danger')
        return redirect(url_for('view_poll', poll_id=poll_id))

    # Check if selected_option_id is valid for this poll
    if not any(opt['id'] == selected_option_id for opt in poll['options']):
        flash('Invalid option selected for this poll.', 'danger')
        return redirect(url_for('view_poll', poll_id=poll_id))

    current_user = session['username']

    # Ensure poll_id entry exists in poll_votes
    if poll_id not in poll_votes:
        poll_votes[poll_id] = {}

    # Check if user has already voted in this poll
    for existing_voters_set in poll_votes[poll_id].values():
        if current_user in existing_voters_set:
            flash('You have already voted on this poll.', 'warning')
            return redirect(url_for('view_poll', poll_id=poll_id))

    # Record the vote
    poll_votes[poll_id].setdefault(selected_option_id, set()).add(current_user)
    flash('Vote cast successfully!', 'success')
    return redirect(url_for('view_poll', poll_id=poll_id))


@app.route('/poll/<int:poll_id>/delete', methods=['POST'])
@login_required
def delete_poll(poll_id):
    poll_to_delete = None
    for i, poll_item in enumerate(polls):
        if poll_item['id'] == poll_id:
            poll_to_delete = poll_item
            poll_index = i
            break

    if not poll_to_delete:
        flash('Poll not found!', 'danger')
        return redirect(url_for('polls_list'))

    if poll_to_delete['author_username'] != session['username']:
        flash('You are not authorized to delete this poll.', 'danger')
        return redirect(url_for('view_poll', poll_id=poll_id))

    # Delete the poll
    polls.pop(poll_index)
    poll_votes.pop(poll_id, None) # Remove vote data for the poll

    flash('Poll deleted successfully!', 'success')
    return redirect(url_for('polls_list'))


@app.route('/events')
@login_required
def events_list():
    # Sort events by event date (upcoming first).
    # Need to handle potential errors if date string is malformed, though validation should prevent this.
    # Also, consider events without a date or with past dates.
    # For simplicity, events without a valid date might appear at the end or beginning based on error handling.

    def sort_key(event):
        try:
            # Assuming event['date'] is in "YYYY-MM-DD" format
            return datetime.strptime(event['date'], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            # For events with missing or invalid dates, place them at the end.
            # Return a date very far in the future.
            return datetime.max.date()

    # Filter out past events if desired, or sort all and let the template handle display.
    # For now, sorting all events.
    # Upcoming events first, so ascending order of dates.
    sorted_events = sorted(events, key=sort_key)

    return render_template('events.html', events=sorted_events)


@app.route('/event/<int:event_id>')
def view_event(event_id):
    event = next((e for e in events if e['id'] == event_id), None)
    if not event:
        flash('Event not found!', 'danger')
        return redirect(url_for('events_list'))

    # RSVP Information
    rsvp_counts = {"Attending": 0, "Maybe": 0, "Not Attending": 0}
    user_rsvp_status = None
    current_user_username = session.get('username')

    if event_id in event_rsvps:
        for username, status in event_rsvps[event_id].items():
            if status in rsvp_counts:
                rsvp_counts[status] += 1
            if username == current_user_username:
                user_rsvp_status = status

    # Determine if the current user is the organizer
    is_organizer = False
    if current_user_username and event['organizer_username'] == current_user_username:
        is_organizer = True

    return render_template('view_event.html',
                           event=event,
                           rsvp_counts=rsvp_counts,
                           user_rsvp_status=user_rsvp_status,
                           is_organizer=is_organizer)


@app.route('/event/<int:event_id>/rsvp', methods=['POST'])
@login_required
def rsvp_event(event_id):
    event = next((e for e in events if e['id'] == event_id), None)
    if not event:
        flash('Event not found!', 'danger')
        return redirect(url_for('events_list'))

    rsvp_status = request.form.get('rsvp_status')
    valid_statuses = ["Attending", "Maybe", "Not Attending"]
    if not rsvp_status or rsvp_status not in valid_statuses:
        flash('Invalid RSVP status submitted.', 'danger')
        return redirect(url_for('view_event', event_id=event_id))

    username = session['username']

    # Ensure the event_id key exists in event_rsvps
    if event_id not in event_rsvps:
        event_rsvps[event_id] = {}

    event_rsvps[event_id][username] = rsvp_status

    flash(f'Your RSVP ("{rsvp_status}") has been recorded!', 'success')
    return redirect(url_for('view_event', event_id=event_id))


@app.route('/event/<int:event_id>/delete', methods=['POST'])
@login_required
def delete_event(event_id):
    event_to_delete = None
    event_index = -1
    for i, e in enumerate(events):
        if e['id'] == event_id:
            event_to_delete = e
            event_index = i
            break

    if not event_to_delete:
        flash('Event not found!', 'danger')
        return redirect(url_for('events_list'))

    if session['username'] != event_to_delete['organizer_username']:
        flash('You are not authorized to delete this event.', 'danger')
        return redirect(url_for('view_event', event_id=event_id))

    # Remove the event from the list
    if event_index != -1:
        events.pop(event_index)

    # Remove RSVP data for the event
    event_rsvps.pop(event_id, None)

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
