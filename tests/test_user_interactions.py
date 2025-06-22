import unittest
from flask import url_for
from tests.test_base import AppTestCase
from models import db, User, Post, Comment, UserBlock, Friendship # Assuming UserBlock and Friendship are in models
import os # Import the os module

class TestUserInteractions(AppTestCase):

    def test_block_user_and_profile_visibility(self):
        with self.app.app_context():
            blocker = self.user1
            blocked_user = self.user2

            # Blocked user creates a post
            post_by_blocked_user = self._create_db_post(user_id=blocked_user.id, title="Blocked User's Post")

            # Blocker logs in
            self.login(blocker.username, "password")

            # Blocker blocks the user via the new route
            response_block = self.client.post(url_for('block_user_route', username_to_block=blocked_user.username), follow_redirects=True)
            self.assertEqual(response_block.status_code, 200) # block_user_route redirects to profile
            self.assertIn(f"You have blocked {blocked_user.username}".encode('utf-8'), response_block.data)

            # Verify block in DB
            block_instance = UserBlock.query.filter_by(blocker_id=blocker.id, blocked_id=blocked_user.id).first()
            self.assertIsNotNone(block_instance)

            # Blocker views blocked user's profile (already on it due to redirect)
            # response = self.client.get(url_for('user_profile', username=blocked_user.username))
            # self.assertEqual(response.status_code, 200)

            # Check content of the redirected page (response_block.data)
            self.assertNotIn(b"Blocked User's Post", response_block.data) # Posts should be hidden
            self.assertIn(b"You have blocked this user or this user has blocked you.", response_block.data)

            self.logout()

    def test_unblock_user(self):
        with self.app.app_context():
            blocker = self.user1
            blocked_user = self.user2

            # Blocker blocks the user initially
            # _create_db_block now returns the ID of the created block
            block_id = self._create_db_block(blocker_user_obj=blocker, blocked_user_obj=blocked_user)

            # Verify it was created by fetching it using the ID in the current session context
            block_instance_check = UserBlock.query.get(block_id)
            self.assertIsNotNone(block_instance_check, "Block instance not found after creation using its ID.")

            # Blocker logs in
            self.login(blocker.username, "password")

            response = self.client.post(url_for('unblock_user', username_to_unblock=blocked_user.username), follow_redirects=True)
            self.assertEqual(response.status_code, 200) # unblock_user redirects to profile

            # Verify the block is removed from DB using the block_id
            self.assertIsNone(UserBlock.query.get(block_id))

            # Verify flash message
            self.assertIn(f"You have unblocked {blocked_user.username}.".encode('utf-8'), response.data)

            # Verify profile is now fully visible (e.g., posts are shown)
            post_by_unblocked_user = self._create_db_post(user_id=blocked_user.id, title="Unblocked User's Post")
            response = self.client.get(url_for('user_profile', username=blocked_user.username))
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Unblocked User&#39;s Post", response.data) # Account for HTML escaping of apostrophe
            self.assertNotIn(b"You have blocked this user", response.data)

            self.logout()

    def test_blocked_user_cannot_send_friend_request_to_blocker(self):
        with self.app.app_context():
            blocker = self.user1 # Blocker
            blocked_user = self.user2 # User who will be blocked

            # Blocker blocks blocked_user
            self._create_db_block(blocker_user_obj=blocker, blocked_user_obj=blocked_user)

            # Blocked_user logs in
            self.login(blocked_user.username, "password")

            # Blocked_user attempts to send friend request to Blocker
            # Assuming `send_friend_request` is the route name and it takes target_user_id
            response = self.client.post(url_for('send_friend_request', target_user_id=blocker.id))

            # Check that the request was denied (e.g., redirect with flash, or specific status code)
            # This depends on how send_friend_request handles this.
            # For now, let's assume it redirects and flashes a message.
            self.assertEqual(response.status_code, 302) # Assuming redirect
            # Fetch flashed messages
            with self.client.session_transaction() as sess:
                flashes = sess.get('_flashes', [])
            self.assertTrue(any("You cannot send a friend request to this user as they have blocked you or you have blocked them." in message[1] for message in flashes))

            # Verify no friendship record was created
            friendship = Friendship.query.filter_by(user_id=blocked_user.id, friend_id=blocker.id).first()
            self.assertIsNone(friendship)
            friendship_reverse = Friendship.query.filter_by(user_id=blocker.id, friend_id=blocked_user.id).first()
            self.assertIsNone(friendship_reverse)

            self.logout()

    def test_user_cannot_send_friend_request_to_user_who_blocked_them(self):
        with self.app.app_context():
            blocker = self.user1 # User who blocks
            requester = self.user2 # User who will attempt to send request

            # Blocker blocks Requester
            self._create_db_block(blocker_user_obj=blocker, blocked_user_obj=requester)

            # Requester logs in
            self.login(requester.username, "password")

            # Requester attempts to send friend request to Blocker
            response = self.client.post(url_for('send_friend_request', target_user_id=blocker.id))
            self.assertEqual(response.status_code, 302) # Assuming redirect
            with self.client.session_transaction() as sess:
                flashes = sess.get('_flashes', [])
            self.assertTrue(any("You cannot send a friend request to this user as they have blocked you or you have blocked them." in message[1] for message in flashes))


            # Verify no friendship record was created
            friendship = Friendship.query.filter_by(user_id=requester.id, friend_id=blocker.id).first()
            self.assertIsNone(friendship)

            self.logout()

    def test_profile_picture_update_reflects_on_profile_page(self):
        with self.app.app_context():
            # Fetch the user from the current session to ensure we're working with a tracked instance
            user_to_update = db.session.get(User, self.user1.id)
            self.login(user_to_update.username, "password")

            # Simulate file upload
            new_pic_filename = "new_test_profile.png"
            # Ensure the URL is generated within the app context for url_for to work correctly
            new_pic_url = url_for('static', filename=f'profile_pics/{new_pic_filename}', _external=False)

            user_to_update.profile_picture = new_pic_url
            db.session.commit()

            # Verify the change in the database directly from the test's session
            fetched_user_for_debug = db.session.get(User, user_to_update.id)
            self.assertEqual(fetched_user_for_debug.profile_picture, new_pic_url, "Profile picture URL not updated in DB as expected by test.")

            # Create a dummy file in static/profile_pics
            static_profile_pics_path = self.app.config["PROFILE_PICS_FOLDER"]
            if not os.path.exists(static_profile_pics_path):
                os.makedirs(static_profile_pics_path)
            dummy_file_path = os.path.join(static_profile_pics_path, new_pic_filename)
            with open(dummy_file_path, 'w') as f:
                f.write("dummy image data")

            # Visit profile page
            response = self.client.get(url_for('user_profile', username=user_to_update.username))
            self.assertEqual(response.status_code, 200)

            # Check if the new profile picture URL is present in the rendered HTML
            self.assertIn(bytes(new_pic_url, 'utf-8'), response.data,
                          f"Expected profile picture URL '{new_pic_url}' not found in response. User profile_picture is '{user_to_update.profile_picture}'. Default might be showing.")

            # Clean up dummy file
            if os.path.exists(dummy_file_path):
                os.remove(dummy_file_path)

            self.logout()

    def test_edit_user_bio_and_verify_update(self):
        with self.app.app_context():
            user_to_edit = self.user1
            self.login(user_to_edit.username, "password")

            new_bio_text = "This is my new awesome bio!"
            response = self.client.post(url_for('edit_profile'), data={
                'username': user_to_edit.username, # Keep username same
                'email': user_to_edit.email,       # Keep email same
                'bio': new_bio_text
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200) # Should redirect to profile page

            # Verify bio is updated on the profile page
            self.assertIn(bytes(new_bio_text, 'utf-8'), response.data)

            # Verify in DB
            updated_user = db.session.get(User, user_to_edit.id)
            self.assertEqual(updated_user.bio, new_bio_text)

            self.logout()

if __name__ == '__main__':
    unittest.main()
