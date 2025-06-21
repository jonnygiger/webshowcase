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
    def test_create_comment_by_different_user(self):
        # 1. Create a post by self.user1
        post_by_user1 = self._create_db_post(user_id=self.user1_id, title="Post by User1 for User2 Comment")
        post_id = post_by_user1.id

        # 2. Create a second user, user2
        user2 = User(username='user2', email='user2@example.com')
        user2.set_password('password') # Assuming set_password method exists and hashes
        self.db.session.add(user2)
        self.db.session.commit()
        # It's good practice to refresh user2 to get any DB-generated defaults or ensure it's fully loaded
        # self.db.session.refresh(user2) # Optional, but can be useful
        user2_id = user2.id
        user2_username = user2.username

        # 3. Log in as user2 to get an auth token
        token_user2 = self._get_jwt_token(user2_username, 'password')

        # Store variables for the next steps (actual API call and assertions)
        # For example, by assigning them to self or returning them if this were a helper
        # For now, just ensure they are defined in the scope of the test method.
        # self.post_id_for_user2_comment = post_id
        # self.token_for_user2 = token_user2
        # self.user2_id_for_comment = user2_id
        # self.user2_username_for_comment = user2_username
        # pass # Next steps will add the API call and assertions

        # 4. Make the API call to create a comment
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

        # Store for assertions in the next step, e.g.:
        # self.response_data = json.loads(response.data)
        # self.response_status_code = response.status_code
        # self.comment_content_sent = comment_content
        # pass # Next step will add assertions

        # 5. Assert the expected outcome
        self.assertEqual(response.status_code, 201, f"Response data: {response.data.decode()}")
        data = json.loads(response.data)

        self.assertEqual(data['message'], 'Comment created successfully')
        self.assertIn('comment', data)
        comment_data = data['comment']

        self.assertEqual(comment_data['content'], comment_content)
        self.assertEqual(comment_data['user_id'], user2_id)
        self.assertEqual(comment_data['author_username'], user2_username)
        self.assertEqual(comment_data['post_id'], post_id)
