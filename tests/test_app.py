import pytest
from app import app, db, User, TodoItem # Assuming app structure allows this import
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

@pytest.fixture
def client():
    # Setup
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing forms easily
    # Use a consistent test database URI. Using :memory: is fine for each test run.
    # If you need data to persist across client requests within a single test function,
    # ensure the app_context is managed correctly or consider a file-based SQLite for specific tests.
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

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

        test_client = app.test_client()
        yield test_client # This is where the testing happens

        # Teardown
        db.session.remove() # Ensures session is properly closed
        db.drop_all()       # Clears schema

def login_test_user(client, username="testuser", password="testpassword"):
    """Helper function to log in a test user."""
    # The client fixture already creates 'testuser'.
    # This function just performs the login action.
    return client.post('/login', data=dict(
        username=username,
        password=password
    ), follow_redirects=True)

def get_test_user():
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
    test_user = get_test_user()
    todo_item = TodoItem.query.filter_by(user_id=test_user.id, task=task_content).first()
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
    test_user = get_test_user()

    # First, create a task
    original_task_content = "Original task for editing"
    todo_item = TodoItem(task=original_task_content, user_id=test_user.id, due_date=datetime.now())
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
    test_user = get_test_user()

    todo_item = TodoItem(task="Task for status update", user_id=test_user.id, is_done=False)
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
    test_user = get_test_user()

    todo_item = TodoItem(task="Task to be deleted", user_id=test_user.id)
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
    test_user = get_test_user()

    # Create items with different due dates
    item1 = TodoItem(task="Due Last", user_id=test_user.id, due_date=datetime.now() + timedelta(days=2))
    item2 = TodoItem(task="Due First", user_id=test_user.id, due_date=datetime.now() + timedelta(days=1))
    item3 = TodoItem(task="No Due Date", user_id=test_user.id, due_date=None)
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
