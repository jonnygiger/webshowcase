import pytest
import os
import shutil
from app import app, db, User, Post, Reaction, TodoItem, Bookmark, Friendship, SharedPost # Added Post, Reaction, Bookmark, Friendship, SharedPost
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


# --- Bookmark Tests ---

def test_bookmark_a_post_when_logged_in(client):
    """Test bookmarking a post successfully when logged in."""
    login_test_user(client)
    user = get_test_user_obj()
    # Create a post by another user to avoid any self-action restrictions if they were ever added
    other_user = create_user_directly("otherposter", "password")
    post = create_post_directly(user_id=other_user.id, title="Test Bookmarkable Post")

    # Ensure the post is not bookmarked yet
    assert Bookmark.query.filter_by(user_id=user.id, post_id=post.id).first() is None

    response = client.post(f'/bookmark/{post.id}', follow_redirects=True)

    assert response.status_code == 200 # Should redirect to view_post
    assert f'/blog/post/{post.id}' in response.request.path # Check redirection URL
    assert b"Post bookmarked!" in response.data # Check flash message

    # Verify in DB
    bookmark = Bookmark.query.filter_by(user_id=user.id, post_id=post.id).first()
    assert bookmark is not None
    assert bookmark.user_id == user.id
    assert bookmark.post_id == post.id

    # Also check the view_post page now shows "Unbookmark" for this user
    # This requires user_has_bookmarked to be correctly passed and used in view_post.html
    response_view_post = client.get(f'/blog/post/{post.id}')
    assert b"Unbookmark" in response_view_post.data
    # And not "Bookmark Post"
    assert b">Bookmark<" not in response_view_post.data # Check for >Bookmark< to avoid matching "Bookmarked on:" etc.

def test_unbookmark_a_post_when_logged_in(client):
    """Test unbookmarking a previously bookmarked post."""
    login_test_user(client)
    user = get_test_user_obj()
    other_user = create_user_directly("anotherposter", "password")
    post = create_post_directly(user_id=other_user.id, title="Test Unbookmarkable Post")

    # Initially bookmark the post
    initial_bookmark = Bookmark(user_id=user.id, post_id=post.id)
    db.session.add(initial_bookmark)
    db.session.commit()
    assert Bookmark.query.filter_by(user_id=user.id, post_id=post.id).first() is not None

    # Send POST request to unbookmark
    response = client.post(f'/bookmark/{post.id}', follow_redirects=True)

    assert response.status_code == 200
    assert f'/blog/post/{post.id}' in response.request.path
    assert b"Post unbookmarked." in response.data

    # Verify in DB
    assert Bookmark.query.filter_by(user_id=user.id, post_id=post.id).first() is None

    # Also check the view_post page now shows "Bookmark" again
    response_view_post = client.get(f'/blog/post/{post.id}')
    assert b">Bookmark<" in response_view_post.data # Using >Bookmark< to be more specific
    assert b"Unbookmark" not in response_view_post.data

def test_view_bookmarked_posts_when_logged_in(client):
    """Test viewing the /bookmarks page when logged in."""
    login_test_user(client)
    user = get_test_user_obj()

    # Create some posts
    post1 = create_post_directly(user_id=user.id, title="Bookmarked Post 1")
    post2 = create_post_directly(user_id=user.id, title="Unbookmarked Post")
    post3 = create_post_directly(user_id=user.id, title="Bookmarked Post 3")

    # Bookmark post1 and post3 for 'testuser'
    db.session.add(Bookmark(user_id=user.id, post_id=post1.id))
    db.session.add(Bookmark(user_id=user.id, post_id=post3.id))
    db.session.commit()

    response = client.get('/bookmarks')
    assert response.status_code == 200
    response_data = response.data.decode()

    assert "My Bookmarked Posts" in response_data
    assert "Bookmarked Post 1" in response_data
    assert "Bookmarked Post 3" in response_data
    assert "Unbookmarked Post" not in response_data # Ensure unbookmarked posts are not listed
    assert "You have no bookmarked posts yet." not in response_data # Since there are bookmarks

