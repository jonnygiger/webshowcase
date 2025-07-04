import unittest
from unittest.mock import patch, ANY, MagicMock
from datetime import datetime, timezone  # Removed timedelta

# Updated commented-out imports for future reference:
# from social_app import create_app, db, socketio
# from social_app.models.db_models import User, Post # Add other models if needed
from tests.test_base import AppTestCase


class TestDiscoverPageViews(AppTestCase):
    @patch(
        "social_app.services.recommendations_service.get_personalized_feed_posts" # Corrected patch target
    )
    def test_discover_page_shows_recommendation_reasons(
        self, mock_get_personalized_feed_posts
    ):
        # Setup: Login as a user
        self.login(
            self.user1.username, "password"
        )  # Assumes user1 is created in AppTestCase.setUp

        # Mocking get_personalized_feed_posts
        # Ensure app context for MagicMock with spec on SQLAlchemy models
        with self.app.app_context():
            # Create a mock author object
            mock_author = MagicMock()
            mock_author.username = "author_username"  # Reverted username

            # Create a mock post object
            mock_post = MagicMock()
            mock_post.id = 123
            mock_post.title = "Mocked Post Title"
        # Ensure content is not None for slicing in template (post.content[:200])
        mock_post.content = "Mocked post content here that is long enough."
        mock_post.author = mock_author
        # Add other attributes that might be accessed if post.to_dict() was called, or by template directly
        mock_post.user_id = self.user2_id  # Assuming user2 might be an author
        mock_post.timestamp = datetime.now(timezone.utc)
        mock_post.comments = []  # For len(post.comments) if used
        mock_post.likes = []  # For len(post.likes) if used
        mock_post.reviews = (
            []
        )  # For len(post.reviews) if used # Assuming reviews is not used or part of Post spec
        mock_post.hashtags = ""  # Assuming hashtags is an attribute
        # mock_post.is_featured = False # Assuming is_featured is an attribute
        # mock_post.featured_at = None # Assuming featured_at is an attribute
        # mock_post.last_edited = None # Assuming last_edited is an attribute

        mock_reason = "Test reason for this post."
        # The function is expected to return a list of (Post, reason_string) tuples
        mock_get_personalized_feed_posts.return_value = [(mock_post, mock_reason)]

        # Execution: Make a GET request to /discover
        response = self.client.get("/discover")

        # Assertions
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        # Check for the reason string
        self.assertIn(f"Recommended: {mock_reason}", response_data)
        # Check for post details
        self.assertIn(mock_post.title, response_data)
        self.assertIn(mock_post.author.username, response_data)
        # Check a snippet of content if it's displayed
        self.assertIn(mock_post.content[:50], response_data)

        # Assert that the mock was called correctly
        mock_get_personalized_feed_posts.assert_called_once_with(
            self.user1_id, limit=15
        )

        self.logout()

    @patch("social_app.services.recommendations_service.get_personalized_feed_posts") # Corrected patch target
    def test_discover_page_handles_post_with_image(
        self, mock_get_personalized_feed_posts
    ):
        # Setup: Login as a user
        self.login(
            self.user1.username, "password"
        )  # Assumes user1 is created in AppTestCase.setUp

        # Mocking get_personalized_feed_posts
        # Ensure app context for MagicMock with spec on SQLAlchemy models
        with self.app.app_context():
            # Create a mock author object
            mock_author = MagicMock()
            mock_author.username = "image_author"

            # Create a mock post object
            mock_post = MagicMock()
            mock_post.id = 789
            mock_post.title = "Post with Image"
            mock_post.content = "This post has an image."
            mock_post.author = mock_author
            mock_post.timestamp = datetime.now(timezone.utc)
            mock_post.comments = []
            mock_post.likes = []
            mock_post.hashtags = ""
            mock_post.user_id = self.user2_id  # Assuming user2 might be an author
            mock_post.reviews = []
            mock_post.image_url = (
                "http://example.com/image.jpg"  # Image URL for the test
            )

        mock_reason = "Reason: post with image."
        # The function is expected to return a list of (Post, reason_string) tuples
        mock_get_personalized_feed_posts.return_value = [(mock_post, mock_reason)]

        # Execution: Make a GET request to /discover
        response = self.client.get("/discover")

        # Assertions
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        # Check for the image tag
        # This assertion might need adjustment based on how images are rendered in the template
        self.assertIn(
            '<img src="http://example.com/image.jpg"', response_data
        )  # Made assertion more flexible

        # Check for other post details
        self.assertIn(mock_post.title, response_data)
        self.assertIn(mock_post.author.username, response_data)
        self.assertIn(mock_post.content[:50], response_data)  # Check for a snippet
        self.assertIn(f"Recommended: {mock_reason}", response_data)

        # Assert that the mock was called correctly
        mock_get_personalized_feed_posts.assert_called_once_with(
            self.user1_id, limit=15
        )

        self.logout()

    @patch("social_app.services.recommendations_service.get_personalized_feed_posts") # Corrected patch target
    def test_discover_page_handles_special_characters_in_posts(
        self, mock_get_personalized_feed_posts
    ):
        # Setup: Login as a user
        self.login(self.user1.username, "password")

        # Mocking get_personalized_feed_posts
        with self.app.app_context():
            # Create a mock author object
            mock_author = MagicMock()
            mock_author.username = "special_char_author"

            # Create a mock post object
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
        # The function is expected to return a list of (Post, reason_string) tuples
        mock_get_personalized_feed_posts.return_value = [(mock_post, mock_reason)]

        # Execution: Make a GET request to /discover
        response = self.client.get("/discover")

        # Assertions
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        # Assert that the mock was called correctly
        mock_get_personalized_feed_posts.assert_called_once_with(
            self.user1_id, limit=15
        )

        # Assertions for post's title and content
        # Note: These assertions might need adjustment based on how Jinja2 escapes characters
        self.assertIn(
            "Test Post with &lt;Special&gt; &amp; &#34;Chars&#34;", response_data
        )
        self.assertIn(
            "This content has &#39;single&#39; &amp; &#34;double&#34; quotes, plus &lt;tags&gt;.",
            response_data,
        )

        # Assert that the recommendation reason is in the response data
        self.assertIn(f"Recommended: {mock_reason}", response_data)

        self.logout()

    @patch("social_app.services.recommendations_service.get_personalized_feed_posts") # Corrected patch target
    def test_discover_page_handles_posts_without_optional_data(
        self, mock_get_personalized_feed_posts
    ):
        # Setup: Login as a user
        self.login(self.user1.username, "password")

        # Mocking get_personalized_feed_posts
        with self.app.app_context():
            mock_author = MagicMock()
            mock_author.username = "testuser"

            mock_post = MagicMock()
            mock_post.id = 1
            mock_post.title = "Post without optional data"
            mock_post.content = "This is the content of the post."
            mock_post.author = mock_author
            mock_post.timestamp = datetime.now(timezone.utc)
            # Optional data missing
            mock_post.comments = []
            mock_post.likes = []
            mock_post.hashtags = None  # Or ""
            # Ensure other attributes that might be accessed are present
            mock_post.user_id = self.user1_id  # Or some other relevant user_id
            mock_post.reviews = []
            # mock_post.is_featured = False
            # mock_post.featured_at = None
            # mock_post.last_edited = None

        # The function is expected to return a list of (Post, reason_string) tuples
        # For this test, the reason string is not critical but should be present
        mock_reason = "A reason for this post."
        mock_get_personalized_feed_posts.return_value = [(mock_post, mock_reason)]

        # Execution: Make a GET request to /discover
        response = self.client.get("/discover")

        # Assertions
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        # Check for essential post details
        self.assertIn(mock_post.title, response_data)
        self.assertIn(mock_post.author.username, response_data)
        self.assertIn(mock_post.content[:50], response_data)  # Check for a snippet

        # Assert that the mock was called correctly
        mock_get_personalized_feed_posts.assert_called_once_with(
            self.user1_id, limit=15
        )

        # Assert that elements related to optional data are NOT present
        # This depends on how the template renders missing data.
        # For example, if comments count is only shown if > 0
        self.assertNotIn("Comments: 0", response_data)  # Assuming "Comments: X" format
        self.assertNotIn("Likes: 0", response_data)  # Assuming "Likes: X" format
        # If hashtags are displayed in a specific way, check they are not there
        # e.g., self.assertNotIn("#", response_data) if hashtags always start with #

        self.logout()

    @patch("social_app.services.recommendations_service.get_personalized_feed_posts") # Corrected patch target
    def test_discover_page_empty_state(self, mock_get_personalized_feed_posts):
        # Setup: Login as a user
        self.login(self.user1.username, "password")

        # Mocking get_personalized_feed_posts to return an empty list
        mock_get_personalized_feed_posts.return_value = []

        # Execution: Make a GET request to /discover
        response = self.client.get("/discover")

        # Assertions
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)

        # Check for a message indicating no recommendations
        # This message will depend on the actual implementation in the template
        self.assertIn(
            "No new post recommendations for you at the moment. Explore existing content or check back later!",
            response_data,
        )
        # Or, if there's a more generic message or a specific HTML structure:
        # self.assertIn("No posts to display.", response_data)

        # Ensure no mock post details are accidentally shown
        # (Example from the other test, assuming 'Mocked Post Title' wouldn't appear)
        self.assertNotIn("Mocked Post Title", response_data)
        # self.assertNotIn("author_username", response_data) # Removed, "author_username" is in JS code

        # Assert that the mock was called correctly
        mock_get_personalized_feed_posts.assert_called_once_with(
            self.user1_id, limit=15
        )

        self.logout()
