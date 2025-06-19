import pytest
import os
import shutil
from app import app, db, User, Post, Reaction, TodoItem # Added Post, Reaction
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from io import BytesIO # For simulating file uploads

@pytest.fixture
def client():
    # Setup
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing forms easily
    # Use a consistent test database URI. Using :memory: is fine for each test run.
    # If you need data to persist across client requests within a single test function,
    # ensure the app_context is managed correctly or consider a file-based SQLite for specific tests.
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    # Ensure PROFILE_PICS_FOLDER is set for tests, app.py should handle creation
    # but good to be explicit if tests run in a slightly different context.
    # app.py now creates this folder, so direct creation here might be redundant
    # but cleanup is important.
    PROFILE_PICS_FOLDER_PATH = app.config['PROFILE_PICS_FOLDER']


    with app.app_context():
        db.create_all()

        # Create a test user for login purposes if not already existing from other tests
        # This user will be available for tests that need a logged-in user.
        user = User.query.filter_by(username="testuser").first()
        if not user:
            hashed_password = generate_password_hash("testpassword")
            test_user = User(username="testuser", password_hash=hashed_password)
            db.session.add(test_user)
            db.session.commit()

        # Ensure PROFILE_PICS_FOLDER exists before client is yielded
        if not os.path.exists(PROFILE_PICS_FOLDER_PATH):
            os.makedirs(PROFILE_PICS_FOLDER_PATH)

        test_client = app.test_client()
        yield test_client # This is where the testing happens

        # Teardown
        db.session.remove() # Ensures session is properly closed
        db.drop_all()       # Clears schema

        # Clean up created profile pictures folder and its contents
        if os.path.exists(PROFILE_PICS_FOLDER_PATH):
            shutil.rmtree(PROFILE_PICS_FOLDER_PATH)

def login_test_user(client, username="testuser", password="testpassword"):
    """Helper function to log in a test user."""
    # The client fixture already creates 'testuser'.
    # This function just performs the login action.
    return client.post('/login', data=dict(
        username=username,
        password=password
    ), follow_redirects=True)

def get_test_user_id():
    """Helper to get the test user ID within app_context."""
    user = User.query.filter_by(username="testuser").first()
    return user.id if user else None

def get_test_user_obj():
    """Helper to get the test user object within app_context."""
    return User.query.filter_by(username="testuser").first()

# Test cases will be added below
def test_todo_access_unauthorized(client):
    """Test accessing /todo without login."""
    response = client.get('/todo', follow_redirects=False) # Don't follow, check for redirect
    assert response.status_code == 302 # Should redirect
    assert '/login' in response.location # Should redirect to login

def test_create_and_view_todo(client):
    """Test creating a new To-Do item and viewing it."""
    login_test_user(client) # Log in the test user

    # Create a task
    task_content = "Buy groceries"
    due_date_val = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    priority_val = "High"

    response_create = client.post('/todo', data=dict(
        task=task_content,
        due_date=due_date_val,
        priority=priority_val
    ), follow_redirects=True)

    assert response_create.status_code == 200 # Should redirect to /todo and load it
    assert b"To-Do item added!" in response_create.data # Check flash message

    # Verify in DB
    test_user_obj = get_test_user_obj()
    todo_item = TodoItem.query.filter_by(user_id=test_user_obj.id, task=task_content).first()
    assert todo_item is not None
    assert todo_item.due_date.strftime('%Y-%m-%d') == due_date_val
    assert todo_item.priority == priority_val
    assert not todo_item.is_done

    # Verify it's visible on the /todo page
    response_view = client.get('/todo')
    assert response_view.status_code == 200
    assert task_content.encode() in response_view.data
    assert due_date_val.encode() in response_view.data
    assert priority_val.encode() in response_view.data

