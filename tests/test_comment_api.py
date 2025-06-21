import unittest
import json

# from unittest.mock import patch, ANY # Removed as not visibly used
# from datetime import datetime, timedelta # Removed as not visibly used
# from app import app, db, socketio # COMMENTED OUT
from models import User, Post, Comment, UserBlock
from tests.test_base import AppTestCase


class TestCommentAPI(AppTestCase):

    def test_create_comment_success(self):
        # with app.app_context(): # Handled by test client or AppTestCase helpers
        # user1 is created in AppTestCase's setUp
        post_id = self._create_db_post(user_id=self.user1_id, title="Post for Commenting")

        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        comment_content = "This is a test comment."

        # This response will depend on whether the post_id actually exists if db is live
        response = self.client.post(f'/api/posts/{post_id}/comments', headers=headers, json={'content': comment_content})
        # For now, assume the route might not deeply check post existence or is mocked
        self.assertEqual(response.status_code, 201, f"Response data: {response.data.decode()}")
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Comment created successfully')
        self.assertIn('comment', data)
        comment_data = data['comment']
        self.assertEqual(comment_data['content'], comment_content)
        self.assertEqual(comment_data['user_id'], self.user1_id)
        self.assertEqual(comment_data['post_id'], post_id)
        self.assertEqual(comment_data['author_username'], self.user1.username)

    def test_create_comment_unauthenticated(self):
        # with app.app_context():
        # test_post = self._create_db_post(user_id=self.user1_id, title="Post for Unauth Comment")
        # post_id = test_post.id
        post_id = 1  # Mock post_id

        headers = {"Content-Type": "application/json"}
        response = self.client.post(
            f"/api/posts/{post_id}/comments",
            headers=headers,
            json={"content": "A comment attempt"},
        )
        self.assertEqual(response.status_code, 401)

    def test_create_comment_post_not_found(self):
        # with app.app_context():
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        non_existent_post_id = 99999

        response = self.client.post(
            f"/api/posts/{non_existent_post_id}/comments",
            headers=headers,
            json={"content": "Commenting on nothing"},
        )
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Post not found')

    def test_create_comment_missing_content(self):
        # with app.app_context():
        post_id = self._create_db_post(user_id=self.user1_id, title="Post for Invalid Comment")

        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        response = self.client.post(
            f"/api/posts/{post_id}/comments", headers=headers, json={}
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('message', data)
        # The actual message from api.py's reqparse is a dict when multiple errors,
        # or string if a single error message is directly returned by help=
        # For "Comment content cannot be blank", it's a direct help message.
        # However, reqparse by default puts errors under a 'message' key, and if specific field error,
        # it's often nested, e.g. data['message']['content']
        # Checking api.py, CommentListResource uses:
        # parser.add_argument("content", required=True, help="Comment content cannot be blank")
        # This usually results in: {'message': {'content': 'Comment content cannot be blank'}}
        # Let's adjust the assertion based on this.
        self.assertIn('content', data['message'])
        self.assertEqual(data['message']['content'], 'Comment content cannot be blank')

    def test_create_comment_by_different_user(self):
        # 1. Create a post by self.user1
        post_id = self._create_db_post(user_id=self.user1_id, title="Post by User1 for User2 Comment")
        # No longer need 'post_by_user1.id' as post_id directly gets the integer ID

        # 2. Create a second user, user2
        with self.app.app_context():
            user2 = User(username='user2', email='user2@example.com')
            user2.set_password('password')
            self.db.session.add(user2)
            self.db.session.commit()
            user2_id = user2.id
            user2_username = user2.username

        # 3. Log in as user2 to get an auth token
        token_user2 = self._get_jwt_token(user2_username, 'password')

        headers = {
            "Authorization": f"Bearer {token_user2}",
            "Content-Type": "application/json",
        }
        comment_content = "A comment from user2 on user1's post"

        response = self.client.post(
            f'/api/posts/{post_id}/comments',
            headers=headers,
            json={'content': comment_content}
        )

        self.assertEqual(response.status_code, 201, f"Response data: {response.data.decode()}")
        data = json.loads(response.data)

        self.assertEqual(data['message'], 'Comment created successfully')
        self.assertIn('comment', data)
        comment_data = data['comment']

        self.assertEqual(comment_data['content'], comment_content)
        self.assertEqual(comment_data['user_id'], user2_id)
        self.assertEqual(comment_data['author_username'], user2_username)
        self.assertEqual(comment_data['post_id'], post_id)

    def test_create_multiple_comments_on_same_post_by_same_user(self):
        post_id = self._create_db_post(user_id=self.user1_id, title="Post for Multiple Comments")
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # First comment
        comment1_content = "This is the first comment."
        response1 = self.client.post(f'/api/posts/{post_id}/comments', headers=headers, json={'content': comment1_content})
        self.assertEqual(response1.status_code, 201, f"Response data for comment 1: {response1.data.decode()}")
        data1 = json.loads(response1.data)
        self.assertEqual(data1['message'], 'Comment created successfully')
        self.assertIn('comment', data1)
        comment1_data = data1['comment']
        self.assertEqual(comment1_data['content'], comment1_content)
        self.assertEqual(comment1_data['user_id'], self.user1_id)
        self.assertEqual(comment1_data['post_id'], post_id)
        self.assertEqual(comment1_data['author_username'], self.user1.username)

        # Second comment
        comment2_content = "This is the second comment by the same user."
        response2 = self.client.post(f'/api/posts/{post_id}/comments', headers=headers, json={'content': comment2_content})
        self.assertEqual(response2.status_code, 201, f"Response data for comment 2: {response2.data.decode()}")
        data2 = json.loads(response2.data)
        self.assertEqual(data2['message'], 'Comment created successfully')
        self.assertIn('comment', data2)
        comment2_data = data2['comment']
        self.assertEqual(comment2_data['content'], comment2_content)
        self.assertEqual(comment2_data['user_id'], self.user1_id)
        self.assertEqual(comment2_data['post_id'], post_id)
        self.assertEqual(comment2_data['author_username'], self.user1.username)

        # Ensure comment IDs are different
        self.assertNotEqual(comment1_data['id'], comment2_data['id'], "Comment IDs should be different for multiple comments.")

    def test_create_comment_when_blocked_by_post_author(self):
        # 1. Create user2 (commenter)
        with self.app.app_context():
            user2 = User(username='blockeduser', email='blocked@example.com')
            user2.set_password('password')
            self.db.session.add(user2)
            self.db.session.commit()
            user2_id = user2.id
            # self.user1 is the post author, created in AppTestCase's setUp

        # 2. user1 (post author) creates a post
        post_id = self._create_db_post(user_id=self.user1_id, title="Post by User1, Comment by Blocked User2")

        # 3. Simulate user1 blocking user2 by creating a UserBlock entry
        with self.app.app_context():
            user_block = UserBlock(blocker_id=self.user1_id, blocked_id=user2_id)
            self.db.session.add(user_block)
            self.db.session.commit()

        # 4. user2 attempts to comment on user1's post
        token_user2 = self._get_jwt_token(user2.username, 'password')
        headers = {
            "Authorization": f"Bearer {token_user2}",
            "Content-Type": "application/json",
        }
        comment_content = "Attempting to comment while blocked."

        response = self.client.post(
            f'/api/posts/{post_id}/comments',
            headers=headers,
            json={'content': comment_content}
        )

        # 5. Assert that the API returns a 403 Forbidden status code
        self.assertEqual(response.status_code, 403, f"Response data: {response.data.decode()}")

        # 6. Assert that the API returns an appropriate error message
        data = json.loads(response.data)
        self.assertEqual(data['message'], "You are blocked by the post author and cannot comment.")
