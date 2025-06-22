import unittest
from datetime import datetime, timezone, timedelta

from app import db
from models import User, Post, PostLock, Friendship, UserBlock, Series, SeriesPost
from tests.test_base import AppTestCase # Assuming this sets up app context and db

class TestUserModel(AppTestCase):

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
            post_fetched = db.session.get(Post, post.id) # Re-fetch
            self.assertFalse(post_fetched.is_locked())

    def test_post_is_locked_active_lock(self):
        with self.app.app_context():
            u = self._create_db_user(username="postlockuser2")
            post = self._create_db_post(user_id=u.id, title="Locked Post Active")

            # Create an active lock
            lock = PostLock(
                post_id=post.id,
                user_id=u.id,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
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
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=15)
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
            self.assertEqual(repr(friendship), f"<Friendship {u1.id} to {u2.id} - pending>")

    def test_cannot_friend_self(self):
        with self.app.app_context():
            u = self._create_db_user(username="self_friender")
            friendship = Friendship(user_id=u.id, friend_id=u.id, status="pending")
            db.session.add(friendship)
            with self.assertRaises(Exception) as context: # Should be sqlalchemy.exc.IntegrityError
                db.session.commit()
            self.assertTrue('ck_user_not_friend_self' in str(context.exception).lower() or
                            'check constraint failed' in str(context.exception).lower()) # More generic for sqlite
            db.session.rollback()

    def test_duplicate_friend_request_constraint(self):
        with self.app.app_context():
            u1 = self._create_db_user(username="friend_requester_dup")
            u2 = self._create_db_user(username="friend_receiver_dup")

            friendship1 = Friendship(user_id=u1.id, friend_id=u2.id, status="pending")
            db.session.add(friendship1)
            db.session.commit()

            friendship2 = Friendship(user_id=u1.id, friend_id=u2.id, status="accepted") # Same pair
            db.session.add(friendship2)

            with self.assertRaises(Exception) as context: # sqlalchemy.exc.IntegrityError
                db.session.commit()
            self.assertTrue('uq_user_friend' in str(context.exception).lower() or
                            'unique constraint failed' in str(context.exception).lower()) # More generic for sqlite
            db.session.rollback()

class TestUserBlockModel(AppTestCase):
    def test_user_block_repr(self):
        with self.app.app_context():
            blocker = self._create_db_user(username="blocker_repr")
            blocked = self._create_db_user(username="blocked_repr")
            user_block = UserBlock(blocker_id=blocker.id, blocked_id=blocked.id)
            db.session.add(user_block)
            db.session.commit()
            self.assertEqual(repr(user_block), f"<UserBlock blocker_id={blocker.id} blocked_id={blocked.id}>")

    def test_cannot_block_self(self):
        with self.app.app_context():
            u = self._create_db_user(username="self_blocker")
            user_block = UserBlock(blocker_id=u.id, blocked_id=u.id)
            db.session.add(user_block)
            with self.assertRaises(Exception) as context: # sqlalchemy.exc.IntegrityError
                db.session.commit()
            self.assertTrue('ck_blocker_not_blocked_self' in str(context.exception).lower() or
                            'check constraint failed' in str(context.exception).lower())
            db.session.rollback()

    def test_duplicate_user_block_constraint(self):
        with self.app.app_context():
            blocker = self._create_db_user(username="blocker_dup")
            blocked = self._create_db_user(username="blocked_dup")

            block1 = UserBlock(blocker_id=blocker.id, blocked_id=blocked.id)
            db.session.add(block1)
            db.session.commit()

            block2 = UserBlock(blocker_id=blocker.id, blocked_id=blocked.id) # Same pair
            db.session.add(block2)

            with self.assertRaises(Exception) as context: # sqlalchemy.exc.IntegrityError
                db.session.commit()
            self.assertTrue('uq_blocker_blocked' in str(context.exception).lower() or
                            'unique constraint failed' in str(context.exception).lower())
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

            sp_entry2 = SeriesPost(series_id=series.id, post_id=post2.id, order=1) # Beta is first
            sp_entry3 = SeriesPost(series_id=series.id, post_id=post3.id, order=2) # Gamma is second
            sp_entry1 = SeriesPost(series_id=series.id, post_id=post1.id, order=3) # Alpha is third

            db.session.add_all([sp_entry1, sp_entry2, sp_entry3])
            db.session.commit()

            # Re-fetch series to ensure relationships are loaded with current DB state
            # and that the series object is bound to the current session.
            fetched_series = db.session.get(Series, series.id)

            # Access series.posts which relies on the relationship's order_by clause
            ordered_posts_from_series = fetched_series.posts

            self.assertEqual(len(ordered_posts_from_series), 3)
            self.assertEqual(ordered_posts_from_series[0].id, post2.id) # Beta
            self.assertEqual(ordered_posts_from_series[1].id, post3.id) # Gamma
            self.assertEqual(ordered_posts_from_series[2].id, post1.id) # Alpha

if __name__ == "__main__":
    unittest.main()
