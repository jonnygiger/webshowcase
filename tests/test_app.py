import os
import unittest
from unittest.mock import patch, call, ANY
from app import app, db, socketio # Import socketio from app
from models import User, Message, Post # Add other models as needed
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

class AppTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Configuration that applies to the entire test class
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SECRET_KEY'] = 'test-secret-key'
        # To prevent real socketio connections during tests if not using test_client's context
        # However, for `socketio.emit` testing, we often mock it anyway.
        # app.config['SOCKETIO_MESSAGE_QUEUE'] = None


    def setUp(self):
        """Set up for each test."""
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            self._create_test_users() # Renamed to avoid conflict if TestCase has create_test_users

    def tearDown(self):
        """Executed after each test."""
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def _create_test_users(self): # Renamed
        # Using instance variables for user objects to make them accessible in tests
        self.user1 = User(username='testuser1', email='test1@example.com', password_hash=generate_password_hash('password'))
        self.user2 = User(username='testuser2', email='test2@example.com', password_hash=generate_password_hash('password'))
        self.user3 = User(username='testuser3', email='test3@example.com', password_hash=generate_password_hash('password'))
        db.session.add_all([self.user1, self.user2, self.user3])
        db.session.commit()
        # Store IDs for later use, helpful if objects become detached or for clarity
        self.user1_id = self.user1.id
        self.user2_id = self.user2.id
        self.user3_id = self.user3.id


    def login(self, username, password):
        return self.client.post('/login', data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def _create_message(self, sender_id, receiver_id, content, timestamp=None, is_read=False): # Renamed
        # This helper now operates within an app_context implicitly if called from a test method that has it.
        # If called from setUpClass or outside a request context, ensure app_context.
        msg = Message(
            sender_id=sender_id,
            receiver_id=receiver_id,
            content=content,
            timestamp=timestamp or datetime.utcnow(),
            is_read=is_read
        )
        db.session.add(msg)
        db.session.commit()
        return msg

    # 1. Test `send_message` Route and SocketIO Emissions
    @patch('app.socketio.emit') # Correctly patching app.socketio.emit
    def test_send_message_real_time(self, mock_socketio_emit):
        with app.app_context(): # Ensure all DB operations and app context needs are met
            self.login(self.user1.username, 'password')
            message_content = "Hello from user1 to user2 in real-time!"

            response = self.client.post(f'/messages/send/{self.user2.username}', data={
                'content': message_content
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)

            msg_from_db = Message.query.filter_by(sender_id=self.user1_id, receiver_id=self.user2_id, content=message_content).first()
            self.assertIsNotNone(msg_from_db)
            self.assertEqual(msg_from_db.content, message_content)

            # Timestamp from the saved message for more accurate comparison
            saved_timestamp_str = msg_from_db.timestamp.strftime("%Y-%m-%d %H:%M:%S")

            expected_direct_message_payload = {
                'id': msg_from_db.id,
                'sender_id': self.user1_id,
                'receiver_id': self.user2_id,
                'content': message_content,
                'timestamp': saved_timestamp_str,
                'sender_username': self.user1.username
            }

            expected_snippet = (message_content[:30] + '...') if len(message_content) > 30 else message_content
            expected_inbox_payload = {
                'sender_id': self.user1_id,
                'sender_username': self.user1.username,
                'message_snippet': expected_snippet,
                'timestamp': saved_timestamp_str,
                'unread_count': 1,
                'conversation_partner_id': self.user1_id,
                'conversation_partner_username': self.user1.username
            }

            # Check calls
            found_direct_message = False
            found_inbox_notification = False

            for actual_call in mock_socketio_emit.call_args_list:
                args, kwargs = actual_call
                event_name = args[0]
                payload = args[1]
                room = kwargs.get('room')

                if event_name == 'new_direct_message' and room == f'user_{self.user2_id}':
                    self.assertEqual(payload, expected_direct_message_payload)
                    found_direct_message = True
                elif event_name == 'update_inbox_notification' and room == f'user_{self.user2_id}':
                    self.assertEqual(payload, expected_inbox_payload)
                    found_inbox_notification = True

            self.assertTrue(found_direct_message, "new_direct_message event was not emitted correctly or with the correct payload.")
            self.assertTrue(found_inbox_notification, "update_inbox_notification event was not emitted correctly or with the correct payload.")

            self.logout()

    # 2. Test `view_conversation` Marks Messages as Read
    def test_view_conversation_marks_read(self):
        with app.app_context():
            message_content = "Test message to be marked as read"
            # Use the helper, ensuring it's within app_context
            msg = self._create_message(sender_id=self.user1_id, receiver_id=self.user2_id, content=message_content, is_read=False)
            self.assertFalse(msg.is_read)

            self.login(self.user2.username, 'password')
            self.client.get(f'/messages/conversation/{self.user1.username}')

            # Re-fetch from DB to get updated state
            updated_msg = Message.query.get(msg.id)
            self.assertTrue(updated_msg.is_read)

            self.logout()

    # 3. Test `inbox` Route Data Preparation
    def test_inbox_route_data(self):
        with app.app_context():
            # User1 sends 2 messages to User2
            # Timestamps are important for sorting and for verifying last_message logic
            time_now = datetime.utcnow()
            msg1_u1_to_u2 = self._create_message(self.user1_id, self.user2_id, "Old Message from User1 to User2", timestamp=time_now - timedelta(minutes=10))
            msg2_u1_to_u2 = self._create_message(self.user1_id, self.user2_id, "Latest Unread from User1 to User2", is_read=False, timestamp=time_now - timedelta(minutes=5))

            # User3 sends 1 message to User2
            msg1_u3_to_u2 = self._create_message(self.user3_id, self.user2_id, "Unread from User3 to User2", is_read=False, timestamp=time_now - timedelta(minutes=2))

            # User2 sends 1 message to User1 (should not affect User2's unread count from User1 for User2's inbox)
            self._create_message(self.user2_id, self.user1_id, "Reply from User2 to User1", timestamp=time_now - timedelta(minutes=1))

            self.login(self.user2.username, 'password')
            response = self.client.get('/messages/inbox')
            self.assertEqual(response.status_code, 200)

            response_data = response.get_data(as_text=True)

            # Check User1's conversation details (partner_id = self.user1_id)
            # Last message from User1 is msg2_u1_to_u2
            self.assertIn(f"id=\"inbox-item-{self.user1_id}\"", response_data)
            expected_snippet_u1 = (msg2_u1_to_u2.content[:50] + "...") if len(msg2_u1_to_u2.content) > 50 else msg2_u1_to_u2.content
            self.assertIn(f'<p id="snippet-{self.user1_id}" class="mb-1">{expected_snippet_u1}</p>', response_data)
            self.assertIn(f'<small id="timestamp-{self.user1_id}">{msg2_u1_to_u2.timestamp.strftime("%Y-%m-%d %H:%M:%S")}</small>', response_data)
            # User2 has 1 unread message from User1
            self.assertIn(f'<span id="unread-count-{self.user1_id}" class="badge rounded-pill bg-danger">1</span>', response_data)


            # Check User3's conversation details (partner_id = self.user3_id)
            # Last message from User3 is msg1_u3_to_u2
            self.assertIn(f"id=\"inbox-item-{self.user3_id}\"", response_data)
            expected_snippet_u3 = (msg1_u3_to_u2.content[:50] + "...") if len(msg1_u3_to_u2.content) > 50 else msg1_u3_to_u2.content
            self.assertIn(f'<p id="snippet-{self.user3_id}" class="mb-1">{expected_snippet_u3}</p>', response_data)
            self.assertIn(f'<small id="timestamp-{self.user3_id}">{msg1_u3_to_u2.timestamp.strftime("%Y-%m-%d %H:%M:%S")}</small>', response_data)
            # User2 has 1 unread message from User3
            self.assertIn(f'<span id="unread-count-{self.user3_id}" class="badge rounded-pill bg-danger">1</span>', response_data)

            # Ensure items are sorted by last message timestamp (User3's message is latest)
            pos_user3_item = response_data.find(f"id=\"inbox-item-{self.user3_id}\"")
            pos_user1_item = response_data.find(f"id=\"inbox-item-{self.user1_id}\"")
            self.assertTrue(pos_user3_item >= 0 and pos_user1_item >= 0, "Inbox items not found in response")
            self.assertTrue(pos_user3_item < pos_user1_item, "Inbox items are not sorted correctly (latest first)")

            self.logout()

if __name__ == '__main__':
    with app.app_context(): # Ensure app context for initial setup if any test runner needs it outside of class/method setup
        db.create_all() # Though typically handled by setUp/setUpClass
    unittest.main()
    with app.app_context(): # Cleanup after tests if run directly
        db.drop_all()
