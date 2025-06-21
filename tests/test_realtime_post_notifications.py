import unittest
import json
from unittest.mock import patch, ANY, MagicMock
from datetime import datetime  # Removed timedelta

# from app import app, db, socketio # COMMENTED OUT
# from models import User, Post # COMMENTED OUT
from app import broadcast_new_post, app as main_app_module
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

    @patch('app.new_post_sse_queues', new_callable=list) # Patch the list directly
    @patch('flask.url_for') # Mock flask.url_for used by broadcast_new_post
    def test_broadcast_new_post_with_url(self, mock_url_for, mock_new_post_sse_queues_list):
        # Setup: Add a mock queue to our patched list
        mock_queue = MagicMock()
        mock_new_post_sse_queues_list.append(mock_queue)

        # Define the expected URL that flask.url_for should return
        expected_url = "http://localhost/post/123"
        mock_url_for.return_value = expected_url

        post_data = {'id': 123, 'title': 'Test Post with URL'}

        # Call the function under test
        # broadcast_new_post is imported from app
        broadcast_new_post(post_data)

        # Assertions
        # 1. Check if flask.url_for was called correctly
        mock_url_for.assert_called_once_with('view_post', post_id=123, _external=True)

        # 2. Check if the mock queue's put method was called
        mock_queue.put.assert_called_once()

        # 3. Check the content of the data passed to queue.put()
        # Get the actual data passed to put
        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]

        self.assertEqual(broadcasted_data['id'], post_data['id'])
        self.assertEqual(broadcasted_data['title'], post_data['title'])
        self.assertIn('url', broadcasted_data)
        self.assertEqual(broadcasted_data['url'], expected_url)

    @patch('app.new_post_sse_queues', new_callable=list) # Patch the list
    @patch('app.app.logger') # Mock app.logger
    def test_broadcast_new_post_missing_id(self, mock_logger, mock_new_post_sse_queues_list):
        # Setup: Add a mock queue to our patched list
        mock_queue = MagicMock()
        mock_new_post_sse_queues_list.append(mock_queue)

        post_data = {'title': 'Test Post Missing ID'}

        # Call the function under test
        broadcast_new_post(post_data) # broadcast_new_post is imported from app

        # Assertions
        # 1. Check if app.logger.warning was called with the specific message
        # The message in app.py is: "Post data missing 'id' field, cannot generate URL for SSE notification. Sending notification without URL."
        mock_logger.warning.assert_called_once_with(
            "Post data missing 'id' field, cannot generate URL for SSE notification. Sending notification without URL."
        )

        # 2. Check if the mock queue's put method was called
        mock_queue.put.assert_called_once()

        # 3. Check the content of the data passed to queue.put()
        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]

        self.assertEqual(broadcasted_data['title'], post_data['title'])
        self.assertNotIn('id', broadcasted_data) # id was not in original, should not be added
        self.assertNotIn('url', broadcasted_data) # url should not be present

    @patch('app.new_post_sse_queues', new_callable=list) # Patch the list
    @patch('app.app.logger') # Mock app.logger
    @patch('flask.url_for') # Mock flask.url_for
    def test_broadcast_new_post_url_for_exception(self, mock_url_for, mock_logger, mock_new_post_sse_queues_list):
        # Setup: Add a mock queue to our patched list
        mock_queue = MagicMock()
        mock_new_post_sse_queues_list.append(mock_queue)

        # Configure flask.url_for mock to raise an exception
        mock_url_for.side_effect = Exception("Test url_for error")

        post_data = {'id': 456, 'title': 'Test Post URL Exception'}

        # Call the function under test
        broadcast_new_post(post_data) # broadcast_new_post is imported from app

        # Assertions
        # 1. Check if flask.url_for was called
        mock_url_for.assert_called_once_with('view_post', post_id=456, _external=True)

        # 2. Check if app.logger.error was called with the specific message
        # The message in app.py is: f"Error generating URL for post ID {post_data_with_url.get('id')}: {e}. Sending notification without URL."
        # We need to use ANY for the exception part of the message, or match the start of the message.
        mock_logger.error.assert_called_once()
        args, _ = mock_logger.error.call_args
        log_message = args[0]
        self.assertTrue(log_message.startswith(f"Error generating URL for post ID {post_data['id']}"))
        self.assertIn("Sending notification without URL.", log_message)


        # 3. Check if the mock queue's put method was called
        mock_queue.put.assert_called_once()

        # 4. Check the content of the data passed to queue.put()
        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]

        self.assertEqual(broadcasted_data['id'], post_data['id'])
        self.assertEqual(broadcasted_data['title'], post_data['title'])
        self.assertNotIn('url', broadcasted_data) # url should not be present due to exception
