import unittest
import json
from flask import url_for
from tests.test_base import AppTestCase
from social_app import db
from social_app.models.db_models import (
    User,
    Post,
    Poll,
    PollOption,
    PostLock,
    SharedFile,
    ChatRoom,
    UserActivity,
    Friendship,
)
from datetime import datetime, timezone, timedelta
import os


class TestApiEdgeCases(AppTestCase):

    def test_vote_on_poll_with_invalid_option_id(self):
        with self.app.app_context():
            poll_creator = self.user1
            voter = self.user2

            poll_obj_initial = self._create_db_poll(
                user_id=poll_creator.id,
                question="Valid Poll?",
                options_texts=["Opt A", "Opt B"],
            )
            poll_obj = db.session.get(Poll, poll_obj_initial.id)
            self.assertIsNotNone(
                poll_obj, "Poll object could not be re-fetched from DB."
            )
            self.assertGreater(
                len(poll_obj.options),
                0,
                "Poll was not created with options for the test.",
            )

            token_voter = self._get_jwt_token(voter.username, "password")
            headers_voter = {"Authorization": f"Bearer {token_voter}"}

            invalid_option_id = 99999

            response = self.client.post(
                f"/api/polls/{poll_obj.id}/vote",
                headers=headers_voter,
                json={"option_id": invalid_option_id},
            )

            self.assertEqual(response.status_code, 404)
            data = response.get_json()
            self.assertIn(
                "Poll option not found or does not belong to this poll", data["message"]
            )

    def test_lock_post_already_locked_by_same_user(self):
        with self.app.app_context():
            post_owner = self.user1
            post_to_lock = self._create_db_post(
                user_id=post_owner.id, title="Self-Lock Post"
            )

            token_owner = self._get_jwt_token(post_owner.username, "password")
            headers_owner = {"Authorization": f"Bearer {token_owner}"}

            response_lock1 = self.client.post(
                f"/api/posts/{post_to_lock.id}/lock", headers=headers_owner
            )
            self.assertEqual(response_lock1.status_code, 200)
            lock1_expires_at_str = response_lock1.get_json()["lock_details"][
                "expires_at"
            ]
            lock1_expires_at = datetime.fromisoformat(
                lock1_expires_at_str.replace("Z", "+00:00")
            )

            response_lock2 = self.client.post(
                f"/api/posts/{post_to_lock.id}/lock", headers=headers_owner
            )
            self.assertEqual(response_lock2.status_code, 200)
            data_lock2 = response_lock2.get_json()
            self.assertIn("Post locked successfully", data_lock2["message"])
            lock2_expires_at_str = data_lock2["lock_details"]["expires_at"]
            lock2_expires_at = datetime.fromisoformat(
                lock2_expires_at_str.replace("Z", "+00:00")
            )

            self.assertTrue(lock2_expires_at > lock1_expires_at)
            self.assertTrue(
                lock2_expires_at > datetime.now(timezone.utc) + timedelta(minutes=14)
            )

    def test_delete_shared_file_by_sender(self):
        with self.app.app_context():
            sender = self.user1
            receiver = self.user2

            dummy_saved_filename = (
                f"sender_delete_test_{datetime.now(timezone.utc).timestamp()}.txt"
            )

            shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
            if not os.path.exists(shared_folder):
                os.makedirs(shared_folder)

            dummy_file_path = os.path.join(shared_folder, dummy_saved_filename)
            with open(dummy_file_path, "w") as f:
                f.write("dummy content for sender deletion test")

            shared_file = SharedFile(
                sender_id=sender.id,
                receiver_id=receiver.id,
                original_filename="original_by_sender.txt",
                saved_filename=dummy_saved_filename,
            )
            db.session.add(shared_file)
            db.session.commit()
            shared_file_id = shared_file.id

            token_sender = self._get_jwt_token(sender.username, "password")
            headers_sender = {"Authorization": f"Bearer {token_sender}"}

            response = self.client.delete(
                f"/api/files/{shared_file_id}", headers=headers_sender
            )

            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn("File deleted successfully", data["message"])

            self.assertIsNone(db.session.get(SharedFile, shared_file_id))
            self.assertFalse(os.path.exists(dummy_file_path))

            if os.path.exists(dummy_file_path):
                os.remove(dummy_file_path)

    def test_create_chat_room_with_empty_name_api(self):
        with self.app.app_context():
            token = self._get_jwt_token(self.user1.username, "password")
            headers = {"Authorization": f"Bearer {token}"}

            response = self.client.post(
                "/api/chat/rooms", headers=headers, json={"name": "   "}
            )
            self.assertEqual(response.status_code, 400)
            data = response.get_json()
            self.assertIn("Chat room name cannot be empty.", data["message"])

    def test_get_user_feed_for_isolated_user(self):
        with self.app.app_context():
            isolated_user = self._create_db_user(username="isolated_user_feed_test")

            token_isolated = self._get_jwt_token(isolated_user.username, "password")
            headers_isolated = {"Authorization": f"Bearer {token_isolated}"}

            response = self.client.get(
                f"/api/users/{isolated_user.id}/feed", headers=headers_isolated
            )

            self.assertEqual(response.status_code, 200)
            data = response.get_json()

            self.assertIn("feed_posts", data)
            self.assertEqual(len(data["feed_posts"]), 0)


if __name__ == "__main__":
    unittest.main()
