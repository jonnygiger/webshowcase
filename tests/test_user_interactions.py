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
            block_instance_initial = self._create_db_block(blocker_user_obj=blocker, blocked_user_obj=blocked_user)
            block_id = block_instance_initial.id # Store ID
            # Verify it was created
            self.assertIsNotNone(UserBlock.query.get(block_id), "Block instance not found after creation.")


            # Blocker logs in
            self.login(blocker.username, "password")

            # Blocker unblocks the user (assuming a route like /user/<username>/unblock)
            # This route doesn't exist yet, so this test will fail or needs adjustment.
            # For now, let's simulate unblocking by deleting the UserBlock record directly for test logic.
            # In a real scenario, this would be a POST request to an unblock endpoint.
            response = self.client.post(url_for('unblock_user', username_to_unblock=blocked_user.username), follow_redirects=True)
            self.assertEqual(response.status_code, 200) # unblock_user redirects to profile

            # Verify the block is removed from DB
            self.assertIsNone(UserBlock.query.get(block_instance.id))

            # Verify flash message
            self.assertIn(f"You have unblocked {blocked_user.username}.".encode('utf-8'), response.data)

            # Verify profile is now fully visible (e.g., posts are shown)
            post_by_unblocked_user = self._create_db_post(user_id=blocked_user.id, title="Unblocked User's Post")
            response = self.client.get(url_for('user_profile', username=blocked_user.username))
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Unblocked User's Post", response.data)
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
            user_to_update = self.user1
            self.login(user_to_update.username, "password")

            # Simulate file upload
            # In a real test, you might need to mock `os.path.join`, `file.save`, etc.
            # For simplicity, we'll directly update the user's profile_picture field
            # as if the upload and file saving were successful.
            new_pic_filename = "new_test_profile.png"
            new_pic_url = url_for('static', filename=f'profile_pics/{new_pic_filename}', _external=False) # internal path for DB

            # This is the action that the /upload_profile_picture route would perform
            user_to_update.profile_picture = new_pic_url
            db.session.commit()

            # Create a dummy file in static/profile_pics so the url_for generates a valid link that doesn't 404 in the template
            # This step is more for ensuring the template renders correctly if it tries to load the image.
            # For testing the DB update and display of the path, it's not strictly necessary if the template handles broken image links gracefully.
            static_profile_pics_path = self.app.config["PROFILE_PICS_FOLDER"]
            if not os.path.exists(static_profile_pics_path):
                os.makedirs(static_profile_pics_path)
            with open(os.path.join(static_profile_pics_path, new_pic_filename), 'w') as f:
                f.write("dummy image data")


            # Visit profile page
            response = self.client.get(url_for('user_profile', username=user_to_update.username))
            self.assertEqual(response.status_code, 200)
            # Check if the new profile picture URL is present in the rendered HTML
            # The exact check depends on how the image is rendered (e.g., <img> tag src attribute)
            self.assertIn(bytes(new_pic_url, 'utf-8'), response.data)

            # Clean up dummy file
            os.remove(os.path.join(static_profile_pics_path, new_pic_filename))

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
