import unittest
import json
from unittest.mock import patch, ANY  # ANY kept for potential future use
from datetime import datetime, timedelta
from werkzeug.security import (
    generate_password_hash,
)  # For new user creation in one test

# from app import app, db, socketio # COMMENTED OUT
from models import User  # Added User import

# from models import Post, Like, Friendship # COMMENTED OUT - Added Friendship
from tests.test_base import AppTestCase


class TestUserFeedAPI(AppTestCase):

    def setUp(self):
        super().setUp()
        # self.user1, self.user2, self.user3 are created by AppTestCase's _setup_base_users()
        # _create_db_like is in AppTestCase

    def test_get_feed_user_not_found(self):
        """Test Case 3: User Not Found."""
        # Obtain a token for an existing user to authenticate the request
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.get("/api/users/99999/feed", headers=headers)
        self.assertEqual(
            response.status_code, 404
        )  # Now it should hit the user not found logic

    @patch(
        "api.get_personalized_feed_posts"
    )  # Reverted patch target to where it's looked up
    def test_get_feed_empty_for_new_user_no_relevant_content(
        self, mock_get_feed_posts_func
    ):
        """Test Case 4: Empty Feed for New User (or user with no relevant activity/content)."""
        mock_get_feed_posts_func.return_value = []

        # To properly test the mocked function, we need to ensure the resource's user check passes.
        # Let's use self.user3 for this, who typically has less activity.
        with self.app.app_context():
            target_user_instance = User.query.filter_by(username="testuser3").first()
            self.assertIsNotNone(
                target_user_instance,
                "User 'testuser3' must exist in the database for this test.",
            )
            target_user_id_for_api = target_user_instance.id

        # Use the target user's token for authentication to ensure authorization passes
        token = self._get_jwt_token(
            target_user_instance.username, "password"
        )  # MODIFIED
        headers = {"Authorization": f"Bearer {token}"}

        # The following comments about new_user_id = 999 are now less relevant
        # as we are using an existing user.
        # new_user_id = 999 # This user ID doesn't exist, UserFeedResource will return 404
        # The mock should ideally not be hit if user is not found.
        # Let's test with an existing user ID that has no feed.
        # For this specific test, we are mocking the function that generates feed items,
        # so the user_id passed to it is what matters for the mock.
        # However, the resource itself will first check if user `new_user_id` exists.

        # To properly test the mocked function, we need to ensure the resource's user check passes.
        # Let's use self.user3 for this, who typically has less activity.
        # Or, we can create a truly new user for this test.
        # For now, let's assume new_user_id = 999 is meant to test the "user not found" path
        # of the UserFeedResource if the mock wasn't there.
        # With the mock, it will bypass the actual content generation IF the user 999 was found.
        # The UserFeedResource.get first does: target_user = User.query.get(user_id)
        # If user 999 is not found, it returns 404, and mock_get_feed_posts_func is not called.

        # Let's adjust the test to use an existing user (e.g., self.user3)
        # for whom the mocked function will return an empty list.

        # Ensure user3 is queryable from the DB perspective of this test method context
        with self.app.app_context():
            target_user_instance = User.query.filter_by(username="testuser3").first()
            self.assertIsNotNone(
                target_user_instance,
                "User 'testuser3' must exist in the database for this test.",
            )
            target_user_id_for_api = target_user_instance.id

        response = self.client.get(
            f"/api/users/{target_user_id_for_api}/feed", headers=headers
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {"feed_posts": []})
        mock_get_feed_posts_func.assert_called_once_with(
            target_user_id_for_api, limit=20
        )  # Original assertion
