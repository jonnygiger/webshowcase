import sys
import os
import pytest
import io # Add this import

# Add the parent directory to the Python path to allow importing 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app as flask_app, allowed_file # Import allowed_file

@pytest.fixture
def app_instance():
    """
    Provides the Flask app instance.
    This fixture is used by the `client` fixture.
    """
    flask_app.config['TESTING'] = True
    # Ensure UPLOAD_FOLDER is set for tests, if not already correctly derived in app.py
    # If app.py uses app.root_path, it should be fine.
    # Forcing a specific test upload folder can also be done here if needed:
    # test_upload_folder = os.path.join(flask_app.root_path, 'test_uploads')
    # flask_app.config['UPLOAD_FOLDER'] = test_upload_folder
    return flask_app

@pytest.fixture
def client(app_instance):
    """
    Provides a test client for the Flask application.
    Ensures that the app context is active for operations that require it.
    """
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
def manage_uploads(app_instance):
    # Setup: ensure upload folder is clean before each test
    upload_folder = app_instance.config['UPLOAD_FOLDER']
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


def test_allowed_file_utility(app_instance):
    # Test the allowed_file utility function directly
    with app_instance.app_context(): # Need app context for app.config
        assert allowed_file("test.jpg") == True
        assert allowed_file("test.png") == True
        assert allowed_file("test.jpeg") == True
        assert allowed_file("test.gif") == True
        assert allowed_file("test.JPG") == True
        assert allowed_file("test.PnG") == True
        assert allowed_file("test.txt") == False
        assert allowed_file("testjpg") == False # No dot
        assert allowed_file(".jpg") == False # No filename part
        assert allowed_file("test.") == False # No extension part


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