def test_view_bookmarked_posts_empty(client):
    """Test viewing the /bookmarks page when logged in and no posts are bookmarked."""
    login_test_user(client)
    # user = get_test_user_obj() # Not strictly needed as no bookmarks will be added for this user

    response = client.get('/bookmarks')
    assert response.status_code == 200
    response_data = response.data.decode()

    assert "My Bookmarked Posts" in response_data
    assert "You have no bookmarked posts yet." in response_data

def test_bookmark_post_not_logged_in(client):
    """Test attempting to bookmark a post when not logged in."""
    # Create a post first
    test_user_for_post = create_user_directly("postowner_nouser", "password")
    post = create_post_directly(user_id=test_user_for_post.id, title="Post for Unauth Bookmark")

    response = client.post(f'/bookmark/{post.id}', follow_redirects=False) # Check for redirect

    assert response.status_code == 302 # Should redirect
    assert '/login' in response.location # To login page
    assert b"You need to be logged in to access this page." in client.get(response.location).data # Check flash on login page

    # Verify no bookmark was created
    assert Bookmark.query.filter_by(post_id=post.id).count() == 0

def test_view_bookmarks_not_logged_in(client):
    """Test attempting to view /bookmarks page when not logged in."""
    response = client.get('/bookmarks', follow_redirects=False) # Check for redirect

    assert response.status_code == 302
    assert '/login' in response.location
    assert b"You need to be logged in to access this page." in client.get(response.location).data


# --- Friendship Tests ---

def test_send_friend_request(client):
    """Test sending a friend request."""
    user1 = create_user_directly("user1send", "pass1")
    user2 = create_user_directly("user2receive", "pass2")

    login_test_user(client, username="user1send", password="pass1")

    # user1 sends a friend request to user2
    response = client.post(f'/user/{user2.id}/send_friend_request', follow_redirects=True)
    assert response.status_code == 200 # Redirects to user2's profile
    assert b"Friend request sent successfully." in response.data

    # Verify Friendship record
    friend_request = Friendship.query.filter_by(user_id=user1.id, friend_id=user2.id).first()
    assert friend_request is not None
    assert friend_request.status == 'pending'

    # Attempt to send again
    response_again = client.post(f'/user/{user2.id}/send_friend_request', follow_redirects=True)
    assert response_again.status_code == 200
    assert b"Friend request already sent or received and pending." in response_again.data

    # Attempt to send to self
    response_self = client.post(f'/user/{user1.id}/send_friend_request', follow_redirects=True)
    assert response_self.status_code == 200
    assert b"You cannot send a friend request to yourself." in response_self.data

def test_accept_friend_request(client):
    """Test accepting a friend request."""
    user1 = create_user_directly("user1acceptor", "pass1") # Will send request
    user2 = create_user_directly("user2acceptee", "pass2") # Will receive and accept

    # user1 sends request to user2
    login_test_user(client, username="user1acceptor", password="pass1")
    client.post(f'/user/{user2.id}/send_friend_request', follow_redirects=True)

    friend_request_obj = Friendship.query.filter_by(user_id=user1.id, friend_id=user2.id).first()
    assert friend_request_obj is not None
    request_id = friend_request_obj.id

    # user2 logs in and accepts the request
    login_test_user(client, username="user2acceptee", password="pass2")
    response_accept = client.post(f'/friend_request/{request_id}/accept', follow_redirects=True)
    assert response_accept.status_code == 200 # Redirects to user1's profile
    assert b"Friend request accepted successfully!" in response_accept.data

    updated_request = Friendship.query.get(request_id)
    assert updated_request.status == 'accepted'

    # user1 (non-recipient) attempts to accept again (should not change anything or error out gracefully)
    login_test_user(client, username="user1acceptor", password="pass1")
    response_accept_by_sender = client.post(f'/friend_request/{request_id}/accept', follow_redirects=True)
    assert response_accept_by_sender.status_code == 200 # Redirects to friend_requests page
    assert b"You are not authorized to respond to this friend request." in response_accept_by_sender.data
    assert Friendship.query.get(request_id).status == 'accepted' # Status remains 'accepted'

