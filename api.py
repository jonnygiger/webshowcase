# Assuming these are from common Flask libraries and local models
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import broadcast_new_post, socketio # Import the function and socketio from app.py
from models import User, Post, Comment, db # Import actual models

class PostListResource(Resource):
    @jwt_required()
    def post(self):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id) # Use actual User model query
        if not user:
            return {'message': 'User not found for provided token'}, 404

        parser = reqparse.RequestParser()
        parser.add_argument('title', required=True, help="Title cannot be blank")
        parser.add_argument('content', required=True, help="Content cannot be blank")
        data = parser.parse_args()

        new_post = Post(title=data['title'], content=data['content'], user_id=user.id)

        db.session.add(new_post)
        db.session.commit()

        # ID is auto-assigned by DB, no need to simulate.
        # if new_post.id is None:
        #     import random
        #     new_post.id = random.randint(1, 1000) # Simulate ID assignment

        post_dict = new_post.to_dict()
        broadcast_new_post(post_dict) # Call the imported function

        return {'message': 'Post created successfully', 'post': post_dict}, 201

class CommentListResource(Resource):
    @jwt_required()
    def post(self, post_id):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return {'message': 'User not found'}, 404

        post = Post.query.get(post_id)
        if not post:
            return {'message': 'Post not found'}, 404

        parser = reqparse.RequestParser()
        parser.add_argument('content', required=True, help='Comment content cannot be blank')
        data = parser.parse_args()

        new_comment = Comment(content=data['content'], user_id=user.id, post_id=post.id)
        db.session.add(new_comment)
        db.session.commit()

        # Real-time notification for the new comment
        new_comment_data_for_post_room = {
            'id': new_comment.id,
            'post_id': new_comment.post_id,
            'author_username': new_comment.author.username, # Accessing via backref
            'content': new_comment.content,
            'timestamp': new_comment.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }
        socketio.emit('new_comment_event', new_comment_data_for_post_room, room=f'post_{post_id}')

        comment_details = {
            'id': new_comment.id,
            'content': new_comment.content,
            'user_id': new_comment.user_id,
            'author_username': new_comment.author.username,
            'post_id': new_comment.post_id,
            'timestamp': new_comment.timestamp.isoformat()
        }

        return {'message': 'Comment created successfully', 'comment': comment_details}, 201
