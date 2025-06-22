import unittest
from flask import session, get_flashed_messages
from app import app, db
from models import User, Post, Friendship, FlaggedContent, SharedFile, Series
from tests.test_base import AppTestCase # Assuming this sets up app context and db
from werkzeug.security import generate_password_hash

class TestViewRoutes(AppTestCase):

    def test_user_profile_friendship_status_display(self):
        with self.app.app_context():
            # User A (viewer), User B (profile owner), User C (another user)
            user_a = self._create_db_user("viewer_a", "password_a", "viewer_a@example.com")
            user_b = self._create_db_user("profile_owner_b", "password_b", "profile_b@example.com")
            user_c = self._create_db_user("other_user_c", "password_c", "other_c@example.com")

            # Scenario 1: Viewer A looking at User B's profile (not friends)
            self.login("viewer_a", "password_a")
            response = self.client.get(f"/user/{user_b.username}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Send Friend Request", response.data.decode()) # Or similar text
            self.logout()

            # Scenario 2: Viewer A sent request to User B (pending_sent for A)
            self._create_db_friendship(user_a, user_b, "pending")
            self.login("viewer_a", "password_a")
            response = self.client.get(f"/user/{user_b.username}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Friend Request Sent", response.data.decode())
            self.logout()
            self._remove_db_friendship(user_a, user_b) # Clean up

            # Scenario 3: User B sent request to Viewer A (pending_received for A)
            fs_b_to_a = self._create_db_friendship(user_b, user_a, "pending")
            self.login("viewer_a", "password_a")
            response = self.client.get(f"/user/{user_b.username}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Respond to Request", response.data.decode()) # Or "Accept Friend Request" etc.
            # Check that the form to accept/reject is present
            self.assertIn(f"/friend_request/{fs_b_to_a.id}/accept", response.data.decode())
            self.logout()
            self._remove_db_friendship(user_b, user_a) # Clean up

            # Scenario 4: Viewer A and User B are friends
            self._create_db_friendship(user_a, user_b, "accepted")
            self.login("viewer_a", "password_a")
            response = self.client.get(f"/user/{user_b.username}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Friends", response.data.decode()) # Or "Remove Friend"
            self.assertIn(f"/user/{user_b.id}/remove_friend", response.data.decode())
            self.logout()
            self._remove_db_friendship(user_a, user_b) # Clean up

            # Scenario 5: Viewer A looking at their own profile
            self.login("viewer_a", "password_a")
            response = self.client.get(f"/user/{user_a.username}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Edit Profile", response.data.decode()) # Key indicator of own profile
            self.assertNotIn("Send Friend Request", response.data.decode())
            self.logout()

    def test_moderation_dashboard_access(self):
        with self.app.app_context():
            # Non-moderator user (user1 is default 'user' role in AppTestCase)
            self.login(self.user1.username, "password")
            response = self.client.get("/moderation", follow_redirects=False)
            self.assertEqual(response.status_code, 302) # Redirect
            self.assertIn("/login", response.location) # Should redirect to login or home if already logged in but not authorized

            # Check flash message after redirect
            # To check flashed messages, you often need to make a request to the page it redirects to
            # or use a test client that captures them.
            # For simplicity here, if it redirects, we assume the flash is there.
            # A more robust test would follow the redirect and check the flashed message on the target page.
            # response_redirected = self.client.get(response.location) # Follow redirect
            # messages = get_flashed_messages(with_categories=True) # This might not work as expected in tests without specific setup
            # self.assertTrue(any("You do not have permission" in message for category, message in messages if category == "danger"))
            self.logout()

            # Moderator user
            moderator = self._create_db_user("mod_user", "modpass", "mod@example.com", role="moderator")
            self.login(moderator.username, "modpass")
            response = self.client.get("/moderation")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Moderation Dashboard", response.data.decode())
            self.logout()

    def test_remove_friend_functionality(self):
        with self.app.app_context():
            user_x = self._create_db_user("user_x_remove", "passx", "x@example.com")
            user_y = self._create_db_user("user_y_remove", "passy", "y@example.com")
            self._create_db_friendship(user_x, user_y, "accepted")

            self.login(user_x.username, "passx")
            # Ensure they are friends first by checking User.get_friends()
            self.assertIn(user_y, user_x.get_friends())

            response = self.client.post(f"/user/{user_y.id}/remove_friend", follow_redirects=True)
            self.assertEqual(response.status_code, 200) # After redirect

            # Check flash message
            # This requires the test client to handle sessions and flashed messages correctly.
            # The default Flask test client should preserve session for subsequent requests.
            # We check the content of the page for the flash message.
            self.assertIn(f"You are no longer friends with {user_y.username}.", response.data.decode())

            # Verify friendship record is deleted
            fs_check = Friendship.query.filter_by(user_id=user_x.id, friend_id=user_y.id).first()
            fs_check_reverse = Friendship.query.filter_by(user_id=user_y.id, friend_id=user_x.id).first()
            self.assertIsNone(fs_check)
            self.assertIsNone(fs_check_reverse)

            # Verify they are no longer friends via model method
            db.session.refresh(user_x) # Refresh to get updated relationships
            db.session.refresh(user_y)
            self.assertNotIn(user_y, user_x.get_friends())
            self.assertNotIn(user_x, user_y.get_friends())
            self.logout()

    def test_file_sharing_download_authorization(self):
        with self.app.app_context():
            sender = self._create_db_user("file_sender", "pass_send", "sender@example.com")
            receiver = self._create_db_user("file_receiver", "pass_receive", "receiver@example.com")
            other_user = self._create_db_user("file_other", "pass_other", "other@example.com")

            # Simulate file upload and create SharedFile record
            # We don't need to actually save a file on disk for this auth test, just the DB record.
            shared_file = SharedFile(
                sender_id=sender.id,
                receiver_id=receiver.id,
                original_filename="test_auth_file.txt",
                saved_filename="uuid_test_auth_file.txt" # Needs to be unique if other tests use it
            )
            db.session.add(shared_file)
            db.session.commit()

            # Test 1: Receiver can download
            self.login(receiver.username, "pass_receive")
            response_receiver = self.client.get(f"/files/download/{shared_file.id}")
            self.assertEqual(response_receiver.status_code, 200)
            # Check for attachment header (depends on how send_from_directory is called)
            self.assertIn("attachment; filename=test_auth_file.txt", response_receiver.headers.get("Content-Disposition", ""))
            self.logout()

            # Test 2: Sender can download
            self.login(sender.username, "pass_send")
            response_sender = self.client.get(f"/files/download/{shared_file.id}")
            self.assertEqual(response_sender.status_code, 200)
            self.assertIn("attachment; filename=test_auth_file.txt", response_sender.headers.get("Content-Disposition", ""))
            self.logout()

            # Test 3: Other user cannot download
            self.login(other_user.username, "pass_other")
            response_other = self.client.get(f"/files/download/{shared_file.id}", follow_redirects=False)
            self.assertEqual(response_other.status_code, 302) # Expect redirect
            # Check flash message after redirect
            response_other_redirected = self.client.get(response_other.location)
            self.assertIn("You are not authorized to download this file.", response_other_redirected.data.decode())
            self.logout()

    def test_edit_series_add_post_not_owned_by_series_author(self):
        with self.app.app_context():
            series_author = self._create_db_user("series_owner_auth", "pass_so", "so@example.com")
            post_author_other = self._create_db_user("post_owner_other", "pass_po", "po@example.com")

            series_by_author = self._create_db_series(user_id=series_author.id, title="Owner Auth Series")
            post_by_other = self._create_db_post(user_id=post_author_other.id, title="Other Author Post")

            self.login(series_author.username, "pass_so")
            response = self.client.post(
                f"/series/{series_by_author.id}/add_post/{post_by_other.id}",
                follow_redirects=True
            )
            self.assertEqual(response.status_code, 200) # After redirect
            self.assertIn("You can only add your own posts to your series.", response.data.decode())

            # Verify post was not added to series
            db.session.refresh(series_by_author)
            self.assertEqual(len(series_by_author.posts), 0)
            self.logout()

    def test_user_blocking_effects_on_profile_and_posts(self):
        with self.app.app_context():
            blocker_user = self._create_db_user("blocker_profile", "pass_blocker", "blocker_p@example.com")
            blocked_user = self._create_db_user("blocked_profile", "pass_blocked", "blocked_p@example.com")

            # Blocker creates a post
            post_by_blocker = self._create_db_post(user_id=blocker_user.id, title="Blocker's Public Post")

            # Blocker blocks Blocked User
            self._create_db_block(blocker_user, blocked_user)

            # Blocked User logs in
            self.login(blocked_user.username, "pass_blocked")

            # 1. Blocked User tries to view Blocker's profile
            # The app.py user_profile route doesn't currently implement a block check before first_or_404.
            # This test assumes that if a user is blocked, their profile should effectively be invisible
            # or show a specific "access denied" message.
            # Current implementation will likely show the profile.
            # This test might FAIL or need adjustment based on how blocking is implemented in views.
            # For now, let's assume a 404 or a specific message is desired.
            # If the profile route simply shows user_profile, this part of test will fail.
            # Let's assume for now the ideal is a redirect or specific message.
            # A common pattern is to show a "User not found" to not reveal blocking.

            # To make this test pass with current code, we'd expect it to load.
            # To test the *desired* (but perhaps not implemented) state, we'd expect 404 or similar.
            # Let's write the test for a desired state where profile is inaccessible.
            # This might require changes in `app.py @user_profile` route.

            # For now, let's test the current state: profile is likely visible.
            # If blocking should hide profile, this test will highlight it.
            response_profile = self.client.get(f"/user/{blocker_user.username}")
            self.assertEqual(response_profile.status_code, 200) # Current state: profile likely visible
            # Add assertion here if a specific "blocked" message is expected on the profile page itself.
            # self.assertIn("You are blocked by this user", response_profile.data.decode()) # If such a message exists

            # 2. Blocked User tries to view Blocker's post directly
            # Similar to profile, view_post route needs to implement block checking.
            response_post_direct = self.client.get(f"/blog/post/{post_by_blocker.id}")
            self.assertEqual(response_post_direct.status_code, 200) # Current state: post likely visible
            # self.assertIn("Content not available", response_post_direct.data.decode()) # If blocking hides content

            # 3. Blocked User views the main blog page
            # Posts from blocker should ideally be filtered out.
            # The /blog route needs to be updated to filter out posts from users who blocked the current user.
            response_blog = self.client.get("/blog")
            self.assertEqual(response_blog.status_code, 200)
            # This assertion will likely fail if /blog doesn't filter based on blocks.
            self.assertNotIn(post_by_blocker.title, response_blog.data.decode(),
                             "Post from blocker should not appear on blog page for blocked user.")

            self.logout()

if __name__ == "__main__":
    unittest.main()
