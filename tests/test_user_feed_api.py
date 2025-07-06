import unittest
import json
from unittest.mock import patch, ANY
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

from social_app.models.db_models import User
from tests.test_base import AppTestCase
from flask import url_for


class TestUserFeedAPI(AppTestCase):

    def setUp(self):
        super().setUp()

    def test_get_feed_user_not_found(self):
        """Test Case 3: User Not Found."""
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        with self.app.app_context():
            response = self.client.get(url_for('userfeedresource', user_id=99999), headers=headers)
        self.assertEqual(response.status_code, 404)

    @patch("social_app.api.routes.get_personalized_feed_posts")
    def test_get_feed_empty_for_new_user_no_relevant_content(
        self, mock_get_feed_posts_func
    ):
        """Test Case 4: Empty Feed for New User (or user with no relevant activity/content)."""
        mock_get_feed_posts_func.return_value = []

        with self.app.app_context():
            target_user_instance = User.query.filter_by(username="testuser3").first()
            self.assertIsNotNone(target_user_instance)
            target_user_id_for_api = target_user_instance.id

        token = self._get_jwt_token(target_user_instance.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        with self.app.app_context():
            target_user_instance = User.query.filter_by(username="testuser3").first()
            self.assertIsNotNone(target_user_instance)
            target_user_id_for_api = target_user_instance.id

            response = self.client.get(
                url_for('userfeedresource', user_id=target_user_id_for_api), headers=headers
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data, {"feed_posts": []})
            mock_get_feed_posts_func.assert_called_once_with(target_user_id_for_api, limit=20)
