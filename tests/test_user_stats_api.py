import unittest
import json
from unittest.mock import patch, ANY
from datetime import datetime, timedelta
from flask import url_for

from tests.test_base import AppTestCase


class TestUserStatsAPI(AppTestCase):

    def setUp(self):
        super().setUp()
        pass

    def test_user_stats_api(self):
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        headers_user1 = {"Authorization": f"Bearer {token_user1}"}

        with self.app.app_context():
            response = self.client.get(
                url_for("userstatsresource", user_id=self.user1_id),
                headers=headers_user1,
            )
        self.assertEqual(response.status_code, 200)
        stats_data = json.loads(response.data)

        self.assertIn("posts_count", stats_data)
        self.assertIn("comments_count", stats_data)
        self.assertIn("likes_received_count", stats_data)
        self.assertIn("friends_count", stats_data)
        self.assertIn("join_date", stats_data)

        with self.app.app_context():
            response_no_token = self.client.get(
                url_for("userstatsresource", user_id=self.user1_id)
            )
        self.assertEqual(response_no_token.status_code, 401)
        data_no_token = json.loads(response_no_token.data)
        self.assertEqual(data_no_token.get("msg"), "Missing Authorization Header")

        token_user2 = self._get_jwt_token(self.user2.username, "password")
        headers_user2 = {"Authorization": f"Bearer {token_user2}"}
        with self.app.app_context():
            response_forbidden = self.client.get(
                url_for("userstatsresource", user_id=self.user1_id),
                headers=headers_user2,
            )
        self.assertEqual(response_forbidden.status_code, 403)
        data_forbidden = json.loads(response_forbidden.data)
        self.assertEqual(
            data_forbidden.get("message"), "You are not authorized to view these stats."
        )
