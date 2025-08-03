import unittest
from unittest.mock import patch, ANY
from datetime import datetime, timedelta, timezone

from tests.test_base import AppTestCase
from flask import url_for, get_flashed_messages


class TestUserStatus(AppTestCase):

    def test_set_status_full(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            status_text = "Feeling great today!"
            emoji = "🎉"

            with self.client as c:
                response = c.post(
                    url_for("core.set_status"),
                    data={"status_text": status_text, "emoji": emoji},
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 302)
                with c.session_transaction() as session:
                    flashed_messages = session["_flashes"]
                    self.assertTrue(
                        any("Your status has been updated!" in message[1] for message in flashed_messages)
                    )

            response = self.client.get(url_for("core.user_profile", username=self.user1.username))
            self.assertEqual(response.status_code, 200)
            response_data = response.get_data(as_text=True)
            self.assertIn(status_text, response_data)
            self.assertIn(emoji, response_data)
            self.logout()

    def test_set_status_only_text(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            status_text = "Just text, no emoji."

            with self.client as c:
                response = c.post(
                    url_for("core.set_status"),
                    data={"status_text": status_text, "emoji": ""},
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 302)
                with c.session_transaction() as session:
                    flashed_messages = session["_flashes"]
                    self.assertTrue(
                        any("Your status has been updated!" in message[1] for message in flashed_messages)
                    )

            response = self.client.get(url_for("core.user_profile", username=self.user1.username))
            self.assertEqual(response.status_code, 200)
            response_data = response.get_data(as_text=True)
            self.assertIn(status_text, response_data)
            self.logout()

    def test_set_status_only_emoji(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            emoji = "🚀"

            with self.client as c:
                response = c.post(
                    url_for("core.set_status"),
                    data={"status_text": "", "emoji": emoji},
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 302)
                with c.session_transaction() as session:
                    flashed_messages = session["_flashes"]
                    self.assertTrue(
                        any("Your status has been updated!" in message[1] for message in flashed_messages)
                    )

            response = self.client.get(url_for("core.user_profile", username=self.user1.username))
            self.assertEqual(response.status_code, 200)
            response_data = response.get_data(as_text=True)
            self.assertIn(emoji, response_data)
            self.logout()

    def test_set_status_empty_input(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")

            with self.client as c:
                response = c.post(
                    url_for("core.set_status"),
                    data={"status_text": "", "emoji": ""},
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 302)
                with c.session_transaction() as session:
                    flashed_messages = session["_flashes"]
                    self.assertTrue(
                        any("Status text or emoji must be provided." in message[1] for message in flashed_messages)
                    )
            self.logout()

    def test_view_status_on_profile(self):
        with self.app.app_context():
            self.login(self.user2.username, "password")
            response = self.client.get(
                url_for("core.user_profile", username=self.user1.username)
            )
            self.assertEqual(response.status_code, 200)
            self.logout()

    def test_view_status_on_profile_no_status(self):
        with self.app.app_context():
            self.login(self.user2.username, "password")
            response = self.client.get(
                url_for("core.user_profile", username=self.user1.username)
            )
            self.assertEqual(response.status_code, 200)
            response_data = response.get_data(as_text=True)
            self.logout()

    def test_set_status_form_visible_on_own_profile(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            response = self.client.get(
                url_for("core.user_profile", username=self.user1.username)
            )
            self.assertEqual(response.status_code, 200)
            response_data = response.get_data(as_text=True)

            self.assertIn(f'action="{url_for("core.set_status", _external=False)}"', response_data)
            self.assertIn('name="status_text"', response_data)
            self.assertIn('name="emoji"', response_data)
            self.assertIn('type="submit"', response_data)
            self.logout()

    def test_set_status_form_not_visible_on_others_profile(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            response = self.client.get(
                url_for("core.user_profile", username=self.user2.username)
            )
            self.assertEqual(response.status_code, 200)
            response_data = response.get_data(as_text=True)

            self.assertNotIn(f'action="{url_for("core.set_status")}"', response_data)
            self.assertNotIn('name="status_text"', response_data)
            self.assertNotIn('name="emoji"', response_data)
            self.logout()
