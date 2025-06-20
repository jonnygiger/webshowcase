# Assuming these are from common Flask libraries and local models
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import broadcast_new_post, socketio # Import the function and socketio from app.py
from models import User, Post, Comment, db, Poll, PollOption, PollVote # Import actual models

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


class PollListResource(Resource):
    @jwt_required()
    def get(self):
        polls = Poll.query.all()
        return {'polls': [poll.to_dict() for poll in polls]}, 200

    @jwt_required()
    def post(self):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return {'message': 'User not found'}, 404

        parser = reqparse.RequestParser()
        parser.add_argument('question', type=str, required=True, help="Question cannot be blank")
        parser.add_argument('options', type=list, location='json', required=True, help="Options cannot be blank")
        data = parser.parse_args()

        if len(data['options']) < 2:
            return {'message': 'A poll must have at least two options'}, 400

        new_poll = Poll(question=data['question'], user_id=user.id)
        db.session.add(new_poll)
        # We need to flush to get the new_poll.id for the options if not using cascade persist for options from poll
        # However, SQLAlchemy handles this if options are added to new_poll.options directly before committing new_poll

        for option_text in data['options']:
            if not option_text.strip(): # Ensure option text is not blank
                return {'message': 'Poll option text cannot be blank'}, 400
            poll_option = PollOption(text=option_text, poll=new_poll) # Associate with new_poll
            db.session.add(poll_option) # Add option explicitly if not cascaded from poll.options.append

        # If Poll.options has cascade="all, delete-orphan" or similar with persist,
        # adding options to new_poll.options and then adding new_poll to session would be enough.
        # Let's assume explicit add for options for clarity or if cascade isn't set up for this.
        # db.session.add(new_poll) # new_poll is already added

        db.session.commit()
        return {'message': 'Poll created successfully', 'poll': new_poll.to_dict()}, 201


class PollResource(Resource):
    @jwt_required()
    def get(self, poll_id):
        poll = Poll.query.get(poll_id)
        if not poll:
            return {'message': 'Poll not found'}, 404
        return {'poll': poll.to_dict()}, 200

    @jwt_required()
    def delete(self, poll_id):
        current_user_id = get_jwt_identity()
        poll = Poll.query.get(poll_id)
        if not poll:
            return {'message': 'Poll not found'}, 404

        if poll.user_id != current_user_id:
            return {'message': 'You are not authorized to delete this poll'}, 403

        db.session.delete(poll)
        db.session.commit()
        return {'message': 'Poll deleted'}, 200


class PollVoteResource(Resource):
    @jwt_required()
    def post(self, poll_id): # The option_id was in the original plan, but typically it's in the request body.
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id) # Query user to ensure they exist, though jwt implies it.
        if not user:
            return {'message': 'User not found'}, 404

        poll = Poll.query.get(poll_id)
        if not poll:
            return {'message': 'Poll not found'}, 404

        parser = reqparse.RequestParser()
        parser.add_argument('option_id', type=int, required=True, help="Option ID cannot be blank")
        data = parser.parse_args()

        option_id = data['option_id']
        poll_option = PollOption.query.filter_by(id=option_id, poll_id=poll.id).first()
        if not poll_option:
            return {'message': 'Poll option not found or does not belong to this poll'}, 404

        existing_vote = PollVote.query.filter_by(user_id=current_user_id, poll_id=poll.id).first()
        if existing_vote:
            return {'message': 'You have already voted on this poll'}, 400

        new_vote = PollVote(user_id=current_user_id, poll_option_id=poll_option.id, poll_id=poll.id)
        db.session.add(new_vote)
        db.session.commit()

        return {'message': 'Vote cast successfully'}, 201
