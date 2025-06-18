import os
from flask import Flask, render_template, request, session, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
socketio = SocketIO(app)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

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

# Ensure the upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[0] != "" and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

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

    return render_template('user.html', username=username, posts=user_posts, user_images=user_images)

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

        return render_template('view_post.html', post=post, comments=post_comments, user_has_liked=user_has_liked)
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

@socketio.on('join_room')
def handle_join_room_event(data):
    app.logger.info(f"User {session.get('username', 'Anonymous')} joined room: {data['room']}")
    join_room(data['room'])

if __name__ == '__main__':
    socketio.run(app, debug=True)
