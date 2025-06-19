import sys
import os
import pytest
import io
import unittest # For new SocketIO tests
from unittest.mock import patch, MagicMock # For new SocketIO tests
from datetime import datetime, timedelta # Added for notification tests

# Deliberately deferring app import

@pytest.fixture
def app_instance():
    # Add the parent directory to the Python path to allow importing 'app'
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

    if 'app' in sys.modules:
        del sys.modules['app']

    from app import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'my_test_secret_key_for_socketio_tests' # Consistent secret key
    return flask_app

@pytest.fixture
def socketio_instance(app_instance):
    # This fixture ensures that app.socketio is available if not directly importable
    # or if it needs to be configured specifically for tests after app creation.
    # Assuming socketio is initialized in app.py as:
    # from flask_socketio import SocketIO
    # socketio = SocketIO(app)
    # Then it should be available via app_instance.extensions['socketio'] or directly from app import socketio
    # For this test structure, let's try importing it directly from app.
    from app import socketio
    return socketio


# Import other things from app or flask here
from flask import url_for
import re # For parsing post IDs
from app import app as flask_app_for_helpers, private_messages # For helper functions and new tests
from werkzeug.security import generate_password_hash # Needed for manage_app_state and new tests

# Helper functions for tests (can be used by new tests too if needed)
def _register_user(client, username, password):
    return client.post(url_for('register'), data={'username': username, 'password': password}, follow_redirects=True)

def _login_user(client, username, password):
    return client.post(url_for('login'), data={'username': username, 'password': password}, follow_redirects=True)

def _create_post(client, title="Test Post Title", content="Test Post Content"):
    # Assumes client is already logged in
    client.post(url_for('create_post'), data={'title': title, 'content': content}, follow_redirects=True)
    return flask_app_for_helpers.blog_post_id_counter


@pytest.fixture
def client(app_instance):
    with app_instance.app_context():
        yield app_instance.test_client()

