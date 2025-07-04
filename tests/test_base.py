import os
import sys
import unittest
import json
import io
import time
from unittest.mock import patch, call, ANY

# Updated imports for the new app structure
from social_app import create_app, db as app_db, socketio as main_app_socketio
from flask import url_for, Response
import flask

from flask_jwt_extended import JWTManager
from flask_restful import Api

# from models import db as app_db # app_db is now imported from social_app
from social_app.models.db_models import ( # Updated model import paths
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
)
# app_db is already imported from social_app, so no separate import for it from models needed.
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash


class AppTestCase(unittest.TestCase):
    app = None
    db = None
    socketio_class_level = None

    @classmethod
    def setUpClass(cls):
        # Create an app instance for testing
        cls.app = create_app('testing') # Assuming a 'testing' config or modify create_app
        # cls.app.config["SERVER_NAME"] = "localhost" # Usually set by testing config
        # cls.app.config["APPLICATION_ROOT"] = "/"
        cls.app.config["PREFERRED_URL_SCHEME"] = "http"
        cls.app.config["SESSION_COOKIE_NAME"] = "session"
        cls.app.config["SESSION_COOKIE_DOMAIN"] = "localhost"
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        # cls.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test_site.db" # Set in testing config
        # cls.app.config["SECRET_KEY"] = "test-secret-key" # Set in testing config
        # cls.app.config["JWT_SECRET_KEY"] = "test-jwt-secret-key" # Set in testing config
        # cls.app.config["SOCKETIO_MESSAGE_QUEUE"] = None # Set in testing config

        # Ensure SHARED_FILES_UPLOAD_FOLDER is set for tests if not in default testing config
        shared_folder_path = cls.app.config.setdefault("SHARED_FILES_UPLOAD_FOLDER", "shared_files_test_folder")
        if not os.path.exists(shared_folder_path):
            os.makedirs(shared_folder_path)

        # cls.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False # Set in testing config
        cls.db = app_db # app_db is imported from social_app

        # SocketIO is initialized within create_app. We use the instance from social_app.
        # No need to call init_app() on main_app_socketio again here.
        cls.socketio_class_level = main_app_socketio

        # Configure logging for tests
        import logging

        cls.app.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        for h_ in cls.app.logger.handlers:
            cls.app.logger.removeHandler(h_)
        cls.app.logger.addHandler(handler)
        cls.app.logger.propagate = False
        logging.getLogger("socketio").setLevel(logging.DEBUG)
        logging.getLogger("engineio").setLevel(logging.DEBUG)

        # Api is initialized in create_app, no need to handle it here.

        with cls.app.app_context():
            cls.db.create_all()

        # Ensure the test client uses the app's test config for cookies, etc.
        # This is usually handled by app.test_client() itself.

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.db.drop_all()

    def setUp(self):
        self.client = self.app.test_client()
        assert (
            self.socketio_class_level is not None
        ), "socketio_class_level is None in setUp instance method!"
        self.socketio_client = self.socketio_class_level.test_client(
            self.app, flask_test_client=self.client
        )
        if self.socketio_client.is_connected(namespace="/"):
            self.socketio_client.disconnect(namespace="/")
        with self.app.app_context():
            self._clean_tables_for_setup()
            self._setup_base_users()

    def _clean_tables_for_setup(self):
        self.db.session.remove()
        self.db.drop_all()
        self.db.create_all()

    def tearDown(self):
        if hasattr(self, "socketio_client") and self.socketio_client:
            if self.socketio_client.is_connected():
                client_sid = getattr(
                    self.socketio_client, "sid", "N/A (sid missing despite connected)"
                )
                print(
                    f"Disconnecting Flask-SocketIO test_client in tearDown. SID: {client_sid}",
                    file=sys.stderr,
                )
                self.socketio_client.disconnect()
                print(
                    "Flask-SocketIO test_client disconnected in tearDown.",
                    file=sys.stderr,
                )
            # Removed the else block that printed "Flask-SocketIO test_client existed in tearDown but was not connected."
        else:
            print("No socketio_client found in tearDown.", file=sys.stderr)

        with self.app.app_context():
            self.db.session.remove()
        shared_files_folder = self.app.config.get("SHARED_FILES_UPLOAD_FOLDER")
        if shared_files_folder and os.path.exists(shared_files_folder):
            for filename in os.listdir(shared_files_folder):
                file_path = os.path.join(shared_files_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}")

    def _setup_base_users(self):
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
        self.db.session.add_all([self.user1, self.user2, self.user3])
        self.db.session.commit()
        self.db.session.refresh(self.user1)
        self.db.session.refresh(self.user2)
        self.db.session.refresh(self.user3)
        self.user1_id = self.user1.id
        self.user2_id = self.user2.id
        self.user3_id = self.user3.id

    def login(self, username, password, client_instance=None):
        # Use the standard Flask test client to log in, which sets the session cookie
        login_response = self.client.post(
            "/login",
            data=dict(username=username, password=password),
            follow_redirects=True,
        )
        self.assertEqual(login_response.status_code, 200)
        # Verify that 'user_id' is in the session after login via HTTP client
        with self.client.session_transaction() as http_session:
            self.assertIn(
                "user_id", http_session, "user_id not in session after HTTP login."
            )
            # Removed debug print statement about user session

        socketio_client_to_use = (
            client_instance if client_instance else self.socketio_client
        )

        # Disconnect if already connected, to ensure a fresh connection attempt
        if socketio_client_to_use.is_connected(namespace="/"):
            # Removed debug print statement about disconnecting existing socketio_client
            socketio_client_to_use.disconnect(namespace="/")
            time.sleep(0.2)  # Short delay for disconnect to process

        # The SocketIO test client, when initialized with the Flask test client,
        # should automatically use the cookies from the Flask test client's cookie jar.
        # No explicit headers with cookies should be needed here.
        # Removed debug print statement about attempting SocketIO connect
        socketio_client_to_use.connect(namespace="/")  # Removed headers=connect_headers

        # Increased sleep and retry logic for SID acquisition
        time.sleep(0.5)
        retry_count = 0
        max_retries = 30  # Increased max_retries
        wait_interval = 0.2  # Slightly longer wait interval

        while (
            not getattr(socketio_client_to_use, "sid", None)
            and retry_count < max_retries
        ):
            time.sleep(wait_interval)
            retry_count += 1
            if not socketio_client_to_use.is_connected(
                namespace="/"
            ) and retry_count < (max_retries / 2):
                # Removed debug print statement about SocketIO client not connected during SID wait
                socketio_client_to_use.connect(namespace="/")
                time.sleep(0.5)

        if not getattr(socketio_client_to_use, "sid", None):
            eio_sid_val = "N/A"
            if (
                hasattr(socketio_client_to_use, "eio_test_client")
                and socketio_client_to_use.eio_test_client
            ):
                eio_sid_val = getattr(
                    socketio_client_to_use.eio_test_client,
                    "sid",
                    "N/A (eio_test_client has no sid)",
                )
            is_connected_status = socketio_client_to_use.is_connected(namespace="/")
            # Removed debug print statement about SocketIO client failed to get SID
            # Log session state from the server side perspective during the failing connect attempt
            with self.app.test_request_context(
                "/socket.io"
            ):  # Simulate a socket.io context for session access
                # Removed debug print statement about Flask session state during SID failure
                pass

            raise ConnectionError(
                f"SocketIO client for {username} failed to get SID after waiting. "
                f"is_connected: {is_connected_status}, sid: None, eio_sid: {eio_sid_val}. "
                "Ensure session cookie is correctly passed and processed by SocketIO server-side authentication."
            )

        # Removed debug print statement about SocketIO client connected with SID
        return login_response  # Return the HTTP login response

    def logout(self, client_instance=None):
        http_client = self.client
        socket_client_to_disconnect = (
            client_instance
            if client_instance
            else getattr(self, "socketio_client", None)
        )
        if (
            socket_client_to_disconnect
            and hasattr(socket_client_to_disconnect, "is_connected")
            and socket_client_to_disconnect.is_connected()
        ):
            socket_client_to_disconnect.disconnect()
        response = http_client.get("/logout", follow_redirects=True)
        self.assertEqual(response.status_code, 200, "HTTP Logout failed")
        return response

    def _create_db_message(
        self, sender_id, receiver_id, content, timestamp=None, is_read=False
    ):
        with self.app.app_context():
            msg = Message(
                sender_id=sender_id,
                receiver_id=receiver_id,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
                is_read=is_read,
            )
            self.db.session.add(msg)
            self.db.session.commit()
            return msg

    def _get_jwt_token(self, username, password):
        response = self.client.post(
            "/api/login", json={"username": username, "password": password}
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
        with self.app.app_context():
            group = Group(name=name, description=description, creator_id=creator_id)
            self.db.session.add(group)
            self.db.session.commit()
            return self.db.session.get(Group, group.id)

    def _create_db_event(
        self,
        user_id,
        title="Test Event",
        description="An event for testing",
        date_str="2024-12-31",
        time_str="18:00",
        location="Test Location",
        created_at=None,
    ):
        with self.app.app_context():
            event_datetime_obj = datetime.strptime(
                f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
            )
            event = Event(
                user_id=user_id,
                title=title,
                description=description,
                date=event_datetime_obj,
                location=location,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(event)
            self.db.session.commit()
            return self.db.session.get(Event, event.id)

    def _create_db_poll(
        self, user_id, question="Test Poll?", options_texts=None, created_at=None
    ):
        if options_texts is None:
            options_texts = ["Option 1", "Option 2"]
        with self.app.app_context():
            poll = Poll(
                user_id=user_id,
                question=question,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(poll)
            self.db.session.commit()
            for text in options_texts:
                option = PollOption(text=text, poll_id=poll.id)
                self.db.session.add(option)
            self.db.session.commit()
            return self.db.session.get(Poll, poll.id)

    def _create_db_post(
        self, user_id, title="Test Post", content="Test Content", timestamp=None
    ):
        with self.app.app_context():
            post = Post(
                user_id=user_id,
                title=title,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(post)
            self.db.session.commit()
            return self.db.session.get(Post, post.id)

    def _create_db_like(self, user_id, post_id, timestamp=None):
        from social_app.models.db_models import Like # Corrected import

        with self.app.app_context():
            like = Like(
                user_id=user_id,
                post_id=post_id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(like)
            self.db.session.commit()
            return like

    def _create_db_comment(
        self, user_id, post_id, content="Test comment", timestamp=None
    ):
        from social_app.models.db_models import Comment # Corrected import

        with self.app.app_context():
            comment = Comment(
                user_id=user_id,
                post_id=post_id,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(comment)
            self.db.session.commit()
            return comment

    def _create_db_event_rsvp(
        self, user_id, event_id, status="Attending", timestamp=None
    ):
        from social_app.models.db_models import EventRSVP # Corrected import

        with self.app.app_context():
            rsvp = EventRSVP(
                user_id=user_id,
                event_id=event_id,
                status=status,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(rsvp)
            self.db.session.commit()
            return rsvp.id

    def _create_db_poll_vote(self, user_id, poll_id, poll_option_id, created_at=None):
        from social_app.models.db_models import PollVote # Corrected import

        with self.app.app_context():
            vote = PollVote(
                user_id=user_id,
                poll_id=poll_id,
                poll_option_id=poll_option_id,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(vote)
            self.db.session.commit()
            return vote.id

    def _create_series(
        self,
        user_id,
        title="Test Series",
        description="A series for testing.",
        created_at=None,
        updated_at=None,
    ):  # This seems to be a duplicate of _create_db_series
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
        from social_app.models.db_models import PostLock # Corrected import

        with self.app.app_context():
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes_offset)
            lock = PostLock(post_id=post_id, user_id=user_id, expires_at=expires_at)
            self.db.session.add(lock)
            self.db.session.commit()
            return self.db.session.get(PostLock, lock.id)

    def _create_db_user(self, username, password="password", email=None, role="user"):
        if email is None:
            email = f"{username}@example.com"
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
        )
        self.db.session.add(user)
        self.db.session.commit()
        self.db.session.refresh(user)
        return user

    def _create_db_series(
        self,
        user_id,
        title="Test Series",
        description="A series for testing.",
        created_at=None,
        updated_at=None,
    ):
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
        from social_app.models.db_models import Bookmark # Corrected import

        with self.app.app_context():
            bookmark = Bookmark(
                user_id=user_id,
                post_id=post_id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(bookmark)
            self.db.session.commit()
            return bookmark

    def _create_db_block(self, blocker_user_obj, blocked_user_obj, timestamp=None):
        from social_app.models.db_models import UserBlock # Corrected import

        with self.app.app_context():
            block = UserBlock(
                blocker_id=blocker_user_obj.id,
                blocked_id=blocked_user_obj.id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(block)
            self.db.session.commit()
            return block.id

    def _create_db_friendship(
        self, user_obj_1, user_obj_2, status="accepted", timestamp=None
    ):
        with self.app.app_context():
            friendship = Friendship(
                user_id=user_obj_1.id,
                friend_id=user_obj_2.id,
                status=status,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(friendship)
            self.db.session.commit()
            self.db.session.refresh(friendship)
            return friendship

    def _remove_db_friendship(self, user_obj_1, user_obj_2):
        with self.app.app_context():
            friendship = Friendship.query.filter(
                (
                    (Friendship.user_id == user_obj_1.id)
                    & (Friendship.friend_id == user_obj_2.id)
                )
                | (
                    (Friendship.user_id == user_obj_2.id)
                    & (Friendship.friend_id == user_obj_1.id)
                )
            ).first()
            if friendship:
                self.db.session.delete(friendship)
                self.db.session.commit()
