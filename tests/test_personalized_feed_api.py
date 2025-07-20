import unittest
import json
from unittest.mock import patch, ANY
from datetime import datetime, timedelta, timezone

from social_app.models.db_models import Friendship
from social_app.models.db_models import (
    User,
    Post,
    Event,
    Poll,
    PollOption,
    Like,
    Comment,
    EventRSVP,
    PollVote,
)
from tests.test_base import AppTestCase
from flask import url_for


class TestPersonalizedFeedAPI(AppTestCase):

    def setUp(self):
        super().setUp()

    def test_personalized_feed_unauthorized(self):
        with self.app.app_context():
            response = self.client.get(url_for("personalizedfeedresource"))
            self.assertEqual(response.status_code, 401)
            data = json.loads(response.data)
            self.assertIn("msg", data)
            self.assertEqual(data["msg"], "Missing Authorization Header")

    def test_personalized_feed_success_and_structure(self):
        self._create_db_friendship(self.user1, self.user2, status="accepted")

        post1_by_user3 = self._create_db_post(
            user_id=self.user3_id,
            title="Post by User3, Liked by User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        self._create_db_like(
            user_id=self.user2_id,
            post_id=post1_by_user3.id,
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=30),
        )

        post2_by_user3 = self._create_db_post(
            user_id=self.user3_id,
            title="Another Post by User3, Commented by User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        self._create_db_comment(
            user_id=self.user2_id,
            post_id=post2_by_user3.id,
            content="Friend comment",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        event1_by_user3 = self._create_db_event(
            user_id=self.user3_id,
            title="Event by User3, User2 Attending",
            date_str=(datetime.now(timezone.utc) + timedelta(days=1)).strftime(
                "%Y-%m-%d"
            ),
        )
        self._create_db_event_rsvp(
            user_id=self.user2_id, event_id=event1_by_user3.id, status="Attending"
        )

        poll1_by_user2 = self._create_db_poll(
            user_id=self.user2_id, question="Poll by User2 (Friend)?"
        )
        with self.app.app_context():
            poll_for_options = self.db.session.merge(poll1_by_user2)
            self.assertTrue(len(poll_for_options.options) > 0)
            option_for_poll1 = poll_for_options.options[0]

            self._create_db_poll_vote(
                user_id=self.user3_id,
                poll_id=poll_for_options.id,
                poll_option_id=option_for_poll1.id,
            )
            poll1_by_user2 = poll_for_options

        with self.app.app_context():
            token = self._get_jwt_token(self.user1.username, "password")
            headers = {"Authorization": f"Bearer {token}"}

            response = self.client.get(
                url_for("personalizedfeedresource"), headers=headers
            )
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
        self.assertIn("feed_items", data)
        feed_items = data["feed_items"]
        self.assertIsInstance(feed_items, list)

        self.assertEqual(
            len(feed_items), 4, f"Expected 4 items, got {len(feed_items)}: {feed_items}"
        )

        found_post = False
        found_event = False
        found_poll = False
        timestamps = []

        for item in feed_items:
            self.assertIn("type", item)
            self.assertIn("id", item)
            self.assertIn("timestamp", item)
            self.assertIsNotNone(item["timestamp"])
            ts_str = item["timestamp"]
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
                timestamps.append(datetime.fromisoformat(ts_str).replace(tzinfo=None))
            else:
                timestamps.append(datetime.fromisoformat(ts_str))

            if item["type"] == "post":
                found_post = True
                self.assertIn("title", item)
                self.assertIn("content", item)
                self.assertIn("author_username", item)
                self.assertIn("reason", item)
                if post1_by_user3 and item["id"] == post1_by_user3.id:
                    self.assertEqual(item["title"], "Post by User3, Liked by User2")
            elif item["type"] == "event":
                found_event = True
                self.assertIn("title", item)
                self.assertIn("description", item)
                self.assertIn("organizer_username", item)
                if event1_by_user3 and item["id"] == event1_by_user3.id:
                    self.assertEqual(item["title"], "Event by User3, User2 Attending")
            elif item["type"] == "poll":
                found_poll = True
                self.assertIn("question", item)
                self.assertIn("creator_username", item)
                self.assertIn("options", item)
                self.assertIsInstance(item["options"], list)
                if item["options"]:
                    self.assertIn("text", item["options"][0])
                    self.assertIn("vote_count", item["options"][0])
                if poll1_by_user2 and item["id"] == poll1_by_user2.id:
                    self.assertEqual(item["question"], "Poll by User2 (Friend)?")

        self.assertTrue(found_post)
        self.assertTrue(found_event)
        self.assertTrue(found_poll)

        if timestamps:
            for i in range(len(timestamps) - 1):
                self.assertGreaterEqual(timestamps[i], timestamps[i + 1])

    def test_personalized_feed_empty(self):
        with self.app.app_context():
            token = self._get_jwt_token(self.user3.username, "password")
            headers = {"Authorization": f"Bearer {token}"}

            response = self.client.get(
                url_for("personalizedfeedresource"), headers=headers
            )
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIn("feed_items", data)
            self.assertEqual(data["feed_items"], [])

    def test_personalized_feed_excludes_own_content_interacted_by_friends(self):
        self._create_db_friendship(self.user1, self.user2, status="accepted")

        post_by_user1 = self._create_db_post(
            user_id=self.user1_id,
            title="User1 Own Post",
            content="Content by User1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        self._create_db_like(
            user_id=self.user2_id,
            post_id=post_by_user1.id,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=4),
        )

        event_by_user1 = self._create_db_event(
            user_id=self.user1_id,
            title="User1 Own Event",
            description="Event by User1",
            date_str=(datetime.now(timezone.utc) + timedelta(days=1)).strftime(
                "%Y-%m-%d"
            ),
        )
        with self.app.app_context():
            event_by_user1_merged = self.db.session.merge(event_by_user1)
            event_by_user1_merged.created_at = datetime.now(timezone.utc) - timedelta(
                hours=3
            )
            self.db.session.commit()
            event_by_user1 = event_by_user1_merged

        with self.app.app_context():
            event_for_rsvp = self.db.session.merge(event_by_user1)
            self._create_db_event_rsvp(
                user_id=self.user2_id,
                event_id=event_for_rsvp.id,
                status="Attending",
                timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            )
            event_by_user1 = event_for_rsvp

        poll_by_user1 = self._create_db_poll(
            user_id=self.user1_id, question="User1 Own Poll?"
        )
        with self.app.app_context():
            poll_by_user1_merged = self.db.session.merge(poll_by_user1)
            poll_by_user1_merged.created_at = datetime.now(timezone.utc) - timedelta(
                hours=1
            )
            self.db.session.commit()
            poll_by_user1 = poll_by_user1_merged

        with self.app.app_context():
            poll_for_vote_options = self.db.session.merge(poll_by_user1)
            self.assertTrue(len(poll_for_vote_options.options) > 0)
            option_for_poll1 = poll_for_vote_options.options[0]

            self._create_db_poll_vote(
                user_id=self.user2_id,
                poll_id=poll_for_vote_options.id,
                poll_option_id=option_for_poll1.id,
                created_at=datetime.now(timezone.utc) - timedelta(minutes=45),
            )
            poll_by_user1 = poll_for_vote_options

        post_by_user3 = self._create_db_post(
            user_id=self.user3_id,
            title="User3 Post for Feed",
            content="Content by User3",
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        self.like_on_user3_post_timestamp = datetime.now(timezone.utc) - timedelta(
            minutes=15
        )
        self._create_db_like(
            user_id=self.user2_id,
            post_id=post_by_user3.id,
            timestamp=self.like_on_user3_post_timestamp,
        )

        self.control_post_id = post_by_user3.id
        self.control_post_title = post_by_user3.title
        self.excluded_post_id = post_by_user1.id
        self.excluded_event_id = event_by_user1.id
        self.excluded_poll_id = poll_by_user1.id

        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.get("/api/personalized-feed", headers=headers)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("feed_items", data)
        feed_items = data["feed_items"]
        self.assertEqual(
            len(feed_items),
            1,
            f"Expected 1 item in feed, but got {len(feed_items)}: {feed_items}",
        )

        if len(feed_items) == 1:
            control_item = feed_items[0]
            self.assertEqual(control_item["type"], "post")
            self.assertEqual(control_item["id"], self.control_post_id)
            self.assertEqual(control_item["title"], self.control_post_title)
            self.assertIn("reason", control_item)
            expected_reason_fragment = f"Liked by your friend {self.user2.username}"
            self.assertIn(expected_reason_fragment, control_item["reason"])

        for item in feed_items:
            if item["type"] == "post":
                self.assertNotEqual(item["id"], self.excluded_post_id)
            elif item["type"] == "event":
                self.assertNotEqual(item["id"], self.excluded_event_id)
            elif item["type"] == "poll":
                self.assertNotEqual(item["id"], self.excluded_poll_id)

    def test_feed_excludes_content_interacted_by_removed_friend(self):
        with self.app.app_context():
            self._create_db_friendship(self.user1, self.user2, status="accepted")

            post_by_user3 = self._create_db_post(
                user_id=self.user3_id, title="Post by User3, to be liked by User2"
            )
            self.target_post_id = post_by_user3.id
            self._create_db_like(user_id=self.user2_id, post_id=self.target_post_id)

            token_user1 = self._get_jwt_token(self.user1.username, "password")
            headers_user1 = {"Authorization": f"Bearer {token_user1}"}

            with self.app.app_context():
                response = self.client.get(
                    url_for("personalizedfeedresource"), headers=headers_user1
                )
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            feed_items = data.get("feed_items", [])
            found_post_in_feed = False
            for item in feed_items:
                if item.get("type") == "post" and item.get("id") == self.target_post_id:
                    found_post_in_feed = True
                    self.assertIn(
                        f"Liked by your friend {self.user2.username}",
                        item.get("reason", ""),
                    )
                    break
            self.assertTrue(found_post_in_feed)

            with self.app.app_context():
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
                if friendship_record:
                    self.db.session.delete(friendship_record)
                    self.db.session.commit()

            response_after_unfriend = self.client.get(
                url_for("personalizedfeedresource"), headers=headers_user1
            )
            self.assertEqual(response_after_unfriend.status_code, 200)
            data_after_unfriend = json.loads(response_after_unfriend.data)
            feed_items_after_unfriend = data_after_unfriend.get("feed_items", [])
            found_post_after_unfriend = False
            for item in feed_items_after_unfriend:
                if item.get("type") == "post" and item.get("id") == self.target_post_id:
                    found_post_after_unfriend = True
                    break
            self.assertFalse(found_post_after_unfriend)

    def test_feed_excludes_posts_from_removed_friend(self):
        with self.app.app_context():
            self._create_db_friendship(self.user1, self.user2, status="accepted")
            post_by_user2 = self._create_db_post(
                user_id=self.user2_id,
                title="Post by User2",
                content="Content by User2, friend of User1",
                timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            token_user1 = self._get_jwt_token(self.user1.username, "password")
            headers_user1 = {"Authorization": f"Bearer {token_user1}"}
            with self.app.app_context():
                response = self.client.get(
                    url_for("personalizedfeedresource"), headers=headers_user1
                )
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            feed_items = data.get("feed_items", [])
            found_post_while_friend = False
            for item in feed_items:
                if item.get("type") == "post" and item.get("id") == post_by_user2.id:
                    found_post_while_friend = True
                    self.assertIn(self.user2.username, item.get("reason", ""))
                    break
            self.assertTrue(found_post_while_friend)

            with self.app.app_context():
                friendship_record = Friendship.query.filter(
                    (
                        (Friendship.user_id == self.user1_id)
                        & (Friendship.friend_id == self.user2_id)
                        & (Friendship.status == "accepted")
                    )
                    | (
                        (Friendship.user_id == self.user2_id)
                        & (Friendship.friend_id == self.user1_id)
                        & (Friendship.status == "accepted")
                    )
                ).first()
                self.assertIsNotNone(friendship_record)
                if friendship_record:
                    self.db.session.delete(friendship_record)
                    self.db.session.commit()

            response_after_unfriend = self.client.get(
                url_for("personalizedfeedresource"), headers=headers_user1
            )
            self.assertEqual(response_after_unfriend.status_code, 200)
            data_after_unfriend = json.loads(response_after_unfriend.data)
            feed_items_after_unfriend = data_after_unfriend.get("feed_items", [])
            found_post_after_unfriend = False
            for item in feed_items_after_unfriend:
                if item.get("type") == "post" and item.get("id") == post_by_user2.id:
                    found_post_after_unfriend = True
                    break
            self.assertFalse(found_post_after_unfriend)
