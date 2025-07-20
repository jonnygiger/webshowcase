import unittest
from unittest.mock import patch, ANY, MagicMock  # Added MagicMock
from datetime import datetime, timedelta, timezone

from social_app.models.db_models import (
    User,
    Post,
    FriendPostNotification,
    UserBlock,
    Friendship,
)
from tests.test_base import AppTestCase


class TestFriendPostNotifications(AppTestCase):

    def _make_post_via_route(self, username, password, title, content, hashtags=""):
        """Logs in a user, creates a post via the /blog/create route, and logs out."""
        self.login(username, password)
        response = self.client.post(
            "/blog/create",  # Assuming core.create_post is the correct endpoint
            data={"title": title, "content": content, "hashtags": hashtags},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.logout()

    def test_notification_creation_and_sse_dispatch(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.user_notification_queues") as mock_user_notification_queues:
                mock_friend_queue = MagicMock()
                mock_user_notification_queues.get.return_value = [mock_friend_queue]
                mock_user_notification_queues.__contains__.return_value = True

                self._create_db_friendship(self.user1, self.user2, status="accepted")

                post_title = "User A's Exciting Post"
                self._make_post_via_route(
                    self.user1.username,
                    "password",
                    title=post_title,
                    content="Content here",
                )

                created_post = Post.query.filter_by(
                    user_id=self.user1_id, title=post_title
                ).first()
                self.assertIsNotNone(created_post)

                notification_for_b = FriendPostNotification.query.filter_by(
                    user_id=self.user2_id, post_id=created_post.id, poster_id=self.user1_id
                ).first()
                self.assertIsNotNone(notification_for_b)
                self.assertFalse(notification_for_b.is_read)

                notification_for_a = FriendPostNotification.query.filter_by(
                    user_id=self.user1_id, post_id=created_post.id
                ).first()
                self.assertIsNone(notification_for_a)

                notification_for_c = FriendPostNotification.query.filter_by(
                    user_id=self.user3_id, post_id=created_post.id
                ).first()
                self.assertIsNone(notification_for_c)

                expected_sse_payload = {
                    "notification_id": notification_for_b.id,
                    "post_id": created_post.id,
                    "post_title": created_post.title,
                    "poster_username": self.user1.username,
                    "timestamp": ANY,
                }

                mock_user_notification_queues.__contains__.assert_any_call(self.user2_id)
                mock_friend_queue.put_nowait.assert_called_once()

                args, _ = mock_friend_queue.put_nowait.call_args
                sse_event_data = args[0]
                self.assertEqual(sse_event_data["type"], "new_friend_post")

                payload_sent = sse_event_data["payload"]
                self.assertEqual(
                    payload_sent["notification_id"], expected_sse_payload["notification_id"]
                )
                self.assertEqual(payload_sent["post_id"], expected_sse_payload["post_id"])
                self.assertEqual(
                    payload_sent["post_title"], expected_sse_payload["post_title"]
                )
                self.assertEqual(
                    payload_sent["poster_username"], expected_sse_payload["poster_username"]
                )
                self.assertIn("timestamp", payload_sent)

    def test_view_friend_post_notifications_page(self):
        with self.app.app_context():
            self._create_db_friendship(self.user1, self.user2)
            post1_obj_by_user1 = self._create_db_post(
                user_id=self.user1_id,
                title="Post 1 by User1",
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
            )
            self.assertIsNotNone(post1_obj_by_user1)
            notif1_for_user2 = FriendPostNotification(
                user_id=self.user2_id,
                post_id=post1_obj_by_user1.id,
                poster_id=self.user1_id,
                timestamp=post1_obj_by_user1.timestamp,
            )

            self._create_db_friendship(self.user3, self.user2)
            post2_obj_by_user3 = self._create_db_post(
                user_id=self.user3_id,
                title="Post 2 by User3",
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
            self.assertIsNotNone(post2_obj_by_user3)
            notif2_for_user2 = FriendPostNotification(
                user_id=self.user2_id,
                post_id=post2_obj_by_user3.id,
                poster_id=self.user3_id,
                timestamp=post2_obj_by_user3.timestamp,
            )

            self.db.session.add_all([notif1_for_user2, notif2_for_user2])
            self.db.session.commit()

            self.login(self.user2.username, "password")
            response = self.client.get("/friend_post_notifications")
            self.assertEqual(response.status_code, 200)
            response_data = response.get_data(as_text=True)

            self.assertIn(self.user3.username, response_data)
            self.assertIn(post2_obj_by_user3.title, response_data)
            self.assertIn(self.user1.username, response_data)
            self.assertIn(post1_obj_by_user1.title, response_data)

            self.assertTrue(
                response_data.find(post2_obj_by_user3.title)
                < response_data.find(post1_obj_by_user1.title)
            )
            self.logout()

    def test_mark_one_notification_as_read(self):
        with self.app.app_context():
            self._create_db_friendship(self.user1, self.user2)
            post_obj_by_user1 = self._create_db_post(user_id=self.user1_id)
            self.assertIsNotNone(post_obj_by_user1)
            notification = FriendPostNotification(
                user_id=self.user2_id,
                post_id=post_obj_by_user1.id,
                poster_id=self.user1_id,
                is_read=False,
            )
            self.db.session.add(notification)
            self.db.session.commit()
            notification_id = notification.id

            self.assertFalse(
                self.db.session.get(FriendPostNotification, notification_id).is_read
            )

            self.login(self.user2.username, "password")
            response = self.client.post(
                f"/friend_post_notifications/mark_as_read/{notification_id}"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json,
                {"status": "success", "message": "Marked as read."},
            )
            self.assertTrue(
                self.db.session.get(FriendPostNotification, notification_id).is_read
            )
            self.logout()

            notification_db = self.db.session.get(
                FriendPostNotification, notification_id
            )
            notification_db.is_read = False
            self.db.session.commit()
            self.assertFalse(
                self.db.session.get(FriendPostNotification, notification_id).is_read
            )

            self.login(self.user3.username, "password")
            response = self.client.post(
                f"/friend_post_notifications/mark_as_read/{notification_id}"
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(
                response.json, {"status": "error", "message": "Unauthorized."}
            )
            self.assertFalse(
                self.db.session.get(FriendPostNotification, notification_id).is_read
            )
            self.logout()

            self.login(self.user2.username, "password")
            response = self.client.post(
                f"/friend_post_notifications/mark_as_read/99999"
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(
                response.json, {"status": "error", "message": "Not found."}
            )
            self.logout()

    def test_mark_all_notifications_as_read(self):
        with self.app.app_context():
            self._create_db_friendship(self.user1, self.user2)
            post1_obj = self._create_db_post(user_id=self.user1_id, title="Post1")
            post2_obj = self._create_db_post(user_id=self.user1_id, title="Post2")
            self.assertIsNotNone(post1_obj)
            self.assertIsNotNone(post2_obj)

            notif1 = FriendPostNotification(
                user_id=self.user2_id,
                post_id=post1_obj.id,
                poster_id=self.user1_id,
                is_read=False,
            )
            notif2 = FriendPostNotification(
                user_id=self.user2_id,
                post_id=post2_obj.id,
                poster_id=self.user1_id,
                is_read=False,
            )
            notif_for_user3 = FriendPostNotification(
                user_id=self.user3_id,
                post_id=post1_obj.id,
                poster_id=self.user1_id,
                is_read=False,
            )

            self.db.session.add_all([notif1, notif2, notif_for_user3])
            self.db.session.commit()
            notif1_id, notif2_id, notif3_id = notif1.id, notif2.id, notif_for_user3.id

            self.login(self.user2.username, "password")
            response = self.client.post("/friend_post_notifications/mark_all_as_read")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json,
                {
                    "status": "success",
                    "message": "All marked as read.",
                },
            )

            self.assertTrue(
                self.db.session.get(FriendPostNotification, notif1_id).is_read
            )
            self.assertTrue(
                self.db.session.get(FriendPostNotification, notif2_id).is_read
            )
            self.assertFalse(
                self.db.session.get(FriendPostNotification, notif3_id).is_read
            )
            self.logout()

            self.login(self.user2.username, "password")
            response = self.client.post("/friend_post_notifications/mark_all_as_read")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json,
                {
                    "status": "success",
                    "message": "No unread notifications.",
                },
            )
            self.logout()

    def test_no_notification_for_own_post(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.user_notification_queues") as mock_user_notification_queues:
                mock_own_queue = MagicMock()
                mock_user_notification_queues.get.return_value = [mock_own_queue]
                # Simulate user1 is not in queues for their own post notification
                mock_user_notification_queues.__contains__.return_value = False

                post_title = "My Own Test Post"
                post_content = "This is content of my own post."
                self._make_post_via_route(
                    self.user1.username, "password", title=post_title, content=post_content
                )

                created_post = Post.query.filter_by(
                    user_id=self.user1_id, title=post_title
                ).first()
                self.assertIsNotNone(created_post)

                notification_for_self = FriendPostNotification.query.filter_by(
                    user_id=self.user1_id, post_id=created_post.id
                ).first()
                self.assertIsNone(notification_for_self)

                # Check that user1's queue was not accessed for putting a new_friend_post event
                mock_user_notification_queues.__contains__.assert_not_called()
                mock_own_queue.put_nowait.assert_not_called()

    def test_no_notification_for_post_before_friendship(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.user_notification_queues") as mock_user_notification_queues:
                mock_friend_queue = MagicMock()
                mock_user_notification_queues.get.return_value = [mock_friend_queue]
                mock_user_notification_queues.__contains__.return_value = False

                post_title = "Post Before Friendship"
                post_content = "Content of post made before friendship"
                self._make_post_via_route(
                    self.user1.username, "password", title=post_title, content=post_content
                )

                created_post = Post.query.filter_by(
                    user_id=self.user1_id, title=post_title
                ).first()
                self.assertIsNotNone(created_post)

                # Create friendship AFTER the post
                self._create_db_friendship(self.user1, self.user2, status="accepted")

                notification_for_user2 = FriendPostNotification.query.filter_by(
                    user_id=self.user2_id, post_id=created_post.id
                ).first()
                self.assertIsNone(notification_for_user2)

                mock_user_notification_queues.__contains__.assert_not_called()
                mock_friend_queue.put_nowait.assert_not_called()

    def test_no_notification_if_poster_is_blocked(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.user_notification_queues") as mock_user_notification_queues:
                mock_friend_queue = MagicMock()
                mock_user_notification_queues.get.return_value = [mock_friend_queue]
                mock_user_notification_queues.__contains__.return_value = False

                self._create_db_friendship(self.user1, self.user2, status="accepted")

                user_block = UserBlock(blocker_id=self.user2_id, blocked_id=self.user1_id)
                self.db.session.add(user_block)
                self.db.session.commit()

                post_title = "Post By Blocked User"
                post_content = "This content should not trigger a notification for User2"
                self._make_post_via_route(
                    self.user1.username, "password", title=post_title, content=post_content
                )

                created_post = Post.query.filter_by(
                    user_id=self.user1_id, title=post_title
                ).first()
                self.assertIsNotNone(created_post)

                notification_for_user2 = FriendPostNotification.query.filter_by(
                    user_id=self.user2_id, post_id=created_post.id, poster_id=self.user1_id
                ).first()
                self.assertIsNone(notification_for_user2)

                mock_user_notification_queues.__contains__.assert_not_called()
                mock_friend_queue.put_nowait.assert_not_called()

    def test_notification_persists_after_unfriend(self):
        with self.app.app_context():
            with patch("social_app.core.views.current_app.user_notification_queues") as mock_user_notification_queues:
                mock_friend_queue = MagicMock()  # Renamed for clarity
                mock_user_notification_queues.get.return_value = [mock_friend_queue]
                mock_user_notification_queues.__contains__.return_value = True

                self._create_db_friendship(self.user1, self.user2, status="accepted")

                post_title = "User A's Post Before Unfriend"
                self._make_post_via_route(
                    self.user1.username,
                    "password",
                    title=post_title,
                    content="Content relevant to this test",
                )

                created_post = Post.query.filter_by(
                    user_id=self.user1_id, title=post_title
                ).first()
                self.assertIsNotNone(created_post)

                notification_for_b = FriendPostNotification.query.filter_by(
                    user_id=self.user2_id, post_id=created_post.id, poster_id=self.user1_id
                ).first()
                self.assertIsNotNone(notification_for_b)
                self.assertFalse(notification_for_b.is_read)

                mock_friend_queue.put_nowait.assert_called_once()
                mock_friend_queue.reset_mock()
                mock_user_notification_queues.reset_mock()
                # After this point, we expect no more calls for user2 regarding new posts from user1

                friendship_record = Friendship.query.filter(
                    (
                        (Friendship.user_id == self.user1_id)
                        & (Friendship.friend_id == self.user2_id)
                    )
                    | (
                        (Friendship.user_id == self.user2_id)
                        & (Friendship.friend_id == self.user1_id)
                    ),
                    Friendship.status == "accepted",
                ).first()
                self.assertIsNotNone(friendship_record)

                self.db.session.delete(friendship_record)
                self.db.session.commit()

                deleted_friendship_record = Friendship.query.filter_by(
                    id=friendship_record.id
                ).first()
                self.assertIsNone(deleted_friendship_record)

                persisted_notification_for_b = self.db.session.get(
                    FriendPostNotification, notification_for_b.id
                )
                self.assertIsNotNone(persisted_notification_for_b)
                self.assertEqual(persisted_notification_for_b.user_id, self.user2_id)
                self.assertEqual(persisted_notification_for_b.post_id, created_post.id)
                self.assertEqual(persisted_notification_for_b.poster_id, self.user1_id)
                self.assertFalse(persisted_notification_for_b.is_read)

                # Make another post by user1 to ensure user2 doesn't get notified
                mock_user_notification_queues.__contains__.return_value = (
                    False  # Simulate user2 no longer has a relevant queue or is not checked
                )
                self._make_post_via_route(
                    self.user1.username,
                    "password",
                    title="User A's Post After Unfriend",
                    content="This should not notify user2.",
                )
                mock_friend_queue.put_nowait.assert_not_called()
                mock_user_notification_queues.__contains__.assert_not_called()
