import unittest
import json
from unittest.mock import patch, ANY, MagicMock
from datetime import datetime, timedelta

from tests.test_base import AppTestCase
# Assuming models are available for AppTestCase and endpoint operations
# from models import User, Poll, PollOption, PollVote

class TestPollAPI(AppTestCase):

    def _create_poll_via_api(self, token, question_text, options_texts):
        """Helper to create a poll via API and return its ID."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        poll_data = {"question": question_text, "options": options_texts}
        response = self.client.post("/api/polls", headers=headers, json=poll_data)
        self.assertEqual(response.status_code, 201, f"Failed to create poll '{question_text}': {response.get_json()}")
        return response.get_json()["poll"]["id"]

    def test_create_poll_success(self):
        # Original test, not the focus of this subtask run
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        poll_data = {
            "question": "What is your favorite color?",
            "options": ["Red", "Green", "Blue"],
        }
        response = self.client.post("/api/polls", headers=headers, json=poll_data)
        if response.status_code == 201: # Basic check
            data = response.get_json()
            self.assertEqual(data["message"], "Poll created successfully")
        self.assertEqual(response.status_code, 201, f"Poll creation failed: {response.data.decode()}")


    def test_create_poll_missing_data(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        response = self.client.post("/api/polls", headers=headers, json={"options": ["Yes", "No"]})
        self.assertEqual(response.status_code, 400)

    def test_create_poll_too_few_options(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        poll_data = {"question": "Need more options?", "options": ["Just one"]}
        response = self.client.post("/api/polls", headers=headers, json=poll_data)
        self.assertEqual(response.status_code, 400)

    def test_create_poll_unauthenticated(self):
        headers = {"Content-Type": "application/json"}
        poll_data = {"question": "Who can post this?", "options": ["Me", "You"]}
        response = self.client.post("/api/polls", headers=headers, json=poll_data)
        self.assertEqual(response.status_code, 401)

    def test_list_polls_empty(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.get("/api/polls", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("polls", data)
        self.assertEqual(len(data["polls"]), 0)

    def test_list_polls_success(self):
        token = self._get_jwt_token(self.user1.username, "password")
        self._create_poll_via_api(token, "Poll One", ["A1", "B1"])
        self._create_poll_via_api(token, "Poll Two", ["A2", "B2"])

        headers = {"Authorization": f"Bearer {token}"}
        response_list = self.client.get("/api/polls", headers=headers)
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

        # Setup: Create a poll
        created_poll_id = self._create_poll_via_api(token, question_text, options_texts)
        self.assertIsNotNone(created_poll_id)

        # Action: Get the created poll
        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.get(f"/api/polls/{created_poll_id}", headers=headers)

        # Assertions
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("poll", data)
        self.assertEqual(data["poll"]["id"], created_poll_id)
        self.assertEqual(data["poll"]["question"], question_text)
        self.assertEqual(data["poll"]["author_username"], self.user1.username)
        self.assertEqual(len(data["poll"]["options"]), len(options_texts))
        retrieved_option_texts = sorted([opt['text'] for opt in data["poll"]["options"]])
        self.assertEqual(retrieved_option_texts, sorted(options_texts))


    def test_get_poll_not_found(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.get("/api/polls/99999", headers=headers) # Assuming 99999 does not exist
        self.assertEqual(response.status_code, 404)

    def test_delete_poll_success(self):
        token = self._get_jwt_token(self.user1.username, "password")

        # Setup: Create a poll
        created_poll_id = self._create_poll_via_api(token, "To Be Deleted", ["DelOpt1", "DelOpt2"])
        self.assertIsNotNone(created_poll_id)

        # Action: Delete the poll
        headers = {"Authorization": f"Bearer {token}"}
        response_delete = self.client.delete(f"/api/polls/{created_poll_id}", headers=headers)

        # Assertions for delete
        self.assertEqual(response_delete.status_code, 200) # API returns 200 with message
        delete_data = response_delete.get_json()
        self.assertEqual(delete_data["message"], "Poll deleted")

        # Verification: Try to get the deleted poll
        response_get = self.client.get(f"/api/polls/{created_poll_id}", headers=headers)
        self.assertEqual(response_get.status_code, 404, "Poll should be deleted and not found.")


    def test_delete_poll_unauthorized(self):
        # Setup: User1 creates a poll
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        poll_id_user1 = self._create_poll_via_api(token_user1, "User1's Poll", ["U1O1", "U1O2"])

        # Action: User2 tries to delete User1's poll
        token_user2 = self._get_jwt_token(self.user2.username, "password") # Assumes self.user2 exists
        headers_user2 = {"Authorization": f"Bearer {token_user2}"}
        response = self.client.delete(f"/api/polls/{poll_id_user1}", headers=headers_user2)

        # Assertion: Should be forbidden (or not found if policy is to hide existence)
        # Based on current API, it's 403 if poll exists but not owned by user
        self.assertEqual(response.status_code, 403)


    def test_delete_poll_unauthenticated(self):
        # No token provided
        # To ensure this test is valid, we might need a poll to exist.
        # However, the auth check should happen first.
        # Let's create one to ensure the 401 is due to auth, not a potential 404.
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        poll_id = self._create_poll_via_api(token_user1, "Temporary Poll", ["T1", "T2"])

        response = self.client.delete(f"/api/polls/{poll_id}")
        self.assertEqual(response.status_code, 401)

    def test_delete_poll_not_found(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.delete("/api/polls/99999", headers=headers) # Assuming 99999 does not exist
        self.assertEqual(response.status_code, 404)

    # Stubs for vote tests - these would require more setup (e.g. ensuring options exist with known IDs)
    def test_vote_on_poll_success(self): pass
    def test_vote_on_poll_already_voted(self): pass
    def test_vote_on_poll_invalid_option_id_for_poll(self): pass

    def test_vote_on_poll_option_not_in_specific_poll(self):
        """
        Test voting on a poll with an option ID that belongs to a different poll.
        The API should return a 404 or 400 error.
        """
        # a. Obtain a JWT token for self.user1
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        headers_user1 = {
            "Authorization": f"Bearer {token_user1}",
            "Content-Type": "application/json",
        }

        # b. Create the first poll (Poll 1)
        poll1_question = "Poll 1: Best Season?"
        poll1_options = ["P1Opt1: Summer", "P1Opt2: Winter"]
        poll1_id = self._create_poll_via_api(token_user1, poll1_question, poll1_options)

        # c. Create a second poll (Poll 2)
        poll2_question = "Poll 2: Best Animal?"
        poll2_options = ["P2Opt1: Dog", "P2Opt2: Cat"]
        poll2_id = self._create_poll_via_api(token_user1, poll2_question, poll2_options)

        # d. Retrieve the details of the second poll (specifically its option IDs)
        response_get_poll2 = self.client.get(f"/api/polls/{poll2_id}", headers=headers_user1)
        self.assertEqual(response_get_poll2.status_code, 200, "Failed to retrieve Poll 2 details")
        poll2_data = response_get_poll2.get_json()

        # Ensure poll2_data and its options are as expected
        self.assertIn("poll", poll2_data, "Poll data missing in response for Poll 2")
        self.assertIn("options", poll2_data["poll"], "Options missing in poll data for Poll 2")
        self.assertTrue(len(poll2_data["poll"]["options"]) > 0, "No options found for Poll 2")

        option_from_poll2_id = poll2_data["poll"]["options"][0]["id"] # Take the first option from Poll 2

        # e. Attempt to vote on the first poll (poll1_id) using an option_id from the second poll
        vote_data = {"option_id": option_from_poll2_id}
        response_vote = self.client.post(f"/api/polls/{poll1_id}/vote", headers=headers_user1, json=vote_data)

        # f. Assert that the response status code is 404 (or 400)
        # Based on common API behavior for such cases, 400 or 404 is expected.
        # The prompt mentions "Poll option not found or does not belong to this poll"
        # which could map to either. Let's check for 400 as per the prompt's hint.
        # If the original code used 404, this might need adjustment.
        self.assertIn(response_vote.status_code, [400, 404],
                      f"Unexpected status code: {response_vote.status_code}. Response: {response_vote.get_json()}")

        # g. Assert that the response JSON contains an appropriate error message
        response_json = response_vote.get_json()
        self.assertIn("message", response_json)
        # The specific message can vary, checking for non-emptiness or a keyword might be robust.
        # For now, let's trust the existing API's error message format.
        # A more specific check could be:
        # self.assertTrue("not found" in response_json["message"].lower() or \
        #                 "does not belong" in response_json["message"].lower())
        # Based on the subtask: "Poll option not found or does not belong to this poll"
        expected_message_fragment_1 = "Poll option not found"
        expected_message_fragment_2 = "does not belong to this poll"
        actual_message = response_json["message"]

        self.assertTrue(
            expected_message_fragment_1.lower() in actual_message.lower() or \
            expected_message_fragment_2.lower() in actual_message.lower(),
            f"Error message '{actual_message}' does not contain expected fragments."
        )

    def test_vote_on_poll_unauthenticated(self): pass
    def test_vote_on_poll_non_existent_poll(self): pass

if __name__ == "__main__":
    unittest.main()
