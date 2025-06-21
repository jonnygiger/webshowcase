import unittest
from unittest.mock import (
    patch,
    call,
    ANY,
    MagicMock,
)  # Added MagicMock here as it's used in helper
from datetime import datetime, timedelta
from werkzeug.security import (
    generate_password_hash,
)  # For new user creation in one test

from app import app, db, socketio
from models import User, UserActivity, Friendship, Post
from tests.test_base import AppTestCase


# Helper to create UserActivity for tests (moved here)
def _create_db_user_activity(
    user_id,
    activity_type,
    related_id=None,
    target_user_id=None,
    content_preview=None,
    link=None,
    timestamp=None,
):
    # Ensure that 'db' and 'UserActivity' are available in the scope
    # These should be imported at the top of the file:
    # from app import db
    # from models import UserActivity

    activity = UserActivity(
        user_id=user_id,
        activity_type=activity_type,
        related_id=related_id,
        target_user_id=target_user_id,
        content_preview=content_preview,
        link=link,
        timestamp=timestamp or datetime.utcnow()
    )
    db.session.add(activity)
    db.session.commit()
    return activity


class TestLiveActivityFeed(AppTestCase):

    def setUp(self):
        super().setUp()
        # self.user1, self.user2, self.user3 are created by AppTestCase
        # These helpers require live db and models. Commented out for now.
        self._create_friendship(self.user2.id, self.user1.id, status='accepted')
        self._create_friendship(self.user2.id, self.user3.id, status='accepted')

    @patch("app.socketio.emit")
    @patch("app.check_and_award_achievements") # Mock achievements function
    def test_new_follow_activity_logging_and_socketio(self, mock_check_achievements, mock_socketio_emit):
        # User1 sends a friend request to User2
        # Ensure no pre-existing friendship that would interfere with the specific pending request for this test
        # This is important if other tests or setUp might create a direct friendship between user1 and user2
        with self.app.app_context():
            existing_friendship = Friendship.query.filter(
                ((Friendship.user_id == self.user1.id) & (Friendship.friend_id == self.user2.id)) |
                ((Friendship.user_id == self.user2.id) & (Friendship.friend_id == self.user1.id))
            ).first()
            if existing_friendship:
                db.session.delete(existing_friendship)
                db.session.commit()

            # _create_friendship now returns an ID
            friend_request_id = self._create_friendship(self.user1.id, self.user2.id, status='pending')
            self.assertIsNotNone(friend_request_id, "Failed to create pending friend request")

        # User2 logs in and accepts the friend request from User1
        self.login(self.user2.username, "password")
        response = self.client.post(f'/friend_request/{friend_request_id}/accept', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Friend request accepted successfully!", response.get_data(as_text=True))

        # Verify UserActivity creation
        # User2 (acceptor) is the one performing the 'new_follow' activity
        # User1 (requester) is the target_user
        with self.app.app_context():
            activity = UserActivity.query.filter_by(user_id=self.user2.id, activity_type='new_follow').order_by(UserActivity.timestamp.desc()).first()
            self.assertIsNotNone(activity, "UserActivity for 'new_follow' was not created.")
            # related_id for 'new_follow' is not explicitly set to the friendship or user in current app.py logic, so it would be None.
            self.assertEqual(activity.related_id, None, "related_id should be None for new_follow activity type.")
            self.assertEqual(activity.target_user_id, self.user1.id, "target_user_id is incorrect.")
            self.assertIsNotNone(activity.link, "Activity link should be set.")
            self.assertTrue(self.user1.username in activity.link, "Activity link should point to the followed user's profile.")

            # Verify emit_new_activity_event was called correctly by socketio.emit
            # emit_new_activity_event is called with the 'activity' object.
            # It then constructs a payload and emits to friends of activity.user (self.user2).

            # Friends of user2 are user3 (established in TestLiveActivityFeed.setUp).
            # User1 also becomes a friend in this test.
            # The activity is by user2. So it should be emitted to user3's room.

            # Expected payload structure (based on emit_new_activity_event in app.py)
            # Profile picture URL might vary based on actual user object or default.
            # Assuming default if no picture is set for self.user2
            user2_profile_pic = self.user2.profile_picture if self.user2.profile_picture else '/static/profile_pics/default.png'
            # If url_for is used with _external=True, it might include server name. For testing, often relative is fine or ANY for the domain.
            # For simplicity, we'll check the path part if it's default. If profile_picture is set, it's used as is.
            if not self.user2.profile_picture:
                 # In test context, url_for might behave differently. Let's use ANY for profile_picture if default.
                 # Or, more robustly, ensure user2 has a known profile_picture or mock url_for within emit_new_activity_event for this part.
                 # For now, let's assume it resolves to the default path or is ANY.
                 # To make it more predictable without complex mocking of url_for, let's check if it ends with the default path.
                 pass # We will use ANY for profile_picture path if it's default path

            expected_payload = {
                "activity_id": activity.id,
                "user_id": self.user2.id,
                "username": self.user2.username,
                "profile_picture": ANY, # Using ANY as exact URL can be tricky with _external=True and test context
                "activity_type": "new_follow",
                "related_id": None,
                "content_preview": activity.content_preview, # Should be None or empty for 'new_follow' as per current app logic
                "link": activity.link,
                "timestamp": ANY,
                "target_user_id": self.user1.id,
                "target_username": self.user1.username,
            }

            # Re-fetch user2 to ensure friend relationships are up-to-date after accepting request
            user2_updated = User.query.get(self.user2.id)
            friends_of_user2 = user2_updated.get_friends()

            emit_calls = []
            for friend_of_user2 in friends_of_user2:
                if friend_of_user2.id != self.user2.id: # Don't send to self
                    # Check if this friend is user3 (from setUp)
                    if friend_of_user2.id == self.user3.id:
                         emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user3.id}'))

            if not emit_calls:
                # This case means user2 (the actor) had no other friends to notify.
                # Given TestLiveActivityFeed.setUp creates a friendship with self.user3, this list should not be empty.
                # If user2 has no friends other than user1 (the target), then emit_new_activity_event might not make any calls.
                # Let's check if user3 is indeed a friend.
                is_user3_friend = any(f.id == self.user3.id for f in friends_of_user2)
                if not is_user3_friend:
                    print(f"Warning: User3 (ID: {self.user3.id}) was expected to be a friend of User2 (ID: {self.user2.id}) but is not.")
                    # This might indicate an issue with setUp or how get_friends() works.
                # If there are no *other* friends, then no calls are expected to 'new_activity_event' for them.
                # For this specific test, we expect user3 to be a friend from setUp.
                self.fail("Expected socketio.emit calls to user3 but no such calls were prepared.")


            mock_socketio_emit.assert_has_calls(emit_calls, any_order=True)
            # Verify that the mock_check_achievements was called (due to friendship acceptance)
            self.assertTrue(mock_check_achievements.called)
            # It should be called for self.user2 (acceptor) and self.user1 (requester)
            mock_check_achievements.assert_any_call(self.user2.id)
            mock_check_achievements.assert_any_call(self.user1.id)

        self.logout()

    def test_live_feed_unauthorized_access(self):
        response = self.client.get("/live_feed", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_live_feed_authorized_access_and_data(self):
        # user1 will log in. user2 will be their friend and have activities.
        # Ensure user1 and user2 are friends.
        # The main setUp in TestLiveActivityFeed makes user2 friends with user1.
        # So, self.user1 is friends with self.user2.

        # Create activities for user2
        with self.app.app_context():
            # Activity 1: user2 creates a post
            post_by_user2_title = "User2's Exciting Post"
            post_by_user2_content = "Content by User2 for live feed."
            post_by_user2 = Post(user_id=self.user2.id, title=post_by_user2_title, content=post_by_user2_content)
            db.session.add(post_by_user2)
            db.session.commit()
            post_by_user2_id_val = post_by_user2.id # Store ID before detaching
            post_by_user2_content_preview = post_by_user2_content[:100]

            activity1 = _create_db_user_activity(
                user_id=self.user2.id,
                activity_type="new_post",
                related_id=post_by_user2_id_val,
                content_preview=post_by_user2_content_preview,
                link=f"/blog/post/{post_by_user2_id_val}",
                timestamp=datetime.utcnow() - timedelta(minutes=10)
            )

            # Activity 2: user2 comments on a post (let's say user3's post for variety)
            post_by_user3_title = "User3's Post"
            post_by_user3_content = "A post by user3."
            post_by_user3 = Post(user_id=self.user3.id, title=post_by_user3_title, content=post_by_user3_content)
            db.session.add(post_by_user3)
            db.session.commit()
            post_by_user3_id_val = post_by_user3.id # Store ID before detaching
            comment_by_user2_content = "User2 commenting on User3's post"
            # We don't need to create a Comment model instance here for UserActivity,
            # as UserActivity for 'new_comment' primarily stores the preview and link to the post.
            activity2 = _create_db_user_activity(
                user_id=self.user2.id,
                activity_type="new_comment",
                related_id=post_by_user3_id_val, # related_id is the post commented on
                content_preview=comment_by_user2_content[:100],
                link=f"/blog/post/{post_by_user3_id_val}",
                timestamp=datetime.utcnow() - timedelta(minutes=5)
            )

            # Activity 3: user2 follows user3 (new_follow)
            # Ensure user2 and user3 are not already friends from setUp if this specific activity is key
            # However, for feed display, any activity from a friend (user2) is fine.
            # Let's assume a 'new_follow' activity where user2 followed user3.
            activity3 = _create_db_user_activity(
                user_id=self.user2.id,
                activity_type="new_follow",
                target_user_id=self.user3.id, # user2 followed user3
                link=f"/user/{self.user3.username}", # Link to target user's profile
                timestamp=datetime.utcnow() - timedelta(minutes=2)
            )

        self.login(self.user1.username, "password")
        response = self.client.get("/live_feed")
        self.assertEqual(response.status_code, 200)

        response_data = response.get_data(as_text=True)

        # Check for user2's username, as they are the actor in the activities
        self.assertIn(self.user2.username, response_data)

        # Check for content from user2's activities
        # Activity 1 (new_post)
        self.assertIn("created a new post:", response_data)
        self.assertIn(post_by_user2_content_preview, response_data)
        self.assertIn(f"/blog/post/{post_by_user2_id_val}", response_data)

        # Activity 2 (new_comment)
        self.assertIn("commented on a post:", response_data)
        # Ensure to check for HTML-escaped content if applicable
        escaped_comment_content = comment_by_user2_content[:100].replace("'", "&#39;")
        self.assertIn(escaped_comment_content, response_data)
        self.assertIn(f"/blog/post/{post_by_user3_id_val}", response_data) # Link to the commented post

        # Activity 3 (new_follow)
        self.assertIn("started following", response_data)
        # The template for 'new_follow' might say "userX started following userY"
        # The content_preview for 'new_follow' is typically None or auto-generated in the template.
        # The link should be to the target_user's profile.
        self.assertIn(f"/user/{self.user3.username}", response_data)
        # Check that the actor (user2) and target (user3) are mentioned for 'new_follow'
        # This depends on how live_feed.html renders 'new_follow'
        # A simple check for target username is good.
        self.assertIn(self.user3.username, response_data)


        # Check that an activity by user1 (self) is NOT present (unless user1 is friends with self, which is not typical)
        self_activity_post = "A post by user1 just for this check"
        with self.app.app_context():
             _create_db_user_activity(
                user_id=self.user1.id,
                activity_type="new_post",
                content_preview=self_activity_post
            )

        # Re-fetch the page after adding self-activity to ensure it's not included
        response_after_self_activity = self.client.get("/live_feed")
        response_data_after_self_activity = response_after_self_activity.get_data(as_text=True)
        self.assertNotIn(self_activity_post, response_data_after_self_activity, "User's own activities should not appear in their live feed of friends' activities.")

        self.logout()

    @patch("app.socketio.emit")
    def test_emit_new_activity_event_helper_direct(self, mock_socketio_emit):
        from app import emit_new_activity_event # Import the helper directly

        with self.app.app_context():
            # user2 is friends with user1 and user3 from TestLiveActivityFeed.setUp()
            # Create a sample activity performed by user2
            sample_post = Post(user_id=self.user2.id, title="Direct Emit Test Post", content="Content for direct emit test.")
            db.session.add(sample_post)
            db.session.commit()

            activity_by_user2 = _create_db_user_activity(
                user_id=self.user2.id,
                activity_type="new_post",
                related_id=sample_post.id,
                content_preview=sample_post.content[:100],
                link=f"/blog/post/{sample_post.id}"
            )

            # Call the helper function directly
            # The emit_new_activity_event function requires the app context to run,
            # especially for url_for and db queries if not all data is perfectly pre-loaded.
            emit_new_activity_event(activity_by_user2)

            # Verify socketio.emit was called correctly
            # Activity by user2, should be emitted to friends of user2 (user1 and user3).
            expected_payload = {
                "activity_id": activity_by_user2.id,
                "user_id": self.user2.id,
                "username": self.user2.username,
                "profile_picture": ANY, # self.user2.profile_picture or default, handled by ANY
                "activity_type": "new_post",
                "related_id": sample_post.id,
                "content_preview": sample_post.content[:100],
                "link": activity_by_user2.link,
                "timestamp": ANY, # activity_by_user2.timestamp.isoformat(),
                "target_user_id": None,
                "target_username": None,
            }

            emit_calls = []
            # user1 and user3 are friends of user2 from setUp
            if self.user1:
                 emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user1.id}'))
            if self.user3:
                 emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user3.id}'))

            self.assertTrue(len(emit_calls) > 0, "No emit calls were prepared. Check friend setup for user2.")
            mock_socketio_emit.assert_has_calls(emit_calls, any_order=True)

            # Ensure it wasn't emitted to user2 (the actor)
            for actual_call_args in mock_socketio_emit.call_args_list:
                # actual_call_args is a tuple: (args_tuple, kwargs_dict)
                kwargs_dict = actual_call_args[1] # Get the kwargs dictionary
                room_arg = kwargs_dict.get('room')
                self.assertNotEqual(room_arg, f'user_{self.user2.id}', "Activity event should not be emitted to the actor's own room.")

    @patch("app.socketio.emit")
    @patch("app.check_and_award_achievements") # Mock achievements function
    def test_new_post_activity_logging_and_socketio(self, mock_check_achievements, mock_socketio_emit):
        self.login(self.user2.username, "password")
        post_title = "My Test Post for Activity"
        post_content = "This is the content of the test post."
        post_hashtags = "test,activity"

        response = self.client.post('/blog/create', data={
            'title': post_title,
            'content': post_content,
            'hashtags': post_hashtags
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Blog post created successfully!", response.get_data(as_text=True))

        with self.app.app_context():
            # Verify UserActivity creation
            activity = UserActivity.query.filter_by(user_id=self.user2.id, activity_type='new_post').order_by(UserActivity.timestamp.desc()).first()
            self.assertIsNotNone(activity, "UserActivity for 'new_post' was not created.")

            created_post = Post.query.get(activity.related_id)
            self.assertIsNotNone(created_post, "Post referred in activity not found.")
            self.assertEqual(created_post.title, post_title)
            self.assertEqual(activity.user_id, self.user2.id)
            self.assertEqual(activity.content_preview, post_content[:100])
            self.assertTrue(f"/blog/post/{created_post.id}" in activity.link)

            # Verify socketio.emit
            # Activity is by user2. Should be emitted to friends of user2 (user1 and user3 from setUp).
            # Note: user1 and user3 are made friends with user2 in TestLiveActivityFeed.setUp
            expected_payload = {
                "activity_id": activity.id,
                "user_id": self.user2.id,
                "username": self.user2.username,
                "profile_picture": ANY,
                "activity_type": "new_post",
                "related_id": created_post.id,
                "content_preview": post_content[:100],
                "link": activity.link,
                "timestamp": ANY,
                "target_user_id": None,
                "target_username": None,
            }

            emit_calls = []
            # Friends of user2 are user1 and user3 (established in TestLiveActivityFeed.setUp)
            # self.user1 and self.user3 objects are available from AppTestCase
            if self.user1: # Check if user1 exists
                 emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user1.id}'))
            if self.user3: # Check if user3 exists
                 emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user3.id}'))

            self.assertTrue(len(emit_calls) > 0, "No emit calls were prepared. Check friend setup.")
            mock_socketio_emit.assert_has_calls(emit_calls, any_order=True)

            # Verify achievements call
            mock_check_achievements.assert_called_with(self.user2.id)

        self.logout()

    @patch("app.socketio.emit")
    @patch("app.check_and_award_achievements")
    def test_new_comment_activity_logging_and_socketio(self, mock_check_achievements, mock_socketio_emit):
        # user1 creates a post
        with self.app.app_context():
            post_by_user1_id = self._create_db_post(user_id=self.user1.id, title="Post to be commented on")
            post_by_user1 = Post.query.get(post_by_user1_id)
            self.assertIsNotNone(post_by_user1)

        # user2 logs in and comments on user1's post
        self.login(self.user2.username, "password")
        comment_content = "This is a test comment on user1's post."
        response = self.client.post(f'/blog/post/{post_by_user1.id}/comment', data={
            'comment_content': comment_content
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Comment added successfully!", response.get_data(as_text=True))

        with self.app.app_context():
            # Verify UserActivity creation by user2
            activity = UserActivity.query.filter_by(user_id=self.user2.id, activity_type='new_comment').order_by(UserActivity.timestamp.desc()).first()
            self.assertIsNotNone(activity, "UserActivity for 'new_comment' was not created.")
            self.assertEqual(activity.related_id, post_by_user1.id) # related_id is the post_id
            self.assertEqual(activity.user_id, self.user2.id)
            self.assertEqual(activity.content_preview, comment_content[:100])
            self.assertTrue(f"/blog/post/{post_by_user1.id}" in activity.link)

            # Verify socketio.emit for user2's activity
            # Activity by user2, emitted to friends of user2 (user1 and user3)
            expected_payload = {
                "activity_id": activity.id,
                "user_id": self.user2.id,
                "username": self.user2.username,
                "profile_picture": ANY,
                "activity_type": "new_comment",
                "related_id": post_by_user1.id,
                "content_preview": comment_content[:100],
                "link": activity.link,
                "timestamp": ANY,
                "target_user_id": None, # No specific target user for a comment activity in this context
                "target_username": None,
            }
            emit_calls = []
            if self.user1:
                 emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user1.id}'))
            if self.user3:
                 emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user3.id}'))

            self.assertTrue(len(emit_calls) > 0, "No emit calls were prepared for new_comment. Check friend setup.")
            mock_socketio_emit.assert_has_calls(emit_calls, any_order=True)

            # Verify achievements call for commenter (user2)
            mock_check_achievements.assert_called_with(self.user2.id)

        self.logout()

    @patch("app.socketio.emit")
    @patch("app.check_and_award_achievements") # Mock achievements, though liking doesn't trigger one by default
    def test_new_like_activity_logging_and_socketio(self, mock_check_achievements, mock_socketio_emit):
        # user1 creates a post
        with self.app.app_context():
            post_by_user1_id = self._create_db_post(user_id=self.user1.id, title="Post to be liked by user2")
            post_by_user1 = Post.query.get(post_by_user1_id)
            self.assertIsNotNone(post_by_user1)

        # user2 logs in and likes user1's post
        self.login(self.user2.username, "password")
        response = self.client.post(f'/blog/post/{post_by_user1.id}/like', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Post liked!", response.get_data(as_text=True))

        with self.app.app_context():
            # Verify UserActivity creation by user2
            activity = UserActivity.query.filter_by(user_id=self.user2.id, activity_type='new_like').order_by(UserActivity.timestamp.desc()).first()
            self.assertIsNotNone(activity, "UserActivity for 'new_like' was not created.")
            self.assertEqual(activity.related_id, post_by_user1.id) # related_id is the post_id
            self.assertEqual(activity.user_id, self.user2.id)
            # Content preview for 'new_like' is the post's content preview
            self.assertEqual(activity.content_preview, post_by_user1.content[:100] if post_by_user1.content else "")
            self.assertTrue(f"/blog/post/{post_by_user1.id}" in activity.link)

            # Verify socketio.emit for user2's activity
            # Activity by user2, emitted to friends of user2 (user1 and user3)
            expected_payload = {
                "activity_id": activity.id,
                "user_id": self.user2.id,
                "username": self.user2.username,
                "profile_picture": ANY,
                "activity_type": "new_like",
                "related_id": post_by_user1.id,
                "content_preview": activity.content_preview,
                "link": activity.link,
                "timestamp": ANY,
                "target_user_id": None,
                "target_username": None,
            }
            emit_calls = []
            if self.user1:
                 emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user1.id}'))
            if self.user3:
                 emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user3.id}'))

            self.assertTrue(len(emit_calls) > 0, "No emit calls were prepared for new_like. Check friend setup.")
            mock_socketio_emit.assert_has_calls(emit_calls, any_order=True)

            # Verify achievements call - Liking a post does NOT award achievements by default in current app logic.
            # So, mock_check_achievements should NOT have been called for this specific activity.
            # If it could be called for other reasons within the request, this assertion might need adjustment.
            # For now, assume liking itself doesn't trigger it.
            # If other actions within the POST request for liking (like notifications) *could* trigger achievements,
            # then this assertion needs refinement or the mock needs to be more specific.
            # Based on app.py, the like route itself doesn't call check_and_award_achievements.
            mock_check_achievements.assert_not_called()


        self.logout()

    def test_live_feed_empty_for_friends_with_no_activity(self):
        """Test live feed when friends have no activities."""
        # user1 logs in. user2 is their friend (established in setUp).
        # user2 (the friend) should have no activities for this test.
        # It's important to ensure no activities from user2 are created by other tests
        # or persist in a way that affects this test.
        # AppTestCase.setUp should handle DB clearing, and setUp here only creates users/friendships.

        self.login(self.user1.username, "password")
        response = self.client.get("/live_feed")
        self.assertEqual(response.status_code, 200)

        html_content = response.get_data(as_text=True)

        # 1. Check for the specific "no activity" message by its ID and text
        #    The message is: "No recent activity from your friends. Try adding more friends or check back later!"
        #    We can check for a part of the message and its ID.
        self.assertIn('id="no-activity-message"', html_content)
        self.assertIn("No recent activity from your friends", html_content)

        # 2. Assert that self.user2.username (friend with no activity) is NOT present
        #    as part of an activity item. The "no-activity-message" check is primary.
        #    If activity items had a specific class e.g. "activity-log-item",
        #    we would check for its absence or that user2.username is not within such items.
        #    For now, ensuring the "no activity" message is present is a strong indicator.
        #    A general check can be to ensure user2's name isn't followed by typical action verbs.
        #    Example: f"{self.user2.username} created a new post"
        self.assertNotIn(f"{self.user2.username} created a new post", html_content)
        self.assertNotIn(f"{self.user2.username} commented on a post", html_content)
        self.assertNotIn(f"{self.user2.username} started following", html_content)


        # 3. Ensure no activities from self.user3 are shown.
        #    self.user1 is friends with self.user2.
        #    self.user2 is friends with self.user3.
        #    self.user1 is NOT friends with self.user3 by default setup.
        #    So, self.user3's activities should not appear on self.user1's feed.
        #    (This also implicitly tests that only friends' activities are shown)
        self.assertNotIn(f"{self.user3.username} created a new post", html_content)
        self.assertNotIn(f"{self.user3.username} commented on a post", html_content)
        self.assertNotIn(f"{self.user3.username} started following", html_content)
        # Also check if any activity item container is present (e.g. if they are list items <li>)
        # This depends on the actual HTML structure. If activities are in <div class="activity-item">
        # self.assertNotIn('<div class="activity-item">', html_content) # Or similar
        # For now, the "no-activity-message" and lack of specific activity texts are the main checks.

        self.logout()

    @patch("app.socketio.emit")
    @patch("app.check_and_award_achievements")
    def test_new_share_activity_logging_and_socketio(self, mock_check_achievements, mock_socketio_emit):
        # Log in as user2 (the one who will share the post)
        self.login(self.user2.username, "password")

        # Create a post by user1 that user2 will share
        with self.app.app_context():
            original_post_title = "Original Post by User1"
            original_post_content = "This post will be shared."
            # Ensure self.user1 and self.user1_id are available from AppTestCase setup
            # If AppTestCase sets up self.user1.id directly, use that.
            # Otherwise, ensure self.user1 is committed and has an id.
            # Based on AppTestCase, self.user1 should have an id after _setup_base_users()
            post_by_user1_id = self._create_db_post(
                user_id=self.user1.id,
                title=original_post_title,
                content=original_post_content
            )
            self.assertIsNotNone(post_by_user1_id, "Failed to create original post by user1")

            # Store original post details for assertions later
            self.original_post_id = post_by_user1_id
            self.original_post_content_preview = original_post_content[:100]

        # Simulate the share action by user2
        sharing_comment_text = "Check out this cool post I found!"
        response = self.client.post(
            f'/post/{self.original_post_id}/share',
            data={'sharing_comment': sharing_comment_text},
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Post shared successfully!", response.get_data(as_text=True))

        # Store sharing comment for later assertions
        self.sharing_comment_text = sharing_comment_text

        # Verify UserActivity creation
        with self.app.app_context():
            from flask import url_for # Ensure url_for is available for direct use if needed, or rely on app context
            activity = UserActivity.query.filter_by(
                user_id=self.user2.id,
                activity_type='shared_a_post'
            ).order_by(UserActivity.timestamp.desc()).first()

            self.assertIsNotNone(activity, "UserActivity for 'shared_a_post' was not created.")
            self.assertEqual(activity.user_id, self.user2.id, "Activity user_id is incorrect.")
            self.assertEqual(activity.related_id, self.original_post_id, "Activity related_id (original post ID) is incorrect.")
            # The content_preview in app.py for 'shared_a_post' uses the sharing comment.
            self.assertEqual(activity.content_preview, self.sharing_comment_text[:100], "Activity content_preview is incorrect.")

            # Construct expected link using url_for, similar to how it's done in app.py
            # This requires the app context, which is already active here.
            expected_link = url_for('view_post', post_id=self.original_post_id, _external=True)
            self.assertEqual(activity.link, expected_link, "Activity link is incorrect.")

            # Store activity_id for SocketIO verification if needed
            self.activity_id = activity.id

        # Verify SocketIO event emission
        # The activity was performed by self.user2.
        # Friends of self.user2 are self.user1 and self.user3 (from TestLiveActivityFeed.setUp).
        # The emit_new_activity_event helper in app.py will fetch user2's profile picture.
        # We use ANY for profile_picture and timestamp due to potential variations.

        # Ensure self.activity_id was set in the UserActivity verification step
        self.assertTrue(hasattr(self, 'activity_id'), "activity_id was not set from UserActivity verification.")

        # Construct expected link again, or retrieve if stored on self from previous step.
        # For safety, let's reconstruct or ensure it's available.
        # Assuming self.original_post_id is correctly set.
        with self.app.app_context(): # url_for needs app context
            from flask import url_for # Ensure url_for is available
            expected_activity_link = url_for('view_post', post_id=self.original_post_id, _external=True)

        expected_payload = {
            "activity_id": self.activity_id, # From previous verification step
            "user_id": self.user2.id,
            "username": self.user2.username,
            "profile_picture": ANY,  # Using ANY as exact URL can be tricky with _external=True and test context
            "activity_type": "shared_a_post",
            "related_id": self.original_post_id, # ID of the original post
            "content_preview": self.sharing_comment_text[:100], # The comment made during sharing
            "link": expected_activity_link,
            "timestamp": ANY,
            "target_user_id": None, # No specific target user for 'shared_a_post' in this context
            "target_username": None,
        }

        # user1 and user3 are friends of user2 from TestLiveActivityFeed.setUp()
        # The AppTestCase creates self.user1, self.user2, self.user3
        emit_calls = []
        if self.user1: # Friend 1
            emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user1.id}'))
        if self.user3: # Friend 2
            emit_calls.append(call('new_activity_event', expected_payload, room=f'user_{self.user3.id}'))

        self.assertTrue(len(emit_calls) > 0, "No emit calls were prepared. Check friend setup for user2.")

        # Check if mock_socketio_emit was called
        # print(f"DEBUG: mock_socketio_emit.call_args_list: {mock_socketio_emit.call_args_list}")
        # print(f"DEBUG: Expected calls: {emit_calls}")

        mock_socketio_emit.assert_has_calls(emit_calls, any_order=True)

        # Ensure it wasn't emitted to self.user2 (the actor)
        for actual_call_args in mock_socketio_emit.call_args_list:
            kwargs_dict = actual_call_args[1] # Get the kwargs dictionary
            room_arg = kwargs_dict.get('room')
            # Check that the room is not the actor's room, AND that the event is 'new_activity_event'
            # (to avoid issues if other socket events are emitted for other reasons)
            if actual_call_args[0][0] == 'new_activity_event': # Check if the event name is 'new_activity_event'
                self.assertNotEqual(room_arg, f'user_{self.user2.id}',
                                    "Activity event should not be emitted to the actor's own room.")
        # TODO: Verify achievement checks (if applicable)

        self.logout() # Ensure logout at the end
