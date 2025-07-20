import unittest
import json
from unittest.mock import patch, ANY
from datetime import datetime, timedelta, timezone

from tests.test_base import AppTestCase
from social_app.models.db_models import User, Post, Event
from werkzeug.security import generate_password_hash
from flask import url_for


class TestOnThisDay(AppTestCase):

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
        self.event_current_year = self._create_db_event(
            user_id=self.test_user.id,
            title="Current Year Event",
            date_str="2023-10-26",
            description="Event on Oct 26, 2023",
        )

    def test_on_this_day_page_unauthorized(self):
        with self.app.app_context():
            response = self.client.get(
                url_for("core.on_this_day_page"), follow_redirects=False
            )
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith(url_for("core.login")))

    def test_on_this_day_page_no_content(self):
        with self.app.app_context():
            with patch("social_app.core.views.datetime") as mock_views_datetime, patch(
                "social_app.services.recommendations_service.datetime"
            ) as mock_reco_datetime:
                no_content_date = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
                mock_views_datetime.now.return_value = no_content_date
                mock_reco_datetime.now.return_value = no_content_date
                mock_reco_datetime.strptime = datetime.strptime

                self.login(self.test_user.username, "password")
                response = self.client.get(url_for("core.on_this_day_page"))
                self.assertEqual(response.status_code, 200)
                response_data = response.get_data(as_text=True)

                self.assertIn("No posts from this day in previous years.", response_data)
                self.assertIn("No events from this day in previous years.", response_data)
                self.assertNotIn(
                    "Nothing to show for 'On This Day' from previous years.", response_data
                )
                self.logout()

    def test_on_this_day_page_with_content_and_filtering(self):
        with self.app.app_context():
            with patch("social_app.core.views.datetime") as mock_views_datetime, patch(
                "social_app.services.recommendations_service.datetime"
            ) as mock_reco_datetime:
                mock_views_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.strptime = datetime.strptime

                self.login(self.test_user.username, "password")
                response = self.client.get(url_for("core.on_this_day_page"))
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

    def test_on_this_day_page_only_posts(self):
        with self.app.app_context():
            with patch("social_app.core.views.datetime") as mock_views_datetime, patch(
                "social_app.services.recommendations_service.datetime"
            ) as mock_reco_datetime:
                mock_views_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.strptime = datetime.strptime

                with self.app.app_context():
                    test_user_for_only_posts = User(
                        username="onlypostsuser",
                        email="onlyposts@example.com",
                        password_hash=generate_password_hash("password"),
                    )
                    self.db.session.add(test_user_for_only_posts)
                    self.db.session.commit()
                    test_user_for_only_posts_id = test_user_for_only_posts.id

                post_only = self._create_db_post(
                    user_id=test_user_for_only_posts_id,
                    title="Post From Last Year, No Events",
                    content="This post is from Oct 26, 2022.",
                    timestamp=datetime(2022, 10, 26, 9, 0, 0),
                )

                self.login(test_user_for_only_posts.username, "password")
                response = self.client.get(url_for("core.on_this_day_page"))
                self.assertEqual(response.status_code, 200)
                response_data = response.get_data(as_text=True)

                self.assertIn(post_only.title, response_data)
                self.assertIn("No events from this day in previous years.", response_data)
                self.assertNotIn("No posts from this day in previous years.", response_data)
                self.assertNotIn(
                    "Nothing to show for 'On This Day' from previous years.", response_data
                )
                self.logout()

    def test_on_this_day_page_only_events(self):
        with self.app.app_context():
            with patch("social_app.core.views.datetime") as mock_views_datetime, patch(
                "social_app.services.recommendations_service.datetime"
            ) as mock_reco_datetime:
                mock_views_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.strptime = datetime.strptime

                with self.app.app_context():
                    test_user_for_only_events = User(
                        username="onlyeventsuser",
                        email="onlyevents@example.com",
                        password_hash=generate_password_hash("password"),
                    )
                    self.db.session.add(test_user_for_only_events)
                    self.db.session.commit()
                    test_user_for_only_events_id = test_user_for_only_events.id

                event_only = self._create_db_event(
                    user_id=test_user_for_only_events_id,
                    title="Event From Last Year, No Posts",
                    date_str="2022-10-26",
                    description="This event is on Oct 26, 2022.",
                )

                self.login(test_user_for_only_events.username, "password")
                response = self.client.get(url_for("core.on_this_day_page"))
                self.assertEqual(response.status_code, 200)
                response_data = response.get_data(as_text=True)

                self.assertIn(event_only.title, response_data)
                self.assertIn("No posts from this day in previous years.", response_data)
                self.assertNotIn("No events from this day in previous years.", response_data)
                self.assertNotIn(
                    "Nothing to show for 'On This Day' from previous years.", response_data
                )
                self.logout()

    def test_on_this_day_page_current_year_and_wrong_day_content_only(self):
        with self.app.app_context():
            with patch("social_app.core.views.datetime") as mock_views_datetime, patch(
                "social_app.services.recommendations_service.datetime"
            ) as mock_reco_datetime:
                mock_views_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.strptime = datetime.strptime

                with self.app.app_context():
                    no_otd_content_user = User(
                        username="no_otd_content_user",
                        email="no_otd@example.com",
                        password_hash=generate_password_hash("password"),
                    )
                    self.db.session.add(no_otd_content_user)
                    self.db.session.commit()
                    no_otd_content_user_id = no_otd_content_user.id
                with self.app.app_context():
                    self.no_otd_content_user = self.db.session.get(
                        User, no_otd_content_user_id
                    )

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

                self.login(self.no_otd_content_user.username, "password")
                response = self.client.get(url_for("core.on_this_day_page"))
                self.assertEqual(response.status_code, 200)
                response_data = response.get_data(as_text=True)

                self.assertNotIn(post_current_year_same_day.title, response_data)
                self.assertNotIn(event_current_year_same_day.title, response_data)
                self.assertNotIn(post_prev_year_diff_day.title, response_data)
                self.assertNotIn(event_prev_year_diff_day.title, response_data)
                self.assertIn("No posts from this day in previous years.", response_data)
                self.assertIn("No events from this day in previous years.", response_data)
                self.assertNotIn(
                    "Nothing to show for 'On This Day' from previous years.", response_data
                )
                self.logout()

    def test_on_this_day_page_content_from_wrong_day_only(self):
        with self.app.app_context():
            with patch("social_app.core.views.datetime") as mock_views_datetime, patch(
                "social_app.services.recommendations_service.datetime"
            ) as mock_reco_datetime:
                mock_views_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.strptime = datetime.strptime

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

                post_wrong_day = self._create_db_post(
                    user_id=self.wrong_day_user.id,
                    title="Previous Year Wrong Day Post",
                    content="This post is from Nov 25, 2022.",
                    timestamp=datetime(2022, 11, 25, 10, 0, 0),
                )
                event_wrong_day = self._create_db_event(
                    user_id=self.wrong_day_user.id,
                    title="Previous Year Wrong Day Event",
                    date_str="2022-09-15",
                    description="This event is on Sep 15, 2022.",
                )

                self.login(self.wrong_day_user.username, "password")
                response = self.client.get(url_for("core.on_this_day_page"))
                self.assertEqual(response.status_code, 200)
                response_data = response.get_data(as_text=True)

                self.assertNotIn(post_wrong_day.title, response_data)
                self.assertNotIn(event_wrong_day.title, response_data)
                self.assertIn("No posts from this day in previous years.", response_data)
                self.assertIn("No events from this day in previous years.", response_data)
                self.assertNotIn(
                    "Nothing to show for 'On This Day' from previous years.", response_data
                )
                self.logout()

    def test_on_this_day_with_content_and_filtering(self):
        with self.app.app_context():
            with patch(
                "social_app.services.recommendations_service.datetime"
            ) as mock_reco_datetime, patch(
                "social_app.api.routes.datetime"
            ) as mock_api_routes_datetime:
                mock_reco_datetime.now.return_value = self.fixed_today
                mock_reco_datetime.strptime = datetime.strptime
                mock_api_routes_datetime.now.return_value = self.fixed_today

                token = self._get_jwt_token(self.test_user.username, "password")
                headers = {"Authorization": f"Bearer {token}"}

                response = self.client.get(url_for("onthisdayresource"), headers=headers)
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

                event_ids_in_response = {e["id"] for e in data["on_this_day_events"]}
                self.assertNotIn(self.event_current_year.id, event_ids_in_response)

    def test_on_this_day_no_content_api(self):
        with self.app.app_context():
            with patch(
                "social_app.services.recommendations_service.datetime"
            ) as mock_reco_datetime, patch(
                "social_app.api.routes.datetime"
            ) as mock_api_routes_datetime:
                no_content_date = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
                mock_reco_datetime.now.return_value = no_content_date
                mock_reco_datetime.strptime = datetime.strptime
                mock_api_routes_datetime.now.return_value = no_content_date

                token = self._get_jwt_token(self.test_user.username, "password")
                headers = {"Authorization": f"Bearer {token}"}

                response = self.client.get(url_for("onthisdayresource"), headers=headers)
                self.assertEqual(response.status_code, 200)
                data = json.loads(response.data)

                self.assertEqual(len(data["on_this_day_posts"]), 0)
                self.assertEqual(len(data["on_this_day_events"]), 0)

    def test_on_this_day_unauthenticated(self):
        with self.app.app_context():
            response = self.client.get(url_for("onthisdayresource"))
            self.assertEqual(response.status_code, 401)
            data = json.loads(response.data)
            self.assertEqual(data["msg"], "Missing Authorization Header")
