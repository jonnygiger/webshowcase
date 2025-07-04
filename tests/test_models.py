import unittest
from datetime import datetime, timezone, timedelta

from app import db
from models import (
    User,
    Post,
    PostLock,
    Friendship,
    UserBlock,
    Series,
    SeriesPost,
    UserStatus,
    Comment,
    Like,
    EventRSVP,
    PollVote,
    Poll,
)  # Added EventRSVP, PollVote, Poll
from tests.test_base import AppTestCase  # Assuming this sets up app context and db


class TestUserModel(AppTestCase):

    def test_user_get_stats(self):
        with self.app.app_context():
            user = self._create_db_user(username="stats_user")
            user_friend = self._create_db_user(username="stats_friend")

            # Create posts
            post1 = self._create_db_post(user_id=user.id, title="User Post 1")
            self._create_db_post(user_id=user.id, title="User Post 2")

            # Create comments by user
            self._create_db_comment(
                user_id=user.id, post_id=post1.id, content="Comment on own post"
            )

            # Create likes received by user on their post
            liker1 = self._create_db_user(username="liker1")
            liker2 = self._create_db_user(username="liker2")
            self._create_db_like(user_id=liker1.id, post_id=post1.id)
            self._create_db_like(user_id=liker2.id, post_id=post1.id)

            # Create friendships
            self._create_db_friendship(user, user_friend, status="accepted")

            # Refresh user to ensure all relationships are loaded
            db.session.refresh(user)

            stats = user.get_stats()

            self.assertEqual(stats["posts_count"], 2)
            self.assertEqual(stats["comments_count"], 1)  # Comments made by the user
            self.assertEqual(stats["likes_received_count"], 2)  # Likes on user's posts
            self.assertEqual(stats["friends_count"], 1)
            self.assertIsNotNone(stats["join_date"])
            # Check if join_date is a valid ISO format string
            try:
                datetime.fromisoformat(stats["join_date"].replace("Z", "+00:00"))
            except ValueError:
                self.fail("join_date is not a valid ISO format string")

    def test_user_get_current_status(self):
        with self.app.app_context():
            user_with_status = self._create_db_user(username="status_user")

            # No status initially
            self.assertIsNone(user_with_status.get_current_status())

            # Add a status
            status1_time = datetime.now(timezone.utc) - timedelta(minutes=10)
            status1 = UserStatus(
                user_id=user_with_status.id,
                status_text="Feeling great!",
                timestamp=status1_time,
            )
            db.session.add(status1)
            db.session.commit()
            db.session.refresh(user_with_status)  # Refresh to update relationships

            current_status = user_with_status.get_current_status()
            self.assertIsNotNone(current_status)
            self.assertEqual(current_status.status_text, "Feeling great!")

            # Add a newer status
            status2_time = datetime.now(timezone.utc) - timedelta(minutes=5)
            status2 = UserStatus(
                user_id=user_with_status.id,
                status_text="Just updated!",
                timestamp=status2_time,
            )
            db.session.add(status2)
            db.session.commit()
            db.session.refresh(user_with_status)

            current_status_updated = user_with_status.get_current_status()
            self.assertIsNotNone(current_status_updated)
            self.assertEqual(current_status_updated.status_text, "Just updated!")
            self.assertEqual(current_status_updated.id, status2.id)

            # Add an older status (should not become current)
            status0_time = datetime.now(timezone.utc) - timedelta(minutes=20)
            status0 = UserStatus(
                user_id=user_with_status.id,
                status_text="Way back when",
                timestamp=status0_time,
            )
            db.session.add(status0)
            db.session.commit()
            db.session.refresh(user_with_status)

            current_status_still_updated = user_with_status.get_current_status()
            self.assertIsNotNone(current_status_still_updated)
            self.assertEqual(current_status_still_updated.status_text, "Just updated!")
            self.assertEqual(current_status_still_updated.id, status2.id)

    def test_password_hashing(self):
        with self.app.app_context():
            u = User(username="testuser_model", email="testmodel@example.com")
            u.set_password("cat")
            self.assertNotEqual(u.password_hash, "cat")
            self.assertTrue(u.check_password("cat"))
            self.assertFalse(u.check_password("dog"))

    def test_user_repr(self):
        with self.app.app_context():
            u = User(username="testuser_repr", email="testrepr@example.com")
            u.set_password("password")
            db.session.add(u)
            db.session.commit()
            self.assertEqual(repr(u), "<User testuser_repr>")

    def test_user_get_friends_no_friends(self):
        with self.app.app_context():
            user_no_friends = self._create_db_user(username="user_no_friends")
            friends = user_no_friends.get_friends()
            self.assertEqual(len(friends), 0)

    def test_user_get_friends_one_way_pending(self):
        with self.app.app_context():
            user_A = self._create_db_user(username="user_A_pending")
            user_B = self._create_db_user(username="user_B_pending")
            _ = self._create_db_friendship(user_A, user_B, "pending")

            self.assertEqual(len(user_A.get_friends()), 0)
            self.assertEqual(len(user_B.get_friends()), 0)

    def test_user_get_friends_accepted(self):
        with self.app.app_context():
            user_C = self._create_db_user(username="user_C_friends")
            user_D = self._create_db_user(username="user_D_friends")
            user_E = self._create_db_user(username="user_E_friends")

            # C <-> D are friends
            self._create_db_friendship(user_C, user_D, "accepted")
            # C -> E request pending
            self._create_db_friendship(user_C, user_E, "pending")

            friends_C = user_C.get_friends()
            self.assertEqual(len(friends_C), 1)
            self.assertIn(user_D, friends_C)
            self.assertNotIn(user_E, friends_C)

            friends_D = user_D.get_friends()
            self.assertEqual(len(friends_D), 1)
            self.assertIn(user_C, friends_D)

            friends_E = user_E.get_friends()
            self.assertEqual(len(friends_E), 0)