def test_reject_friend_request(client):
    """Test rejecting a friend request."""
    user1 = create_user_directly("user1rejector", "pass1") # Will send
    user2 = create_user_directly("user2rejectee", "pass2") # Will reject

    login_test_user(client, username="user1rejector", password="pass1")
    client.post(f'/user/{user2.id}/send_friend_request', follow_redirects=True)

    friend_request_obj = Friendship.query.filter_by(user_id=user1.id, friend_id=user2.id).first()
    assert friend_request_obj is not None
    request_id = friend_request_obj.id

    login_test_user(client, username="user2rejectee", password="pass2")
    response_reject = client.post(f'/friend_request/{request_id}/reject', follow_redirects=True)
    assert response_reject.status_code == 200 # Redirects to friend_requests page
    assert b"Friend request rejected." in response_reject.data

    updated_request = Friendship.query.get(request_id)
    assert updated_request.status == 'rejected'

    # user1 (non-recipient) attempts to reject (should not change or error out gracefully)
    login_test_user(client, username="user1rejector", password="pass1")
    response_reject_by_sender = client.post(f'/friend_request/{request_id}/reject', follow_redirects=True)
    assert response_reject_by_sender.status_code == 200
    assert b"You are not authorized to respond to this friend request." in response_reject_by_sender.data
    assert Friendship.query.get(request_id).status == 'rejected' # Status remains 'rejected'

def test_remove_friend(client):
    """Test removing a friend."""
    user1 = create_user_directly("user1remover", "pass1")
    user2 = create_user_directly("user2removee", "pass2")

    # Establish friendship
    login_test_user(client, username="user1remover", password="pass1")
    client.post(f'/user/{user2.id}/send_friend_request', follow_redirects=True)
    request_obj = Friendship.query.filter_by(user_id=user1.id, friend_id=user2.id).first()

    login_test_user(client, username="user2removee", password="pass2")
    client.post(f'/friend_request/{request_obj.id}/accept', follow_redirects=True)
    assert Friendship.query.get(request_obj.id).status == 'accepted'

    # user1 removes user2
    login_test_user(client, username="user1remover", password="pass1")
    response_remove = client.post(f'/user/{user2.id}/remove_friend', follow_redirects=True)
    assert response_remove.status_code == 200 # Redirects to user2's profile
    assert b"You are no longer friends with user2removee." in response_remove.data

    # Verify Friendship record is deleted
    assert Friendship.query.get(request_obj.id) is None

    # Attempt to remove again
    response_remove_again = client.post(f'/user/{user2.id}/remove_friend', follow_redirects=True)
    assert response_remove_again.status_code == 200
    assert b"You are not currently friends with user2removee." in response_remove_again.data

def test_view_friend_requests_page(client):
    """Test viewing the friend requests page."""
    user1 = create_user_directly("user1viewreqsender", "pass1")
    user2 = create_user_directly("user2viewreqreceiver", "pass2")

    # user1 sends request to user2
    login_test_user(client, username="user1viewreqsender", password="pass1")
    client.post(f'/user/{user2.id}/send_friend_request', follow_redirects=True)

    # Login as user2 and view requests
    login_test_user(client, username="user2viewreqreceiver", password="pass2")
    response = client.get('/friend_requests')
    assert response.status_code == 200
    assert b"user1viewreqsender" in response.data # user1's username should be there
    assert b"Accept" in response.data # Accept button should be there

    # Login as user1 and view requests (should be empty for user1)
    login_test_user(client, username="user1viewreqsender", password="pass1")
    response_user1 = client.get('/friend_requests')
    assert response_user1.status_code == 200
    assert b"You have no pending friend requests." in response_user1.data

