import os
import sys
import unittest
import json  # For checking JSON responses
import io  # For BytesIO
import time  # Added for sleep
from unittest.mock import patch, call, ANY

# from flask_socketio import SocketIO # No longer creating a new SocketIO instance here
# Import the main app instance AND its socketio instance
from app import app as main_app, socketio as main_app_socketio  # Import app's socketio

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
    db = None  # Class attribute for SQLAlchemy instance
    socketio_class_level = None  # Stores the SocketIO object at class level

    @classmethod
    def setUpClass(cls):
        # Use the main app instance from app.py
        cls.app = main_app

        # Apply test-specific configurations TO THE IMPORTED APP
        # IMPORTANT: Set SERVER_NAME before initializing extensions that might use it (like SocketIO for session cookies)
        cls.app.config["SERVER_NAME"] = (
            "localhost"  # Changed from localhost.test for simpler cookie domain
        )
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        # Use a file-based SQLite DB for tests to ensure data visibility
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test_site.db"
        cls.app.config["SECRET_KEY"] = "test-secret-key"
        cls.app.config["JWT_SECRET_KEY"] = (
            "test-jwt-secret-key"  # Added as per requirements
        )
        cls.app.config["SOCKETIO_MESSAGE_QUEUE"] = None # Ensure this is None for testing
        cls.app.config["SHARED_FILES_UPLOAD_FOLDER"] = (
            "shared_files_test_folder"  # Added for subtask
        )
        shared_folder = cls.app.config["SHARED_FILES_UPLOAD_FOLDER"]
        if not os.path.exists(shared_folder):
            os.makedirs(shared_folder)
        cls.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = (
            False  # Often set for SQLAlchemy
        )

        # Initialize extensions with the test app
        # We use app_db which is the SQLAlchemy object from models.py
        # app_db.init_app(cls.app) # This is redundant if cls.app is main_app from app.py, as db is already initialized.
        # The config for SQLALCHEMY_DATABASE_URI has been updated on cls.app (main_app).
        # db.create_all() should respect this new URI when called within app_context.
        cls.db = app_db  # Assign to class attribute for use in methods

        # Re-initialize SocketIO with the test-configured app instance (cls.app)
        # This ensures that SocketIO uses the same SECRET_KEY for session handling
        # as the one used by the Flask test client for HTTP requests.
        # We need to import SocketIO class here.
        from flask_socketio import SocketIO as TestSocketIO

        cls.socketio_class_level = TestSocketIO(
            cls.app, message_queue=cls.app.config.get("SOCKETIO_MESSAGE_QUEUE")
        )
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
        # cls.socketio_class_level = main_app_socketio # OLD APPROACH

        # NEW APPROACH: Re-initialize SocketIO with the test-configured app.
        # This ensures that the SocketIO instance uses all the test configurations.
        from flask_socketio import SocketIO as TestSocketIOAppSocketIO
        cls.socketio_class_level = TestSocketIOAppSocketIO(
            cls.app,
            async_mode=cls.app.config.get("SOCKETIO_ASYNC_MODE", 'threading'), # Ensure async_mode is consistent
            message_queue=cls.app.config.get("SOCKETIO_MESSAGE_QUEUE")
        )
        # Register handlers from app.py onto this new socketio instance
        # This is the tricky part. The handlers are registered on `main_app_socketio`.
        # We need to either re-register them or find a way to make `main_app_socketio` re-init with new config.
        # The cleanest is that app.py's socketio object should be the one used and it should pick up config.
        # Let's revert to using main_app_socketio but ensure its app reference is cls.app and it re-reads config.
        # Flask-SocketIO's init_app method can be called to re-initialize.
        main_app_socketio.init_app(cls.app, async_mode=cls.app.config.get("SOCKETIO_ASYNC_MODE", 'threading'),
                                   message_queue=cls.app.config.get("SOCKETIO_MESSAGE_QUEUE"))
        cls.socketio_class_level = main_app_socketio


        assert cls.socketio_class_level is not None, "main_app_socketio is None"
        # Let's log the secret key that the main_app_socketio's app instance is using.
        if hasattr(cls.socketio_class_level, "app") and cls.socketio_class_level.app:
            print(
                f"DEBUG: SocketIO App's SECRET_KEY in setUpClass after init_app: {cls.socketio_class_level.app.secret_key}"
            )
            # This should print "test-secret-key" if our assumption is correct.

        # Configure Flask app logger to output DEBUG messages to stderr
        import logging
        cls.app.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        # Remove existing handlers to avoid duplicate messages if any were added by default
        for h in cls.app.logger.handlers:
            cls.app.logger.removeHandler(h)
        cls.app.logger.addHandler(handler)
        cls.app.logger.propagate = False # Prevent messages from propagating to the root logger if it has handlers


        # Initialize JWTManager - This is already done in app.py when 'jwt = JWTManager(app)' is called.
        # Re-initializing it here on cls.app (which is main_app from app.py) can cause errors
        # like "AssertionError: The setup method 'errorhandler' can no longer be called...".
        # JWTManager(cls.app) # REMOVED

        # Initialize Flask-Restful Api, if routes tested through self.client need it
        # cls.api = Api(cls.app) # Assign to cls.api - RELY ON app.api from app.py
        cls.api = cls.app.extensions.get(
            "restful", None
        )  # Try to get existing Api instance from app.py
        if (
            cls.api is None
        ):  # If app.py didn't initialize Flask-RESTful, then we might need to.
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
        self.client = self.app.test_client()  # Use the class's app instance for HTTP requests

        # Create the SocketIO test client for each test instance
        # Now connects to the live test server
        assert (
            self.socketio_class_level is not None
        ), "socketio_class_level is None in setUp instance method!"

        # When connecting to a live server, we don't pass flask_test_client.
        # We connect to the server's URL.
        # However, SocketIOTestClient is designed to work with the app directly or a test client.
        # For connecting to a live, separate server, we'd use a standard python-socketio client.
        # Let's stick to the Flask-SocketIO test client but without flask_test_client if server is live.
        # This is where it gets tricky. The SocketIOTestClient is not meant for a truly external server.
        # It's for testing the app *directly*.
        # If we run a live server, we should use a regular socketio.Client().

        # For now, let's assume the goal is to make the *existing* test client work better
        # by ensuring the app it tests is configured correctly.
        # The live server approach is an alternative if this direct testing continues to fail.
        # The current plan is to implement live server. So, we need a real client.

        # Reverting to use the standard test_client for now, and will adjust if live server
        # is fully implemented with a real client.
        # The re-initialization of main_app_socketio in setUpClass should have fixed config issues.
        # The live server setup above is a preparation for a different client connection strategy.

        # If using live server, the client would be:
        # import socketio as std_socketio
        # self.socketio_client_live = std_socketio.Client()
        # self.socketio_client_live.connect(f'http://localhost:{self.TEST_SERVER_PORT}')
        # For now, keep using the Flask-SocketIO test client, assuming the live server
        # isn't strictly needed if direct app testing can be fixed.
        # The plan says "implement live test server", so let's adjust client instantiation.
        # This means `login` method will also need to change how it gets cookies to this client.

        # For now, to test the server setup, let's keep the original socketio_client
        # that works directly with the app. The live server is running, but not used by this client.
        # This is an intermediate step.
        self.socketio_client = self.socketio_class_level.test_client( # Reverted to Flask-SocketIO test client
             self.app, flask_test_client=self.client
        )


        with self.app.app_context():  # Use the class's app instance for context
            self._clean_tables_for_setup()  # Reverted to cleaning tables
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
        # Disconnect the Flask-SocketIO test client
        if hasattr(self, 'socketio_client') and self.socketio_client:
            if self.socketio_client.is_connected():
                client_sid = getattr(self.socketio_client, 'sid', 'N/A (sid missing despite connected)')
                print(f"Disconnecting Flask-SocketIO test_client in tearDown. SID: {client_sid}", file=sys.stderr)
                self.socketio_client.disconnect()
                print("Flask-SocketIO test_client disconnected in tearDown.", file=sys.stderr)
            else:
                print("Flask-SocketIO test_client existed in tearDown but was not connected.", file=sys.stderr)
        else:
            print("No socketio_client found in tearDown.", file=sys.stderr)


        with self.app.app_context():  # Ensure app context for DB operations
            self.db.session.remove()  # Remove the current session
            # self.db.drop_all() # drop_all is now in _clean_tables_for_setup via setUp

        # Use the class's app instance for config
        shared_files_folder = self.app.config.get("SHARED_FILES_UPLOAD_FOLDER")
        if shared_files_folder and os.path.exists(shared_files_folder):
            for filename in os.listdir(shared_files_folder):
                file_path = os.path.join(shared_files_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}")

        # Ensure the main socketio_client for the test case is disconnected
        # This part was for the Flask-SocketIO test client, may not be needed if using std_socketio client
        # if hasattr(self, 'socketio_client') and self.socketio_client and self.socketio_client.is_connected():
        #     self.socketio_client.disconnect()

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
        self.db.session.add_all([self.user1, self.user2, self.user3])  # Use class's db
        self.db.session.commit()  # Use class's db
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
        with self.app.app_context():  # Ensure app context for DB operations
            friendship = Friendship(user_id=user1_id, friend_id=user2_id, status=status)
            self.db.session.add(friendship)  # Use class's db
            self.db.session.commit()  # Use class's db
            return friendship.id  # Return the ID

    def _create_db_post(
        self, user_id, title="Test Post", content="Test Content", timestamp=None
    ):
        # Requires live Post model and db session
        with self.app.app_context():  # Ensure app context for DB operations
            post = Post(
                user_id=user_id,
                title=title,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(post)  # Use class's db
            self.db.session.commit()  # Use class's db

            # Debug check
            # retrieved_post = self.db.session.get(Post, post.id) # Re-fetch to ensure it's in session
            # self.assertIsNotNone(retrieved_post, f"Post with id {post.id} was NOT found immediately after commit in _create_db_post!")
            return self.db.session.get(Post, post.id) # Return the re-fetched post object

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
        return self.socketio_class_level.test_client(
            self.app, flask_test_client=self.client
        )

    def login(self, username, password, client_instance=None):
        # Determine which HTTP client to use for login
        http_client = self.client
        login_response = None

        # Flask login via POST request
        with http_client.session_transaction() as sess:
            # This ensures session modifications by self.client.post are captured
            # and available for the SocketIO client if it uses the same session mechanism.
            # However, SocketIO client typically relies on cookies.
            pass # Just to establish the context

        login_response = http_client.post(
            "/login",
            data=dict(username=username, password=password),
            follow_redirects=True,
        )
        self.assertEqual(login_response.status_code, 200, f"HTTP Login failed for {username}")

        # Extract cookies from the HTTP client's cookie jar AFTER the login request
        cookie_header = None
        cookies_list = []
        if hasattr(http_client, "cookie_jar") and http_client.cookie_jar is not None:
            for cookie_in_jar in http_client.cookie_jar:
                cookies_list.append(f"{cookie_in_jar.name}={cookie_in_jar.value}")

        if cookies_list:
            cookie_header = "; ".join(cookies_list)
            print(f"DEBUG: Cookie header for SocketIO connect for {username}: {cookie_header}")
        else:
            # Fallback for cases where cookie_jar might not be populated as expected,
            # e.g., if using a different test client setup or version.
            print(f"DEBUG: No cookies found in http_client.cookie_jar for {username}. Trying Set-Cookie header.")
            set_cookie_header_value = login_response.headers.get('Set-Cookie')
            if set_cookie_header_value:
                # Simplistic parsing: take the first part of Set-Cookie, assuming it's the session cookie.
                # This might need refinement if multiple cookies are set or format is complex.
                cookie_header = set_cookie_header_value.split(';')[0]
                print(f"DEBUG: Fallback - Using Set-Cookie from login response for {username}: {cookie_header}")


        connect_headers = {}
        if cookie_header:
            connect_headers['Cookie'] = cookie_header
        else:
            print(f"DEBUG: No cookie header could be constructed for {username}. SocketIO connection might fail authentication.")


        # If a specific client_instance is provided, use it. Otherwise, use self.socketio_client.
        # This part is tricky because the self.socketio_client is often recreated.
        # Forcing a new client for each login to ensure cookie freshness.

        if hasattr(self, 'socketio_client') and self.socketio_client and self.socketio_client.is_connected(namespace='/'):
            self.socketio_client.disconnect(namespace='/')
            time.sleep(0.2) # Give server a moment to process disconnect

        # Create a new SocketIO client instance FOR THIS LOGIN, ensuring it uses the latest cookies from self.client
        # This new client becomes the primary self.socketio_client for subsequent actions in the test.
        self.socketio_client = self.socketio_class_level.test_client(
            self.app,
            flask_test_client=self.client, # Use the main test client
            headers=connect_headers # Pass extracted cookies if available
        )
        # The test_client attempts to connect automatically when created with flask_test_client.
        # The headers argument ensures this initial connection attempt uses the session cookie.

        time.sleep(0.1) # Give a brief moment for connection to establish and SID to be assigned.

        if not getattr(self.socketio_client, 'sid', None):
            # If SID is still not assigned, the connection with authentication failed.
            eio_sid_val = "N/A"
            if hasattr(self.socketio_client, 'eio_test_client') and self.socketio_client.eio_test_client:
                eio_sid_val = getattr(self.socketio_client.eio_test_client, 'sid', "N/A (eio_test_client has no sid)")

            # Check is_connected status for more detailed error reporting
            is_connected_status = self.socketio_client.is_connected(namespace='/')
            print(f"DEBUG: SocketIO client for {username} failed to get SID. "
                  f"is_connected: {is_connected_status}, sid: None, eio_sid: {eio_sid_val}", file=sys.stderr)

            # It's possible the client thinks it's connected but didn't get an SID,
            # or the connection failed more fundamentally.
            if not is_connected_status and eio_sid_val == "N/A (eio_test_client has no sid)":
                 # This suggests a more fundamental Engine.IO connection failure.
                 # Try a more forceful explicit connect, though it might be redundant if the constructor's attempt failed.
                 print(f"DEBUG: Attempting a more explicit connect for {username} due to fundamental connection failure indication.", file=sys.stderr)
                 self.socketio_client.connect(namespace='/', headers=connect_headers)
                 time.sleep(0.1) # Wait again after explicit connect
                 if not getattr(self.socketio_client, 'sid', None):
                    raise ConnectionError(
                        f"SocketIO client for {username} still failed to connect or get SID after explicit attempt. "
                        f"is_connected: {self.socketio_client.is_connected(namespace='/')}, "
                        f"sid: {getattr(self.socketio_client, 'sid', None)}, eio_sid: {eio_sid_val}"
                    )
            elif not getattr(self.socketio_client, 'sid', None) : # SID still missing even if is_connected might be true
                raise ConnectionError(
                    f"SocketIO client for {username} failed to get SID despite connection attempt. "
                    f"is_connected: {is_connected_status}, "
                    f"sid: None, eio_sid: {eio_sid_val}"
                )


        print(f"DEBUG: SocketIO client for {username} connected with SID: {self.socketio_client.sid}", file=sys.stderr)

        return login_response # Return the login_response

    def logout(self, client_instance=None):
        http_client = self.client  # Default to the instance's primary flask test client

        # If a specific socketio client is being logged out, disconnect it.
        socket_client_to_disconnect = None
        if client_instance:
            socket_client_to_disconnect = client_instance
        elif hasattr(self, "socketio_client"):
            socket_client_to_disconnect = self.socketio_client

        if (
            socket_client_to_disconnect
            and hasattr(socket_client_to_disconnect, "is_connected")
            and socket_client_to_disconnect.is_connected()
        ):
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
        with self.app.app_context():  # Ensure app context for DB operations
            msg = Message(
                sender_id=sender_id,
                receiver_id=receiver_id,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
                is_read=is_read,
            )
            self.db.session.add(msg)  # Use class's db
            self.db.session.commit()  # Use class's db
            return msg

    def _get_jwt_token(self, username, password):
        response = self.client.post(
            "/api/login",
            json={
                "username": username,
                "password": password,
            },  # Changed to /api/login to match app.py
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
        with self.app.app_context():  # Ensure app context for DB operations
            group = Group(name=name, description=description, creator_id=creator_id)
            self.db.session.add(group)  # Use class's db
            self.db.session.commit()  # Use class's db
            return self.db.session.get(Group, group.id)  # Re-fetch

    def _create_db_event(
        self,
        user_id,
        title="Test Event",
        description="An event for testing",
        date_str="2024-12-31",  # Expected format YYYY-MM-DD
        time_str="18:00",  # Expected format HH:MM
        location="Test Location",
        created_at=None,
    ):
        # Requires live Event model and db session
        with self.app.app_context():  # Ensure app context for DB operations
            # Combine date_str and time_str to create a datetime object
            event_datetime_obj = datetime.strptime(
                f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
            )
            event = Event(
                user_id=user_id,
                title=title,
                description=description,
                date=event_datetime_obj,  # Store the datetime object
                location=location,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(event)  # Use class's db
            self.db.session.commit()  # Use class's db
            # _ = event.id # Ensure ID is loaded # Not strictly necessary if re-fetching
            return self.db.session.get(Event, event.id)  # Re-fetch

    def _create_db_poll(
        self, user_id, question="Test Poll?", options_texts=None, created_at=None
    ):
        if options_texts is None:
            options_texts = ["Option 1", "Option 2"]
        # Requires live Poll, PollOption models and db session
        with self.app.app_context():  # Ensure app context for DB operations
            poll = Poll(
                user_id=user_id,
                question=question,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(poll)  # Use class's db
            self.db.session.commit()  # Commit to get poll.id, use class's db
            for text in options_texts:
                option = PollOption(text=text, poll_id=poll.id)
                self.db.session.add(option)  # Use class's db
            self.db.session.commit()  # Use class's db
            _ = poll.id  # Ensure ID is loaded
            # Also ensure options are loaded if they are accessed via poll.options in tests
            # _ = [opt.id for opt in poll.options] # Re-fetching poll should handle this
            return self.db.session.get(Poll, poll.id)  # Re-fetch

    def _create_db_like(self, user_id, post_id, timestamp=None):
        from models import Like  # Local import to avoid circular if not using live DB

        with self.app.app_context():  # Ensure app context for DB operations
            like = Like(
                user_id=user_id,
                post_id=post_id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(like)  # Use class's db
            self.db.session.commit()  # Use class's db
            return like

    def _create_db_comment(
        self, user_id, post_id, content="Test comment", timestamp=None
    ):
        from models import Comment

        with self.app.app_context():  # Ensure app context for DB operations
            comment = Comment(
                user_id=user_id,
                post_id=post_id,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(comment)  # Use class's db
            self.db.session.commit()  # Use class's db
            return comment

    def _create_db_event_rsvp(
        self, user_id, event_id, status="Attending", timestamp=None
    ):
        from models import EventRSVP

        with self.app.app_context():  # Ensure app context for DB operations
            rsvp = EventRSVP(
                user_id=user_id,
                event_id=event_id,
                status=status,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(rsvp)  # Use class's db
            self.db.session.commit()  # Use class's db
            return rsvp.id # Return ID

    def _create_db_poll_vote(self, user_id, poll_id, poll_option_id, created_at=None):
        from models import PollVote

        with self.app.app_context():  # Ensure app context for DB operations
            vote = PollVote(
                user_id=user_id,
                poll_id=poll_id,
                poll_option_id=poll_option_id,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(vote)  # Use class's db
            self.db.session.commit()  # Use class's db
            return vote.id # Return ID

    def _create_series(
        self,
        user_id,
        title="Test Series",
        description="A series for testing.",
        created_at=None,
        updated_at=None,
    ):
        # Requires Series model and db session
        with self.app.app_context():  # Ensure app context for DB operations
            series = Series(
                user_id=user_id,
                title=title,
                description=description,
                created_at=created_at or datetime.now(timezone.utc),
                updated_at=updated_at or datetime.now(timezone.utc),
            )
            self.db.session.add(series)  # Use class's db
            self.db.session.commit()  # Use class's db
            return self.db.session.get(Series, series.id)  # Re-fetch

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

        with self.app.app_context():  # Ensure app context for DB operations
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes_offset)
            lock = PostLock(post_id=post_id, user_id=user_id, expires_at=expires_at)
            self.db.session.add(lock)  # Use class's db
            self.db.session.commit()  # Use class's db
            # Re-fetch the lock to ensure it's bound to the session and has its ID populated.
            return self.db.session.get(PostLock, lock.id)

    def _create_db_user(self, username, password="password", email=None, role="user"):
        if email is None:
            email = f"{username}@example.com"
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role
        )
        self.db.session.add(user)
        self.db.session.commit()
        self.db.session.refresh(user) # Ensure ID and other defaults are loaded
        return user

    def _create_db_series(self, user_id, title="Test Series", description="A series for testing.", created_at=None, updated_at=None):
        # This method was named _create_series before, standardizing to _create_db_series
        with self.app.app_context():
            series = Series(
                user_id=user_id,
                title=title,
                description=description,
                created_at=created_at or datetime.now(timezone.utc),
                updated_at=updated_at or datetime.now(timezone.utc),
            )
            self.db.session.add(series)
            self.db.session.commit()
            return self.db.session.get(Series, series.id)

    def _create_db_bookmark(self, user_id, post_id, timestamp=None):
        from models import Bookmark # Local import just in case
        with self.app.app_context():
            bookmark = Bookmark(
                user_id=user_id,
                post_id=post_id,
                timestamp=timestamp or datetime.now(timezone.utc)
            )
            self.db.session.add(bookmark)
            self.db.session.commit()
            return bookmark

    def _create_db_block(self, blocker_user_obj, blocked_user_obj, timestamp=None):
        from models import UserBlock # Local import
        with self.app.app_context():
            block = UserBlock(
                blocker_id=blocker_user_obj.id,
                blocked_id=blocked_user_obj.id,
                timestamp=timestamp or datetime.now(timezone.utc)
            )
            self.db.session.add(block)
            self.db.session.commit()
            block_id = block.id # Get the ID before context closes or object becomes detached
            return block_id # Return the ID

    def _create_db_friendship(self, user_obj_1, user_obj_2, status="accepted", timestamp=None):
        # This method was _create_friendship before, standardizing and using user objects
        with self.app.app_context():
            friendship = Friendship(
                user_id=user_obj_1.id,
                friend_id=user_obj_2.id,
                status=status,
                timestamp=timestamp or datetime.now(timezone.utc)
            )
            self.db.session.add(friendship)
            self.db.session.commit()
            self.db.session.refresh(friendship)
            return friendship

    def _remove_db_friendship(self, user_obj_1, user_obj_2):
        with self.app.app_context():
            friendship = Friendship.query.filter(
                ((Friendship.user_id == user_obj_1.id) & (Friendship.friend_id == user_obj_2.id)) |
                ((Friendship.user_id == user_obj_2.id) & (Friendship.friend_id == user_obj_1.id))
            ).first()
            if friendship:
                self.db.session.delete(friendship)
                self.db.session.commit()
