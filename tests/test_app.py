import sys
import os
import pytest

# Add the parent directory to the Python path to allow importing 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app as flask_app

@pytest.fixture
def app_instance():
    """
    Provides the Flask app instance.
    This fixture is used by the `client` fixture.
    """
    # You might need to set specific configurations for testing here
    # For example, if your app has a database, you might configure a test database.
    flask_app.config['TESTING'] = True
    # It's good practice to use a different secret key for tests if sessions are involved,
    # though for this simple case, the app's default might be fine.
    # flask_app.config['SECRET_KEY'] = 'testsecretkey'
    return flask_app

@pytest.fixture
def client(app_instance):
    """
    Provides a test client for the Flask application.
    Ensures that the app context is active for operations that require it (like session handling).
    """
    with app_instance.app_context():
        # If your app initializes sessions, DB connections, or other context-bound resources,
        # ensure they are set up here if not handled by app_context itself.
        # For example, if you initialize session['todos'] somewhere globally or in a before_first_request,
        # that logic should ideally be part of app creation or handled within the app_context.
        # In this app, session['todos'] is initialized within the 'todo' route if not present,
        # so the app_context should be sufficient.
        yield app_instance.test_client()

def test_todo_page_get_empty(client):
    """Test accessing the /todo page when no tasks are present."""
    response = client.get('/todo')
    assert response.status_code == 200
    assert b"My To-Do List" in response.data
    assert b"No tasks yet!" in response.data

def test_add_task_post(client):
    """Test adding a single task via POST request."""
    # First, ensure the session is clean or behaves as expected for a new task
    # For this app, visiting /todo or any route that initializes session['todos'] is good.
    # Alternatively, if session clearing is needed, use a dedicated fixture or clear explicitly.

    # Add a task
    response_add = client.post('/todo', data={'task': 'Test Task 1'}, follow_redirects=False)
    assert response_add.status_code == 302  # Should redirect to /todo
    assert response_add.location == '/todo'

    # Verify the task is on the page after redirect
    response_get = client.get('/todo')
    assert response_get.status_code == 200
    assert b"Test Task 1" in response_get.data
    assert b"No tasks yet!" not in response_get.data # Ensure the 'empty' message is gone

def test_add_multiple_tasks(client):
    """Test adding multiple tasks and verifying they all appear."""
    # Add first task
    client.post('/todo', data={'task': 'First Test Task'}, follow_redirects=True)

    # Add second task
    client.post('/todo', data={'task': 'Second Test Task'}, follow_redirects=True)

    # Get the page and check for both tasks
    response = client.get('/todo')
    assert response.status_code == 200
    assert b"First Test Task" in response.data
    assert b"Second Test Task" in response.data

def test_clear_tasks(client):
    """Test clearing all tasks."""
    # First, add a task to ensure there's something to clear
    client.post('/todo', data={'task': 'Task to be cleared'}, follow_redirects=True)

    # Verify it's there
    response_before_clear = client.get('/todo')
    assert b"Task to be cleared" in response_before_clear.data

    # Clear the tasks
    response_clear = client.get('/todo/clear', follow_redirects=False)
    assert response_clear.status_code == 302  # Should redirect to /todo
    assert response_clear.location == '/todo'

    # Verify the task is gone and the "No tasks" message is back
    response_after_clear = client.get('/todo')
    assert response_after_clear.status_code == 200
    assert b"Task to be cleared" not in response_after_clear.data
    assert b"No tasks yet!" in response_after_clear.data

def test_clear_empty_list(client):
    """Test clearing tasks when the list is already empty."""
    # Ensure the list is empty (e.g., by clearing or starting fresh)
    # For this test, we'll assume a fresh client starts with an empty or new session.
    # If not, explicitly clear first:
    client.get('/todo/clear', follow_redirects=True) # Ensure it's empty

    response_clear = client.get('/todo/clear', follow_redirects=False)
    assert response_clear.status_code == 302
    assert response_clear.location == '/todo'

    response_after_clear = client.get('/todo')
    assert response_after_clear.status_code == 200
    assert b"No tasks yet!" in response_after_clear.data

def test_add_empty_task_string(client):
    """Test adding an empty string as a task."""
    response_add = client.post('/todo', data={'task': ''}, follow_redirects=True)
    assert response_add.status_code == 200 # Assuming it stays on /todo or redirects there
    # The app currently allows adding empty strings.
    # Check if an empty list item `<li></li>` or similar might appear,
    # or if the task count increases.
    # For this app, an empty string task will be rendered as an empty <li>.
    # This might be hard to distinguish from "No tasks yet!" if it's the only task.
    # Let's add a real task first, then an empty one.
    client.post('/todo', data={'task': 'Non-empty task'}, follow_redirects=True)
    client.post('/todo', data={'task': ''}, follow_redirects=True)

    response_get = client.get('/todo')
    assert b"Non-empty task" in response_get.data
    # Check for two list items. A simple way: count occurrences of "<li>"
    # This depends heavily on the HTML structure in todo.html
    # For `<li>{{ task }}</li>`, an empty task is `<li></li>`
    assert response_get.data.count(b"<li></li>") >= 1 # At least one empty task shown
    # Or, more robustly, check the session content if possible, but that's harder with just the client.
    # For now, checking rendered output is the primary method.
    # A more specific check might be:
    assert b"<li></li>" in response_get.data # Assuming empty task renders as <li></li>

    # Cleanup: Clear tasks to not affect other tests if tests share session state (they shouldn't with this fixture setup)
    client.get('/todo/clear')

# It's good practice to ensure tests clean up after themselves if they modify shared state.
# Pytest fixtures help isolate tests, especially the client fixture re-creating the client or app context.
# For session data, the test client under `app.app_context()` should handle session isolation
# if the sessions are correctly managed by Flask (e.g., using secure cookies).
# If tests were to interfere, one might need to explicitly clear session data in setup/teardown logic for tests.
# For this app, `session.pop('todos', None)` in `clear_todos` and re-initialization in `todo` route
# along with `app.app_context()` in the client fixture should provide sufficient isolation.
# The `SECRET_KEY` is also important for session consistency; using the app's actual key is fine
# as long as it's not changed during the test suite run in a way that invalidates sessions unexpectedly.
# `app.config['TESTING'] = True` also influences Flask's behavior to aid testing.

# To run these tests:
# 1. Make sure pytest is installed (`pip install pytest`).
# 2. Navigate to the root directory of the project in your terminal.
# 3. Run the command `pytest`.
# Pytest will automatically discover files named `test_*.py` or `*_test.py`
# and functions/methods prefixed with `test_`.
# The `tests` directory should be discoverable by pytest if you run it from the project root.
# Ensure `__init__.py` is in the `tests` directory.
# Ensure `app.py` is in the project root or adjust `sys.path` accordingly.
# The provided `sys.path.insert` should handle the case where `app.py` is in the parent dir of `tests/test_app.py`.