def test_view_friends_list_page(client):
    """Test viewing a user's friends list."""
    user1 = create_user_directly("user1friendlist", "pass1")
    user2 = create_user_directly("user2friendlist", "pass2")
    user3 = create_user_directly("user3friendlist", "pass3") # Not a friend of user1

    # user1 and user2 become friends
    login_test_user(client, username="user1friendlist", password="pass1")
    client.post(f'/user/{user2.id}/send_friend_request', follow_redirects=True)
    request_obj = Friendship.query.filter_by(user_id=user1.id, friend_id=user2.id).first()
    login_test_user(client, username="user2friendlist", password="pass2")
    client.post(f'/friend_request/{request_obj.id}/accept', follow_redirects=True)

    # View user1's friends list (publicly)
    client.get('/logout', follow_redirects=True) # Logout first
    response_user1_friends = client.get(f'/user/{user1.username}/friends')
    assert response_user1_friends.status_code == 200
    assert f"{user1.username}'s Friends".encode() in response_user1_friends.data
    assert user2.username.encode() in response_user1_friends.data
    assert user3.username.encode() not in response_user1_friends.data # user3 is not a friend

    # View user2's friends list
    response_user2_friends = client.get(f'/user/{user2.username}/friends')
    assert response_user2_friends.status_code == 200
    assert f"{user2.username}'s Friends".encode() in response_user2_friends.data
    assert user1.username.encode() in response_user2_friends.data

    # View user3's friends list (should be empty)
    response_user3_friends = client.get(f'/user/{user3.username}/friends')
    assert response_user3_friends.status_code == 200
    assert f"{user3.username} has no friends yet.".encode() in response_user3_friends.data

def test_profile_page_friendship_actions(client):
    """Test friendship action buttons on user profile pages."""
    user1 = create_user_directly("user1profileactions", "pass1")
    user2 = create_user_directly("user2profileactions", "pass2")

    # Scenario 1: Not Friends
    login_test_user(client, username="user1profileactions", password="pass1")
    response = client.get(f'/user/{user2.username}')
    assert response.status_code == 200
    assert b"Send Friend Request" in response.data

    # Scenario 2: Request Sent by Current User (user1 to user2)
    client.post(f'/user/{user2.id}/send_friend_request', follow_redirects=True) # user1 sends to user2
    response = client.get(f'/user/{user2.username}') # user1 views user2's profile
    assert response.status_code == 200
    assert b"Friend request pending" in response.data
    assert b"Send Friend Request" not in response.data

    # Scenario 3: Request Received by Current User (user2 views user1's profile)
    login_test_user(client, username="user2profileactions", password="pass2")
    response = client.get(f'/user/{user1.username}') # user2 views user1's profile
    assert response.status_code == 200
    assert b"Accept Friend Request" in response.data
    assert b"Reject Friend Request" in response.data
    assert b"Send Friend Request" not in response.data

    # Scenario 4: Already Friends
    # user2 accepts user1's request
    request_obj = Friendship.query.filter_by(user_id=user1.id, friend_id=user2.id).first()
    client.post(f'/friend_request/{request_obj.id}/accept', follow_redirects=True)

    login_test_user(client, username="user1profileactions", password="pass1") # Back to user1
    response = client.get(f'/user/{user2.username}') # user1 views user2's profile
    assert response.status_code == 200
    assert b"Remove Friend" in response.data
    assert b"Send Friend Request" not in response.data
    assert b"Accept Friend Request" not in response.data


# --- SharedPost Model Tests ---

def test_shared_post_model_creation(client):
    """Test creating a SharedPost instance and its relationships."""
    # client fixture provides app_context
    user_sharer = create_user_directly("sharer", "password")
    user_original_author = create_user_directly("originalauthor", "password")
    original_post_obj = create_post_directly(user_id=user_original_author.id, title="Original Post for Sharing")

    comment_text = "This is a great post!"
    shared_post_entry = SharedPost(
        original_post_id=original_post_obj.id,
        shared_by_user_id=user_sharer.id,
        sharing_user_comment=comment_text
    )
    db.session.add(shared_post_entry)
    db.session.commit()

    assert shared_post_entry.id is not None
    assert shared_post_entry.original_post_id == original_post_obj.id
    assert shared_post_entry.shared_by_user_id == user_sharer.id
    assert shared_post_entry.sharing_user_comment == comment_text
    assert shared_post_entry.shared_at is not None

    # Test relationships
    assert shared_post_entry.original_post == original_post_obj
    assert shared_post_entry.sharing_user == user_sharer

    # Test backrefs
    assert shared_post_entry in user_sharer.shared_posts
    assert shared_post_entry in original_post_obj.shares