class TestPostModel(AppTestCase):

    def test_post_repr(self):
        with self.app.app_context():
            u = self._create_db_user(username="postauthor")
            p = Post(title="Test Post Title", content="Some content", user_id=u.id)
            db.session.add(p)
            db.session.commit()
            self.assertEqual(repr(p), "<Post Test Post Title>")

    def test_post_is_locked_no_lock(self):
        with self.app.app_context():
            u = self._create_db_user(username="postlockuser1")
            post = self._create_db_post(user_id=u.id, title="Unlocked Post")
            post_fetched = db.session.get(Post, post.id)  # Re-fetch
            self.assertFalse(post_fetched.is_locked())

    def test_post_is_locked_active_lock(self):
        with self.app.app_context():
            u = self._create_db_user(username="postlockuser2")
            post = self._create_db_post(user_id=u.id, title="Locked Post Active")

            # Create an active lock
            lock = PostLock(
                post_id=post.id,
                user_id=u.id,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
            db.session.add(lock)
            db.session.commit()

            # Re-fetch post or refresh its lock_info relationship if necessary
            post_fetched = db.session.get(Post, post.id)
            self.assertTrue(post_fetched.is_locked())

    def test_post_is_locked_expired_lock(self):
        with self.app.app_context():
            u = self._create_db_user(username="postlockuser3")
            post = self._create_db_post(user_id=u.id, title="Locked Post Expired")

            # Create an expired lock
            lock = PostLock(
                post_id=post.id,
                user_id=u.id,
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            )
            db.session.add(lock)
            db.session.commit()

            post_fetched = db.session.get(Post, post.id)
            self.assertFalse(post_fetched.is_locked())


class TestFriendshipModel(AppTestCase):

    def test_friendship_repr(self):
        with self.app.app_context():
            u1 = self._create_db_user(username="friend1_repr")
            u2 = self._create_db_user(username="friend2_repr")
            friendship = Friendship(user_id=u1.id, friend_id=u2.id, status="pending")
            db.session.add(friendship)
            db.session.commit()
            self.assertEqual(
                repr(friendship), f"<Friendship {u1.id} to {u2.id} - pending>"
            )

    def test_cannot_friend_self(self):
        with self.app.app_context():
            u = self._create_db_user(username="self_friender")
            friendship = Friendship(user_id=u.id, friend_id=u.id, status="pending")
            db.session.add(friendship)
            with self.assertRaises(
                Exception
            ) as context:  # Should be sqlalchemy.exc.IntegrityError
                db.session.commit()
            self.assertTrue(
                "ck_user_not_friend_self" in str(context.exception).lower()
                or "check constraint failed" in str(context.exception).lower()
            )  # More generic for sqlite
            db.session.rollback()

    def test_duplicate_friend_request_constraint(self):
        with self.app.app_context():
            u1 = self._create_db_user(username="friend_requester_dup")
            u2 = self._create_db_user(username="friend_receiver_dup")

            friendship1 = Friendship(user_id=u1.id, friend_id=u2.id, status="pending")
            db.session.add(friendship1)
            db.session.commit()

            friendship2 = Friendship(
                user_id=u1.id, friend_id=u2.id, status="accepted"
            )  # Same pair
            db.session.add(friendship2)

            with self.assertRaises(
                Exception
            ) as context:  # sqlalchemy.exc.IntegrityError
                db.session.commit()
            self.assertTrue(
                "uq_user_friend" in str(context.exception).lower()
                or "unique constraint failed" in str(context.exception).lower()
            )  # More generic for sqlite
            db.session.rollback()


class TestUserBlockModel(AppTestCase):
    def test_user_block_repr(self):
        with self.app.app_context():
            blocker = self._create_db_user(username="blocker_repr")
            blocked = self._create_db_user(username="blocked_repr")
            user_block = UserBlock(blocker_id=blocker.id, blocked_id=blocked.id)
            db.session.add(user_block)
            db.session.commit()
            self.assertEqual(
                repr(user_block),
                f"<UserBlock blocker_id={blocker.id} blocked_id={blocked.id}>",
            )

    def test_cannot_block_self(self):
        with self.app.app_context():
            u = self._create_db_user(username="self_blocker")
            user_block = UserBlock(blocker_id=u.id, blocked_id=u.id)
            db.session.add(user_block)
            with self.assertRaises(
                Exception
            ) as context:  # sqlalchemy.exc.IntegrityError
                db.session.commit()
            self.assertTrue(
                "ck_blocker_not_blocked_self" in str(context.exception).lower()
                or "check constraint failed" in str(context.exception).lower()
            )
            db.session.rollback()

    def test_duplicate_user_block_constraint(self):
        with self.app.app_context():
            blocker = self._create_db_user(username="blocker_dup")
            blocked = self._create_db_user(username="blocked_dup")

            block1 = UserBlock(blocker_id=blocker.id, blocked_id=blocked.id)
            db.session.add(block1)
            db.session.commit()

            block2 = UserBlock(
                blocker_id=blocker.id, blocked_id=blocked.id
            )  # Same pair
            db.session.add(block2)

            with self.assertRaises(
                Exception
            ) as context:  # sqlalchemy.exc.IntegrityError
                db.session.commit()
            self.assertTrue(
                "uq_blocker_blocked" in str(context.exception).lower()
                or "unique constraint failed" in str(context.exception).lower()
            )
            db.session.rollback()


class TestSeriesModel(AppTestCase):
    def test_series_repr(self):
        with self.app.app_context():
            u = self._create_db_user(username="series_author_repr")
            s = Series(title="My Awesome Series", description="Fun stuff", user_id=u.id)
            db.session.add(s)
            db.session.commit()
            self.assertEqual(repr(s), '<Series "My Awesome Series">')

    def test_series_posts_property_order(self):
        with self.app.app_context():
            author = self._create_db_user(username="series_post_order_author")
            series = self._create_db_series(user_id=author.id, title="Ordered Series")

            post1 = self._create_db_post(user_id=author.id, title="Post Alpha")
            post2 = self._create_db_post(user_id=author.id, title="Post Beta")
            post3 = self._create_db_post(user_id=author.id, title="Post Gamma")

            # Add posts to series in a specific order, then commit
            # Note: SeriesPost.order is important here.
            # The test assumes direct creation of SeriesPost entries or a helper that manages order.
            # Let's create SeriesPost entries directly for clarity on order.

            sp_entry2 = SeriesPost(
                series_id=series.id, post_id=post2.id, order=1
            )  # Beta is first
            sp_entry3 = SeriesPost(
                series_id=series.id, post_id=post3.id, order=2
            )  # Gamma is second
            sp_entry1 = SeriesPost(
                series_id=series.id, post_id=post1.id, order=3
            )  # Alpha is third

            db.session.add_all([sp_entry1, sp_entry2, sp_entry3])
            db.session.commit()

            # Re-fetch series to ensure relationships are loaded with current DB state
            # and that the series object is bound to the current session.
            fetched_series = db.session.get(Series, series.id)

            # Access series.posts which relies on the relationship's order_by clause
            ordered_posts_from_series = fetched_series.posts

            self.assertEqual(len(ordered_posts_from_series), 3)
            self.assertEqual(ordered_posts_from_series[0].id, post2.id)  # Beta
            self.assertEqual(ordered_posts_from_series[1].id, post3.id)  # Gamma
            self.assertEqual(ordered_posts_from_series[2].id, post1.id)  # Alpha

    def test_series_to_dict_with_posts(self):
        with self.app.app_context():
            author = self._create_db_user(username="series_dict_author")
            series = self._create_db_series(
                user_id=author.id, title="Series For Dict Test"
            )

            post1 = self._create_db_post(user_id=author.id, title="Post One Dict")
            post2 = self._create_db_post(user_id=author.id, title="Post Two Dict")

            # Add posts to series
            sp_entry1 = SeriesPost(series_id=series.id, post_id=post1.id, order=1)
            sp_entry2 = SeriesPost(series_id=series.id, post_id=post2.id, order=2)
            db.session.add_all([sp_entry1, sp_entry2])
            db.session.commit()

            # Re-fetch series to ensure relationships are loaded
            fetched_series = db.session.get(Series, series.id)
            series_dict = fetched_series.to_dict()

            self.assertEqual(series_dict["title"], "Series For Dict Test")
            self.assertEqual(series_dict["author_username"], author.username)
            self.assertEqual(len(series_dict["posts"]), 2)
            self.assertEqual(series_dict["posts"][0]["title"], "Post One Dict")
            self.assertEqual(
                series_dict["posts"][0]["author_username"], author.username
            )
            self.assertEqual(series_dict["posts"][1]["title"], "Post Two Dict")

    def test_add_post_to_series_property(self):
        with self.app.app_context():
            author = self._create_db_user(username="series_add_post_author")
            series = self._create_db_series(
                user_id=author.id, title="Series Adding Posts"
            )
            post_to_add = self._create_db_post(
                user_id=author.id, title="Standalone Post"
            )

            # Add post to series
            series_post_entry = SeriesPost(
                series_id=series.id, post_id=post_to_add.id, order=1
            )
            db.session.add(series_post_entry)
            db.session.commit()

            fetched_series = db.session.get(Series, series.id)
            self.assertEqual(len(fetched_series.posts), 1)
            self.assertEqual(fetched_series.posts[0].id, post_to_add.id)
            self.assertEqual(fetched_series.posts[0].title, "Standalone Post")


class TestEventRSVPModel(AppTestCase):
    def test_event_rsvp_unique_constraint(self):
        # Tests the _user_event_uc unique constraint (user_id, event_id)
        with self.app.app_context():
            user = self._create_db_user(username="rsvp_user")
            event_organizer = self._create_db_user(username="event_organizer_rsvp")
            event = self._create_db_event(
                user_id=event_organizer.id, title="RSVP Test Event"
            )

            # First RSVP should be fine
            # Helper now returns ID directly
            rsvp1_id = self._create_db_event_rsvp(
                user_id=user.id, event_id=event.id, status="Attending"
            )

            # Re-fetch to ensure we have a session-bound object for assertions
            rsvp1_fetched = db.session.get(EventRSVP, rsvp1_id)
            self.assertIsNotNone(
                rsvp1_fetched, "RSVP1 object could not be re-fetched from DB."
            )
            self.assertIsNotNone(rsvp1_fetched.id, "RSVP1 ID is None after re-fetch.")

            # Second RSVP for the same user and event should fail
            rsvp2 = EventRSVP(user_id=user.id, event_id=event.id, status="Maybe")
            db.session.add(rsvp2)
            with self.assertRaises(
                Exception
            ) as context:  # sqlalchemy.exc.IntegrityError
                db.session.commit()
            self.assertTrue(
                "unique constraint failed" in str(context.exception).lower()
                or "_user_event_uc" in str(context.exception).lower()
            )
            db.session.rollback()


class TestPollVoteModel(AppTestCase):
    def test_poll_vote_unique_constraint(self):
        # Tests the _user_poll_uc unique constraint (user_id, poll_id)
        with self.app.app_context():
            voter = self._create_db_user(username="poll_voter_uc")
            poll_creator = self._create_db_user(username="poll_creator_uc")

            # Create the poll using the helper
            created_poll_obj = self._create_db_poll(
                user_id=poll_creator.id, question="Unique Vote Test Poll?"
            )
            # Get its ID
            poll_id = created_poll_obj.id

            # Re-fetch the poll within the current session context to ensure it's bound
            poll = db.session.get(Poll, poll_id)
            self.assertIsNotNone(
                poll, "Poll could not be re-fetched in the test context."
            )

            # Now access poll.options
            self.assertTrue(
                len(poll.options) > 0, "Poll created without options for testing."
            )
            option1 = poll.options[0]  # This option is from the re-fetched 'poll'

            # First vote should be fine
            # Helper now returns ID directly
            vote1_id = self._create_db_poll_vote(
                user_id=voter.id, poll_id=poll.id, poll_option_id=option1.id
            )

            # Re-fetch vote1 to ensure it's session-bound
            vote1_fetched = db.session.get(PollVote, vote1_id)
            self.assertIsNotNone(
                vote1_fetched, "Vote1 object could not be re-fetched from DB."
            )
            self.assertIsNotNone(vote1_fetched.id, "Vote1 ID is None after re-fetch.")

            # Second vote by the same user in the same poll (even if for a different option) should fail
            option2 = None
            # Access poll.options from the session-bound 'poll' object
            if len(poll.options) > 1:
                option2 = poll.options[1]
            else:  # If only one option, create another one for the test.
                from models import PollOption

                # Ensure operations on 'poll' use the session-bound instance
                option2_obj = PollOption(text="Option 2 For UC Test", poll_id=poll.id)
                db.session.add(option2_obj)
                db.session.commit()  # Commit the new option
                # The 'poll' object's 'options' collection might be stale.
                # Refresh 'poll' to update its 'options' relationship.
                db.session.refresh(poll)
                # Get the newly created option, now session-bound
                option2 = db.session.get(PollOption, option2_obj.id)

            self.assertIsNotNone(option2, "Option2 could not be prepared for the test.")
            self.assertIsNotNone(
                option2.id, "Option2 ID is None after creation/retrieval."
            )

            vote2 = PollVote(
                user_id=voter.id, poll_id=poll.id, poll_option_id=option2.id
            )
            db.session.add(vote2)
            with self.assertRaises(
                Exception
            ) as context:  # sqlalchemy.exc.IntegrityError
                db.session.commit()
            self.assertTrue(
                "unique constraint failed" in str(context.exception).lower()
                or "_user_poll_uc" in str(context.exception).lower()
            )
            db.session.rollback()


if __name__ == "__main__":
    unittest.main()
