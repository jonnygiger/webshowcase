import unittest
import json
from unittest.mock import (
    patch,
    ANY,
)  # ANY is kept as tests are commented out but might use it
from datetime import datetime, timedelta

# from app import app, db, socketio # COMMENTED OUT
# from models import User, Post, Event # COMMENTED OUT
# from recommendations import get_on_this_day_posts_and_events # Potentially used by API
from tests.test_base import AppTestCase

# from flask import url_for # Conditional import is good practice


class TestOnThisDayPage(AppTestCase):

    def setUp(self):
        super().setUp()
        self.test_user = self.user1
        self.fixed_today = datetime(2023, 10, 26, 12, 0, 0)

        self.post_target_correct = self._create_db_post(
            user_id=self.test_user.id,
            title="Correct Web Post",
            content="Web content from Oct 26, 2022",
            timestamp=datetime(2022, 10, 26, 10, 0, 0),
        )
        self.event_target_correct = self._create_db_event(
            user_id=self.test_user.id,
            title="Correct Web Event",
            date_str="2022-10-26",
            description="Web event on Oct 26, 2022",
        )
        self.post_current_year_web = self._create_db_post(
            user_id=self.test_user.id,
            title="Current Year Web Post",
            timestamp=datetime(2023, 10, 26, 11, 0, 0),
        )
        self.event_different_day_web = self._create_db_event(
            user_id=self.test_user.id,
            title="Different Day Web Event",
            date_str="2022-10-27",
        )
        # Commits are handled by AppTestCase helpers

    def test_on_this_day_page_unauthorized(self):
        response = self.client.get("/onthisday", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))

    @patch("app.datetime")
    @patch("recommendations.datetime")
    def test_on_this_day_page_no_content(self, mock_reco_datetime, mock_app_datetime):
        no_content_date = datetime(2023, 1, 1, 12, 0, 0)
        mock_app_datetime.utcnow.return_value = no_content_date
        mock_reco_datetime.utcnow.return_value = no_content_date
        mock_reco_datetime.strptime = datetime.strptime

        self.login(self.test_user.username, "password")
        response = self.client.get("/onthisday")
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        self.assertIn("No posts from this day in previous years.", response_data)
        self.assertIn("No events from this day in previous years.", response_data)
        self.assertIn(
            "Nothing to show for 'On This Day' from previous years.", response_data
        )
        self.logout()

    @patch("app.datetime")
    @patch("recommendations.datetime")
    def test_on_this_day_page_with_content_and_filtering(
        self, mock_reco_datetime, mock_app_datetime
    ):
        from flask import url_for

        mock_app_datetime.utcnow.return_value = self.fixed_today
        mock_reco_datetime.utcnow.return_value = self.fixed_today
        mock_reco_datetime.strptime = datetime.strptime

        self.login(self.test_user.username, "password")
        response = self.client.get("/onthisday")
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        self.assertIn(self.post_target_correct.title, response_data)
        self.assertIn(self.event_target_correct.title, response_data)
        self.assertRegex(
            response_data, f'href="[^"]*/blog/post/{self.post_target_correct.id}[^"]*"'
        )
        self.assertRegex(
            response_data, f'href="[^"]*/event/{self.event_target_correct.id}[^"]*"'
        )

        self.assertNotIn(self.post_current_year_web.title, response_data)
        self.assertNotIn(self.event_different_day_web.title, response_data)
        self.logout()


