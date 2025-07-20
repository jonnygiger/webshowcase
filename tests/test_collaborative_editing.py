import unittest
import json
import time
from unittest.mock import patch, call, ANY, MagicMock
from datetime import datetime, timedelta, timezone

from social_app import db, create_app
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

    def tearDown(self):
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
        self.assertEqual(response_data.get("message"), "Post unlocked successfully.")

        with self.app.app_context():
            current_post_after_release = self.db.session.get(Post, self.test_post.id)
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
            current_post_collaborator_lock = self.db.session.get(
                Post, self.test_post.id
            )
            self.assertIsNotNone(current_post_collaborator_lock)
            self.assertTrue(current_post_collaborator_lock.is_locked())

            lock_collaborator = PostLock.query.filter_by(
                post_id=current_post_collaborator_lock.id, user_id=self.collaborator.id
            ).first()
            self.assertIsNotNone(lock_collaborator)
            self.assertEqual(lock_collaborator.user_id, self.collaborator.id)

    def test_sse_edit_post_by_lock_owner(self):  # Renamed test
        with self.app.app_context():
            with patch("social_app.core.views.current_app.post_event_listeners") as mock_post_event_listeners:
                token = self._get_jwt_token(self.collaborator.username, "password")
                headers = {"Authorization": f"Bearer {token}"}

                # Acquire lock via API
                response_lock = self.client.post(
                    f"/api/posts/{self.test_post.id}/lock", headers=headers
                )
                self.assertEqual(response_lock.status_code, 200)

                # Setup a mock queue for SSE
                mock_queue = MagicMock()
                mock_post_event_listeners.get.return_value = [mock_queue]
                mock_post_event_listeners.__contains__.return_value = True

                # Perform edit via HTTP POST (simulating form submission)
                edit_payload = {
                    "title": self.test_post.title,  # Title might be required by the form
                    "content": "Updated content by lock owner via SSE test.",
                    "hashtags": self.test_post.hashtags,
                }
                self.login(
                    self.collaborator.username, "password"
                )  # Login the user performing the edit
                response_edit = self.client.post(
                    f"/posts/{self.test_post.id}/edit",
                    data=edit_payload,
                    headers=headers,  # Re-use headers with token for authorization if view requires
                )
                self.assertEqual(
                    response_edit.status_code, 302
                )  # Redirect after successful post

                updated_post = self.db.session.get(Post, self.test_post.id)
                self.assertIsNotNone(updated_post)
                self.assertEqual(updated_post.content, edit_payload["content"])

                # Check if SSE was dispatched
                # This part needs careful implementation based on how SSE is dispatched in views.py
                # Assuming views.py uses something like:
                # current_app.post_event_listeners[post_id].put_nowait(sse_data)

                self.assertTrue(mock_post_event_listeners.__contains__.called)
                mock_queue.put_nowait.assert_called_once()

                args, _ = mock_queue.put_nowait.call_args
                sse_event_data = args[0]

                self.assertEqual(sse_event_data["type"], "post_content_updated")
                payload = sse_event_data["payload"]
                self.assertEqual(payload["post_id"], self.test_post.id)
                self.assertEqual(payload["new_content"], edit_payload["content"])
                self.assertEqual(payload["edited_by_user_id"], self.collaborator.id)
                self.assertEqual(payload["edited_by_username"], self.collaborator.username)
                self.assertIn("last_edited", payload)

    def test_edit_post_by_non_author_without_lock(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.post_event_listeners") as mock_post_event_listeners:
                # Ensure no lock exists
                PostLock.query.filter_by(post_id=self.test_post.id).delete()
                self.db.session.commit()

                current_post_state = self.db.session.get(Post, self.test_post.id)
                self.assertIsNotNone(current_post_state)
                original_content = current_post_state.content

                # self.collaborator (user2) is NOT the author of self.test_post (created by user1)
                self.login(self.collaborator.username, "password")

                edit_payload = {
                    "title": current_post_state.title,
                    "content": "Attempted edit by non-author.",
                    "hashtags": current_post_state.hashtags,
                }

                response_edit = self.client.post(
                    f"/posts/{self.test_post.id}/edit",
                    data=edit_payload,
                    follow_redirects=True,  # To check flash messages
                )

                # Edit should be rejected by the authorship check in edit_post view
                self.assertEqual(response_edit.status_code, 200)  # After redirect
                self.assertIn(
                    b"You are not authorized to edit this post.", response_edit.data
                )

                post_after_attempt = self.db.session.get(Post, self.test_post.id)
                self.assertIsNotNone(post_after_attempt)
                self.assertEqual(
                    post_after_attempt.content, original_content
                )  # Content should not change

                # No SSE should have been dispatched for post_content_updated
                # Check that the .get method on the mock_post_event_listeners was not called,
                # or if it could be called (e.g. to check if post.id is in listeners),
                # then check that put_nowait on the queue was not called.
                if hasattr(mock_post_event_listeners, "get"):
                    mock_post_event_listeners.get.assert_not_called()
                elif hasattr(mock_post_event_listeners, "__contains__"):
                    # If the code checks `post.id in current_app.post_event_listeners`
                    # then __contains__ might be called. If so, check the queue.
                    if mock_post_event_listeners.__contains__.called:
                        mock_queue = mock_post_event_listeners.get.return_value[
                            0
                        ]  # Or however queue is accessed
                        mock_queue.put_nowait.assert_not_called()

    def test_sse_lock_acquired_broadcast_from_api(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.post_event_listeners") as mock_post_event_listeners:
                mock_queue = MagicMock()
                mock_post_event_listeners.get.return_value = [mock_queue]
                mock_post_event_listeners.__contains__.return_value = True

                token = self._get_jwt_token(self.collaborator.username, "password")
                headers = {"Authorization": f"Bearer {token}"}

                response = self.client.post(
                    f"/api/posts/{self.test_post.id}/lock", headers=headers
                )

                self.assertEqual(response.status_code, 200)
                time.sleep(0.1)  # Allow time for SSE dispatch if async

                mock_queue.put_nowait.assert_called_once()
                args, _ = mock_queue.put_nowait.call_args
                sse_event_data = args[0]

                self.assertEqual(sse_event_data["type"], "post_lock_acquired")
                payload = sse_event_data["payload"]
                self.assertEqual(payload["post_id"], self.test_post.id)
                self.assertEqual(payload["user_id"], self.collaborator.id)
                self.assertEqual(payload["username"], self.collaborator.username)
                self.assertIn("expires_at", payload)

    def test_sse_lock_released_broadcast_from_api(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.post_event_listeners") as mock_post_event_listeners_release:
                mock_queue_release = MagicMock()
                mock_post_event_listeners_release.get.return_value = [mock_queue_release]
                mock_post_event_listeners_release.__contains__.return_value = True

                token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
                headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
                response_acquire = self.client.post(
                    f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
                )
                self.assertEqual(response_acquire.status_code, 200)

                # Reset mock for the release part if the same mock is used or ensure fresh mock
                mock_queue_release.reset_mock()  # Reset the specific queue mock

                response_release = self.client.delete(
                    f"/api/posts/{self.test_post.id}/lock", headers=headers_collaborator
                )
                self.assertEqual(response_release.status_code, 200)
                time.sleep(0.1)  # Allow time for SSE dispatch

                mock_queue_release.put_nowait.assert_called_once()
                args_release, _ = mock_queue_release.put_nowait.call_args
                sse_event_data_release = args_release[0]

                self.assertEqual(sse_event_data_release["type"], "post_lock_released")
                payload_release = sse_event_data_release["payload"]
                self.assertEqual(payload_release["post_id"], self.test_post.id)
                self.assertEqual(payload_release["released_by_user_id"], self.collaborator.id)
                self.assertEqual(payload_release["username"], self.collaborator.username)
