import unittest
import json
from unittest.mock import patch, ANY
from datetime import datetime, timedelta, timezone

# from app import app, db, socketio # COMMENTED OUT or ensure app context is handled by AppTestCase
from models import User, Post, Group, Event, Poll, PollOption, Like, Comment, EventRSVP, PollVote # Ensure this line is active or add necessary imports
from tests.test_base import AppTestCase


class TestRecommendationAPI(AppTestCase):

    # _create_db_group, _create_db_event, _create_db_poll, _create_db_like,
    # _create_db_comment, _create_db_event_rsvp, _create_db_poll_vote
    # are now in AppTestCase (tests/test_base.py)

    def setUp(self):
        super().setUp()  # Call parent setUp to get base users (self.user1, self.user2, self.user3)
        # self.user1 is the target user for recommendations
        # self.user2 will create content
        # self.user3 is the "lonely" user

        # Create some content by user2 that user1 might be recommended
        # These helpers are now in AppTestCase
        self.post_by_user2 = self._create_db_post(
            user_id=self.user2_id, title="User2's Post"
        )
        self.group_by_user2 = self._create_db_group(
            creator_id=self.user2_id, name="User2's Group"
        )
        # Ensure _create_db_event in AppTestCase uses date_str and handles created_at
        self.event_by_user2 = self._create_db_event(
            user_id=self.user2_id,
            title="User2's Event",
            date_str=(datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d"),
        )
        self.poll_by_user2 = self._create_db_poll(
            user_id=self.user2_id, question="User2's Poll?"
        )

        # User1 joins a different group (not by user2) to test suggest_groups_to_join logic (won't recommend this one)
        # self.other_group_user1_member_of = self._create_db_group(creator_id=self.user3_id, name="Other Group")
        # self.other_group_user1_member_of.members.append(self.user1) # This assumes Group model has a 'members' relationship
        # db.session.commit()

    def test_get_recommendations_success(self):
        # with app.app_context(): # Handled by test client / AppTestCase
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
        # with app.app_context():
        response = self.client.get("/api/recommendations?user_id=99999")
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertIn("message", data)
        # The message might be "User 99999 not found" or "User not found"
        self.assertTrue("not found" in data["message"].lower())

    def test_get_recommendations_missing_user_id(self):
        # with app.app_context():
        response = self.client.get("/api/recommendations")
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("message", data)
        # Example: {'message': {'user_id': 'User ID is required and must be an integer.'}}
        # Exact message depends on reqparse error formatting
        self.assertIn("user_id", data["message"])
        self.assertTrue("required" in data["message"]["user_id"].lower())

    def test_get_recommendations_no_suggestions(self):
        # self.user3 is set up by AppTestCase.setUp -> _setup_base_users()
        # It has no specific content or interactions created in this class's setUp,
        # so it should get minimal to no recommendations.
        # with app.app_context():
        response = self.client.get(f"/api/recommendations?user_id={self.user3_id}")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertEqual(data["user_id"], self.user3_id)
        self.assertEqual(data["suggested_posts"], [])
        self.assertEqual(data["suggested_groups"], [])
        self.assertEqual(data["suggested_events"], [])
        # user3 might be recommended user1 and user2 if the suggestion logic is simple
        # For now, let's assert it's a list. More specific checks depend on recommendation logic.
        self.assertIsInstance(data["suggested_users_to_follow"], list)
        self.assertEqual(data["suggested_polls_to_vote"], [])

    def test_recommend_post_liked_by_friend(self):
        """Test recommending a post liked by a friend."""
        # 1. Access user1, user2, user3 (already available from AppTestCase.setUp)
        # user1_id, user2_id, user3_id are also available

        # 2. Create a friendship between self.user1 and self.user3
        # The _create_friendship helper in AppTestCase creates one side of the friendship.
        # For a mutual friendship, it might need to be called twice or the helper might handle it.
        # Assuming helper creates user_id -> friend_id link.
        self._create_friendship(self.user1_id, self.user3_id, status='accepted')
        self._create_friendship(self.user3_id, self.user1_id, status='accepted') # Ensure mutual friendship

        # 3. Create a post by self.user2
        post_by_user2 = self._create_db_post(user_id=self.user2_id, title="Post by User2", content="Content by User2")

        # 4. Create a like on this post by self.user3
        self._create_db_like(user_id=self.user3_id, post_id=post_by_user2.id)

        # 5. Make API call and assertions
        response = self.client.get(f"/api/recommendations?user_id={self.user1_id}")
        self.assertEqual(response.status_code, 200)

        recommendations = json.loads(response.data)

        self.assertIn("suggested_posts", recommendations)
        self.assertIsInstance(recommendations["suggested_posts"], list)

        # Ensure the list is not empty before trying to find the post
        self.assertTrue(len(recommendations["suggested_posts"]) > 0,
                        "Suggested posts list is empty, expected post liked by friend.")

        found_post_in_recommendations = False
        for recommended_post in recommendations["suggested_posts"]:
            if recommended_post.get("id") == post_by_user2.id:
                self.assertEqual(recommended_post.get("title"), post_by_user2.title)
                # Add other relevant assertions if needed, e.g., author
                # self.assertEqual(recommended_post.get("author_username"), self.user2.username)
                found_post_in_recommendations = True
                break

        self.assertTrue(found_post_in_recommendations,
                        f"Post ID {post_by_user2.id} (Title: '{post_by_user2.title}') liked by friend was not found in recommendations.")

    def test_recommend_post_commented_on_by_friend(self):
        '''Test recommending a post commented on by a friend.'''
        # 1. user1, user2, user3 are available from AppTestCase.setUp
        # user1_id, user2_id, user3_id are also available

        # 2. Create a friendship between self.user1 and self.user3
        self._create_friendship(self.user1_id, self.user3_id, status='accepted')
        self._create_friendship(self.user3_id, self.user1_id, status='accepted') # Ensure mutual friendship

        # 3. Create a post by self.user2
        post_by_user2 = self._create_db_post(user_id=self.user2_id, title="Post Commented On Test", content="Content for comment test")

        # 4. Create a comment on this post by self.user3
        self._create_db_comment(user_id=self.user3_id, post_id=post_by_user2.id, content="A insightful comment") # Changed 'text' to 'content'

        # 5. Make API call and assertions
        response = self.client.get(f"/api/recommendations?user_id={self.user1_id}")
        self.assertEqual(response.status_code, 200)

        recommendations = json.loads(response.data)

        self.assertIn("suggested_posts", recommendations)
        self.assertIsInstance(recommendations["suggested_posts"], list)

        self.assertTrue(len(recommendations["suggested_posts"]) > 0,
                        "Suggested posts list is empty, expected post commented on by friend.")

        found_post_in_recommendations = False
        for recommended_post in recommendations["suggested_posts"]:
            if recommended_post.get("id") == post_by_user2.id:
                self.assertEqual(recommended_post.get("title"), post_by_user2.title)
                # self.assertEqual(recommended_post.get("author_username"), self.user2.username) # user2 object not directly available here
                found_post_in_recommendations = True
                break

        self.assertTrue(found_post_in_recommendations,
                        f"Post ID {post_by_user2.id} (Title: '{post_by_user2.title}') commented on by friend was not found in recommendations.")

    # _get_jwt_token is in AppTestCase

    # Helpers for creating likes, comments, RSVPs, votes are in AppTestCase
    # _create_db_like, _create_db_comment, _create_db_event_rsvp, _create_db_poll_vote
    # are inherited from AppTestCase

    def test_recommend_group_joined_by_friend(self):
        # user1 (self.user1_id) is the target for recommendations
        # user2 (self.user2_id) is the friend
        # user3 (self.user3_id) can be the group creator

        # 1. Create friendship between user1 and user2
        # Assuming _create_friendship helper creates a mutual 'accepted' friendship or needs to be called twice.
        # Based on test_recommend_post_liked_by_friend, it seems it needs to be mutual for suggestions.
        self._create_friendship(self.user1_id, self.user2_id, status='accepted')
        self._create_friendship(self.user2_id, self.user1_id, status='accepted')

        # 2. Create a group by user3
        group_by_user3 = self._create_db_group(
            creator_id=self.user3_id,
            name="Friend's Joined Group Test",
            description="A group for testing recommendations"
        )

        # 3. user2 joins this group
        # Need to fetch user2 and group_by_user3 as ORM objects to append to relationship
        with self.app.app_context(): # Add app context here
            user2 = self.db.session.get(User, self.user2_id)
            # group_obj = self.db.session.get(Group, group_by_user3.id) # _create_db_group should return the object
            group_by_user3_merged = self.db.session.merge(group_by_user3) # Ensure group is in session

            if user2 and group_by_user3_merged:
                # Assuming User model has 'joined_groups' relationship (e.g., backref from Group.members)
                # or Group model has 'members' relationship.
                # Based on recommendations.py (suggest_groups_to_join):
                # `user_groups_ids = {group.id for group in current_user.joined_groups.all()}`
                # `friend.joined_groups.all()`
                # This implies User.joined_groups is the correct relationship.
                user2.joined_groups.append(group_by_user3_merged)
                self.db.session.add(user2) # Add user2 to session if relationship change doesn't auto-add
                self.db.session.commit()
            else:
                self.fail("Failed to fetch user2 or group_by_user3 for test setup")

        # 4. Call the recommendation API for user1
        response = self.client.get(f"/api/recommendations?user_id={self.user1_id}")

        # 5. Assert the expected outcome
        self.assertEqual(response.status_code, 200, "API call should be successful")

        recommendations = json.loads(response.data)
        self.assertIn("suggested_groups", recommendations, "Response should contain suggested_groups")

        suggested_groups = recommendations["suggested_groups"]
        self.assertIsInstance(suggested_groups, list, "suggested_groups should be a list")

        self.assertTrue(len(suggested_groups) > 0,
                        "Suggested groups list should not be empty.")

        found_group_in_recommendations = False
        for recommended_group in suggested_groups:
            self.assertIn("id", recommended_group)
            self.assertIn("name", recommended_group)
            if recommended_group["id"] == group_by_user3.id:
                self.assertEqual(recommended_group["name"], group_by_user3.name,
                                 "Recommended group name does not match.")
                # Optionally, assert other details like creator if available and relevant
                # self.assertIn("creator_username", recommended_group)
                found_group_in_recommendations = True
                break

        self.assertTrue(found_group_in_recommendations,
                        f"Group ID {group_by_user3.id} (Name: '{group_by_user3.name}') joined by friend was not found in recommendations.")
