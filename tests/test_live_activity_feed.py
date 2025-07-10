import unittest
from unittest.mock import (
    patch,
    call,
    ANY,
    MagicMock,
)
from datetime import datetime, timedelta, timezone
from werkzeug.security import (
    generate_password_hash,
)

from io import BytesIO
from flask import url_for
from social_app import db
from social_app.models.db_models import User, UserActivity, Friendship, Post
from tests.test_base import AppTestCase


def _create_db_user_activity(
    user_id,
    activity_type,
    related_id=None,
    target_user_id=None,
    content_preview=None,
    link=None,
    timestamp=None,
):
    activity = UserActivity(
        user_id=user_id,
        activity_type=activity_type,
        related_id=related_id,
        target_user_id=target_user_id,
        content_preview=content_preview,
        link=link,
        timestamp=timestamp or datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()
    return activity


class TestLiveActivityFeed(AppTestCase):

    def setUp(self):
        super().setUp()
        self._create_db_friendship(self.user2, self.user1, status="accepted")
        self._create_db_friendship(self.user2, self.user3, status="accepted")

    @patch("social_app.core.views.current_app.user_notification_queues")
    @patch("social_app.services.achievements.check_and_award_achievements")
    def test_new_follow_activity_logging_and_sse_dispatch(
        self, mock_check_achievements, mock_user_notification_queues
    ):
        with self.app.app_context():
            mock_friend_queue = MagicMock()
            # Simulate that user3 (a friend of user2, the one accepting the request) has an active queue
            def contains_side_effect(user_id_to_check):
                return user_id_to_check == self.user3.id

            def get_side_effect(user_id_to_get, default=None):
                if user_id_to_get == self.user3.id:
                    return [mock_friend_queue]
                return default if default is not None else []

            mock_user_notification_queues.__contains__.side_effect = contains_side_effect
            mock_user_notification_queues.get.side_effect = get_side_effect

            existing_friendship = Friendship.query.filter(
                (
                    (Friendship.user_id == self.user1.id)
                    & (Friendship.friend_id == self.user2.id)
                )
                | (
                    (Friendship.user_id == self.user2.id)
                    & (Friendship.friend_id == self.user1.id)
                )
            ).first()
            if existing_friendship:
                db.session.delete(existing_friendship)
                db.session.commit()

            friend_request_id = self._create_db_friendship(
                self.user1, self.user2, status="pending"
            ).id
            self.assertIsNotNone(friend_request_id)

        self.login(self.user2.username, "password")
        response = self.client.post(
            url_for('core.accept_friend_request', request_id=friend_request_id), follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Friend request accepted successfully!", response.get_data(as_text=True))

        with self.app.app_context():
            activity = (
                UserActivity.query.filter_by(
                    user_id=self.user2.id, activity_type="new_follow"
                )
                .order_by(UserActivity.timestamp.desc())
                .first()
            )
            self.assertIsNotNone(activity)
            self.assertEqual(activity.related_id, None)
            self.assertEqual(activity.target_user_id, self.user1.id)
            self.assertIsNotNone(activity.link)
            self.assertTrue(self.user1.username in activity.link)

            user2_profile_pic = (
                self.user2.profile_picture
                if self.user2.profile_picture
                else "/static/profile_pics/default.png"
            )

            expected_payload = {
                "activity_id": activity.id,
                "user_id": self.user2.id,
                "username": self.user2.username,
                "profile_picture": ANY,
                "activity_type": "new_follow",
                "related_id": None,
                "content_preview": activity.content_preview,
                "link": activity.link,
                "timestamp": ANY,
                "target_user_id": self.user1.id,
                "target_username": self.user1.username,
            }

            user2_updated = self.db.session.get(User, self.user2.id)
            # The emit_new_activity_event function in views.py will iterate through friends.
            # We need to ensure our mock setup correctly intercepts the call for user3.

            # Check that user3's queue was checked and accessed
            mock_user_notification_queues.__contains__.assert_any_call(self.user3.id)
            mock_user_notification_queues.get.assert_any_call(self.user3.id)

            # Check that put_nowait was called on user3's queue
            mock_friend_queue.put_nowait.assert_called_once()
            args, _ = mock_friend_queue.put_nowait.call_args
            sse_event_data = args[0]

            self.assertEqual(sse_event_data['type'], "new_activity") # This should match emit_new_activity_event in views

            # Compare payload contents, allowing for ANY for timestamp and profile_picture if dynamic
            payload_sent = sse_event_data['payload']
            self.assertEqual(payload_sent['activity_id'], expected_payload['activity_id'])
            self.assertEqual(payload_sent['user_id'], expected_payload['user_id'])
            self.assertEqual(payload_sent['username'], expected_payload['username'])
            # self.assertEqual(payload_sent['profile_picture'], expected_payload['profile_picture']) # Can be ANY
            self.assertEqual(payload_sent['activity_type'], expected_payload['activity_type'])
            self.assertEqual(payload_sent['related_id'], expected_payload['related_id'])
            self.assertEqual(payload_sent['content_preview'], expected_payload['content_preview'])
            self.assertEqual(payload_sent['link'], expected_payload['link'])
            self.assertEqual(payload_sent['target_user_id'], expected_payload['target_user_id'])
            self.assertEqual(payload_sent['target_username'], expected_payload['target_username'])
            self.assertIn('timestamp', payload_sent)


            self.assertTrue(mock_check_achievements.called)
            mock_check_achievements.assert_any_call(self.user2.id)
            mock_check_achievements.assert_any_call(self.user1.id)

        self.logout()

    def test_live_feed_unauthorized_access(self):
        response = self.client.get(url_for('core.live_feed'), follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn(url_for('core.login'), response.location)

    def test_live_feed_authorized_access_and_data(self):
        with self.app.app_context():
            post_by_user2_title = "User2's Exciting Post"
            post_by_user2_content = "Content by User2 for live feed."
            post_by_user2 = Post(
                user_id=self.user2.id,
                title=post_by_user2_title,
                content=post_by_user2_content,
            )
            db.session.add(post_by_user2)
            db.session.commit()
            post_by_user2_id_val = post_by_user2.id
            post_by_user2_content_preview = post_by_user2_content[:100]

            activity1 = _create_db_user_activity(
                user_id=self.user2.id,
                activity_type="new_post",
                related_id=post_by_user2_id_val,
                content_preview=post_by_user2_content_preview,
                link=f"/blog/post/{post_by_user2_id_val}",
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
            )

            post_by_user3_title = "User3's Post"
            post_by_user3_content = "A post by user3."
            post_by_user3 = Post(
                user_id=self.user3.id,
                title=post_by_user3_title,
                content=post_by_user3_content,
            )
            db.session.add(post_by_user3)
            db.session.commit()
            post_by_user3_id_val = post_by_user3.id
            comment_by_user2_content = "User2 commenting on User3's post"
            activity2 = _create_db_user_activity(
                user_id=self.user2.id,
                activity_type="new_comment",
                related_id=post_by_user3_id_val,
                content_preview=comment_by_user2_content[:100],
                link=f"/blog/post/{post_by_user3_id_val}",
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
            )

            activity3 = _create_db_user_activity(
                user_id=self.user2.id,
                activity_type="new_follow",
                target_user_id=self.user3.id,
                link=f"/user/{self.user3.username}",
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=2),
            )

        self.login(self.user1.username, "password")
        response = self.client.get(url_for('core.live_feed'))
        self.assertEqual(response.status_code, 200)

        response_data = response.get_data(as_text=True)

        self.assertIn(self.user2.username, response_data)

        self.assertIn("created a new post:", response_data)
        self.assertIn(post_by_user2_content_preview, response_data)
        self.assertIn(f"/blog/post/{post_by_user2_id_val}", response_data)

        self.assertIn("commented on a post:", response_data)
        escaped_comment_content = comment_by_user2_content[:100].replace("'", "&#39;")
        self.assertIn(escaped_comment_content, response_data)
        self.assertIn(f"/blog/post/{post_by_user3_id_val}", response_data)

        self.assertIn("started following", response_data)
        self.assertIn(f"/user/{self.user3.username}", response_data)
        self.assertIn(self.user3.username, response_data)

        self_activity_post = "A post by user1 just for this check"
        with self.app.app_context():
            _create_db_user_activity(
                user_id=self.user1.id,
                activity_type="new_post",
                content_preview=self_activity_post,
            )

        response_after_self_activity = self.client.get(url_for('core.live_feed'))
        response_data_after_self_activity = response_after_self_activity.get_data(as_text=True)
        self.assertNotIn(self_activity_post, response_data_after_self_activity)

        self.logout()

    @patch("social_app.core.views.emit_new_activity_event")
    @patch("social_app.services.achievements.check_and_award_achievements")
    def test_new_post_activity_logging_and_sse_dispatch(
        self, mock_check_achievements, mock_emit_new_activity_event
    ):
        self.login(self.user2.username, "password")
        post_title = "My Test Post for Activity"
        post_content = "This is the content of the test post."
        post_hashtags = "test,activity"

        response = self.client.post(
            url_for('core.create_post'),
            data={
                "title": post_title,
                "content": post_content,
                "hashtags": post_hashtags,
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Blog post created successfully!", response.get_data(as_text=True))

        with self.app.app_context():
            activity = (
                UserActivity.query.filter_by(
                    user_id=self.user2.id, activity_type="new_post"
                )
                .order_by(UserActivity.timestamp.desc())
                .first()
            )
            self.assertIsNotNone(activity)

            created_post = self.db.session.get(Post, activity.related_id)
            self.assertIsNotNone(created_post)
            self.assertEqual(created_post.title, post_title)
            self.assertEqual(activity.user_id, self.user2.id)
            self.assertEqual(activity.content_preview, post_content[:100])
            self.assertTrue(f"/blog/post/{created_post.id}" in activity.link)

            mock_emit_new_activity_event.assert_called_once_with(activity)
            mock_check_achievements.assert_called_with(self.user2.id)

        self.logout()

    @patch("social_app.core.views.emit_new_activity_event")
    @patch("social_app.services.achievements.check_and_award_achievements")
    def test_new_comment_activity_logging_and_sse_dispatch(
        self, mock_check_achievements, mock_emit_new_activity_event
    ):
        with self.app.app_context():
            post_by_user1_obj = self._create_db_post(
                user_id=self.user1.id, title="Post to be commented on"
            )
            self.assertIsNotNone(post_by_user1_obj)

        self.login(self.user2.username, "password")
        comment_content = "This is a test comment on user1's post."
        response = self.client.post(
            url_for('core.add_comment', post_id=post_by_user1_obj.id),
            data={"comment_content": comment_content},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Comment added successfully!", response.get_data(as_text=True))

        with self.app.app_context():
            activity = (
                UserActivity.query.filter_by(
                    user_id=self.user2.id, activity_type="new_comment"
                )
                .order_by(UserActivity.timestamp.desc())
                .first()
            )
            self.assertIsNotNone(activity)
            self.assertEqual(activity.related_id, post_by_user1_obj.id)
            self.assertEqual(activity.user_id, self.user2.id)
            self.assertEqual(activity.content_preview, comment_content[:100])
            self.assertTrue(f"/blog/post/{post_by_user1_obj.id}" in activity.link)

            mock_emit_new_activity_event.assert_called_once_with(activity)
            mock_check_achievements.assert_called_with(self.user2.id)

        self.logout()

    @patch("social_app.core.views.emit_new_activity_event")
    @patch("social_app.services.achievements.check_and_award_achievements")
    def test_new_like_activity_logging_and_sse_dispatch(
        self, mock_check_achievements, mock_emit_new_activity_event
    ):
        with self.app.app_context():
            post_by_user1_obj = self._create_db_post(
                user_id=self.user1.id, title="Post to be liked by user2"
            )
            self.assertIsNotNone(post_by_user1_obj)

        self.login(self.user2.username, "password")
        response = self.client.post(
            url_for('core.like_post', post_id=post_by_user1_obj.id), follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Post liked!", response.get_data(as_text=True))

        with self.app.app_context():
            activity = (
                UserActivity.query.filter_by(
                    user_id=self.user2.id, activity_type="new_like"
                )
                .order_by(UserActivity.timestamp.desc())
                .first()
            )
            self.assertIsNotNone(activity)
            self.assertEqual(activity.related_id, post_by_user1_obj.id)
            self.assertEqual(activity.user_id, self.user2.id)
            self.assertEqual(
                activity.content_preview,
                post_by_user1_obj.content[:100] if post_by_user1_obj.content else "",
            )
            self.assertTrue(f"/blog/post/{post_by_user1_obj.id}" in activity.link)

            mock_emit_new_activity_event.assert_called_once_with(activity)
            mock_check_achievements.assert_not_called()

        self.logout()

    def test_live_feed_empty_for_friends_with_no_activity(self):
        """Test live feed when friends have no activities."""
        self.login(self.user1.username, "password")
        response = self.client.get("/live_feed")
        self.assertEqual(response.status_code, 200)
        html_content = response.get_data(as_text=True)
        self.assertIn('id="no-activity-message"', html_content)
        self.assertIn("No recent activity from your friends", html_content)
        self.assertNotIn(f"{self.user2.username} created a new post", html_content)
        self.assertNotIn(f"{self.user2.username} commented on a post", html_content)
        self.assertNotIn(f"{self.user2.username} started following", html_content)
        self.assertNotIn(f"{self.user3.username} created a new post", html_content)
        self.assertNotIn(f"{self.user3.username} commented on a post", html_content)
        self.assertNotIn(f"{self.user3.username} started following", html_content)
        self.logout()

    @patch("social_app.core.views.emit_new_activity_event")
    @patch("social_app.services.achievements.check_and_award_achievements")
    def test_new_share_activity_logging_and_sse_dispatch(
        self, mock_check_achievements, mock_emit_new_activity_event
    ):
        self.login(self.user2.username, "password")

        with self.app.app_context():
            original_post_title = "Original Post by User1"
            original_post_content = "This post will be shared."
            post_by_user1_id = self._create_db_post(
                user_id=self.user1.id,
                title=original_post_title,
                content=original_post_content,
            )
            self.assertIsNotNone(post_by_user1_id)
            self.original_post_object = post_by_user1_id
            self.original_post_id = post_by_user1_id.id
            self.original_post_content_preview = original_post_content[:100]

        sharing_comment_text = "Check out this cool post I found!"
        response = self.client.post(
            f"/post/{self.original_post_id}/share",
            data={"sharing_comment": sharing_comment_text},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Post shared successfully!", response.get_data(as_text=True))
        self.sharing_comment_text = sharing_comment_text

        with self.app.app_context():
            activity = (
                UserActivity.query.filter_by(
                    user_id=self.user2.id, activity_type="shared_a_post"
                )
                .order_by(UserActivity.timestamp.desc())
                .first()
            )
            self.assertIsNotNone(activity)
            self.assertEqual(activity.user_id, self.user2.id)
            self.assertEqual(activity.related_id, self.original_post_id)
            self.assertEqual(activity.content_preview, self.sharing_comment_text[:100])
            expected_link = url_for("core.view_post", post_id=self.original_post_id, _external=True)
            self.assertEqual(activity.link, expected_link)
            self.activity_id = activity.id

            mock_emit_new_activity_event.assert_called_once_with(activity)
        self.logout()

    @patch("social_app.core.views.emit_new_activity_event")
    @patch("social_app.services.achievements.check_and_award_achievements")
    def test_updated_profile_picture_activity_logging_and_sse_dispatch(
        self, mock_check_achievements, mock_emit_new_activity_event
    ):
        self.login(self.user1.username, "password")
        with self.app.app_context():
            user1_before_update = self.db.session.get(User, self.user1.id)
            original_profile_pic = user1_before_update.profile_picture
        image_content = b"dummy_image_content_for_test_profile_pic_update"
        image_file = BytesIO(image_content)
        data = {"profile_pic": (image_file, "test_profile.png")}
        response = self.client.post(
            url_for('core.upload_profile_picture'),
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Profile picture uploaded successfully!", response.get_data(as_text=True))

        with self.app.app_context():
            user1_after_update = self.db.session.get(User, self.user1.id)
            self.assertIsNotNone(user1_after_update.profile_picture)
            self.assertNotEqual(original_profile_pic, user1_after_update.profile_picture)
            self.assertTrue(user1_after_update.profile_picture.startswith("/static/profile_pics/"))
            self.assertTrue("test_profile.png" in user1_after_update.profile_picture)

        with self.app.app_context():
            activity = (
                UserActivity.query.filter_by(
                    user_id=self.user1.id,
                    activity_type="updated_profile_picture",
                )
                .order_by(UserActivity.timestamp.desc())
                .first()
            )
            self.assertIsNotNone(activity)
            self.assertEqual(activity.user_id, self.user1.id)
            self.assertIsNone(activity.related_id)
            self.assertEqual(activity.content_preview, "Updated their profile picture.")
            expected_link = url_for("core.user_profile", username=self.user1.username, _external=True)
            self.assertEqual(activity.link, expected_link)

            mock_emit_new_activity_event.assert_called_once_with(activity)
        mock_check_achievements.assert_not_called()
        self.logout()
