import unittest
import json
import time
from unittest.mock import patch, call, ANY, MagicMock
from datetime import datetime, timedelta, timezone

from social_app import db, socketio, create_app
from social_app.models.db_models import Post, User, PostLock
from tests.test_base import AppTestCase
import logging


class TestCollaborativeEditing(AppTestCase):

    def setUp(self):
        super().setUp()

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

        self.test_post = self._create_db_post(
            user_id=self.post_author.id,
            title="Collaborative Post",
            content="Initial content.",
        )

        if self.socketio_client and self.socketio_client.connected:
            self.socketio_client.disconnect()

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
        ):
            self.socketio_client.disconnect()
        super().tearDown()

    def test_post_lock_creation(self):
        with self.app.app_context():
            test_post_merged = self.db.session.merge(self.test_post)
            lock = self._create_db_lock(
                post_id=test_post_merged.id,
                user_id=self.post_author.id,
                minutes_offset=15,
            )
            self.assertIsNotNone(lock)
            self.assertIsNotNone(lock.id)
            self.assertEqual(lock.post_id, test_post_merged.id)
            self.assertEqual(lock.user_id, self.post_author.id)
            expires_at_aware = lock.expires_at.replace(tzinfo=timezone.utc)
            self.assertTrue(expires_at_aware > datetime.now(timezone.utc))

            queried_lock_again = self.db.session.get(PostLock, lock.id)
            self.assertIsNotNone(queried_lock_again)
            self.assertEqual(queried_lock_again.post_id, test_post_merged.id)

    def test_post_is_locked_method(self):
        with self.app.app_context():
            current_post = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(current_post)

            self.assertFalse(current_post.is_locked())

            active_lock = self._create_db_lock(
                post_id=current_post.id, user_id=self.post_author.id, minutes_offset=15
            )
            self.db.session.refresh(current_post)
            self.assertTrue(current_post.is_locked())

            merged_active_lock = self.db.session.merge(active_lock)
            self.db.session.delete(merged_active_lock)
            self.db.session.commit()

            self.db.session.refresh(current_post)
            self.assertFalse(current_post.is_locked())

            expired_lock = self._create_db_lock(
                post_id=current_post.id, user_id=self.post_author.id, minutes_offset=-5
            )
            self.db.session.refresh(current_post)
            self.assertFalse(current_post.is_locked())

            merged_expired_lock = self.db.session.merge(expired_lock)
            self.db.session.delete(merged_expired_lock)
            self.db.session.commit()

    def test_api_acquire_lock_success(self):
        token = self._get_jwt_token(self.collaborator.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers
        )
        response_data = json.loads(response.data.decode())

        self.assertEqual(response.status_code, 200, f"Response data: {response_data}")
        self.assertEqual(response_data.get("message"), "Post locked successfully.")
        self.assertIn("lock_details", response_data)
        self.assertEqual(response_data["lock_details"]["post_id"], self.test_post.id)
        self.assertEqual(
            response_data["lock_details"]["locked_by_user_id"], self.collaborator.id
        )
        self.assertEqual(
            response_data["lock_details"]["locked_by_username"],
            self.collaborator.username,
        )
        self.assertIsNotNone(response_data["lock_details"].get("expires_at"))

        with self.app.app_context():
            current_post = self.db.session.get(Post, self.test_post.id)
            lock = PostLock.query.filter_by(
                post_id=current_post.id, user_id=self.collaborator.id
            ).first()
            self.assertIsNotNone(lock)
            self.assertTrue(current_post.is_locked())

    def test_api_acquire_lock_conflict(self):
        token_author = self._get_jwt_token(self.post_author.username, "password")
        headers_author = {"Authorization": f"Bearer {token_author}"}
        response_author = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_author
        )
        self.assertEqual(response_author.status_code, 200)

        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
        response_collaborator = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )

        self.assertEqual(response_collaborator.status_code, 409)
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
            self.assertEqual(lock.user_id, self.post_author.id)

    def test_api_release_lock_success(self):
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
            current_post = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(current_post)
            self.assertTrue(current_post.is_locked())

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
            self.assertIsNotNone(current_post_after_release)
            lock = PostLock.query.filter_by(
                post_id=current_post_after_release.id
            ).first()
            self.assertIsNone(lock)
            self.assertFalse(current_post_after_release.is_locked())

    def test_api_release_lock_unauthorized(self):
        token_author = self._get_jwt_token(self.post_author.username, "password")
        headers_author = {"Authorization": f"Bearer {token_author}"}
        response_acquire = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_author
        )
        self.assertEqual(response_acquire.status_code, 200)

        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
        response_release = self.client.delete(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )

        self.assertEqual(response_release.status_code, 403)
        response_data = json.loads(response_release.data.decode())
        self.assertEqual(
            response_data.get("message"),
            "You are not authorized to unlock this post as it is locked by another user.",
        )

        with self.app.app_context():
            current_post = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(current_post)
            lock = PostLock.query.filter_by(post_id=current_post.id).first()
            self.assertIsNotNone(lock)
            self.assertEqual(lock.user_id, self.post_author.id)
            self.assertTrue(current_post.is_locked())

    def test_api_acquire_lock_unauthenticated(self):
        response = self.client.post(f"/api/posts/{self.test_post.id}/lock")
        self.assertEqual(response.status_code, 401)
        response_data = json.loads(response.data.decode())
        self.assertIn("Missing Authorization Header", response_data.get("msg", ""))

    def test_api_acquire_lock_on_non_existent_post(self):
        token = self._get_jwt_token(self.collaborator.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        non_existent_post_id = 99999
        response = self.client.post(
            f"/api/posts/{non_existent_post_id}/lock", headers=headers
        )
        response_data = json.loads(response.data.decode())
        self.assertEqual(response.status_code, 404, f"Response data: {response_data}")
        self.assertIn("Post not found", response_data.get("message", ""))

    def test_api_lock_expiry_and_reacquire(self):
        token_author = self._get_jwt_token(self.post_author.username, "password")
        headers_author = {"Authorization": f"Bearer {token_author}"}

        response_acquire_author = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_author
        )
        self.assertEqual(response_acquire_author.status_code, 200)
        response_data_author = json.loads(response_acquire_author.data.decode())
        self.assertIn("lock_details", response_data_author)
        self.assertIn("locked_by_username", response_data_author["lock_details"])
        self.assertEqual(
            response_data_author["lock_details"]["locked_by_username"],
            self.post_author.username,
        )

        with self.app.app_context():
            current_post_author_lock = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(current_post_author_lock)
            self.assertTrue(current_post_author_lock.is_locked())

            lock = PostLock.query.filter_by(
                post_id=self.test_post.id, user_id=self.post_author.id
            ).first()
            self.assertIsNotNone(lock)

            lock.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            self.db.session.add(lock)
            self.db.session.commit()

            current_post_after_expiry = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(current_post_after_expiry)
            self.assertFalse(current_post_after_expiry.is_locked())

        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}

        response_acquire_collaborator = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )
        self.assertEqual(response_acquire_collaborator.status_code, 200)
        response_data_collaborator = json.loads(
            response_acquire_collaborator.data.decode()
        )
        self.assertIn("lock_details", response_data_collaborator)
        self.assertIn("locked_by_username", response_data_collaborator["lock_details"])
        self.assertEqual(
            response_data_collaborator["lock_details"]["locked_by_username"],
            self.collaborator.username,
        )

        with self.app.app_context():
            current_post_collaborator_lock = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(current_post_collaborator_lock)
            self.assertTrue(current_post_collaborator_lock.is_locked())

            lock_collaborator = PostLock.query.filter_by(
                post_id=current_post_collaborator_lock.id, user_id=self.collaborator.id
            ).first()
            self.assertIsNotNone(lock_collaborator)
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
            self.assertEqual(response_lock.status_code, 200)
            mock_socketio_emit.reset_mock()

            self.login(self.collaborator.username, "password")

            if not self.socketio_client or not self.socketio_client.is_connected():
                self.socketio_client = self.socketio_class_level.test_client(
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
            self.assertIsNotNone(updated_post)
            self.assertEqual(updated_post.content, edit_data["new_content"])

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
            self.assertTrue(found_call)

    @patch("social_app.socketio.emit")
    def test_socketio_edit_post_without_lock(self, mock_emit):
        with self.app.app_context():
            PostLock.query.filter_by(post_id=self.test_post.id).delete()
            self.db.session.commit()

            current_post_state = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(current_post_state)
            self.assertFalse(current_post_state.is_locked())
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
            self.socketio_client = self.socketio_class_level.test_client(
                self.app, flask_test_client=self.client
            )
            self.assertTrue(self.socketio_client.is_connected())

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

            self.assertTrue(found_edit_error_call)

            post_after_attempt = self.db.session.get(Post, self.test_post.id)
            self.assertIsNotNone(post_after_attempt)
            self.assertEqual(post_after_attempt.content, original_content)

            all_calls = mock_emit.call_args_list
            for call_args_item in all_calls:
                event_name_called = call_args_item[0][0]
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

        self.assertEqual(response.status_code, 200)
        time.sleep(0.1)

        expected_data = {
            "post_id": self.test_post.id,
            "user_id": self.collaborator.id,
            "username": self.collaborator.username,
            "expires_at": ANY,
        }
        expected_room = f"post_{self.test_post.id}"

        self.assertEqual(mock_socketio_emit.call_count, 1)

        actual_call = mock_socketio_emit.call_args_list[0]

        self.assertEqual(actual_call.args[0], "post_lock_acquired")
        self.assertEqual(actual_call.kwargs.get("room"), expected_room)

        actual_data_dict = actual_call.args[1]
        self.assertEqual(actual_data_dict.get("post_id"), expected_data["post_id"])
        self.assertEqual(actual_data_dict.get("user_id"), expected_data["user_id"])
        self.assertEqual(actual_data_dict.get("username"), expected_data["username"])
        self.assertIn("expires_at", actual_data_dict)

    @patch("social_app.socketio.emit")
    def test_socketio_lock_released_broadcast_from_api(
        self, mock_socketio_emit_release
    ):
        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
        response_acquire = self.client.post(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )
        self.assertEqual(response_acquire.status_code, 200)

        mock_socketio_emit_release.reset_mock()

        response_release = self.client.delete(
            f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
        )
        self.assertEqual(response_release.status_code, 200)
        time.sleep(0.1)

        expected_data = {
            "post_id": self.test_post.id,
            "released_by_user_id": self.collaborator.id,
            "username": self.collaborator.username,
        }
        expected_room = f"post_{self.test_post.id}"

        self.assertEqual(mock_socketio_emit_release.call_count, 1)

        actual_call = mock_socketio_emit_release.call_args_list[0]
        self.assertEqual(actual_call.args[0], "post_lock_released")
        self.assertEqual(actual_call.kwargs.get("room"), expected_room)

        actual_data_dict = actual_call.args[1]
        self.assertEqual(actual_data_dict, expected_data)
