import unittest
import json
from unittest.mock import patch, ANY  # ANY kept for potential future use
from datetime import datetime, timedelta
from werkzeug.security import (
    generate_password_hash,
)  # For new user creation in one test

# from app import app, db, socketio # COMMENTED OUT
# from models import User, Post, Like, Friendship # COMMENTED OUT - Added Friendship
from tests.test_base import AppTestCase


class TestUserFeedAPI(AppTestCase):

    def setUp(self):
        super().setUp()
        # self.user1, self.user2, self.user3 are created by AppTestCase's _setup_base_users()
        # _create_db_like is in AppTestCase

    def test_get_feed_user_not_found(self):
        """Test Case 3: User Not Found."""
        response = self.client.get("/api/users/99999/feed")
        self.assertEqual(response.status_code, 404)

    @patch("app.api.get_personalized_feed_posts")
    def test_get_feed_empty_for_new_user_no_relevant_content(
        self, mock_get_feed_posts_func
    ):
        """Test Case 4: Empty Feed for New User (or user with no relevant activity/content)."""
        mock_get_feed_posts_func.return_value = []
        new_user_id = 999

        response = self.client.get(f"/api/users/{new_user_id}/feed")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {"feed_posts": []})
        mock_get_feed_posts_func.assert_called_once_with(new_user_id, limit=20)
