from flask import request
from flask_restful import Resource, reqparse
from models import db, User, Post, Event, Poll, PollOption # Assuming models.py contains these
from flask_jwt_extended import jwt_required, get_jwt_identity # Will be used later
from datetime import datetime

from recommendations import (
    suggest_posts_to_read,
    suggest_events_to_attend,
    suggest_polls_to_vote,
    suggest_groups_to_join, # Keep existing imports from RecommendationResource
    suggest_users_to_follow # Keep existing imports from RecommendationResource
)

# Placeholder for authentication logic for now
# In a real scenario, you would use @jwt_required and get_jwt_identity

class UserListResource(Resource):
    def get(self):
        users = User.query.all()
        return {'users': [user.to_dict() for user in users]}, 200

class UserResource(Resource):
    def get(self, user_id):
        user = User.query.get_or_404(user_id)
        return {'user': user.to_dict()}, 200

class PostListResource(Resource):
    def get(self):
        posts = Post.query.all()
        return {'posts': [post.to_dict() for post in posts]}, 200

    @jwt_required()
    def post(self):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            # This case should ideally not happen if JWT is valid and user exists
            return {'message': 'User not found for provided token'}, 404

        parser = reqparse.RequestParser()
        parser.add_argument('title', required=True, help="Title cannot be blank")
        parser.add_argument('content', required=True, help="Content cannot be blank")
        data = parser.parse_args()

        new_post = Post(title=data['title'], content=data['content'], user_id=user.id)
        db.session.add(new_post)
        db.session.commit()
        return {'message': 'Post created successfully', 'post': new_post.to_dict()}, 201

class PostResource(Resource):
    def get(self, post_id):
        post = Post.query.get_or_404(post_id)
        return {'post': post.to_dict()}, 200

    @jwt_required()
    def put(self, post_id):
        current_user_id = get_jwt_identity()
        post = Post.query.get_or_404(post_id)

        if post.user_id != current_user_id:
            return {'message': 'Unauthorized to edit this post'}, 403

        parser = reqparse.RequestParser()
        parser.add_argument('title', required=False)
        parser.add_argument('content', required=False)
        data = parser.parse_args()

        if data.get('title') is not None: # Check for None explicitly to allow empty strings if desired
            post.title = data['title']
        if data.get('content') is not None:
            post.content = data['content']

        db.session.commit()
        return {'message': 'Post updated successfully', 'post': post.to_dict()}, 200

    @jwt_required()
    def delete(self, post_id):
        current_user_id = get_jwt_identity()
        post = Post.query.get_or_404(post_id)

        if post.user_id != current_user_id:
           return {'message': 'Unauthorized to delete this post'}, 403

        db.session.delete(post)
        db.session.commit()
        return {'message': 'Post deleted successfully'}, 200

class EventListResource(Resource):
    def get(self):
        events = Event.query.all()
        return {'events': [event.to_dict() for event in events]}, 200

    @jwt_required()
    def post(self):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return {'message': 'User not found for provided token'}, 404

        parser = reqparse.RequestParser()
        parser.add_argument('title', required=True, help="Title cannot be blank")
        parser.add_argument('description', required=False)
        parser.add_argument('date', required=True, help="Date cannot be blank")
        parser.add_argument('time', required=False)
        parser.add_argument('location', required=False)
        data = parser.parse_args()

        new_event = Event(
            title=data['title'],
            description=data.get('description'),
            date=data['date'],
            time=data.get('time'),
            location=data.get('location'),
            user_id=user.id
        )
        db.session.add(new_event)
        db.session.commit()
        return {'message': 'Event created successfully', 'event': new_event.to_dict()}, 201

class EventResource(Resource):
    def get(self, event_id):
        event = Event.query.get_or_404(event_id)
        return {'event': event.to_dict()}, 200

# Note: PUT and DELETE for individual events can be added if needed,
# similar to PostResource, including authorization checks.
# For now, focusing on GET for single event and POST for list.

