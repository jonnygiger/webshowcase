import os
import sys
import unittest
import json
import io
import time
import threading
from unittest.mock import patch, call, ANY

from social_app import create_app, db as app_db, socketio as main_app_socketio
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
    socketio_class_level = None

    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.db = app_db
        cls.socketio_class_level = main_app_socketio

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

        with cls.app.app_context():
            cls.db.create_all()

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
        for table in reversed(self.db.metadata.sorted_tables):
            self.db.session.execute(table.delete())
        self.db.session.commit()

    def tearDown(self):
        if hasattr(self, "socketio_client") and self.socketio_client:
            if self.socketio_client.is_connected():
                client_sid = getattr(self.socketio_client, "sid", None)
                if client_sid:
                    print(
                        f"Disconnecting Flask-SocketIO test_client in tearDown. SID: {client_sid}",
                        file=sys.stderr,
                    )
                    self.socketio_client.disconnect()
                    print(
                        "Flask-SocketIO test_client disconnected in tearDown.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        "Flask-SocketIO test_client in tearDown: connected but SID missing. Attempting disconnect.",
                        file=sys.stderr,
                    )
                    self.socketio_client.disconnect()
                    print(
                        "Flask-SocketIO test_client (attempted) disconnected in tearDown.",
                        file=sys.stderr,
                    )
            else:
                print(
                    "Flask-SocketIO test_client in tearDown: was already disconnected.",
                    file=sys.stderr,
                )
        else:
            print("No socketio_client found or set in tearDown.", file=sys.stderr)

        with self.app.app_context():
            self.db.session.rollback()
            self.db.session.remove()

        shared_files_folder = self.app.config.get("SHARED_FILES_UPLOAD_FOLDER")
        if shared_files_folder and os.path.exists(shared_files_folder):
            for filename in os.listdir(shared_files_folder):
                file_path = os.path.join(shared_files_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}", file=sys.stderr)

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
        # Perform standard HTTP login first to establish session
        login_response = self.client.post(
            "/login",
            data=dict(username=username, password=password),
            follow_redirects=True,
        )
        self.assertEqual(login_response.status_code, 200)
        with self.client.session_transaction() as http_session:
            self.assertIn("_user_id", http_session)

        # Then, get the JWT token for SocketIO authentication
        # This token is obtained by calling /api/login which is separate from the /login above
        jwt_token = self._get_jwt_token(username, password)

        socketio_client_to_use = (
            client_instance if client_instance else self.socketio_client
        )

        if socketio_client_to_use.is_connected(namespace="/"):
            self.app.logger.debug(f"SocketIO client for {username} already connected, disconnecting before reconnecting with token.")
            socketio_client_to_use.disconnect(namespace="/")
            time.sleep(0.2) # Give a moment for disconnect to process

        # Always clear any stale events from previous interactions *before* this new connection attempt.
        # This is important if the client instance is being reused or if an implicit anonymous connection left events.
        self.app.logger.debug(f"SocketIO client for {username}: Clearing pre-existing events before connect call.")
        # Loop to clear out any existing events from the socketio_client_to_use
        self.app.logger.debug(f"SocketIO client for {username}: Starting pre-connection event clearing loop.")
        for i in range(5): # Try up to 5 times
            if not socketio_client_to_use.is_connected(namespace="/"):
                self.app.logger.debug(f"SocketIO client for {username}: Not connected (attempt {i+1}), so no pre-existing events to clear from server.")
                break
            try:
                # Attempt to get received events. If the client is connected but the queue is empty, it returns an empty list.
                events = socketio_client_to_use.get_received(namespace="/")
                if not events:
                    self.app.logger.debug(f"SocketIO client for {username}: Event queue cleared on attempt {i+1}.")
                    break
                self.app.logger.debug(f"SocketIO client for {username}: Drained {len(events)} events on attempt {i+1}, checking again.")
                # time.sleep(0.01) # Small delay if events were found - consider if this sleep is truly needed or if it slows down tests.
                                 # For now, let's keep it to match original behavior if events are drained.
                if len(events) > 0: # Only sleep if we actually processed events
                    time.sleep(0.01)

            except RuntimeError as e: # Catch 'not connected' if is_connected() was true but then it disconnected.
                self.app.logger.warning(f"SocketIO client for {username}: Error '{e}' during pre-event clearing on attempt {i+1}. Assuming disconnected.")
                break
        else: # Executed if the loop completed without breaking (i.e., events were found each time for 5 attempts)
            # This 'else' block runs if the loop finished normally (didn't break).
            # We should check connection status before logging a warning.
            if socketio_client_to_use.is_connected(namespace="/"):
                # If still connected and loop finished, it means events were received each time.
                self.app.logger.warning(f"SocketIO client for {username}: Event queue still had events after 5 clearing attempts (client still connected).")
            else:
                # If not connected and loop finished, it means it likely disconnected during one of the attempts.
                self.app.logger.info(f"SocketIO client for {username}: Event clearing loop finished; client was or became disconnected during the attempts.")
        self.app.logger.debug(f"SocketIO client for {username}: Finished pre-connection event clearing loop.")


        # Connect SocketIO client with JWT token
        self.app.logger.info(f"SocketIO client for {username} attempting to connect with JWT token.")
        socketio_client_to_use.connect(namespace="/", auth={'token': jwt_token}, headers={'Authorization': f'Bearer {jwt_token}'})

        # Events received immediately upon connection will now be processed by the auth checking loop.
        start_time = time.time()
        timeout_seconds = 10
        auth_successful = False
        auth_error_message = None

        while time.time() - start_time < timeout_seconds:
            try:
                received_events = socketio_client_to_use.get_received(namespace="/") # Short timeout for non-blocking check
                for event in received_events:
                    event_name = event.get('name')
                    event_args = event.get('args')
                    self.app.logger.debug(f"SocketIO event received for {username}: Name: {event_name}, Args: {event_args}")

                    if event_name == 'confirm_namespace_connected':
                        # Check if the event is for the current connection attempt and status is authenticated
                        if event_args and event_args[0].get('status') == 'authenticated':
                            self.app.logger.info(f"SocketIO 'confirm_namespace_connected' (authenticated) received for {username} (Attempt specific).")
                            auth_successful = True
                            break
                        elif event_args: # Log if 'confirm_namespace_connected' is received but not authenticated
                            self.app.logger.warning(f"SocketIO 'confirm_namespace_connected' received for {username} but status was not 'authenticated': {event_args[0].get('status')}")
                    elif event_name == 'auth_error':
                        # This event indicates a failure for the current connection attempt
                        self.app.logger.error(f"SocketIO 'auth_error' received for {username}: {event_args} (Attempt specific).")
                        auth_error_message = event_args[0].get('message', str(event_args[0])) if event_args and event_args[0] else "Unknown authentication error"
                        break
                    # Other events can be logged but might not terminate the loop unless they signify a different problem.

                if auth_successful or auth_error_message: # If auth success or a specific auth error for this attempt, exit loop.
                    break
            except Exception as e: # get_received might raise if client disconnects unexpectedly
                self.app.logger.error(f"Error while getting received events for {username}: {e}")
                # Potentially treat as a connection failure, especially if it's persistent.
                break # Exit loop on error to avoid busy-looping on a broken client.
            time.sleep(0.05) # Small delay to prevent busy-waiting

        current_sid = getattr(socketio_client_to_use, "sid", None)

        if auth_error_message:
            self.app.logger.error(f"SocketIO authentication failed for {username}: {auth_error_message}")
            raise ConnectionError(f"SocketIO authentication failed: {auth_error_message}")
        elif not auth_successful:
            eio_sid_val = "N/A"
            if hasattr(socketio_client_to_use, 'eio_test_client') and socketio_client_to_use.eio_test_client:
                eio_sid_val = getattr(socketio_client_to_use.eio_test_client, 'sid', "N/A (eio_test_client has no sid)")
            is_connected_status = socketio_client_to_use.is_connected(namespace="/")
            error_message = (
                f"SocketIO connection attempt for {username} timed out after {timeout_seconds}s "
                f"without successful 'confirm_namespace_connected' or 'auth_error'. "
                f"is_connected: {is_connected_status}, current_sid: {current_sid}, eio_sid: {eio_sid_val}."
            )
            self.app.logger.error(error_message)
            raise ConnectionError(error_message)
        elif not current_sid:
            error_message = (
                f"SocketIO client for {username} authenticated but SID is missing. "
                "This indicates a potential issue with the connection process or client state."
            )
            self.app.logger.error(error_message)
            raise ConnectionError(error_message)
        else:
            self.app.logger.info(f"SocketIO client for {username} connected successfully with SID: {current_sid}. Authentication successful.")
        return login_response

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
