from social_app import db
from social_app.models.db_models import ChatRoom, ChatMessage
from tests.test_base import AppTestCase
from flask_jwt_extended import create_access_token
from datetime import datetime, timezone


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
            self.assertEqual(data["messages"][0]["content"], "Hello from user1")
            self.assertEqual(data["messages"][0]["user_id"], self.user1_id)


if __name__ == "__main__":
    unittest.main()
