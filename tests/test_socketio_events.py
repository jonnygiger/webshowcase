import unittest
import json
from social_app.models.db_models import User, Post, Like, PostLock, Achievement, UserAchievement, ChatRoom, ChatMessage
from tests.test_base import AppTestCase
from flask_jwt_extended import create_access_token
from datetime import datetime, timedelta, timezone
import time
from unittest.mock import patch, call, ANY, MagicMock
import logging


class TestSocketIOEvents(AppTestCase):

    def setUp(self):
        super().setUp()
        self.app.logger.setLevel(logging.DEBUG)
        if not any(isinstance(handler, logging.StreamHandler) for handler in self.app.logger.handlers):
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.DEBUG)
            self.app.logger.addHandler(stream_handler)

        self.post_author = self.user1
        self.collaborator = self.user2
        self.another_user = self.user3

        self.test_post = self._create_db_post(
            user_id=self.post_author.id,
            title="Collaborative Post",
            content="Initial content.",
        )

        if self.socketio_client and self.socketio_client.connected:
            self.socketio_client.disconnect()

        self.socketio_client = self.socketio_class_level.test_client(
            self.app, flask_test_client=self.client
        )
        self.assertTrue(self.socketio_client.is_connected())
        self.app.logger.debug(f"TestClient setUp: Initial client SID: {self.socketio_client.eio_sid}, Connected: {self.socketio_client.is_connected()}")

    def tearDown(self):
        if self.socketio_client and self.socketio_client.is_connected():
            self.app.logger.debug(f"TestClient tearDown: Client SID: {self.socketio_client.eio_sid}, Connected: {self.socketio_client.is_connected()} before disconnect.")
            self.socketio_client.disconnect()
        super().tearDown()

    def test_socketio_new_like_notification(self):
        with self.app.app_context():
            post_author = self.user1
            liker_user = self.user2

            post_by_author = self._create_db_post(
                user_id=post_author.id, title="Post to be Liked"
            )

            self.login(liker_user.username, "password")

            author_socket_client = self.socketio_class_level.test_client(self.app)
            self.app.logger.debug(f"test_new_like_notification: Author client created. SID: {author_socket_client.eio_sid}, Connected: {author_socket_client.is_connected()}")
            self.login(post_author.username, "password", client_instance=author_socket_client)
            time.sleep(0.5)

            author_token = self._get_jwt_token(post_author.username, "password")
            self.app.logger.debug(f"test_new_like_notification: Author client emitting 'join_room'. SID: {author_socket_client.eio_sid}, Data: {{'room': f'user_{post_author.id}', 'token': {author_token[:20] if author_token else 'None'}+...}}")
            author_socket_client.emit("join_room", {"room": f"user_{post_author.id}", "token": author_token}, namespace="/")

            join_ack_start_time = time.time()
            while time.time() - join_ack_start_time < 0.2: # Short timeout for immediate events
                join_ack_batch = author_socket_client.get_received(namespace="/")
                self.app.logger.debug(f"test_new_like_notification: Author client polling for join ack. SID: {author_socket_client.eio_sid}. Received batch: {join_ack_batch}")
                if not join_ack_batch: # if empty, means no more immediate events
                    break
                # Process or just consume if not specifically checking join_ack here

            self.logout()
            self.login(liker_user.username, "password")

            response = self.client.post(f"/blog/post/{post_by_author.id}/like")
            self.assertEqual(response.status_code, 302) # Redirects to view_post

            time.sleep(0.5) # Allow time for server-side processing and event emission

            received_by_author_total = []
            notification_receive_start_time = time.time()
            while time.time() - notification_receive_start_time < 1.0: # Polling duration
                received_event_batch = author_socket_client.get_received(namespace="/")
                self.app.logger.debug(f"test_new_like_notification: Author client polling for events. SID: {author_socket_client.eio_sid}. Received batch: {received_event_batch}")
                if received_event_batch:
                    if isinstance(received_event_batch, list):
                        received_by_author_total.extend(received_event_batch)
                    else:
                        received_by_author_total.append(received_event_batch)
                else: # No events in this poll
                    if any(r["name"] == "new_like_notification" for r in received_by_author_total): # Check if we already got it
                        break
                    time.sleep(0.05) # Wait a bit before next poll if nothing received and target not met

            self.app.logger.debug(f"test_new_like_notification: Author client checking for 'new_like_notification'. SID: {author_socket_client.eio_sid}. Total received: {received_by_author_total}")
            like_notification_events = [r for r in received_by_author_total if r["name"] == "new_like_notification"]
            self.assertTrue(len(like_notification_events) > 0, "No 'new_like_notification' events received.")

            notification_data = like_notification_events[0]["args"][0]
            self.assertEqual(notification_data["liker_username"], liker_user.username)
            self.assertEqual(notification_data["post_id"], post_by_author.id)
            self.assertEqual(notification_data["post_title"], post_by_author.title)

            self.logout()
            if author_socket_client.is_connected():
                author_socket_client.disconnect()

    def test_socketio_post_lock_released_on_manual_release(self):
        with self.app.app_context():
            locking_user = self.user1
            post_to_lock = self._create_db_post(
                user_id=locking_user.id, title="Post for Lock Release Test"
            )

            listener_client = self.socketio_class_level.test_client(self.app)
            self.login(locking_user.username, "password", client_instance=listener_client)
            time.sleep(0.5)

            listener_token = self._get_jwt_token(locking_user.username, "password")
            listener_client.emit("join_room", {"room": f"post_{post_to_lock.id}", "token": listener_token}, namespace="/")

            join_ack_start_time = time.time()
            while time.time() - join_ack_start_time < 0.2:
                if not listener_client.get_received(namespace="/"):
                    break

            token_user1 = self._get_jwt_token(locking_user.username, "password")
            headers_user1 = {"Authorization": f"Bearer {token_user1}"}
            lock_response = self.client.post(f"/api/posts/{post_to_lock.id}/lock", headers=headers_user1)
            self.assertEqual(lock_response.status_code, 200)
            listener_client.get_received() # Consume potential post_lock_acquired event

            unlock_response = self.client.delete(f"/api/posts/{post_to_lock.id}/lock", headers=headers_user1)
            self.assertEqual(unlock_response.status_code, 200)

            time.sleep(0.5) # Allow time for event propagation
            received_by_listener_total = []
            notification_receive_start_time = time.time()
            while time.time() - notification_receive_start_time < 1.0: # Loop with timeout
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

            lock_released_events = [r for r in received_by_listener_total if r["name"] == "post_lock_released"]
            self.assertTrue(len(lock_released_events) > 0)
            event_data = lock_released_events[0]["args"][0]
            self.assertEqual(event_data["post_id"], post_to_lock.id)
            self.assertEqual(event_data["released_by_user_id"], locking_user.id)
            self.assertEqual(event_data["username"], locking_user.username)

            if listener_client.is_connected():
                listener_client.disconnect()

    def test_socketio_join_chat_room_auth(self):
        with self.app.app_context():
            client = self.socketio_class_level.test_client(self.app)
            self.app.logger.debug(f"test_join_chat_auth: New test client created. SID: {client.eio_sid}, Connected: {client.is_connected()}")
            self.login(self.user1.username, "password", client_instance=client)
            self.app.logger.debug(f"test_join_chat_auth: Post-login client SID: {client.eio_sid}, Connected: {client.is_connected()}")
            time.sleep(0.1); client.get_received() # Consume login event, if any
            room_name = "test_chat_room_auth"

            self.app.logger.debug(f"test_join_chat_auth: Emitting 'join_chat_room' (no token). SID: {client.eio_sid}, Data: {{'room_name': '{room_name}'}}")
            client.emit("join_chat_room", {"room_name": room_name})
            received = client.get_received()
            self.app.logger.debug(f"test_join_chat_auth: Received after 'join_chat_room' (no token). SID: {client.eio_sid}, Events: {received}")
            self.assertTrue(received); self.assertEqual(received[0]["name"], "auth_error")
            self.assertIn("Authentication token missing", received[0]["args"][0]["message"])

            self.app.logger.debug(f"test_join_chat_auth: Emitting 'join_chat_room' (invalid token). SID: {client.eio_sid}, Data: {{'room_name': '{room_name}', 'token': 'invalid.token.here'}}")
            client.emit("join_chat_room", {"room_name": room_name, "token": "invalid.token.here"})
            received = client.get_received()
            self.app.logger.debug(f"test_join_chat_auth: Received after 'join_chat_room' (invalid token). SID: {client.eio_sid}, Events: {received}")
            self.assertTrue(received); self.assertEqual(received[0]["name"], "auth_error")
            self.assertIn("Invalid token", received[0]["args"][0]["message"])

            user1_token = self._get_jwt_token(self.user1.username, "password")
            self.app.logger.debug(f"test_join_chat_auth: Emitting 'join_chat_room' (valid token). SID: {client.eio_sid}, Data: {{'room_name': '{room_name}', 'token': {user1_token[:20] if user1_token else 'None'}+...}}")
            client.emit("join_chat_room", {"room_name": room_name, "token": user1_token})
            received = client.get_received()
            self.app.logger.debug(f"test_join_chat_auth: Received after 'join_chat_room' (valid token). SID: {client.eio_sid}, Events: {received}")
            if received: self.assertNotEqual(received[0]["name"], "auth_error")

            if client.is_connected(): client.disconnect()

    def test_socketio_send_chat_message_auth(self):
        with self.app.app_context():
            chat_room_db_name = "chat_room_for_send_test"
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

            sender_client.emit("send_chat_message", {"room_name": room_sio_name, "message": message_text})
            received = sender_client.get_received(); self.assertTrue(received); self.assertEqual(received[0]["name"], "auth_error")
            self.assertIn("Authentication token missing", received[0]["args"][0]["message"])

            sender_client.emit("send_chat_message", {"room_name": room_sio_name, "message": message_text, "token": "invalid.token"})
            received = sender_client.get_received(); self.assertTrue(received); self.assertEqual(received[0]["name"], "auth_error")
            self.assertIn("Invalid token", received[0]["args"][0]["message"])

            sender_client.emit("send_chat_message", {"room_name": room_sio_name, "message": message_text, "token": user1_token})
            received_by_receiver = None
            for _ in range(10): # Loop with a timeout mechanism
                received_by_receiver = receiver_client.get_received()
                if received_by_receiver and received_by_receiver[0]["name"] == "new_chat_message": break
                time.sleep(0.1) # Wait a bit before retrying
            self.assertTrue(received_by_receiver)
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

            editor_client.emit("edit_post_content", {**edit_payload})
            received = editor_client.get_received(); self.assertTrue(received); self.assertEqual(received[0]["name"], "auth_error")
            self.assertIn("Authentication token missing", received[0]["args"][0]["message"])

            editor_client.emit("edit_post_content", {**edit_payload, "token": "invalid"})
            received = editor_client.get_received(); self.assertTrue(received); self.assertEqual(received[0]["name"], "auth_error")
            self.assertIn("Invalid token", received[0]["args"][0]["message"])

            editor_client.emit("edit_post_content", {**edit_payload, "token": owner_token})
            received = editor_client.get_received(); self.assertTrue(received); self.assertEqual(received[0]["name"], "edit_error")
            self.assertIn("Post not locked", received[0]["args"][0]["message"])

            lock_headers = {"Authorization": f"Bearer {owner_token}"}
            self.client.post(f"/api/posts/{post.id}/lock", headers=lock_headers); time.sleep(0.1)

            listener_client = self.socketio_class_level.test_client(self.app)
            self.login(other_user.username, "password", client_instance=listener_client); time.sleep(0.1); listener_client.get_received()
            listener_client.emit("join_room", {"room": post_room, "token": other_user_token}); time.sleep(0.1); listener_client.get_received()

            successful_edit_payload = {"post_id": post.id, "new_content": "Updated Content by Owner", "token": owner_token}
            editor_client.emit("edit_post_content", successful_edit_payload)
            received_edit_confirm = editor_client.get_received(); self.assertTrue(received_edit_confirm); self.assertEqual(received_edit_confirm[0]["name"], "edit_success")

            received_broadcast = None
            for _ in range(10): # Loop with a timeout mechanism
                received_broadcast = listener_client.get_received()
                if received_broadcast and received_broadcast[0]["name"] == "post_content_updated": break
                time.sleep(0.1) # Wait a bit before retrying
            self.assertTrue(received_broadcast)
            self.assertEqual(received_broadcast[0]["name"], "post_content_updated")
            self.assertEqual(received_broadcast[0]["args"][0]["new_content"], "Updated Content by Owner")

            editor_client.emit("edit_post_content", {**edit_payload, "token": other_user_token, "new_content": "Other user content"})
            received = editor_client.get_received(); self.assertTrue(received); self.assertEqual(received[0]["name"], "edit_error")
            self.assertIn("Post locked by another user", received[0]["args"][0]["message"])

            self.client.delete(f"/api/posts/{post.id}/lock", headers=lock_headers); time.sleep(0.1)
            if editor_client.is_connected(): editor_client.disconnect()
            if listener_client.is_connected(): listener_client.disconnect()

if __name__ == "__main__":
    unittest.main()