class TestOnThisDayAPI(AppTestCase):

    def setUp(self):
        super().setUp()
        self.test_user = self.user1
        self.fixed_today = datetime(2023, 10, 26, 12, 0, 0)

        self.post_target_correct = self._create_db_post(
            user_id=self.test_user.id,
            title="Correct Post",
            content="Content from Oct 26, 2022",
            timestamp=datetime(2022, 10, 26, 10, 0, 0),
        )
        self.post_current_year = self._create_db_post(
            user_id=self.test_user.id,
            title="Current Year Post",
            content="Content from Oct 26, 2023",
            timestamp=datetime(2023, 10, 26, 11, 0, 0),
        )
        self.post_different_day = self._create_db_post(
            user_id=self.test_user.id,
            title="Different Day Post",
            content="Content from Oct 27, 2022",
            timestamp=datetime(2022, 10, 27, 12, 0, 0),
        )
        self.post_different_month = self._create_db_post(
            user_id=self.test_user.id,
            title="Different Month Post",
            content="Content from Nov 26, 2022",
            timestamp=datetime(2022, 11, 26, 12, 0, 0),
        )
        self.post_by_other_user_correct_date = self._create_db_post(
            user_id=self.user2_id,
            title="Other User Correct Date Post",
            content="Content from Oct 26, 2022 by other user",
            timestamp=datetime(2022, 10, 26, 10, 0, 0),
        )
        self.event_target_correct = self._create_db_event(
            user_id=self.test_user.id,
            title="Correct Event",
            date_str="2022-10-26",
            description="Event on Oct 26, 2022",
        )
        self.event_current_year = self._create_db_event(
            user_id=self.test_user.id,
            title="Current Year Event",
            date_str="2023-10-26",
            description="Event on Oct 26, 2023",
        )
        self.event_different_day = self._create_db_event(
            user_id=self.test_user.id,
            title="Different Day Event",
            date_str="2022-10-27",
            description="Event on Oct 27, 2022",
        )
        self.event_different_month = self._create_db_event(
            user_id=self.test_user.id,
            title="Different Month Event",
            date_str="2022-11-26",
            description="Event on Nov 26, 2022",
        )
        self.event_by_other_user_correct_date = self._create_db_event(
            user_id=self.user2_id,
            title="Other User Correct Date Event",
            date_str="2022-10-26",
            description="Event on Oct 26, 2022 by other user",
        )
        self.event_invalid_date_format = self._create_db_event(
            user_id=self.test_user.id,
            title="Invalid Date Format Event",
            date_str="2022/10/26",
        )
        # Commits are handled by AppTestCase helpers

    @patch("recommendations.datetime")
    @patch("api.datetime")
    def test_on_this_day_with_content_and_filtering(
        self, mock_api_datetime, mock_reco_datetime
    ):
        mock_reco_datetime.utcnow.return_value = self.fixed_today
        mock_reco_datetime.strptime = datetime.strptime
        mock_api_datetime.utcnow.return_value = self.fixed_today

        token = self._get_jwt_token(self.test_user.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.get("/api/onthisday", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertIn("on_this_day_posts", data)
        self.assertIn("on_this_day_events", data)

        self.assertEqual(len(data["on_this_day_posts"]), 1)
        self.assertEqual(
            data["on_this_day_posts"][0]["id"], self.post_target_correct.id
        )
        self.assertEqual(
            data["on_this_day_posts"][0]["title"], self.post_target_correct.title
        )

        self.assertEqual(len(data["on_this_day_events"]), 1)
        self.assertEqual(
            data["on_this_day_events"][0]["id"], self.event_target_correct.id
        )
        self.assertEqual(
            data["on_this_day_events"][0]["title"], self.event_target_correct.title
        )

        post_ids_in_response = {p["id"] for p in data["on_this_day_posts"]}
        self.assertNotIn(self.post_current_year.id, post_ids_in_response)
        self.assertNotIn(self.post_different_day.id, post_ids_in_response)
        # ... (other assertions for filtering)

        event_ids_in_response = {e["id"] for e in data["on_this_day_events"]}
        self.assertNotIn(self.event_current_year.id, event_ids_in_response)
        # ... (other assertions for filtering)

    @patch("recommendations.datetime")
    @patch("api.datetime")
    def test_on_this_day_no_content_api(self, mock_api_datetime, mock_reco_datetime):
        no_content_date = datetime(2023, 1, 1, 12, 0, 0)
        mock_reco_datetime.utcnow.return_value = no_content_date
        mock_reco_datetime.strptime = datetime.strptime
        mock_api_datetime.utcnow.return_value = no_content_date

        token = self._get_jwt_token(self.test_user.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.get("/api/onthisday", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertEqual(len(data["on_this_day_posts"]), 0)
        self.assertEqual(len(data["on_this_day_events"]), 0)

    def test_on_this_day_unauthenticated(self):
        response = self.client.get("/api/onthisday")
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data["msg"], "Missing Authorization Header")