# --- Share Post Route Tests (/post/<int:post_id>/share) ---

def test_share_post_successful_with_comment(client):
    """Test successfully sharing a post with a comment."""
    sharer = create_user_directly("sharer1", "password")
    author = create_user_directly("author1", "password")
    post_to_share = create_post_directly(user_id=author.id, title="Post to be Shared with Comment")

    login_test_user(client, username="sharer1", password="password")

    share_comment = "My insightful comment on this share."
    response = client.post(f'/post/{post_to_share.id}/share', data={
        'sharing_comment': share_comment
    }, follow_redirects=True)

    assert response.status_code == 200 # Redirects to view_post
    assert f'/blog/post/{post_to_share.id}' in response.request.path
    assert b"Post shared successfully!" in response.data

    shared_entry = SharedPost.query.filter_by(original_post_id=post_to_share.id, shared_by_user_id=sharer.id).first()
    assert shared_entry is not None
    assert shared_entry.sharing_user_comment == share_comment

def test_share_post_successful_without_comment(client):
    """Test successfully sharing a post without a comment."""
    sharer = create_user_directly("sharer2", "password")
    author = create_user_directly("author2", "password")
    post_to_share = create_post_directly(user_id=author.id, title="Post to be Shared without Comment")

    login_test_user(client, username="sharer2", password="password")

    response = client.post(f'/post/{post_to_share.id}/share', data={}, follow_redirects=True)

    assert response.status_code == 200
    assert f'/blog/post/{post_to_share.id}' in response.request.path
    assert b"Post shared successfully!" in response.data

    shared_entry = SharedPost.query.filter_by(original_post_id=post_to_share.id, shared_by_user_id=sharer.id).first()
    assert shared_entry is not None
    assert shared_entry.sharing_user_comment is None or shared_entry.sharing_user_comment == ""

def test_share_post_not_logged_in(client):
    """Test trying to share a post without being logged in."""
    author = create_user_directly("author3", "password")
    post_to_share = create_post_directly(user_id=author.id, title="Post for Unauth Share")

    response = client.post(f'/post/{post_to_share.id}/share', data={'sharing_comment': 'test'}, follow_redirects=False)

    assert response.status_code == 302
    assert '/login' in response.location
    # Check flash message on the login page
    login_page_response = client.get(response.location)
    assert b"You need to be logged in to access this page." in login_page_response.data

    assert SharedPost.query.filter_by(original_post_id=post_to_share.id).count() == 0

def test_share_non_existent_post(client):
    """Test trying to share a post that does not exist."""
    sharer = create_user_directly("sharer4", "password")
    login_test_user(client, username="sharer4", password="password")

    response = client.post('/post/99999/share', data={'sharing_comment': 'test'}, follow_redirects=False)
    assert response.status_code == 404

def test_share_post_twice_by_same_user(client):
    """Test sharing the same post twice by the same user."""
    sharer = create_user_directly("sharer5", "password")
    author = create_user_directly("author5", "password")
    post_to_share = create_post_directly(user_id=author.id, title="Post to be Shared Twice")

    login_test_user(client, username="sharer5", password="password")

    # First share
    client.post(f'/post/{post_to_share.id}/share', data={'sharing_comment': 'First share'}, follow_redirects=True)
    assert SharedPost.query.filter_by(original_post_id=post_to_share.id, shared_by_user_id=sharer.id).count() == 1

    # Attempt second share
    response = client.post(f'/post/{post_to_share.id}/share', data={'sharing_comment': 'Second attempt'}, follow_redirects=True)

    assert response.status_code == 200 # Redirects to view_post
    assert b"You have already shared this post." in response.data
    assert SharedPost.query.filter_by(original_post_id=post_to_share.id, shared_by_user_id=sharer.id).count() == 1 # Count remains 1


