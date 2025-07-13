import unittest
import json
from flask_jwt_extended import create_access_token

from social_app import db
from social_app.models.db_models import User, ChatRoom, ChatMessage
from tests.test_base import AppTestCase
from datetime import datetime


class TestChatAPI(AppTestCase):

    def setUp(self):
        super().setUp()
        with self.app.app_context():
            self.api_user = self._create_db_user(
                username="chat_api_user", password="password"
            )
            self.access_token = create_access_token(identity=str(self.api_user.id))
            self.auth_headers = {"Authorization": f"Bearer {self.access_token}"}

            test_room_obj = self._create_db_chat_room(
                name="General Chat Room", creator_id=self.api_user.id
            )
            self.test_room_id = test_room_obj.id

            for i in range(25):
                msg = ChatMessage(
                    room_id=self.test_room_id,
                    user_id=self.api_user.id,
                    message=f"Message {i}",
                )
                db.session.add(msg)
            db.session.commit()

    def _create_db_chat_room(self, name, creator_id=None):
        room = ChatRoom(name=name, creator_id=creator_id)
        db.session.add(room)
        db.session.commit()
        return db.session.get(ChatRoom, room.id)

    def test_get_chat_room_messages_invalid_room_id(self):
        with self.app.app_context():
            invalid_room_id = 99999
            response = self.client.get(
                f"/api/chat/rooms/{invalid_room_id}/messages", headers=self.auth_headers
            )
            self.assertEqual(response.status_code, 404)
            data = response.get_json()
            self.assertIn("Chat room not found", data["message"])

    def test_get_chat_room_messages_pagination(self):
        with self.app.app_context():
            response_page1 = self.client.get(
                f"/api/chat/rooms/{self.test_room_id}/messages?page=1&per_page=10",
                headers=self.auth_headers,
            )
            self.assertEqual(response_page1.status_code, 200)
            data_page1 = response_page1.get_json()

            self.assertEqual(data_page1["room_id"], self.test_room_id)
            self.assertEqual(len(data_page1["messages"]), 10)
            self.assertEqual(data_page1["page"], 1)
            self.assertEqual(data_page1["per_page"], 10)
            self.assertEqual(data_page1["total_messages"], 25)
            self.assertEqual(data_page1["total_pages"], 3)
            self.assertEqual(data_page1["messages"][0]["message"], "Message 24")

            response_page2 = self.client.get(
                f"/api/chat/rooms/{self.test_room_id}/messages?page=2&per_page=10",
                headers=self.auth_headers,
            )
            self.assertEqual(response_page2.status_code, 200)
            data_page2 = response_page2.get_json()

            self.assertEqual(len(data_page2["messages"]), 10)
            self.assertEqual(data_page2["page"], 2)
            self.assertEqual(data_page2["messages"][0]["message"], "Message 14")

            response_page3 = self.client.get(
                f"/api/chat/rooms/{self.test_room_id}/messages?page=3&per_page=10",
                headers=self.auth_headers,
            )
            self.assertEqual(response_page3.status_code, 200)
            data_page3 = response_page3.get_json()

            self.assertEqual(len(data_page3["messages"]), 5)
            self.assertEqual(data_page3["page"], 3)
            self.assertEqual(data_page3["messages"][0]["message"], "Message 4")

    def test_get_chat_room_messages_default_pagination(self):
        with self.app.app_context():
            response = self.client.get(
                f"/api/chat/rooms/{self.test_room_id}/messages",
                headers=self.auth_headers,
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()

            self.assertEqual(len(data["messages"]), 20)
            self.assertEqual(data["page"], 1)
            self.assertEqual(data["per_page"], 20)
            self.assertEqual(data["total_messages"], 25)
            self.assertEqual(data["total_pages"], 2)


if __name__ == "__main__":
    unittest.main()
