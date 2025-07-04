import unittest
import json
from unittest.mock import patch, ANY, MagicMock
from datetime import datetime  # Removed timedelta

# Updated commented-out imports for future reference:
# from social_app import create_app, db, socketio
# from social_app.models.db_models import User, Post
# Updated import for broadcast_new_post and app context usage
from social_app.services.notifications_service import broadcast_new_post
# main_app_module for app_context will be self.app from AppTestCase
from tests.test_base import AppTestCase

class TestRealtimePostNotifications(AppTestCase):

    @patch("social_app.api.routes.broadcast_new_post")  # Corrected: Patch where it's imported and used
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

    @patch("notifications.new_post_sse_queues", new_callable=list)
    @patch("notifications.url_for")
    @patch("notifications.current_app", MagicMock(logger=MagicMock()))
    # Test method signature expects args for url_for and new_post_sse_queues only
    def test_broadcast_new_post_with_url(
        self, mock_url_for_obj, mock_new_post_sse_queues_list_obj
    ):  # MODIFIED SIGNATURE
        # Access the logger from the pre-configured mock current_app
        # Need to import notifications_service to access its current_app mock
        from social_app.services import notifications_service

        mock_logger = notifications_service.current_app.logger # Use the mocked current_app

        # Setup: Add a mock queue to our patched list
        mock_queue = MagicMock()
        mock_new_post_sse_queues_list_obj.append(mock_queue)

        # Define the expected URL that flask.url_for should return
        expected_url = "http://localhost/post/123"
        mock_url_for_obj.return_value = expected_url

        post_data = {"id": 123, "title": "Test Post with URL"}

        # Call the function under test
        with self.app.app_context(): # Use self.app from AppTestCase
            broadcast_new_post(post_data)

        # Assertions
        missing_id_warning_msg = "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."
        was_missing_id_warning_called = False
        for call_args in mock_logger.warning.call_args_list:
            if call_args[0][0] == missing_id_warning_msg:
                was_missing_id_warning_called = True
                break
        self.assertFalse(
            was_missing_id_warning_called,
            f"'{missing_id_warning_msg}' was unexpectedly logged.",
        )

        mock_logger.error.assert_not_called()
        mock_url_for_obj.assert_called_once_with(
            "view_post", post_id=123, _external=True
        )
        mock_queue.put.assert_called_once()

        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]

        self.assertEqual(broadcasted_data["id"], post_data["id"])
        self.assertEqual(broadcasted_data["title"], post_data["title"])
        self.assertIn("url", broadcasted_data)
        self.assertEqual(broadcasted_data["url"], expected_url)

    @patch("social_app.services.notifications_service.new_post_sse_queues", new_callable=list) # Corrected
    # Note: No @patch for url_for here, as it should not be called if 'id' is missing
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock())) # Corrected
    def test_broadcast_new_post_missing_id(
        self, mock_new_post_sse_queues_list_obj
    ):
        from social_app.services import notifications_service # Corrected import

        mock_logger = notifications_service.current_app.logger # Use the mocked current_app

        # Setup: Add a mock queue to our patched list
        mock_queue = MagicMock()
        mock_new_post_sse_queues_list_obj.append(mock_queue)

        post_data = {"title": "Test Post Missing ID"}

        # Call the function under test
        with self.app.app_context(): # Use self.app from AppTestCase
            broadcast_new_post(post_data)

        # Assertions
        # 1. Check if app.logger.warning was called with the specific message
        # The message in app.py is: "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL." # MODIFIED
        # This also implies flask.url_for should not have been called.
        mock_logger.warning.assert_any_call(  # Use assert_any_call if other warnings might occur due to no queues.
            "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."  # MODIFIED
        )
        # Additionally, ensure the "no queues" warning is also there, as new_post_sse_queues is not empty here.
        # Actually, for this test, new_post_sse_queues has one mock queue.
        # So, only the "missing id" warning should be there.

        # Let's be more specific: check that ONLY the 'missing id' warning is called.
        # And that 'no sse queues' is NOT called.

        # Check for the specific "missing id" warning.
        missing_id_warning_msg = "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."  # MODIFIED
        no_queues_warning_msg = "No SSE queues to send new post notifications to."

        called_warnings = [c[0][0] for c in mock_logger.warning.call_args_list]
        self.assertIn(missing_id_warning_msg, called_warnings)
        self.assertNotIn(no_queues_warning_msg, called_warnings)

        # 2. Check if the mock queue's put method was called
        mock_queue.put.assert_called_once()

        # 3. Check the content of the data passed to queue.put()
        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]

        self.assertEqual(broadcasted_data["title"], post_data["title"])
        self.assertNotIn(
            "id", broadcasted_data
        )  # id was not in original, should not be added
        self.assertNotIn("url", broadcasted_data)  # url should not be present

    @patch("social_app.services.notifications_service.new_post_sse_queues", new_callable=list) # Corrected
    @patch("social_app.services.notifications_service.url_for") # Corrected
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock())) # Corrected
    def test_broadcast_new_post_url_for_exception(
        self, mock_url_for_obj, mock_new_post_sse_queues_list_obj
    ):
        from social_app.services import notifications_service # Corrected import

        mock_logger = notifications_service.current_app.logger # Use the mocked current_app

        # Setup: Add a mock queue to our patched list
        mock_queue = MagicMock()
        mock_new_post_sse_queues_list_obj.append(mock_queue)

        # Configure flask.url_for mock to raise an exception
        mock_url_for_obj.side_effect = Exception("Test url_for error")

        post_data = {"id": 456, "title": "Test Post URL Exception"}

        # Call the function under test
        with self.app.app_context(): # Use self.app from AppTestCase
            broadcast_new_post(post_data)

        # Assertions
        mock_url_for_obj.assert_called_once_with(
            "core.view_post", post_id=456, _external=True # Corrected route name
        )

        mock_logger.error.assert_called_once()
        args, _ = mock_logger.error.call_args
        log_message = args[0]
        self.assertTrue(
            log_message.startswith(
                f"Error generating URL for post ID {post_data['id']}"
            )
        )
        self.assertIn("Sending notification without URL.", log_message)

        mock_queue.put.assert_called_once()

        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]

        self.assertEqual(broadcasted_data["id"], post_data["id"])
        self.assertEqual(broadcasted_data["title"], post_data["title"])
        self.assertNotIn("url", broadcasted_data)

    @patch("social_app.services.notifications_service.url_for") # Corrected
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock())) # Corrected
    def test_broadcast_new_post_with_no_queues(
        self, mock_url_for_obj # Patched object is passed
    ):
        from social_app.services import notifications_service # Corrected import

        mock_logger = notifications_service.current_app.logger # Use the mocked current_app

        original_queues = list(
            notifications_service.new_post_sse_queues # Use imported module
        )
        notifications_service.new_post_sse_queues.clear() # Use imported module

        try:
            # Confirm the list is empty before the call
            self.assertEqual(len(notifications_service.new_post_sse_queues), 0) # Use imported module

            with self.app.app_context(): # Use self.app from AppTestCase
                broadcast_new_post({"title": "Test No Queues"})  # 'id' is missing

            # Check for both warnings
            expected_warning_id_missing = "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."
            expected_warning_no_queues = "No SSE queues in new_post_sse_queues to send new post notifications to."

            called_warnings = [c[0][0] for c in mock_logger.warning.call_args_list]
            self.assertIn(expected_warning_id_missing, called_warnings)
            self.assertIn(expected_warning_no_queues, called_warnings)
            self.assertEqual(
                len(called_warnings), 2
            )  # Ensure exactly these two warnings

            mock_url_for_obj.assert_not_called()
        finally:
            # Restore original list
            notifications_service.new_post_sse_queues.clear() # Use imported module
            notifications_service.new_post_sse_queues.extend(original_queues) # Use imported module

    @patch("social_app.services.notifications_service.new_post_sse_queues", new_callable=list) # Corrected
    @patch("social_app.services.notifications_service.url_for") # Corrected
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock())) # Corrected
    def test_broadcast_new_post_empty_data_no_queues(
        self, mock_url_for_obj, mock_new_post_sse_queues_list_obj
    ):
        from social_app.services import notifications_service # Corrected import

        mock_logger = notifications_service.current_app.logger # Use the mocked current_app
        """
        Tests broadcast_new_post with empty data and no SSE queues.
        Checks for appropriate logging and no flask.url_for call.
        """
        # Ensure new_post_sse_queues is empty (handled by new_callable=list)
        self.assertEqual(len(mock_new_post_sse_queues_list_obj), 0)

        with self.app.app_context(): # Use self.app from AppTestCase
            broadcast_new_post({})

        # Assert that flask.url_for was not called
        mock_url_for_obj.assert_not_called()

        # Assert logger warnings
        expected_warning_id_missing = "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."
        expected_warning_no_queues = "No SSE queues in new_post_sse_queues to send new post notifications to."

        # Check all calls to warning
        called_warnings = [c[0][0] for c in mock_logger.warning.call_args_list]
        self.assertIn(expected_warning_id_missing, called_warnings)
        self.assertIn(expected_warning_no_queues, called_warnings)

    @patch("social_app.services.notifications_service.new_post_sse_queues", new_callable=list) # Corrected
    @patch("social_app.services.notifications_service.url_for") # Corrected
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock())) # Corrected
    def test_broadcast_new_post_empty_data_with_queue(
        self, mock_url_for_obj, mock_new_post_sse_queues_list_obj
    ):
        from social_app.services import notifications_service # Corrected import

        mock_logger = notifications_service.current_app.logger # Use the mocked current_app
        """
        Tests broadcast_new_post with empty data but with an SSE queue.
        Checks for appropriate logging, no flask.url_for call, and queue interaction.
        """
        # Add a mock queue
        mock_queue = MagicMock()
        mock_new_post_sse_queues_list_obj.append(mock_queue)

        with self.app.app_context(): # Use self.app from AppTestCase
            broadcast_new_post({})

        # Assert that flask.url_for was not called
        mock_url_for_obj.assert_not_called()

        # Assert logger warnings
        expected_warning_id_missing = "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."
        warning_no_queues = "No SSE queues to send new post notifications to."

        called_warnings = [c[0][0] for c in mock_logger.warning.call_args_list]
        self.assertIn(expected_warning_id_missing, called_warnings)
        self.assertNotIn(warning_no_queues, called_warnings)

        # Assert queue interaction
        mock_queue.put.assert_called_once()

        # Assert the data put to the queue
        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]
        self.assertEqual(broadcasted_data, {})
        self.assertNotIn("id", broadcasted_data)
        self.assertNotIn("url", broadcasted_data)
