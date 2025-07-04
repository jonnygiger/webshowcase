import unittest
from unittest.mock import patch
from datetime import datetime

from social_app import db, create_app
from social_app.models.db_models import User, Post, Notification
from tests.test_base import AppTestCase


class TestLikeNotifications(AppTestCase):

    def setUp(self):
        super().setUp()
        self.author1 = self.user1
        self.liker = self.user2
        with self.app.app_context():
            self.author2 = User(
                username="author2",
                email="author2@example.com",
                # Use set_password for consistency if available, or direct hash
                password_hash="password_hash_for_author2", # Placeholder, use generate_password_hash if testing registration
            )
            # If User model has set_password method:
            # self.author2.set_password("password")
            db.session.add(self.author2)
            db.session.commit()
            self.author2 = db.session.get(User, self.author2.id)

    @patch("social_app.core.views.socketio.emit")
    def test_like_post_sends_notification_and_emits_event(self, mock_socketio_emit):
        with self.app.app_context():
            post_by_author = self._create_db_post(
                user_id=self.author1.id, title="Author's Likable Post"
            )
            self.assertIsNotNone(post_by_author, "Failed to create post.")

            self.login(self.liker.username, "password")
            response = self.client.post(
                f"/blog/post/{post_by_author.id}/like", follow_redirects=True
            )
            self.assertEqual(response.status_code, 200)

            notification = Notification.query.filter_by(
                user_id=self.author1.id,
                type="like",
                related_id=post_by_author.id,
            ).first()
            self.assertIsNotNone(
                notification, "Database notification was not created for the author."
            )
            expected_message = f"{self.liker.username} liked your post: '{post_by_author.title}'"
            self.assertEqual(notification.message, expected_message)

            app_expected_payload = {
                "liker_username": self.liker.username,
                "post_id": post_by_author.id,
                "post_title": post_by_author.title,
                "message": expected_message,
                "notification_id": notification.id,
            }
            mock_socketio_emit.assert_any_call(
                "new_like_notification",
                app_expected_payload,
                room=f"user_{self.author1.id}",
            )

        self.logout()

    @patch("social_app.core.views.socketio.emit")
    def test_like_post_sends_notification_to_correct_author(self, mock_socketio_emit):
        with self.app.app_context():
            post_by_author1 = self._create_db_post(
                user_id=self.author1.id, title="Author1's Test Post"
            )
            self.assertIsNotNone(post_by_author1, "Failed to create post by author1.")

            self.login(self.liker.username, "password")
            response = self.client.post(
                f"/blog/post/{post_by_author1.id}/like", follow_redirects=True
            )
            self.assertEqual(response.status_code, 200, "Liking the post failed.")

            notification_author1 = Notification.query.filter_by(
                user_id=self.author1.id, type="like", related_id=post_by_author1.id
            ).first()
            self.assertIsNotNone(
                notification_author1,
                "Database notification for author1 was not created.",
            )
            expected_message_author1 = (
                f"{self.liker.username} liked your post: '{post_by_author1.title}'"
            )
            self.assertEqual(notification_author1.message, expected_message_author1)

            expected_payload_author1 = {
                "liker_username": self.liker.username,
                "post_id": post_by_author1.id,
                "post_title": post_by_author1.title,
                "message": expected_message_author1,
                "notification_id": notification_author1.id,
            }
            mock_socketio_emit.assert_any_call(
                "new_like_notification",
                expected_payload_author1,
                room=f"user_{self.author1.id}",
            )

            notification_author2 = Notification.query.filter_by(
                user_id=self.author2.id,
                type="like",
                related_id=post_by_author1.id,
            ).first()
            self.assertIsNone(
                notification_author2,
                "Notification for author2 was created, but should not have been for author1's post.",
            )

            author2_room = f"user_{self.author2.id}"
            called_author2_room = False
            for call_args_tuple in mock_socketio_emit.call_args_list:
                args, kwargs = call_args_tuple
                if (
                    args
                    and args[0] == "new_like_notification"
                    and kwargs.get("room") == author2_room
                ):
                    payload = args[1] if len(args) > 1 else {}
                    if payload.get("post_id") == post_by_author1.id:
                        called_author2_room = True
                        break
            self.assertFalse(
                called_author2_room,
                f"'new_like_notification' event for post ID {post_by_author1.id} "
                f"should NOT be emitted to author2's room ({author2_room}). Found calls: {mock_socketio_emit.call_args_list}",
            )
        self.logout()

    @patch("social_app.core.views.socketio.emit")
    def test_like_post_multiple_times_sends_single_notification(
        self, mock_socketio_emit
    ):
        with self.app.app_context():
            post_by_author = self._create_db_post(
                user_id=self.author1.id, title="Author's Post for Multiple Likes"
            )
            self.assertIsNotNone(post_by_author, "Failed to create post.")

            self.login(self.liker.username, "password")
            response = self.client.post(
                f"/blog/post/{post_by_author.id}/like", follow_redirects=True
            )
            self.assertEqual(response.status_code, 200, "First like attempt failed.")

            notification = Notification.query.filter_by(
                user_id=self.author1.id,
                type="like",
                related_id=post_by_author.id,
            ).first()
            self.assertIsNotNone(
                notification,
                "Database notification was not created for the author on the first like.",
            )
            expected_message = (
                f"{self.liker.username} liked your post: '{post_by_author.title}'"
            )
            self.assertEqual(
                notification.message,
                expected_message,
                "Notification message is incorrect for the first like.",
            )
            self.assertEqual(
                mock_socketio_emit.call_count,
                1,
                "SocketIO emit was not called exactly once on the first like.",
            )
            first_notification_id = notification.id

            response_again = self.client.post(
                f"/blog/post/{post_by_author.id}/like", follow_redirects=True
            )
            self.assertEqual(
                response_again.status_code, 200, "Second like attempt failed."
            )

            notifications_count = Notification.query.filter_by(
                user_id=self.author1.id,
                type="like",
                related_id=post_by_author.id,
            ).count()
            self.assertEqual(
                notifications_count,
                1,
                "Notification count for the author should remain 1 after multiple likes.",
            )

            current_notification = Notification.query.filter_by(
                user_id=self.author1.id,
                type="like",
                related_id=post_by_author.id,
            ).first()
            self.assertIsNotNone(
                current_notification, "Could not find notification after second like."
            )
            self.assertEqual(
                current_notification.id,
                first_notification_id,
                "The existing notification ID should not change.",
            )
            self.assertEqual(
                current_notification.message,
                expected_message,
                "Notification message is incorrect after second like.",
            )
            self.assertEqual(
                mock_socketio_emit.call_count,
                1,
                "SocketIO emit call count should remain 1 after the second like.",
            )
        self.logout()

    @patch("social_app.core.views.socketio.emit")
    def test_like_own_post_does_not_send_notification_or_emit_event(
        self, mock_socketio_emit
    ):
        with self.app.app_context():
            post_by_author = self._create_db_post(
                user_id=self.author1.id, title="Author's Own Post to Like"
            )
            self.assertIsNotNone(post_by_author, "Failed to create post.")

            self.login(self.author1.username, "password")

            response = self.client.post(
                f"/blog/post/{post_by_author.id}/like", follow_redirects=True
            )
            self.assertEqual(response.status_code, 200)

            notification = Notification.query.filter_by(
                user_id=self.author1.id,
                type="like",
                related_id=post_by_author.id,
            ).first()
            self.assertIsNone(
                notification,
                "Notification should NOT be created when an author likes their own post.",
            )

            for call_args_tuple in mock_socketio_emit.call_args_list:
                args, kwargs = call_args_tuple
                if (
                    args and args[0] == "new_like_notification"
                ):
                    self.fail(
                        f"'new_like_notification' event should NOT be emitted to the author for liking their own post. Found: {call_args_tuple}"
                    )
        self.logout()

    @patch("social_app.core.views.socketio.emit")
    def test_anonymous_user_cannot_like_post(self, mock_socketio_emit):
        with self.app.app_context():
            post_by_author = self._create_db_post(
                user_id=self.author1.id, title="Anonymous Like Test Post"
            )
            self.assertIsNotNone(post_by_author, "Failed to create post by author.")

            response = self.client.post(
                f"/blog/post/{post_by_author.id}/like", follow_redirects=False
            )
            self.assertEqual(
                response.status_code,
                302,
                "Response status code should be 302 for anonymous like attempt.",
            )
            expected_login_url_path = "/login"
            self.assertTrue(
                response.location.startswith(expected_login_url_path),
                f"Redirect location '{response.location}' does not match expected login URL path '{expected_login_url_path}'.",
            )

            notification = Notification.query.filter_by(
                user_id=self.author1.id,
                type="like",
                related_id=post_by_author.id,
            ).first()
            self.assertIsNone(
                notification,
                "Notification should NOT be created for the author when an anonymous user attempts to like.",
            )

            for call_args_tuple in mock_socketio_emit.call_args_list:
                args, _ = call_args_tuple
                if args and args[0] == "new_like_notification":
                    self.fail(
                        f"'new_like_notification' event should NOT be emitted for an anonymous like attempt. Found: {call_args_tuple}"
                    )

    @patch("social_app.core.views.socketio.emit")
    def test_like_non_existent_post(self, mock_socketio_emit):
        with self.app.app_context():
            self.login(self.liker.username, "password")
            non_existent_post_id = 99999
            response = self.client.post(
                f"/blog/post/{non_existent_post_id}/like", follow_redirects=True
            )
            self.assertEqual(response.status_code, 404)

            notification = Notification.query.filter_by(
                related_id=non_existent_post_id, type="like"
            ).first()
            self.assertIsNone(
                notification,
                "Notification should not be created for liking a non-existent post.",
            )

            for call_args_tuple in mock_socketio_emit.call_args_list:
                args, _ = call_args_tuple
                if args and args[0] == "new_like_notification":
                    self.fail(
                        f"'new_like_notification' event should NOT be emitted for liking a non-existent post. Found: {call_args_tuple}"
                    )
        self.logout()

```
