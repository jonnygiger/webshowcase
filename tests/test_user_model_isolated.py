import unittest
from datetime import datetime, timezone, timedelta

from social_app import db
from social_app.models.db_models import (
    User,
    Post,
    UserStatus,
    Comment,
    Like,
)
from tests.test_base import AppTestCase


class TestUserModelIsolated(AppTestCase):

    def test_user_get_stats(self):
        with self.app.app_context():
            user = self._create_db_user(username="stats_user")
            user_friend = self._create_db_user(username="stats_friend")

            post1 = self._create_db_post(user_id=user.id, title="User Post 1")
            self._create_db_post(user_id=user.id, title="User Post 2")

            self._create_db_comment(
                user_id=user.id, post_id=post1.id, content="Comment on own post"
            )

            liker1 = self._create_db_user(username="liker1")
            liker2 = self._create_db_user(username="liker2")
            self._create_db_like(user_id=liker1.id, post_id=post1.id)
            self._create_db_like(user_id=liker2.id, post_id=post1.id)

            self._create_db_friendship(user, user_friend, status="accepted")

            db.session.refresh(user)

            stats = user.get_stats()

            self.assertEqual(stats["posts_count"], 2)
            self.assertEqual(stats["comments_count"], 1)
            self.assertEqual(stats["likes_received_count"], 2)
            self.assertEqual(stats["friends_count"], 1)
            self.assertIsNotNone(stats["join_date"])
            try:
                datetime.fromisoformat(stats["join_date"].replace("Z", "+00:00"))
            except ValueError:
                self.fail("join_date is not a valid ISO format string")

    def test_user_get_current_status(self):
        with self.app.app_context():
            user_with_status = self._create_db_user(username="status_user")

            self.assertIsNone(user_with_status.get_current_status())

            status1_time = datetime.now(timezone.utc) - timedelta(minutes=10)
            status1 = UserStatus(
                user_id=user_with_status.id,
                status_text="Feeling great!",
                timestamp=status1_time,
            )
            db.session.add(status1)
            db.session.commit()
            db.session.refresh(user_with_status)

            current_status = user_with_status.get_current_status()
            self.assertIsNotNone(current_status)
            self.assertEqual(current_status.status_text, "Feeling great!")

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

            self._create_db_friendship(user_C, user_D, "accepted")
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

if __name__ == "__main__":
    unittest.main()
