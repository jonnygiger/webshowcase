import os
import unittest
import json  # For checking JSON responses
import io  # For BytesIO
from unittest.mock import patch, call, ANY
from flask_socketio import SocketIO # Keep this if cls.socketio is re-initialized
# Import the main app instance
from app import app as main_app
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
from datetime import datetime, timedelta
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
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        cls.app.config["SECRET_KEY"] = "test-secret-key"
        cls.app.config["JWT_SECRET_KEY"] = "test-jwt-secret-key"  # Added as per requirements
        cls.app.config["SERVER_NAME"] = "localhost.test" # Added to allow _external=True for url_for
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

        # Initialize SocketIO with the test app
        # Store the SocketIO object at class level
        cls.socketio_class_level = SocketIO(cls.app,
                                            message_queue=cls.app.config["SOCKETIO_MESSAGE_QUEUE"],
                                            manage_session=False) # Good for tests
        assert cls.socketio_class_level is not None, "socketio_class_level is None in setUpClass!"

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
        self.socketio_client = self.socketio_class_level.test_client(self.app)

        with self.app.app_context(): # Use the class's app instance for context
            self._clean_tables_for_setup()
            self._setup_base_users()  # This would require live User model and db session
        # pass

    def _clean_tables_for_setup(self):
        """Clears data from tables before each test's user setup."""
        # Use the class's db instance
        self.db.session.remove()
        for table in reversed(self.db.metadata.sorted_tables):
            self.db.session.execute(table.delete())
        self.db.session.commit()
        # pass

    def tearDown(self):
        """Executed after each test."""
        with self.app.app_context(): # Ensure app context for DB operations
            # Use the class's db instance
            self.db.session.remove()
            for table in reversed(self.db.metadata.sorted_tables):
                self.db.session.execute(table.delete())
            self.db.session.commit()

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
                timestamp=timestamp or datetime.utcnow(),
            )
            self.db.session.add(post) # Use class's db
            self.db.session.commit() # Use class's db
            _ = post.id # Ensure ID is loaded
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

    def login(self, username, password):
        return self.client.post(
            "/login",
            data=dict(username=username, password=password),
            follow_redirects=True,
        )

    def logout(self):
        return self.client.get("/logout", follow_redirects=True)

    def _create_db_message(
        self, sender_id, receiver_id, content, timestamp=None, is_read=False
    ):
        # Requires live Message model and db session
        with self.app.app_context(): # Ensure app context for DB operations
            msg = Message(
                sender_id=sender_id,
                receiver_id=receiver_id,
                content=content,
                timestamp=timestamp or datetime.utcnow(),
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
            return group

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
                created_at=created_at or datetime.utcnow(),
            )
            self.db.session.add(event) # Use class's db
            self.db.session.commit() # Use class's db
            _ = event.id # Ensure ID is loaded
            return event

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
                created_at=created_at or datetime.utcnow(),
            )
            self.db.session.add(poll) # Use class's db
            self.db.session.commit()  # Commit to get poll.id, use class's db
            for text in options_texts:
                option = PollOption(text=text, poll_id=poll.id)
                self.db.session.add(option) # Use class's db
            self.db.session.commit() # Use class's db
            _ = poll.id # Ensure ID is loaded
            # Also ensure options are loaded if they are accessed via poll.options in tests
            _ = [opt.id for opt in poll.options]
            return poll

    def _create_db_like(self, user_id, post_id, timestamp=None):
        from models import Like  # Local import to avoid circular if not using live DB

        with self.app.app_context(): # Ensure app context for DB operations
            like = Like(
                user_id=user_id, post_id=post_id, timestamp=timestamp or datetime.utcnow()
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
                timestamp=timestamp or datetime.utcnow(),
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
                timestamp=timestamp or datetime.utcnow(),
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
                created_at=created_at or datetime.utcnow(),
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
                created_at=created_at or datetime.utcnow(),
                updated_at=updated_at or datetime.utcnow(),
            )
            self.db.session.add(series) # Use class's db
            self.db.session.commit() # Use class's db
            return series

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
            expires_at = datetime.utcnow() + timedelta(minutes=minutes_offset)
            lock = PostLock(post_id=post_id, user_id=user_id, expires_at=expires_at)
            self.db.session.add(lock) # Use class's db
            self.db.session.commit() # Use class's db
            return lock
