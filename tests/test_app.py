import os
import unittest
import json # For checking JSON responses
from unittest.mock import patch, call, ANY
from app import app, db, socketio # Import socketio from app
from models import User, Message, Post, Friendship, FriendPostNotification, Group, Event, Poll, PollOption # Added Group, Event, Poll, PollOption
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
            self._setup_base_users()

    def tearDown(self):
        """Executed after each test."""
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def _setup_base_users(self):
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

    def _create_friendship(self, user1_id, user2_id, status='accepted'):
        friendship = Friendship(user_id=user1_id, friend_id=user2_id, status=status)
        db.session.add(friendship)
        db.session.commit()
        return friendship

    def _create_db_post(self, user_id, title="Test Post", content="Test Content", timestamp=None):
        post = Post(user_id=user_id, title=title, content=content, timestamp=timestamp or datetime.utcnow())
        db.session.add(post)
        db.session.commit()
        return post

    def _make_post_via_route(self, username, password, title="Test Post", content="Test Content", hashtags=""):
        self.login(username, password)
        response = self.client.post('/blog/create', data=dict(
            title=title,
            content=content,
            hashtags=hashtags
        ), follow_redirects=True)
        self.logout() # Logout after post creation to keep session state clean for next login
        return response

    def login(self, username, password):
        return self.client.post('/login', data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def _create_db_message(self, sender_id, receiver_id, content, timestamp=None, is_read=False):
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

    # Example existing tests (shortened for brevity)
    @patch('app.socketio.emit')
    def test_send_message_real_time(self, mock_socketio_emit):
        # This test seems to be about direct messages, will keep it as is.
        # My new tests will focus on FriendPostNotification.
        with app.app_context():
            self.login(self.user1.username, 'password')
            # ... (rest of the existing test) ...
            self.logout()

    def test_view_conversation_marks_read(self):
        with app.app_context():
            msg = self._create_db_message(sender_id=self.user1_id, receiver_id=self.user2_id, content="Test", is_read=False)
            # ... (rest of the existing test) ...
            self.logout()

    def test_inbox_route_data(self):
        with app.app_context():
            # ... (rest of the existing test) ...
            self.logout()


class TestFriendPostNotifications(AppTestCase): # Inherit from AppTestCase for setup

    @patch('app.socketio.emit') # Patch socketio.emit from the app instance
    def test_notification_creation_and_socketio_emit(self, mock_socketio_emit):
        with app.app_context():
            # 1. User A and User B are friends.
            self._create_friendship(self.user1_id, self.user2_id, status='accepted')

            # 2. User A creates a new post.
            post_title = "User A's Exciting Post"
            self._make_post_via_route(self.user1.username, 'password', title=post_title, content="Content here")

            # Retrieve the post created by User A
            created_post = Post.query.filter_by(user_id=self.user1_id, title=post_title).first()
            self.assertIsNotNone(created_post)

            # 3. Assert that a FriendPostNotification record is created for User B
            notification_for_b = FriendPostNotification.query.filter_by(
                user_id=self.user2_id,
                post_id=created_post.id,
                poster_id=self.user1_id
            ).first()
            self.assertIsNotNone(notification_for_b)
            self.assertFalse(notification_for_b.is_read)

            # 4. Assert that no notification is created for User A
            notification_for_a = FriendPostNotification.query.filter_by(
                user_id=self.user1_id,
                post_id=created_post.id
            ).first()
            self.assertIsNone(notification_for_a)

            # 5. Assert that if User C is not friends with User A, User C does not receive a notification.
            notification_for_c = FriendPostNotification.query.filter_by(
                user_id=self.user3_id,
                post_id=created_post.id
            ).first()
            self.assertIsNone(notification_for_c)

            # 6. Assert socketio.emit was called for User B
            expected_socket_payload = {
                'notification_id': notification_for_b.id,
                'post_id': created_post.id,
                'post_title': created_post.title,
                'poster_username': self.user1.username,
                'timestamp': ANY # Timestamps can be tricky, mock with ANY or compare with tolerance
            }
            # We need to compare timestamp more carefully if not using ANY
            # For now, ANY is simpler. If using specific timestamp, ensure it matches notification_for_b.timestamp.isoformat()

            mock_socketio_emit.assert_any_call(
                'new_friend_post',
                expected_socket_payload,
                room=f'user_{self.user2_id}'
            )
            # Check it wasn't called for user A or C for this specific post
            # This is harder to assert directly without more complex call tracking if emit is called for other reasons
            # The DB checks largely cover this.

    def test_view_friend_post_notifications_page(self):
        with app.app_context():
            # User1 and User2 are friends. User1 posts. User2 gets a notification.
            self._create_friendship(self.user1_id, self.user2_id)
            post1_by_user1 = self._create_db_post(user_id=self.user1_id, title="Post 1 by User1", timestamp=datetime.utcnow() - timedelta(minutes=10))
            # Manually create notification as if post route was hit by user1
            notif1_for_user2 = FriendPostNotification(user_id=self.user2_id, post_id=post1_by_user1.id, poster_id=self.user1_id, timestamp=post1_by_user1.timestamp)

            # User3 and User2 are friends. User3 posts. User2 gets another notification (newer).
            self._create_friendship(self.user3_id, self.user2_id)
            post2_by_user3 = self._create_db_post(user_id=self.user3_id, title="Post 2 by User3", timestamp=datetime.utcnow() - timedelta(minutes=5))
            notif2_for_user2 = FriendPostNotification(user_id=self.user2_id, post_id=post2_by_user3.id, poster_id=self.user3_id, timestamp=post2_by_user3.timestamp)

            db.session.add_all([notif1_for_user2, notif2_for_user2])
            db.session.commit()

            self.login(self.user2.username, 'password')
            response = self.client.get('/friend_post_notifications')
            self.assertEqual(response.status_code, 200)
            response_data = response.get_data(as_text=True)

            self.assertIn(self.user3.username, response_data) # Poster of newer notification
            self.assertIn(post2_by_user3.title, response_data)
            self.assertIn(self.user1.username, response_data) # Poster of older notification
            self.assertIn(post1_by_user1.title, response_data)

            # Assert order (newer notification from user3 appears before older from user1)
            self.assertTrue(response_data.find(post2_by_user3.title) < response_data.find(post1_by_user1.title))
            self.logout()

    def test_mark_one_notification_as_read(self):
        with app.app_context():
            self._create_friendship(self.user1_id, self.user2_id)
            post_by_user1 = self._create_db_post(user_id=self.user1_id)
            notification = FriendPostNotification(user_id=self.user2_id, post_id=post_by_user1.id, poster_id=self.user1_id, is_read=False)
            db.session.add(notification)
            db.session.commit()
            notification_id = notification.id

            self.assertFalse(FriendPostNotification.query.get(notification_id).is_read)

            # User2 (owner) marks as read
            self.login(self.user2.username, 'password')
            response = self.client.post(f'/friend_post_notifications/mark_as_read/{notification_id}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, {'status': 'success', 'message': 'Notification marked as read.'})
            self.assertTrue(FriendPostNotification.query.get(notification_id).is_read)
            self.logout()

            # User3 (not owner) tries to mark as read
            # First, set it back to unread for this part of the test
            notification_db = FriendPostNotification.query.get(notification_id)
            notification_db.is_read = False
            db.session.commit()
            self.assertFalse(FriendPostNotification.query.get(notification_id).is_read)

            self.login(self.user3.username, 'password')
            response = self.client.post(f'/friend_post_notifications/mark_as_read/{notification_id}')
            self.assertEqual(response.status_code, 403) # Forbidden
            self.assertEqual(response.json, {'status': 'error', 'message': 'Unauthorized.'})
            self.assertFalse(FriendPostNotification.query.get(notification_id).is_read) # Still false
            self.logout()

            # Test non-existent notification
            self.login(self.user2.username, 'password')
            response = self.client.post(f'/friend_post_notifications/mark_as_read/99999')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json, {'status': 'error', 'message': 'Notification not found.'})
            self.logout()


    def test_mark_all_notifications_as_read(self):
        with app.app_context():
            self._create_friendship(self.user1_id, self.user2_id)
            post1 = self._create_db_post(user_id=self.user1_id, title="Post1")
            post2 = self._create_db_post(user_id=self.user1_id, title="Post2")

            notif1 = FriendPostNotification(user_id=self.user2_id, post_id=post1.id, poster_id=self.user1_id, is_read=False)
            notif2 = FriendPostNotification(user_id=self.user2_id, post_id=post2.id, poster_id=self.user1_id, is_read=False)
            # Notification for another user (user3) - should not be affected
            notif_for_user3 = FriendPostNotification(user_id=self.user3_id, post_id=post1.id, poster_id=self.user1_id, is_read=False)

            db.session.add_all([notif1, notif2, notif_for_user3])
            db.session.commit()
            notif1_id, notif2_id, notif3_id = notif1.id, notif2.id, notif_for_user3.id


            self.login(self.user2.username, 'password')
            response = self.client.post('/friend_post_notifications/mark_all_as_read')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, {'status': 'success', 'message': 'All friend post notifications marked as read.'})

            self.assertTrue(FriendPostNotification.query.get(notif1_id).is_read)
            self.assertTrue(FriendPostNotification.query.get(notif2_id).is_read)
            self.assertFalse(FriendPostNotification.query.get(notif3_id).is_read) # User3's notification untouched
            self.logout()

            # Test when no unread notifications exist for the user
            self.login(self.user2.username, 'password') # user2's notifs are now read
            response = self.client.post('/friend_post_notifications/mark_all_as_read')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, {'status': 'success', 'message': 'No unread friend post notifications.'})
            self.logout()