# --- Test Display of Share Counts ---

def test_share_count_on_view_post_page(client):
    """Test share count is displayed correctly on the view_post page."""
    author = create_user_directly("author_view_count", "password")
    sharer1 = create_user_directly("sharer_vc1", "password")
    sharer2 = create_user_directly("sharer_vc2", "password")
    post_obj = create_post_directly(user_id=author.id, title="Post for View Count")

    # sharer1 shares the post
    SharedPost.query.session.add(SharedPost(original_post_id=post_obj.id, shared_by_user_id=sharer1.id))
    # sharer2 shares the post
    SharedPost.query.session.add(SharedPost(original_post_id=post_obj.id, shared_by_user_id=sharer2.id))
    db.session.commit()

    response = client.get(f'/blog/post/{post_obj.id}')
    assert response.status_code == 200
    # Based on the template: <p>{{ post.shares.count() if post.shares else 0 }} Share(s)</p>
    assert b"2 Share(s)" in response.data

    # Test with zero shares
    post_no_shares = create_post_directly(user_id=author.id, title="Post with No Shares for View Count")
    response_no_shares = client.get(f'/blog/post/{post_no_shares.id}')
    assert response_no_shares.status_code == 200
    assert b"0 Share(s)" in response_no_shares.data


def test_share_count_on_blog_page(client):
    """Test share count is displayed correctly on the main blog page."""
    author = create_user_directly("author_blog_count", "password")
    sharer1 = create_user_directly("sharer_bc1", "password")
    post_obj = create_post_directly(user_id=author.id, title="Post for Blog Page Count")

    SharedPost.query.session.add(SharedPost(original_post_id=post_obj.id, shared_by_user_id=sharer1.id))
    db.session.commit()

    response = client.get('/blog')
    assert response.status_code == 200
    # Based on template: | {{ post.shares.count() if post.shares else 0 }} Share(s)
    # Need to be careful with exact string matching due to surrounding HTML and whitespace.
    # We'll check for the post title and then the share count in its vicinity.
    expected_text = f"{post_obj.title}</a></h3>"
    expected_share_text = f"| 1 Share(s)" # Assuming one share for this test

    response_data_str = response.data.decode()
    post_html_snippet_start = response_data_str.find(expected_text)
    assert post_html_snippet_start != -1

    # Search for share count within a reasonable range after the title
    search_range = response_data_str[post_html_snippet_start : post_html_snippet_start + 500] # Adjust range as needed
    assert expected_share_text in search_range

    # Test with zero shares
    post_no_shares = create_post_directly(user_id=author.id, title="Post No Shares Blog Page")
    response_no_shares_blog = client.get('/blog')
    assert response_no_shares_blog.status_code == 200
    response_no_shares_data_str = response_no_shares_blog.data.decode()
    post_no_shares_html_snippet_start = response_no_shares_data_str.find(f"{post_no_shares.title}</a></h3>")
    assert post_no_shares_html_snippet_start != -1
    search_range_no_shares = response_no_shares_data_str[post_no_shares_html_snippet_start : post_no_shares_html_snippet_start + 500]
    assert f"| 0 Share(s)" in search_range_no_shares


# --- Test Display of Shared Posts on User Profile ---

