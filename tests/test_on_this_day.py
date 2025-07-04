import unittest
import json
from unittest.mock import (
    patch,
    ANY,
)  # ANY is kept as tests are commented out but might use it
from datetime import datetime, timedelta, timezone

# Updated commented-out imports for future reference:
# from social_app import create_app, db, socketio
# from social_app.models.db_models import User, Post, Event
# from social_app.services.recommendations_service import get_on_this_day_content
from tests.test_base import AppTestCase
from social_app.models.db_models import User  # Updated model import path
from werkzeug.security import generate_password_hash  # Needed for hashing password
from flask import url_for # Ensure url_for is imported


class TestOnThisDayPage(AppTestCase):

    def setUp(self):
        super().setUp()
        self.test_user = self.user1
        self.fixed_today = datetime(2023, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

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
        response = self.client.get(url_for('core.on_this_day_page'), follow_redirects=False) # Use url_for
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith(url_for('core.login'))) # Use url_for

    @patch("social_app.core.views.datetime") # Patching datetime where view might use it
    @patch("social_app.services.recommendations_service.datetime") # Patching datetime where service might use it
    def test_on_this_day_page_no_content(self, mock_reco_datetime, mock_views_datetime):
        no_content_date = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_views_datetime.now.return_value = no_content_date
        mock_reco_datetime.now.return_value = no_content_date
        mock_reco_datetime.strptime = datetime.strptime # Ensure strptime is not mocked away if service uses it

        self.login(self.test_user.username, "password")
        response = self.client.get(url_for('core.on_this_day_page')) # Use url_for
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        # Assert that the specific messages for no posts/events are shown
        self.assertIn("No posts from this day in previous years.", response_data)
        self.assertIn("No events from this day in previous years.", response_data)
        # Assert that the general "Nothing to show..." message is NOT present
        self.assertNotIn(
            "Nothing to show for 'On This Day' from previous years.", response_data
        )
        self.logout()

    @patch("social_app.core.views.datetime") # Patching datetime where view might use it
    @patch("social_app.services.recommendations_service.datetime") # Patching datetime where service might use it
    def test_on_this_day_page_with_content_and_filtering(
        self, mock_reco_datetime, mock_views_datetime
    ):
        # from flask import url_for # Already imported at top

        mock_views_datetime.now.return_value = self.fixed_today
        mock_reco_datetime.now.return_value = self.fixed_today
        mock_reco_datetime.strptime = datetime.strptime

        self.login(self.test_user.username, "password")
        response = self.client.get(url_for('core.on_this_day_page')) # Use url_for
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

    @patch("social_app.core.views.datetime") # Patching datetime where view might use it
    @patch("social_app.services.recommendations_service.datetime") # Patching datetime where service might use it
    def test_on_this_day_page_only_posts(self, mock_reco_datetime, mock_views_datetime):
        mock_views_datetime.now.return_value = self.fixed_today
        mock_reco_datetime.now.return_value = self.fixed_today
        mock_reco_datetime.strptime = datetime.strptime

        # Create a new user for this test to ensure no other events interfere
        with self.app.app_context():
            test_user_for_only_posts = User(
                username="onlypostsuser",
                email="onlyposts@example.com",
                password_hash=generate_password_hash("password"),
            )
            self.db.session.add(test_user_for_only_posts)
            self.db.session.commit()
            test_user_for_only_posts_id = (
                test_user_for_only_posts.id
            )  # Get ID before context closes

        # Create a post for this user on "this day" in a previous year
        post_only = self._create_db_post(
            user_id=test_user_for_only_posts_id,
            title="Post From Last Year, No Events",
            content="This post is from Oct 26, 2022.",
            timestamp=datetime(
                2022, 10, 26, 9, 0, 0
            ),  # Matches self.fixed_today's date, previous year
        )

        self.login(test_user_for_only_posts.username, "password")
        response = self.client.get(url_for('core.on_this_day_page')) # Use url_for
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        self.assertIn(post_only.title, response_data)
        self.assertIn("No events from this day in previous years.", response_data)

        # Ensure the general "no content" message for events is there,
        # but not the one for posts, nor the overall "Nothing to show".
        self.assertNotIn("No posts from this day in previous years.", response_data)
        self.assertNotIn(
            "Nothing to show for 'On This Day' from previous years.", response_data
        )

        self.logout()

    @patch("social_app.core.views.datetime") # Patching datetime where view might use it
    @patch("social_app.services.recommendations_service.datetime") # Patching datetime where service might use it
    def test_on_this_day_page_only_events(self, mock_reco_datetime, mock_views_datetime):
        mock_views_datetime.now.return_value = self.fixed_today
        mock_reco_datetime.now.return_value = self.fixed_today
        mock_reco_datetime.strptime = datetime.strptime

        # Create a new user for this test to ensure no other posts interfere
        with self.app.app_context():
            test_user_for_only_events = User(
                username="onlyeventsuser",
                email="onlyevents@example.com",
                password_hash=generate_password_hash("password"),
            )
            self.db.session.add(test_user_for_only_events)
            self.db.session.commit()
            test_user_for_only_events_id = (
                test_user_for_only_events.id
            )  # Get ID before context closes

        # Create an event for this user on "this day" in a previous year
        event_only = self._create_db_event(
            user_id=test_user_for_only_events_id,
            title="Event From Last Year, No Posts",
            date_str="2022-10-26",  # Matches self.fixed_today's date, previous year
            description="This event is on Oct 26, 2022.",
        )

        self.login(test_user_for_only_events.username, "password")
        response = self.client.get(url_for('core.on_this_day_page')) # Use url_for
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        self.assertIn(event_only.title, response_data)
        self.assertIn("No posts from this day in previous years.", response_data)

        # Ensure the general "no content" message for posts is there,
        # but not the one for events, nor the overall "Nothing to show".
        self.assertNotIn("No events from this day in previous years.", response_data)
        self.assertNotIn(
            "Nothing to show for 'On This Day' from previous years.", response_data
        )

        self.logout()

    @patch("social_app.core.views.datetime") # Patching datetime where view might use it
    @patch("social_app.services.recommendations_service.datetime") # Patching datetime where service might use it
    def test_on_this_day_page_current_year_and_wrong_day_content_only(
        self, mock_reco_datetime, mock_views_datetime
    ):
        # 1. Mock datetime BEFORE any logic that might use it
        mock_views_datetime.now.return_value = self.fixed_today
        mock_reco_datetime.now.return_value = self.fixed_today
        # Ensure that strptime used by recommendations.py is the real one
        mock_reco_datetime.strptime = datetime.strptime

        # 2. Create a specific test user
        with self.app.app_context():
            no_otd_content_user = User(
                username="no_otd_content_user",
                email="no_otd@example.com",
                password_hash=generate_password_hash("password"),
            )
            self.db.session.add(no_otd_content_user)
            self.db.session.commit()
            no_otd_content_user_id = no_otd_content_user.id
        # Content creation was moved after fetching self.no_otd_content_user

        # Store user for login later
        # Re-fetch the user to ensure it's bound to the current session
        # and available for login and content creation.
        with self.app.app_context():
            self.no_otd_content_user = self.db.session.get(User, no_otd_content_user_id)

        # Corrected: Ensure content is created with the fetched user's ID
        # self.fixed_today is datetime(2023, 10, 26, 12, 0, 0)
        post_current_year_same_day = self._create_db_post(
            user_id=self.no_otd_content_user.id,
            title="Current Year Post (OTD)",
            content="This post is from Oct 26, 2023.",
            timestamp=datetime(2023, 10, 26, 10, 0, 0),
        )

        event_current_year_same_day = self._create_db_event(
            user_id=self.no_otd_content_user.id,
            title="Current Year Event (OTD)",
            date_str="2023-10-26",
            description="This event is on Oct 26, 2023.",
        )

        post_prev_year_diff_day = self._create_db_post(
            user_id=self.no_otd_content_user.id,
            title="Previous Year Wrong Day Post",
            content="This post is from Nov 26, 2022.",
            timestamp=datetime(2022, 11, 26, 10, 0, 0),
        )

        event_prev_year_diff_day = self._create_db_event(
            user_id=self.no_otd_content_user.id,
            title="Previous Year Wrong Day Event",
            date_str="2022-11-26",
            description="This event is on Nov 26, 2022.",
        )

        # Perform login and request
        self.login(self.no_otd_content_user.username, "password")
        response = self.client.get(url_for('core.on_this_day_page')) # Use url_for

        # Assert status code
        self.assertEqual(response.status_code, 200)

        response_data = response.get_data(as_text=True)

        # Assertions for content filtering
        # These items should NOT be displayed:
        # - Items from the current year (OTD logic only looks at previous years)
        # - Items from previous years but wrong day/month
        self.assertNotIn(post_current_year_same_day.title, response_data)
        self.assertNotIn(event_current_year_same_day.title, response_data)
        self.assertNotIn(post_prev_year_diff_day.title, response_data)
        self.assertNotIn(event_prev_year_diff_day.title, response_data)

        # Assertions for messages
        # Since no applicable posts/events from previous years are found,
        # specific messages for each type should be shown.
        self.assertIn("No posts from this day in previous years.", response_data)
        self.assertIn("No events from this day in previous years.", response_data)
        # The overall "Nothing to show" message should NOT be present if specific ones are.
        self.assertNotIn(
            "Nothing to show for 'On This Day' from previous years.", response_data
        )

        self.logout()

    @patch("social_app.core.views.datetime") # Patching datetime where view might use it
    @patch("social_app.services.recommendations_service.datetime") # Patching datetime where service might use it
    def test_on_this_day_page_content_from_wrong_day_only(
        self, mock_reco_datetime, mock_views_datetime
    ):
        # Mock datetime objects and set fixed_today
        mock_views_datetime.now.return_value = self.fixed_today
        mock_reco_datetime.now.return_value = self.fixed_today
        mock_reco_datetime.strptime = datetime.strptime

        # Create a new unique user
        with self.app.app_context():
            wrong_day_user = User(
                username="wrongdayuser",
                email="wrongday@example.com",
                password_hash=generate_password_hash("password"),
            )
            self.db.session.add(wrong_day_user)
            self.db.session.commit()
            wrong_day_user_id = wrong_day_user.id

        with self.app.app_context():
            self.wrong_day_user = self.db.session.get(User, wrong_day_user_id)

        # Create a post by this user from a previous year but a different day/month
        # self.fixed_today is datetime(2023, 10, 26, 12, 0, 0)
        post_wrong_day = self._create_db_post(
            user_id=self.wrong_day_user.id,
            title="Previous Year Wrong Day Post",
            content="This post is from Nov 25, 2022.",  # Different day and month
            timestamp=datetime(2022, 11, 25, 10, 0, 0),
        )

        # Create an event by this user from a previous year but a different day/month
        event_wrong_day = self._create_db_event(
            user_id=self.wrong_day_user.id,
            title="Previous Year Wrong Day Event",
            date_str="2022-09-15",  # Different day and month
            description="This event is on Sep 15, 2022.",
        )

        # Log in as the new test user
        self.login(self.wrong_day_user.username, "password")

        # Access the /onthisday page
        response = self.client.get(url_for('core.on_this_day_page')) # Use url_for

        # Assert that the response status code is 200
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        # Assert that the previously created post is not displayed
        self.assertNotIn(post_wrong_day.title, response_data)

        # Assert that the previously created event is not displayed
        self.assertNotIn(event_wrong_day.title, response_data)

        # Assert that the page shows "No posts from this day in previous years."
        self.assertIn("No posts from this day in previous years.", response_data)

        # Assert that the page shows "No events from this day in previous years."
        self.assertIn("No events from this day in previous years.", response_data)

        # Assert that the page does not show "Nothing to show for 'On This Day' from previous years."
        self.assertNotIn(
            "Nothing to show for 'On This Day' from previous years.", response_data
        )

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
        # self.event_invalid_date_format = self._create_db_event(
        #     user_id=self.test_user.id,
        #     title="Invalid Date Format Event",
        #     date_str="2022/10/26", # This will cause strptime to fail in _create_db_event
        # )
        # Commits are handled by AppTestCase helpers

    @patch("social_app.services.recommendations_service.datetime") # Corrected patch target
    @patch("social_app.api.routes.datetime") # Corrected patch target
    def test_on_this_day_with_content_and_filtering(
        self, mock_api_routes_datetime, mock_reco_datetime # Renamed mock params
    ):
        mock_reco_datetime.now.return_value = self.fixed_today
        mock_reco_datetime.strptime = datetime.strptime # Ensure strptime from datetime module is used
        mock_api_routes_datetime.now.return_value = self.fixed_today

        token = self._get_jwt_token(self.test_user.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.get(url_for('onthisdayresource'), headers=headers) # Use url_for with resource name
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

    @patch("social_app.services.recommendations_service.datetime") # Corrected patch target
    @patch("social_app.api.routes.datetime") # Corrected patch target
    def test_on_this_day_no_content_api(self, mock_api_routes_datetime, mock_reco_datetime): # Renamed mock params
        no_content_date = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_reco_datetime.now.return_value = no_content_date
        mock_reco_datetime.strptime = datetime.strptime
        mock_api_routes_datetime.now.return_value = no_content_date

        token = self._get_jwt_token(self.test_user.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.get(url_for('onthisdayresource'), headers=headers) # Use url_for
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertEqual(len(data["on_this_day_posts"]), 0)
        self.assertEqual(len(data["on_this_day_events"]), 0)

    def test_on_this_day_unauthenticated(self):
        response = self.client.get(url_for('onthisdayresource')) # Use url_for
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data["msg"], "Missing Authorization Header")
