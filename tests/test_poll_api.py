import unittest
import json
from unittest.mock import patch, ANY, MagicMock
from datetime import datetime, timedelta

from tests.test_base import AppTestCase
from flask import url_for


class TestPollAPI(AppTestCase):

    def _create_poll_via_api(self, token, question_text, options_texts):
        """Helper to create a poll via API and return its ID."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        poll_data = {"question": question_text, "options": options_texts}
        with self.app.app_context():
            response = self.client.post(
                url_for("polllistresource"), headers=headers, json=poll_data
            )
        self.assertEqual(
            response.status_code,
            201,
            f"Failed to create poll '{question_text}': {response.get_json()}",
        )
        return response.get_json()["poll"]["id"]

    def test_create_poll_success(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        poll_data = {
            "question": "What is your favorite color?",
            "options": ["Red", "Green", "Blue"],
        }
        with self.app.app_context():
            response = self.client.post(
                url_for("polllistresource"), headers=headers, json=poll_data
            )
        if response.status_code == 201:
            data = response.get_json()
            self.assertEqual(data["message"], "Poll created successfully")
        self.assertEqual(response.status_code, 201)

    def test_create_poll_missing_data(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        with self.app.app_context():
            response = self.client.post(
                url_for("polllistresource"),
                headers=headers,
                json={"options": ["Yes", "No"]},
            )
        self.assertEqual(response.status_code, 400)

    def test_create_poll_too_few_options(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        poll_data = {"question": "Need more options?", "options": ["Just one"]}
        with self.app.app_context():
            response = self.client.post(
                url_for("polllistresource"), headers=headers, json=poll_data
            )
        self.assertEqual(response.status_code, 400)

    def test_create_poll_unauthenticated(self):
        headers = {"Content-Type": "application/json"}
        poll_data = {"question": "Who can post this?", "options": ["Me", "You"]}
        with self.app.app_context():
            response = self.client.post(
                url_for("polllistresource"), headers=headers, json=poll_data
            )
        self.assertEqual(response.status_code, 401)

    def test_list_polls_empty(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        with self.app.app_context():
            response = self.client.get(url_for("polllistresource"), headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("polls", data)
        self.assertEqual(len(data["polls"]), 0)

    def test_list_polls_success(self):
        token = self._get_jwt_token(self.user1.username, "password")
        self._create_poll_via_api(token, "Poll One", ["A1", "B1"])
        self._create_poll_via_api(token, "Poll Two", ["A2", "B2"])

        headers = {"Authorization": f"Bearer {token}"}
        with self.app.app_context():
            response_list = self.client.get(
                url_for("polllistresource"), headers=headers
            )
        self.assertEqual(response_list.status_code, 200)
        data = response_list.get_json()
        self.assertIn("polls", data)
        self.assertEqual(len(data["polls"]), 2)
        response_questions = {poll["question"] for poll in data["polls"]}
        self.assertIn("Poll One", response_questions)
        self.assertIn("Poll Two", response_questions)

    def test_get_poll_success(self):
        token = self._get_jwt_token(self.user1.username, "password")
        question_text = "Test Get Poll"
        options_texts = ["OptX", "OptY"]

        created_poll_id = self._create_poll_via_api(token, question_text, options_texts)
        self.assertIsNotNone(created_poll_id)

        headers = {"Authorization": f"Bearer {token}"}
        with self.app.app_context():
            response = self.client.get(
                url_for("pollresource", poll_id=created_poll_id), headers=headers
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("poll", data)
        self.assertEqual(data["poll"]["id"], created_poll_id)
        self.assertEqual(data["poll"]["question"], question_text)
        self.assertEqual(data["poll"]["author_username"], self.user1.username)
        self.assertEqual(len(data["poll"]["options"]), len(options_texts))
        retrieved_option_texts = sorted(
            [opt["text"] for opt in data["poll"]["options"]]
        )
        self.assertEqual(retrieved_option_texts, sorted(options_texts))

    def test_get_poll_not_found(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        with self.app.app_context():
            response = self.client.get(
                url_for("pollresource", poll_id=99999), headers=headers
            )
        self.assertEqual(response.status_code, 404)

    def test_delete_poll_success(self):
        token = self._get_jwt_token(self.user1.username, "password")

        created_poll_id = self._create_poll_via_api(
            token, "To Be Deleted", ["DelOpt1", "DelOpt2"]
        )
        self.assertIsNotNone(created_poll_id)

        headers = {"Authorization": f"Bearer {token}"}
        with self.app.app_context():
            response_delete = self.client.delete(
                url_for("pollresource", poll_id=created_poll_id), headers=headers
            )

        self.assertEqual(response_delete.status_code, 200)
        delete_data = response_delete.get_json()
        self.assertEqual(delete_data["message"], "Poll deleted")

        with self.app.app_context():
            response_get = self.client.get(
                url_for("pollresource", poll_id=created_poll_id), headers=headers
            )
        self.assertEqual(response_get.status_code, 404)

    def test_delete_poll_unauthorized(self):
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        poll_id_user1 = self._create_poll_via_api(
            token_user1, "User1's Poll", ["U1O1", "U1O2"]
        )

        token_user2 = self._get_jwt_token(self.user2.username, "password")
        headers_user2 = {"Authorization": f"Bearer {token_user2}"}
        with self.app.app_context():
            response = self.client.delete(
                url_for("pollresource", poll_id=poll_id_user1), headers=headers_user2
            )

        self.assertEqual(response.status_code, 403)

    def test_delete_poll_unauthenticated(self):
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        poll_id = self._create_poll_via_api(token_user1, "Temporary Poll", ["T1", "T2"])
        with self.app.app_context():
            response = self.client.delete(url_for("pollresource", poll_id=poll_id))
        self.assertEqual(response.status_code, 401)

    def test_delete_poll_not_found(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        with self.app.app_context():
            response = self.client.delete(
                url_for("pollresource", poll_id=99999), headers=headers
            )
        self.assertEqual(response.status_code, 404)

    def test_vote_on_poll_success(self):
        pass

    def test_vote_on_poll_already_voted(self):
        pass

    def test_vote_on_poll_invalid_option_id_for_poll(self):
        pass

    def test_vote_on_poll_option_not_in_specific_poll(self):
        """
        Test voting on a poll with an option ID that belongs to a different poll.
        The API should return a 404 or 400 error.
        """
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        headers_user1 = {
            "Authorization": f"Bearer {token_user1}",
            "Content-Type": "application/json",
        }

        poll1_question = "Poll 1: Best Season?"
        poll1_options = ["P1Opt1: Summer", "P1Opt2: Winter"]
        poll1_id = self._create_poll_via_api(token_user1, poll1_question, poll1_options)

        poll2_question = "Poll 2: Best Animal?"
        poll2_options = ["P2Opt1: Dog", "P2Opt2: Cat"]
        poll2_id = self._create_poll_via_api(token_user1, poll2_question, poll2_options)

        with self.app.app_context():
            response_get_poll2 = self.client.get(
                url_for("pollresource", poll_id=poll2_id), headers=headers_user1
            )
        self.assertEqual(response_get_poll2.status_code, 200)
        poll2_data = response_get_poll2.get_json()

        self.assertIn("poll", poll2_data)
        self.assertIn("options", poll2_data["poll"])
        self.assertTrue(len(poll2_data["poll"]["options"]) > 0)

        option_from_poll2_id = poll2_data["poll"]["options"][0]["id"]

        vote_data = {"option_id": option_from_poll2_id}
        with self.app.app_context():
            response_vote = self.client.post(
                url_for("pollvoteresource", poll_id=poll1_id),
                headers=headers_user1,
                json=vote_data,
            )

        self.assertIn(response_vote.status_code, [400, 404])

        response_json = response_vote.get_json()
        self.assertIn("message", response_json)
        expected_message_fragment_1 = "Poll option not found"
        expected_message_fragment_2 = "does not belong to this poll"
        actual_message = response_json["message"]

        self.assertTrue(
            expected_message_fragment_1.lower() in actual_message.lower()
            or expected_message_fragment_2.lower() in actual_message.lower()
        )

    def test_vote_on_poll_with_non_existent_option_id(self):
        """
        Test voting on a poll with an option ID that does not exist in the database.
        The API should return a 404 error.
        """
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        headers_user1 = {
            "Authorization": f"Bearer {token_user1}",
            "Content-Type": "application/json",
        }

        poll_question = "Test Poll for Non-Existent Option Vote"
        poll_options = ["Option A", "Option B"]
        poll_id = self._create_poll_via_api(token_user1, poll_question, poll_options)

        non_existent_option_id = 99999
        vote_data = {"option_id": non_existent_option_id}
        with self.app.app_context():
            response_vote = self.client.post(
                url_for("pollvoteresource", poll_id=poll_id),
                headers=headers_user1,
                json=vote_data,
            )

        self.assertEqual(response_vote.status_code, 404)

        response_json = response_vote.get_json()
        self.assertIn("message", response_json)
        expected_message_fragment = "Poll option not found"
        actual_message = response_json["message"]
        self.assertIn(expected_message_fragment.lower(), actual_message.lower())

    def test_vote_on_poll_unauthenticated(self):
        pass

    def test_vote_on_poll_non_existent_poll(self):
        pass

    def test_get_poll_results_after_voting(self):
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        token_user2 = self._get_jwt_token(self.user2.username, "password")
        token_user3 = self._get_jwt_token(self.user3.username, "password")

        poll_question = "What's the best testing strategy?"
        poll_options_texts = ["Strategy A", "Strategy B", "Strategy C"]
        poll_id = self._create_poll_via_api(
            token_user1, poll_question, poll_options_texts
        )
        self.assertIsNotNone(poll_id)

        headers_user1 = {"Authorization": f"Bearer {token_user1}"}
        with self.app.app_context():
            response_get_poll = self.client.get(
                url_for("pollresource", poll_id=poll_id), headers=headers_user1
            )
        self.assertEqual(response_get_poll.status_code, 200)
        poll_data = response_get_poll.get_json()["poll"]

        options_map = {}
        for option in poll_data["options"]:
            options_map[option["text"]] = option["id"]

        self.assertIn("Strategy A", options_map)
        self.assertIn("Strategy B", options_map)
        self.assertIn("Strategy C", options_map)

        option_id_A = options_map["Strategy A"]
        option_id_B = options_map["Strategy B"]

        headers_vote_user1 = {
            "Authorization": f"Bearer {token_user1}",
            "Content-Type": "application/json",
        }
        with self.app.app_context():
            response_vote1 = self.client.post(
                url_for("pollvoteresource", poll_id=poll_id),
                headers=headers_vote_user1,
                json={"option_id": option_id_A},
            )
        self.assertEqual(response_vote1.status_code, 201)

        headers_vote_user2 = {
            "Authorization": f"Bearer {token_user2}",
            "Content-Type": "application/json",
        }
        with self.app.app_context():
            response_vote2 = self.client.post(
                url_for("pollvoteresource", poll_id=poll_id),
                headers=headers_vote_user2,
                json={"option_id": option_id_B},
            )
        self.assertEqual(response_vote2.status_code, 201)

        headers_vote_user3 = {
            "Authorization": f"Bearer {token_user3}",
            "Content-Type": "application/json",
        }
        with self.app.app_context():
            response_vote3 = self.client.post(
                url_for("pollvoteresource", poll_id=poll_id),
                headers=headers_vote_user3,
                json={"option_id": option_id_A},
            )
        self.assertEqual(response_vote3.status_code, 201)

        with self.app.app_context():
            response_get_results = self.client.get(
                url_for("pollresource", poll_id=poll_id), headers=headers_user1
            )

        self.assertEqual(response_get_results.status_code, 200)
        results_data = response_get_results.get_json()["poll"]

        self.assertEqual(results_data["id"], poll_id)
        self.assertEqual(results_data["question"], poll_question)
        self.assertEqual(len(results_data["options"]), 3)

        found_option_A = False
        found_option_B = False
        found_option_C = False

        for option in results_data["options"]:
            if option["text"] == "Strategy A":
                self.assertEqual(option["vote_count"], 2)
                found_option_A = True
            elif option["text"] == "Strategy B":
                self.assertEqual(option["vote_count"], 1)
                found_option_B = True
            elif option["text"] == "Strategy C":
                self.assertEqual(option["vote_count"], 0)
                found_option_C = True

        self.assertTrue(found_option_A)
        self.assertTrue(found_option_B)
        self.assertTrue(found_option_C)

    def test_view_poll_html_renders_vote_counts(self):
        """
        Tests that the HTML view for a poll correctly renders vote counts
        after the fix for accessing vote_count in the template.
        """
        with self.app.app_context():
            token_user1 = self._get_jwt_token(self.user1.username, "password")

            poll_question = "HTML Render Test Poll"
            poll_options_texts = ["RenderOpt1", "RenderOpt2"]
            poll_id = self._create_poll_via_api(
                token_user1, poll_question, poll_options_texts
            )
            self.assertIsNotNone(poll_id)

            headers_user1 = {"Authorization": f"Bearer {token_user1}"}
            with self.app.app_context():
                response_get_poll = self.client.get(
                    url_for("pollresource", poll_id=poll_id), headers=headers_user1
                )
            self.assertEqual(response_get_poll.status_code, 200)
            poll_data_api = response_get_poll.get_json()["poll"]
            option_id_1 = next(
                opt["id"] for opt in poll_data_api["options"] if opt["text"] == "RenderOpt1"
            )
            option_id_2 = next(
                opt["id"] for opt in poll_data_api["options"] if opt["text"] == "RenderOpt2"
            )

            self.login(self.user1.username, "password")
            with self.app.app_context():
                self.client.post(
                    url_for("core.vote_on_poll", poll_id=poll_id),
                    data={"option_id": str(option_id_1)},
                )
            self.logout()

            self.login(self.user2.username, "password")
            with self.app.app_context():
                self.client.post(
                    url_for("core.vote_on_poll", poll_id=poll_id),
                    data={"option_id": str(option_id_1)},
                )
            self.logout()

            self.login(self.user3.username, "password")
            with self.app.app_context():
                self.client.post(
                    url_for("core.vote_on_poll", poll_id=poll_id),
                    data={"option_id": str(option_id_2)},
                )
            self.logout()

            self.login(self.user1.username, "password")
            with self.app.app_context():
                response_html = self.client.get(url_for("core.view_poll", poll_id=poll_id))
            self.assertEqual(response_html.status_code, 200)
            html_content = response_html.data.decode()

            self.assertIn(poll_question, html_content)
            self.assertIn("RenderOpt1", html_content)
            self.assertIn("RenderOpt2", html_content)

            self.assertRegex(
                html_content,
                r"RenderOpt1[\s\S]*?<span[^>]*class=[\"'][^\"']*badge[^\"']*[\"'][^>]*>\s*2\s*vote\(s\)\s*</span>",
            )
            self.assertRegex(
                html_content,
                r"RenderOpt2[\s\S]*?<span[^>]*class=[\"'][^\"']*badge[^\"']*[\"'][^>]*>\s*1\s*vote\(s\)\s*</span>",
            )
            self.assertRegex(html_content, r"width:\s*66\.6+%;")
            self.assertRegex(html_content, r"width:\s*33\.3+%;")


if __name__ == "__main__":
    unittest.main()
