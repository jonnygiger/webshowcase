import unittest
import json
from unittest.mock import patch, call, ANY, MagicMock  # Added MagicMock here
from datetime import datetime, timedelta

# from app import app, db, socketio # COMMENTED OUT
from models import Post, User, PostLock # Import PostLock for querying
from tests.test_base import AppTestCase


class TestCollaborativeEditing(AppTestCase):
    # _create_db_post and _create_db_lock are in AppTestCase

    def setUp(self):
        super().setUp()
        self.post_author = self.user1
        self.collaborator = self.user2
        self.another_user = self.user3

        # Create a real post using the helper from AppTestCase
        self.test_post = self._create_db_post(user_id=self.post_author.id, title="Collaborative Post", content="Initial content.")

        # Initialize SocketIO test client using the app and socketio instance from AppTestCase
        # AppTestCase.app and AppTestCase.socketio are class attributes
        # self.socketio_client is now created in AppTestCase.setUp()

    def tearDown(self):
        if self.socketio_client and self.socketio_client.connected:
            self.socketio_client.disconnect()
        super().tearDown()

    # --- Model Tests ---
    def test_post_lock_creation(self):
        with self.app.app_context():
            lock = self._create_db_lock(post_id=self.test_post.id, user_id=self.post_author.id, minutes_offset=15)
            self.assertIsNotNone(lock)
            self.assertIsNotNone(lock.id)
            self.assertEqual(lock.post_id, self.test_post.id)
            self.assertEqual(lock.user_id, self.post_author.id)
            self.assertTrue(lock.expires_at > datetime.utcnow())

            # Verify it's in the database
            queried_lock = self.db.session.get(PostLock, lock.id)
            self.assertIsNotNone(queried_lock)
            self.assertEqual(queried_lock.post_id, self.test_post.id)

    def test_post_is_locked_method(self):
        with self.app.app_context():
            # 1. Test with no lock
            self.assertFalse(self.test_post.is_locked(), "Post should not be locked if no lock exists.")

            # 2. Test with an active lock
            active_lock = self._create_db_lock(post_id=self.test_post.id, user_id=self.post_author.id, minutes_offset=15)
            self.db.session.refresh(self.test_post) # Refresh to ensure lock_info is loaded
            self.assertTrue(self.test_post.is_locked(), "Post should be locked with an active lock.")

            # 3. Test with an expired lock
            # First, remove the active lock to ensure a clean state for the next check
            self.db.session.delete(active_lock)
            self.db.session.commit()
            self.db.session.refresh(self.test_post) # Refresh to ensure lock_info is cleared
            # Sanity check that it's indeed not locked now
            self.assertFalse(self.test_post.is_locked(), "Post should not be locked after deleting the active lock.")


            expired_lock = self._create_db_lock(post_id=self.test_post.id, user_id=self.post_author.id, minutes_offset=-5)
            self.db.session.refresh(self.test_post) # Refresh to ensure the new lock_info is loaded
            self.assertFalse(self.test_post.is_locked(), "Post should not be locked with an expired lock.")

            # Clean up the expired lock
            self.db.session.delete(expired_lock)
            self.db.session.commit()


    # --- API Endpoint Tests (PostLockResource) ---
    def test_api_acquire_lock_success(self):
        token = self._get_jwt_token(self.collaborator.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.post(f'/api/posts/{self.test_post.id}/lock', headers=headers)
        response_data = json.loads(response.data.decode())

        self.assertEqual(response.status_code, 200, f"Response data: {response_data}")
        self.assertEqual(response_data.get('message'), 'Lock acquired successfully.')
        self.assertIn('lock_details', response_data)
        self.assertEqual(response_data['lock_details']['post_id'], self.test_post.id)
        self.assertEqual(response_data['lock_details']['user_id'], self.collaborator.id)
        self.assertEqual(response_data.get('locked_by_username'), self.collaborator.username)
        self.assertIsNotNone(response_data.get('expires_at'))

        with self.app.app_context():
            lock = PostLock.query.filter_by(post_id=self.test_post.id, user_id=self.collaborator.id).first()
            self.assertIsNotNone(lock)
            self.db.session.refresh(self.test_post)
            self.assertTrue(self.test_post.is_locked())

    def test_api_acquire_lock_conflict(self):
        # User1 (post_author) acquires the lock first
        token_author = self._get_jwt_token(self.post_author.username, "password")
        headers_author = {"Authorization": f"Bearer {token_author}"}
        response_author = self.client.post(f'/api/posts/{self.test_post.id}/lock', headers=headers_author)
        self.assertEqual(response_author.status_code, 200)

        # User2 (collaborator) attempts to acquire the same lock
        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
        response_collaborator = self.client.post(f'/api/posts/{self.test_post.id}/lock', headers=headers_collaborator)

        self.assertEqual(response_collaborator.status_code, 409) # Conflict
        response_data = json.loads(response_collaborator.data.decode())
        self.assertIn("already locked by", response_data.get("message", "").lower())
        self.assertIn(self.post_author.username.lower(), response_data.get("message", "").lower())


        with self.app.app_context():
            lock = PostLock.query.filter_by(post_id=self.test_post.id).first()
            self.assertIsNotNone(lock)
            self.assertEqual(lock.user_id, self.post_author.id) # Still locked by author

    def test_api_release_lock_success(self):
        # Collaborator acquires the lock
        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
        response_acquire = self.client.post(f'/api/posts/{self.test_post.id}/lock', headers=headers_collaborator)
        self.assertEqual(response_acquire.status_code, 200, f"Acquire failed: {response_acquire.data.decode()}")

        with self.app.app_context():
            self.db.session.refresh(self.test_post)
            self.assertTrue(self.test_post.is_locked(), "Post should be locked before release attempt.")

        # Collaborator releases the lock
        response_release = self.client.delete(f'/api/posts/{self.test_post.id}/lock', headers=headers_collaborator)
        response_data = json.loads(response_release.data.decode())

        self.assertEqual(response_release.status_code, 200, f"Response data: {response_data}")
        self.assertEqual(response_data.get('message'), 'Lock released successfully.')

        with self.app.app_context():
            lock = PostLock.query.filter_by(post_id=self.test_post.id).first()
            self.assertIsNone(lock)
            self.db.session.refresh(self.test_post)
            self.assertFalse(self.test_post.is_locked())

    def test_api_release_lock_unauthorized(self):
        # Post_author acquires the lock
        token_author = self._get_jwt_token(self.post_author.username, "password")
        headers_author = {"Authorization": f"Bearer {token_author}"}
        response_acquire = self.client.post(f'/api/posts/{self.test_post.id}/lock', headers=headers_author)
        self.assertEqual(response_acquire.status_code, 200)

        # Collaborator attempts to release the lock
        token_collaborator = self._get_jwt_token(self.collaborator.username, "password")
        headers_collaborator = {"Authorization": f"Bearer {token_collaborator}"}
        response_release = self.client.delete(f'/api/posts/{self.test_post.id}/lock', headers=headers_collaborator)

        self.assertEqual(response_release.status_code, 403) # Forbidden
        response_data = json.loads(response_release.data.decode())
        self.assertEqual(response_data.get('message'), 'You do not own this lock.')

        with self.app.app_context():
            lock = PostLock.query.filter_by(post_id=self.test_post.id).first()
            self.assertIsNotNone(lock) # Lock should still exist
            self.assertEqual(lock.user_id, self.post_author.id) # Still locked by author
            self.db.session.refresh(self.test_post)
            self.assertTrue(self.test_post.is_locked())

    def test_api_acquire_lock_unauthenticated(self):
        response = self.client.post(f"/api/posts/{self.test_post.id}/lock")  # No token
        self.assertEqual(response.status_code, 401)
        response_data = json.loads(response.data.decode())
        self.assertIn("Missing JWT", response_data.get("msg", "")) # Or specific message from flask_jwt_extended

    def test_api_acquire_lock_on_non_existent_post(self):
        token = self._get_jwt_token(self.collaborator.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        # Assuming 99999 is an ID that will not exist
        non_existent_post_id = 99999

        response = self.client.post(f'/api/posts/{non_existent_post_id}/lock', headers=headers)
        response_data = json.loads(response.data.decode())

        self.assertEqual(response.status_code, 404, f"Response data: {response_data}")
        self.assertIn('Post not found', response_data.get('message', ''), "Response message did not indicate post not found.")

    # --- SocketIO Event Tests ---
    # These tests are more complex and depend heavily on live app, socketio, and db.
    @patch("app.socketio.emit")
    def test_socketio_edit_post_with_lock(self, mock_app_socketio_emit):
        # with app.app_context():
        # token_collab = self._get_jwt_token(self.collaborator.username, 'password')
        # self.client.post(f'/api/posts/{self.test_post.id}/lock', headers=headers_collab) # Acquire lock
        # ... (simulate socketio connection and event emission) ...
        pass  # Placeholder

    def test_socketio_edit_post_without_lock(self):
        # with app.app_context():
        # PostLock.query.delete() # Requires live DB
        # db.session.commit()
        # ... (simulate socketio client and event) ...
        pass  # Placeholder

    @patch("app.socketio.emit") # Corrected mock path and indented
    def test_socketio_lock_acquired_broadcast_from_api(self, mock_app_socketio_emit): # Renamed mock argument and indented
        token = self._get_jwt_token(self.collaborator.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.post(f'/api/posts/{self.test_post.id}/lock', headers=headers)

        self.assertEqual(response.status_code, 200, f"Failed to acquire lock: {response.data.decode()}")

        expected_data = {
            'post_id': self.test_post.id,
            'user_id': self.collaborator.id,
            'username': self.collaborator.username,
            'expires_at': ANY  # We use ANY for the expiry time as it's dynamic
        }
        mock_app_socketio_emit.assert_called_once_with( # Renamed mock argument and indented
            'post_lock_acquired', # Corrected event name
            expected_data,
            room=f'post_{self.test_post.id}'
        )

    @patch("app.socketio.emit") # Corrected mock path and indented
    def test_socketio_lock_released_broadcast_from_api(self, mock_app_socketio_emit): # Renamed mock argument and indented
        # with app.app_context():
        # self._create_db_lock(post_id=self.test_post.id, user_id=self.collaborator.id, minutes_offset=15)
        # token = self._get_jwt_token(self.collaborator.username, 'password')
        # ...
        # response = self.client.delete(f'/api/posts/{self.test_post.id}/lock', headers=headers)
        # ... (assertions on mock_api_socketio_emit) ...
        pass  # Placeholder