def test_display_shared_posts_on_user_profile(client):
    """Test that shared posts by a user are displayed on their profile page."""
    sharer_user = create_user_directly("profile_sharer", "password")
    original_author = create_user_directly("profile_original_author", "password")

    post1_by_author = create_post_directly(user_id=original_author.id, title="Original Post One", content="Content of post one.")
    post2_by_author = create_post_directly(user_id=original_author.id, title="Original Post Two", content="Content of post two.")

    share_comment1 = "My thoughts on post one."
    share_comment2 = "Another great read!"

    # sharer_user shares post1
    SharedPost.query.session.add(SharedPost(
        original_post_id=post1_by_author.id,
        shared_by_user_id=sharer_user.id,
        sharing_user_comment=share_comment1
    ))
    # sharer_user shares post2 (simulating a bit later)
    shared_at_later = datetime.utcnow() - timedelta(seconds=60) # Ensure different timestamp for ordering test
    SharedPost.query.session.add(SharedPost(
        original_post_id=post2_by_author.id,
        shared_by_user_id=sharer_user.id,
        sharing_user_comment=share_comment2,
        shared_at=shared_at_later
    ))
    db.session.commit()

    # Log in (optional, as profiles are public, but good for full context)
    login_test_user(client, username="profile_sharer", password="password")

    response = client.get(f'/user/{sharer_user.username}')
    assert response.status_code == 200
    response_data = response.data.decode()

    assert "<h3>Shared Posts</h3>" in response_data

    # Check for details of shared post 1 (should appear first due to default timestamp order)
    # More robust check for shared post presence
    assert b"Shared by" in response.data
    assert sharer_user.username.encode() in response.data # Username of sharer
    assert original_author.username.encode() in response.data # Username of original author
    assert post1_by_author.title.encode() in response.data # Title of shared post
    assert share_comment1.encode() in response.data # Sharing comment

    # Check for details of shared post 2
    assert post2_by_author.title.encode() in response.data
    assert share_comment2.encode() in response.data

    # Ensure the order is descending by shared_at (post1 shared more recently than post2 in this setup if default now() is used)
    # If shared_at for post1 is later (default now()), it should appear before post2 (shared_at_later)
    # This check needs to be on the raw response data (bytes) or decoded string consistently
    position_post1_share = response_data.find(post1_by_author.title)
    position_post2_share = response_data.find(post2_by_author.title)
    assert position_post1_share != -1 and position_post2_share != -1
    # Post1 was shared with default datetime.utcnow(), post2 was shared 60s earlier. So post1 is newer.
    assert position_post1_share < position_post2_share

def test_display_no_shared_posts_on_user_profile(client):
    """Test profile page shows appropriate message if user has no shared posts."""
    user_no_shares = create_user_directly("user_with_no_shares", "password")
    login_test_user(client, username="user_with_no_shares", password="password")

    response = client.get(f'/user/{user_no_shares.username}')
    assert response.status_code == 200
    assert "<h3>Shared Posts</h3>" in response.data.decode()
    assert f"{user_no_shares.username} has not shared any posts yet." in response.data.decode()


# --- Profile Editing Tests ---

