import unittest
import json
from models import User, Post, Comment, UserBlock # Ensure User is imported for user creation
from tests.test_base import AppTestCase
from werkzeug.security import generate_password_hash # For creating user password

class TestCommentAPI(AppTestCase):

    def setUp(self):
        super().setUp()
        # self.user1, self.user2, self.user3 are created by AppTestCase's _setup_base_users()
        # and their IDs (self.user1_id etc.) are available and refreshed.
        # Specific posts needed by tests will be created within test methods or more specific setups.

    def test_create_comment_success(self):
        with self.app.app_context():
            post_obj = self._create_db_post(user_id=self.user1_id, title="Post for Commenting")
            self.assertIsNotNone(post_obj.id, "Post object must have an ID for comment creation test.")

            token = self._get_jwt_token(self.user1.username, "password")
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            comment_content = "This is a test comment."

            response = self.client.post(f'/api/posts/{post_obj.id}/comments', headers=headers, json={'content': comment_content})
            self.assertEqual(response.status_code, 201, f"Response data: {response.data.decode()}")
            data = json.loads(response.data)
            self.assertEqual(data['message'], 'Comment created successfully')
            self.assertIn('comment', data)
            comment_data = data['comment']
            self.assertEqual(comment_data['content'], comment_content)
            self.assertEqual(comment_data['user_id'], self.user1_id)
            self.assertEqual(comment_data['post_id'], post_obj.id)
            self.assertEqual(comment_data['author_username'], self.user1.username)

            # Verify the comment is in the database
            comment_in_db = self.db.session.get(Comment, data["comment"]["id"])
            self.assertIsNotNone(comment_in_db)
            self.assertEqual(comment_in_db.content, comment_content) # Use variable with period
            self.assertEqual(comment_in_db.user_id, self.user1.id)
            self.assertEqual(comment_in_db.post_id, post_obj.id)

    def test_create_comment_unauthenticated(self):
        post_obj = self._create_db_post(user_id=self.user1_id, title="Post for Unauth Comment")
        self.assertIsNotNone(post_obj.id)

        headers = {"Content-Type": "application/json"}
        response = self.client.post(
            f"/api/posts/{post_obj.id}/comments",
            headers=headers,
            json={"content": "A comment attempt"},
        )
        self.assertEqual(response.status_code, 401)

    def test_create_comment_post_not_found(self):
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

    def test_create_comment_on_non_existent_post_with_specific_message(self):
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        non_existent_post_id = 99999

        response = self.client.post(
            f"/api/posts/{non_existent_post_id}/comments",
            headers=headers,
            json={"content": "Attempting to comment on a non-existent post"},
        )
        self.assertEqual(response.status_code, 404, f"Response data: {response.data.decode()}")
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Post not found', "Error message for non-existent post did not match.")

    def test_create_comment_missing_content(self):
        post_obj = self._create_db_post(user_id=self.user1_id, title="Post for Invalid Comment")
        self.assertIsNotNone(post_obj.id)

        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        response = self.client.post(
            f"/api/posts/{post_obj.id}/comments", headers=headers, json={}
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('message', data)
        self.assertIn('content', data['message'])
        self.assertEqual(data['message']['content'], 'Comment content cannot be blank')

    def test_create_comment_by_different_user(self):
        post_obj_by_user1 = self._create_db_post(user_id=self.user1_id, title="Post by User1 for User2 Comment")
        self.assertIsNotNone(post_obj_by_user1.id)

        with self.app.app_context():
            user2_for_comment = User(username='user2_commenter', email='user2commenter@example.com', password_hash=generate_password_hash('password'))
            self.db.session.add(user2_for_comment)
            self.db.session.commit()
            self.db.session.refresh(user2_for_comment)
            user2_id = user2_for_comment.id
            user2_username = user2_for_comment.username

        token_user2 = self._get_jwt_token(user2_username, 'password')
        headers = {
            "Authorization": f"Bearer {token_user2}",
            "Content-Type": "application/json",
        }
        comment_content = "A comment from user2 on user1's post"

        response = self.client.post(
            f'/api/posts/{post_obj_by_user1.id}/comments',
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
        self.assertEqual(comment_data['post_id'], post_obj_by_user1.id)

    def test_create_multiple_comments_on_same_post_by_same_user(self):
        post_obj = self._create_db_post(user_id=self.user1_id, title="Post for Multiple Comments")
        self.assertIsNotNone(post_obj.id)
        token = self._get_jwt_token(self.user1.username, "password")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        comment1_content = "This is the first comment."
        response1 = self.client.post(f'/api/posts/{post_obj.id}/comments', headers=headers, json={'content': comment1_content})
        self.assertEqual(response1.status_code, 201, f"Response data for comment 1: {response1.data.decode()}")
        data1 = json.loads(response1.data)
        self.assertEqual(data1['message'], 'Comment created successfully')
        self.assertIn('comment', data1)
        comment1_data = data1['comment']
        self.assertEqual(comment1_data['content'], comment1_content)
        self.assertEqual(comment1_data['user_id'], self.user1_id)
        self.assertEqual(comment1_data['post_id'], post_obj.id)
        self.assertEqual(comment1_data['author_username'], self.user1.username)

        comment2_content = "This is the second comment by the same user."
        response2 = self.client.post(f'/api/posts/{post_obj.id}/comments', headers=headers, json={'content': comment2_content})
        self.assertEqual(response2.status_code, 201, f"Response data for comment 2: {response2.data.decode()}")
        data2 = json.loads(response2.data)
        self.assertEqual(data2['message'], 'Comment created successfully')
        self.assertIn('comment', data2)
        comment2_data = data2['comment']
        self.assertEqual(comment2_data['content'], comment2_content)
        self.assertEqual(comment2_data['user_id'], self.user1_id)
        self.assertEqual(comment2_data['post_id'], post_obj.id)
        self.assertEqual(comment2_data['author_username'], self.user1.username)
        self.assertNotEqual(comment1_data['id'], comment2_data['id'])

    def test_create_comment_when_blocked_by_post_author(self):
        with self.app.app_context():
            user2_block_test = User(username='blocked_commenter', email='blockedcommenter@example.com', password_hash=generate_password_hash('password'))
            self.db.session.add(user2_block_test)
            self.db.session.commit()
            self.db.session.refresh(user2_block_test)
            user2_id = user2_block_test.id

        post_by_user1 = self._create_db_post(user_id=self.user1_id, title="Post by User1, Comment by Blocked User2")
        self.assertIsNotNone(post_by_user1.id)

        with self.app.app_context():
            user_block = UserBlock(blocker_id=self.user1_id, blocked_id=user2_id)
            self.db.session.add(user_block)
            self.db.session.commit()

        token_user2 = self._get_jwt_token(user2_block_test.username, 'password')
        headers = {
            "Authorization": f"Bearer {token_user2}",
            "Content-Type": "application/json",
        }
        comment_content = "Attempting to comment while blocked."

        response = self.client.post(
            f'/api/posts/{post_by_user1.id}/comments',
            headers=headers,
            json={'content': comment_content}
        )
        self.assertEqual(response.status_code, 403, f"Response data: {response.data.decode()}")
        data = json.loads(response.data)
        self.assertEqual(data['message'], "You are blocked by the post author and cannot comment.")
