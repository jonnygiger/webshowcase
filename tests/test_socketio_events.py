import unittest
import json
from app import app, db, socketio
from models import User, Post, Like, PostLock, Achievement, UserAchievement
from tests.test_base import AppTestCase # Assuming this sets up app context and db
from flask_jwt_extended import create_access_token
from datetime import datetime, timedelta, timezone

class TestSocketIOEvents(AppTestCase):

    def test_socketio_new_like_notification(self):
        with self.app.app_context():
            post_author = self.user1
            liker_user = self.user2

            post_by_author = self._create_db_post(user_id=post_author.id, title="Post to be Liked")

            # Liker user needs to be logged in to like via a route,
            # but for direct SocketIO test, we simulate the like and notification trigger.
            # The route /blog/post/<post_id>/like handles emitting 'new_like_notification'

            self.login(liker_user.username, "password") # Liker logs in

            import time

            # Liker user logs in using the main self.client for HTTP actions
            self.login(liker_user.username, "password")

            # Create an independent SocketIO client for the post_author
            author_socket_client = self.socketio_class_level.test_client(self.app) # No flask_test_client linkage

            import time

            # Client for post_author to receive notifications
            author_socket_client = self.socketio_class_level.test_client(self.app)

            # Log in post_author. This will:
            # 1. Associate author_socket_client with post_author's session (due to client_instance arg).
            # 2. Set self.client (HTTP client) cookies to post_author's session.
            self.login(post_author.username, "password", client_instance=author_socket_client)
            time.sleep(0.5) # Added delay: Allow server to fully process the connection and session from login

            # Author's client joins its room
            author_socket_client.emit('join_room', {'room': f'user_{post_author.id}'}, namespace='/')
            # Clear any ack from join_room
            join_ack_start_time = time.time()
            while time.time() - join_ack_start_time < 0.2: # Max 0.2s to clear
                if not author_socket_client.get_received(namespace='/'):
                    break

            # self.client (HTTP client) is currently logged in as post_author.
            # We need liker_user to make the HTTP POST request for the like.
            # So, log out self.client (from post_author) and log in liker_user.
            self.logout() # Logs out self.client (HTTP) and self.socketio_client (default socket client)

            # Log in liker_user. This sets self.client (HTTP) to liker_user's session.
            # It also connects/reconfigures self.socketio_client (the default one for the test case) for liker_user.
            self.login(liker_user.username, "password")

            # Liker performs the action (self.client is now liker_user for HTTP)
            response = self.client.post(f"/blog/post/{post_by_author.id}/like")
            self.assertEqual(response.status_code, 302) # Redirects after like

            # Check for 'new_like_notification' received by the author's client
            time.sleep(0.5) # Wait for server-side emit

            # Collect all received messages within a timeout period
            received_by_author_total = []
            notification_receive_start_time = time.time()
            while time.time() - notification_receive_start_time < 1.0: # Collect for up to 1 second
                received_event_batch = author_socket_client.get_received(namespace='/')
                if received_event_batch:
                    # get_received can return a list of events if multiple were processed
                    if isinstance(received_event_batch, list):
                         received_by_author_total.extend(received_event_batch)
                    else: # Or a single event
                        received_by_author_total.append(received_event_batch)
                else: # No more messages in the queue currently
                    if like_notification_events := [r for r in received_by_author_total if r['name'] == 'new_like_notification']:
                        break # Found the notification, no need to wait longer
                    time.sleep(0.05) # Small pause before trying get_received again

            like_notification_events = [r for r in received_by_author_total if r['name'] == 'new_like_notification']
            self.assertTrue(len(like_notification_events) > 0, "Author did not receive 'new_like_notification'")

            notification_data = like_notification_events[0]['args'][0]
            self.assertEqual(notification_data['liker_username'], liker_user.username)
            self.assertEqual(notification_data['post_id'], post_by_author.id)
            self.assertEqual(notification_data['post_title'], post_by_author.title)

            self.logout() # Liker logs out
            if author_socket_client.is_connected():
                author_socket_client.disconnect()


    def test_socketio_post_lock_released_on_manual_release(self):
        with self.app.app_context():
            locking_user = self.user1
            post_to_lock = self._create_db_post(user_id=locking_user.id, title="Post for Lock Release Test")

            # Client to listen on the post's room
            listener_client = self.socketio_class_level.test_client(self.app)
            # Log in a user with this client to ensure it's properly connected.
            # The user performing the login for this listener client doesn't strictly matter
            # as it's just joining a room to listen. We can use locking_user.
            self.login(locking_user.username, "password", client_instance=listener_client)
            import time # Ensure time is imported
            time.sleep(0.5) # Allow server to fully process the connection

            listener_client.emit('join_room', {'room': f'post_{post_to_lock.id}'}, namespace='/')
            # Clear any ack from join_room
            join_ack_start_time = time.time()
            while time.time() - join_ack_start_time < 0.2: # Max 0.2s to clear
                if not listener_client.get_received(namespace='/'):
                    break
            # listener_client.get_received() # Original line, replaced by loop

            # User1 locks the post via API - self.client is now locking_user from the self.login above.
            # This is fine, or we can re-login if needed, but JWT token is used below, making self.client's session less critical for this API call.
            token_user1 = self._get_jwt_token(locking_user.username, "password")
            headers_user1 = {"Authorization": f"Bearer {token_user1}"}
            lock_response = self.client.post(f'/api/posts/{post_to_lock.id}/lock', headers=headers_user1)
            self.assertEqual(lock_response.status_code, 200)
            # Clear lock_acquired event from listener
            listener_client.get_received(timeout=0.5)


            # User1 releases the lock via API
            unlock_response = self.client.delete(f'/api/posts/{post_to_lock.id}/lock', headers=headers_user1)
            self.assertEqual(unlock_response.status_code, 200)

            # Check for 'post_lock_released' event
            received_by_listener = listener_client.get_received(timeout=1)
            lock_released_events = [r for r in received_by_listener if r['name'] == 'post_lock_released']

            self.assertTrue(len(lock_released_events) > 0, "Listener did not receive 'post_lock_released' event")
            event_data = lock_released_events[0]['args'][0]
            self.assertEqual(event_data['post_id'], post_to_lock.id)
            self.assertEqual(event_data['released_by_user_id'], locking_user.id)
            self.assertEqual(event_data['username'], locking_user.username)

            if listener_client.is_connected():
                listener_client.disconnect()

    # Test for lock release on expiry is more complex as it involves time passing
    # and scheduler behavior or manual time manipulation, often better suited for integration/E2E.
    # We can simulate the effect if the lock check logic directly handles expiry.
    # The PostLockResource's POST method already handles deleting expired locks if another user tries to lock.
    # A dedicated test for `Post.is_locked()` already covers expiry logic at model level.

if __name__ == "__main__":
    unittest.main()
