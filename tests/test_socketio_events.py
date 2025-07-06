import unittest
import json
from social_app.models.db_models import User, Post, Like, PostLock, Achievement, UserAchievement
from tests.test_base import AppTestCase  # Assuming this sets up app context and db
from flask_jwt_extended import create_access_token
from datetime import datetime, timedelta, timezone
import time # Ensure time is imported at the top level

class TestSocketIOEvents(AppTestCase):

    def test_socketio_new_like_notification(self):
        with self.app.app_context():
            post_author = self.user1
            liker_user = self.user2

            post_by_author = self._create_db_post(
                user_id=post_author.id, title="Post to be Liked"
            )

            # Liker user logs in using the main self.client for HTTP actions
            self.login(liker_user.username, "password")

            # Client for post_author to receive notifications
            author_socket_client = self.socketio_class_level.test_client(self.app)

            # Log in post_author for session association with author_socket_client
            self.login(
                post_author.username, "password", client_instance=author_socket_client
            )
            time.sleep(0.5)

            # Author's client joins its room, now requiring a token for the 'join_room' event
            author_token = self._get_jwt_token(post_author.username, "password")
            author_socket_client.emit(
                "join_room", {"room": f"user_{post_author.id}", "token": author_token}, namespace="/"
            )

            # Clear any ack from join_room
            join_ack_start_time = time.time()
            while time.time() - join_ack_start_time < 0.2:  # Max 0.2s to clear
                if not author_socket_client.get_received(namespace="/"):
                    break

            # self.client (HTTP client) is currently logged in as post_author from the previous self.login.
            # Log out self.client (from post_author) and log in liker_user to perform the like action.
            self.logout()
            self.login(liker_user.username, "password") # self.client is now liker_user

            # Liker performs the action
            response = self.client.post(f"/blog/post/{post_by_author.id}/like")
            self.assertEqual(response.status_code, 302)

            time.sleep(0.5)  # Wait for server-side emit

            received_by_author_total = []
            notification_receive_start_time = time.time()
            while time.time() - notification_receive_start_time < 1.0:
                received_event_batch = author_socket_client.get_received(namespace="/")
                if received_event_batch:
                    if isinstance(received_event_batch, list):
                        received_by_author_total.extend(received_event_batch)
                    else:
                        received_by_author_total.append(received_event_batch)
                else:
                    if any(r["name"] == "new_like_notification" for r in received_by_author_total):
                        break
                    time.sleep(0.05)

            like_notification_events = [
                r for r in received_by_author_total if r["name"] == "new_like_notification"
            ]
            self.assertTrue(
                len(like_notification_events) > 0,
                "Author did not receive 'new_like_notification'"
            )

            notification_data = like_notification_events[0]["args"][0]
            self.assertEqual(notification_data["liker_username"], liker_user.username)
            self.assertEqual(notification_data["post_id"], post_by_author.id)
            self.assertEqual(notification_data["post_title"], post_by_author.title)

            self.logout()  # Liker logs out
            if author_socket_client.is_connected():
                author_socket_client.disconnect()

    def test_socketio_post_lock_released_on_manual_release(self):
        with self.app.app_context():
            locking_user = self.user1
            post_to_lock = self._create_db_post(
                user_id=locking_user.id, title="Post for Lock Release Test"
            )

            listener_client = self.socketio_class_level.test_client(self.app)
            self.login(
                locking_user.username, "password", client_instance=listener_client
            )
            time.sleep(0.5)

            # Listener client joins post's room, now requiring a token for 'join_room' event
            listener_token = self._get_jwt_token(locking_user.username, "password")
            listener_client.emit(
                "join_room", {"room": f"post_{post_to_lock.id}", "token": listener_token}, namespace="/"
            )

            join_ack_start_time = time.time()
            while time.time() - join_ack_start_time < 0.2:
                if not listener_client.get_received(namespace="/"):
                    break

            # User1 locks the post via API (self.client is locking_user due to earlier self.login)
            token_user1 = self._get_jwt_token(locking_user.username, "password") # This token is for HTTP API
            headers_user1 = {"Authorization": f"Bearer {token_user1}"}
            lock_response = self.client.post(
                f"/api/posts/{post_to_lock.id}/lock", headers=headers_user1
            )
            self.assertEqual(lock_response.status_code, 200)
            # Clear lock_acquired event from listener if any
            listener_client.get_received(timeout=0.5)

            # User1 releases the lock via API
            unlock_response = self.client.delete(
                f"/api/posts/{post_to_lock.id}/lock", headers=headers_user1
            )
            self.assertEqual(unlock_response.status_code, 200)

            # Check for 'post_lock_released' event
            # Wait a bit longer to ensure event is processed and received
            time.sleep(0.5)
            received_by_listener_total = []
            notification_receive_start_time = time.time()
            while time.time() - notification_receive_start_time < 1.0:
                received_event_batch = listener_client.get_received(namespace="/")
                if received_event_batch:
                    if isinstance(received_event_batch, list):
                        received_by_listener_total.extend(received_event_batch)
                    else:
                        received_by_listener_total.append(received_event_batch)
                else:
                    if any(r["name"] == "post_lock_released" for r in received_by_listener_total):
                        break
                    time.sleep(0.05)

            lock_released_events = [
                r for r in received_by_listener_total if r["name"] == "post_lock_released"
            ]

            self.assertTrue(
                len(lock_released_events) > 0,
                f"Listener did not receive 'post_lock_released' event. Received: {received_by_listener_total}"
            )
            event_data = lock_released_events[0]["args"][0]
            self.assertEqual(event_data["post_id"], post_to_lock.id)
            self.assertEqual(event_data["released_by_user_id"], locking_user.id)
            self.assertEqual(event_data["username"], locking_user.username)

            if listener_client.is_connected():
                listener_client.disconnect()

    def test_socketio_join_chat_room_auth(self):
        with self.app.app_context():
            client = self.socketio_class_level.test_client(self.app)
            self.login(self.user1.username, "password", client_instance=client) # For connect handler
            time.sleep(0.1) # Allow connection
            client.get_received() # Clear connect confirmation

            room_name = "test_chat_room_auth"

            # 1. No token
            client.emit("join_chat_room", {"room_name": room_name})
            received = client.get_received(timeout=1)
            self.assertTrue(received, "No response from server for no token")
            self.assertEqual(received[0]["name"], "auth_error", "Event name mismatch for no token")
            self.assertIn("Authentication token missing", received[0]["args"][0]["message"], "Message content mismatch for no token")

            # 2. Invalid token
            client.emit("join_chat_room", {"room_name": room_name, "token": "invalid.token.here"})
            received = client.get_received(timeout=1)
            self.assertTrue(received, "No response from server for invalid token")
            self.assertEqual(received[0]["name"], "auth_error", "Event name mismatch for invalid token")
            self.assertIn("Invalid token", received[0]["args"][0]["message"], "Message content mismatch for invalid token")

            # 3. Valid token
            user1_token = self._get_jwt_token(self.user1.username, "password")
            client.emit("join_chat_room", {"room_name": room_name, "token": user1_token})
            received = client.get_received(timeout=0.5)
            if received:
                 self.assertNotEqual(received[0]["name"], "auth_error", f"Auth error received with valid token: {received}")

            if client.is_connected():
                client.disconnect()

    def test_socketio_send_chat_message_auth(self):
        with self.app.app_context():
            chat_room_db_name = "chat_room_for_send_test"
            from social_app.models.db_models import ChatRoom # Local import for clarity
            chat_room_obj = ChatRoom.query.filter_by(name=chat_room_db_name).first()
            if not chat_room_obj:
                chat_room_obj = ChatRoom(name=chat_room_db_name, creator_id=self.user1.id)
                self.db.session.add(chat_room_obj)
                self.db.session.commit()
            room_sio_name = f"chat_room_{chat_room_obj.id}"

            sender_client = self.socketio_class_level.test_client(self.app)
            self.login(self.user1.username, "password", client_instance=sender_client); time.sleep(0.1); sender_client.get_received()

            receiver_client = self.socketio_class_level.test_client(self.app)
            self.login(self.user2.username, "password", client_instance=receiver_client); time.sleep(0.1); receiver_client.get_received()

            user1_token = self._get_jwt_token(self.user1.username, "password")
            user2_token = self._get_jwt_token(self.user2.username, "password")

            sender_client.emit("join_chat_room", {"room_name": room_sio_name, "token": user1_token}); time.sleep(0.1); sender_client.get_received()
            receiver_client.emit("join_chat_room", {"room_name": room_sio_name, "token": user2_token}); time.sleep(0.1); receiver_client.get_received()

            message_text = "Hello from test_socketio_send_chat_message_auth"

            # 1. No token
            sender_client.emit("send_chat_message", {"room_name": room_sio_name, "message": message_text})
            received = sender_client.get_received(timeout=1)
            self.assertTrue(received); self.assertEqual(received[0]["name"], "auth_error")
            self.assertIn("Authentication token missing", received[0]["args"][0]["message"])

            # 2. Invalid token
            sender_client.emit("send_chat_message", {"room_name": room_sio_name, "message": message_text, "token": "invalid.token"})
            received = sender_client.get_received(timeout=1)
            self.assertTrue(received); self.assertEqual(received[0]["name"], "auth_error")
            self.assertIn("Invalid token", received[0]["args"][0]["message"])

            # 3. Valid token
            sender_client.emit("send_chat_message", {"room_name": room_sio_name, "message": message_text, "token": user1_token})
            received_by_receiver = None
            for _ in range(10): # Increased attempts for reliability
                received_by_receiver = receiver_client.get_received(timeout=0.2)
                if received_by_receiver and received_by_receiver[0]["name"] == "new_chat_message": break
                time.sleep(0.1)
            self.assertTrue(received_by_receiver, f"Receiver did not get new_chat_message. Last: {receiver_client.get_received(timeout=0.1)}")
            self.assertEqual(received_by_receiver[0]["name"], "new_chat_message")
            self.assertEqual(received_by_receiver[0]["args"][0]["message"], message_text)
            self.assertEqual(received_by_receiver[0]["args"][0]["username"], self.user1.username)

            if sender_client.is_connected(): sender_client.disconnect()
            if receiver_client.is_connected(): receiver_client.disconnect()

    def test_socketio_edit_post_content_auth_and_logic(self):
        with self.app.app_context():
            post_owner = self.user1
            other_user = self.user2
            post = self._create_db_post(user_id=post_owner.id, title="Editable Post", content="Original Content")
            post_room = f"post_{post.id}"

            editor_client = self.socketio_class_level.test_client(self.app)
            self.login(post_owner.username, "password", client_instance=editor_client); time.sleep(0.1); editor_client.get_received()

            owner_token = self._get_jwt_token(post_owner.username, "password")
            other_user_token = self._get_jwt_token(other_user.username, "password")
            edit_payload = {"post_id": post.id, "new_content": "Attempted Content"}

            # No token
            editor_client.emit("edit_post_content", {**edit_payload})
            received = editor_client.get_received(timeout=1); self.assertTrue(received); self.assertEqual(received[0]["name"], "auth_error")
            self.assertIn("Authentication token missing", received[0]["args"][0]["message"])

            # Invalid token
            editor_client.emit("edit_post_content", {**edit_payload, "token": "invalid"})
            received = editor_client.get_received(timeout=1); self.assertTrue(received); self.assertEqual(received[0]["name"], "auth_error")
            self.assertIn("Invalid token", received[0]["args"][0]["message"])

            # Valid token (owner), post not locked
            editor_client.emit("edit_post_content", {**edit_payload, "token": owner_token})
            received = editor_client.get_received(timeout=1); self.assertTrue(received); self.assertEqual(received[0]["name"], "edit_error")
            self.assertIn("Post not locked", received[0]["args"][0]["message"])

            # Owner locks post (via API)
            lock_headers = {"Authorization": f"Bearer {owner_token}"}
            self.client.post(f"/api/posts/{post.id}/lock", headers=lock_headers); time.sleep(0.1)

            # Valid token (owner), post locked by owner - successful edit
            listener_client = self.socketio_class_level.test_client(self.app)
            self.login(other_user.username, "password", client_instance=listener_client); time.sleep(0.1); listener_client.get_received()
            listener_client.emit("join_room", {"room": post_room, "token": other_user_token}); time.sleep(0.1); listener_client.get_received()

            successful_edit_payload = {"post_id": post.id, "new_content": "Updated Content by Owner", "token": owner_token}
            editor_client.emit("edit_post_content", successful_edit_payload)
            received_edit_confirm = editor_client.get_received(timeout=1); self.assertTrue(received_edit_confirm); self.assertEqual(received_edit_confirm[0]["name"], "edit_success")

            received_broadcast = None
            for _ in range(10): # Increased attempts
                received_broadcast = listener_client.get_received(timeout=0.2)
                if received_broadcast and received_broadcast[0]["name"] == "post_content_updated": break
                time.sleep(0.1)
            self.assertTrue(received_broadcast, "No broadcast for post_content_updated")
            self.assertEqual(received_broadcast[0]["name"], "post_content_updated")
            self.assertEqual(received_broadcast[0]["args"][0]["new_content"], "Updated Content by Owner")

            # Other user tries to edit (valid token), post locked by owner
            editor_client.emit("edit_post_content", {**edit_payload, "token": other_user_token, "new_content": "Other user content"})
            received = editor_client.get_received(timeout=1); self.assertTrue(received); self.assertEqual(received[0]["name"], "edit_error")
            self.assertIn("Post locked by another user", received[0]["args"][0]["message"])

            self.client.delete(f"/api/posts/{post.id}/lock", headers=lock_headers); time.sleep(0.1)
            if editor_client.is_connected(): editor_client.disconnect()
            if listener_client.is_connected(): listener_client.disconnect()

if __name__ == "__main__":
    unittest.main()
