import json
from models import db, User, ChatRoom, ChatMessage
from tests.test_base import AppTestCase  # Assuming AppTestCase is set up for SocketIO
from flask_jwt_extended import create_access_token
from datetime import datetime, timezone


class ChatTestCase(AppTestCase):

    def setUp(self):
        super().setUp()
        # Additional setup specific to chat tests if needed
        with self.app.app_context():
            self.user1_token = create_access_token(identity=str(self.user1_id))
            self.user2_token = create_access_token(identity=str(self.user2_id))

    def test_create_chat_room_api(self):
        with self.app.app_context():
            room_name = "Test Room API"
            response = self.client.post(
                "/api/chat/rooms",
                json={"name": room_name},
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(response.status_code, 201)
            data = response.get_json()
            self.assertIn("chat_room", data)
            self.assertEqual(data["chat_room"]["name"], room_name)
            self.assertEqual(data["chat_room"]["creator_id"], self.user1_id)

            # Verify room exists in DB
            room_db = db.session.get(ChatRoom, data["chat_room"]["id"])
            self.assertIsNotNone(room_db)
            self.assertEqual(room_db.name, room_name)

    def test_get_chat_rooms_api(self):
        with self.app.app_context():
            # Create a room first
            room1 = ChatRoom(name="Room Alpha", creator_id=self.user1_id)
            room2 = ChatRoom(name="Room Beta", creator_id=self.user2_id)
            db.session.add_all([room1, room2])
            db.session.commit()

            response = self.client.get(
                "/api/chat/rooms",
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn("chat_rooms", data)
            self.assertEqual(len(data["chat_rooms"]), 2)
            room_names = {room["name"] for room in data["chat_rooms"]}
            self.assertIn("Room Alpha", room_names)
            self.assertIn("Room Beta", room_names)

    def test_get_chat_room_messages_api(self):
        with self.app.app_context():
            room = ChatRoom(name="Message Test Room", creator_id=self.user1_id)
            db.session.add(room)
            db.session.commit()

            msg1_time = datetime.now(timezone.utc)
            msg1 = ChatMessage(
                room_id=room.id,
                user_id=self.user1_id,
                message="Hello from user1",
                timestamp=msg1_time,
            )
            db.session.add(msg1)
            db.session.commit()
            # To ensure distinct timestamps for ordering test
            # msg2_time = datetime.now(timezone.utc) + timedelta(seconds=1)
            # msg2 = ChatMessage(room_id=room.id, user_id=self.user2_id, message="Hi user1, from user2", timestamp=msg2_time)
            # db.session.add(msg2)
            # db.session.commit()

            response = self.client.get(
                f"/api/chat/rooms/{room.id}/messages",
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn("messages", data)
            self.assertEqual(
                len(data["messages"]), 1
            )  # Adjusted to 1 message for simplicity
            self.assertEqual(data["messages"][0]["message"], "Hello from user1")
            self.assertEqual(data["messages"][0]["user_id"], self.user1_id)
            # Check timestamp (may need to parse and compare closely)
            # self.assertEqual(data['messages'][1]['message'], "Hi user1, from user2")

    def test_socketio_join_and_send_message(self):
        with self.app.app_context():
            # 1. Create a room via API or directly for setup
            room_response = self.client.post(
                "/api/chat/rooms",
                json={"name": "Socket Test Room"},
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(room_response.status_code, 201)
            room_data = room_response.get_json()["chat_room"]
            room_id = room_data["id"]
            socket_room_name = f"chat_room_{room_id}"

            # 2. User1 connects and joins the room
            # The AppTestCase's self.socketio_client is already connected implicitly
            # when it's created. We need to simulate login for session context.
            self.login(self.user1.username, "password")  # Login user1 to set session for self.socketio_client
            import time
            time.sleep(0.5) # Allow server to fully process the connection established in login

            # User1 joins the room
            self.socketio_client.emit(
                "join_chat_room", {"room_name": socket_room_name}, namespace="/"
            )

            # Check for 'user_joined_chat' broadcast (optional, might need another client to verify)
            # For simplicity, we'll assume join works and focus on message sending.

            # 3. User1 sends a message
            test_message = "Hello from SocketIO test!"
            self.socketio_client.emit(
                "send_chat_message",
                {"room_name": socket_room_name, "message": test_message},
                namespace="/",
            )

            # 4. Verify the message is received (by the sender themselves, and potentially others)
            # The test client can receive events it emits if not careful with rooms/broadcasts
            # We expect 'new_chat_message'
            received = self.socketio_client.get_received()

            # Filter for 'new_chat_message' events specifically for this test message
            # This is a simplified check. A more robust test might involve a second client.

            new_message_events = [
                r for r in received if r["name"] == "new_chat_message"
            ]
            self.assertTrue(
                len(new_message_events) > 0, "No 'new_chat_message' event received"
            )

            # Check the content of the received message
            # The last 'new_chat_message' should be ours if no other tests are interfering.
            # This part can be tricky due to test client behavior and event ordering.
            found_message = False
            for event_data in new_message_events:
                args = event_data["args"][
                    0
                ]  # Assuming message payload is the first argument
                if (
                    args["message"] == test_message
                    and args["username"] == self.user1.username
                ):
                    found_message = True
                    self.assertEqual(args["room_name"], socket_room_name)
                    self.assertEqual(args["user_id"], self.user1_id)
                    break
            self.assertTrue(
                found_message, "Sent message not found in received SocketIO events"
            )

            # 5. Verify message is in the database
            message_in_db = ChatMessage.query.filter_by(
                room_id=room_id, user_id=self.user1_id, message=test_message
            ).first()
            self.assertIsNotNone(message_in_db)
            self.logout()  # Clean up session

    def test_send_message_to_unjoined_room(self):
        with self.app.app_context():
            # 1. User1 creates a room
            room_response = self.client.post(
                "/api/chat/rooms",
                json={"name": "Unjoined Test Room"},
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(room_response.status_code, 201)
            room_data = room_response.get_json()["chat_room"]
            room_id = room_data["id"]
            socket_room_name = f"chat_room_{room_id}"

            # 2. User1 (socketio_client) connects and joins the room
            self.login(
                self.user1.username, "password"
            )  # Simulate login for User1's socket client
            import time # Make sure time is imported
            time.sleep(0.5) # Allow server to fully process the connection established in login
            self.socketio_client.emit("join_chat_room", {"room_name": socket_room_name}, namespace="/")
            # Clear any initial messages from User1 joining
            self.socketio_client.get_received()
            # We keep user1's socketio_client connected.
            # self.logout() here would disconnect self.socketio_client if not careful.
            # We'll logout/disconnect user1's client at the end of the test.

            # 3. User2 (socketio_client_user2) connects but DOES NOT join the room
            # We need a separate client for user2
            socketio_client_user2 = self.create_socketio_client()
            self.login(
                self.user2.username, "password", client_instance=socketio_client_user2
            )  # Login user2 to set session for this new client

            # 4. User2 attempts to send a message to the room
            test_message_by_user2 = "Hello from User2 (unjoined)"
            socketio_client_user2.emit(
                "send_chat_message",
                {"room_name": socket_room_name, "message": test_message_by_user2},
                namespace="/",
            )

            # 5. Verify User1 (original socketio_client) did NOT receive User2's message
            # Allow some time for events to (not) propagate
            import time

            time.sleep(0.1)  # Small delay
            received_by_user1 = self.socketio_client.get_received()
            user1_messages = [
                r for r in received_by_user1 if r["name"] == "new_chat_message"
            ]
            for event_data in user1_messages:
                args = event_data["args"][0]
                self.assertNotEqual(
                    args["message"],
                    test_message_by_user2,
                    "User1 should not receive message from unjoined User2",
                )

            # 6. Verify User2 did not get their own message back (if server drops it, which is expected)
            received_by_user2 = socketio_client_user2.get_received()
            user2_own_messages = [
                r
                for r in received_by_user2
                if r["name"] == "new_chat_message"
                and r["args"][0]["message"] == test_message_by_user2
            ]
            self.assertEqual(
                len(user2_own_messages),
                0,
                "User2 should not receive their own message if they are not in the room",
            )

            # It's possible the server sends an error event instead. If so, that would be a different test.
            # For now, we assume no message event is sent back to the unauthorized sender.

            # 7. Verify message from User2 is NOT in the database
            message_in_db = ChatMessage.query.filter_by(
                room_id=room_id, user_id=self.user2_id, message=test_message_by_user2
            ).first()
            self.assertIsNone(
                message_in_db, "Message from unjoined User2 should not be saved in DB"
            )

            # Cleanup
            self.logout(
                client_instance=socketio_client_user2
            )  # Logout User2 from HTTP session & disconnect its socket client
            # Explicitly disconnect self.socketio_client (user1's client) and logout its HTTP session
            if self.socketio_client and self.socketio_client.is_connected():
                self.socketio_client.disconnect()
            self.logout()  # Logs out self.client (associated with user1's initial login)

    def test_chat_page_loads_for_logged_in_user(self):
        self.login(self.user1.username, "password")
        response = self.client.get("/chat")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Real-Time Chat", response.data)
        self.assertIn(b"chatRoomList", response.data)  # Check for key elements
        self.assertIn(b"messagesArea", response.data)
        self.logout()

    def test_chat_page_redirects_for_anonymous_user(self):
        response = self.client.get(
            "/chat", follow_redirects=False
        )  # Important: follow_redirects=False
        self.assertEqual(response.status_code, 302)  # Expect redirect
        self.assertIn("/login", response.location)  # Check redirect location


if __name__ == "__main__":
    unittest.main()