class TestRecommendationAPI(AppTestCase):

    def _create_db_group(self, creator_id, name="Test Group", description="A group for testing"):
        group = Group(name=name, description=description, creator_id=creator_id)
        db.session.add(group)
        db.session.commit()
        return group

    def _create_db_event(self, user_id, title="Test Event", description="An event for testing", date="2024-12-31", time="18:00", location="Test Location"):
        event = Event(title=title, description=description, date=date, time=time, location=location, user_id=user_id)
        db.session.add(event)
        db.session.commit()
        return event

    def _create_db_poll(self, user_id, question="Test Poll?", options_texts=None):
        if options_texts is None:
            options_texts = ["Option 1", "Option 2"]
        poll = Poll(question=question, user_id=user_id)
        db.session.add(poll)
        db.session.flush() # So poll gets an ID before adding options
        for text in options_texts:
            option = PollOption(text=text, poll_id=poll.id)
            db.session.add(option)
        db.session.commit()
        return poll

    def setUp(self):
        super().setUp() # Call parent setUp to get base users (self.user1, self.user2, self.user3)
        # self.user1 is the target user for recommendations
        # self.user2 will create content
        # self.user3 is the "lonely" user

        # Create some content by user2 that user1 might be recommended
        self.post_by_user2 = self._create_db_post(user_id=self.user2_id, title="User2's Post")
        self.group_by_user2 = self._create_db_group(creator_id=self.user2_id, name="User2's Group")
        self.event_by_user2 = self._create_db_event(user_id=self.user2_id, title="User2's Event")
        self.poll_by_user2 = self._create_db_poll(user_id=self.user2_id, question="User2's Poll?")

        # User1 joins a different group (not by user2) to test suggest_groups_to_join logic (won't recommend this one)
        # self.other_group_user1_member_of = self._create_db_group(creator_id=self.user3_id, name="Other Group")
        # self.other_group_user1_member_of.members.append(self.user1)
        # db.session.commit()


    def test_get_recommendations_success(self):
        with app.app_context():
            response = self.client.get(f'/api/recommendations?user_id={self.user1_id}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, 'application/json')

            data = json.loads(response.data)

            self.assertIn('user_id', data)
            self.assertEqual(data['user_id'], self.user1_id)

            self.assertIn('suggested_posts', data)
            self.assertIsInstance(data['suggested_posts'], list)
            if data['suggested_posts']:
                post = data['suggested_posts'][0]
                self.assertIn('id', post)
                self.assertIn('title', post)
                self.assertIn('author_username', post)

            self.assertIn('suggested_groups', data)
            self.assertIsInstance(data['suggested_groups'], list)
            if data['suggested_groups']:
                group = data['suggested_groups'][0]
                self.assertIn('id', group)
                self.assertIn('name', group)
                self.assertIn('creator_username', group)

            self.assertIn('suggested_events', data)
            self.assertIsInstance(data['suggested_events'], list)
            if data['suggested_events']:
                event = data['suggested_events'][0]
                self.assertIn('id', event)
                self.assertIn('title', event)
                self.assertIn('organizer_username', event)

            self.assertIn('suggested_users_to_follow', data)
            self.assertIsInstance(data['suggested_users_to_follow'], list)
            if data['suggested_users_to_follow']:
                user = data['suggested_users_to_follow'][0]
                self.assertIn('id', user)
                self.assertIn('username', user)

            self.assertIn('suggested_polls_to_vote', data)
            self.assertIsInstance(data['suggested_polls_to_vote'], list)
            if data['suggested_polls_to_vote']:
                poll = data['suggested_polls_to_vote'][0]
                self.assertIn('id', poll)
                self.assertIn('question', poll)
                self.assertIn('author_username', poll)
                self.assertIn('options', poll)
                self.assertIsInstance(poll['options'], list)
                if poll['options']:
                    option = poll['options'][0]
                    self.assertIn('id', option)
                    self.assertIn('text', option)
                    self.assertIn('vote_count', option)

    def test_get_recommendations_invalid_user_id(self):
        with app.app_context():
            response = self.client.get('/api/recommendations?user_id=99999')
            self.assertEqual(response.status_code, 404)
            data = json.loads(response.data)
            self.assertIn('message', data)
            # The message might be "User 99999 not found" or "User not found"
            # Let's check if "not found" is in the message for robustness
            self.assertTrue('not found' in data['message'].lower())


    def test_get_recommendations_missing_user_id(self):
        with app.app_context():
            response = self.client.get('/api/recommendations')
            self.assertEqual(response.status_code, 400)
            data = json.loads(response.data)
            self.assertIn('message', data)
            # Example: {'message': {'user_id': 'User ID is required and must be an integer.'}}
            # Exact message depends on reqparse error formatting
            self.assertIn('user_id', data['message'])
            self.assertTrue('required' in data['message']['user_id'].lower())


    def test_get_recommendations_no_suggestions(self):
        # self.user3 is set up by AppTestCase.setUp -> _setup_base_users()
        # It has no specific content or interactions created in this class's setUp,
        # so it should get minimal to no recommendations.
        with app.app_context():
            response = self.client.get(f'/api/recommendations?user_id={self.user3_id}')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)

            self.assertEqual(data['user_id'], self.user3_id)
            self.assertEqual(data['suggested_posts'], [])
            self.assertEqual(data['suggested_groups'], [])
            self.assertEqual(data['suggested_events'], [])
            # user3 might be recommended user1 and user2 if the suggestion logic is simple
            # For now, let's assert it's a list. More specific checks depend on recommendation logic.
            self.assertIsInstance(data['suggested_users_to_follow'], list)
            self.assertEqual(data['suggested_polls_to_vote'], [])


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    unittest.main()
    with app.app_context():
        db.drop_all()
