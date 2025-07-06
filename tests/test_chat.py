import json
from social_app import db
from social_app.models.db_models import User, ChatRoom, ChatMessage
from tests.test_base import AppTestCase
from flask_jwt_extended import create_access_token
from datetime import datetime, timezone
import time


class ChatTestCase(AppTestCase):

    def setUp(self):
        super().setUp()
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

            room_db = db.session.get(ChatRoom, data["chat_room"]["id"])
            self.assertIsNotNone(room_db)
            self.assertEqual(room_db.name, room_name)

    def test_get_chat_rooms_api(self):
        with self.app.app_context():
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

            response = self.client.get(
                f"/api/chat/rooms/{room.id}/messages",
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn("messages", data)
            self.assertEqual(len(data["messages"]), 1)
            self.assertEqual(data["messages"][0]["message"], "Hello from user1")
            self.assertEqual(data["messages"][0]["user_id"], self.user1_id)

    def test_socketio_join_and_send_message(self):
        with self.app.app_context():
            room_response = self.client.post(
                "/api/chat/rooms",
                json={"name": "Socket Test Room"},
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(room_response.status_code, 201)
            room_data = room_response.get_json()["chat_room"]
            room_id = room_data["id"]
            socket_room_name = f"chat_room_{room_id}"

            self.login(self.user1.username, "password")

            self.socketio_client.emit(
                "join_chat_room", {"room_name": socket_room_name}, namespace="/"
            )

            test_message = "Hello from SocketIO test!"
            self.socketio_client.emit(
                "send_chat_message",
                {"room_name": socket_room_name, "message": test_message},
                namespace="/",
            )

            received = self.socketio_client.get_received()

            new_message_events = [
                r for r in received if r["name"] == "new_chat_message"
            ]
            self.assertTrue(len(new_message_events) > 0)

            found_message = False
            for event_data in new_message_events:
                args = event_data["args"][0]
                if (
                    args["message"] == test_message
                    and args["username"] == self.user1.username
                ):
                    found_message = True
                    self.assertEqual(args["room_name"], socket_room_name)
                    self.assertEqual(args["user_id"], self.user1_id)
                    break
            self.assertTrue(found_message)

            message_in_db = ChatMessage.query.filter_by(
                room_id=room_id, user_id=self.user1_id, message=test_message
            ).first()
            self.assertIsNotNone(message_in_db)
            self.logout()

    def test_send_message_to_unjoined_room(self):
        with self.app.app_context():
            room_response = self.client.post(
                "/api/chat/rooms",
                json={"name": "Unjoined Test Room"},
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(room_response.status_code, 201)
            room_data = room_response.get_json()["chat_room"]
            room_id = room_data["id"]
            socket_room_name = f"chat_room_{room_id}"

            self.login(self.user1.username, "password")
            self.socketio_client.emit(
                "join_chat_room", {"room_name": socket_room_name}, namespace="/"
            )
            self.socketio_client.get_received()

            socketio_client_user2 = self.create_socketio_client()
            self.login(
                self.user2.username, "password", client_instance=socketio_client_user2
            )

            test_message_by_user2 = "Hello from User2 (unjoined)"
            socketio_client_user2.emit(
                "send_chat_message",
                {"room_name": socket_room_name, "message": test_message_by_user2},
                namespace="/",
            )

            time.sleep(0.1)
            received_by_user1 = self.socketio_client.get_received()
            user1_messages = [
                r for r in received_by_user1 if r["name"] == "new_chat_message"
            ]
            for event_data in user1_messages:
                args = event_data["args"][0]
                self.assertNotEqual(args["message"], test_message_by_user2)

            received_by_user2 = socketio_client_user2.get_received()
            user2_own_messages = [
                r
                for r in received_by_user2
                if r["name"] == "new_chat_message"
                and r["args"][0]["message"] == test_message_by_user2
            ]
            self.assertEqual(len(user2_own_messages), 0)

            message_in_db = ChatMessage.query.filter_by(
                room_id=room_id, user_id=self.user2_id, message=test_message_by_user2
            ).first()
            self.assertIsNone(message_in_db)

            self.logout(client_instance=socketio_client_user2)
            if self.socketio_client and self.socketio_client.is_connected():
                self.socketio_client.disconnect()
            self.logout()

    def test_chat_page_loads_for_logged_in_user(self):
        self.login(self.user1.username, "password")
        response = self.client.get("/chat")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Real-Time Chat", response.data)
        self.assertIn(b"chatRoomList", response.data)
        self.assertIn(b"messagesArea", response.data)
        self.logout()

    def test_chat_page_redirects_for_anonymous_user(self):
        response = self.client.get("/chat", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)


if __name__ == "__main__":
    unittest.main()
