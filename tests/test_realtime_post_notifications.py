import unittest
import json
from unittest.mock import patch, ANY, MagicMock
from datetime import datetime

from social_app.services.notifications_service import broadcast_new_post
from tests.test_base import AppTestCase


class TestRealtimePostNotifications(AppTestCase):

    @patch("social_app.api.routes.broadcast_new_post")
    def test_create_post_api_triggers_broadcast(self, mock_broadcast_new_post_func):
        """
        Tests that creating a new post via the API correctly calls the
        broadcast function.
        """
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        post_payload = {
            "title": "Realtime Test Post API SSE",
            "content": "This API post should trigger a broadcast with a snippet for SSE.",
        }

        response = self.client.post("/api/posts", headers=headers, json=post_payload)

        self.assertEqual(response.status_code, 201)
        mock_broadcast_new_post_func.assert_called_once()
        response_json = response.get_json()
        created_post_id = response_json["post"]["id"]
        call_args, call_kwargs = mock_broadcast_new_post_func.call_args
        broadcasted_data = call_args[0]
        self.assertIsInstance(broadcasted_data, dict)
        self.assertEqual(broadcasted_data["id"], created_post_id)
        self.assertEqual(broadcasted_data["title"], post_payload["title"])

    @patch("social_app.services.notifications_service.new_post_sse_queues", new_callable=list)
    @patch("social_app.services.notifications_service.url_for")
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock()))
    def test_broadcast_new_post_with_url(
        self, mock_url_for_obj, mock_new_post_sse_queues_list_obj
    ):
        from social_app.services import notifications_service
        mock_logger = notifications_service.current_app.logger

        mock_queue = MagicMock()
        mock_new_post_sse_queues_list_obj.append(mock_queue)

        expected_url = "http://localhost/post/123"
        mock_url_for_obj.return_value = expected_url
        post_data = {"id": 123, "title": "Test Post with URL"}

        with self.app.app_context():
            broadcast_new_post(post_data)

        missing_id_warning_msg = "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."
        was_missing_id_warning_called = False
        for call_args in mock_logger.warning.call_args_list:
            if call_args[0][0] == missing_id_warning_msg:
                was_missing_id_warning_called = True
                break
        self.assertFalse(was_missing_id_warning_called)

        mock_logger.error.assert_not_called()
        mock_url_for_obj.assert_called_once_with(
            "core.view_post", post_id=123, _external=True
        )
        mock_queue.put.assert_called_once()

        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]

        self.assertEqual(broadcasted_data["id"], post_data["id"])
        self.assertEqual(broadcasted_data["title"], post_data["title"])
        self.assertIn("url", broadcasted_data)
        self.assertEqual(broadcasted_data["url"], expected_url)

    @patch("social_app.services.notifications_service.new_post_sse_queues", new_callable=list)
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock()))
    def test_broadcast_new_post_missing_id(
        self, mock_new_post_sse_queues_list_obj
    ):
        from social_app.services import notifications_service
        mock_logger = notifications_service.current_app.logger

        mock_queue = MagicMock()
        mock_new_post_sse_queues_list_obj.append(mock_queue)
        post_data = {"title": "Test Post Missing ID"}

        with self.app.app_context():
            broadcast_new_post(post_data)

        missing_id_warning_msg = "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."
        no_queues_warning_msg = "No SSE queues to send new post notifications to."
        called_warnings = [c[0][0] for c in mock_logger.warning.call_args_list]
        self.assertIn(missing_id_warning_msg, called_warnings)
        self.assertNotIn(no_queues_warning_msg, called_warnings)

        mock_queue.put.assert_called_once()
        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]
        self.assertEqual(broadcasted_data["title"], post_data["title"])
        self.assertNotIn("id", broadcasted_data)
        self.assertNotIn("url", broadcasted_data)

    @patch("social_app.services.notifications_service.new_post_sse_queues", new_callable=list)
    @patch("social_app.services.notifications_service.url_for")
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock()))
    def test_broadcast_new_post_url_for_exception(
        self, mock_url_for_obj, mock_new_post_sse_queues_list_obj
    ):
        from social_app.services import notifications_service
        mock_logger = notifications_service.current_app.logger

        mock_queue = MagicMock()
        mock_new_post_sse_queues_list_obj.append(mock_queue)
        mock_url_for_obj.side_effect = Exception("Test url_for error")
        post_data = {"id": 456, "title": "Test Post URL Exception"}

        with self.app.app_context():
            broadcast_new_post(post_data)

        mock_url_for_obj.assert_called_once_with("core.view_post", post_id=456, _external=True)
        mock_logger.error.assert_called_once()
        args, _ = mock_logger.error.call_args
        log_message = args[0]
        self.assertTrue(log_message.startswith(f"Error generating URL for post ID {post_data['id']}"))
        self.assertIn("Sending notification without URL.", log_message)
        mock_queue.put.assert_called_once()
        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]
        self.assertEqual(broadcasted_data["id"], post_data["id"])
        self.assertEqual(broadcasted_data["title"], post_data["title"])
        self.assertNotIn("url", broadcasted_data)

    @patch("social_app.services.notifications_service.url_for")
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock()))
    def test_broadcast_new_post_with_no_queues(self, mock_url_for_obj):
        from social_app.services import notifications_service
        mock_logger = notifications_service.current_app.logger
        original_queues = list(notifications_service.new_post_sse_queues)
        notifications_service.new_post_sse_queues.clear()

        try:
            self.assertEqual(len(notifications_service.new_post_sse_queues), 0)
            with self.app.app_context():
                broadcast_new_post({"title": "Test No Queues"})

            expected_warning_id_missing = "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."
            expected_warning_no_queues = "No SSE queues in new_post_sse_queues to send new post notifications to."
            called_warnings = [c[0][0] for c in mock_logger.warning.call_args_list]
            self.assertIn(expected_warning_id_missing, called_warnings)
            self.assertIn(expected_warning_no_queues, called_warnings)
            self.assertEqual(len(called_warnings), 2)
            mock_url_for_obj.assert_not_called()
        finally:
            notifications_service.new_post_sse_queues.clear()
            notifications_service.new_post_sse_queues.extend(original_queues)

    @patch("social_app.services.notifications_service.new_post_sse_queues", new_callable=list)
    @patch("social_app.services.notifications_service.url_for")
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock()))
    def test_broadcast_new_post_empty_data_no_queues(
        self, mock_url_for_obj, mock_new_post_sse_queues_list_obj
    ):
        from social_app.services import notifications_service
        mock_logger = notifications_service.current_app.logger
        """
        Tests broadcast_new_post with empty data and no SSE queues.
        Checks for appropriate logging and no flask.url_for call.
        """
        self.assertEqual(len(mock_new_post_sse_queues_list_obj), 0)
        with self.app.app_context():
            broadcast_new_post({})
        mock_url_for_obj.assert_not_called()
        expected_warning_id_missing = "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."
        expected_warning_no_queues = "No SSE queues in new_post_sse_queues to send new post notifications to."
        called_warnings = [c[0][0] for c in mock_logger.warning.call_args_list]
        self.assertIn(expected_warning_id_missing, called_warnings)
        self.assertIn(expected_warning_no_queues, called_warnings)

    @patch("social_app.services.notifications_service.new_post_sse_queues", new_callable=list)
    @patch("social_app.services.notifications_service.url_for")
    @patch("social_app.services.notifications_service.current_app", MagicMock(logger=MagicMock()))
    def test_broadcast_new_post_empty_data_with_queue(
        self, mock_url_for_obj, mock_new_post_sse_queues_list_obj
    ):
        from social_app.services import notifications_service
        mock_logger = notifications_service.current_app.logger
        """
        Tests broadcast_new_post with empty data but with an SSE queue.
        Checks for appropriate logging, no flask.url_for call, and queue interaction.
        """
        mock_queue = MagicMock()
        mock_new_post_sse_queues_list_obj.append(mock_queue)
        with self.app.app_context():
            broadcast_new_post({})
        mock_url_for_obj.assert_not_called()
        expected_warning_id_missing = "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."
        warning_no_queues = "No SSE queues to send new post notifications to."
        called_warnings = [c[0][0] for c in mock_logger.warning.call_args_list]
        self.assertIn(expected_warning_id_missing, called_warnings)
        self.assertNotIn(warning_no_queues, called_warnings)
        mock_queue.put.assert_called_once()
        args, _ = mock_queue.put.call_args
        broadcasted_data = args[0]
        self.assertEqual(broadcasted_data, {})
        self.assertNotIn("id", broadcasted_data)
        self.assertNotIn("url", broadcasted_data)