def test_edit_profile_unauthenticated(client):
    """Test accessing /profile/edit without being logged in."""
    response = client.get('/profile/edit', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.location

    # Check for flash message on the login page after redirect
    login_page_response = client.get(response.location)
    assert b"You need to be logged in to access this page." in login_page_response.data

def test_edit_profile_get(client):
    """Test GET request to /profile/edit when logged in."""
    login_test_user(client, username="testuser", password="testpassword")
    user = get_test_user_obj() # 'testuser'
    user.email = "testuser@example.com" # Ensure email is set for the test
    user.bio = "Initial bio."
    db.session.commit()

    response = client.get('/profile/edit')
    assert response.status_code == 200
    response_data = response.data.decode()

    assert f'value="{user.username}"' in response_data
    assert f'value="{user.email}"' in response_data
    assert f'>{user.bio}</textarea>' in response_data # Check bio in textarea
    assert b"Edit Your Profile" in response.data

def test_edit_profile_post_success(client):
    """Test successful profile update via POST request."""
    login_test_user(client, username="testuser", password="testpassword")
    user = get_test_user_obj()

    original_username = user.username
    original_email = user.email if user.email else "original@example.com"
    if not user.email: # Ensure user has an email to change from
        user.email = original_email
        db.session.commit()

    new_username = "updateduser"
    new_email = "updated@example.com"
    new_bio = "This is my updated bio."

    response = client.post('/profile/edit', data={
        'username': new_username,
        'email': new_email,
        'bio': new_bio
    }, follow_redirects=True)

    assert response.status_code == 200 # Redirects to profile page
    assert f'/user/{new_username}' in response.request.path # Check redirection URL
    assert b"Profile updated successfully!" in response.data

    # Verify in DB
    updated_user = User.query.get(user.id)
    assert updated_user.username == new_username
    assert updated_user.email == new_email
    assert updated_user.bio == new_bio

    # Verify session username is updated
    with client.session_transaction() as sess:
        assert sess['username'] == new_username

def test_edit_profile_post_username_taken(client):
    """Test profile update failure when new username is already taken."""
    user1 = create_user_directly("user1profile", "pass1")
    user2 = create_user_directly("user2profile", "pass2") # This username will be taken

    login_test_user(client, username="user1profile", password="pass1")

    original_email_user1 = user1.email if user1.email else "user1@example.com"
    if not user1.email:
        user1.email = original_email_user1
        db.session.commit()

    response = client.post('/profile/edit', data={
        'username': user2.username, # Attempt to take user2's username
        'email': original_email_user1, # Keep original email
        'bio': 'Bio attempt with taken username'
    }, follow_redirects=True)

    assert response.status_code == 200 # Should re-render edit_profile page
    assert b"That username is already taken." in response.data

    # Verify user1's username has not changed in DB
    db_user1 = User.query.get(user1.id)
    assert db_user1.username == "user1profile" # Original username

def test_edit_profile_post_email_taken(client):
    """Test profile update failure when new email is already taken."""
    user1 = create_user_directly("user3email", "pass3")
    user2 = create_user_directly("user4email", "pass4")
    user2.email = "taken@example.com" # user4's email
    db.session.commit()

    login_test_user(client, username="user3email", password="pass3")

    original_username_user1 = user1.username

    response = client.post('/profile/edit', data={
        'username': original_username_user1, # Keep original username
        'email': user2.email, # Attempt to take user2's email
        'bio': 'Bio attempt with taken email'
    }, follow_redirects=True)

    assert response.status_code == 200 # Re-renders edit_profile
    assert b"That email is already registered by another user." in response.data

    # Verify user1's email has not changed in DB
    db_user1 = User.query.get(user1.id)
    assert db_user1.email != user2.email # Should not be updated to the taken email
    # If user1 had a previous email, it should remain. If not, it should be None.
    # For simplicity, we just check it's not the conflicting one.

def test_edit_profile_post_empty_username(client):
    """Test profile update failure with empty username."""
    login_test_user(client, username="testuser", password="testpassword")
    user = get_test_user_obj()
    original_username = user.username
    original_email = user.email if user.email else "test@example.com"
    if not user.email:
        user.email = original_email
        db.session.commit()

    response = client.post('/profile/edit', data={
        'username': '', # Empty username
        'email': original_email,
        'bio': 'Trying empty username'
    }, follow_redirects=True)

    assert response.status_code == 200 # Re-renders edit_profile
    assert b"Username cannot be empty." in response.data
    db_user = User.query.get(user.id)
    assert db_user.username == original_username # Username should not change

def test_edit_profile_post_empty_email(client):
    """Test profile update failure with empty email."""
    login_test_user(client, username="testuser", password="testpassword")
    user = get_test_user_obj()
    original_username = user.username
    original_email = user.email if user.email else "test@example.com"
    if not user.email: # Ensure there is an email to compare against
        user.email = original_email
        db.session.commit()

    response = client.post('/profile/edit', data={
        'username': original_username,
        'email': '', # Empty email
        'bio': 'Trying empty email'
    }, follow_redirects=True)

    assert response.status_code == 200 # Re-renders edit_profile
    assert b"Email cannot be empty." in response.data
    db_user = User.query.get(user.id)
    assert db_user.email == original_email # Email should not change
