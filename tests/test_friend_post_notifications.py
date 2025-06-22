import unittest
from unittest.mock import patch, ANY
from datetime import datetime, timedelta

# from app import app, db, socketio # COMMENTED OUT - app, db, socketio likely from AppTestCase
from models import User, Post, FriendPostNotification, UserBlock, Friendship # Make sure these are available
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
            # _create_db_post returns the post object directly
            post1_obj_by_user1 = self._create_db_post(user_id=self.user1_id, title="Post 1 by User1", timestamp=datetime.utcnow() - timedelta(minutes=10))
            # No need to fetch again if _create_db_post returns a usable object
            # post1_by_user1 = self.db.session.get(Post, post1_obj_by_user1.id)
            self.assertIsNotNone(post1_obj_by_user1, "Post1 object by User1 should not be None.")
            # Manually create notification as if post route was hit by user1
            notif1_for_user2 = FriendPostNotification(user_id=self.user2_id, post_id=post1_obj_by_user1.id, poster_id=self.user1_id, timestamp=post1_obj_by_user1.timestamp)

            # User3 and User2 are friends. User3 posts. User2 gets another notification (newer).
            self._create_friendship(self.user3_id, self.user2_id)
            post2_obj_by_user3 = self._create_db_post(user_id=self.user3_id, title="Post 2 by User3", timestamp=datetime.utcnow() - timedelta(minutes=5))
            # post2_by_user3 = self.db.session.get(Post, post2_obj_by_user3.id)
            self.assertIsNotNone(post2_obj_by_user3, "Post2 object by User3 should not be None.")
            notif2_for_user2 = FriendPostNotification(user_id=self.user2_id, post_id=post2_obj_by_user3.id, poster_id=self.user3_id, timestamp=post2_obj_by_user3.timestamp)

            self.db.session.add_all([notif1_for_user2, notif2_for_user2])
            self.db.session.commit()

            self.login(self.user2.username, 'password')
            response = self.client.get('/friend_post_notifications')
            self.assertEqual(response.status_code, 200)
            response_data = response.get_data(as_text=True)

            self.assertIn(self.user3.username, response_data) # Poster of newer notification
            self.assertIn(post2_obj_by_user3.title, response_data)
            self.assertIn(self.user1.username, response_data) # Poster of older notification
            self.assertIn(post1_obj_by_user1.title, response_data)

            # Assert order (newer notification from user3 appears before older from user1)
            self.assertTrue(response_data.find(post2_obj_by_user3.title) < response_data.find(post1_obj_by_user1.title))
            self.logout()

    def test_mark_one_notification_as_read(self):
        with self.app.app_context():
            self._create_friendship(self.user1_id, self.user2_id)
            post_obj_by_user1 = self._create_db_post(user_id=self.user1_id)
            # post_by_user1 = self.db.session.get(Post, post_obj_by_user1.id) # Not needed if post_obj_by_user1 is used directly
            self.assertIsNotNone(post_obj_by_user1, "Post object by User1 should not be None.")
            notification = FriendPostNotification(user_id=self.user2_id, post_id=post_obj_by_user1.id, poster_id=self.user1_id, is_read=False)
            self.db.session.add(notification)
            self.db.session.commit()
            notification_id = notification.id

            self.assertFalse(self.db.session.get(FriendPostNotification, notification_id).is_read)

            # User2 (owner) marks as read
            self.login(self.user2.username, 'password')
            response = self.client.post(f'/friend_post_notifications/mark_as_read/{notification_id}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, {'status': 'success', 'message': 'Notification marked as read.'})
            self.assertTrue(self.db.session.get(FriendPostNotification, notification_id).is_read)
            self.logout()

            # User3 (not owner) tries to mark as read
            # First, set it back to unread for this part of the test
            notification_db = self.db.session.get(FriendPostNotification, notification_id)
            notification_db.is_read = False
            self.db.session.commit()
            self.assertFalse(self.db.session.get(FriendPostNotification, notification_id).is_read)

            self.login(self.user3.username, 'password')
            response = self.client.post(f'/friend_post_notifications/mark_as_read/{notification_id}')
            self.assertEqual(response.status_code, 403) # Forbidden
            self.assertEqual(response.json, {'status': 'error', 'message': 'Unauthorized.'})
            self.assertFalse(self.db.session.get(FriendPostNotification, notification_id).is_read) # Still false
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
            post1_obj = self._create_db_post(user_id=self.user1_id, title="Post1")
            post2_obj = self._create_db_post(user_id=self.user1_id, title="Post2")
            # post1 = self.db.session.get(Post, post1_obj.id) # Not needed
            # post2 = self.db.session.get(Post, post2_obj.id) # Not needed
            self.assertIsNotNone(post1_obj, "Post1 object should not be None.")
            self.assertIsNotNone(post2_obj, "Post2 object should not be None.")

            notif1 = FriendPostNotification(user_id=self.user2_id, post_id=post1_obj.id, poster_id=self.user1_id, is_read=False)
            notif2 = FriendPostNotification(user_id=self.user2_id, post_id=post2_obj.id, poster_id=self.user1_id, is_read=False)
            # Notification for another user (user3) - should not be affected
            notif_for_user3 = FriendPostNotification(user_id=self.user3_id, post_id=post1_obj.id, poster_id=self.user1_id, is_read=False)

            self.db.session.add_all([notif1, notif2, notif_for_user3])
            self.db.session.commit()
            notif1_id, notif2_id, notif3_id = notif1.id, notif2.id, notif_for_user3.id


            self.login(self.user2.username, 'password')
            response = self.client.post('/friend_post_notifications/mark_all_as_read')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, {'status': 'success', 'message': 'All friend post notifications marked as read.'})

            self.assertTrue(self.db.session.get(FriendPostNotification, notif1_id).is_read)
            self.assertTrue(self.db.session.get(FriendPostNotification, notif2_id).is_read)
            self.assertFalse(self.db.session.get(FriendPostNotification, notif3_id).is_read) # User3's notification untouched
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

    @patch('app.socketio.emit')
    def test_no_notification_for_post_before_friendship(self, mock_socketio_emit):
        with self.app.app_context():
            # 1. User1 creates a post
            post_title = "Post Before Friendship"
            post_content = "Content of post made before friendship"
            # Ensure the post is made by logging in as user1 or using a helper that handles auth
            self._make_post_via_route(self.user1.username, 'password', title=post_title, content=post_content)

            # Retrieve the created post to get its ID
            created_post = Post.query.filter_by(user_id=self.user1_id, title=post_title).first()
            self.assertIsNotNone(created_post, "Post creation failed or post not found.")

            # Store post_id for later assertions
            post_id = created_post.id

            # 2. AFTER the post is created, User1 and User2 become friends
            self._create_friendship(self.user1_id, self.user2_id, status='accepted')

            # 3. Assert that no FriendPostNotification was created for User2 for this post
            notification_for_user2 = FriendPostNotification.query.filter_by(
                user_id=self.user2_id,
                post_id=created_post.id  # or post_id variable
            ).first()
            self.assertIsNone(notification_for_user2,
                              "A notification was created for a post made before friendship.")

            # 4. Assert socketio.emit was not called for User2 for this specific post
            called_for_user2 = False
            for call_args in mock_socketio_emit.call_args_list:
                args, kwargs = call_args
                # args[0] is event name, args[1] is payload, kwargs['room'] is the room
                if args[0] == 'new_friend_post' and \
                   kwargs.get('room') == f'user_{self.user2_id}' and \
                   args[1].get('post_id') == created_post.id:
                    called_for_user2 = True
                    break
            self.assertFalse(called_for_user2,
                             "socketio.emit was called for user2 for a post made before friendship.")

    @patch('app.socketio.emit')
    def test_no_notification_if_poster_is_blocked(self, mock_socketio_emit):
        with self.app.app_context():
            # 1. User1 and User2 are friends
            self._create_friendship(self.user1_id, self.user2_id, status='accepted')

            # 2. User2 blocks User1
            user_block = UserBlock(blocker_id=self.user2_id, blocked_id=self.user1_id)
            self.db.session.add(user_block)
            self.db.session.commit()

            # 3. User1 creates a new post
            post_title = "Post By Blocked User"
            post_content = "This content should not trigger a notification for User2"
            self._make_post_via_route(self.user1.username, 'password', title=post_title, content=post_content)

            # Retrieve the post created by User1
            created_post = Post.query.filter_by(user_id=self.user1_id, title=post_title).first()
            self.assertIsNotNone(created_post, "Post creation failed or post not found.")

            # 4. Assert that no FriendPostNotification record is created in the database for User2 from User1's post
            notification_for_user2 = FriendPostNotification.query.filter_by(
                user_id=self.user2_id,
                post_id=created_post.id,
                poster_id=self.user1_id
            ).first()
            self.assertIsNone(notification_for_user2,
                              "A FriendPostNotification was created for User2 even though User1 is blocked.")

            # 5. Assert that no new_friend_post socket.io event is emitted to User2's room for this specific post
            called_for_user2 = False
            for call_args in mock_socketio_emit.call_args_list:
                args, kwargs = call_args
                # args[0] is event name, args[1] is payload, kwargs['room'] is the room
                if args[0] == 'new_friend_post' and \
                   kwargs.get('room') == f'user_{self.user2_id}' and \
                   args[1].get('post_id') == created_post.id:
                    called_for_user2 = True
                    break
            self.assertFalse(called_for_user2,
                             "socketio.emit was called for User2 for a post from a blocked user.")

    @patch('app.socketio.emit')
    def test_notification_persists_after_unfriend(self, mock_socketio_emit_unfriend):
        with self.app.app_context():
            # 1. User A (user1) and User B (user2) are friends.
            self._create_friendship(self.user1_id, self.user2_id, status='accepted')

            # 2. User A creates a new post.
            post_title = "User A's Post Before Unfriend"
            self._make_post_via_route(self.user1.username, 'password', title=post_title, content="Content relevant to this test")

            created_post = Post.query.filter_by(user_id=self.user1_id, title=post_title).first()
            self.assertIsNotNone(created_post, "Post by User A should be created.")

            # 3. Assert that a FriendPostNotification record is created for User B.
            notification_for_b = FriendPostNotification.query.filter_by(
                user_id=self.user2_id,
                post_id=created_post.id,
                poster_id=self.user1_id
            ).first()
            self.assertIsNotNone(notification_for_b, "Notification for User B should exist after User A posts.")
            self.assertFalse(notification_for_b.is_read, "Notification for User B should initially be unread.")

            # Store notification_id for later steps, if needed directly
            # self.notification_id_for_b = notification_for_b.id
            # Storing the object itself is fine too.

            # Clear any mock calls that might have occurred during post creation,
            # as we are not testing them in *this specific step*.
            # We'll be more interested in what happens *after* the unfriend action later.
            mock_socketio_emit_unfriend.reset_mock()

            # 3. User A (user1) unfriends User B (user2).
            # Find the friendship record. Note: _create_friendship likely sets status to 'accepted'.
            # We need to find it regardless of who initiated it, if it's a simple two-way record.
            # Assuming Friendship model has user_id and friend_id
            friendship_record = Friendship.query.filter(
                ((Friendship.user_id == self.user1_id) & (Friendship.friend_id == self.user2_id)) |
                ((Friendship.user_id == self.user2_id) & (Friendship.friend_id == self.user1_id)),
                Friendship.status == 'accepted' # Ensure we are targeting the active friendship
            ).first()

            self.assertIsNotNone(friendship_record, "Friendship record should exist before unfriending.")

            self.db.session.delete(friendship_record)
            self.db.session.commit()

            # Verify friendship is deleted
            deleted_friendship_record = Friendship.query.filter_by(id=friendship_record.id).first()
            self.assertIsNone(deleted_friendship_record, "Friendship record should be deleted after unfriending.")

            # 4. Assert that the FriendPostNotification for User B still exists.
            # notification_for_b was captured during the initial setup.
            # Let's refetch it from DB to ensure it wasn't cascade-deleted or altered.
            persisted_notification_for_b = self.db.session.get(FriendPostNotification, notification_for_b.id)

            self.assertIsNotNone(persisted_notification_for_b,
                                 "Notification for User B should still exist after unfriending.")

            # Verify its attributes remain correct
            self.assertEqual(persisted_notification_for_b.user_id, self.user2_id,
                             "Notification's user_id should remain unchanged.")
            self.assertEqual(persisted_notification_for_b.post_id, created_post.id,
                             "Notification's post_id should remain unchanged.")
            self.assertEqual(persisted_notification_for_b.poster_id, self.user1_id,
                             "Notification's poster_id should remain unchanged.")
            self.assertFalse(persisted_notification_for_b.is_read, # This line had a typo in the original, fixed here.
                             "Notification's is_read status should remain unchanged (false).")

            # 5. Assert SocketIO behavior post-unfriend for the original notification
            # We reset mock_socketio_emit_unfriend after the initial post.
            # Now, we ensure no *new* 'new_friend_post' event for this specific post was emitted to user2
            # during/after the unfriend action.

            called_again_for_user2 = False
            for call_args in mock_socketio_emit_unfriend.call_args_list:
                args, kwargs = call_args
                if args[0] == 'new_friend_post' and                    kwargs.get('room') == f'user_{self.user2_id}' and                    args[1].get('post_id') == created_post.id:
                    called_again_for_user2 = True
                    break
            self.assertFalse(called_again_for_user2,
                             "SocketIO should not have emitted 'new_friend_post' again for User B "
                             "for the original post after the unfriend action.")

            # End of the test method
