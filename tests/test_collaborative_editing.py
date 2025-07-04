import unittest
import json
import time  # Import the time module
from unittest.mock import patch, call, ANY, MagicMock  # Added MagicMock here
from datetime import datetime, timedelta, timezone

from social_app import db, socketio, create_app
from social_app.models.db_models import Post, User, PostLock  # Import PostLock for querying
from tests.test_base import AppTestCase
import logging  # Add logging import


class TestCollaborativeEditing(AppTestCase):
    # _create_db_post and _create_db_lock are in AppTestCase

    def setUp(self):
        # super().setUp() creates self.app using create_app('testing')
        super().setUp()

        # Explicitly set logger level for the app logger to DEBUG
        self.app.logger.setLevel(logging.DEBUG)
        if not any(
            isinstance(handler, logging.StreamHandler)
            for handler in self.app.logger.handlers
        ):
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.DEBUG)
            self.app.logger.addHandler(stream_handler)

        self.post_author = self.user1
        self.collaborator = self.user2
        self.another_user = self.user3

        # Create a real post using the helper from AppTestCase
        self.test_post = self._create_db_post(
            user_id=self.post_author.id,
            title="Collaborative Post",
            content="Initial content.",
        )

        # Re-initialize SocketIO test client, ensuring it shares cookies with self.client
        if self.socketio_client and self.socketio_client.connected:
            self.socketio_client.disconnect()

        # self.socketio is the instance from social_app, self.socketio_class_level is the one from test_base
        self.socketio_client = self.socketio_class_level.test_client(
            self.app, flask_test_client=self.client
        )
        self.assertTrue(
            self.socketio_client.is_connected(),
            "SocketIO client failed to connect in setUp.",
        )

    def tearDown(self):
        if (
            self.socketio_client and self.socketio_client.is_connected()
        ):  # Check is_connected() not just connected
            self.socketio_client.disconnect()
        super().tearDown()

    # --- Model Tests ---
    def test_post_lock_creation(self):
        with self.app.app_context():
            # self.test_post might be from a different session, re-fetch or merge.
            test_post_merged = self.db.session.merge(self.test_post)
            lock = self._create_db_lock(
                post_id=test_post_merged.id,
                user_id=self.post_author.id,
                minutes_offset=15,
            )
            self.assertIsNotNone(lock, "Lock object should not be None.")
            self.assertIsNotNone(
                lock.id, "Lock ID should not be None after creation and re-fetch."
            )  # ID should be populated by _create_db_lock now
            self.assertEqual(lock.post_id, test_post_merged.id)
            self.assertEqual(lock.user_id, self.post_author.id)
            expires_at_aware = lock.expires_at.replace(tzinfo=timezone.utc)
            self.assertTrue(expires_at_aware > datetime.now(timezone.utc))

            # Verify it's in the database again, though _create_db_lock should ensure this
            queried_lock_again = self.db.session.get(PostLock, lock.id)
            self.assertIsNotNone(queried_lock_again)
            self.assertEqual(queried_lock_again.post_id, test_post_merged.id)

    def test_post_is_locked_method(self):
        with self.app.app_context():
            # Ensure self.test_post is managed by the current session
            current_post = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(
                current_post,
                "Test post not found in session at start of test_post_is_locked_method.",
            )

            # 1. Test with no lock
            self.assertFalse(
                current_post.is_locked(), "Post should not be locked if no lock exists."
            )

            # 2. Test with an active lock
            active_lock = self._create_db_lock(
                post_id=current_post.id, user_id=self.post_author.id, minutes_offset=15
            )
            self.db.session.refresh(
                current_post
            )  # Refresh to ensure lock_info is loaded
            self.assertTrue(
                current_post.is_locked(), "Post should be locked with an active lock."
            )

            # 3. Test with an expired lock
            # First, remove the active lock to ensure a clean state for the next check
            merged_active_lock = self.db.session.merge(active_lock)
            self.db.session.delete(merged_active_lock)
            self.db.session.commit()

            self.db.session.refresh(
                current_post
            )  # Refresh to ensure lock_info is cleared
            # Sanity check that it's indeed not locked now
            self.assertFalse(
                current_post.is_locked(),
                "Post should not be locked after deleting the active lock.",
            )

            expired_lock = self._create_db_lock(
                post_id=current_post.id, user_id=self.post_author.id, minutes_offset=-5
            )
            self.db.session.refresh(
                current_post
            )  # Refresh to ensure the new lock_info is loaded
            self.assertFalse(
                current_post.is_locked(),
                "Post should not be locked with an expired lock.",
            )

            # Clean up the expired lock
            merged_expired_lock = self.db.session.merge(expired_lock)
            self.db.session.delete(merged_expired_lock)
            self.db.session.commit()

    # --- API Endpoint Tests (PostLockResource) ---
    def test_api_acquire_lock_success(self):
        token = self._get_jwt_token(self.collaborator.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers
        )
        response_data = json.loads(response.data.decode())

        self.assertEqual(response.status_code, 200, f"Response data: {response_data}")
        self.assertEqual(
            response_data.get("message"), "Post locked successfully."
        )  # Updated expected message
        self.assertIn("lock_details", response_data)
        self.assertEqual(response_data["lock_details"]["post_id"], self.test_post.id)
        # The API returns 'locked_by_user_id' and 'locked_by_username' inside 'lock_details'
        self.assertEqual(
            response_data["lock_details"]["locked_by_user_id"], self.collaborator.id
        )
        self.assertEqual(
            response_data["lock_details"]["locked_by_username"],
            self.collaborator.username,
        )
        self.assertIsNotNone(
            response_data["lock_details"].get("expires_at")
        )  # Check within lock_details

        with self.app.app_context():
            current_post = self.db.session.get(Post, self.test_post.id)  # Re-fetch post
            lock = PostLock.query.filter_by(
                post_id=current_post.id, user_id=self.collaborator.id
            ).first()
            self.assertIsNotNone(lock)
            self.assertTrue(current_post.is_locked())

    def test_api_acquire_lock_conflict(self):
        # User1 (post_author) acquires the lock first
        token_author = self._get_jwt_token(self.post_author.username, "password")
        headers_author = {"Authorization": f"Bearer {token_author}"}
        response_author = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_author
        )
        self.assertEqual(response_author.status_code, 200)

        # User2 (collaborator) attempts to acquire the same lock
        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
        response_collaborator = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )

        self.assertEqual(response_collaborator.status_code, 409)  # Conflict
        response_data = json.loads(response_collaborator.data.decode())
        self.assertEqual(
            response_data.get("message"), "Post is currently locked by another user."
        )
        self.assertEqual(
            response_data.get("locked_by_username"), self.post_author.username
        )

        with self.app.app_context():
            lock = PostLock.query.filter_by(post_id=self.test_post.id).first()
            self.assertIsNotNone(lock)
            self.assertEqual(
                lock.user_id, self.post_author.id
            )  # Still locked by author

    def test_api_release_lock_success(self):
        # Collaborator acquires the lock
        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
        response_acquire = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )
        self.assertEqual(
            response_acquire.status_code,
            200,
            f"Acquire failed: {response_acquire.data.decode()}",
        )

        with self.app.app_context():
            current_post = self.db.session.get(Post, self.test_post.id)  # Re-fetch post
            self.assertIsNotNone(
                current_post,
                "Post not found before checking lock status in release test.",
            )
            self.assertTrue(
                current_post.is_locked(),
                "Post should be locked before release attempt.",
            )

        # Collaborator releases the lock
        response_release = self.client.delete(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )
        response_data = json.loads(response_release.data.decode())

        self.assertEqual(
            response_release.status_code, 200, f"Response data: {response_data}"
        )
        self.assertEqual(
            response_data.get("message"), "Post unlocked successfully."
        )

        with self.app.app_context():
            current_post_after_release = self.db.session.get(
                Post, self.test_post.id
            )
            self.assertIsNotNone(
                current_post_after_release, "Post not found after release attempt."
            )
            lock = PostLock.query.filter_by(
                post_id=current_post_after_release.id
            ).first()
            self.assertIsNone(lock)
            self.assertFalse(current_post_after_release.is_locked())

    def test_api_release_lock_unauthorized(self):
        # Post_author acquires the lock
        token_author = self._get_jwt_token(self.post_author.username, "password")
        headers_author = {"Authorization": f"Bearer {token_author}"}
        response_acquire = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_author
        )
        self.assertEqual(response_acquire.status_code, 200)

        # Collaborator attempts to release the lock
        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
        response_release = self.client.delete(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )

        self.assertEqual(response_release.status_code, 403)  # Forbidden
        response_data = json.loads(response_release.data.decode())
        self.assertEqual(
            response_data.get("message"),
            "You are not authorized to unlock this post as it is locked by another user.",
        )

        with self.app.app_context():
            current_post = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(
                current_post, "Post not found in unauthorized release test."
            )
            lock = PostLock.query.filter_by(post_id=current_post.id).first()
            self.assertIsNotNone(lock)
            self.assertEqual(
                lock.user_id, self.post_author.id
            )
            self.assertTrue(current_post.is_locked())

    def test_api_acquire_lock_unauthenticated(self):
        response = self.client.post(f"/api/posts/{self.test_post.id}/lock")  # No token
        self.assertEqual(response.status_code, 401)
        response_data = json.loads(response.data.decode())
        self.assertIn(
            "Missing Authorization Header", response_data.get("msg", "")
        )

    def test_api_acquire_lock_on_non_existent_post(self):
        token = self._get_jwt_token(self.collaborator.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        non_existent_post_id = 99999

        response = self.client.post(
            f"/api/posts/{non_existent_post_id}/lock", headers=headers
        )
        response_data = json.loads(response.data.decode())

        self.assertEqual(response.status_code, 404, f"Response data: {response_data}")
        self.assertIn(
            "Post not found",
            response_data.get("message", ""),
            "Response message did not indicate post not found.",
        )

    def test_api_lock_expiry_and_reacquire(self):
        token_author = self._get_jwt_token(self.post_author.username, "password")
        headers_author = {"Authorization": f"Bearer {token_author}"}

        response_acquire_author = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_author
        )
        self.assertEqual(
            response_acquire_author.status_code,
            200,
            "Author failed to acquire lock initially.",
        )
        response_data_author = json.loads(response_acquire_author.data.decode())
        self.assertIn("lock_details", response_data_author)
        self.assertIn("locked_by_username", response_data_author["lock_details"])
        self.assertEqual(
            response_data_author["lock_details"]["locked_by_username"],
            self.post_author.username,
        )

        with self.app.app_context():
            current_post_author_lock = self.db.session.get(
                Post, self.test_post.id
            )
            self.assertIsNotNone(
                current_post_author_lock, "Post not found when checking author's lock."
            )
            self.assertTrue(
                current_post_author_lock.is_locked(), "Post should be locked by author."
            )

            lock = PostLock.query.filter_by(
                post_id=self.test_post.id, user_id=self.post_author.id
            ).first()
            self.assertIsNotNone(lock, "Lock not found in database for author.")

            lock.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            self.db.session.add(lock)
            self.db.session.commit()

            current_post_after_expiry = self.db.session.get(
                Post, self.test_post.id
            )
            self.assertIsNotNone(
                current_post_after_expiry,
                "Post not found after simulating lock expiry.",
            )
            self.assertFalse(
                current_post_after_expiry.is_locked(),
                "Post should be unlocked after lock expiry.",
            )

        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}

        response_acquire_collaborator = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )
        self.assertEqual(
            response_acquire_collaborator.status_code,
            200,
            f"Collaborator failed to acquire lock after expiry. Response: {response_acquire_collaborator.data.decode()}",
        )
        response_data_collaborator = json.loads(
            response_acquire_collaborator.data.decode()
        )
        self.assertIn("lock_details", response_data_collaborator)
        self.assertIn("locked_by_username", response_data_collaborator["lock_details"])
        self.assertEqual(
            response_data_collaborator["lock_details"]["locked_by_username"],
            self.collaborator.username,
            "Lock not acquired by collaborator.",
        )

        with self.app.app_context():
            current_post_collaborator_lock = self.db.session.get(
                Post, self.test_post.id
            )
            self.assertIsNotNone(
                current_post_collaborator_lock,
                "Post not found when checking collaborator's lock.",
            )
            self.assertTrue(
                current_post_collaborator_lock.is_locked(),
                "Post should be locked by collaborator.",
            )

            lock_collaborator = PostLock.query.filter_by(
                post_id=current_post_collaborator_lock.id, user_id=self.collaborator.id
            ).first()
            self.assertIsNotNone(
                lock_collaborator, "Lock for collaborator not found in database."
            )
            self.assertEqual(lock_collaborator.user_id, self.collaborator.id)

    @patch("social_app.socketio.emit")
    def test_socketio_edit_post_by_lock_owner(
        self, mock_socketio_emit
    ):
        with self.app.app_context():
            token = self._get_jwt_token(self.collaborator.username, "password")
            headers = {"Authorization": f"Bearer {token}"}
            response_lock = self.client.post(
                f"/api/posts/{self.test_post.id}/lock", headers=headers
            )
            self.assertEqual(
                response_lock.status_code,
                200,
                "Failed to acquire lock for collaborator.",
            )
            mock_socketio_emit.reset_mock()

            self.login(self.collaborator.username, "password")

            if not self.socketio_client or not self.socketio_client.is_connected():
                self.socketio_client = self.socketio_class_level.test_client( # Use test_base's socketio
                    self.app, namespace="/"
                )
                self.assertTrue(self.socketio_client.is_connected("/"))

            edit_data = {
                "post_id": self.test_post.id,
                "new_content": "Updated content by lock owner.",
                "token": token,
            }

            self.socketio_client.emit(
                "edit_post_content", edit_data, namespace="/"
            )
            time.sleep(0.2)

            updated_post = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(
                updated_post,
                "Post could not be re-fetched from DB after SocketIO edit.",
            )
            self.assertEqual(
                updated_post.content,
                edit_data["new_content"],
                "Post content was not updated in the database.",
            )

            expected_broadcast_data = {
                "post_id": self.test_post.id,
                "new_content": edit_data["new_content"],
                "edited_by_user_id": self.collaborator.id,
                "edited_by_username": self.collaborator.username,
                "last_edited": ANY,
            }

            found_call = False
            for call_args_item in mock_socketio_emit.call_args_list:
                event_name_called = call_args_item[0][0]
                event_data_called = call_args_item[0][1]
                event_room_called = call_args_item[1].get("room")

                if (
                    event_name_called == "post_content_updated"
                    and event_room_called == f"post_{self.test_post.id}"
                ):
                    match = True
                    for key, expected_value in expected_broadcast_data.items():
                        if key == "last_edited":
                            if key not in event_data_called:
                                match = False
                                break
                            continue
                        if event_data_called.get(key) != expected_value:
                            match = False
                            break
                    if match:
                        if "last_edited" in event_data_called and isinstance(
                            event_data_called["last_edited"], str
                        ):
                            found_call = True
                            break
                        else:
                            self.app.logger.debug(
                                f"Call matched basic data but 'last_edited' was missing or not a string: {event_data_called}"
                            )

            self.assertTrue(
                found_call,
                f"Expected 'post_content_updated' event with data matching {expected_broadcast_data} "
                f"to room f'post_{self.test_post.id}' not found or 'last_edited' invalid. "
                f"Actual calls: {mock_socketio_emit.call_args_list}",
            )

    @patch("social_app.socketio.emit")
    def test_socketio_edit_post_without_lock(self, mock_emit):
        with self.app.app_context():
            PostLock.query.filter_by(post_id=self.test_post.id).delete()
            self.db.session.commit()

            current_post_state = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(
                current_post_state,
                "Test post not found before edit attempt without lock.",
            )
            self.assertFalse(
                current_post_state.is_locked(),
                "Post should be unlocked at the start of the test.",
            )
            original_content = current_post_state.content

            token_collaborator = self._get_jwt_token(
                self.collaborator.username, "password"
            )
            edit_data = {
                "post_id": self.test_post.id,
                "new_content": "Content edit attempt without lock.",
                "token": token_collaborator,
            }

            if self.socketio_client and self.socketio_client.connected:
                self.socketio_client.disconnect()
            self.socketio_client = self.socketio_class_level.test_client( # Use test_base's socketio
                self.app, flask_test_client=self.client
            )
            self.assertTrue(
                self.socketio_client.is_connected(),
                "SocketIO client failed to connect for edit attempt.",
            )

            self.socketio_client.get_received()
            self.socketio_client.emit("edit_post_content", edit_data)

            time.sleep(0.5)

            found_edit_error_call = False
            received_error_message = None
            all_server_emits = mock_emit.call_args_list

            self.app.logger.debug(
                f"Test '{self.id()}': Checking server emits for 'edit_error'. All mock_emit calls: {all_server_emits}"
            )

            for call_args_item in all_server_emits:
                event_name = call_args_item[0][0]
                if event_name == "edit_error":
                    error_data_emitted = call_args_item[0][1]
                    received_error_message = error_data_emitted.get("message")
                    self.app.logger.debug(
                        f"Test '{self.id()}': Found 'edit_error' emit. Data: {error_data_emitted}, Room: {call_args_item[1].get('room')}, Expected SID for comparison: {self.socketio_client.sid}"
                    )

                    if (
                        received_error_message
                        == "Post is not locked for editing. Please acquire a lock first."
                    ):
                        found_edit_error_call = True
                        break
                    elif "Token error" in (
                        received_error_message or ""
                    ) or "Authentication required" in (received_error_message or ""):
                        self.app.logger.warning(
                            f"Test '{self.id()}': Received an auth-related 'edit_error': '{received_error_message}' instead of 'not locked' error. This indicates the SID/auth issue is primary."
                        )

            self.assertTrue(
                found_edit_error_call,
                f"'edit_error' with message 'Post is not locked for editing. Please acquire a lock first.' not found or not correctly targeted. "
                f"Last received 'edit_error' message (if any): '{received_error_message}'. All server calls: {all_server_emits}",
            )

            post_after_attempt = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(
                post_after_attempt, "Post not found after edit attempt."
            )
            self.assertEqual(
                post_after_attempt.content,
                original_content,
                "Post content should not have changed.",
            )

            all_calls = mock_emit.call_args_list # Use the correct mock name
            for call_args_item in all_calls:
                event_name_called = call_args_item[0][0]
                # Check if it's a broadcast by checking if the room is NOT the client's SID
                # This logic is a bit indirect; ideally, broadcasts don't specify a room or use a general room.
                is_broadcast_like = call_args_item[1].get("room") != self.socketio_client.sid

                if event_name_called == "post_content_updated" and is_broadcast_like:
                    self.fail(
                        f"'post_content_updated' should not have been broadcast. Calls: {all_calls}"
                    )


    @patch("social_app.socketio.emit")
    def test_socketio_lock_acquired_broadcast_from_api(
        self, mock_socketio_emit
    ):
        token = self._get_jwt_token(self.collaborator.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers
        )

        self.assertEqual(
            response.status_code,
            200,
            f"Failed to acquire lock: {response.data.decode()}",
        )
        time.sleep(0.1)

        expected_data = {
            "post_id": self.test_post.id,
            "user_id": self.collaborator.id,
            "username": self.collaborator.username,
            "expires_at": ANY,
        }
        expected_room = f"post_{self.test_post.id}"

        self.assertEqual(
            mock_socketio_emit.call_count,
            1,
            f"Expected emit to be called once. Actual calls: {mock_socketio_emit.call_args_list}",
        )

        actual_call = mock_socketio_emit.call_args_list[0]

        self.assertEqual(actual_call.args[0], "post_lock_acquired")
        self.assertEqual(actual_call.kwargs.get("room"), expected_room)

        actual_data_dict = actual_call.args[1]
        self.assertEqual(actual_data_dict.get("post_id"), expected_data["post_id"])
        self.assertEqual(actual_data_dict.get("user_id"), expected_data["user_id"])
        self.assertEqual(actual_data_dict.get("username"), expected_data["username"])
        self.assertIn(
            "expires_at", actual_data_dict
        )

    @patch("social_app.socketio.emit") # Corrected patch target
    def test_socketio_lock_released_broadcast_from_api(
        self, mock_socketio_emit_release # Corrected mock name
    ):
        # 1. Acquire lock first
        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
        response_acquire = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )
        self.assertEqual(response_acquire.status_code, 200, "Failed to acquire lock initially.")

        # Reset mock after lock acquisition's emit
        mock_socketio_emit_release.reset_mock()

        # 2. Release the lock
        response_release = self.client.delete(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )
        self.assertEqual(response_release.status_code, 200, f"Failed to release lock: {response_release.data.decode()}")
        time.sleep(0.1) # Allow time for emit

        # 3. Assert the 'post_lock_released' event was emitted
        expected_data = {
            "post_id": self.test_post.id,
            "released_by_user_id": self.collaborator.id,
            "username": self.collaborator.username,
        }
        expected_room = f"post_{self.test_post.id}"

        self.assertEqual(
            mock_socketio_emit_release.call_count,
            1,
            f"Expected emit to be called once for lock release. Actual calls: {mock_socketio_emit_release.call_args_list}",
        )

        actual_call = mock_socketio_emit_release.call_args_list[0]
        self.assertEqual(actual_call.args[0], "post_lock_released", "Event name mismatch.")
        self.assertEqual(actual_call.kwargs.get("room"), expected_room, "Room mismatch.")

        actual_data_dict = actual_call.args[1]
        self.assertEqual(actual_data_dict, expected_data, "Data mismatch.")

```