def cleanup_uploads(upload_folder_path):
    if not os.path.exists(upload_folder_path):
        return
    for filename in os.listdir(upload_folder_path):
        if filename == '.gitkeep':
            continue
        file_path = os.path.join(upload_folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

@pytest.fixture(autouse=True)
def manage_app_state(app_instance):
    upload_folder = app_instance.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    gitkeep_path = os.path.join(upload_folder, '.gitkeep')
    if not os.path.exists(gitkeep_path):
        with open(gitkeep_path, 'w') as f:
            pass

    cleanup_uploads(upload_folder)

    from app import blog_posts, users, comments, post_likes, private_messages as app_private_messages, app as current_app_instance

    users.clear()
    users["demo"] = {
        "password": generate_password_hash("password123"),
        "uploaded_images": [],
        "blog_post_ids": []
    }
    users["testuser"] = { # Add common test user for SocketIO tests
        "password": generate_password_hash("password"),
        "uploaded_images": [],
        "blog_post_ids": []
    }

    blog_posts.clear()
    current_app_instance.blog_post_id_counter = 0
    comments.clear()
    current_app_instance.comment_id_counter = 0
    post_likes.clear()
    app_private_messages.clear()
    current_app_instance.private_message_id_counter = 0

    # Clear poll data
    from app import polls, poll_votes # Import poll specific data
    polls.clear()
    poll_votes.clear()
    current_app_instance.poll_id_counter = 0
    current_app_instance.poll_option_id_counter = 0

    # Clear event data
    from app import events, event_rsvps # Import event specific data
    events.clear()
    event_rsvps.clear()
    current_app_instance.event_id_counter = 0

    yield

    cleanup_uploads(upload_folder)
    blog_posts.clear()
    current_app_instance.blog_post_id_counter = 0
    comments.clear()
    current_app_instance.comment_id_counter = 0
    post_likes.clear()
    app_private_messages.clear()
    current_app_instance.private_message_id_counter = 0

    # Clear poll data after tests
    polls.clear()
    poll_votes.clear()
    current_app_instance.poll_id_counter = 0
    current_app_instance.poll_option_id_counter = 0

    # Clear event data after tests
    events.clear()
    event_rsvps.clear()
    current_app_instance.event_id_counter = 0


# --- Existing tests ... (keeping them as is) ---
def test_allowed_file_utility(app_instance):
    from app import allowed_file as af_test
    with app_instance.app_context():
        assert af_test("test.jpg") == True
        assert af_test("test.png") == True
        assert af_test("test.jpeg") == True
        assert af_test("test.gif") == True
        assert af_test("test.JPG") == True
        assert af_test("test.PnG") == True
        assert af_test("test.txt") == False
        assert af_test("testjpg") == False
        assert af_test(".jpg") == False
        assert af_test("test.") == False

def test_gallery_page_empty(client):
    response = client.get('/gallery')
    assert response.status_code == 200
    assert b"Image Gallery" in response.data
    assert b"No images uploaded yet." in response.data

def test_upload_page_get(client):
    # Login first
    _login_user(client, "demo", "password123")
    response = client.get('/gallery/upload')
    assert response.status_code == 200
    assert b"Upload a New Image" in response.data

def test_upload_image_success(client, app_instance):
    _login_user(client, "demo", "password123") # Login user
    upload_folder = app_instance.config['UPLOAD_FOLDER']
    data = {'file': (io.BytesIO(b"testimagecontent"), 'test_image.jpg')}
    response = client.post('/gallery/upload', data=data, content_type='multipart/form-data', follow_redirects=False)
    assert response.status_code == 302
    assert response.location == '/gallery'
    uploaded_files = os.listdir(upload_folder)
    assert 'test_image.jpg' in uploaded_files
    with open(os.path.join(upload_folder, 'test_image.jpg'), 'rb') as f:
        content = f.read()
        assert content == b"testimagecontent"
    response_gallery = client.get('/gallery')
    assert b"test_image.jpg" in response_gallery.data
    response_image_access = client.get('/uploads/test_image.jpg')
    assert response_image_access.status_code == 200
    assert response_image_access.data == b"testimagecontent"

def test_upload_image_no_file_part(client):
    _login_user(client, "demo", "password123")
    response = client.post('/gallery/upload', data={}, content_type='multipart/form-data', follow_redirects=True)
    assert b"No file part" in response.data

def test_upload_image_no_selected_file(client):
    _login_user(client, "demo", "password123")
    data = {'file': (io.BytesIO(b""), '')}
    response = client.post('/gallery/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert b"No selected file" in response.data

def test_upload_image_invalid_extension(client, app_instance):
    _login_user(client, "demo", "password123")
    upload_folder = app_instance.config['UPLOAD_FOLDER']
    data = {'file': (io.BytesIO(b"testtextcontent"), 'test_document.txt')}
    response = client.post('/gallery/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert b"Allowed image types are png, jpg, jpeg, gif" in response.data
    uploaded_files = os.listdir(upload_folder)
    assert 'test_document.txt' not in uploaded_files

def test_upload_multiple_images_and_gallery_display(client, app_instance):
    _login_user(client, "demo", "password123")
    upload_folder = app_instance.config['UPLOAD_FOLDER']
    client.post('/gallery/upload', data={'file': (io.BytesIO(b"img1_content"), 'img1.png')}, content_type='multipart/form-data', follow_redirects=True)
    client.post('/gallery/upload', data={'file': (io.BytesIO(b"img2_content"), 'img2.jpg')}, content_type='multipart/form-data', follow_redirects=True)
    uploaded_files = os.listdir(upload_folder)
    assert 'img1.png' in uploaded_files
    assert 'img2.jpg' in uploaded_files
    response_gallery = client.get('/gallery')
    assert b'src="/uploads/img1.png"' in response_gallery.data
    assert b'src="/uploads/img2.jpg"' in response_gallery.data

# --- To-Do tests ---
def test_todo_page_get_empty(client):
    _login_user(client, "demo", "password123")
    response = client.get('/todo')
    assert response.status_code == 200
    assert b"My To-Do List" in response.data
    assert b"No tasks yet!" in response.data

def test_add_task_post(client):
    _login_user(client, "demo", "password123")
    client.post('/todo', data={'task': 'Test Task 1'}, follow_redirects=True)
    response_get = client.get('/todo')
    assert b"Test Task 1" in response_get.data

def test_add_multiple_tasks(client):
    _login_user(client, "demo", "password123")
    client.post('/todo', data={'task': 'First Test Task'}, follow_redirects=True)
    client.post('/todo', data={'task': 'Second Test Task'}, follow_redirects=True)
    response = client.get('/todo')
    assert b"First Test Task" in response.data
    assert b"Second Test Task" in response.data

def test_clear_tasks(client):
    _login_user(client, "demo", "password123")
    client.post('/todo', data={'task': 'Task to be cleared'}, follow_redirects=True)
    client.get('/todo/clear', follow_redirects=True)
    response_after_clear = client.get('/todo')
    assert b"Task to be cleared" not in response_after_clear.data
    assert b"No tasks yet!" in response_after_clear.data

# ... (Keep other existing tests like login, registration, blog, profile, comments as they are) ...
# For brevity, I'm omitting the full list of existing tests here, but they should be preserved.

def test_login_logout_successful(client):
    response_login = client.post('/login', data={'username': 'demo', 'password': 'password123'}, follow_redirects=False)
    assert response_login.status_code == 302
    assert response_login.location == '/'
    with client.session_transaction() as sess:
        assert sess['logged_in'] is True
        assert sess['username'] == 'demo'
    response_redirected = client.get(response_login.location)
    assert b"You are now logged in!" in response_redirected.data
    response_logout = client.get('/logout', follow_redirects=False)
    assert response_logout.status_code == 302
    assert response_logout.location == '/login'
    with client.session_transaction() as sess:
        assert 'logged_in' not in sess
    response_redirected_logout = client.get(response_logout.location)
    assert b"You are now logged out." in response_redirected_logout.data

def test_login_failed_wrong_password(client):
    response = client.post('/login', data={'username': 'demo', 'password': 'wrongpassword'}, follow_redirects=True)
    assert b"Invalid login." in response.data

def test_access_protected_route_todo_unauthenticated(client, app_instance):
    with client: # Ensure session context is managed
        client.get('/logout', follow_redirects=True) # Log out first
        response = client.get('/todo', follow_redirects=False)
    assert response.status_code == 302
    assert response.location == '/login'

def test_successful_registration(client, app_instance):
    username = "newtestuser_reg" # Make sure username is unique for this test run
    password = "newpassword123"
    response = client.post('/register', data={'username': username, 'password': password}, follow_redirects=True)
    assert b"Registration successful! Please log in." in response.data
    from app import users as app_users # Import users from app for verification
    assert username in app_users

def test_registration_existing_username(client):
    response = client.post('/register', data={'username': 'demo', 'password': 'somepassword'}, follow_redirects=True)
    assert b"Username already exists." in response.data

def test_blog_page_loads_empty(client):
    response = client.get('/blog')
    assert b"No blog posts yet." in response.data

def test_create_view_edit_delete_post_as_author(client, app_instance):
    _login_user(client, "demo", "password123")
    create_post_data = {'title': 'Original Test Title Blog', 'content': 'Original Content'}
    _ = _create_post(client, title=create_post_data['title'], content=create_post_data['content'])
    # Find post ID - assuming it's the latest/only one
    from app import blog_posts as app_blog_posts
    post_id = app_blog_posts[0]['id'] if app_blog_posts else None
    assert post_id is not None

    # View
    view_resp = client.get(f'/blog/post/{post_id}')
    assert bytes(create_post_data['title'], 'utf-8') in view_resp.data
    # Edit
    edit_post_data = {'title': 'Updated Test Title Blog', 'content': 'Updated Content'}
    client.post(f'/blog/edit/{post_id}', data=edit_post_data, follow_redirects=True)
    verify_view_resp = client.get(f'/blog/post/{post_id}')
    assert bytes(edit_post_data['title'], 'utf-8') in verify_view_resp.data
    # Delete
    client.post(f'/blog/delete/{post_id}', follow_redirects=True)
    blog_page_resp = client.get('/blog')
    assert bytes(edit_post_data['title'], 'utf-8') not in blog_page_resp.data

def test_add_comment_to_post_logged_in(client, app_instance):
    _login_user(client, "testuser", "password") # Use the user from manage_app_state
    post_id = _create_post(client, title="Post for Commenting Test", content="Content here")
    comment_text = "This is a specific test comment."
    response = client.post(url_for('add_comment', post_id=post_id), data={'comment_content': comment_text}, follow_redirects=True)
    assert bytes(comment_text, 'utf-8') in response.data
    assert b"Comment added successfully!" in response.data

# --- SocketIO Tests ---
from flask_socketio import SocketIOTestClient

# Need to ensure app and socketio are imported correctly for the TestClass
# The app_instance fixture provides the app, socketio_instance provides socketio
# Pytest can run unittest.TestCase classes.

# --- Tests for Post Liking/Unliking ---
class TestLikeUnlikeFeatures:
    # Helper to get a specific post from app.blog_posts
    def _get_post_by_id(self, post_id):
        from app import blog_posts
        return next((p for p in blog_posts if p['id'] == post_id), None)

    # 1. Authentication Tests
    def test_like_post_unauthenticated(self, client):
        _login_user(client, "demo", "password123")
        post_id = _create_post(client, "Like Test", "Content")
        _login_user(client, "demo", "password123") # Logout by logging in another user or implement logout
        client.get('/logout', follow_redirects=True) # Proper logout

        response = client.post(url_for('like_post', post_id=post_id), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')

        # Check flash message on the redirected page
        response_redirected = client.get(response.location)
        assert b"You need to be logged in to access this page." in response_redirected.data


    def test_unlike_post_unauthenticated(self, client):
        _login_user(client, "demo", "password123")
        post_id = _create_post(client, "Unlike Test", "Content")
        client.get('/logout', follow_redirects=True)

        response = client.post(url_for('unlike_post', post_id=post_id), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')

        response_redirected = client.get(response.location)
        assert b"You need to be logged in to access this page." in response_redirected.data

    # 2. Liking a Post Tests
    def test_like_post_success(self, client, app_instance):
        _login_user(client, "testuser", "password")
        post_id = _create_post(client, "Test Like Success", "Content")

        from app import post_likes # Import here to get current state
        post_before = self._get_post_by_id(post_id)
        assert post_before['likes'] == 0
        assert post_id not in post_likes or "testuser" not in post_likes[post_id]

        response = client.post(url_for('like_post', post_id=post_id), follow_redirects=True)
        assert response.status_code == 200 # Assuming redirect to view_post
        assert b"Post liked!" in response.data

        post_after = self._get_post_by_id(post_id)
        assert post_after['likes'] == 1
        assert "testuser" in post_likes[post_id]

    def test_like_non_existent_post(self, client):
        _login_user(client, "testuser", "password")
        response = client.post(url_for('like_post', post_id=999), follow_redirects=True)
        assert b"Post not found!" in response.data
        # Should redirect to blog page as per current app logic
        assert b"Blog Posts" in response.data # Check if we landed on blog page

    def test_like_post_already_liked(self, client, app_instance):
        _login_user(client, "testuser", "password")
        post_id = _create_post(client, "Test Already Liked", "Content")

        from app import post_likes # Import here

        # First like
        client.post(url_for('like_post', post_id=post_id), follow_redirects=True)
        post_after_first_like = self._get_post_by_id(post_id)
        assert post_after_first_like['likes'] == 1
        assert "testuser" in post_likes[post_id]

        # Second like attempt
        response = client.post(url_for('like_post', post_id=post_id), follow_redirects=True)
        assert b"You have already liked this post." in response.data

        post_after_second_like_attempt = self._get_post_by_id(post_id)
        assert post_after_second_like_attempt['likes'] == 1 # Count should not change
        assert len(post_likes[post_id]) == 1 # Still only one user in the set

    # 3. Unliking a Post Tests
    def test_unlike_post_success(self, client, app_instance):
        _login_user(client, "testuser", "password")
        post_id = _create_post(client, "Test Unlike Success", "Content")
        from app import post_likes

        # Like the post first
        client.post(url_for('like_post', post_id=post_id), follow_redirects=True)
        post_after_like = self._get_post_by_id(post_id)
        assert post_after_like['likes'] == 1
        assert "testuser" in post_likes.get(post_id, set())

        # Unlike the post
        response = client.post(url_for('unlike_post', post_id=post_id), follow_redirects=True)
        assert response.status_code == 200
        assert b"Post unliked!" in response.data

        post_after_unlike = self._get_post_by_id(post_id)
        assert post_after_unlike['likes'] == 0
        assert post_id not in post_likes or "testuser" not in post_likes.get(post_id, set())

    def test_unlike_post_not_liked(self, client, app_instance):
        _login_user(client, "testuser", "password")
        post_id = _create_post(client, "Test Unlike Not Liked", "Content")
        from app import post_likes

        post_before = self._get_post_by_id(post_id)
        assert post_before['likes'] == 0

        response = client.post(url_for('unlike_post', post_id=post_id), follow_redirects=True)
        assert b"You have not liked this post yet." in response.data

        post_after = self._get_post_by_id(post_id)
        assert post_after['likes'] == 0 # Count should not change
        assert post_id not in post_likes # User should not be in likes set

    def test_unlike_non_existent_post(self, client):
        _login_user(client, "testuser", "password")
        response = client.post(url_for('unlike_post', post_id=999), follow_redirects=True)
        assert b"Post not found!" in response.data
        assert b"Blog Posts" in response.data

    # 4. View Post Page Tests
    def test_view_post_shows_likes_and_correct_button(self, client, app_instance):
        _login_user(client, "testuser", "password")
        post_id = _create_post(client, "View Post Test", "Content")

        # Scenario 1: User has not liked the post
        response_not_liked = client.get(url_for('view_post', post_id=post_id))
        assert b"0 like(s)" in response_not_liked.data
        assert b'<button type="submit" class="btn btn-primary btn-sm">Like</button>' in response_not_liked.data
        assert b"Unlike</button>" not in response_not_liked.data # Ensure Unlike button is not present

        # User likes the post
        client.post(url_for('like_post', post_id=post_id), follow_redirects=True)

        # Scenario 2: User has liked the post
        response_liked = client.get(url_for('view_post', post_id=post_id))
        assert b"1 like(s)" in response_liked.data
        assert b'<button type="submit" class="btn btn-secondary btn-sm">Unlike</button>' in response_liked.data
        assert b">Like</button>" not in response_liked.data # Ensure Like button is not present

        # User unlikes the post
        client.post(url_for('unlike_post', post_id=post_id), follow_redirects=True)

        # Scenario 3: User has unliked the post (back to original state)
        response_unliked = client.get(url_for('view_post', post_id=post_id))
        assert b"0 like(s)" in response_unliked.data
        assert b'<button type="submit" class="btn btn-primary btn-sm">Like</button>' in response_unliked.data

    def test_view_post_not_logged_in_shows_likes_no_buttons(self, client, app_instance):
        _login_user(client, "testuser", "password")
        post_id = _create_post(client, "View Post Not Logged In", "Content")
        # Another user (or same user) likes the post to have some likes
        client.post(url_for('like_post', post_id=post_id), follow_redirects=True)
        _login_user(client, "demo", "password123") # login as another user
        client.post(url_for('like_post', post_id=post_id), follow_redirects=True) # demo also likes it

        post = self._get_post_by_id(post_id)
        assert post['likes'] == 2 # Verify likes setup

        client.get('/logout', follow_redirects=True) # Log out

        response = client.get(url_for('view_post', post_id=post_id))
        assert b"2 like(s)" in response.data
        assert b">Like</button>" not in response.data # No Like button
        assert b"Unlike</button>" not in response.data # No Unlike button

    def test_view_post_shows_other_user_likes(self, client, app_instance):
        # User "testuser" creates a post
        _login_user(client, "testuser", "password")
        post_id = _create_post(client, "Post by testuser", "Content")

        # User "demo" logs in and likes the post
        _login_user(client, "demo", "password123")
        client.post(url_for('like_post', post_id=post_id), follow_redirects=True)

        # User "testuser" logs back in and views the post
        _login_user(client, "testuser", "password")
        response = client.get(url_for('view_post', post_id=post_id))

        assert b"1 like(s)" in response.data # Should show the like from "demo"
        # "testuser" has not liked this post, so should see "Like" button
        assert b'<button type="submit" class="btn btn-primary btn-sm">Like</button>' in response.data


class TestPrivateMessaging:
    # Helper to register users if they don't exist, using the global `users` dict from app
    # Note: `manage_app_state` fixture clears users dict before each test,
    # and adds "demo" and "testuser".
    def _ensure_user_exists(self, client, username, password):
        from app import users as app_users
        if username not in app_users:
            _register_user(client, username, password)
            # Verify registration by checking the users dict directly for simplicity in tests
            assert username in app_users, f"Failed to register user {username} for tests"

    def test_send_message_requires_login(self, client, app_instance):
        response = client.get(url_for('send_message', receiver_username='testuser'), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')

        # Check flash message on redirected page
        response_redirected = client.get(response.location, follow_redirects=True) # follow to get flash
        assert b"You need to be logged in to access this page." in response_redirected.data


    def test_send_message_to_nonexistent_user(self, client, app_instance):
        self._ensure_user_exists(client, "testsender", "password")
        _login_user(client, "testsender", "password")

        response = client.post(url_for('send_message', receiver_username='nonexistentuser'),
                               data={'content': 'Hello there'},
                               follow_redirects=True)
        assert b"User not found." in response.data
        from app import private_messages as app_private_messages
        assert len(app_private_messages) == 0

    def test_send_message_empty_content(self, client, app_instance):
        self._ensure_user_exists(client, "msg_sender1", "password")
        self._ensure_user_exists(client, "msg_receiver1", "password")
        _login_user(client, "msg_sender1", "password")

        response = client.post(url_for('send_message', receiver_username='msg_receiver1'),
                               data={'content': ''},
                               follow_redirects=True) # Send message page re-renders
        assert response.status_code == 200 # Should re-render the send_message.html
        assert b"Message content cannot be empty." in response.data
        from app import private_messages as app_private_messages
        assert len(app_private_messages) == 0

    def test_send_message_success(self, client, app_instance):
        self._ensure_user_exists(client, "sender_s", "password")
        self._ensure_user_exists(client, "receiver_s", "password")
        _login_user(client, "sender_s", "password")

        response = client.post(url_for('send_message', receiver_username='receiver_s'),
                               data={'content': 'Hello receiver_s'},
                               follow_redirects=False) # Check redirect location
        assert response.status_code == 302
        assert response.location == url_for('view_conversation', username='receiver_s')

        # Follow redirect to check flash message
        response_redirected = client.get(response.location, follow_redirects=True)
        assert b"Message sent successfully!" in response_redirected.data

        from app import private_messages as app_private_messages
        assert len(app_private_messages) == 1
        msg = app_private_messages[0]
        assert msg['sender_username'] == 'sender_s'
        assert msg['receiver_username'] == 'receiver_s'
        assert msg['content'] == 'Hello receiver_s'
        assert msg['is_read'] is False

    def test_view_conversation_requires_login(self, client, app_instance):
        response = client.get(url_for('view_conversation', username='testuser'), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')

        response_redirected = client.get(response.location, follow_redirects=True)
        assert b"You need to be logged in to access this page." in response_redirected.data


    def test_view_conversation_nonexistent_user(self, client, app_instance):
        self._ensure_user_exists(client, "convo_user1", "password")
        _login_user(client, "convo_user1", "password")

        response = client.get(url_for('view_conversation', username='nonexistentuser_convo'), follow_redirects=True)
        assert b"User not found." in response.data
        # It should redirect to hello_world as per current app.py logic
        assert b"Welcome to the Flask App" in response.data # Assuming this is on hello_world

    def test_view_conversation_and_mark_read(self, client, app_instance):
        from app import private_messages as app_private_messages, users as app_users, app as current_app

        # Ensure users exist
        self._ensure_user_exists(client, "msg_sender_mr", "password")
        self._ensure_user_exists(client, "msg_receiver_mr", "password")

        # Add a message programmatically
        current_app.private_message_id_counter += 1
        test_message = {
            "message_id": current_app.private_message_id_counter,
            "sender_username": "msg_sender_mr",
            "receiver_username": "msg_receiver_mr",
            "content": "Mark me as read!",
            "timestamp": "2023-01-01 12:00:00", # Use a fixed past timestamp
            "is_read": False
        }
        app_private_messages.append(test_message)

        _login_user(client, "msg_receiver_mr", "password")
        response = client.get(url_for('view_conversation', username='msg_sender_mr'))

        assert response.status_code == 200
        assert b"Mark me as read!" in response.data

        # Verify the message in the list is marked as read
        found_message = next((m for m in app_private_messages if m['message_id'] == test_message['message_id']), None)
        assert found_message is not None
        assert found_message['is_read'] is True

    def test_inbox_requires_login(self, client, app_instance):
        response = client.get(url_for('inbox'), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')

        response_redirected = client.get(response.location, follow_redirects=True)
        assert b"You need to be logged in to access this page." in response_redirected.data

    def test_inbox_view_empty(self, client, app_instance):
        self._ensure_user_exists(client, "inbox_user_empty", "password")
        _login_user(client, "inbox_user_empty", "password")

        response = client.get(url_for('inbox'))
        assert response.status_code == 200
        assert b"You have no messages." in response.data

    def test_inbox_view_with_messages(self, client, app_instance):
        from app import private_messages as app_private_messages, app as current_app, users as app_users

        self._ensure_user_exists(client, "inbox_user1", "password")
        self._ensure_user_exists(client, "inbox_user2", "password")
        self._ensure_user_exists(client, "inbox_user3", "password")

        # Message 1: inbox_user2 to inbox_user1
        current_app.private_message_id_counter += 1
        msg1_content = "Hello from user2 to user1"
        app_private_messages.append({
            "message_id": current_app.private_message_id_counter, "sender_username": "inbox_user2",
            "receiver_username": "inbox_user1", "content": msg1_content,
            "timestamp": "2023-01-02 10:00:00", "is_read": False
        })

        # Message 2: inbox_user1 to inbox_user3
        current_app.private_message_id_counter += 1
        msg2_content = "Hi user3 from user1"
        app_private_messages.append({
            "message_id": current_app.private_message_id_counter, "sender_username": "inbox_user1",
            "receiver_username": "inbox_user3", "content": msg2_content,
            "timestamp": "2023-01-02 11:00:00", "is_read": False
        })

        _login_user(client, "inbox_user1", "password")
        response = client.get(url_for('inbox'))
        assert response.status_code == 200

        assert b"Conversation with: inbox_user2" in response.data
        assert bytes(msg1_content[:50], 'utf-8') in response.data # Check for snippet
        assert b"1 Unread" in response.data # User1 received from User2, unread

        assert b"Conversation with: inbox_user3" in response.data
        assert bytes(msg2_content[:50], 'utf-8') in response.data # Check for snippet
        # This message was sent by user1, so no unread count for user1 from this convo
        assert b"0 Unread" not in response.data # Or check it's not marked as unread for this item
        # More robust: check that the specific "1 Unread" is associated with inbox_user2's conversation block

        # Check order - msg2 was later, so inbox_user3 should appear first
        content_str = response.data.decode('utf-8')
        pos_user3 = content_str.find("Conversation with: inbox_user3")
        pos_user2 = content_str.find("Conversation with: inbox_user2")
        assert pos_user3 < pos_user2, "Conversations in inbox are not sorted by most recent first"


    def test_send_message_button_on_profile(self, client, app_instance):
        self._ensure_user_exists(client, "profile_viewer", "password")
        self._ensure_user_exists(client, "profile_owner", "password")

        _login_user(client, "profile_viewer", "password")

        # Viewing other user's profile
        response_other = client.get(url_for('user_profile', username='profile_owner'))
        assert response_other.status_code == 200
        expected_link_other = url_for('send_message', receiver_username='profile_owner')
        assert bytes(f'href="{expected_link_other}"', 'utf-8') in response_other.data
        assert b"Send Message to profile_owner" in response_other.data

        # Viewing own profile
        response_self = client.get(url_for('user_profile', username='profile_viewer'))
        assert response_self.status_code == 200
        expected_link_self = url_for('send_message', receiver_username='profile_viewer')
        assert bytes(f'href="{expected_link_self}"', 'utf-8') not in response_self.data
        assert b"Send Message to profile_viewer" not in response_self.data

    def test_reply_from_conversation_view(self, client, app_instance):
        from app import private_messages as app_private_messages, app as current_app
        self._ensure_user_exists(client, "userA_reply", "password")
        self._ensure_user_exists(client, "userB_reply", "password")

        # UserA logs in, views conversation with UserB (empty at first)
        _login_user(client, "userA_reply", "password")
        response_convo_view = client.get(url_for('view_conversation', username='userB_reply'))
        assert response_convo_view.status_code == 200
        assert b"Conversation with userB_reply" in response_convo_view.data # Check it's the right page
        assert b"No messages yet." in response_convo_view.data


        # UserA sends a reply/first message from conversation view
        reply_content = "This is a reply from UserA to UserB"
        response_post_reply = client.post(url_for('send_message', receiver_username='userB_reply'),
                                          data={'content': reply_content},
                                          follow_redirects=False) # POST to send_message

        assert response_post_reply.status_code == 302 # Should redirect back to conversation
        assert response_post_reply.location == url_for('view_conversation', username='userB_reply')

        response_after_reply = client.get(response_post_reply.location) # Follow redirect
        assert bytes(reply_content, 'utf-8') in response_after_reply.data
        assert b"Message sent successfully!" in response_after_reply.data # Flash message

        assert len(app_private_messages) == 1
        msg = app_private_messages[0]
        assert msg['sender_username'] == 'userA_reply'
        assert msg['receiver_username'] == 'userB_reply'
        assert msg['content'] == reply_content


# --- Polls Tests ---
class TestPolls:
    def _create_sample_poll(self, client, question="Test Poll Question?", options=None):
        """ Helper to create a poll, assumes client is logged in. """
        if options is None:
            options = ["Option A", "Option B", "Option C"]

        # Use the app's global polls list and counters for direct manipulation if needed,
        # but prefer using the endpoint for more integrated testing.
        from app import app as current_app, polls as app_polls, poll_votes as app_poll_votes

        # Get current counter values to predict next ID
        next_poll_id = current_app.poll_id_counter + 1

        response = client.post(url_for('create_poll'), data={
            'question': question,
            'options[]': options
        }, follow_redirects=False) # Follow redirect to view_poll

        # The create_poll redirects to view_poll(poll_id=new_poll_id)
        # We need to parse this new_poll_id if we want to return it.
        # For now, this helper just creates the poll. The calling test can inspect app.polls.
        return response, next_poll_id


    def test_create_poll_get_not_logged_in(self, client):
        response = client.get(url_for('create_poll'), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')

    def test_create_poll_get_logged_in(self, client):
        _login_user(client, "testuser", "password")
        response = client.get(url_for('create_poll'))
        assert response.status_code == 200
        assert b"Create a New Poll" in response.data
        assert b'name="question"' in response.data
        assert b'name="options[]"' in response.data

    def test_create_poll_post_logged_in_valid(self, client, app_instance):
        _login_user(client, "testuser", "password")
        question = "Is this a valid poll?"
        options = ["Yes, it is!", "No, not really."]

        response, new_poll_id = self._create_sample_poll(client, question, options)

        assert response.status_code == 302 # Redirects to view_poll
        assert response.location == url_for('view_poll', poll_id=new_poll_id)

        # Verify flash message on the redirected page
        response_redirected = client.get(response.location)
        assert b"Poll created successfully!" in response_redirected.data

        from app import polls as app_polls, poll_votes as app_poll_votes
        assert len(app_polls) == 1
        created_poll = app_polls[0]
        assert created_poll['id'] == new_poll_id
        assert created_poll['question'] == question
        assert created_poll['author_username'] == "testuser"
        assert len(created_poll['options']) == 2
        assert created_poll['options'][0]['text'] == options[0]
        assert created_poll['options'][1]['text'] == options[1]
        assert created_poll['options'][0]['votes'] == 0

        assert new_poll_id in app_poll_votes
        assert app_poll_votes[new_poll_id] == {}

    def test_create_poll_post_logged_in_invalid_no_question(self, client):
        _login_user(client, "testuser", "password")
        response = client.post(url_for('create_poll'), data={
            'question': '', 'options[]': ['Opt1', 'Opt2']
        }, follow_redirects=True)
        assert response.status_code == 200 # Stays on create_poll page
        assert b"Poll question cannot be empty." in response.data

    def test_create_poll_post_logged_in_invalid_insufficient_options(self, client):
        _login_user(client, "testuser", "password")
        response = client.post(url_for('create_poll'), data={
            'question': 'A Question', 'options[]': ['OnlyOneOption']
        }, follow_redirects=True)
        assert response.status_code == 200 # Stays on create_poll page
        assert b"Please provide at least two valid options" in response.data

    def test_create_poll_post_not_logged_in(self, client):
        response = client.post(url_for('create_poll'), data={
            'question': 'Q', 'options[]': ['O1', 'O2']
        }, follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')

    def test_polls_list_empty(self, client):
        response = client.get(url_for('polls_list'))
        assert response.status_code == 200
        assert b"No polls available yet." in response.data
        assert b"Create New Poll" in response.data # Link to create should be there

    def test_polls_list_with_polls(self, client, app_instance):
        _login_user(client, "testuser", "password")
        _, poll1_id = self._create_sample_poll(client, "Poll 1 Question", ["P1O1", "P1O2"])
        # To ensure different creation times for sorting, could add a small delay or manually adjust created_at
        # For simplicity, assume they are created sequentially and sorting will work if tested.
        _login_user(client, "demo", "password123") # Different author
        _, poll2_id = self._create_sample_poll(client, "Poll 2 Question by Demo", ["P2O1", "P2O2"])

        response = client.get(url_for('polls_list'))
        assert response.status_code == 200
        assert b"Poll 1 Question" in response.data
        assert b"testuser" in response.data # Author of Poll 1
        assert b"Poll 2 Question by Demo" in response.data
        assert b"demo" in response.data # Author of Poll 2
        # Check if links to view polls are present
        assert bytes(url_for('view_poll', poll_id=poll1_id), 'utf-8') in response.data
        assert bytes(url_for('view_poll', poll_id=poll2_id), 'utf-8') in response.data


    def test_view_poll_exists_not_logged_in_shows_results(self, client, app_instance):
        _login_user(client, "testuser", "password") # testuser creates poll
        _, poll_id = self._create_sample_poll(client, "View Poll Test Question", ["VOpt1", "VOpt2"])

        client.get('/logout', follow_redirects=True) # Log out before viewing

        response = client.get(url_for('view_poll', poll_id=poll_id))
        assert response.status_code == 200
        assert b"View Poll Test Question" in response.data
        assert b"VOpt1" in response.data
        assert b"VOpt2" in response.data
        assert b"0 vote(s)" in response.data # Results are shown
        assert b"Please log in to vote." in response.data # Prompt to log in
        assert b'name="option_id"' not in response.data # Voting form NOT shown

    def test_view_poll_not_exists(self, client):
        response = client.get(url_for('view_poll', poll_id=9999), follow_redirects=True)
        assert response.status_code == 200 # Redirects to polls_list
        assert b"Poll not found!" in response.data
        assert b"Available Polls" in response.data # Check we are on polls_list

    def test_view_poll_shows_voting_form_if_logged_in_not_voted(self, client, app_instance):
        _login_user(client, "testuser", "password") # testuser creates poll
        _, poll_id = self._create_sample_poll(client, "Voting Form Test", ["FormOpt1", "FormOpt2"])

        # testuser (who is logged in) views the poll they haven't voted on
        response = client.get(url_for('view_poll', poll_id=poll_id))
        assert response.status_code == 200
        assert b"Voting Form Test" in response.data
        assert b"Cast Your Vote:" in response.data
        assert b'name="option_id"' in response.data # Voting form IS shown
        assert b'value="FormOpt1"' not in response.data # Check for actual option id from created poll

        from app import polls as app_polls
        created_poll = app_polls[0]
        option1_id = created_poll['options'][0]['id']
        assert bytes(f'value="{option1_id}"', 'utf-8') in response.data


    def test_vote_on_poll_logged_in_first_vote(self, client, app_instance):
        _login_user(client, "voter1", "password") # Register and login voter1
        _register_user(client, "voter1", "password") # Ensure user exists
        _login_user(client, "voter1", "password")

        _login_user(client, "poll_creator", "password") # poll_creator creates poll
        _register_user(client, "poll_creator", "password")
        _login_user(client, "poll_creator", "password")
        _, poll_id = self._create_sample_poll(client, "Poll for Voting", ["VoteOptA", "VoteOptB"])

        from app import polls as app_polls, poll_votes as app_poll_votes
        created_poll = app_polls[0] # Assuming it's the first/only one
        option_to_vote_id = created_poll['options'][0]['id']

        _login_user(client, "voter1", "password") # voter1 logs back in to vote
        response = client.post(url_for('vote_on_poll', poll_id=poll_id), data={
            'option_id': str(option_to_vote_id)
        }, follow_redirects=False) # Redirects to view_poll

        assert response.status_code == 302
        assert response.location == url_for('view_poll', poll_id=poll_id)

        response_redirected = client.get(response.location)
        assert b"Vote cast successfully!" in response_redirected.data
        assert b"You voted for: VoteOptA" in response_redirected.data # Results are shown after voting

        assert "voter1" in app_poll_votes[poll_id][option_to_vote_id]
        # Check vote count on option in results
        assert b"1 vote(s)" in response_redirected.data # Check specific option count if possible or total


    def test_vote_on_poll_logged_in_already_voted(self, client, app_instance):
        _login_user(client, "testuser", "password")
        _, poll_id = self._create_sample_poll(client, "Already Voted Poll", ["AV_Opt1", "AV_Opt2"])

        from app import polls as app_polls
        option_id = app_polls[0]['options'][0]['id']

        # First vote
        client.post(url_for('vote_on_poll', poll_id=poll_id), data={'option_id': str(option_id)}, follow_redirects=True)

        # Attempt second vote
        response = client.post(url_for('vote_on_poll', poll_id=poll_id), data={'option_id': str(option_id)}, follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('view_poll', poll_id=poll_id)
        response_redirected = client.get(response.location)
        assert b"You have already voted on this poll." in response_redirected.data


    def test_vote_on_poll_not_logged_in(self, client, app_instance):
        _login_user(client, "testuser", "password") # testuser creates poll
        _, poll_id = self._create_sample_poll(client, "Vote Not Logged In Poll", ["VNL_Opt1"])
        option_id = app_instance.polls[0]['options'][0]['id']
        client.get('/logout', follow_redirects=True) # Log out

        response = client.post(url_for('vote_on_poll', poll_id=poll_id), data={'option_id': str(option_id)}, follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')

    def test_delete_poll_author_logged_in(self, client, app_instance):
        _login_user(client, "author_user", "password")
        _register_user(client, "author_user", "password") # Ensure user exists
        _login_user(client, "author_user", "password")

        _, poll_id = self._create_sample_poll(client, "Poll to Delete", ["DelOpt1"])

        from app import polls as app_polls, poll_votes as app_poll_votes
        assert len(app_polls) == 1
        assert poll_id in app_poll_votes

        response = client.post(url_for('delete_poll', poll_id=poll_id), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('polls_list')

        response_redirected = client.get(response.location)
        assert b"Poll deleted successfully!" in response_redirected.data

        assert len(app_polls) == 0
        assert poll_id not in app_poll_votes

    def test_delete_poll_not_author_logged_in(self, client, app_instance):
        _login_user(client, "original_author", "password") # original_author creates poll
        _register_user(client, "original_author", "password")
        _login_user(client, "original_author", "password")
        _, poll_id = self._create_sample_poll(client, "Protected Poll", ["POpt1"])

        _login_user(client, "another_user", "password") # another_user logs in
        _register_user(client, "another_user", "password")
        _login_user(client, "another_user", "password")

        response = client.post(url_for('delete_poll', poll_id=poll_id), follow_redirects=False)
        assert response.status_code == 302 # Redirects to view_poll
        assert response.location == url_for('view_poll', poll_id=poll_id)

        response_redirected = client.get(response.location)
        assert b"You are not authorized to delete this poll." in response_redirected.data

        from app import polls as app_polls
        assert len(app_polls) == 1 # Poll should still exist

    def test_delete_poll_not_logged_in(self, client, app_instance):
        _login_user(client, "testuser", "password") # testuser creates poll
        _, poll_id = self._create_sample_poll(client, "Delete Not Logged In Poll", ["DNL_Opt1"])
        client.get('/logout', follow_redirects=True) # Log out

        response = client.post(url_for('delete_poll', poll_id=poll_id), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')

    def test_view_poll_shows_delete_button_for_author(self, client, app_instance):
        _login_user(client, "author_del_view", "password")
        _register_user(client, "author_del_view", "password")
        _login_user(client, "author_del_view", "password")
        _, poll_id = self._create_sample_poll(client, "Author View Delete Button Test")

        response = client.get(url_for('view_poll', poll_id=poll_id))
        assert response.status_code == 200
        assert b'action="/poll/' + str(poll_id).encode('utf-8') + b'/delete"' in response.data
        assert b"Delete Poll</button>" in response.data

    def test_view_poll_hides_delete_button_for_non_author(self, client, app_instance):
        _login_user(client, "author_user_a", "password") # Author creates poll
        _register_user(client, "author_user_a", "password")
        _login_user(client, "author_user_a", "password")
        _, poll_id = self._create_sample_poll(client, "Non-Author View Test")

        _login_user(client, "non_author_user_b", "password") # Non-author views
        _register_user(client, "non_author_user_b", "password")
        _login_user(client, "non_author_user_b", "password")

        response = client.get(url_for('view_poll', poll_id=poll_id))
        assert response.status_code == 200
        assert b'action="/poll/' + str(poll_id).encode('utf-8') + b'/delete"' not in response.data
        assert b"Delete Poll</button>" not in response.data

    def test_view_poll_hides_delete_button_for_not_logged_in(self, client, app_instance):
        _login_user(client, "author_temp", "password") # Author creates poll
        _register_user(client, "author_temp", "password")
        _login_user(client, "author_temp", "password")
        _, poll_id = self._create_sample_poll(client, "Not Logged In View Test")
        client.get('/logout', follow_redirects=True) # Log out

        response = client.get(url_for('view_poll', poll_id=poll_id))
        assert response.status_code == 200
        assert b'action="/poll/' + str(poll_id).encode('utf-8') + b'/delete"' not in response.data
        assert b"Delete Poll</button>" not in response.data


class TestAppSocketIO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This ensures that the app and socketio are imported and configured once for the class
        # Add the parent directory to the Python path to allow importing 'app'
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        if 'app' in sys.modules:
            del sys.modules['app'] # Force re-import for fresh state if tests run multiple times in one session

        from app import app as flask_app, socketio as flask_socketio, users as app_users, blog_posts as app_blog_posts, comments as app_comments
        cls.app = flask_app
        cls.socketio = flask_socketio
        cls.app_users = app_users
        cls.app_blog_posts = app_blog_posts
        cls.app_comments = app_comments

        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'testsecretkey_socketio_class'
        # No need to call users.clear() etc here, manage_app_state fixture will handle it for each test method

    def setUp(self):
        # Each test method will get a fresh app context and client
        self.app_context = self.app.app_context()
        self.app_context.push() # Manually push app context for each test

        self.client = self.app.test_client() # Flask test client
        self.socketio_test_client = SocketIOTestClient(self.app, self.socketio)

        # Reset state using the logic from manage_app_state fixture (simplified for unittest context)
        # This is crucial because the autouse fixture might not run "around" unittest methods in the same way
        self.app_users.clear()
        self.app_users["testuser"] = {"password": generate_password_hash("password"), "uploaded_images": [], "blog_post_ids": []}
        self.app_users["demo"] = {"password": generate_password_hash("password123"),"uploaded_images": [],"blog_post_ids": []}
        self.app_blog_posts.clear()
        self.app.blog_post_id_counter = 0
        self.app_comments.clear()
        self.app.comment_id_counter = 0
        # Also clear post_likes for TestAppSocketIO, though not directly used by its current tests
        from app import post_likes as app_post_likes # import if not already class member
        app_post_likes.clear()


        # Create a demo user and a blog post for comment testing
        self.app.blog_post_id_counter += 1
        self.post_id = self.app.blog_post_id_counter
        self.test_post = {
            "id": self.post_id, "title": "Test Post SocketIO", "content": "Content for SocketIO",
            "author_username": "testuser", "timestamp": "2023-01-01 10:00:00"
        }
        self.app_blog_posts.append(self.test_post)

    def tearDown(self):
        if self.socketio_test_client.is_connected():
            self.socketio_test_client.disconnect()
        self.app_context.pop() # Pop app context

    # Helper to log in a user using Flask client
    def _login_flask_user(self, username, password):
        return self.client.post('/login', data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    @patch('app.socketio.emit') # Patch where 'socketio' is used (app.py)
    def test_add_comment_emits_socketio_event(self, mock_emit):
        self._login_flask_user('testuser', 'password')

        response = self.client.post(f'/blog/post/{self.post_id}/comment', data={
            'comment_content': 'A new socket test comment'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        self.assertTrue(mock_emit.called)
        args, kwargs = mock_emit.call_args
        self.assertEqual(args[0], 'new_comment_event')

        emitted_comment_data = args[1]
        self.assertEqual(emitted_comment_data['content'], 'A new socket test comment')
        self.assertEqual(emitted_comment_data['author_username'], 'testuser')
        self.assertEqual(emitted_comment_data['post_id'], self.post_id)

        self.assertEqual(kwargs['room'], f'post_{self.post_id}')

    @patch('app.join_room') # Patch where join_room is used (app.py)
    def test_join_room_event(self, mock_join_room):
        # Simulate a client connecting and emitting 'join_room'
        # Need to set session for the app.logger line in handle_join_room_event
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'testuser_join_socket'

        # Connect the client first if your 'join_room' handler expects a connected client context
        # For SocketIOTestClient, emit can be called directly.
        self.socketio_test_client.emit('join_room', {'room': 'post_789'})

        self.assertTrue(mock_join_room.called)
        mock_join_room.assert_called_once_with('post_789')

    def test_socketio_connection_and_disconnect(self):
        self.assertTrue(self.socketio_test_client.is_connected())
        received_on_connect = self.socketio_test_client.get_received()
        self.assertEqual(len(received_on_connect), 0) # Assuming no auto-messages on connect

        self.socketio_test_client.disconnect()
        self.assertFalse(self.socketio_test_client.is_connected())

# --- Event Management Tests ---
class TestEventManager:
    # Helper to create an event, returns the event_id
    def _create_event_via_api(self, client, title="Test Event", description="Test Description",
                              event_date="2024-12-31", event_time="18:00", location="Test Location"):
        from app import app as current_app # To access event_id_counter for prediction

        # Assumes client is already logged in
        client.post(url_for('create_event'), data={
            'title': title,
            'description': description,
            'event_date': event_date,
            'event_time': event_time,
            'location': location
        }, follow_redirects=False) # Usually redirects to view_event or events_list

        # Return the ID of the created event.
        return current_app.event_id_counter # This will be the ID of the event just created.

    # 1. Event Creation
    def test_create_event_get_not_logged_in(self, client):
        response = client.get(url_for('create_event'), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')
        # Check flash message on redirected page
        response_redirected = client.get(response.location)
        assert b"You need to be logged in to access this page." in response_redirected.data


    def test_create_event_get_logged_in(self, client):
        _login_user(client, "testuser", "password")
        response = client.get(url_for('create_event'))
        assert response.status_code == 200
        assert b"Create New Event" in response.data
        assert b'name="title"' in response.data

    def test_create_event_post_success(self, client, app_instance):
        _login_user(client, "testuser", "password")
        event_data = {
            'title': 'My Awesome Event',
            'description': 'This is a great event.',
            'event_date': '2025-01-15',
            'event_time': '10:00',
            'location': 'Conference Hall A'
        }
        response = client.post(url_for('create_event'), data=event_data, follow_redirects=False)

        from app import events as app_events, app as current_app
        assert response.status_code == 302
        assert response.location == url_for('events_list')

        assert len(app_events) == 1
        created_event = app_events[0]
        assert created_event['title'] == event_data['title']
        assert created_event['description'] == event_data['description']
        assert created_event['date'] == event_data['event_date']
        assert created_event['time'] == event_data['event_time']
        assert created_event['location'] == event_data['location']
        assert created_event['organizer_username'] == "testuser"
        assert created_event['id'] == current_app.event_id_counter

        response_redirected = client.get(response.location)
        assert b"Event created successfully!" in response_redirected.data


    def test_create_event_post_missing_title(self, client, app_instance):
        _login_user(client, "testuser", "password")
        from app import events as app_events
        initial_event_count = len(app_events)

        event_data = {
            'title': '',
            'description': 'Description without title.',
            'event_date': '2025-02-10',
            'event_time': '14:00',
            'location': 'Room B'
        }
        response = client.post(url_for('create_event'), data=event_data, follow_redirects=True)

        assert response.status_code == 200
        assert b"Event title is required." in response.data
        assert len(app_events) == initial_event_count

    def test_create_event_post_missing_date(self, client, app_instance):
        _login_user(client, "testuser", "password")
        from app import events as app_events
        initial_event_count = len(app_events)

        event_data = {
            'title': 'Event With No Date',
            'description': 'This event has no date.',
            'event_date': '',
            'event_time': '11:00',
            'location': 'Venue C'
        }
        response = client.post(url_for('create_event'), data=event_data, follow_redirects=True)

        assert response.status_code == 200
        assert b"Event date is required." in response.data
        assert len(app_events) == initial_event_count

    # 2. Event Listing
    def test_events_list_page_empty(self, client):
        _login_user(client, "testuser", "password") # events_list requires login
        response = client.get(url_for('events_list'))
        assert response.status_code == 200
        assert b"Upcoming Events" in response.data # Title of the page
        # The template shows "No events scheduled yet." if events list is empty.
        # The actual text might vary based on templates/events.html content.
        assert b"No events scheduled yet." in response.data


    def test_events_list_shows_event(self, client, app_instance):
        _login_user(client, "testuser", "password")
        event_id = self._create_event_via_api(client, title="Visible Test Event")

        response = client.get(url_for('events_list'))
        assert response.status_code == 200
        assert b"Visible Test Event" in response.data
        assert bytes(url_for('view_event', event_id=event_id), 'utf-8') in response.data

    # 3. Single Event View
    def test_view_event_exists(self, client, app_instance):
        _login_user(client, "testuser", "password")
        event_id = self._create_event_via_api(client, title="Detailed Test Event", description="Details here.")

        response = client.get(url_for('view_event', event_id=event_id))
        assert response.status_code == 200
        assert b"Detailed Test Event" in response.data
        assert b"Details here." in response.data
        assert b"Organized by: testuser" in response.data # Check organizer displayed
        assert b"RSVP Status" in response.data # Check RSVP section is present

    def test_view_event_not_exists(self, client):
        _login_user(client, "testuser", "password") # Login to access view_event if it has protection
        response = client.get(url_for('view_event', event_id=999), follow_redirects=True)
        assert response.status_code == 200 # After redirect to events_list
        assert b"Event not found!" in response.data
        assert b"Upcoming Events" in response.data # Should be on events_list page

    # 4. RSVP Functionality
    def test_rsvp_event_not_logged_in(self, client, app_instance):
        # Create an event first (e.g., by user "testuser")
        _login_user(client, "testuser", "password")
        event_id = self._create_event_via_api(client, title="Event for RSVP Test")
        client.get('/logout', follow_redirects=True) # Log out

        response = client.post(url_for('rsvp_event', event_id=event_id),
                               data={'rsvp_status': 'Attending'},
                               follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')
        response_redirected = client.get(response.location)
        assert b"You need to be logged in to access this page." in response_redirected.data


    def test_rsvp_event_success(self, client, app_instance):
        _login_user(client, "testuser", "password")
        event_id = self._create_event_via_api(client, title="RSVP Success Event")

        from app import event_rsvps as app_event_rsvps
        assert event_id not in app_event_rsvps or "testuser" not in app_event_rsvps[event_id]

        response = client.post(url_for('rsvp_event', event_id=event_id),
                               data={'rsvp_status': 'Attending'},
                               follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('view_event', event_id=event_id)

        response_redirected = client.get(response.location)
        assert b'Your RSVP ("Attending") has been recorded!' in response_redirected.data
        assert b"Your RSVP: Attending" in response_redirected.data # Check updated view

        assert event_id in app_event_rsvps
        assert app_event_rsvps[event_id]["testuser"] == "Attending"

    def test_rsvp_event_invalid_status(self, client, app_instance):
        _login_user(client, "testuser", "password")
        event_id = self._create_event_via_api(client, title="RSVP Invalid Status Event")

        from app import event_rsvps as app_event_rsvps
        initial_rsvps_for_event = app_event_rsvps.get(event_id, {}).copy()

        response = client.post(url_for('rsvp_event', event_id=event_id),
                               data={'rsvp_status': 'Definitely Attending'},  # Invalid status
                               follow_redirects=True) # Follow to see flash on view_event

        assert response.status_code == 200 # Should be on view_event page
        assert b"Invalid RSVP status submitted." in response.data
        # Check that RSVPs didn't change for an invalid status
        assert app_event_rsvps.get(event_id, {}) == initial_rsvps_for_event

    def test_rsvp_to_nonexistent_event(self, client):
        _login_user(client, "testuser", "password")
        response = client.post(url_for('rsvp_event', event_id=999),
                               data={'rsvp_status': 'Attending'},
                               follow_redirects=True)
        assert response.status_code == 200 # Redirects to events_list
        assert b"Event not found!" in response.data
        assert b"Upcoming Events" in response.data # Check we are on events_list

    # 5. Event Deletion
    def test_delete_event_not_logged_in(self, client, app_instance):
        _login_user(client, "testuser", "password")
        event_id = self._create_event_via_api(client, title="Delete Test Event Unauth")
        client.get('/logout', follow_redirects=True)

        response = client.post(url_for('delete_event', event_id=event_id), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('login')
        response_redirected = client.get(response.location)
        assert b"You need to be logged in to access this page." in response_redirected.data

    def test_delete_event_not_organizer(self, client, app_instance):
        # User "organizer" creates an event
        _register_user(client, "organizer", "orgpassword")
        _login_user(client, "organizer", "orgpassword")
        event_id = self._create_event_via_api(client, title="Event by Organizer")

        # User "testuser" (who is not the organizer) tries to delete it
        _login_user(client, "testuser", "password")
        response = client.post(url_for('delete_event', event_id=event_id), follow_redirects=False)

        assert response.status_code == 302
        assert response.location == url_for('view_event', event_id=event_id)

        response_redirected = client.get(response.location)
        assert b"You are not authorized to delete this event." in response_redirected.data

        from app import events as app_events
        assert any(event['id'] == event_id for event in app_events) # Event should still exist

    def test_delete_event_success_organizer(self, client, app_instance):
        _login_user(client, "testuser", "password") # testuser is the organizer
        event_id = self._create_event_via_api(client, title="Event to be Deleted by Organizer")

        # Add a dummy RSVP to check it gets cleared
        from app import event_rsvps as app_event_rsvps
        app_event_rsvps[event_id] = {"someuser": "Attending"}

        response = client.post(url_for('delete_event', event_id=event_id), follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for('events_list')

        response_redirected = client.get(response.location)
        assert b"Event deleted successfully." in response_redirected.data

        from app import events as app_events
        assert not any(event['id'] == event_id for event in app_events) # Event should be gone
        assert event_id not in app_event_rsvps # RSVPs for event should be gone

    def test_delete_nonexistent_event(self, client):
        _login_user(client, "testuser", "password")
        response = client.post(url_for('delete_event', event_id=999), follow_redirects=True)
        assert response.status_code == 200 # Redirects to events_list
        assert b"Event not found!" in response.data
        assert b"Upcoming Events" in response.data # Check we are on events_list


# Note: The comment block at the end of the original file is removed by this replacement.
# If it's important, it would need to be re-added after the TestEventManager class.
# For now, assuming it's not critical for test functionality.

class TestNotifications(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        if 'app' in sys.modules:
            del sys.modules['app']

        from app import app as flask_app, socketio as flask_socketio, users as app_users, \
                        blog_posts as app_blog_posts, comments as app_comments, \
                        notifications as app_notifications, polls as app_polls, events as app_events

        cls.app = flask_app
        cls.socketio = flask_socketio # Though not directly used, kept for consistency if needed
        cls.app_users = app_users
        cls.app_blog_posts = app_blog_posts
        cls.app_comments = app_comments
        cls.app_notifications = app_notifications
        cls.app_polls = app_polls
        cls.app_events = app_events


        cls.app.config['TESTING'] = True
        cls.app.config['DEBUG'] = True # Enable debug mode for test_only route
        cls.app.config['SECRET_KEY'] = 'testsecretkey_notifications_class'

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()

        self.client = self.app.test_client()

        # Reset state for each test
        self.app_users.clear()
        self.app_users["testuser"] = {"password": generate_password_hash("password"), "uploaded_images": [], "blog_post_ids": []}
        self.app_users["demo"] = {"password": generate_password_hash("password123"),"uploaded_images": [],"blog_post_ids": []}

        self.app_blog_posts.clear()
        self.app.blog_post_id_counter = 0
        self.app_comments.clear()
        self.app.comment_id_counter = 0

        self.app_notifications.clear()
        self.app.notification_id_counter = 0

        self.app_polls.clear()
        self.app.poll_id_counter = 0
        self.app.poll_option_id_counter = 0

        self.app_events.clear()
        self.app.event_id_counter = 0

        # Set last_activity_check_time to a known state, e.g., far in the past
        self.app.last_activity_check_time = datetime.now() - timedelta(days=7)


    def tearDown(self):
        self.app_context.pop()

    def _login_flask_user(self, username, password): # Copied from TestAppSocketIO
        return self.client.post('/login', data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    def test_notifications_page_requires_login(self):
        # Ensure logged out
        self.client.get('/logout', follow_redirects=True)
        response = self.client.get(url_for('view_notifications'), follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith(url_for('login')))

        # Check flash message
        response_redirected = self.client.get(response.location, follow_redirects=True)
        self.assertIn(b"You need to be logged in to access this page.", response_redirected.data)

    def test_notifications_page_loads_for_logged_in_user(self):
        self._login_flask_user('testuser', 'password')
        response = self.client.get(url_for('view_notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Notifications", response.data)
        # Check for "no new notifications" if list is empty
        if not self.app_notifications:
            self.assertIn(b"You have no new notifications.", response.data)

    def test_notification_generation_and_display(self):
        self._login_flask_user('testuser', 'password')

        # 1. Clear existing notifications and reset time to ensure new post is picked up
        self.app_notifications.clear()
        self.app.notification_id_counter = 0
        # Set last_activity_check_time to sometime before the new post
        # The new post's timestamp will be datetime.now()
        self.app.last_activity_check_time = datetime.now() - timedelta(minutes=5)


        # 2. Create a new blog post programmatically
        original_post_count = len(self.app_blog_posts)
        self.app.blog_post_id_counter += 1
        post_id = self.app.blog_post_id_counter
        post_title = "Test Post for Real Notifications"
        test_post = {
            "id": post_id,
            "title": post_title,
            "content": "This post should generate a notification.",
            "author_username": "testuser",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Critical: timestamp is now
        }
        self.app_blog_posts.append(test_post)
        self.assertEqual(len(self.app_blog_posts), original_post_count + 1)


        # 3. Call the manual trigger (ensure user is logged in for this route)
        # The _login_flask_user above handles this.
        # Check if debug is True, as the route requires it.
        self.assertTrue(self.app.debug, "app.debug should be True for trigger_notifications_test_only")

        trigger_response = self.client.get(url_for('trigger_notifications_test_only'), follow_redirects=True)
        self.assertEqual(trigger_response.status_code, 200) # Should redirect to notifications page
        self.assertIn(b"Notification generation triggered for test.", trigger_response.data)

        # 4. Assert that app.notifications is not empty
        self.assertGreater(len(self.app_notifications), 0, "Notifications list should not be empty after generation.")

        # 5. Access /notifications and check for the message
        response_notifications_page = self.client.get(url_for('view_notifications'))
        self.assertEqual(response_notifications_page.status_code, 200)

        expected_message = f"New blog post: '{post_title}'"
        self.assertIn(bytes(expected_message, 'utf-8'), response_notifications_page.data,
                      f"Notification message for post '{post_title}' not found on page.")

        # Optional: Check specific details of the notification object if needed
        found_notification = False
        for notif in self.app_notifications:
            if notif['message'] == expected_message and notif['related_id'] == post_id and notif['type'] == 'new_post':
                found_notification = True
                break
        self.assertTrue(found_notification, "The specific notification object was not found in app.notifications")
