import unittest
import json
from unittest.mock import (
    patch,
    ANY,
)  # Kept patch and ANY for potential future use or AppTestCase interactions
from datetime import datetime, timedelta, timezone

# from app import app, db, socketio # COMMENTED OUT
from models import Friendship  # Ensure Friendship is imported

# from models import User, Post, Event, Poll, PollOption, Like, Comment, EventRSVP, PollVote # COMMENTED OUT - Added Friendship, PollOption
from tests.test_base import AppTestCase


class TestPersonalizedFeedAPI(AppTestCase):

    def setUp(self):
        super().setUp()
        # Users are created by AppTestCase's _setup_base_users: self.user1, self.user2, self.user3
        # self.user1_id, self.user2_id, self.user3_id

    def test_personalized_feed_unauthorized(self):
        # with app.app_context(): # Context likely handled by AppTestCase or client calls
        response = self.client.get("/api/personalized-feed")
        self.assertEqual(
            response.status_code, 401
        )  # JWT errors are usually 401 or 422 if malformed
        # Flask-JWT-Extended typically returns 401 for missing token
        data = json.loads(response.data)
        self.assertIn("msg", data)  # Default message key for flask-jwt-extended
        self.assertEqual(data["msg"], "Missing Authorization Header")

    def test_personalized_feed_success_and_structure(self):
        # with app.app_context():
        # 1. Setup Data
        # Friendships: user1 is friends with user2
        self._create_db_friendship(
            self.user1, self.user2, status="accepted"
        )  # Changed to use user objects

        # Posts:
        # Post by user3 (not friend), liked by user2 (friend of user1) -> should be recommended
        post1_by_user3 = self._create_db_post(
            user_id=self.user3_id,
            title="Post by User3, Liked by User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        self._create_db_like(
            user_id=self.user2_id,
            post_id=post1_by_user3.id,
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=30),
        )

        # Post by user3 (not friend), commented by user2 (friend of user1)
        post2_by_user3 = self._create_db_post(
            user_id=self.user3_id,
            title="Another Post by User3, Commented by User2",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        self._create_db_comment(
            user_id=self.user2_id,
            post_id=post2_by_user3.id,
            content="Friend comment",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        # Events:
        # Event by user3, user2 (friend of user1) RSVP'd 'Attending' -> should be recommended
        event1_by_user3 = self._create_db_event(
            user_id=self.user3_id,
            title="Event by User3, User2 Attending",
            date_str=(datetime.now(timezone.utc) + timedelta(days=1)).strftime(
                "%Y-%m-%d"
            ),
        )
        # event1_by_user3.created_at = datetime.now(timezone.utc) - timedelta(days=1) # Set created_at for sorting - _create_db_event in AppTestCase should handle this
        # db.session.commit() # commit is in _create_db_event
        self._create_db_event_rsvp(
            user_id=self.user2_id, event_id=event1_by_user3.id, status="Attending"
        )

        # Polls:
        # Poll by user2 (friend of user1) -> should be recommended
        poll1_by_user2 = self._create_db_poll(
            user_id=self.user2_id, question="Poll by User2 (Friend)?"
        )
        # poll1_by_user2.created_at = datetime.now(timezone.utc) - timedelta(days=2) # Set created_at - _create_db_poll in AppTestCase should handle this
        # db.session.commit() # commit is in _create_db_poll
        # Add a vote from user3 to make it seem active
        with self.app.app_context():  # Add app context for accessing .options
            poll_for_options = self.db.session.merge(poll1_by_user2)
            self.assertTrue(
                len(poll_for_options.options) > 0, "Poll should have options."
            )
            option_for_poll1 = poll_for_options.options[0]

            self._create_db_poll_vote(
                user_id=self.user3_id,
                poll_id=poll_for_options.id,  # Use ID from merged object
                poll_option_id=option_for_poll1.id,
            )
            poll1_by_user2 = (
                poll_for_options  # Update poll1_by_user2 to the merged instance
            )

        # 2. Login as user1 and get token
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Make request
        response = self.client.get("/api/personalized-feed", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("feed_items", data)
        feed_items = data["feed_items"]
        self.assertIsInstance(feed_items, list)

        # We expect at least one of each type based on setup (if DB is live)
        self.assertEqual(
            len(feed_items), 4, f"Expected 4 items, got {len(feed_items)}: {feed_items}"
        )

        found_post = False
        found_event = False
        found_poll = False

        timestamps = []

        for item in feed_items:
            self.assertIn("type", item)
            self.assertIn("id", item)
            self.assertIn("timestamp", item)
            self.assertIsNotNone(item["timestamp"])
            ts_str = item["timestamp"]
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
                timestamps.append(datetime.fromisoformat(ts_str).replace(tzinfo=None))
            else:
                timestamps.append(datetime.fromisoformat(ts_str))

            if item["type"] == "post":
                found_post = True
                self.assertIn("title", item)
                self.assertIn("content", item)
                self.assertIn("author_username", item)
                self.assertIn("reason", item)
                if (
                    post1_by_user3 and item["id"] == post1_by_user3.id
                ):  # Check if post1_by_user3 is not None
                    self.assertEqual(item["title"], "Post by User3, Liked by User2")
            elif item["type"] == "event":
                found_event = True
                self.assertIn("title", item)
                self.assertIn("description", item)
                self.assertIn("organizer_username", item)
                if (
                    event1_by_user3 and item["id"] == event1_by_user3.id
                ):  # Check if event1_by_user3 is not None
                    self.assertEqual(item["title"], "Event by User3, User2 Attending")
            elif item["type"] == "poll":
                found_poll = True
                self.assertIn("question", item)
                self.assertIn("creator_username", item)
                self.assertIn("options", item)
                self.assertIsInstance(item["options"], list)
                if item["options"]:
                    self.assertIn("text", item["options"][0])
                    self.assertIn("vote_count", item["options"][0])
                if (
                    poll1_by_user2 and item["id"] == poll1_by_user2.id
                ):  # Check if poll1_by_user2 is not None
                    self.assertEqual(item["question"], "Poll by User2 (Friend)?")

        # These assertions might fail if DB helpers are not creating items due to missing live DB
        self.assertTrue(found_post, "No post found in feed")
        self.assertTrue(found_event, "No event found in feed")
        self.assertTrue(found_poll, "No poll found in feed")

        if timestamps:  # Only check sorting if there are items
            for i in range(len(timestamps) - 1):
                self.assertGreaterEqual(
                    timestamps[i],
                    timestamps[i + 1],
                    "Feed items are not sorted correctly by timestamp",
                )

    def test_personalized_feed_empty(self):
        # with app.app_context():
        token = self._get_jwt_token(
            self.user3.username, "password"
        )  # user3 has no relevant activity
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.get("/api/personalized-feed", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("feed_items", data)
        self.assertEqual(data["feed_items"], [])

    def test_personalized_feed_excludes_own_content_interacted_by_friends(self):
        # 1. Establish friendship
        self._create_db_friendship(
            self.user1, self.user2, status="accepted"
        )  # Changed to use user objects

        # --- Items created by user1, interacted by user2 (friend) ---
        # These SHOULD NOT appear in user1's feed

        # 2. User1 creates a post, User2 likes it
        post_by_user1 = self._create_db_post(
            user_id=self.user1_id,
            title="User1 Own Post",
            content="Content by User1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        self._create_db_like(
            user_id=self.user2_id,
            post_id=post_by_user1.id,
            timestamp=datetime.now(timezone.utc)
            - timedelta(hours=4),  # Older interaction
        )

        # 3. User1 creates an event, User2 RSVPs
        event_by_user1 = self._create_db_event(
            user_id=self.user1_id,
            title="User1 Own Event",
            description="Event by User1",
            date_str=(datetime.now(timezone.utc) + timedelta(days=1)).strftime(
                "%Y-%m-%d"
            ),
        )
        # Explicitly set older creation for the event itself
        with self.app.app_context():  # Add app context here
            event_by_user1_merged = self.db.session.merge(event_by_user1)
            event_by_user1_merged.created_at = datetime.now(timezone.utc) - timedelta(
                hours=3
            )
            self.db.session.commit()
            event_by_user1 = event_by_user1_merged  # Use the merged object

        # Ensure event_by_user1 is session-bound before accessing its ID for RSVP
        with self.app.app_context():
            event_for_rsvp = self.db.session.merge(event_by_user1)
            self._create_db_event_rsvp(
                user_id=self.user2_id,
                event_id=event_for_rsvp.id,  # Use ID from merged object
                status="Attending",
                timestamp=datetime.now(timezone.utc)
                - timedelta(hours=2),  # Older interaction
            )
            event_by_user1 = (
                event_for_rsvp  # Update event_by_user1 to the merged instance
            )

        # 4. User1 creates a poll, User2 votes
        poll_by_user1 = self._create_db_poll(
            user_id=self.user1_id, question="User1 Own Poll?"
        )
        # Explicitly set older creation for the poll itself
        with self.app.app_context():  # Add app context here
            poll_by_user1_merged = self.db.session.merge(poll_by_user1)
            poll_by_user1_merged.created_at = datetime.now(timezone.utc) - timedelta(
                hours=1
            )
            self.db.session.commit()
            poll_by_user1 = poll_by_user1_merged  # Use the merged object

        # Assuming _create_db_poll helper creates at least one option.
        with self.app.app_context():  # Add app context for accessing .options
            poll_for_vote_options = self.db.session.merge(poll_by_user1)
            self.assertTrue(
                len(poll_for_vote_options.options) > 0,
                "Poll (for excluding own content) should have options.",
            )
            option_for_poll1 = poll_for_vote_options.options[0]

            self._create_db_poll_vote(
                user_id=self.user2_id,
                poll_id=poll_for_vote_options.id,  # Use ID from merged object
                poll_option_id=option_for_poll1.id,
                created_at=datetime.now(timezone.utc)
                - timedelta(minutes=45),  # Changed 'timestamp' to 'created_at'
            )
            poll_by_user1 = poll_for_vote_options  # Update reference

        # --- Control Item: Post by User3, Liked by User2 (friend of User1) ---
        # This SHOULD APPEAR in user1's feed

        post_by_user3 = self._create_db_post(
            user_id=self.user3_id,
            title="User3 Post for Feed",
            content="Content by User3",
            timestamp=datetime.now(timezone.utc)
            - timedelta(minutes=30),  # Content creation time
        )
        self.like_on_user3_post_timestamp = datetime.now(timezone.utc) - timedelta(
            minutes=15
        )  # Most recent interaction
        self._create_db_like(
            user_id=self.user2_id,
            post_id=post_by_user3.id,
            timestamp=self.like_on_user3_post_timestamp,
        )

        # Store details for assertions
        self.control_post_id = post_by_user3.id
        self.control_post_title = post_by_user3.title

        self.excluded_post_id = post_by_user1.id
        self.excluded_event_id = event_by_user1.id
        self.excluded_poll_id = poll_by_user1.id

        # Log in as user1 and fetch feed
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.get("/api/personalized-feed", headers=headers)

        # Basic response validation
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("feed_items", data)

        feed_items = data["feed_items"]

        # Assertions
        self.assertEqual(
            len(feed_items),
            1,
            f"Expected 1 item in feed, but got {len(feed_items)}: {feed_items}",
        )

        if len(feed_items) == 1:
            control_item = feed_items[0]
            self.assertEqual(control_item["type"], "post")
            self.assertEqual(control_item["id"], self.control_post_id)
            self.assertEqual(control_item["title"], self.control_post_title)
            self.assertIn("reason", control_item, "Feed item should have a reason")
            # Assuming self.user2 is available from AppTestCase setup
            expected_reason_fragment = f"Liked by your friend {self.user2.username}"
            self.assertIn(
                expected_reason_fragment,
                control_item["reason"],
                f"Reason '{control_item.get('reason')}' does not contain '{expected_reason_fragment}'",
            )

        # Explicitly check that none of the user1's own items (interacted by user2) are present
        for item in feed_items:
            if item["type"] == "post":
                self.assertNotEqual(
                    item["id"],
                    self.excluded_post_id,
                    f"Feed should not contain user1's own post (ID: {self.excluded_post_id}) that was liked by a friend.",
                )
            elif item["type"] == "event":
                self.assertNotEqual(
                    item["id"],
                    self.excluded_event_id,
                    f"Feed should not contain user1's own event (ID: {self.excluded_event_id}) that a friend RSVP'd to.",
                )
            elif item["type"] == "poll":
                self.assertNotEqual(
                    item["id"],
                    self.excluded_poll_id,
                    f"Feed should not contain user1's own poll (ID: {self.excluded_poll_id}) that a friend voted on.",
                )

    def test_feed_excludes_content_interacted_by_removed_friend(self):
        # 1. Setup Users: self.user1 (viewer), self.user2 (friend), self.user3 (content creator)
        # Users are available from AppTestCase setUp: self.user1_id, self.user2_id, self.user3_id

        # 2. Establish friendship between user1 and user2
        self._create_db_friendship(
            self.user1, self.user2, status="accepted"
        )  # Changed to use user objects

        # 3. user3 creates a post
        post_by_user3 = self._create_db_post(
            user_id=self.user3_id, title="Post by User3, to be liked by User2"
        )
        self.target_post_id = post_by_user3.id  # Store for later assertions

        # 4. user2 (friend of user1) likes user3's post
        self._create_db_like(user_id=self.user2_id, post_id=self.target_post_id)

        # 2. Verify post appears in user1's feed (user2 is a friend)
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        headers_user1 = {"Authorization": f"Bearer {token_user1}"}

        response = self.client.get("/api/personalized-feed", headers=headers_user1)
        self.assertEqual(response.status_code, 200, "Failed to fetch feed for user1")
        data = json.loads(response.data)

        feed_items = data.get("feed_items", [])
        found_post_in_feed = False
        for item in feed_items:
            if item.get("type") == "post" and item.get("id") == self.target_post_id:
                found_post_in_feed = True
                self.assertIn(
                    f"Liked by your friend {self.user2.username}",
                    item.get("reason", ""),
                    "Feed item reason is incorrect or missing friend's like.",
                )
                break

        self.assertTrue(
            found_post_in_feed,
            f"Post {self.target_post_id} liked by friend {self.user2.username} not found in user1's feed when it should be.",
        )

        # 3. Remove friendship between user1 and user2
        # Friendships might be stored in one direction or both, query flexibly.
        with self.app.app_context():  # Add app context here
            friendship_record = Friendship.query.filter(
                (
                    (Friendship.user_id == self.user1_id)
                    & (Friendship.friend_id == self.user2_id)
                )
                | (
                    (Friendship.user_id == self.user2_id)
                    & (Friendship.friend_id == self.user1_id)
                ),
                Friendship.status
                == "accepted",  # Ensure we are targeting the accepted friendship
            ).first()

            self.assertIsNotNone(
                friendship_record,
                "Friendship record not found before attempting to remove.",
            )

            if friendship_record:
                self.db.session.delete(friendship_record)
                self.db.session.commit()

        # 4. Verify post no longer appears in user1's feed
        # Use the same token and headers for user1
        response_after_unfriend = self.client.get(
            "/api/personalized-feed", headers=headers_user1
        )
        self.assertEqual(
            response_after_unfriend.status_code,
            200,
            "Failed to fetch feed for user1 after unfriending user2",
        )
        data_after_unfriend = json.loads(response_after_unfriend.data)

        feed_items_after_unfriend = data_after_unfriend.get("feed_items", [])
        found_post_after_unfriend = False
        for item in feed_items_after_unfriend:
            if item.get("type") == "post" and item.get("id") == self.target_post_id:
                found_post_after_unfriend = True
                break

        self.assertFalse(
            found_post_after_unfriend,
            f"Post {self.target_post_id} (liked by removed friend {self.user2.username}) "
            f"was found in user1's feed when it should be excluded.",
        )

    def test_feed_excludes_posts_from_removed_friend(self):
        # 1. Establish an 'accepted' friendship between self.user1_id and self.user2_id
        self._create_db_friendship(
            self.user1, self.user2, status="accepted"
        )  # Changed to use user objects

        # 2. Have self.user2 create a post
        post_by_user2 = self._create_db_post(
            user_id=self.user2_id,
            title="Post by User2",
            content="Content by User2, friend of User1",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        # 3. Obtain a JWT token for self.user1
        token_user1 = self._get_jwt_token(self.user1.username, "password")
        headers_user1 = {"Authorization": f"Bearer {token_user1}"}

        # 4. Fetch self.user1's personalized feed
        response = self.client.get("/api/personalized-feed", headers=headers_user1)

        # 5. Assert that the response status code is 200
        self.assertEqual(
            response.status_code,
            200,
            "Failed to fetch feed for user1 while friend is active.",
        )

        # 6. Load the JSON response and extract feed_items
        data = json.loads(response.data)
        feed_items = data.get("feed_items", [])

        # 7. Iterate through feed_items to find the post created by self.user2. Assert that it is present.
        found_post_while_friend = False
        for item in feed_items:
            if item.get("type") == "post" and item.get("id") == post_by_user2.id:
                found_post_while_friend = True
                # 8. Assert that the 'reason' for the post in the feed correctly identifies self.user2.username
                expected_reason = f"Posted by your friend {self.user2.username}"  # Or similar, based on actual reason format
                # For now, we'll check if the username is in the reason, as exact phrasing might vary.
                self.assertIn(
                    self.user2.username,
                    item.get("reason", ""),
                    "Reason for friend's post is incorrect or missing friend's username.",
                )
                break

        self.assertTrue(
            found_post_while_friend,
            f"Post {post_by_user2.id} by friend {self.user2.username} not found in user1's feed when it should be present.",
        )

        # --- Remove friendship and verify exclusion ---

        # 1. Remove the friendship
        # Query for the friendship record. _create_friendship might create one or two records.
        # We need to ensure the 'accepted' status is targeted.
        with self.app.app_context():  # Add app context here
            friendship_record = Friendship.query.filter(
                (
                    (Friendship.user_id == self.user1_id)
                    & (Friendship.friend_id == self.user2_id)
                    & (Friendship.status == "accepted")
                )
                | (
                    (Friendship.user_id == self.user2_id)
                    & (Friendship.friend_id == self.user1_id)
                    & (Friendship.status == "accepted")
                )
            ).first()

            self.assertIsNotNone(
                friendship_record,
                "Friendship record not found before attempting to remove.",
            )

            if friendship_record:
                self.db.session.delete(friendship_record)
                # If _create_friendship creates two records (one for each direction), delete the other one too.
                # This depends on the implementation of _create_friendship. Assuming it creates one for now.
                # If issues arise, this part might need adjustment.
                self.db.session.commit()

        # 2. Fetch user1's personalized feed again (using the same token)
        response_after_unfriend = self.client.get(
            "/api/personalized-feed", headers=headers_user1
        )
        self.assertEqual(
            response_after_unfriend.status_code,
            200,
            "Failed to fetch feed for user1 after unfriending user2.",
        )

        data_after_unfriend = json.loads(response_after_unfriend.data)
        feed_items_after_unfriend = data_after_unfriend.get("feed_items", [])

        # 3. Verify post exclusion
        found_post_after_unfriend = False
        for item in feed_items_after_unfriend:
            if item.get("type") == "post" and item.get("id") == post_by_user2.id:
                found_post_after_unfriend = True
                break

        self.assertFalse(
            found_post_after_unfriend,
            f"Post {post_by_user2.id} from formerly friended user {self.user2.username} "
            f"was found in user1's feed when it should be excluded.",
        )