class PersonalizedFeedResource(Resource):
    @jwt_required()
    def get(self):
        current_user_id = get_jwt_identity()
        feed_items = []

        # Get recommended posts
        recommended_posts_with_reasons = suggest_posts_to_read(current_user_id, limit=10)
        for post_obj, reason in recommended_posts_with_reasons:
            if post_obj:
                feed_items.append({
                    'type': 'post',
                    'id': post_obj.id,
                    'title': post_obj.title,
                    'content': post_obj.content,
                    'author_username': post_obj.author.username if post_obj.author else 'Unknown',
                    'timestamp': post_obj.timestamp.isoformat() if post_obj.timestamp else None,
                    'reason': reason
                })

        # Get recommended events
        recommended_events = suggest_events_to_attend(current_user_id, limit=5)
        for event_obj in recommended_events:
            if event_obj:
                feed_items.append({
                    'type': 'event',
                    'id': event_obj.id,
                    'title': event_obj.title,
                    'description': event_obj.description,
                    'date': event_obj.date, # Assuming date is already a string
                    'time': event_obj.time, # Assuming time is already a string
                    'location': event_obj.location,
                    'organizer_username': event_obj.organizer.username if event_obj.organizer else 'Unknown',
                    # Use created_at for sorting, event.date is specific to the event's occurrence
                    'timestamp': event_obj.created_at.isoformat() if event_obj.created_at else None
                })

        # Get recommended polls
        recommended_polls = suggest_polls_to_vote(current_user_id, limit=5)
        for poll_obj in recommended_polls:
            if poll_obj:
                options_data = []
                for option in poll_obj.options: # Assuming poll_obj.options is a list of PollOption
                    options_data.append({
                        'id': option.id,
                        'text': option.text,
                        'vote_count': len(option.votes) # Assuming option.votes is a list/collection of votes
                    })
                feed_items.append({
                    'type': 'poll',
                    'id': poll_obj.id,
                    'question': poll_obj.question,
                    'creator_username': poll_obj.creator.username if poll_obj.creator else 'Unknown',
                    'options': options_data,
                    'timestamp': poll_obj.created_at.isoformat() if poll_obj.created_at else None
                })

        # Sort feed items by timestamp (most recent first)
        # Ensure all items have a valid timestamp; handle None if necessary, though recommendations should have them
        feed_items.sort(key=lambda x: x['timestamp'] if x['timestamp'] else datetime.min.isoformat(), reverse=True)

        return {'feed_items': feed_items}, 200

from flask import jsonify # Added jsonify
# Note: recommendation function imports are now at the top of the file
from models import Group # User, Post, Event, Poll are already imported at the top

class RecommendationResource(Resource):
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument('user_id', type=int, required=True, help='User ID is required and must be an integer.')
        args = parser.parse_args()

        user_id = args['user_id']

        user = User.query.get(user_id)
        if not user:
            return {'message': 'User not found'}, 404

        # Get suggestions
        posts = suggest_posts_to_read(user_id, limit=5)
        groups = suggest_groups_to_join(user_id, limit=3)
        events = suggest_events_to_attend(user_id, limit=3)
        users_to_follow = suggest_users_to_follow(user_id, limit=3)
        polls = suggest_polls_to_vote(user_id, limit=3)

        # Serialize results
        suggested_posts = [post.to_dict() for post in posts]
        suggested_groups = [group.to_dict() for group in groups]
        suggested_events = [event.to_dict() for event in events]
        suggested_users = [u.to_dict() for u in users_to_follow]
        suggested_polls = [poll.to_dict() for poll in polls]

        return {
            'user_id': user_id,
            'suggested_posts': suggested_posts,
            'suggested_groups': suggested_groups,
            'suggested_events': suggested_events,
            'suggested_users_to_follow': suggested_users,
            'suggested_polls_to_vote': suggested_polls
        }, 200
