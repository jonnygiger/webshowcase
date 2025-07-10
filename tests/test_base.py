import os
import sys
import unittest
import json
import io
import time
import threading
from unittest.mock import patch, call, ANY
# from flask_socketio import SocketIOTestClient # Removed

from social_app import create_app, db as app_db #, socketio as main_app_socketio # Removed
from flask import url_for, Response
import flask

from flask_jwt_extended import JWTManager
from flask_restful import Api

from social_app.models.db_models import (
    Achievement,
    Bookmark,
    Comment,
    Event,
    EventRSVP,
    FriendPostNotification,
    Friendship,
    Group,
    Like,
    Message,
    Notification,
    Poll,
    PollOption,
    PollVote,
    Post,
    PostLock,
    Series,
    SeriesPost,
    SharedFile,
    TrendingHashtag,
    User,
    UserAchievement,
    UserBlock,
    UserStatus,
)
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash


class AppTestCase(unittest.TestCase):
    app = None
    db = None
    # socketio_class_level = None # Removed

    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.db = app_db
        # cls.socketio_class_level = main_app_socketio # Removed

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
        # logging.getLogger("socketio").setLevel(logging.DEBUG) # Removed
        # logging.getLogger("engineio").setLevel(logging.DEBUG) # Removed

        with cls.app.app_context():
            cls.db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.db.drop_all()

    def setUp(self):
        """
        Set up the test environment before each test case.
        Initializes the Flask test client.
        It cleans all database tables and sets up base users.
        """
        self.client = self.app.test_client()

        # All SocketIO client related setup is removed.

        # Prepare database: clean tables and set up base users
        with self.app.app_context():
            self._clean_tables_for_setup()
            self._setup_base_users()

    def _clean_tables_for_setup(self):
        self.db.session.remove()
        for table in reversed(self.db.metadata.sorted_tables):
            self.db.session.execute(table.delete())
        self.db.session.commit()

    def tearDown(self):
        """
        Clean up the test environment after each test case.
        Rolls back any pending database transactions and removes the session.
        Deletes any files created in the shared files upload folder during tests.
        """
        # All SocketIO client related teardown is removed.

        # Clean up database session
        with self.app.app_context():
            self.db.session.rollback() # Rollback any uncommitted transactions
            self.db.session.remove()

        shared_files_folder = self.app.config.get("SHARED_FILES_UPLOAD_FOLDER")
        if shared_files_folder and os.path.exists(shared_files_folder):
            for filename in os.listdir(shared_files_folder):
                file_path = os.path.join(shared_files_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    self.app.logger.error(f"Failed to delete {file_path} in tearDown. Reason: {e}")

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

    # Removed _ensure_socketio_disconnected
    # Removed _clear_socketio_events

    def login(self, username, password, client_instance=None): # client_instance is no longer used
        """
        Handles the HTTP session login for a user.
        JWT token retrieval is kept as it might be used by other API endpoints.

        Args:
            username (str): The username to log in with.
            password (str): The password for the user.
            client_instance: This argument is no longer used.

        Returns:
            flask.Response: The response object from the initial HTTP POST to /login.
        """
        # Step 1: Perform standard HTTP form login to establish a Flask session.
        self.app.logger.info(f"Initiating HTTP login for user '{username}'.")
        login_response = self.client.post(
            "/login",
            data=dict(username=username, password=password),
            follow_redirects=True,
        )
        self.assertEqual(login_response.status_code, 200, f"HTTP login failed for '{username}': {login_response.data.decode()}")
        with self.client.session_transaction() as http_session: # Verify Flask session
            self.assertIn("_user_id", http_session, f"'_user_id' not found in session after HTTP login for '{username}'.")
        self.app.logger.info(f"HTTP login successful for '{username}', Flask session created.")

        # Step 2: Obtain a JWT token. This is kept as JWTs might be used for non-SocketIO API auth.
        self.app.logger.debug(f"Fetching JWT token for '{username}' (potentially for API use).")
        jwt_token = self._get_jwt_token(username, password)

        self.app.logger.info(f"HTTP login for '{username}' completed.")
        return login_response

    def logout(self, client_instance=None, username_for_log=None): # client_instance is no longer used
        """
        Logs out the user by clearing the HTTP session.

        Args:
            client_instance: This argument is no longer used.
            username_for_log (str, optional): An optional username string to make log
                                              messages more descriptive.
        Returns:
            flask.Response: The response object from the HTTP GET request to /logout.
        """
        http_client = self.client

        user_context_log = f"for '{username_for_log}'" if username_for_log else "for current user"
        self.app.logger.info(f"Logout process: Performing HTTP session logout {user_context_log}.")
        response = http_client.get("/logout", follow_redirects=True)
        self.assertEqual(response.status_code, 200, f"HTTP Logout failed {user_context_log}: {response.data.decode()}")
        self.app.logger.info(f"HTTP session logout successful {user_context_log}.")

        with http_client.session_transaction() as http_session:
            if "_user_id" in http_session:
                self.app.logger.warning(f"Session check: '_user_id' still found in session after HTTP logout {user_context_log}. This might indicate an issue with server-side session clearing.")
            else:
                self.app.logger.debug(f"Session check: '_user_id' confirmed removed after HTTP logout {user_context_log}.")

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
        with self.app.app_context():
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

    # _wait_for_socketio_event method was here. It has been removed as it's no longer used.
