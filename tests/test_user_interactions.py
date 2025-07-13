import unittest
from flask import url_for
from tests.test_base import AppTestCase
from social_app import db
from social_app.models.db_models import (
    User,
    Post,
    Comment,
    UserBlock,
    Friendship,
)
import os


class TestUserInteractions(AppTestCase):

    def test_block_user_and_profile_visibility(self):
        with self.app.app_context():
            blocker = self.user1
            blocked_user = self.user2

            post_by_blocked_user = self._create_db_post(
                user_id=blocked_user.id, title="Blocked User's Post"
            )

            self.login(blocker.username, "password")

            response_block = self.client.post(
                url_for(
                    "core.block_user_route", username_to_block=blocked_user.username
                ),
                follow_redirects=True,
            )
            self.assertEqual(response_block.status_code, 200)
            self.assertIn(
                f"You have blocked {blocked_user.username}".encode("utf-8"),
                response_block.data,
            )

            block_instance = UserBlock.query.filter_by(
                blocker_id=blocker.id, blocked_id=blocked_user.id
            ).first()
            self.assertIsNotNone(block_instance)

            self.assertNotIn(b"Blocked User's Post", response_block.data)
            self.assertIn(
                b"You have blocked this user or this user has blocked you.",
                response_block.data,
            )

            self.logout()

    def test_unblock_user(self):
        with self.app.app_context():
            blocker = self.user1
            blocked_user = self.user2

            block_id = self._create_db_block(
                blocker_user_obj=blocker, blocked_user_obj=blocked_user
            )

            block_instance_check = db.session.get(UserBlock, block_id)
            self.assertIsNotNone(block_instance_check)

            self.login(blocker.username, "password")

            response = self.client.post(
                url_for("core.unblock_user", username_to_unblock=blocked_user.username),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)

            self.assertIsNone(db.session.get(UserBlock, block_id))
            self.assertIn(
                f"You have unblocked {blocked_user.username}.".encode("utf-8"),
                response.data,
            )

            post_by_unblocked_user = self._create_db_post(
                user_id=blocked_user.id, title="Unblocked User's Post"
            )
            response = self.client.get(
                url_for("core.user_profile", username=blocked_user.username)
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Unblocked User&#39;s Post", response.data)
            self.assertNotIn(b"You have blocked this user", response.data)

            self.logout()

    def test_blocked_user_cannot_send_friend_request_to_blocker(self):
        with self.app.app_context():
            blocker = self.user1
            blocked_user = self.user2

            self._create_db_block(
                blocker_user_obj=blocker, blocked_user_obj=blocked_user
            )

            self.login(blocked_user.username, "password")

            response = self.client.post(
                url_for("core.send_friend_request", target_user_id=blocker.id)
            )
            self.assertEqual(response.status_code, 302)
            with self.client.session_transaction() as sess:
                flashes = sess.get("_flashes", [])
            self.assertTrue(
                any(
                    "You cannot send a friend request to this user as they have blocked you or you have blocked them."
                    in message[1]
                    for message in flashes
                )
            )

            friendship = Friendship.query.filter_by(
                user_id=blocked_user.id, friend_id=blocker.id
            ).first()
            self.assertIsNone(friendship)
            friendship_reverse = Friendship.query.filter_by(
                user_id=blocker.id, friend_id=blocked_user.id
            ).first()
            self.assertIsNone(friendship_reverse)

            self.logout()

    def test_user_cannot_send_friend_request_to_user_who_blocked_them(self):
        with self.app.app_context():
            blocker = self.user1
            requester = self.user2

            self._create_db_block(blocker_user_obj=blocker, blocked_user_obj=requester)

            self.login(requester.username, "password")

            response = self.client.post(
                url_for("core.send_friend_request", target_user_id=blocker.id)
            )
            self.assertEqual(response.status_code, 302)
            with self.client.session_transaction() as sess:
                flashes = sess.get("_flashes", [])
            self.assertTrue(
                any(
                    "You cannot send a friend request to this user as they have blocked you or you have blocked them."
                    in message[1]
                    for message in flashes
                )
            )

            friendship = Friendship.query.filter_by(
                user_id=requester.id, friend_id=blocker.id
            ).first()
            self.assertIsNone(friendship)

            self.logout()

    def test_profile_picture_update_reflects_on_profile_page(self):
        with self.app.app_context():
            user_to_update = db.session.get(User, self.user1.id)
            self.login(user_to_update.username, "password")

            new_pic_filename = "new_test_profile.png"
            new_pic_url = url_for(
                "static", filename=f"profile_pics/{new_pic_filename}", _external=False
            )

            user_to_update.profile_picture = new_pic_url
            db.session.commit()

            fetched_user_for_debug = db.session.get(User, user_to_update.id)
            self.assertEqual(fetched_user_for_debug.profile_picture, new_pic_url)

            static_profile_pics_path = self.app.config["PROFILE_PICS_FOLDER"]
            if not os.path.exists(static_profile_pics_path):
                os.makedirs(static_profile_pics_path)
            dummy_file_path = os.path.join(static_profile_pics_path, new_pic_filename)
            with open(dummy_file_path, "w") as f:
                f.write("dummy image data")

            response = self.client.get(
                url_for("core.user_profile", username=user_to_update.username)
            )
            self.assertEqual(response.status_code, 200)

            self.assertIn(bytes(new_pic_url, "utf-8"), response.data)

            if os.path.exists(dummy_file_path):
                os.remove(dummy_file_path)

            self.logout()

    def test_edit_user_bio_and_verify_update(self):
        with self.app.app_context():
            user_to_edit = self.user1
            self.login(user_to_edit.username, "password")

            new_bio_text = "This is my new awesome bio!"
            response = self.client.post(
                url_for("core.edit_profile"),
                data={
                    "username": user_to_edit.username,
                    "email": user_to_edit.email,
                    "bio": new_bio_text,
                },
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(bytes(new_bio_text, "utf-8"), response.data)

            updated_user = db.session.get(User, user_to_edit.id)
            self.assertEqual(updated_user.bio, new_bio_text)

            self.logout()


if __name__ == "__main__":
    unittest.main()