def test_edit_todo(client):
    """Test editing an existing To-Do item."""
    login_test_user(client)
    test_user_obj = get_test_user_obj()

    # First, create a task
    original_task_content = "Original task for editing"
    todo_item = TodoItem(task=original_task_content, user_id=test_user_obj.id, due_date=datetime.now())
    db.session.add(todo_item)
    db.session.commit()

    edited_task_content = "Edited task content"
    edited_due_date_val = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
    edited_priority_val = "Low"

    response_edit = client.post('/todo', data=dict(
        task_id=str(todo_item.id),
        task=edited_task_content,
        due_date=edited_due_date_val,
        priority=edited_priority_val
    ), follow_redirects=True)

    assert response_edit.status_code == 200
    assert b"To-Do item updated!" in response_edit.data

    # Verify in DB
    edited_item = TodoItem.query.get(todo_item.id)
    assert edited_item.task == edited_task_content
    assert edited_item.due_date.strftime('%Y-%m-%d') == edited_due_date_val
    assert edited_item.priority == edited_priority_val

def test_update_todo_status(client):
    """Test updating the status of a To-Do item."""
    login_test_user(client)
    test_user_obj = get_test_user_obj()

    todo_item = TodoItem(task="Task for status update", user_id=test_user_obj.id, is_done=False)
    db.session.add(todo_item)
    db.session.commit()

    # Mark as done
    response_done = client.post(f'/todo/update_status/{todo_item.id}', follow_redirects=True)
    assert response_done.status_code == 200
    assert b"Task status updated!" in response_done.data
    assert TodoItem.query.get(todo_item.id).is_done is True

    # Mark as undone
    response_undone = client.post(f'/todo/update_status/{todo_item.id}', follow_redirects=True)
    assert response_undone.status_code == 200
    assert b"Task status updated!" in response_undone.data
    assert TodoItem.query.get(todo_item.id).is_done is False

def test_delete_todo(client):
    """Test deleting a To-Do item."""
    login_test_user(client)
    test_user_obj = get_test_user_obj()

    todo_item = TodoItem(task="Task to be deleted", user_id=test_user_obj.id)
    db.session.add(todo_item)
    db.session.commit()
    task_id = todo_item.id

    response_delete = client.post(f'/todo/delete/{task_id}', follow_redirects=True)
    assert response_delete.status_code == 200
    assert b"To-Do item deleted!" in response_delete.data

    assert TodoItem.query.get(task_id) is None

def test_sort_todo_by_due_date(client):
    """Test sorting To-Do items by due date."""
    login_test_user(client)
    test_user_obj = get_test_user_obj()

    # Create items with different due dates
    item1 = TodoItem(task="Due Last", user_id=test_user_obj.id, due_date=datetime.now() + timedelta(days=2))
    item2 = TodoItem(task="Due First", user_id=test_user_obj.id, due_date=datetime.now() + timedelta(days=1))
    item3 = TodoItem(task="No Due Date", user_id=test_user_obj.id, due_date=None)
    db.session.add_all([item1, item2, item3])
    db.session.commit()

    # Test ASC order (nulls first by default in our app.py logic)
    response_asc = client.get('/todo?sort_by=due_date&order=asc')
    assert response_asc.status_code == 200
    response_data_asc = response_asc.data.decode()

    # Check order: No Due Date, Due First, Due Last
    pos_no_due = response_data_asc.find("No Due Date")
    pos_due_first = response_data_asc.find("Due First")
    pos_due_last = response_data_asc.find("Due Last")

    assert pos_no_due != -1 and pos_due_first != -1 and pos_due_last != -1
    assert pos_no_due < pos_due_first < pos_due_last

    # Test DESC order (nulls last by default in our app.py logic)
    response_desc = client.get('/todo?sort_by=due_date&order=desc')
    assert response_desc.status_code == 200
    response_data_desc = response_desc.data.decode()

    # Check order: Due Last, Due First, No Due Date
    pos_no_due_desc = response_data_desc.find("No Due Date")
    pos_due_first_desc = response_data_desc.find("Due First")
    pos_due_last_desc = response_data_desc.find("Due Last")

    assert pos_no_due_desc != -1 and pos_due_first_desc != -1 and pos_due_last_desc != -1
    assert pos_due_last_desc < pos_due_first_desc < pos_no_due_desc

# Add more tests, e.g., for priority sorting, status sorting if time permits
# test_sort_todo_by_priority, test_sort_todo_by_status

# test_clear_todos could also be added.
# test_other_user_cannot_modify_todo (more complex, requires setting up another user)

# Initial test of the setup
def test_client_fixture_works(client):
    assert client is not None
    response = client.get('/') # A basic route that should exist
    assert response.status_code == 200


