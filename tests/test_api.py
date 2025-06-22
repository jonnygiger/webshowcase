import unittest
import json
from unittest.mock import patch

from app import app, db
from models import User, Post, Poll, PollOption, PostLock, ChatRoom, TrendingHashtag, UserBlock, SharedFile
from tests.test_base import AppTestCase # Assuming this sets up app context and db
from flask_jwt_extended import create_access_token
import os
from datetime import datetime, timedelta, timezone

class TestPollAPI(AppTestCase):

    def test_create_poll_api_invalid_options_too_few(self):
        with self.app.app_context():
            token = self._get_jwt_token(self.user1.username, "password")
            headers = {"Authorization": f"Bearer {token}"}

            response = self.client.post('/api/polls', headers=headers, json={
                "question": "Too few options?",
                "options": ["Option 1"] # Only one option
            })
            self.assertEqual(response.status_code, 400)
            data = response.get_json()
            self.assertIn("A poll must have at least two options", data["message"])

    def test_create_poll_api_invalid_options_empty_text(self):
        with self.app.app_context():
            token = self._get_jwt_token(self.user1.username, "password")
            headers = {"Authorization": f"Bearer {token}"}

            response = self.client.post('/api/polls', headers=headers, json={
                "question": "Empty option text?",
                "options": ["Option 1", "   "] # One valid, one empty
            })
            self.assertEqual(response.status_code, 400)
            data = response.get_json()
            self.assertIn("Poll option text cannot be blank", data["message"])

class TestEventAPI(AppTestCase): # Placeholder, actual tests depend on EventListResource implementation

    def test_get_event_list_api_placeholder(self):
        # This test assumes EventListResource is implemented and returns event data
        # For now, we'll just check if the endpoint exists and returns a successful status code
        # if the resource is more than a placeholder.
        # If it's a true placeholder, this test might need adjustment or will fail.
        with self.app.app_context():
            token = self._get_jwt_token(self.user1.username, "password") # Assuming auth is required
            headers = {"Authorization": f"Bearer {token}"}

            # Create some events for the list to pick up if implemented
            self._create_db_event(self.user1_id, title="Event Alpha")
            self._create_db_event(self.user2_id, title="Event Beta")

            response = self.client.get('/api/events', headers=headers)
            # Current placeholder returns 200 with a message.
            # If it were fully implemented, it would also return event data.
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn("message", data)
            # self.assertIn("events", data) # This would be for a full implementation

class TestTrendingHashtagsAPI(AppTestCase):

    @patch('recommendations.get_trending_hashtags') # Corrected mock path
    def test_get_trending_hashtags_api(self, mock_get_trending_hashtags):
        with self.app.app_context():
            # Configure the mock to return a predefined list of hashtags
            mock_hashtags_data = [
                TrendingHashtag(hashtag="#test1", score=10.0, rank=1),
                TrendingHashtag(hashtag="#test2", score=8.0, rank=2)
            ]
            # The actual get_trending_hashtags in recommendations.py returns model instances.
            # The API resource then calls to_dict() on them. So the mock should behave similarly.
            # Let's assume the resource directly uses the list of dicts from a helper.
            # For simplicity, if TrendingHashtagsResource directly calls get_trending_hashtags
            # and that function returns model objects, the resource will call to_dict().
            # If get_trending_hashtags itself returns dicts, then the mock should too.
            # Based on recommendations.py, get_trending_hashtags returns model instances.

            # We need to make sure the mock returns data that can be serialized by .to_dict()
            # or that the resource is robust to what mock_get_trending_hashtags returns.
            # The api.TrendingHashtagsResource is a placeholder.
            # For this test, let's assume it will eventually call .to_dict().

            # Let's mock the output of the *resource method* or the *function it calls*.
            # The current placeholder api.TrendingHashtagsResource doesn't call any function.
            # This test will need to be updated once the resource is implemented.
            # For now, we check the placeholder response.

            token = self._get_jwt_token(self.user1.username, "password") # Assuming auth might be added
            headers = {"Authorization": f"Bearer {token}"}
            response = self.client.get('/api/trending_hashtags', headers=headers)
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn("message", data) # Placeholder check
            # self.assertEqual(len(data["trending_hashtags"]), 2)
            # self.assertEqual(data["trending_hashtags"][0]["hashtag"], "#test1")
            # mock_get_trending_hashtags.assert_called_once() # Verify the mocked function was called


class TestPostLockAPI(AppTestCase):

    def test_lock_already_locked_post_by_another_user(self):
        with self.app.app_context():
            post_to_lock = self._create_db_post(user_id=self.user1_id, title="Shared Lock Post")

            # User1 locks the post
            token_user1 = self._get_jwt_token(self.user1.username, "password")
            headers_user1 = {"Authorization": f"Bearer {token_user1}"}
            response_user1_lock = self.client.post(f'/api/posts/{post_to_lock.id}/lock', headers=headers_user1)
            self.assertEqual(response_user1_lock.status_code, 200)

            # User2 attempts to lock the same post
            token_user2 = self._get_jwt_token(self.user2.username, "password")
            headers_user2 = {"Authorization": f"Bearer {token_user2}"}
            response_user2_lock_attempt = self.client.post(f'/api/posts/{post_to_lock.id}/lock', headers=headers_user2)

            self.assertEqual(response_user2_lock_attempt.status_code, 409) # Conflict
            data = response_user2_lock_attempt.get_json()
            self.assertIn("Post is currently locked by another user.", data["message"])
            self.assertEqual(data["locked_by_username"], self.user1.username)

