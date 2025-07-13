import unittest
from unittest.mock import patch, ANY
from datetime import datetime, timedelta, timezone

from tests.test_base import AppTestCase
from flask import url_for


class TestUserStatus(AppTestCase):

    def test_set_status_full(self):
        self.login(self.user1.username, "password")
        status_text = "Feeling great today!"
        emoji = "🎉"

        response = self.client.post(
            url_for("core.set_status"),
            data={"status_text": status_text, "emoji": emoji},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.request.path.endswith(
                url_for("core.user_profile", username=self.user1.username)
            )
        )
        self.assertIn("Your status has been updated!", response.get_data(as_text=True))
        self.logout()

    def test_set_status_only_text(self):
        self.login(self.user1.username, "password")
        status_text = "Just text, no emoji."

        response = self.client.post(
            url_for("core.set_status"),
            data={"status_text": status_text, "emoji": ""},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.request.path.endswith(
                url_for("core.user_profile", username=self.user1.username)
            )
        )
        self.assertIn("Your status has been updated!", response.get_data(as_text=True))
        self.logout()

    def test_set_status_only_emoji(self):
        self.login(self.user1.username, "password")
        emoji = "🚀"

        response = self.client.post(
            url_for("core.set_status"),
            data={"status_text": "", "emoji": emoji},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.request.path.endswith(
                url_for("core.user_profile", username=self.user1.username)
            )
        )
        self.assertIn("Your status has been updated!", response.get_data(as_text=True))
        self.logout()

    def test_set_status_empty_input(self):
        self.login(self.user1.username, "password")

        response = self.client.post(
            url_for("core.set_status"),
            data={"status_text": "", "emoji": ""},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.request.path.endswith(
                url_for("core.user_profile", username=self.user1.username)
            )
        )
        self.assertIn(
            "Status text or emoji must be provided.", response.get_data(as_text=True)
        )
        self.logout()

    def test_view_status_on_profile(self):
        self.login(self.user2.username, "password")
        response = self.client.get(
            url_for("core.user_profile", username=self.user1.username)
        )
        self.assertEqual(response.status_code, 200)
        self.logout()

    def test_view_status_on_profile_no_status(self):
        self.login(self.user2.username, "password")
        response = self.client.get(
            url_for("core.user_profile", username=self.user1.username)
        )
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)
        self.logout()

    def test_set_status_form_visible_on_own_profile(self):
        self.login(self.user1.username, "password")
        response = self.client.get(
            url_for("core.user_profile", username=self.user1.username)
        )
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        self.assertIn(f'action="{url_for("core.set_status")}"', response_data)
        self.assertIn('name="status_text"', response_data)
        self.assertIn('name="emoji"', response_data)
        self.assertIn('type="submit"', response_data)
        self.assertIn("Set Status", response_data)
        self.logout()

    def test_set_status_form_not_visible_on_others_profile(self):
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
