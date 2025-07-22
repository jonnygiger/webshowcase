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
                password_hash="password_hash_for_author2",  # pragma: allowlist secret
            )
            db.session.add(self.author2)
            db.session.commit()
            self.author2 = db.session.get(User, self.author2.id)

    def test_like_post_sends_notification_and_dispatches_sse(self):
        with self.app.app_context():
            with patch(
                "social_app.core.views.current_app.user_notification_queues"
            ) as mock_user_notification_queues:
                mock_author_queue = MagicMock()
                mock_user_notification_queues.__contains__.return_value = True
                mock_user_notification_queues.get.return_value = [mock_author_queue]

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

                mock_author_queue.put_nowait.assert_called_once()
            self.logout()

    def test_like_post_sends_notification_to_correct_author(self):
        with self.app.app_context():
            with patch(
                "social_app.core.views.current_app.user_notification_queues"
            ) as mock_user_notification_queues:
                mock_author1_queue = MagicMock()

                def get_side_effect(user_id):
                    if user_id == self.author1.id:
                        return [mock_author1_queue]
                    return []

                mock_user_notification_queues.get.side_effect = get_side_effect
                mock_user_notification_queues.__contains__.side_effect = (
                    lambda user_id: user_id == self.author1.id
                )

                post_by_author1 = self._create_db_post(
                    user_id=self.author1.id, title="Author1's Test Post"
                )
                self.assertIsNotNone(post_by_author1)

                self.login(self.liker.username, "password")
                self.client.post(
                    f"/blog/post/{post_by_author1.id}/like", follow_redirects=True
                )

                notification_author1 = Notification.query.filter_by(
                    user_id=self.author1.id, type="like", related_id=post_by_author1.id
                ).first()
                self.assertIsNotNone(notification_author1)

                mock_user_notification_queues.__contains__.assert_any_call(self.author1.id)
                mock_author1_queue.put_nowait.assert_called_once()

                notification_author2 = Notification.query.filter_by(
                    user_id=self.author2.id,
                    type="like",
                    related_id=post_by_author1.id,
                ).first()
                self.assertIsNone(notification_author2)
            self.logout()

    def test_like_post_multiple_times_sends_single_notification(self):
        with self.app.app_context():
            with patch(
                "social_app.core.views.current_app.user_notification_queues"
            ) as mock_user_notification_queues:
                mock_author_queue = MagicMock()
                mock_user_notification_queues.get.return_value = [mock_author_queue]
                mock_user_notification_queues.__contains__.return_value = True

                post_by_author = self._create_db_post(
                    user_id=self.author1.id, title="Author's Post for Multiple Likes"
                )
                self.assertIsNotNone(post_by_author)

                self.login(self.liker.username, "password")
                self.client.post(
                    f"/blog/post/{post_by_author.id}/like", follow_redirects=True
                )

                mock_author_queue.put_nowait.assert_called_once()
                mock_author_queue.reset_mock()

                self.client.post(
                    f"/blog/post/{post_by_author.id}/like", follow_redirects=True
                )

                notifications_count = Notification.query.filter_by(
                    user_id=self.author1.id,
                    type="like",
                    related_id=post_by_author.id,
                ).count()
                self.assertEqual(notifications_count, 1)

                mock_author_queue.put_nowait.assert_not_called()
            self.logout()

    def test_like_own_post_does_not_send_notification_or_dispatch_sse(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.user_notification_queues") as mock_user_notification_queues:
                mock_own_queue = MagicMock()
                mock_user_notification_queues.get.return_value = [mock_own_queue]
                mock_user_notification_queues.__contains__.return_value = (
                    False  # Should not find queue for self
                )

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

                mock_user_notification_queues.__contains__.assert_not_called()
                mock_own_queue.put_nowait.assert_not_called()

            self.logout()

    def test_anonymous_user_cannot_like_post(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.user_notification_queues") as mock_user_notification_queues:
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

    def test_like_non_existent_post(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.user_notification_queues") as mock_user_notification_queues:
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
