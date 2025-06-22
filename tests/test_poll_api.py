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
        self.assertEqual(
            response.status_code,
            201,
            f"Failed to create poll '{question_text}': {response.get_json()}",
        )
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
        if response.status_code == 201:  # Basic check
            data = response.get_json()
            self.assertEqual(data["message"], "Poll created successfully")
        self.assertEqual(
            response.status_code, 201, f"Poll creation failed: {response.data.decode()}"
        )

    def test_create_poll_missing_data(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        response = self.client.post(
            "/api/polls", headers=headers, json={"options": ["Yes", "No"]}
        )
        self.assertEqual(response.status_code, 400)

    def test_create_poll_too_few_options(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
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
        retrieved_option_texts = sorted(
            [opt["text"] for opt in data["poll"]["options"]]
        )
        self.assertEqual(retrieved_option_texts, sorted(options_texts))

    def test_get_poll_not_found(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.get(
            "/api/polls/99999", headers=headers
        )  # Assuming 99999 does not exist
        self.assertEqual(response.status_code, 404)

    def test_delete_poll_success(self):
        token = self._get_jwt_token(self.user1.username, "password")

        # Setup: Create a poll
        created_poll_id = self._create_poll_via_api(
            token, "To Be Deleted", ["DelOpt1", "DelOpt2"]
        )
        self.assertIsNotNone(created_poll_id)

        # Action: Delete the poll
        headers = {"Authorization": f"Bearer {token}"}
        response_delete = self.client.delete(
            f"/api/polls/{created_poll_id}", headers=headers
        )

        # Assertions for delete
        self.assertEqual(
            response_delete.status_code, 200
        )  # API returns 200 with message
        delete_data = response_delete.get_json()
        self.assertEqual(delete_data["message"], "Poll deleted")

        # Verification: Try to get the deleted poll
        response_get = self.client.get(f"/api/polls/{created_poll_id}", headers=headers)
        self.assertEqual(
            response_get.status_code, 404, "Poll should be deleted and not found."
        )

    def test_delete_poll_unauthorized(self):
        # Setup: User1 creates a poll
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        poll_id_user1 = self._create_poll_via_api(
            token_user1, "User1's Poll", ["U1O1", "U1O2"]
        )

        # Action: User2 tries to delete User1's poll
        token_user2 = self._get_jwt_token(
            self.user2.username, "password"
        )  # Assumes self.user2 exists
        headers_user2 = {"Authorization": f"Bearer {token_user2}"}
        response = self.client.delete(
            f"/api/polls/{poll_id_user1}", headers=headers_user2
        )

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
        response = self.client.delete(
            "/api/polls/99999", headers=headers
        )  # Assuming 99999 does not exist
        self.assertEqual(response.status_code, 404)

    # Stubs for vote tests - these would require more setup (e.g. ensuring options exist with known IDs)
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
        response_get_poll2 = self.client.get(
            f"/api/polls/{poll2_id}", headers=headers_user1
        )
        self.assertEqual(
            response_get_poll2.status_code, 200, "Failed to retrieve Poll 2 details"
        )
        poll2_data = response_get_poll2.get_json()

        # Ensure poll2_data and its options are as expected
        self.assertIn("poll", poll2_data, "Poll data missing in response for Poll 2")
        self.assertIn(
            "options", poll2_data["poll"], "Options missing in poll data for Poll 2"
        )
        self.assertTrue(
            len(poll2_data["poll"]["options"]) > 0, "No options found for Poll 2"
        )

        option_from_poll2_id = poll2_data["poll"]["options"][0][
            "id"
        ]  # Take the first option from Poll 2

        # e. Attempt to vote on the first poll (poll1_id) using an option_id from the second poll
        vote_data = {"option_id": option_from_poll2_id}
        response_vote = self.client.post(
            f"/api/polls/{poll1_id}/vote", headers=headers_user1, json=vote_data
        )

        # f. Assert that the response status code is 404 (or 400)
        # Based on common API behavior for such cases, 400 or 404 is expected.
        # The prompt mentions "Poll option not found or does not belong to this poll"
        # which could map to either. Let's check for 400 as per the prompt's hint.
        # If the original code used 404, this might need adjustment.
        self.assertIn(
            response_vote.status_code,
            [400, 404],
            f"Unexpected status code: {response_vote.status_code}. Response: {response_vote.get_json()}",
        )

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
            expected_message_fragment_1.lower() in actual_message.lower()
            or expected_message_fragment_2.lower() in actual_message.lower(),
            f"Error message '{actual_message}' does not contain expected fragments.",
        )

    def test_vote_on_poll_with_non_existent_option_id(self):
        """
        Test voting on a poll with an option ID that does not exist in the database.
        The API should return a 404 error.
        """
        # a. Obtain a JWT token for self.user1
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        headers_user1 = {
            "Authorization": f"Bearer {token_user1}",
            "Content-Type": "application/json",
        }

        # b. Create a poll
        poll_question = "Test Poll for Non-Existent Option Vote"
        poll_options = ["Option A", "Option B"]
        poll_id = self._create_poll_via_api(token_user1, poll_question, poll_options)

        # c. Attempt to vote on the poll using a non-existent option_id
        non_existent_option_id = 99999  # An ID that is highly unlikely to exist
        vote_data = {"option_id": non_existent_option_id}
        response_vote = self.client.post(
            f"/api/polls/{poll_id}/vote", headers=headers_user1, json=vote_data
        )

        # d. Assert that the response status code is 404
        self.assertEqual(
            response_vote.status_code,
            404,
            f"Expected 404 status code for non-existent option ID, got {response_vote.status_code}. Response: {response_vote.get_json()}",
        )

        # e. Assert that the response JSON contains an appropriate error message
        response_json = response_vote.get_json()
        self.assertIn("message", response_json)
        expected_message_fragment = (
            "Poll option not found"  # Based on PollVoteResource logic
        )
        actual_message = response_json["message"]
        self.assertIn(
            expected_message_fragment.lower(),
            actual_message.lower(),
            f"Error message '{actual_message}' does not contain expected fragment '{expected_message_fragment}'.",
        )

    def test_vote_on_poll_unauthenticated(self):
        pass

    def test_vote_on_poll_non_existent_poll(self):
        pass

    def test_get_poll_results_after_voting(self):
        # 1. User Tokens
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        token_user2 = self._get_jwt_token(self.user2.username, "password")
        token_user3 = self._get_jwt_token(self.user3.username, "password")

        # 2. Create Poll (User1 creates)
        poll_question = "What's the best testing strategy?"
        poll_options_texts = ["Strategy A", "Strategy B", "Strategy C"]
        poll_id = self._create_poll_via_api(
            token_user1, poll_question, poll_options_texts
        )
        self.assertIsNotNone(poll_id)

        # 3. Retrieve Poll Options to get their IDs
        headers_user1 = {"Authorization": f"Bearer {token_user1}"}
        response_get_poll = self.client.get(
            f"/api/polls/{poll_id}", headers=headers_user1
        )
        self.assertEqual(
            response_get_poll.status_code, 200, "Failed to retrieve created poll"
        )
        poll_data = response_get_poll.get_json()["poll"]

        options_map = {}  # Store text -> id
        for option in poll_data["options"]:
            options_map[option["text"]] = option["id"]

        self.assertIn("Strategy A", options_map)
        self.assertIn("Strategy B", options_map)
        self.assertIn("Strategy C", options_map)

        option_id_A = options_map["Strategy A"]
        option_id_B = options_map["Strategy B"]
        # option_id_C will be used implicitly by checking its vote count as 0

        # 4. Cast Votes
        # User1 votes for Strategy A
        headers_vote_user1 = {
            "Authorization": f"Bearer {token_user1}",
            "Content-Type": "application/json",
        }
        response_vote1 = self.client.post(
            f"/api/polls/{poll_id}/vote",
            headers=headers_vote_user1,
            json={"option_id": option_id_A},
        )
        self.assertEqual(
            response_vote1.status_code,
            201,
            f"User1 failed to vote for Strategy A. Response: {response_vote1.get_json()}",
        )

        # User2 votes for Strategy B
        headers_vote_user2 = {
            "Authorization": f"Bearer {token_user2}",
            "Content-Type": "application/json",
        }
        response_vote2 = self.client.post(
            f"/api/polls/{poll_id}/vote",
            headers=headers_vote_user2,
            json={"option_id": option_id_B},
        )
        self.assertEqual(
            response_vote2.status_code,
            201,
            f"User2 failed to vote for Strategy B. Response: {response_vote2.get_json()}",
        )

        # User3 votes for Strategy A
        headers_vote_user3 = {
            "Authorization": f"Bearer {token_user3}",
            "Content-Type": "application/json",
        }
        response_vote3 = self.client.post(
            f"/api/polls/{poll_id}/vote",
            headers=headers_vote_user3,
            json={"option_id": option_id_A},
        )
        self.assertEqual(
            response_vote3.status_code,
            201,
            f"User3 failed to vote for Strategy A. Response: {response_vote3.get_json()}",
        )

        # 5. Get Poll Results (User1 gets)
        response_get_results = self.client.get(
            f"/api/polls/{poll_id}", headers=headers_user1
        )

        # 6. Assert Results
        self.assertEqual(
            response_get_results.status_code,
            200,
            "Failed to get poll results after voting",
        )
        results_data = response_get_results.get_json()["poll"]

        self.assertEqual(results_data["id"], poll_id)
        self.assertEqual(results_data["question"], poll_question)
        self.assertEqual(len(results_data["options"]), 3)

        found_option_A = False
        found_option_B = False
        found_option_C = False

        for option in results_data["options"]:
            if option["text"] == "Strategy A":
                self.assertEqual(
                    option["vote_count"], 2, "Vote count for Strategy A is incorrect"
                )
                found_option_A = True
            elif option["text"] == "Strategy B":
                self.assertEqual(
                    option["vote_count"], 1, "Vote count for Strategy B is incorrect"
                )
                found_option_B = True
            elif option["text"] == "Strategy C":
                self.assertEqual(
                    option["vote_count"], 0, "Vote count for Strategy C is incorrect"
                )
                found_option_C = True

        self.assertTrue(found_option_A, "Strategy A not found in results")
        self.assertTrue(found_option_B, "Strategy B not found in results")
        self.assertTrue(found_option_C, "Strategy C not found in results")

    def test_view_poll_html_renders_vote_counts(self):
        """
        Tests that the HTML view for a poll correctly renders vote counts
        after the fix for accessing vote_count in the template.
        """
        # 1. Setup Users and Tokens
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        # User2 and User3 will vote via UI/form submission after login

        # 2. User1 creates a poll via API (simpler setup than UI for creation)
        poll_question = "HTML Render Test Poll"
        poll_options_texts = ["RenderOpt1", "RenderOpt2"]
        poll_id = self._create_poll_via_api(
            token_user1, poll_question, poll_options_texts
        )
        self.assertIsNotNone(poll_id)

        # Retrieve option IDs to use for voting
        headers_user1 = {"Authorization": f"Bearer {token_user1}"}
        response_get_poll = self.client.get(
            f"/api/polls/{poll_id}", headers=headers_user1
        )
        self.assertEqual(response_get_poll.status_code, 200)
        poll_data_api = response_get_poll.get_json()["poll"]
        option_id_1 = next(
            opt["id"]
            for opt in poll_data_api["options"]
            if opt["text"] == "RenderOpt1"
        )
        option_id_2 = next(
            opt["id"]
            for opt in poll_data_api["options"]
            if opt["text"] == "RenderOpt2"
        )

        # 3. Users vote on the poll (simulating form submissions)
        # User1 votes for RenderOpt1
        self.login(self.user1.username, "password") # Corrected: self.login
        self.client.post(
            f"/poll/{poll_id}/vote", data={"option_id": str(option_id_1)}
        )
        self._logout()

        # User2 votes for RenderOpt1
        self._login(self.user2.username, "password")
        self.client.post(
            f"/poll/{poll_id}/vote", data={"option_id": str(option_id_1)}
        )
        self._logout()

        # User3 votes for RenderOpt2
        self.user3 = self._create_user("testuser3", "password") # Ensure user3 exists
        self._login(self.user3.username, "password")
        self.client.post(
            f"/poll/{poll_id}/vote", data={"option_id": str(option_id_2)}
        )
        self.logout() # Corrected: self.logout

        # Expected counts: RenderOpt1: 2 votes, RenderOpt2: 1 vote

        # 4. Fetch the HTML page for the poll (as an anonymous user or logged-in user)
        self.login(self.user1.username, "password") # Corrected: self.login # Or view as anonymous
        response_html = self.client.get(f"/poll/{poll_id}")
        self.assertEqual(response_html.status_code, 200)
        html_content = response_html.data.decode()

        # 5. Assertions for rendered HTML content
        self.assertIn(poll_question, html_content)
        self.assertIn("RenderOpt1", html_content)
        self.assertIn("RenderOpt2", html_content)

        # Check for vote counts (e.g., "2 vote(s)", "1 vote(s)")
        # This is a basic check; more robust might involve parsing HTML structure
        self.assertIn("RenderOpt1", html_content)
        # Check that "2 vote(s)" appears after "RenderOpt1" for that option's display
        # A more robust way would be to use an HTML parser, but for this, string finding should be okay.
        # We expect something like: <li>RenderOpt1 ... <span ...>2 vote(s)</span></li>
        # This can be fragile. Let's check for the specific badge text.
        self.assertRegex(html_content, r"RenderOpt1.*?<span.*?badge.*?>\s*2\s*vote\(s\)\s*</span>", "Vote count for RenderOpt1 not rendered correctly or not found.")
        self.assertRegex(html_content, r"RenderOpt2.*?<span.*?badge.*?>\s*1\s*vote\(s\)\s*</span>", "Vote count for RenderOpt2 not rendered correctly or not found.")


        # Check progress bar percentages (approximate)
        # Opt1: 2/3 = 66.6%
        # Opt2: 1/3 = 33.3%
        # Example: style="width: 66.6...%;"
        # Using regex to find the style attribute for progress bars
        self.assertRegex(html_content, r"width:\s*66\.[67]%", "Progress bar for RenderOpt1 (2/3 votes) not rendered correctly.") # Allows for 66.6 or 66.7 due to formatting "%.1f"
        self.assertRegex(html_content, r"width:\s*33\.3%", "Progress bar for RenderOpt2 (1/3 votes) not rendered correctly.")


if __name__ == "__main__":
    unittest.main()