class TestUserFeedAPI(AppTestCase):

    def test_get_user_feed_unauthorized(self):
        with self.app.app_context():
            # Attempt to access without a token
            response = self.client.get(f'/api/users/{self.user1_id}/feed')
            self.assertEqual(response.status_code, 401) # Expect Unauthorized

class TestChatRoomAPI(AppTestCase):

    def test_create_chat_room_duplicate_name(self):
        with self.app.app_context():
            token = self._get_jwt_token(self.user1.username, "password")
            headers = {"Authorization": f"Bearer {token}"}
            room_name = "Duplicate Room Test"

            # Create the first room
            response1 = self.client.post('/api/chat/rooms', headers=headers, json={"name": room_name})
            self.assertEqual(response1.status_code, 201)

            # Attempt to create another room with the same name
            response2 = self.client.post('/api/chat/rooms', headers=headers, json={"name": room_name})
            self.assertEqual(response2.status_code, 409) # Conflict
            data = response2.get_json()
            self.assertIn(f"Chat room with name '{room_name}' already exists.", data["message"])

class TestCommentAPI(AppTestCase):
    def test_post_comment_to_non_existent_post(self):
        with self.app.app_context():
            token = self._get_jwt_token(self.user1.username, "password")
            headers = {"Authorization": f"Bearer {token}"}
            non_existent_post_id = 99999

            response = self.client.post(f'/api/posts/{non_existent_post_id}/comments', headers=headers, json={
                "content": "A comment for a ghost post."
            })
            self.assertEqual(response.status_code, 404)
            data = response.get_json()
            self.assertIn("Post not found", data["message"])

    def test_post_comment_when_blocked_by_author(self):
        with self.app.app_context():
            post_author = self.user1
            commenter = self.user2

            # Post author (user1) blocks commenter (user2)
            self._create_db_block(blocker_user_obj=post_author, blocked_user_obj=commenter)

            # Post by user1
            post_by_author = self._create_db_post(user_id=post_author.id, title="Blocker's Post")

            # Commenter (user2) attempts to comment - should be blocked
            token_commenter = self._get_jwt_token(commenter.username, "password")
            headers_commenter = {"Authorization": f"Bearer {token_commenter}"}

            response = self.client.post(f'/api/posts/{post_by_author.id}/comments', headers=headers_commenter, json={
                "content": "Trying to comment while blocked."
            })

            self.assertEqual(response.status_code, 403)
            data = response.get_json()
            self.assertIn("You are blocked by the post author and cannot comment.", data["message"])

class TestSharedFileAPI(AppTestCase):

    def setUp(self):
        super().setUp() # Call AppTestCase.setUp
        # Ensure the test shared files folder exists
        shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
        if not os.path.exists(shared_folder):
            os.makedirs(shared_folder)

    def tearDown(self):
        # Clean up any created files in the test shared folder
        shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
        if os.path.exists(shared_folder):
            for filename in os.listdir(shared_folder):
                file_path = os.path.join(shared_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path} during teardown. Reason: {e}")
        super().tearDown()


    def _create_db_shared_file_for_api_test(self, sender, receiver, original_filename="test_file.txt", saved_filename="saved_test_file.txt"):
        # Create a dummy file on disk for deletion test
        upload_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
        dummy_file_path = os.path.join(upload_folder, saved_filename)
        with open(dummy_file_path, "w") as f:
            f.write("dummy content")

        shared_file = SharedFile(
            sender_id=sender.id,
            receiver_id=receiver.id,
            original_filename=original_filename,
            saved_filename=saved_filename # This is crucial
        )
        db.session.add(shared_file)
        db.session.commit()
        return shared_file

    def test_delete_shared_file_unauthorized_user(self):
        with self.app.app_context():
            sender = self.user1
            receiver = self.user2
            unauthorized_user = self.user3 # Neither sender nor receiver

            shared_file = self._create_db_shared_file_for_api_test(sender=sender, receiver=receiver)

            token_unauthorized = self._get_jwt_token(unauthorized_user.username, "password")
            headers_unauthorized = {"Authorization": f"Bearer {token_unauthorized}"}

            response = self.client.delete(f'/api/files/{shared_file.id}', headers=headers_unauthorized)

            self.assertEqual(response.status_code, 403)
            data = response.get_json()
            self.assertIn("You are not authorized to delete this file", data["message"])

            # Ensure file still exists in DB and on disk
            self.assertIsNotNone(db.session.get(SharedFile, shared_file.id))
            upload_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
            self.assertTrue(os.path.exists(os.path.join(upload_folder, shared_file.saved_filename)))


    def test_delete_non_existent_shared_file_record(self):
        with self.app.app_context():
            token = self._get_jwt_token(self.user1.username, "password")
            headers = {"Authorization": f"Bearer {token}"}
            non_existent_file_id = 99999

            response = self.client.delete(f'/api/files/{non_existent_file_id}', headers=headers)

            self.assertEqual(response.status_code, 404)
            data = response.get_json()
            self.assertIn("File not found", data["message"])

if __name__ == "__main__":
    unittest.main()
