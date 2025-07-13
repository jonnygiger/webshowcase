from social_app import db
from social_app.models.db_models import ChatRoom, ChatMessage
from tests.test_base import AppTestCase
from flask_jwt_extended import create_access_token
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


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

    @patch("social_app.api.routes.current_app.chat_room_listeners")
    def test_sse_send_and_receive_message(self, mock_chat_room_listeners):
        with self.app.app_context():
            # 1. Create a room via API
            room_response = self.client.post(
                "/api/chat/rooms",
                json={"name": "SSE Test Room"},
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(room_response.status_code, 201)
            room_data = room_response.get_json()["chat_room"]
            room_id = room_data["id"]

            # 2. Setup mock SSE listener for this room
            mock_room_queue = MagicMock()
            # Simulate that when the room_id is looked up, our mock_queue is returned
            mock_chat_room_listeners.get.return_value = [mock_room_queue]
            # Simulate that the room_id is in the listeners
            mock_chat_room_listeners.__contains__.return_value = True

            # 3. User1 sends a message to this room via API
            test_message = "Hello from SSE test!"
            send_message_response = self.client.post(
                f"/api/chat/rooms/{room_id}/messages",
                json={"message": test_message},
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(send_message_response.status_code, 201)
            sent_message_data = send_message_response.get_json()["chat_message"]

            # 4. Verify the message was put into the mock queue for SSE dispatch
            mock_chat_room_listeners.__contains__.assert_called_with(room_id)
            mock_chat_room_listeners.get.assert_called_with(room_id)
            mock_room_queue.put_nowait.assert_called_once()

            args, _ = mock_room_queue.put_nowait.call_args
            sse_event_data = args[0]

            self.assertEqual(sse_event_data['type'], "new_chat_message")
            payload = sse_event_data['payload']
            self.assertEqual(payload['id'], sent_message_data['id'])
            self.assertEqual(payload['message'], test_message)
            self.assertEqual(payload['user_id'], self.user1_id)
            self.assertEqual(payload['username'], self.user1.username)
            self.assertEqual(payload['room_id'], room_id)

            # 5. Verify message is in DB
            message_in_db = db.session.get(ChatMessage, sent_message_data['id'])
            self.assertIsNotNone(message_in_db)
            self.assertEqual(message_in_db.message, test_message)

    @patch("social_app.api.routes.dispatch_to_chat_room_listeners")
    def test_message_delivery_to_sse_listeners(self, mock_dispatch):
        with self.app.app_context():
            # 1. User1 creates a room
            room_response = self.client.post(
                "/api/chat/rooms",
                json={"name": "SSE Listener Test Room"},
                headers={"Authorization": f"Bearer {self.user1_token}"},
            )
            self.assertEqual(room_response.status_code, 201)
            room_data = room_response.get_json()["chat_room"]
            room_id = room_data["id"]

            # 2. User2 sends a message to this room
            test_message_by_user2 = "Hello to all listeners from User2!"
            send_response = self.client.post(
                f"/api/chat/rooms/{room_id}/messages",
                json={"message": test_message_by_user2},
                headers={"Authorization": f"Bearer {self.user2_token}"},  # User2 sends
            )
            self.assertEqual(send_response.status_code, 201)
            sent_message_details = send_response.get_json()["chat_message"]

            # 3. Verify that the dispatch function was called correctly
            mock_dispatch.assert_called_once()
            args, _ = mock_dispatch.call_args

            # The first argument to dispatch_to_chat_room_listeners should be the room_id
            self.assertEqual(args[0], room_id)

            # The second argument should be the message payload
            message_payload = args[1]
            self.assertEqual(message_payload['content'], test_message_by_user2)
            self.assertEqual(message_payload['user_id'], self.user2_id)
            self.assertEqual(message_payload['username'], self.user2.username)
            self.assertEqual(message_payload['id'], sent_message_details['id'])

            # 4. Verify the message is correctly stored in the database
            message_in_db = db.session.get(ChatMessage, sent_message_details['id'])
            self.assertIsNotNone(message_in_db)
            self.assertEqual(message_in_db.message, test_message_by_user2)
            self.assertEqual(message_in_db.user_id, self.user2_id)
            self.assertEqual(message_in_db.room_id, room_id)

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
