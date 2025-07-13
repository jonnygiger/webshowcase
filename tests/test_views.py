import unittest
import os
from flask import session, get_flashed_messages, url_for
from social_app import create_app, db
from social_app.models.db_models import (
    User,
    Post,
    Friendship,
    FlaggedContent,
    SharedFile,
    Series,
    UserBlock,
)
from tests.test_base import AppTestCase
from werkzeug.security import generate_password_hash


class TestViewRoutes(AppTestCase):

    def test_user_profile_friendship_status_display(self):
        with self.app.app_context():
            user_a = self._create_db_user(
                "viewer_a", "password_a", "viewer_a@example.com"
            )
            user_b = self._create_db_user(
                "profile_owner_b", "password_b", "profile_b@example.com"
            )

            self.login("viewer_a", "password_a")
            response = self.client.get(
                url_for("core.user_profile", username=user_b.username)
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("Send Friend Request", response.data.decode())
            self.logout()

            self._create_db_friendship(user_a, user_b, "pending")
            self.login("viewer_a", "password_a")
            response = self.client.get(
                url_for("core.user_profile", username=user_b.username)
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("Friend request pending", response.data.decode())
            self.logout()
            self._remove_db_friendship(user_a, user_b)

            fs_b_to_a = self._create_db_friendship(user_b, user_a, "pending")
            self.login("viewer_a", "password_a")
            response = self.client.get(
                url_for("core.user_profile", username=user_b.username)
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("Accept Friend Request", response.data.decode())
            self.assertIn(
                url_for("core.accept_friend_request", request_id=fs_b_to_a.id),
                response.data.decode(),
            )
            self.logout()
            self._remove_db_friendship(user_b, user_a)

            self._create_db_friendship(user_a, user_b, "accepted")
            self.login("viewer_a", "password_a")
            response = self.client.get(
                url_for("core.user_profile", username=user_b.username)
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("Friends", response.data.decode())
            self.assertIn(
                url_for("core.remove_friend", friend_user_id=user_b.id),
                response.data.decode(),
            )
            self.logout()
            self._remove_db_friendship(user_a, user_b)

            self.login("viewer_a", "password_a")
            response = self.client.get(
                url_for("core.user_profile", username=user_a.username)
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("Edit Profile", response.data.decode())
            self.assertNotIn("Send Friend Request", response.data.decode())
            self.logout()

    def test_moderation_dashboard_access(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            response = self.client.get(
                url_for("core.moderation_dashboard"), follow_redirects=False
            )
            self.assertEqual(response.status_code, 302)
            self.assertIn(url_for("core.login"), response.location)
            self.logout()

            moderator = self._create_db_user(
                "mod_user", "modpass", "mod@example.com", role="moderator"
            )
            self.login(moderator.username, "modpass")
            response = self.client.get(url_for("core.moderation_dashboard"))
            self.assertEqual(response.status_code, 200)
            self.assertIn("Moderation Dashboard", response.data.decode())
            self.logout()

    def test_remove_friend_functionality(self):
        with self.app.app_context():
            user_x = self._create_db_user("user_x_remove", "passx", "x@example.com")
            user_y = self._create_db_user("user_y_remove", "passy", "y@example.com")
            self._create_db_friendship(user_x, user_y, "accepted")
            self._create_db_friendship(user_y, user_x, "accepted")

            self.login(user_x.username, "passx")
            self.assertIn(user_y, user_x.get_friends())

            response = self.client.post(
                url_for("core.remove_friend", friend_user_id=user_y.id),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(
                f"You are no longer friends with {user_y.username}.",
                response.data.decode(),
            )

            fs_check = Friendship.query.filter_by(
                user_id=user_x.id, friend_id=user_y.id, status="accepted"
            ).first()
            fs_check_reverse = Friendship.query.filter_by(
                user_id=user_y.id, friend_id=user_x.id, status="accepted"
            ).first()
            self.assertIsNone(fs_check)
            self.assertIsNone(fs_check_reverse)

            db.session.refresh(user_x)
            db.session.refresh(user_y)
            self.assertNotIn(user_y, user_x.get_friends())
            self.assertNotIn(user_x, user_y.get_friends())
            self.logout()

    def test_file_sharing_download_authorization(self):
        with self.app.app_context():
            sender = self._create_db_user(
                "file_sender", "pass_send", "sender@example.com"
            )
            receiver = self._create_db_user(
                "file_receiver", "pass_receive", "receiver@example.com"
            )
            other_user = self._create_db_user(
                "file_other", "pass_other", "other@example.com"
            )

            saved_filename_on_disk = "uuid_test_auth_file.txt"
            shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
            if not os.path.exists(shared_folder):
                os.makedirs(shared_folder)
            dummy_file_path = os.path.join(shared_folder, saved_filename_on_disk)
            with open(dummy_file_path, "w") as f:
                f.write("dummy content for download test")

            shared_file = SharedFile(
                sender_id=sender.id,
                receiver_id=receiver.id,
                original_filename="test_auth_file.txt",
                saved_filename=saved_filename_on_disk,
            )
            db.session.add(shared_file)
            db.session.commit()

            self.login(receiver.username, "pass_receive")
            response_receiver = self.client.get(
                url_for("core.download_shared_file", shared_file_id=shared_file.id)
            )
            self.assertEqual(response_receiver.status_code, 200)
            self.assertIn(
                "attachment; filename=test_auth_file.txt",
                response_receiver.headers.get("Content-Disposition", ""),
            )
            self.logout()

            self.login(sender.username, "pass_send")
            response_sender = self.client.get(
                url_for("core.download_shared_file", shared_file_id=shared_file.id)
            )
            self.assertEqual(response_sender.status_code, 200)
            self.assertIn(
                "attachment; filename=test_auth_file.txt",
                response_sender.headers.get("Content-Disposition", ""),
            )
            self.logout()

            self.login(other_user.username, "pass_other")
            response_other = self.client.get(
                url_for("core.download_shared_file", shared_file_id=shared_file.id),
                follow_redirects=False,
            )
            self.assertEqual(response_other.status_code, 302)

            response_other_redirected = self.client.get(response_other.location)
            self.assertEqual(response_other_redirected.status_code, 200)
            self.assertIn(
                "You are not authorized to download this file.",
                response_other_redirected.data.decode(),
            )
            self.logout()

            if os.path.exists(dummy_file_path):
                os.remove(dummy_file_path)

    def test_edit_series_add_post_not_owned_by_series_author(self):
        with self.app.app_context():
            series_author = self._create_db_user(
                "series_owner_auth", "pass_so", "so@example.com"
            )
            post_author_other = self._create_db_user(
                "post_owner_other", "pass_po", "po@example.com"
            )

            temp_series_obj = self._create_db_series(
                user_id=series_author.id, title="Owner Auth Series"
            )
            series_id = temp_series_obj.id

            temp_post_obj = self._create_db_post(
                user_id=post_author_other.id, title="Other Author Post"
            )
            post_id = temp_post_obj.id

            self.login(series_author.username, "pass_so")
            response = self.client.post(
                url_for(
                    "core.add_post_to_series", series_id=series_id, post_id=post_id
                ),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(
                "You can only add your own posts to your series.",
                response.data.decode(),
            )

            series_in_current_session = db.session.get(Series, series_id)
            self.assertIsNotNone(series_in_current_session)
            self.assertEqual(len(series_in_current_session.posts), 0)
            self.logout()

    def test_user_blocking_effects_on_profile_and_posts(self):
        with self.app.app_context():
            blocker_user = self._create_db_user(
                "blocker_profile", "pass_blocker", "blocker_p@example.com"
            )
            blocked_user = self._create_db_user(
                "blocked_profile", "pass_blocked", "blocked_p@example.com"
            )

            post_by_blocker = self._create_db_post(
                user_id=blocker_user.id, title="Blocker's Public Post"
            )
            self._create_db_block(blocker_user, blocked_user)
            self.login(blocked_user.username, "pass_blocked")

            response_profile = self.client.get(
                url_for("core.user_profile", username=blocker_user.username)
            )
            self.assertEqual(response_profile.status_code, 200)
            self.assertNotIn(post_by_blocker.title, response_profile.data.decode())

            response_post_direct = self.client.get(
                url_for("core.view_post", post_id=post_by_blocker.id)
            )
            self.assertEqual(response_post_direct.status_code, 200)

            response_blog = self.client.get(url_for("core.blog"))
            self.assertEqual(response_blog.status_code, 200)
            self.assertIn(post_by_blocker.title, response_blog.data.decode())
            self.logout()


if __name__ == "__main__":
    unittest.main()
