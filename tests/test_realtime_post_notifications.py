import unittest
import json
from unittest.mock import patch, ANY
from datetime import datetime  # Removed timedelta

# from app import app, db, socketio # COMMENTED OUT
# from models import User, Post # COMMENTED OUT
from tests.test_base import AppTestCase


class TestRealtimePostNotifications(AppTestCase):

    @patch(
        "app.broadcast_new_post"
    )  # Patch the function where it's defined/imported, e.g., 'app.views.broadcast_new_post'
    def test_create_post_api_triggers_broadcast(self, mock_broadcast_new_post_func):
        """
        Tests that creating a new post via the API correctly calls the
        broadcast function.
        """
        # Get a valid JWT token for an authenticated user
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        post_payload = {
            "title": "Realtime Test Post API SSE",
            "content": "This API post should trigger a broadcast with a snippet for SSE.",
        }

        # Make the API call to create a new post
        response = self.client.post("/api/posts", headers=headers, json=post_payload)

        # Assert that the post was created successfully
        self.assertEqual(
            response.status_code,
            201,
            f"API post creation failed: {response.data.decode()}",
        )

        # Assert that our mocked broadcast function was called exactly once
        mock_broadcast_new_post_func.assert_called_once()

        # (Optional) You can also inspect the arguments it was called with
        # For example, let's assume it was called with the created post object or its data
        response_json = response.get_json()
        created_post_id = response_json["post"]["id"]

        # Get the first (and only) call's arguments
        call_args, call_kwargs = mock_broadcast_new_post_func.call_args

        # Assuming the first argument is the post data dict
        broadcasted_data = call_args[0]
        self.assertIsInstance(broadcasted_data, dict)
        self.assertEqual(broadcasted_data["id"], created_post_id)
        self.assertEqual(broadcasted_data["title"], post_payload["title"])
