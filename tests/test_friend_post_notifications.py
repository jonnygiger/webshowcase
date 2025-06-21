import unittest
from unittest.mock import patch, ANY
from datetime import datetime, timedelta

# from app import app, db, socketio # COMMENTED OUT - app, db, socketio likely from AppTestCase
from models import User, Post, FriendPostNotification # Make sure these are available
from tests.test_base import AppTestCase


class TestFriendPostNotifications(AppTestCase):  # Inherit from AppTestCase for setup

    @patch('app.socketio.emit') # Patch socketio.emit from the app instance
    def test_notification_creation_and_socketio_emit(self, mock_socketio_emit):
        with self.app.app_context():
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
        with self.app.app_context():
            # User1 and User2 are friends. User1 posts. User2 gets a notification.
            self._create_friendship(self.user1_id, self.user2_id)
            post1_id_by_user1 = self._create_db_post(user_id=self.user1_id, title="Post 1 by User1", timestamp=datetime.utcnow() - timedelta(minutes=10))
            post1_by_user1 = db.session.get(Post, post1_id_by_user1)
            # Manually create notification as if post route was hit by user1
            notif1_for_user2 = FriendPostNotification(user_id=self.user2_id, post_id=post1_by_user1.id, poster_id=self.user1_id, timestamp=post1_by_user1.timestamp)

            # User3 and User2 are friends. User3 posts. User2 gets another notification (newer).
            self._create_friendship(self.user3_id, self.user2_id)
            post2_id_by_user3 = self._create_db_post(user_id=self.user3_id, title="Post 2 by User3", timestamp=datetime.utcnow() - timedelta(minutes=5))
            post2_by_user3 = db.session.get(Post, post2_id_by_user3)
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
        with self.app.app_context():
            self._create_friendship(self.user1_id, self.user2_id)
            post_id_by_user1 = self._create_db_post(user_id=self.user1_id)
            post_by_user1 = db.session.get(Post, post_id_by_user1)
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
        with self.app.app_context():
            self._create_friendship(self.user1_id, self.user2_id)
            post1_id = self._create_db_post(user_id=self.user1_id, title="Post1")
            post2_id = self._create_db_post(user_id=self.user1_id, title="Post2")
            post1 = db.session.get(Post, post1_id)
            post2 = db.session.get(Post, post2_id)

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

    @patch('app.socketio.emit')
    def test_no_notification_for_own_post(self, mock_socketio_emit):
        with self.app.app_context():
            # 1. User1 creates a post
            post_title = "My Own Test Post"
            post_content = "This is content of my own post."
            self._make_post_via_route(self.user1.username, 'password', title=post_title, content=post_content)

            # 2. Retrieve the created post
            created_post = Post.query.filter_by(user_id=self.user1_id, title=post_title).first()
            self.assertIsNotNone(created_post, "Post creation failed or post not found.")

            # 3. Assert no FriendPostNotification was created for user1 for this post
            notification_for_self = FriendPostNotification.query.filter_by(
                user_id=self.user1_id,
                post_id=created_post.id
            ).first()
            self.assertIsNone(notification_for_self, "A notification was created for user's own post.")

            # 4. Assert socketio.emit was not called for user1's room for 'new_friend_post'
            # Check if emit was called at all. If it was, check its arguments.
            for call in mock_socketio_emit.call_args_list:
                event_name, payload, room = call[0] # call[0] contains args
                if event_name == 'new_friend_post' and room == f'user_{self.user1_id}':
                    # Check if the post_id in payload matches our created_post.id
                    # This is important if other posts by friends could trigger notifications in the same test session
                    if 'post_id' in payload and payload['post_id'] == created_post.id:
                        self.fail(f"socketio.emit called for user's own post: event={event_name}, room={room}, payload={payload}")
            # A simpler check if no other socketio events are expected for this user during this specific action:
            # mock_socketio_emit.assert_not_called() might be too broad if other calls are permissible.
            # The loop above is more specific.

            # If we are certain that NO emit should happen for user1 related to *this post notification*,
            # and other emits are possible (e.g. other notifications for other users, general app events),
            # the loop is the most robust way.
            # If this test is isolated and no other socket events are expected for self.user1,
            # we could check that no call has room=f'user_{self.user1_id}' and event='new_friend_post'
            # for the specific post.

            # Let's refine the socketio assertion to be very specific:
            # No call to emit for 'new_friend_post' to user1's room for this specific post.
            called_for_own_post = False
            for call_args in mock_socketio_emit.call_args_list:
                args, kwargs = call_args
                # args[0] is event name, args[1] is payload, kwargs['room'] is the room
                if args[0] == 'new_friend_post' and \
                   kwargs.get('room') == f'user_{self.user1_id}' and \
                   args[1].get('post_id') == created_post.id:
                    called_for_own_post = True
                    break
            self.assertFalse(called_for_own_post, "socketio.emit was called for the user's own post notification.")
