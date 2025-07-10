import unittest
from unittest.mock import patch, ANY, MagicMock
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
                password_hash="password_hash_for_author2", # pragma: allowlist secret
            )
            db.session.add(self.author2)
            db.session.commit()
            self.author2 = db.session.get(User, self.author2.id)

    @patch("social_app.core.views.current_app.user_notification_queues")
    def test_like_post_sends_notification_and_dispatches_sse(self, mock_user_notification_queues):
        with self.app.app_context():
            mock_author_queue = MagicMock()
            mock_user_notification_queues.get.return_value = [mock_author_queue]
            mock_user_notification_queues.__contains__.return_value = True

            post_by_author = self._create_db_post(
                user_id=self.author1.id, title="Author's Likable Post"
            )
            self.assertIsNotNone(post_by_author)

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
            self.assertIsNotNone(notification)
            expected_message = f"{self.liker.username} liked your post: '{post_by_author.title}'"
            self.assertEqual(notification.message, expected_message)

            expected_sse_payload = {
                "liker_username": self.liker.username,
                "post_id": post_by_author.id,
                "post_title": post_by_author.title,
                "message": expected_message,
                "notification_id": notification.id,
            }

            mock_user_notification_queues.__contains__.assert_any_call(self.author1.id)
            mock_author_queue.put_nowait.assert_called_once()

            args, _ = mock_author_queue.put_nowait.call_args
            sse_event_data = args[0]
            self.assertEqual(sse_event_data['type'], "new_like")
            self.assertEqual(sse_event_data['payload'], expected_sse_payload)

        self.logout()

    @patch("social_app.core.views.current_app.user_notification_queues")
    def test_like_post_sends_notification_to_correct_author(self, mock_user_notification_queues):
        with self.app.app_context():
            mock_author1_queue = MagicMock()

            def contains_side_effect(user_id_to_check):
                return user_id_to_check == self.author1.id

            def get_side_effect(user_id_to_get, default=None):
                if user_id_to_get == self.author1.id:
                    return [mock_author1_queue]
                return default if default is not None else []

            mock_user_notification_queues.__contains__.side_effect = contains_side_effect
            mock_user_notification_queues.get.side_effect = get_side_effect

            post_by_author1 = self._create_db_post(
                user_id=self.author1.id, title="Author1's Test Post"
            )
            self.assertIsNotNone(post_by_author1)

            self.login(self.liker.username, "password")
            response = self.client.post(
                f"/blog/post/{post_by_author1.id}/like", follow_redirects=True
            )
            self.assertEqual(response.status_code, 200)

            notification_author1 = Notification.query.filter_by(
                user_id=self.author1.id, type="like", related_id=post_by_author1.id
            ).first()
            self.assertIsNotNone(notification_author1)
            expected_message_author1 = (
                f"{self.liker.username} liked your post: '{post_by_author1.title}'"
            )
            self.assertEqual(notification_author1.message, expected_message_author1)

            expected_sse_payload_author1 = {
                "liker_username": self.liker.username,
                "post_id": post_by_author1.id,
                "post_title": post_by_author1.title,
                "message": expected_message_author1,
                "notification_id": notification_author1.id,
            }

            mock_user_notification_queues.__contains__.assert_any_call(self.author1.id)
            mock_user_notification_queues.get.assert_any_call(self.author1.id)
            mock_author1_queue.put_nowait.assert_called_once()
            args, _ = mock_author1_queue.put_nowait.call_args
            sse_event_data = args[0]
            self.assertEqual(sse_event_data['type'], "new_like")
            self.assertEqual(sse_event_data['payload'], expected_sse_payload_author1)

            notification_author2 = Notification.query.filter_by(
                user_id=self.author2.id,
                type="like",
                related_id=post_by_author1.id,
            ).first()
            self.assertIsNone(notification_author2)

            self.assertFalse(mock_user_notification_queues.__contains__(self.author2.id))
            self.assertEqual(mock_user_notification_queues.get(self.author2.id, []), [])
        self.logout()

    @patch("social_app.core.views.current_app.user_notification_queues")
    def test_like_post_multiple_times_sends_single_notification(
        self, mock_user_notification_queues
    ):
        with self.app.app_context():
            mock_author_queue = MagicMock()
            mock_user_notification_queues.get.return_value = [mock_author_queue]
            mock_user_notification_queues.__contains__.return_value = True

            post_by_author = self._create_db_post(
                user_id=self.author1.id, title="Author's Post for Multiple Likes"
            )
            self.assertIsNotNone(post_by_author)

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
            self.assertIsNotNone(notification)
            expected_message = (
                f"{self.liker.username} liked your post: '{post_by_author.title}'"
            )
            self.assertEqual(notification.message, expected_message)

            mock_author_queue.put_nowait.assert_called_once()
            first_notification_id = notification.id
            mock_author_queue.reset_mock()

            response_again = self.client.post(
                f"/blog/post/{post_by_author.id}/like", follow_redirects=True
            )
            self.assertEqual(response_again.status_code, 200)

            notifications_count = Notification.query.filter_by(
                user_id=self.author1.id,
                type="like",
                related_id=post_by_author.id,
            ).count()
            self.assertEqual(notifications_count, 1)

            current_notification = Notification.query.filter_by(
                user_id=self.author1.id,
                type="like",
                related_id=post_by_author.id,
            ).first()
            self.assertIsNotNone(current_notification)
            self.assertEqual(current_notification.id, first_notification_id)
            self.assertEqual(current_notification.message, expected_message)

            mock_author_queue.put_nowait.assert_not_called()
        self.logout()

    @patch("social_app.core.views.current_app.user_notification_queues")
    def test_like_own_post_does_not_send_notification_or_dispatch_sse(
        self, mock_user_notification_queues
    ):
        with self.app.app_context():
            mock_own_queue = MagicMock()
            mock_user_notification_queues.get.return_value = [mock_own_queue]
            mock_user_notification_queues.__contains__.return_value = False # Should not find queue for self

            post_by_author = self._create_db_post(
                user_id=self.author1.id, title="Author's Own Post to Like"
            )
            self.assertIsNotNone(post_by_author)

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
            self.assertIsNone(notification)

            mock_user_notification_queues.__contains__.assert_not_any_call(self.author1.id)
            mock_own_queue.put_nowait.assert_not_called()

        self.logout()

    @patch("social_app.core.views.current_app.user_notification_queues")
    def test_anonymous_user_cannot_like_post(self, mock_user_notification_queues):
        with self.app.app_context():
            mock_author_queue = MagicMock()
            mock_user_notification_queues.get.return_value = [mock_author_queue]
            mock_user_notification_queues.__contains__.return_value = False


            post_by_author = self._create_db_post(
                user_id=self.author1.id, title="Anonymous Like Test Post"
            )
            self.assertIsNotNone(post_by_author)

            response = self.client.post(
                f"/blog/post/{post_by_author.id}/like", follow_redirects=False
            )
            self.assertEqual(response.status_code, 302)
            expected_login_url_path = "/login"
            self.assertTrue(response.location.startswith(expected_login_url_path))

            notification = Notification.query.filter_by(
                user_id=self.author1.id,
                type="like",
                related_id=post_by_author.id,
            ).first()
            self.assertIsNone(notification)

            mock_user_notification_queues.__contains__.assert_not_called()
            mock_author_queue.put_nowait.assert_not_called()


    @patch("social_app.core.views.current_app.user_notification_queues")
    def test_like_non_existent_post(self, mock_user_notification_queues):
        with self.app.app_context():
            mock_any_queue = MagicMock()
            mock_user_notification_queues.get.return_value = [mock_any_queue]
            mock_user_notification_queues.__contains__.return_value = False

            self.login(self.liker.username, "password")
            non_existent_post_id = 99999
            response = self.client.post(
                f"/blog/post/{non_existent_post_id}/like", follow_redirects=True
            )
            self.assertEqual(response.status_code, 404)

            notification = Notification.query.filter_by(
                related_id=non_existent_post_id, type="like"
            ).first()
            self.assertIsNone(notification)

            mock_user_notification_queues.__contains__.assert_not_called()
            mock_any_queue.put_nowait.assert_not_called()
        self.logout()