# --- Profile Picture Tests ---

def test_render_upload_profile_picture_page_unauthorized(client):
    """Test accessing /upload_profile_picture without login."""
    response = client.get('/upload_profile_picture', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.location

def test_render_upload_profile_picture_page_authorized(client):
    """Test accessing /upload_profile_picture when logged in."""
    login_test_user(client)
    response = client.get('/upload_profile_picture')
    assert response.status_code == 200
    assert b"Upload New Profile Picture" in response.data

def test_profile_picture_upload_success(client):
    """Test successful profile picture upload."""
    login_test_user(client)
    test_user = get_test_user_obj()

    # Ensure user initially has no profile picture or a known default
    assert test_user.profile_picture is None

    data = {
        'profile_pic': (BytesIO(b"my image data"), 'test_pic.png')
    }
    response = client.post('/upload_profile_picture', data=data, content_type='multipart/form-data', follow_redirects=True)

    assert response.status_code == 200 # After redirect to profile page
    assert b"Profile picture uploaded successfully!" in response.data

    # Verify in DB
    updated_user = get_test_user_obj()
    assert updated_user.profile_picture is not None
    assert 'test_pic.png' in updated_user.profile_picture
    assert updated_user.profile_picture.startswith('/static/profile_pics/')

    # Verify file exists (check for the unique part of the filename)
    # This is a bit tricky as the filename is made unique with UUID
    profile_pic_filename = os.path.basename(updated_user.profile_picture)
    expected_file_path = os.path.join(app.config['PROFILE_PICS_FOLDER'], profile_pic_filename)
    assert os.path.exists(expected_file_path)

def test_profile_picture_upload_no_file_selected(client):
    """Test uploading with no file selected."""
    login_test_user(client)
    response = client.post('/upload_profile_picture', data={}, content_type='multipart/form-data', follow_redirects=True)

    assert response.status_code == 200 # Stays on/redirects to upload page
    assert b"No file part selected." in response.data # Or "No file selected." depending on which check hits first

def test_profile_picture_upload_empty_filename(client):
    """Test uploading with an empty filename (e.g., file input submitted but no file chosen)."""
    login_test_user(client)
    data = {
        'profile_pic': (BytesIO(b""), '') # Empty filename
    }
    response = client.post('/upload_profile_picture', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b"No file selected." in response.data


def test_profile_picture_upload_invalid_file_type(client):
    """Test uploading a file with a disallowed extension."""
    login_test_user(client)
    test_user = get_test_user_obj()
    initial_profile_pic = test_user.profile_picture # Could be None

    data = {
        'profile_pic': (BytesIO(b"this is not an image"), 'test_doc.txt')
    }
    response = client.post('/upload_profile_picture', data=data, content_type='multipart/form-data', follow_redirects=True)

    assert response.status_code == 200 # Stays on/redirects to upload page
    assert b"Invalid file type." in response.data

    # Verify DB entry hasn't changed
    updated_user = get_test_user_obj()
    assert updated_user.profile_picture == initial_profile_pic

def test_display_profile_picture_on_profile_page_with_picture(client):
    """Test profile page displays the user's uploaded picture."""
    login_test_user(client)
    test_user = get_test_user_obj()

    # Simulate an upload to set the picture
    dummy_image_data = (BytesIO(b"fake image data"), 'user_avatar.png')
    client.post('/upload_profile_picture', data={'profile_pic': dummy_image_data}, content_type='multipart/form-data')

    # Fetch the user again to get the updated profile_picture path
    test_user_updated = get_test_user_obj()
    assert test_user_updated.profile_picture is not None

    response = client.get(f'/user/{test_user_updated.username}')
    assert response.status_code == 200
    # Check for the img tag with the specific src
    expected_img_src = test_user_updated.profile_picture
    assert f'src="{expected_img_src}"' in response.data.decode()

def test_display_profile_picture_on_profile_page_no_picture(client):
    """Test profile page displays default picture if user has none."""
    login_test_user(client) # testuser by default has no picture initially
    test_user = get_test_user_obj()
    assert test_user.profile_picture is None # Pre-condition

    response = client.get(f'/user/{test_user.username}')
    assert response.status_code == 200
    # Check for the img tag with the default src
    # Assuming default.png is used as per app.py logic in user.html
    assert 'src="/static/profile_pics/default.png"' in response.data.decode()
    assert f'alt="{test_user.username}\'s Profile Picture"' not in response.data.decode() # This alt is for custom pics
    assert 'alt="Default Profile Picture"' in response.data.decode()


def test_display_profile_picture_in_navbar_with_picture(client):
    """Test navbar displays user's picture when available."""
    login_test_user(client)
    test_user = get_test_user_obj()

    # Simulate an upload
    dummy_image_data = (BytesIO(b"fake nav image"), 'nav_avatar.jpg')
    client.post('/upload_profile_picture', data={'profile_pic': dummy_image_data}, content_type='multipart/form-data')

    test_user_updated = get_test_user_obj()
    assert test_user_updated.profile_picture is not None

    response = client.get('/') # Get any page with the base template
    assert response.status_code == 200
    # This is a simplified check. A more robust test might parse HTML.
    # We are checking if the user's specific profile picture URL is in the nav.
    # This assumes the base.html includes it for current_user.
    # As of the current base.html, it does not display the picture in the navbar,
    # but it does link to the profile. If a small thumbnail were added to base.html
    # next to the username, this test would be more relevant.
    # For now, we test that "My Profile" and "Change Profile Picture" links are present.
    assert b'My Profile' in response.data
    assert b'Change Profile Picture' in response.data
    # If base.html were to include <img src="{{ current_user.profile_picture }}">
    # then we could assert test_user_updated.profile_picture.encode() in response.data


def test_display_default_picture_in_navbar_no_picture(client):
    """Test navbar uses default when user has no picture (if navbar showed one)."""
    login_test_user(client)
    test_user = get_test_user_obj()
    assert test_user.profile_picture is None # Pre-condition

    response = client.get('/')
    assert response.status_code == 200
    # Similar to above, current base.html doesn't show pic in nav.
    # If it did, and used a default, we'd check for that default path.
    # assert b'/static/profile_pics/default.png' in response.data (if nav showed default)
    # For now, checking existing relevant links:
    assert b'My Profile' in response.data
    assert b'Change Profile Picture' in response.data

# It's good practice to also test that another user cannot see/modify profile pic upload for someone else
# but that's covered by @login_required on the upload route itself.
# The user_profile page visibility is public by design.


# --- Reaction Tests ---

# Helper to create a user directly in DB (if different from 'testuser' or for specific test users)
def create_user_directly(username, password="password"):
    hashed_password = generate_password_hash(password)
    user = User(username=username, password_hash=hashed_password)
    db.session.add(user)
    db.session.commit()
    return user

# Helper to create a post directly in DB
def create_post_directly(user_id, title="Test Post for Reactions", content="Content for reaction testing"):
    post = Post(title=title, content=content, user_id=user_id)
    db.session.add(post)
    db.session.commit()
    return post

def test_reaction_add_new(client):
    """Test adding a new reaction to a post."""
    login_test_user(client, username="testuser", password="testpassword")
    user = get_test_user_obj()
    post = create_post_directly(user_id=user.id, title="Post for Adding Reaction")

    response = client.post(f'/post/{post.id}/react', data={'emoji': '👍'}, follow_redirects=True)
    assert response.status_code == 200 # Redirects to view_post
    assert b"Reaction added." in response.data # Flash message

    reaction_in_db = Reaction.query.filter_by(user_id=user.id, post_id=post.id, emoji='👍').first()
    assert reaction_in_db is not None
    assert reaction_in_db.user_id == user.id
    assert reaction_in_db.post_id == post.id
    assert reaction_in_db.emoji == '👍'

def test_reaction_change_existing(client):
    """Test changing an existing reaction on a post."""
    login_test_user(client, username="testuser", password="testpassword")
    user = get_test_user_obj()
    post = create_post_directly(user_id=user.id, title="Post for Changing Reaction")

    # Add initial reaction
    client.post(f'/post/{post.id}/react', data={'emoji': '👍'}, follow_redirects=True)

    # Change reaction
    response = client.post(f'/post/{post.id}/react', data={'emoji': '❤️'}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Reaction updated." in response.data

    reaction_in_db = Reaction.query.filter_by(user_id=user.id, post_id=post.id).first()
    assert reaction_in_db is not None
    assert reaction_in_db.emoji == '❤️'
    assert Reaction.query.filter_by(user_id=user.id, post_id=post.id).count() == 1

def test_reaction_remove_toggle_off(client):
    """Test removing a reaction by submitting the same emoji again."""
    login_test_user(client, username="testuser", password="testpassword")
    user = get_test_user_obj()
    post = create_post_directly(user_id=user.id, title="Post for Removing Reaction")

    # Add initial reaction
    client.post(f'/post/{post.id}/react', data={'emoji': '🎉'}, follow_redirects=True)

    # Remove reaction
    response = client.post(f'/post/{post.id}/react', data={'emoji': '🎉'}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Reaction removed." in response.data

    reaction_in_db = Reaction.query.filter_by(user_id=user.id, post_id=post.id).first()
    assert reaction_in_db is None

def test_reaction_counts_on_post_view(client):
    """Test that reaction counts are correctly displayed on the post view page."""
    user1 = create_user_directly("user1_react")
    user2 = create_user_directly("user2_react")
    # 'testuser' is also available from fixture. Let's use it as user3.
    user3 = get_test_user_obj() # This is 'testuser'

    post = create_post_directly(user_id=user1.id, title="Post for Reaction Counts")

    # User1 reacts with 👍
    login_test_user(client, username="user1_react", password="password")
    client.post(f'/post/{post.id}/react', data={'emoji': '👍'}, follow_redirects=True)

    # User2 reacts with 👍
    login_test_user(client, username="user2_react", password="password")
    client.post(f'/post/{post.id}/react', data={'emoji': '👍'}, follow_redirects=True)

    # User3 (testuser) reacts with ❤️
    login_test_user(client, username="testuser", password="testpassword")
    client.post(f'/post/{post.id}/react', data={'emoji': '❤️'}, follow_redirects=True)

    # User1 changes their reaction to 🎉 (original 👍 from user1 is gone)
    login_test_user(client, username="user1_react", password="password")
    client.post(f'/post/{post.id}/react', data={'emoji': '🎉'}, follow_redirects=True)

    # Expected counts: 👍 (1 from user2), ❤️ (1 from user3), 🎉 (1 from user1)
    response = client.get(f'/blog/post/{post.id}')
    assert response.status_code == 200
    response_data = response.data.decode()

    assert "👍 (1)" in response_data
    assert "❤️ (1)" in response_data
    assert "🎉 (1)" in response_data
    # Check for a non-reacted emoji to ensure it's not shown or shown as 0 (current template doesn't show 0)
    assert "😂" not in response_data # Assuming 😂 wasn't used and template doesn't list emojis with 0 count

def test_reaction_unauthenticated_attempt(client):
    """Test attempting to react without being logged in."""
    user = create_user_directly("owner_user_react") # Some user to own the post
    post = create_post_directly(user_id=user.id, title="Post for Unauth Reaction Test")

    # client is not logged in here
    response = client.post(f'/post/{post.id}/react', data={'emoji': '👍'}, follow_redirects=False) # Check redirect
    assert response.status_code == 302
    assert '/login' in response.location

    assert Reaction.query.filter_by(post_id=post.id).count() == 0

def test_reaction_to_non_existent_post(client):
    """Test reacting to a post that does not exist."""
    login_test_user(client, username="testuser", password="testpassword")

    response = client.post('/post/99999/react', data={'emoji': '👍'}, follow_redirects=False)
    assert response.status_code == 404 # Post.query.get_or_404 should trigger this

def test_reaction_no_emoji_provided(client):
    """Test submitting a reaction without an emoji."""
    login_test_user(client, username="testuser", password="testpassword")
    user = get_test_user_obj()
    post = create_post_directly(user_id=user.id, title="Post for No Emoji Test")

    response = client.post(f'/post/{post.id}/react', data={}, follow_redirects=True) # No emoji in data
    assert response.status_code == 200 # Redirects to view_post
    assert b"No emoji provided for reaction." in response.data # Flash message
    assert Reaction.query.filter_by(post_id=post.id).count() == 0
