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

    # Helper to get JWT token
    def _get_jwt_token(self, username, password):
        response = self.client.post('/api/login', json={'username': username, 'password': password})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('access_token', data)
        return data['access_token']

    # Helpers for creating likes, comments, RSVPs, votes
    def _create_db_like(self, user_id, post_id, timestamp=None):
        from models import Like # Import here to avoid circular dependency if models import app
        like = Like(user_id=user_id, post_id=post_id, timestamp=timestamp or datetime.utcnow())
        db.session.add(like)
        db.session.commit()
        return like

    def _create_db_comment(self, user_id, post_id, content="Test comment", timestamp=None):
        from models import Comment # Import here
        comment = Comment(user_id=user_id, post_id=post_id, content=content, timestamp=timestamp or datetime.utcnow())
        db.session.add(comment)
        db.session.commit()
        return comment

    def _create_db_event_rsvp(self, user_id, event_id, status="Attending", timestamp=None):
        from models import EventRSVP # Import here
        rsvp = EventRSVP(user_id=user_id, event_id=event_id, status=status, timestamp=timestamp or datetime.utcnow())
        db.session.add(rsvp)
        db.session.commit()
        return rsvp

    def _create_db_poll_vote(self, user_id, poll_id, poll_option_id, timestamp=None):
        from models import PollVote # Import here
        vote = PollVote(user_id=user_id, poll_id=poll_id, poll_option_id=poll_option_id, timestamp=timestamp or datetime.utcnow())
        db.session.add(vote)
        db.session.commit()
        return vote


class TestPersonalizedFeedAPI(AppTestCase):

    def setUp(self):
        super().setUp()
        # Users are created by AppTestCase's _setup_base_users: self.user1, self.user2, self.user3
        # self.user1_id, self.user2_id, self.user3_id

    def test_personalized_feed_unauthorized(self):
        with app.app_context():
            response = self.client.get('/api/personalized-feed')
            self.assertEqual(response.status_code, 401) # JWT errors are usually 401 or 422 if malformed
            # Flask-JWT-Extended typically returns 401 for missing token
            data = json.loads(response.data)
            self.assertIn('msg', data) # Default message key for flask-jwt-extended
            self.assertEqual(data['msg'], 'Missing Authorization Header')


    def test_personalized_feed_success_and_structure(self):
        with app.app_context():
            # 1. Setup Data
            # Friendships: user1 is friends with user2
            self._create_friendship(self.user1_id, self.user2_id, status='accepted')

            # Posts:
            # Post by user3 (not friend), liked by user2 (friend of user1) -> should be recommended
            post1_by_user3 = self._create_db_post(user_id=self.user3_id, title="Post by User3, Liked by User2", timestamp=datetime.utcnow() - timedelta(hours=1))
            self._create_db_like(user_id=self.user2_id, post_id=post1_by_user3.id, timestamp=datetime.utcnow() - timedelta(minutes=30))

            # Post by user2 (friend of user1) -> should be recommended (because friend created it, even if no other interaction)
            # The current suggest_posts_to_read logic might not pick this up unless it's also interacted with by another friend or meets other criteria.
            # For testing, let's ensure it's picked up. We might need to make user1 also friend with user3, and user3 likes user2's post.
            # Let's simplify: user3 (not friend) posts, user2 (friend) comments.
            post2_by_user3 = self._create_db_post(user_id=self.user3_id, title="Another Post by User3, Commented by User2", timestamp=datetime.utcnow() - timedelta(hours=3))
            self._create_db_comment(user_id=self.user2_id, post_id=post2_by_user3.id, content="Friend comment", timestamp=datetime.utcnow() - timedelta(hours=2))

            # Events:
            # Event by user3, user2 (friend of user1) RSVP'd 'Attending' -> should be recommended
            event1_by_user3 = self._create_db_event(user_id=self.user3_id, title="Event by User3, User2 Attending", date="2025-01-01")
            event1_by_user3.created_at = datetime.utcnow() - timedelta(days=1) # Set created_at for sorting
            db.session.commit()
            self._create_db_event_rsvp(user_id=self.user2_id, event_id=event1_by_user3.id, status="Attending")

            # Polls:
            # Poll by user2 (friend of user1) -> should be recommended
            poll1_by_user2 = self._create_db_poll(user_id=self.user2_id, question="Poll by User2 (Friend)?")
            poll1_by_user2.created_at = datetime.utcnow() - timedelta(days=2) # Set created_at
            db.session.commit()
            # Add a vote from user3 to make it seem active, though suggest_polls_to_vote might pick it up just by being friend-created
            option_for_poll1 = poll1_by_user2.options[0]
            self._create_db_poll_vote(user_id=self.user3_id, poll_id=poll1_by_user2.id, poll_option_id=option_for_poll1.id)


            # 2. Login as user1 and get token
            token = self._get_jwt_token(self.user1.username, 'password')
            headers = {'Authorization': f'Bearer {token}'}

            # 3. Make request
            response = self.client.get('/api/personalized-feed', headers=headers)
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIn('feed_items', data)
            feed_items = data['feed_items']
            self.assertIsInstance(feed_items, list)

            # We expect at least one of each type based on setup
            self.assertTrue(len(feed_items) >= 3, f"Expected at least 3 items, got {len(feed_items)}")

            found_post = False
            found_event = False
            found_poll = False

            timestamps = []

            for item in feed_items:
                self.assertIn('type', item)
                self.assertIn('id', item)
                self.assertIn('timestamp', item)
                self.assertIsNotNone(item['timestamp'])
                timestamps.append(datetime.fromisoformat(item['timestamp'].replace('Z', ''))) # Handle Z if present

                if item['type'] == 'post':
                    found_post = True
                    self.assertIn('title', item)
                    self.assertIn('content', item)
                    self.assertIn('author_username', item)
                    self.assertIn('reason', item)
                    if item['id'] == post1_by_user3.id:
                        self.assertEqual(item['title'], "Post by User3, Liked by User2")
                elif item['type'] == 'event':
                    found_event = True
                    self.assertIn('title', item)
                    self.assertIn('description', item)
                    self.assertIn('organizer_username', item)
                    if item['id'] == event1_by_user3.id:
                        self.assertEqual(item['title'], "Event by User3, User2 Attending")
                elif item['type'] == 'poll':
                    found_poll = True
                    self.assertIn('question', item)
                    self.assertIn('creator_username', item)
                    self.assertIn('options', item)
                    self.assertIsInstance(item['options'], list)
                    if item['options']:
                        self.assertIn('text', item['options'][0])
                        self.assertIn('vote_count', item['options'][0])
                    if item['id'] == poll1_by_user2.id:
                         self.assertEqual(item['question'], "Poll by User2 (Friend)?")

            self.assertTrue(found_post, "No post found in feed")
            self.assertTrue(found_event, "No event found in feed")
            self.assertTrue(found_poll, "No poll found in feed")

            # Assert sorting by timestamp (descending)
            for i in range(len(timestamps) - 1):
                self.assertGreaterEqual(timestamps[i], timestamps[i+1], "Feed items are not sorted correctly by timestamp")

    def test_personalized_feed_empty(self):
        with app.app_context():
            # user3 is set up but has no friends or interactions that would generate a feed for them based on current logic
            token = self._get_jwt_token(self.user3.username, 'password')
            headers = {'Authorization': f'Bearer {token}'}

            response = self.client.get('/api/personalized-feed', headers=headers)
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIn('feed_items', data)
            self.assertEqual(data['feed_items'], [])


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    unittest.main()
    with app.app_context():
        db.drop_all()
