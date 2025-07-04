import unittest
from datetime import datetime, timezone
from app import db
from models import User, ChatRoom, ChatMessage
from tests.test_base import AppTestCase


class TestChatModel(AppTestCase):

    def test_chat_room_repr(self):
        with self.app.app_context():
            room = ChatRoom(name="Chat Room Repr Test")
            db.session.add(room)
            db.session.commit()
            self.assertEqual(repr(room), "<ChatRoom Chat Room Repr Test>")

    def test_chat_message_repr(self):
        with self.app.app_context():
            user = self._create_db_user(username="chat_msg_user_repr")
            room = self._create_db_chat_room(
                name="Chat Msg Repr Room", creator_id=user.id
            )

            msg_time = datetime.now(timezone.utc)
            msg = ChatMessage(
                room_id=room.id,
                user_id=user.id,
                message="Hello repr world",
                timestamp=msg_time,
            )
            db.session.add(msg)
            db.session.commit()
            # The repr includes the timestamp, which can be tricky for exact match.
            # We'll check the static parts.
            self.assertTrue(
                repr(msg).startswith(
                    f"<ChatMessage User {user.id} in Room {room.id} at"
                )
            )

    def test_chat_message_to_dict(self):
        with self.app.app_context():
            user = self._create_db_user(username="chat_msg_user_dict")
            room = self._create_db_chat_room(
                name="Chat Msg Dict Room", creator_id=user.id
            )

            msg_content = "This is a test message for to_dict."
            msg_time = datetime.now(timezone.utc)  # Approximate

            chat_msg = ChatMessage(
                room_id=room.id,
                user_id=user.id,
                message=msg_content,
                timestamp=msg_time,
            )
            db.session.add(chat_msg)
            db.session.commit()

            # Re-fetch to ensure all attributes are loaded correctly
            fetched_msg = db.session.get(ChatMessage, chat_msg.id)

            expected_dict = {
                "id": fetched_msg.id,
                "room_id": room.id,
                "user_id": user.id,
                "username": user.username,
                "message": msg_content,
                "timestamp": fetched_msg.timestamp.isoformat(),  # Use actual DB value
            }
            self.assertDictEqual(fetched_msg.to_dict(), expected_dict)

    def _create_db_chat_room(self, name, creator_id=None):
        # Helper to create chat rooms consistently for chat model tests
        room = ChatRoom(name=name, creator_id=creator_id)
        db.session.add(room)
        db.session.commit()
        return db.session.get(ChatRoom, room.id)


if __name__ == "__main__":
    unittest.main()
