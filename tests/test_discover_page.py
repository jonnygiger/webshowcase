import unittest
from unittest.mock import patch, ANY, MagicMock
from datetime import datetime, timezone

from tests.test_base import AppTestCase


class TestDiscoverPageViews(AppTestCase):
    @patch("social_app.core.views.get_personalized_feed_posts")
    def test_discover_page_shows_recommendation_reasons(
        self, mock_get_personalized_feed_posts
    ):
        self.login(self.user1.username, "password")

        with self.app.app_context():
            mock_author = MagicMock()
            mock_author.username = "author_username"

            mock_post = MagicMock()
            mock_post.id = 123
            mock_post.title = "Mocked Post Title"
            mock_post.content = "Mocked post content here that is long enough."
            mock_post.author = mock_author
            mock_post.user_id = self.user2_id
            mock_post.timestamp = datetime.now(timezone.utc)
            mock_post.comments = []
            mock_post.likes = []
            mock_post.reviews = []
            mock_post.hashtags = ""

        mock_reason = "Test reason for this post."
        mock_get_personalized_feed_posts.return_value = [(mock_post, mock_reason)]

        response = self.client.get("/discover")

        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        self.assertIn(f"Recommended: {mock_reason}", response_data)
        self.assertIn(mock_post.title, response_data)
        self.assertIn(mock_post.author.username, response_data)
        self.assertIn(mock_post.content[:50], response_data)

        mock_get_personalized_feed_posts.assert_called_once_with(
            user_id=self.user1.id, limit=15
        )

        self.logout()

    @patch("social_app.core.views.get_personalized_feed_posts")
    def test_discover_page_handles_post_with_image(
        self, mock_get_personalized_feed_posts
    ):
        self.login(self.user1.username, "password")

        with self.app.app_context():
            mock_author = MagicMock()
            mock_author.username = "image_author"

            mock_post = MagicMock()
            mock_post.id = 789
            mock_post.title = "Post with Image"
            mock_post.content = "This post has an image."
            mock_post.author = mock_author
            mock_post.timestamp = datetime.now(timezone.utc)
            mock_post.comments = []
            mock_post.likes = []
            mock_post.hashtags = ""
            mock_post.user_id = self.user2_id
            mock_post.reviews = []
            mock_post.image_url = "http://example.com/image.jpg"

        mock_reason = "Reason: post with image."
        mock_get_personalized_feed_posts.return_value = [(mock_post, mock_reason)]

        response = self.client.get("/discover")

        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        self.assertIn('<img src="http://example.com/image.jpg"', response_data)
        self.assertIn(mock_post.title, response_data)
        self.assertIn(mock_post.author.username, response_data)
        self.assertIn(mock_post.content[:50], response_data)
        self.assertIn(f"Recommended: {mock_reason}", response_data)

        mock_get_personalized_feed_posts.assert_called_once_with(
            user_id=self.user1.id, limit=15
        )

        self.logout()

    @patch("social_app.core.views.get_personalized_feed_posts")
    def test_discover_page_handles_special_characters_in_posts(
        self, mock_get_personalized_feed_posts
    ):
        self.login(self.user1.username, "password")

        with self.app.app_context():
            mock_author = MagicMock()
            mock_author.username = "special_char_author"

            mock_post = MagicMock()
            mock_post.id = 456
            mock_post.title = 'Test Post with <Special> & "Chars"'
            mock_post.content = (
                "This content has 'single' & \"double\" quotes, plus <tags>."
            )
            mock_post.author = mock_author
            mock_post.timestamp = datetime.now(timezone.utc)
            mock_post.comments = []
            mock_post.likes = []
            mock_post.hashtags = None
            mock_post.user_id = self.user1_id
            mock_post.reviews = []

        mock_reason = "Reason: testing special characters"
        mock_get_personalized_feed_posts.return_value = [(mock_post, mock_reason)]

        response = self.client.get("/discover")

        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        mock_get_personalized_feed_posts.assert_called_once_with(
            user_id=self.user1.id, limit=15
        )

        self.assertIn(
            "Test Post with &lt;Special&gt; &amp; &#34;Chars&#34;", response_data
        )
        self.assertIn(
            "This content has &#39;single&#39; &amp; &#34;double&#34; quotes, plus &lt;tags&gt;.",
            response_data,
        )
        self.assertIn(f"Recommended: {mock_reason}", response_data)

        self.logout()

    @patch("social_app.core.views.get_personalized_feed_posts")
    def test_discover_page_handles_posts_without_optional_data(
        self, mock_get_personalized_feed_posts
    ):
        self.login(self.user1.username, "password")

        with self.app.app_context():
            mock_author = MagicMock()
            mock_author.username = "testuser"

            mock_post = MagicMock()
            mock_post.id = 1
            mock_post.title = "Post without optional data"
            mock_post.content = "This is the content of the post."
            mock_post.author = mock_author
            mock_post.timestamp = datetime.now(timezone.utc)
            mock_post.comments = []
            mock_post.likes = []
            mock_post.hashtags = None
            mock_post.user_id = self.user1_id
            mock_post.reviews = []
            mock_post.image_url = None

        mock_reason = "A reason for this post."
        mock_get_personalized_feed_posts.return_value = [(mock_post, mock_reason)]

        response = self.client.get("/discover")

        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        self.assertIn(mock_post.title, response_data)
        self.assertIn(mock_post.author.username, response_data)
        self.assertIn(mock_post.content[:50], response_data)

        mock_get_personalized_feed_posts.assert_called_once_with(
            user_id=self.user1.id, limit=15
        )

        self.assertNotIn("Comments: 0", response_data)
        self.assertNotIn("Likes: 0", response_data)

        self.logout()

    @patch("social_app.core.views.get_personalized_feed_posts")
    def test_discover_page_empty_state(self, mock_get_personalized_feed_posts):
        self.login(self.user1.username, "password")

        mock_get_personalized_feed_posts.return_value = []

        response = self.client.get("/discover")

        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        self.assertIn(
            "No new post recommendations for you at the moment. Explore existing content or check back later!",
            response_data,
        )
        self.assertNotIn("Mocked Post Title", response_data)

        mock_get_personalized_feed_posts.assert_called_once_with(
            user_id=self.user1.id, limit=15
        )

        self.logout()
