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

            # Client for post_author to receive notifications
            author_socket_client = self.create_socketio_client()
            # Simulate author joining their own user room
            author_socket_client.emit('join_room', {'room': f'user_{post_author.id}'}, namespace='/')
            author_socket_client.get_received() # Clear any initial messages

            # Liker performs the action that triggers the notification (e.g., POST to like route)
            response = self.client.post(f"/blog/post/{post_by_author.id}/like")
            self.assertEqual(response.status_code, 302) # Redirects after like

            # Check for 'new_like_notification' received by the author's client
            received_by_author = author_socket_client.get_received(timeout=1)

            like_notification_events = [r for r in received_by_author if r['name'] == 'new_like_notification']
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
            listener_client = self.create_socketio_client()
            listener_client.emit('join_room', {'room': f'post_{post_to_lock.id}'}, namespace='/')
            listener_client.get_received()

            # User1 locks the post via API
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
