import sys
import os
import pytest
import io # Add this import

import io # Add this import
# Deliberately deferring app import

@pytest.fixture
def app_instance():
    # Add the parent directory to the Python path to allow importing 'app'
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

    # Attempt to remove app from sys.modules to force a fresh import
    if 'app' in sys.modules:
        del sys.modules['app']

    from app import app as flask_app
    flask_app.config['TESTING'] = True
    return flask_app

# Import other things from app or flask here if they are needed globally or in other fixtures
# For example, if allowed_file was needed by another fixture not using app_instance directly.
# from app import allowed_file
from flask import url_for


@pytest.fixture
def client(app_instance):
    """
    Provides a test client for the Flask application.
    Ensures that the app context is active for operations that require it.
    """
    # Now allowed_file needs to be imported where used or made available if it's used in tests directly
    # For now, assuming it's used within routes that are part of app_instance
    with app_instance.app_context():
        yield app_instance.test_client()

# Helper to clean up uploaded files after tests
def cleanup_uploads(upload_folder_path):
    if not os.path.exists(upload_folder_path):
        return
    for filename in os.listdir(upload_folder_path):
        if filename == '.gitkeep': # Don't delete .gitkeep
            continue
        file_path = os.path.join(upload_folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            # Could also remove directories if tests create them, but not for current scope
            # elif os.path.isdir(file_path):
            #     shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

@pytest.fixture(autouse=True) # auto-use to apply to all tests in this module
def manage_uploads(app_instance): # app_instance will trigger the import
    # Setup: ensure upload folder is clean before each test
    upload_folder = app_instance.config['UPLOAD_FOLDER'] # app_instance is now the flask_app
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    # Create .gitkeep if it doesn't exist, to mimic real folder structure
    # and test cleanup_uploads's ability to preserve it.
    gitkeep_path = os.path.join(upload_folder, '.gitkeep')
    if not os.path.exists(gitkeep_path):
        with open(gitkeep_path, 'w') as f:
            pass # Create empty .gitkeep

    cleanup_uploads(upload_folder) # Clean before test, preserving .gitkeep

    yield # This is where the test runs

    # Teardown: clean up upload folder after each test
    cleanup_uploads(upload_folder)


def test_allowed_file_utility(app_instance): # app_instance will trigger the import
    # Test the allowed_file utility function directly
    # To use allowed_file directly, it needs to be imported.
    # Let's import it locally for this test or make it available from app_instance if that's how it's structured.
    from app import allowed_file as af_test
    with app_instance.app_context(): # Need app context for app.config
        assert af_test("test.jpg") == True
        assert af_test("test.png") == True
        assert af_test("test.jpeg") == True
        assert af_test("test.gif") == True
        assert af_test("test.JPG") == True
        assert af_test("test.PnG") == True
        assert af_test("test.txt") == False
        assert af_test("testjpg") == False # No dot
        assert af_test(".jpg") == False # No filename part
        assert af_test("test.") == False # No extension part


def test_gallery_page_empty(client):
    response = client.get('/gallery')
    assert response.status_code == 200
    assert b"Image Gallery" in response.data
    assert b"No images uploaded yet." in response.data

def test_upload_page_get(client):
    response = client.get('/gallery/upload')
    assert response.status_code == 200
    assert b"Upload a New Image" in response.data

def test_upload_image_success(client, app_instance):
    upload_folder = app_instance.config['UPLOAD_FOLDER']

    data = {
        'file': (io.BytesIO(b"testimagecontent"), 'test_image.jpg')
    }
    response = client.post('/gallery/upload', data=data, content_type='multipart/form-data', follow_redirects=False)

    assert response.status_code == 302
    assert response.location == '/gallery'

    # Check if file exists in upload folder by listing directory
    uploaded_files = os.listdir(upload_folder)
    assert 'test_image.jpg' in uploaded_files

    # Verify file content
    with open(os.path.join(upload_folder, 'test_image.jpg'), 'rb') as f:
        content = f.read()
        assert content == b"testimagecontent"

    # Check gallery page now shows the image
    response_gallery = client.get('/gallery')
    assert response_gallery.status_code == 200
    assert b"test_image.jpg" in response_gallery.data
    assert b'src="/uploads/test_image.jpg"' in response_gallery.data
    assert b"No images uploaded yet." not in response_gallery.data

    # Check if the uploaded file can be accessed directly
    response_image_access = client.get('/uploads/test_image.jpg')
    assert response_image_access.status_code == 200
    assert response_image_access.data == b"testimagecontent"


def test_upload_image_no_file_part(client):
    response = client.post('/gallery/upload', data={}, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b"No file part" in response.data
    assert b"Upload a New Image" in response.data # Should stay on the upload page

def test_upload_image_no_selected_file(client):
    data = {
        'file': (io.BytesIO(b""), '') # Empty filename
    }
    response = client.post('/gallery/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b"No selected file" in response.data
    assert b"Upload a New Image" in response.data

def test_upload_image_invalid_extension(client, app_instance):
    upload_folder = app_instance.config['UPLOAD_FOLDER']
    data = {
        'file': (io.BytesIO(b"testtextcontent"), 'test_document.txt')
    }
    response = client.post('/gallery/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b"Allowed image types are png, jpg, jpeg, gif" in response.data
    assert b"Upload a New Image" in response.data

    uploaded_files = os.listdir(upload_folder)
    assert 'test_document.txt' not in uploaded_files
    # Ensure .gitkeep is not the only thing, or handle if it is
    if '.gitkeep' in uploaded_files:
        assert len(uploaded_files) == 1 # Only .gitkeep should be there
    else:
        assert len(uploaded_files) == 0


def test_upload_multiple_images_and_gallery_display(client, app_instance):
    upload_folder = app_instance.config['UPLOAD_FOLDER']

    # Upload first image
    client.post('/gallery/upload', data={'file': (io.BytesIO(b"img1_content"), 'img1.png')}, content_type='multipart/form-data', follow_redirects=True)

    # Upload second image
    client.post('/gallery/upload', data={'file': (io.BytesIO(b"img2_content"), 'img2.jpg')}, content_type='multipart/form-data', follow_redirects=True)

    uploaded_files = os.listdir(upload_folder)
    assert 'img1.png' in uploaded_files
    assert 'img2.jpg' in uploaded_files
    assert len(uploaded_files) == 3 # img1.png, img2.jpg, .gitkeep

    response_gallery = client.get('/gallery')
    assert response_gallery.status_code == 200
    assert b'src="/uploads/img1.png"' in response_gallery.data
    assert b'src="/uploads/img2.jpg"' in response_gallery.data

    # Check content of accessed images
    response_img1 = client.get('/uploads/img1.png')
    assert response_img1.status_code == 200
    assert response_img1.data == b"img1_content"

    response_img2 = client.get('/uploads/img2.jpg')
    assert response_img2.status_code == 200
    assert response_img2.data == b"img2_content"

# --- Existing To-Do tests from original file ---
def test_todo_page_get_empty(client):
    """Test accessing the /todo page when no tasks are present."""
    response = client.get('/todo')
    assert response.status_code == 200
    assert b"My To-Do List" in response.data
    assert b"No tasks yet!" in response.data

def test_add_task_post(client):
    """Test adding a single task via POST request."""
    response_add = client.post('/todo', data={'task': 'Test Task 1'}, follow_redirects=False)
    assert response_add.status_code == 302
    assert response_add.location == '/todo'

    response_get = client.get('/todo')
    assert response_get.status_code == 200
    assert b"Test Task 1" in response_get.data
    assert b"No tasks yet!" not in response_get.data

def test_add_multiple_tasks(client):
    """Test adding multiple tasks and verifying they all appear."""
    client.post('/todo', data={'task': 'First Test Task'}, follow_redirects=True)
    client.post('/todo', data={'task': 'Second Test Task'}, follow_redirects=True)

    response = client.get('/todo')
    assert response.status_code == 200
    assert b"First Test Task" in response.data
    assert b"Second Test Task" in response.data

def test_clear_tasks(client):
    """Test clearing all tasks."""
    client.post('/todo', data={'task': 'Task to be cleared'}, follow_redirects=True)
    response_before_clear = client.get('/todo')
    assert b"Task to be cleared" in response_before_clear.data

    response_clear = client.get('/todo/clear', follow_redirects=False)
    assert response_clear.status_code == 302
    assert response_clear.location == '/todo'

    response_after_clear = client.get('/todo')
    assert response_after_clear.status_code == 200
    assert b"Task to be cleared" not in response_after_clear.data
    assert b"No tasks yet!" in response_after_clear.data

def test_clear_empty_list(client):
    """Test clearing tasks when the list is already empty."""
    client.get('/todo/clear', follow_redirects=True)

    response_clear = client.get('/todo/clear', follow_redirects=False)
    assert response_clear.status_code == 302
    assert response_clear.location == '/todo'

    response_after_clear = client.get('/todo')
    assert response_after_clear.status_code == 200
    assert b"No tasks yet!" in response_after_clear.data

def test_add_empty_task_string(client):
    """Test adding an empty string as a task."""
    client.post('/todo', data={'task': 'Non-empty task'}, follow_redirects=True)
    client.post('/todo', data={'task': ''}, follow_redirects=True)

    response_get = client.get('/todo')
    assert b"Non-empty task" in response_get.data
    assert b"<li></li>" in response_get.data

    client.get('/todo/clear') # Cleanup


# --- Authentication Tests ---

def test_login_logout_successful(client):
    """Test successful login and then logout."""
    # Login
    response_login = client.post('/login', data={
        'username': 'demo',
        'password': 'password123'
    }, follow_redirects=False) # Don't follow redirect to check session and flash

    assert response_login.status_code == 302 # Should redirect after login
    # Default redirect is to hello_world which is '/'
    assert response_login.location == '/'


    with client.session_transaction() as sess:
        assert sess['logged_in'] is True
        assert sess['username'] == 'demo'

    # Check flash message on the redirected page
    response_redirected = client.get(response_login.location) # Manually follow redirect
    assert b"You are now logged in!" in response_redirected.data

    # Logout
    response_logout = client.get('/logout', follow_redirects=False)
    assert response_logout.status_code == 302
    assert response_logout.location == '/login' # Redirects to login page

    with client.session_transaction() as sess:
        assert 'logged_in' not in sess
        assert 'username' not in sess

    # Check flash message on the redirected page
    response_redirected_logout = client.get(response_logout.location)
    assert b"You are now logged out." in response_redirected_logout.data

def test_login_failed_wrong_password(client):
    """Test login attempt with incorrect password."""
    response = client.post('/login', data={
        'username': 'demo',
        'password': 'wrongpassword'
    }, follow_redirects=True) # Follow redirect to see rendered page with message

    assert response.status_code == 200 # Should re-render login page
    assert b"Invalid login." in response.data
    assert b"Login</title>" in response.data # Check we are on login page
    with client.session_transaction() as sess:
        assert 'logged_in' not in sess

def test_login_failed_wrong_username(client):
    """Test login attempt with a non-existent username."""
    response = client.post('/login', data={
        'username': 'nouser',
        'password': 'password123'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Invalid login." in response.data
    assert b"Login</title>" in response.data
    with client.session_transaction() as sess:
        assert 'logged_in' not in sess

def test_access_protected_route_todo_unauthenticated(client):
    """Test accessing /todo when not logged in."""
    response = client.get('/todo', follow_redirects=False)
    assert response.status_code == 302
    assert response.location == '/login'

    response_redirected = client.get(response.location) # Manually follow
    assert b"You need to be logged in to access this page." in response_redirected.data

def test_access_protected_route_upload_unauthenticated(client):
    """Test accessing /gallery/upload when not logged in."""
    response = client.get('/gallery/upload', follow_redirects=False)
    assert response.status_code == 302
    assert response.location == '/login'

    response_redirected = client.get(response.location)
    assert b"You need to be logged in to access this page." in response_redirected.data

def test_access_protected_route_todo_authenticated(client):
    """Test accessing /todo after successful login."""
    # First, log in
    client.post('/login', data={'username': 'demo', 'password': 'password123'}, follow_redirects=True)

    # Then, access the protected route
    response = client.get('/todo')
    assert response.status_code == 200
    assert b"My To-Do List" in response.data # Check for content from todo.html
    assert b"You need to be logged in" not in response.data # No error message

def test_access_protected_route_upload_authenticated(client):
    """Test accessing /gallery/upload after successful login."""
    client.post('/login', data={'username': 'demo', 'password': 'password123'}, follow_redirects=True)

    response = client.get('/gallery/upload')
    assert response.status_code == 200
    assert b"Upload a New Image" in response.data # Check for content from upload_image.html
    assert b"You need to be logged in" not in response.data
