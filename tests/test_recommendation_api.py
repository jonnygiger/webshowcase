import unittest
import json
from unittest.mock import patch, ANY
from datetime import datetime, timedelta, timezone

from social_app import create_app, db
from social_app.models.db_models import (
    User,
    Post,
    Group,
    Event,
    Poll,
    PollOption,
    Like,
    Comment,
    EventRSVP,
    PollVote,
    Friendship, # Added Friendship
)
from tests.test_base import AppTestCase


class TestRecommendationAPI(AppTestCase):

    def setUp(self):
        super().setUp()
        self.post_by_user2 = self._create_db_post(
            user_id=self.user2_id, title="User2's Post"
        )
        self.group_by_user2 = self._create_db_group(
            creator_id=self.user2_id, name="User2's Group"
        )
        self.event_by_user2 = self._create_db_event(
            user_id=self.user2_id,
            title="User2's Event",
            date_str=(datetime.now(timezone.utc) + timedelta(days=30)).strftime(
                "%Y-%m-%d"
            ),
        )
        self.poll_by_user2 = self._create_db_poll(
            user_id=self.user2_id, question="User2's Poll?"
        )

    def test_get_recommendations_success(self):
        response = self.client.get(f"/api/recommendations?user_id={self.user1_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")

        data = json.loads(response.data)

        self.assertIn("user_id", data)
        self.assertEqual(data["user_id"], self.user1_id)

        self.assertIn("suggested_posts", data)
        self.assertIsInstance(data["suggested_posts"], list)
        if data["suggested_posts"]:
            post = data["suggested_posts"][0]
            self.assertIn("id", post)
            self.assertIn("title", post)
            self.assertIn("author_username", post)

        self.assertIn("suggested_groups", data)
        self.assertIsInstance(data["suggested_groups"], list)
        if data["suggested_groups"]:
            group = data["suggested_groups"][0]
            self.assertIn("id", group)
            self.assertIn("name", group)
            self.assertIn("creator_username", group)

        self.assertIn("suggested_events", data)
        self.assertIsInstance(data["suggested_events"], list)
        if data["suggested_events"]:
            event = data["suggested_events"][0]
            self.assertIn("id", event)
            self.assertIn("title", event)
            self.assertIn("organizer_username", event)

        self.assertIn("suggested_users_to_follow", data)
        self.assertIsInstance(data["suggested_users_to_follow"], list)
        if data["suggested_users_to_follow"]:
            user = data["suggested_users_to_follow"][0]
            self.assertIn("id", user)
            self.assertIn("username", user)

        self.assertIn("suggested_polls_to_vote", data)
        self.assertIsInstance(data["suggested_polls_to_vote"], list)
        if data["suggested_polls_to_vote"]:
            poll = data["suggested_polls_to_vote"][0]
            self.assertIn("id", poll)
            self.assertIn("question", poll)
            self.assertIn("author_username", poll)
            self.assertIn("options", poll)
            self.assertIsInstance(poll["options"], list)
            if poll["options"]:
                option = poll["options"][0]
                self.assertIn("id", option)
                self.assertIn("text", option)
                self.assertIn("vote_count", option)

    def test_get_recommendations_invalid_user_id(self):
        response = self.client.get("/api/recommendations?user_id=99999")
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertIn("message", data)
        self.assertTrue("not found" in data["message"].lower())

    def test_get_recommendations_missing_user_id(self):
        response = self.client.get("/api/recommendations")
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("message", data)
        self.assertIn("user_id", data["message"])
        self.assertTrue("required" in data["message"]["user_id"].lower())

    def test_get_recommendations_no_suggestions(self):
        response = self.client.get(f"/api/recommendations?user_id={self.user3_id}")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertEqual(data["user_id"], self.user3_id)
        self.assertEqual(data["suggested_posts"], [])
        self.assertEqual(data["suggested_groups"], [])
        self.assertEqual(data["suggested_events"], [])
        self.assertIsInstance(data["suggested_users_to_follow"], list)
        self.assertEqual(data["suggested_polls_to_vote"], [])

    def test_recommend_post_liked_by_friend(self):
        self._create_db_friendship(self.user1, self.user3, status="accepted")
        # Ensure friendship is mutual for some recommendation logic
        self._create_db_friendship(self.user3, self.user1, status="accepted")


        post_by_user2 = self._create_db_post(
            user_id=self.user2_id, title="Post by User2", content="Content by User2"
        )
        self._create_db_like(user_id=self.user3_id, post_id=post_by_user2.id)

        response = self.client.get(f"/api/recommendations?user_id={self.user1_id}")
        self.assertEqual(response.status_code, 200)
        recommendations = json.loads(response.data)

        self.assertIn("suggested_posts", recommendations)
        self.assertIsInstance(recommendations["suggested_posts"], list)
        self.assertTrue(
            len(recommendations["suggested_posts"]) > 0,
            "Suggested posts list is empty, expected post liked by friend.",
        )

        found_post_in_recommendations = any(
            rec_post.get("id") == post_by_user2.id
            for rec_post in recommendations["suggested_posts"]
        )
        self.assertTrue(
            found_post_in_recommendations,
            f"Post ID {post_by_user2.id} liked by friend was not found.",
        )

    def test_recommend_post_commented_on_by_friend(self):
        self._create_db_friendship(self.user1, self.user3, status="accepted")
        self._create_db_friendship(self.user3, self.user1, status="accepted")


        post_by_user2 = self._create_db_post(
            user_id=self.user2_id,
            title="Post Commented On Test",
            content="Content for comment test",
        )
        self._create_db_comment(
            user_id=self.user3_id,
            post_id=post_by_user2.id,
            content="An insightful comment",
        )

        response = self.client.get(f"/api/recommendations?user_id={self.user1_id}")
        self.assertEqual(response.status_code, 200)
        recommendations = json.loads(response.data)

        self.assertIn("suggested_posts", recommendations)
        self.assertIsInstance(recommendations["suggested_posts"], list)
        self.assertTrue(
            len(recommendations["suggested_posts"]) > 0,
            "Suggested posts list is empty, expected post commented by friend.",
        )

        found_post_in_recommendations = any(
            rec_post.get("id") == post_by_user2.id
            for rec_post in recommendations["suggested_posts"]
        )
        self.assertTrue(
            found_post_in_recommendations,
            f"Post ID {post_by_user2.id} commented on by friend was not found.",
        )

    def test_recommend_group_joined_by_friend(self):
        self._create_db_friendship(self.user1, self.user2, status="accepted")
        self._create_db_friendship(self.user2, self.user1, status="accepted")

        group_by_user3 = self._create_db_group(
            creator_id=self.user3_id,
            name="Friend's Joined Group Test",
            description="A group for testing recommendations",
        )

        with self.app.app_context():
            user2_obj = db.session.get(User, self.user2_id) # Renamed from user2 to user2_obj
            group_obj = db.session.get(Group, group_by_user3.id) # Renamed from group_by_user3_merged to group_obj

            if user2_obj and group_obj: # Use renamed variables
                user2_obj.joined_groups.append(group_obj) # Use renamed variables
                db.session.add(user2_obj) # Use renamed variable
                db.session.commit()
            else:
                self.fail("Failed to fetch user2 or group_by_user3 for test setup")

        response = self.client.get(f"/api/recommendations?user_id={self.user1_id}")
        self.assertEqual(response.status_code, 200, "API call should be successful")
        recommendations = json.loads(response.data)

        self.assertIn(
            "suggested_groups",
            recommendations,
            "Response should contain suggested_groups",
        )
        suggested_groups = recommendations["suggested_groups"]
        self.assertIsInstance(
            suggested_groups, list, "suggested_groups should be a list"
        )
        self.assertTrue(
            len(suggested_groups) > 0, "Suggested groups list should not be empty."
        )

        found_group_in_recommendations = any(
            rec_group.get("id") == group_by_user3.id
            for rec_group in suggested_groups
        )
        self.assertTrue(
            found_group_in_recommendations,
            f"Group ID {group_by_user3.id} joined by friend was not found.",
        )

```
