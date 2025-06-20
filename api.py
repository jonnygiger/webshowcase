from flask import request
from flask_restful import Resource, reqparse
from models import db, User, Post, Event, Poll, PollOption, TrendingHashtag, Series, SeriesPost # Added Series, SeriesPost
from flask_jwt_extended import jwt_required, get_jwt_identity # Will be used later
from datetime import datetime
from sqlalchemy import extract # Added for OnThisDayResource

from recommendations import (
    suggest_posts_to_read,
    suggest_events_to_attend,
    suggest_polls_to_vote,
    suggest_groups_to_join, # Keep existing imports from RecommendationResource
    suggest_users_to_follow, # Keep existing imports from RecommendationResource
    get_personalized_feed_posts, # Import for PersonalizedFeedResource
    get_on_this_day_content # Import for OnThisDayResource
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
    # @jwt_required() # Assuming user_id from path means public access or different auth
    def get(self, user_id):
        # Ensure user exists, otherwise get_or_404 will abort with a 404 error
        User.query.get_or_404(user_id)

        # Call the new recommendation function to get personalized feed posts
        # This function is expected to return a list of Post objects (or similar data)
        # The subtask mentions a limit of 20
        feed_posts_data = get_personalized_feed_posts(user_id, limit=20)

        # Serialize the post objects. Assuming Post model has a to_dict() method.
        # If get_personalized_feed_posts already returns dicts, this step might differ.
        # For now, assuming it returns Post objects.
        if not feed_posts_data: # If no posts are found, return an empty list
            return {'feed_posts': []}, 200

        # Assuming feed_posts_data is a list of (Post, reason) tuples
        # or just Post objects. The subtask description implies it's just posts.
        # If it's (Post, reason) and reason is not needed, extract Post.
        # For this implementation, let's assume get_personalized_feed_posts returns a list of Post objects.

        serialized_posts = []
        if isinstance(feed_posts_data, list):
            # feed_posts_data is now a list of (Post, reason_string) tuples
            for post_object, reason_string in feed_posts_data:
                post_dict = post_object.to_dict()
                post_dict['recommendation_reason'] = reason_string
                serialized_posts.append(post_dict)
        # If get_personalized_feed_posts is guaranteed to return a list of Post objects:
        # serialized_posts = [post.to_dict() for post in feed_posts_data]

        return {'feed_posts': serialized_posts}, 200

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


class TrendingHashtagsResource(Resource):
    def get(self):
        trending_hashtags_from_db = TrendingHashtag.query.order_by(TrendingHashtag.rank.asc()).all()
        return {'trending_hashtags': [th.to_dict() for th in trending_hashtags_from_db]}, 200


class OnThisDayResource(Resource):
    @jwt_required()
    def get(self):
        current_user_id = get_jwt_identity()

        # Call the function from recommendations.py
        on_this_day_data = get_on_this_day_content(current_user_id)

        # Ensure the User object exists, though jwt_required and get_jwt_identity should handle auth.
        # If get_on_this_day_content requires a User object, this might need adjustment,
        # but it's designed to take user_id.
        user = User.query.get(current_user_id)
        if not user:
             return {'message': 'User not found'}, 404 # Should be rare due to JWT

        return {
            'on_this_day_posts': [post.to_dict() for post in on_this_day_data.get("posts", [])],
            'on_this_day_events': [event.to_dict() for event in on_this_day_data.get("events", [])]
        }, 200

class UserStatsResource(Resource):
    @jwt_required()
    def get(self, user_id):
        # current_user_id = get_jwt_identity() # Not needed if allowing public access to stats

        # Ensure the user_id from path is treated as the same type as current_user_id (usually int)
        try:
            target_user_id = int(user_id)
        except ValueError:
            return {'message': 'Invalid user ID format'}, 400

        # if target_user_id != current_user_id: # Assuming public access for now, or handled by @jwt_required if uncommented
            # Basic authorization: only the user can see their own stats.
            # In a more complex system, admins or friends might have access.
            # return {'message': 'Unauthorized to view these stats'}, 403

        user = User.query.get_or_404(target_user_id)

        stats = user.get_stats()
        return stats, 200

class SeriesListResource(Resource):
    def get(self):
        series_list = Series.query.order_by(Series.created_at.desc()).all()
        return {'series': [s.to_dict() for s in series_list]}, 200

class SeriesResource(Resource):
    def get(self, series_id):
        series = Series.query.get_or_404(series_id)
        return {'series': series.to_dict()}, 200
