import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from tests.test_base import AppTestCase

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from social_app import db
from social_app.models.db_models import User, Post, Like, Comment, SharedPost, Bookmark
from social_app.services.recommendations_service import suggest_trending_posts


class TestSuggestTrendingPosts(AppTestCase):
    def setUp(self):
        super().setUp()

        self.user1 = User(
            username="user1", email="user1@example.com", password_hash="test"
        )
        self.user2 = User(
            username="user2", email="user2@example.com", password_hash="test"
        )
        self.user3 = User(
            username="user3", email="user3@example.com", password_hash="test"
        )

        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        super().tearDown()

    def _create_post(self, user, timestamp, title="Test Post", content="Test content"):
        post = Post(user_id=user.id, timestamp=timestamp, title=title, content=content)
        db.session.add(post)
        db.session.commit()
        return post

    def _create_like(self, user, post, timestamp):
        like = Like(user_id=user.id, post_id=post.id, timestamp=timestamp)
        db.session.add(like)
        db.session.commit()
        return like

    def _create_comment(self, user, post, timestamp, content="Test comment"):
        comment = Comment(
            user_id=user.id, post_id=post.id, timestamp=timestamp, content=content
        )
        db.session.add(comment)
        db.session.commit()
        return comment

    def _create_share(self, user, post, timestamp):
        share = SharedPost(
            shared_by_user_id=user.id, original_post_id=post.id, shared_at=timestamp
        )
        db.session.add(share)
        db.session.commit()
        return share

    def _create_bookmark(self, user, post):
        bookmark = Bookmark(user_id=user.id, post_id=post.id)
        db.session.add(bookmark)
        db.session.commit()
        return bookmark

    def test_no_posts_returns_empty_list(self):
        """Test that an empty list is returned when there are no posts."""
        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(trending_posts, [])

    def test_recent_post_is_trending(self):
        """Test that a recent post appears in trending suggestions."""
        post1 = self._create_post(self.user2, self.now - timedelta(days=1))
        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(len(trending_posts), 1)
        self.assertEqual(trending_posts[0].id, post1.id)

    def test_old_post_not_trending_without_activity(self):
        """Test that an old post without recent activity is not trending."""
        self._create_post(self.user2, self.now - timedelta(days=10))
        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(trending_posts, [])

    def test_post_with_recent_like_is_trending(self):
        """Test that an old post with a recent like appears in trending."""
        post1 = self._create_post(self.user2, self.now - timedelta(days=10))
        self._create_like(self.user3, post1, self.now - timedelta(days=1))

        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(len(trending_posts), 1)
        self.assertEqual(trending_posts[0].id, post1.id)

    def test_post_with_recent_comment_is_trending(self):
        """Test that an old post with a recent comment appears in trending."""
        post1 = self._create_post(self.user2, self.now - timedelta(days=10))
        self._create_comment(self.user3, post1, self.now - timedelta(days=1))

        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(len(trending_posts), 1)
        self.assertEqual(trending_posts[0].id, post1.id)

    def test_post_with_recent_share_is_trending(self):
        """Test that an old post with a recent share appears in trending."""
        post1 = self._create_post(self.user2, self.now - timedelta(days=10))
        self._create_share(self.user3, post1, self.now - timedelta(days=1))

        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(len(trending_posts), 1)
        self.assertEqual(trending_posts[0].id, post1.id)

    def test_own_post_excluded(self):
        """Test that posts created by the suggesting user are excluded."""
        self._create_post(self.user1, self.now - timedelta(days=1))
        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(trending_posts, [])

    def test_bookmarked_post_excluded(self):
        """Test that posts bookmarked by the user are excluded."""
        post1 = self._create_post(self.user2, self.now - timedelta(days=1))
        self._create_bookmark(self.user1, post1)
        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(trending_posts, [])

    def test_liked_by_user_post_excluded(self):
        """Test that posts liked by the user are excluded."""
        post1 = self._create_post(self.user2, self.now - timedelta(days=1))
        self._create_like(self.user1, post1, self.now - timedelta(hours=1))
        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(trending_posts, [])

    def test_commented_by_user_post_excluded(self):
        """Test that posts commented on by the user are excluded."""
        post1 = self._create_post(self.user2, self.now - timedelta(days=1))
        self._create_comment(self.user1, post1, self.now - timedelta(hours=1))
        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(trending_posts, [])

    def test_limit_parameter(self):
        """Test that the limit parameter is respected."""
        self._create_post(self.user2, self.now - timedelta(days=1), title="Post 1")
        self._create_post(self.user2, self.now - timedelta(days=2), title="Post 2")
        self._create_post(self.user2, self.now - timedelta(days=3), title="Post 3")

        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=2, since_days=7
        )
        self.assertEqual(len(trending_posts), 2)

    def test_since_days_parameter(self):
        """Test that the since_days parameter correctly filters posts by recency of post or activity."""
        post_recent = self._create_post(self.user2, self.now - timedelta(days=3))
        post_old_recent_like = self._create_post(
            self.user3, self.now - timedelta(days=10)
        )
        self._create_like(self.user2, post_old_recent_like, self.now - timedelta(days=2))
        post_old_old_like = self._create_post(self.user3, self.now - timedelta(days=15))
        self._create_like(self.user2, post_old_old_like, self.now - timedelta(days=10))

        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        post_ids = {p.id for p in trending_posts}

        self.assertIn(post_recent.id, post_ids)
        self.assertIn(post_old_recent_like.id, post_ids)
        self.assertNotIn(post_old_old_like.id, post_ids)
        self.assertEqual(len(trending_posts), 2)

    def test_scoring_priority_recent_activity_over_just_recent_post(self):
        """
        Test that a slightly older post with more/stronger recent activity scores higher
        than a very recent post with no activity.
        WEIGHT_RECENT_LIKE = 1
        WEIGHT_RECENT_COMMENT = 3
        WEIGHT_RECENT_SHARE = 2
        TRENDING_POST_AGE_FACTOR_SCALE = 5
        """
        post_very_recent_no_interactions = self._create_post(
            self.user2, self.now - timedelta(hours=1)
        )
        post_older_with_comment = self._create_post(
            self.user3, self.now - timedelta(days=2)
        )
        self._create_comment(self.user2, post_older_with_comment, self.now - timedelta(hours=2))
        post_older_with_like = self._create_post(
            self.user2, self.now - timedelta(days=3)
        )
        self._create_like(self.user3, post_older_with_like, self.now - timedelta(hours=3))

        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=3, since_days=7
        )

        self.assertEqual(len(trending_posts), 3)
        self.assertEqual(trending_posts[0].id, post_older_with_comment.id)
        post_ids = {p.id for p in trending_posts}
        self.assertIn(post_very_recent_no_interactions.id, post_ids)
        self.assertIn(post_older_with_like.id, post_ids)

    def test_user_id_none(self):
        """Test behavior when user_id is None (guest user)."""
        post1 = self._create_post(self.user2, self.now - timedelta(days=1))
        self._create_like(self.user3, post1, self.now - timedelta(hours=1))

        trending_posts = suggest_trending_posts(user_id=None, limit=5, since_days=7)
        self.assertEqual(len(trending_posts), 1)
        self.assertEqual(trending_posts[0].id, post1.id)

    def test_interaction_weights(self):
        """Test that different interactions are weighted correctly in scoring."""
        post_a = self._create_post(self.user2, self.now - timedelta(days=2))
        self._create_comment(self.user3, post_a, self.now - timedelta(hours=1))
        post_b = self._create_post(self.user2, self.now - timedelta(days=2))
        self._create_share(self.user3, post_b, self.now - timedelta(hours=1))
        post_c = self._create_post(self.user2, self.now - timedelta(days=2))
        self._create_like(self.user3, post_c, self.now - timedelta(hours=1))

        trending_posts = suggest_trending_posts(
            user_id=self.user1.id, limit=3, since_days=7
        )
        self.assertEqual(len(trending_posts), 3)
        self.assertEqual(trending_posts[0].id, post_a.id)
        self.assertEqual(trending_posts[1].id, post_b.id)
        self.assertEqual(trending_posts[2].id, post_c.id)

    def test_multiple_interactions_on_one_post(self):
        """Test a post with multiple types of recent interactions."""
        post1 = self._create_post(self.user2, self.now - timedelta(days=3))
        self._create_like(self.user3, post1, self.now - timedelta(days=1))
        self._create_comment(self.user1, post1, self.now - timedelta(days=1))
        self._create_share(self.user3, post1, self.now - timedelta(days=1))

        trending_posts_user1 = suggest_trending_posts(
            user_id=self.user1.id, limit=5, since_days=7
        )
        self.assertEqual(trending_posts_user1, [])

        trending_posts_user2 = suggest_trending_posts(
            user_id=self.user2.id, limit=5, since_days=7
        )
        self.assertEqual(trending_posts_user2, [])

        trending_posts_user3 = suggest_trending_posts(
            user_id=self.user3.id, limit=5, since_days=7
        )
        self.assertEqual(len(trending_posts_user3), 0)


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
