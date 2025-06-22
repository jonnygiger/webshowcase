import unittest
import json
from flask_jwt_extended import create_access_token

from app import db
from models import User, ChatRoom, ChatMessage # Correctly import ChatMessage
from tests.test_base import AppTestCase # Assuming this sets up app context and db

class TestChatAPI(AppTestCase):

    def setUp(self):
        super().setUp() # Call AppTestCase.setUp
        with self.app.app_context():
            # User for authentication
            self.api_user = self._create_db_user(username="chat_api_user", password="password")
            self.access_token = create_access_token(identity=self.api_user.id)
            self.auth_headers = {"Authorization": f"Bearer {self.access_token}"}

            # Common chat room for tests
            test_room_obj = self._create_db_chat_room(name="General Chat Room", creator_id=self.api_user.id)
            self.test_room_id = test_room_obj.id # Store the ID

            # Add some messages to the room for pagination tests
            for i in range(25): # Create 25 messages
                msg = ChatMessage(
                    room_id=self.test_room_id, # Use the ID
                    user_id=self.api_user.id,
                    message=f"Message {i}"
                )
                db.session.add(msg)
            db.session.commit()

    def _create_db_chat_room(self, name, creator_id=None):
        # Helper specific to this test file, if not using one from AppTestCase or if customization is needed
        room = ChatRoom(name=name, creator_id=creator_id)
        db.session.add(room)
        db.session.commit()
        return db.session.get(ChatRoom, room.id) # Return the managed object

    def test_get_chat_room_messages_invalid_room_id(self):
        with self.app.app_context():
            invalid_room_id = 99999
            response = self.client.get(f'/api/chat/rooms/{invalid_room_id}/messages', headers=self.auth_headers)
            self.assertEqual(response.status_code, 404)
            data = response.get_json()
            self.assertIn("Chat room not found", data["message"])

    def test_get_chat_room_messages_pagination(self):
        with self.app.app_context():
            # Test first page
            response_page1 = self.client.get(f'/api/chat/rooms/{self.test_room_id}/messages?page=1&per_page=10', headers=self.auth_headers)
            self.assertEqual(response_page1.status_code, 200)
            data_page1 = response_page1.get_json()

            self.assertEqual(data_page1["room_id"], self.test_room_id)
            self.assertEqual(len(data_page1["messages"]), 10)
            self.assertEqual(data_page1["page"], 1)
            self.assertEqual(data_page1["per_page"], 10)
            self.assertEqual(data_page1["total_messages"], 25)
            self.assertEqual(data_page1["total_pages"], 3) # 25 messages, 10 per page = 3 pages

            # Messages are ordered by timestamp desc in API, so Message 24 should be first on page 1
            self.assertEqual(data_page1["messages"][0]["message"], "Message 24")

            # Test second page
            response_page2 = self.client.get(f'/api/chat/rooms/{self.test_room_id}/messages?page=2&per_page=10', headers=self.auth_headers)
            self.assertEqual(response_page2.status_code, 200)
            data_page2 = response_page2.get_json()

            self.assertEqual(len(data_page2["messages"]), 10)
            self.assertEqual(data_page2["page"], 2)
            # Message 14 should be first on page 2 (messages 24-15 on page 1, 14-5 on page 2)
            self.assertEqual(data_page2["messages"][0]["message"], "Message 14")

            # Test last page (should have remaining 5 messages)
            response_page3 = self.client.get(f'/api/chat/rooms/{self.test_room_id}/messages?page=3&per_page=10', headers=self.auth_headers)
            self.assertEqual(response_page3.status_code, 200)
            data_page3 = response_page3.get_json()

            self.assertEqual(len(data_page3["messages"]), 5)
            self.assertEqual(data_page3["page"], 3)
            # Message 4 should be first on page 3
            self.assertEqual(data_page3["messages"][0]["message"], "Message 4")

    def test_get_chat_room_messages_default_pagination(self):
        with self.app.app_context():
            # Test default pagination (per_page=20 as per API implementation)
            response = self.client.get(f'/api/chat/rooms/{self.test_room_id}/messages', headers=self.auth_headers)
            self.assertEqual(response.status_code, 200)
            data = response.get_json()

            self.assertEqual(len(data["messages"]), 20) # Default per_page is 20
            self.assertEqual(data["page"], 1)
            self.assertEqual(data["per_page"], 20)
            self.assertEqual(data["total_messages"], 25)
            self.assertEqual(data["total_pages"], 2) # 25 messages, 20 per page = 2 pages

if __name__ == "__main__":
    unittest.main()
