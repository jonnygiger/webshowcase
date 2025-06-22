import os
import unittest
import json  # For checking JSON responses
import io  # For BytesIO
import time # Added for sleep
from unittest.mock import patch, call, ANY
# from flask_socketio import SocketIO # No longer creating a new SocketIO instance here
# Import the main app instance AND its socketio instance
from app import app as main_app, socketio as main_app_socketio # Import app's socketio
# db object is imported as app_db from models
from flask_jwt_extended import JWTManager
from flask_restful import Api
# Import db object directly, and other models
from models import db as app_db  # Alias to avoid conflict if we define 'db' locally
from models import (
    User,
    Message,
    Post,
    Friendship,
    FriendPostNotification,
    Group,
    Event,
    Poll,
    PollOption,
    TrendingHashtag,
    SharedFile,
    UserStatus,
    Achievement,
    UserAchievement,
    Comment,
    Series,
    SeriesPost,
    Notification,
    Like,
    EventRSVP,
    PollVote,
    PostLock,
)  # COMMENTED OUT - Added EventRSVP, PollVote, PostLock
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash


class AppTestCase(unittest.TestCase):
    app = None  # Class attribute for the Flask app
    db = None   # Class attribute for SQLAlchemy instance
    socketio_class_level = None # Stores the SocketIO object at class level

    @classmethod
    def setUpClass(cls):
        # Use the main app instance from app.py
        cls.app = main_app

        # Apply test-specific configurations TO THE IMPORTED APP
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        # Use a file-based SQLite DB for tests to ensure data visibility
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test_site.db"
        cls.app.config["SECRET_KEY"] = "test-secret-key"
        cls.app.config["JWT_SECRET_KEY"] = "test-jwt-secret-key"  # Added as per requirements
        cls.app.config["SERVER_NAME"] = "localhost" # Changed from localhost.test for simpler cookie domain
        cls.app.config["SOCKETIO_MESSAGE_QUEUE"] = None
        cls.app.config["SHARED_FILES_UPLOAD_FOLDER"] = "shared_files_test_folder" # Added for subtask
        shared_folder = cls.app.config["SHARED_FILES_UPLOAD_FOLDER"]
        if not os.path.exists(shared_folder):
            os.makedirs(shared_folder)
        cls.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False # Often set for SQLAlchemy

        # Initialize extensions with the test app
        # We use app_db which is the SQLAlchemy object from models.py
        # app_db.init_app(cls.app) # This is redundant if cls.app is main_app from app.py, as db is already initialized.
        # The config for SQLALCHEMY_DATABASE_URI has been updated on cls.app (main_app).
        # db.create_all() should respect this new URI when called within app_context.
        cls.db = app_db # Assign to class attribute for use in methods

        # Re-initialize SocketIO with the test-configured app instance (cls.app)
        # This ensures that SocketIO uses the same SECRET_KEY for session handling
        # as the one used by the Flask test client for HTTP requests.
        # We need to import SocketIO class here.
        from flask_socketio import SocketIO as TestSocketIO
        cls.socketio_class_level = TestSocketIO(cls.app, message_queue=cls.app.config.get('SOCKETIO_MESSAGE_QUEUE'))
        # Note: This new SocketIO instance (cls.socketio_class_level) does NOT have the
        # event handlers from app.py's `socketio` instance registered on it.
        # This is a problem. The event handlers (@socketio.on(...)) are registered on `main_app_socketio`.

        # The core issue is that the `socketio` instance from `app.py` (main_app_socketio)
        # is initialized with the original app config (original SECRET_KEY).
        # Modifying cls.app.config["SECRET_KEY"] later doesn't change the SECRET_KEY
        # that main_app_socketio's session interface is using.

        # A better approach: Instead of creating a new SocketIO instance,
        # try to make the existing main_app_socketio aware of the new SECRET_KEY.
        # This is tricky as Flask-SocketIO doesn't have a public API to reconfigure SECRET_KEY
        # after initialization.
        # The most straightforward way to ensure config consistency for sessions is for SocketIO
        # to be initialized *after* app config is set. This usually means a factory pattern for app creation.

        # Given the current structure, let's try a less ideal but potentially working hack:
        # Update the `secret_key` attribute on the app instance that `main_app_socketio` holds a reference to,
        # if it's different from `cls.app`. However, `main_app_socketio.app` should be `main_app`, which is `cls.app`.
        # So, `main_app_socketio.app.secret_key` should already reflect `cls.app.config["SECRET_KEY"]`.

        # Let's verify this assumption. If main_app_socketio.app.secret_key is indeed "test-secret-key",
        # then the SECRET_KEY mismatch is not the root cause, or not in the way described.

        # For now, let's stick to using the imported `main_app_socketio` and assume its
        # underlying app's secret_key is correctly updated when `cls.app.config` is changed,
        # because `cls.app` *is* `main_app`.
        cls.socketio_class_level = main_app_socketio
        assert cls.socketio_class_level is not None, "main_app_socketio is None"
        # Let's log the secret key that the main_app_socketio's app instance is using.
        if hasattr(cls.socketio_class_level, 'app') and cls.socketio_class_level.app:
            print(f"DEBUG: SocketIO App's SECRET_KEY in setUpClass: {cls.socketio_class_level.app.secret_key}")
            # This should print "test-secret-key" if our assumption is correct.

        # Initialize JWTManager - This is already done in app.py when 'jwt = JWTManager(app)' is called.
        # Re-initializing it here on cls.app (which is main_app from app.py) can cause errors
        # like "AssertionError: The setup method 'errorhandler' can no longer be called...".
        # JWTManager(cls.app) # REMOVED

        # Initialize Flask-Restful Api, if routes tested through self.client need it
        # cls.api = Api(cls.app) # Assign to cls.api - RELY ON app.api from app.py
        cls.api = cls.app.extensions.get('restful', None) # Try to get existing Api instance from app.py
        if cls.api is None: # If app.py didn't initialize Flask-RESTful, then we might need to.
             # However, app.py does initialize it, so this block should ideally not run.
             cls.api = Api(cls.app)


        # Import necessary components for routes - these are already on main_app from app.py
        # from app import api_login # As per app.py, this handles /api/login
        # from api import PostLockResource, CommentListResource, PostListResource

        # Register essential routes and resources - these are already on main_app from app.py
        # cls.app.add_url_rule('/api/login', view_func=api_login, methods=['POST'])
        # cls.api.add_resource(PostLockResource, '/api/posts/<int:post_id>/lock')
        # cls.api.add_resource(PostListResource, '/api/posts')
        # cls.api.add_resource(CommentListResource, '/api/posts/<int:post_id>/comments')

        # Example for other routes/blueprints if needed:
        # from app import main_routes_blueprint
        # cls.app.register_blueprint(main_routes_blueprint)

        with cls.app.app_context():
            cls.db.create_all()  # Create tables once per class

        # Store app_context for easy use in tests if needed, though usually `with cls.app.app_context():` is preferred
        # cls.app_context = cls.app.app_context()
        # cls.app_context.push() # Not pushing here, do it in setUp if needed or use 'with'

        # Re-initialize Api with the test app if it was already initialized in app.py with main app
        # This might be tricky if app.api is already populated with routes.
        # For now, let's assume app.api from app.py is what we want to use,
        # and test-specific API routes in this file might need to be re-evaluated.
        # If app.py's `api = Api(app)` has run, cls.api here might not be needed
        # or could conflict if we re-assign cls.app.api
        # Let's comment out cls.api initialization here and rely on app.py's api object.
        # cls.api = Api(cls.app)
        # The API routes added in app.py are already on main_app.api
        # The API routes added below using cls.api might be problematic.
        # For now, we will comment them out as they might be for specific test scenarios
        # not relevant to the current test file, or they might need to be added to main_app.api
        # if they are essential for all tests.

        # Import necessary components for routes - these are already on main_app
        # from app import api_login
        # from api import PostLockResource, CommentListResource, PostListResource

        # Register essential routes and resources - these are already on main_app
        # cls.app.add_url_rule('/api/login', view_func=api_login, methods=['POST'])
        # cls.api.add_resource(PostLockResource, '/api/posts/<int:post_id>/lock')
        # cls.api.add_resource(PostListResource, '/api/posts')
        # cls.api.add_resource(CommentListResource, '/api/posts/<int:post_id>/comments')


    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.db.drop_all()  # Drop tables once after all tests in the class
        # if hasattr(cls, 'app_context') and cls.app_context: # If we pushed context in setUpClass
            # cls.app_context.pop()
        # pass # Simplified for timeout debugging

    def setUp(self):
        """Set up for each test."""
        self.client = self.app.test_client() # Use the class's app instance

        # Create the SocketIO test client for each test instance
        assert self.socketio_class_level is not None, "socketio_class_level is None in setUp instance method!"
        self.socketio_client = self.socketio_class_level.test_client(self.app, flask_test_client=self.client)

        with self.app.app_context(): # Use the class's app instance for context
            self._clean_tables_for_setup() # Reverted to cleaning tables
            self._setup_base_users()  # Sets up self.user1, self.user2, self.user3
        # pass

    def _clean_tables_for_setup(self):
        """Clears data from tables before each test's user setup."""
        # Use the class's db instance
        self.db.session.remove()
        # Drop all tables and recreate them to ensure a truly clean state for each test.
        # This is more robust than deleting from tables, especially with complex relationships.
        self.db.drop_all()
        self.db.create_all()
        # No commit needed here as drop_all/create_all are DDL. Session is clean.
        # pass

    def tearDown(self):
        """Executed after each test."""
        with self.app.app_context(): # Ensure app context for DB operations
            self.db.session.remove() # Remove the current session
            # self.db.drop_all() # drop_all is now in _clean_tables_for_setup via setUp

        # Use the class's app instance for config
        shared_files_folder = self.app.config.get(
            "SHARED_FILES_UPLOAD_FOLDER"
        )
        if shared_files_folder and os.path.exists(shared_files_folder):
            for filename in os.listdir(shared_files_folder):
                file_path = os.path.join(shared_files_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}")

    def _setup_base_users(self):
        # This method is problematic without live User model and db session.
        # Called in setUp, which is now simplified. Kept for reference.
        self.user1 = User(
            username="testuser1",
            email="test1@example.com",
            password_hash=generate_password_hash("password"),
        )
        self.user2 = User(
            username="testuser2",
            email="test2@example.com",
            password_hash=generate_password_hash("password"),
        )
        self.user3 = User(
            username="testuser3",
            email="test3@example.com",
            password_hash=generate_password_hash("password"),
        )
        self.db.session.add_all([self.user1, self.user2, self.user3]) # Use class's db
        self.db.session.commit() # Use class's db
        # Refresh users to ensure their IDs are loaded from the DB session
        self.db.session.refresh(self.user1)
        self.db.session.refresh(self.user2)
        self.db.session.refresh(self.user3)
        self.user1_id = self.user1.id
        self.user2_id = self.user2.id
        self.user3_id = self.user3.id
        # pass

    def _create_friendship(self, user1_id, user2_id, status="accepted"):
        # Requires live Friendship model and db session
        with self.app.app_context(): # Ensure app context for DB operations
            friendship = Friendship(user_id=user1_id, friend_id=user2_id, status=status)
            self.db.session.add(friendship) # Use class's db
            self.db.session.commit() # Use class's db
            return friendship.id # Return the ID

    def _create_db_post(
        self, user_id, title="Test Post", content="Test Content", timestamp=None
    ):
        # Requires live Post model and db session
        with self.app.app_context(): # Ensure app context for DB operations
            post = Post(
                user_id=user_id,
                title=title,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(post) # Use class's db
            self.db.session.commit() # Use class's db

            # Debug check
            retrieved_post = self.db.session.get(Post, post.id)
            if retrieved_post is None:
                print(f"DEBUG: Post with id {post.id} was NOT found immediately after commit in _create_db_post!")
                # Optionally raise an exception to make it a hard failure here
                raise Exception(f"Post with id {post.id} not found immediately after commit in _create_db_post!")
            else:
                print(f"DEBUG: Post with id {post.id} WAS found immediately after commit in _create_db_post.")

            return post # Return the full post object

    def _make_post_via_route(
        self, username, password, title="Test Post", content="Test Content", hashtags=""
    ):
        self.login(username, password)
        response = self.client.post(
            "/blog/create",
            data=dict(title=title, content=content, hashtags=hashtags),
            follow_redirects=True,
        )
        self.logout()
        return response

    def create_socketio_client(self):
        """Creates a new SocketIO test client instance."""
        # It's important that this new client also has access to the Flask test client's cookie jar
        # if we want to share session state easily.
        # The flask_test_client argument to socketio.test_client() helps share cookies.
        return self.socketio_class_level.test_client(self.app, flask_test_client=self.client)

    def login(self, username, password, client_instance=None):
        # Determine which HTTP client to use for login
        http_client = self.client # Default to the instance's primary flask test client

        # Flask login via POST request
        response = http_client.post(
            "/login",
            data=dict(username=username, password=password),
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200, f"HTTP Login failed for {username}")

        # If a specific socketio client instance is provided, ensure its session is updated.
        # Flask-SocketIO's test_client when initialized with flask_test_client=self.client
        # should share the cookie jar. So, the login via self.client should update cookies
        # that are then available to socketio_client instances created with that self.client.
        # No explicit cookie copying might be needed if this link is correctly established.
        # However, the issue in tests might stem from SocketIO handlers not picking up Flask session
        # correctly during emits if the session wasn't established *for that socket connection*.
        # The `connect()` method of the socketio_client is usually where initial session handshake would occur.
        # For testing, explicitly connecting after login might be beneficial if not done automatically.

        # If a specific socket.io client (different from self.socketio_client) needs to reflect this login
        # and it was created with its own flask_test_client or none, this would be more complex.
        # But given create_socketio_client also links to self.client, this should be okay.

        # After HTTP login, if a specific socketio client instance is being set up,
        # explicitly connect it to ensure its connection handshake uses the new session.
        socket_client_to_connect = None
        if client_instance: # If a specific socketio client is passed
            socket_client_to_connect = client_instance
        elif hasattr(self, 'socketio_client'): # Fallback to the default one for the test case
            socket_client_to_connect = self.socketio_client

        if socket_client_to_connect:
            if socket_client_to_connect.is_connected():
                socket_client_to_connect.disconnect()
            socket_client_to_connect.connect() # Connect (or reconnect) to the default namespace
            time.sleep(0.05) # Allow time for connection to establish fully on server side
            # Try to process any connection acknowledgment packets
            socket_client_to_connect.get_received('/')

        return response


    def logout(self, client_instance=None):
        http_client = self.client # Default to the instance's primary flask test client

        # If a specific socketio client is being logged out, disconnect it.
        socket_client_to_disconnect = None
        if client_instance:
            socket_client_to_disconnect = client_instance
        elif hasattr(self, 'socketio_client'):
             socket_client_to_disconnect = self.socketio_client

        if socket_client_to_disconnect and hasattr(socket_client_to_disconnect, 'is_connected') and socket_client_to_disconnect.is_connected():
            socket_client_to_disconnect.disconnect()

        response = http_client.get("/logout", follow_redirects=True)
        self.assertEqual(response.status_code, 200, "HTTP Logout failed")

        # Similar to login, cookie changes from http_client.get('/logout')
        # should be reflected in socketio_clients that share its cookie jar.
        return response

    def _create_db_message(
        self, sender_id, receiver_id, content, timestamp=None, is_read=False
    ):
        # Requires live Message model and db session
        with self.app.app_context(): # Ensure app context for DB operations
            msg = Message(
                sender_id=sender_id,
                receiver_id=receiver_id,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
                is_read=is_read,
            )
            self.db.session.add(msg) # Use class's db
            self.db.session.commit() # Use class's db
            return msg

    def _get_jwt_token(self, username, password):
        response = self.client.post(
            "/api/login", json={"username": username, "password": password} # Changed to /api/login to match app.py
        )
        self.assertEqual(
            response.status_code,
            200,
            f"Login failed for token generation: {response.data.decode()}",
        )
        data = json.loads(response.data)
        self.assertIn("access_token", data, "Access token not found in login response.")
        return data["access_token"]

    def create_dummy_file(
        self, filename="test.txt", content=b"hello world", content_type="text/plain"
    ):
        return (io.BytesIO(content), filename, content_type)

    def _create_db_group(
        self, creator_id, name="Test Group", description="A group for testing"
    ):
        # Requires live Group model and db session
        with self.app.app_context(): # Ensure app context for DB operations
            group = Group(name=name, description=description, creator_id=creator_id)
            self.db.session.add(group) # Use class's db
            self.db.session.commit() # Use class's db
            return self.db.session.get(Group, group.id) # Re-fetch

    def _create_db_event(
        self,
        user_id,
        title="Test Event",
        description="An event for testing",
        date_str="2024-12-31", # Expected format YYYY-MM-DD
        time_str="18:00",      # Expected format HH:MM
        location="Test Location",
        created_at=None,
    ):
        # Requires live Event model and db session
        with self.app.app_context(): # Ensure app context for DB operations
            # Combine date_str and time_str to create a datetime object
            event_datetime_obj = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            event = Event(
                user_id=user_id,
                title=title,
                description=description,
                date=event_datetime_obj, # Store the datetime object
                location=location,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(event) # Use class's db
            self.db.session.commit() # Use class's db
            # _ = event.id # Ensure ID is loaded # Not strictly necessary if re-fetching
            return self.db.session.get(Event, event.id) # Re-fetch

    def _create_db_poll(
        self, user_id, question="Test Poll?", options_texts=None, created_at=None
    ):
        if options_texts is None:
            options_texts = ["Option 1", "Option 2"]
        # Requires live Poll, PollOption models and db session
        with self.app.app_context(): # Ensure app context for DB operations
            poll = Poll(
                user_id=user_id,
                question=question,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(poll) # Use class's db
            self.db.session.commit()  # Commit to get poll.id, use class's db
            for text in options_texts:
                option = PollOption(text=text, poll_id=poll.id)
                self.db.session.add(option) # Use class's db
            self.db.session.commit() # Use class's db
            _ = poll.id # Ensure ID is loaded
            # Also ensure options are loaded if they are accessed via poll.options in tests
            # _ = [opt.id for opt in poll.options] # Re-fetching poll should handle this
            return self.db.session.get(Poll, poll.id) # Re-fetch

    def _create_db_like(self, user_id, post_id, timestamp=None):
        from models import Like  # Local import to avoid circular if not using live DB

        with self.app.app_context(): # Ensure app context for DB operations
            like = Like(
                user_id=user_id, post_id=post_id, timestamp=timestamp or datetime.now(timezone.utc)
            )
            self.db.session.add(like) # Use class's db
            self.db.session.commit() # Use class's db
            return like

    def _create_db_comment(
        self, user_id, post_id, content="Test comment", timestamp=None
    ):
        from models import Comment

        with self.app.app_context(): # Ensure app context for DB operations
            comment = Comment(
                user_id=user_id,
                post_id=post_id,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(comment) # Use class's db
            self.db.session.commit() # Use class's db
            return comment

    def _create_db_event_rsvp(
        self, user_id, event_id, status="Attending", timestamp=None
    ):
        from models import EventRSVP

        with self.app.app_context(): # Ensure app context for DB operations
            rsvp = EventRSVP(
                user_id=user_id,
                event_id=event_id,
                status=status,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(rsvp) # Use class's db
            self.db.session.commit() # Use class's db
            return rsvp

    def _create_db_poll_vote(self, user_id, poll_id, poll_option_id, created_at=None):
        from models import PollVote

        with self.app.app_context(): # Ensure app context for DB operations
            vote = PollVote(
                user_id=user_id,
                poll_id=poll_id,
                poll_option_id=poll_option_id,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(vote) # Use class's db
            self.db.session.commit() # Use class's db
            return vote

    def _create_series(
        self,
        user_id,
        title="Test Series",
        description="A series for testing.",
        created_at=None,
        updated_at=None,
    ):
        # Requires Series model and db session
        with self.app.app_context(): # Ensure app context for DB operations
            series = Series(
                user_id=user_id,
                title=title,
                description=description,
                created_at=created_at or datetime.now(timezone.utc),
                updated_at=updated_at or datetime.now(timezone.utc),
            )
            self.db.session.add(series) # Use class's db
            self.db.session.commit() # Use class's db
            return self.db.session.get(Series, series.id) # Re-fetch

    def assertInHTML(self, needle, haystack, achievement_name):
        try:
            ach_name_idx = haystack.find(achievement_name)
            self.assertTrue(
                ach_name_idx != -1,
                f"Achievement name '{achievement_name}' not found in HTML.",
            )
            search_range = haystack[ach_name_idx : ach_name_idx + 300]
            self.assertIn(
                needle,
                search_range,
                f"'{needle}' not found near '{achievement_name}' in HTML: {search_range[:200]}...",
            )
        except AttributeError:
            self.fail("Haystack for assertInHTML was not a string.")

    def _create_db_lock(self, post_id, user_id, minutes_offset=0):
        from models import PostLock

        with self.app.app_context(): # Ensure app context for DB operations
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes_offset)
            lock = PostLock(post_id=post_id, user_id=user_id, expires_at=expires_at)
            self.db.session.add(lock) # Use class's db
            self.db.session.commit() # Use class's db
            # Re-fetch the lock to ensure it's bound to the session and has its ID populated.
            return self.db.session.get(PostLock, lock.id)
