import unittest
import json

# from unittest.mock import patch, ANY # Removed as not visibly used
# from datetime import datetime, timedelta # Removed as not visibly used
# from app import app, db, socketio # COMMENTED OUT
from models import User, Post, Comment
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
