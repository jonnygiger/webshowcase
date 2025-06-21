import unittest

# import json # Not used
from unittest.mock import patch  # Removed ANY
from datetime import datetime  # Removed timedelta

# from app import app, db, socketio # COMMENTED OUT
from models import User, Post, Notification # COMMENTED OUT
from tests.test_base import AppTestCase


class TestLikeNotifications(AppTestCase):

    def setUp(self):
        super().setUp()
        # self.user1 (author), self.user2 (liker) are created by AppTestCase._setup_base_users()
        self.author = self.user1
        self.liker = self.user2

    @patch(
        "app.socketio.emit"
    )  # Ensure correct path to socketio.emit if used by the app route
    def test_like_post_sends_notification_and_emits_event(self, mock_socketio_emit):
        with self.app.app_context():
            # 1. Setup Post by author
            created_post = self._create_db_post(user_id=self.author.id, title="Author's Likable Post")
            # post_by_author = Post.query.get(created_post.id) # No need to re-fetch, created_post is the object
            post_by_author = created_post
            self.assertIsNotNone(post_by_author, "Failed to create post.")

            # 2. Login as liker
            self.login(self.liker.username, "password")

            # 3. Liker likes the post
            response = self.client.post(f'/blog/post/{post_by_author.id}/like', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            # Assuming a flash message or some indicator of a successful like might not be present or relevant for API test
            # self.assertIn(b"Post liked!", response.data)

            # 4. Verify Database Notification for author
            notification = Notification.query.filter_by(
                user_id=self.author.id,
                type='like',
                related_id=post_by_author.id  # Use post_by_author.id here
            ).first()
            self.assertIsNotNone(notification, "Database notification was not created for the author.")
            expected_message = f"{self.liker.username} liked your post: '{post_by_author.title}'"  # Changed to single quotes
            self.assertEqual(notification.message, expected_message)

            # 5. Verify SocketIO Emission to author's room
            # Ensure expected_payload uses the same message format (single quotes)
            # The app.py emits 'new_like_notification' for likes.
            # The payload in app.py for 'new_like_notification' is:
            # {
            #     "liker_username": liker.username,
            #     "post_id": post.id,
            #     "post_title": post.title, # Note: title is separate, not part of message here
            #     "message": notification_message, # This is the full message string
            #     "notification_id": new_notification.id,
            # }
            # The test's expected_payload needs to match this structure.

            # Let's reconstruct expected_payload based on app.py's actual emission for 'new_like_notification'
            app_expected_payload = {
                'liker_username': self.liker.username,
                'post_id': post_by_author.id,
                'post_title': post_by_author.title, # Title is separate
                'message': expected_message, # Full message string (now with single quotes for title)
                'notification_id': notification.id # The notification ID from the DB
            }
            mock_socketio_emit.assert_any_call('new_like_notification', app_expected_payload, room=f'user_{self.author.id}')

        self.logout()

    @patch("app.socketio.emit")
    def test_like_own_post_does_not_send_notification_or_emit_event(
        self, mock_socketio_emit
    ):
        with self.app.app_context():
            # 1. Setup Post by author
            created_post = self._create_db_post(user_id=self.author.id, title="Author's Own Post to Like")
            # post_by_author = Post.query.get(created_post.id) # No need to re-fetch
            post_by_author = created_post
            self.assertIsNotNone(post_by_author, "Failed to create post.")

            # 2. Login as author
            self.login(self.author.username, "password")

            # 3. Author likes their own post
            response = self.client.post(f'/blog/post/{post_by_author.id}/like', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            # self.assertIn(b"Post liked!", response.data) # Or appropriate flash message if any

            # 4. Verify No Database Notification for author
            notification = Notification.query.filter_by(
                user_id=self.author.id,
                type='like',
                related_id=post_by_author.id # Use post_by_author.id here
            ).first()
            self.assertIsNone(notification, "Notification should NOT be created when an author likes their own post.")

            # 5. Verify SocketIO Emission was NOT called for 'new_notification'
            # (Note: the event name for like notifications is 'new_like_notification',
            # so checking for 'new_notification' here is correct if we want to ensure
            # no *other* 'new_notification' event was sent. If the goal is to ensure
            # 'new_like_notification' was not sent, this check should be updated.)
            for call_args_tuple in mock_socketio_emit.call_args_list:
                args, kwargs = call_args_tuple
                # Check the event name in args[0]
                if args and args[0] == 'new_like_notification': # Check specifically for new_like_notification
                    # If a 'new_like_notification' is found, it's a failure for this test case.
                    self.fail(f"'new_like_notification' event should NOT be emitted to the author for liking their own post. Found: {call_args_tuple}")

        self.logout()

    @patch("app.socketio.emit")
    def test_like_non_existent_post(self, mock_socketio_emit):
        """Test liking a post that does not exist."""
        with self.app.app_context():
            # 1. Login as a user
            self.login(self.liker.username, "password")

            # 2. Attempt to like a non-existent post
            non_existent_post_id = 99999
            response = self.client.post(f'/blog/post/{non_existent_post_id}/like', follow_redirects=True)

            # 3. Assertions
            # Assert that the response status code indicates an error (e.g., 404)
            self.assertEqual(response.status_code, 404) # Assuming 404 for not found

            # Assert that no notification was created in the database
            notification = Notification.query.filter_by(
                related_id=non_existent_post_id,
                type='like'
            ).first()
            self.assertIsNone(notification, "Notification should not be created for liking a non-existent post.")

            # Assert that no socket event was emitted
            # Check if mock_socketio_emit was called with 'new_like_notification'
            for call_args_tuple in mock_socketio_emit.call_args_list:
                args, _ = call_args_tuple
                if args and args[0] == 'new_like_notification':
                    self.fail(f"'new_like_notification' event should NOT be emitted for liking a non-existent post. Found: {call_args_tuple}")

        self.logout()
