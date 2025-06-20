# Assuming these are from common Flask libraries and local models
from flask_restful import Resource, reqparse
from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta

import app as main_app  # Modified import
from models import User, Post, Comment, db, Poll, PollOption, PollVote, PostLock


# Placeholder for UserListResource
class UserListResource(Resource):
    def get(self):
        return {"message": "User list resource placeholder"}, 200


# Placeholder for UserResource
class UserResource(Resource):
    def get(self, user_id):
        return {"message": f"User resource placeholder for user_id {user_id}"}, 200


class PostListResource(Resource):
    @jwt_required()
    def post(self):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)  # Use actual User model query
        if not user:
            return {"message": "User not found for provided token"}, 404

        parser = reqparse.RequestParser()
        parser.add_argument("title", required=True, help="Title cannot be blank")
        parser.add_argument("content", required=True, help="Content cannot be blank")
        data = parser.parse_args()

        new_post = Post(title=data["title"], content=data["content"], user_id=user.id)

        db.session.add(new_post)
        db.session.commit()

        # ID is auto-assigned by DB, no need to simulate.
        # if new_post.id is None:
        #     import random
        #     new_post.id = random.randint(1, 1000) # Simulate ID assignment

        post_dict = new_post.to_dict()
        main_app.broadcast_new_post(post_dict)  # Call using main_app

        return {"message": "Post created successfully", "post": post_dict}, 201


class CommentListResource(Resource):
    @jwt_required()
    def post(self, post_id):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return {"message": "User not found"}, 404

        post = Post.query.get(post_id)
        if not post:
            return {"message": "Post not found"}, 404

        parser = reqparse.RequestParser()
        parser.add_argument(
            "content", required=True, help="Comment content cannot be blank"
        )
        data = parser.parse_args()

        new_comment = Comment(content=data["content"], user_id=user.id, post_id=post.id)
        db.session.add(new_comment)
        db.session.commit()

        # Real-time notification for the new comment
        new_comment_data_for_post_room = {
            "id": new_comment.id,
            "post_id": new_comment.post_id,
            "author_username": new_comment.author.username,  # Accessing via backref
            "content": new_comment.content,
            "timestamp": new_comment.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        }
        main_app.socketio.emit(
            "new_comment_event", new_comment_data_for_post_room, room=f"post_{post_id}"
        )  # Use main_app

        comment_details = {
            "id": new_comment.id,
            "content": new_comment.content,
            "user_id": new_comment.user_id,
            "author_username": new_comment.author.username,
            "post_id": new_comment.post_id,
            "timestamp": new_comment.timestamp.isoformat(),
        }

        return {
            "message": "Comment created successfully",
            "comment": comment_details,
        }, 201


class PollListResource(Resource):
    @jwt_required()
    def get(self):
        polls = Poll.query.all()
        return {"polls": [poll.to_dict() for poll in polls]}, 200

    @jwt_required()
    def post(self):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return {"message": "User not found"}, 404

        parser = reqparse.RequestParser()
        parser.add_argument(
            "question", type=str, required=True, help="Question cannot be blank"
        )
        parser.add_argument(
            "options",
            type=list,
            location="json",
            required=True,
            help="Options cannot be blank",
        )
        data = parser.parse_args()

        if len(data["options"]) < 2:
            return {"message": "A poll must have at least two options"}, 400

        new_poll = Poll(question=data["question"], user_id=user.id)
        db.session.add(new_poll)
        # We need to flush to get the new_poll.id for the options if not using cascade persist for options from poll
        # However, SQLAlchemy handles this if options are added to new_poll.options directly before committing new_poll

        for option_text in data["options"]:
            if not option_text.strip():  # Ensure option text is not blank
                return {"message": "Poll option text cannot be blank"}, 400
            poll_option = PollOption(
                text=option_text, poll=new_poll
            )  # Associate with new_poll
            db.session.add(
                poll_option
            )  # Add option explicitly if not cascaded from poll.options.append

        # If Poll.options has cascade="all, delete-orphan" or similar with persist,
        # adding options to new_poll.options and then adding new_poll to session would be enough.
        # Let's assume explicit add for options for clarity or if cascade isn't set up for this.
        # db.session.add(new_poll) # new_poll is already added

        db.session.commit()
        return {"message": "Poll created successfully", "poll": new_poll.to_dict()}, 201


class PollResource(Resource):
    @jwt_required()
    def get(self, poll_id):
        poll = Poll.query.get(poll_id)
        if not poll:
            return {"message": "Poll not found"}, 404
        return {"poll": poll.to_dict()}, 200

    @jwt_required()
    def delete(self, poll_id):
        current_user_id = get_jwt_identity()
        poll = Poll.query.get(poll_id)
        if not poll:
            return {"message": "Poll not found"}, 404

        if poll.user_id != current_user_id:
            return {"message": "You are not authorized to delete this poll"}, 403

        db.session.delete(poll)
        db.session.commit()
        return {"message": "Poll deleted"}, 200


class PollVoteResource(Resource):
    @jwt_required()
    def post(
        self, poll_id
    ):  # The option_id was in the original plan, but typically it's in the request body.
        current_user_id = get_jwt_identity()
        user = User.query.get(
            current_user_id
        )  # Query user to ensure they exist, though jwt implies it.
        if not user:
            return {"message": "User not found"}, 404

        poll = Poll.query.get(poll_id)
        if not poll:
            return {"message": "Poll not found"}, 404

        parser = reqparse.RequestParser()
        parser.add_argument(
            "option_id", type=int, required=True, help="Option ID cannot be blank"
        )
        data = parser.parse_args()

        option_id = data["option_id"]
        poll_option = PollOption.query.filter_by(id=option_id, poll_id=poll.id).first()
        if not poll_option:
            return {
                "message": "Poll option not found or does not belong to this poll"
            }, 404

        existing_vote = PollVote.query.filter_by(
            user_id=current_user_id, poll_id=poll.id
        ).first()
        if existing_vote:
            return {"message": "You have already voted on this poll"}, 400

        new_vote = PollVote(
            user_id=current_user_id, poll_option_id=poll_option.id, poll_id=poll.id
        )
        db.session.add(new_vote)
        db.session.commit()

        return {"message": "Vote cast successfully"}, 201


class PostLockResource(Resource):
    @jwt_required()
    def post(self, post_id):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return {"message": "User not found for provided token"}, 404

        post = Post.query.get(post_id)
        if not post:
            return {"message": "Post not found"}, 404

        existing_lock = PostLock.query.filter_by(post_id=post.id).first()

        if existing_lock:
            if (
                existing_lock.user_id != current_user_id
                and existing_lock.expires_at > datetime.utcnow()
            ):
                return {
                    "message": "Post is currently locked by another user.",
                    "locked_by_username": existing_lock.user.username,
                    "expires_at": existing_lock.expires_at.isoformat(),
                }, 409
            else:
                db.session.delete(existing_lock)

        lock_duration_minutes = 15
        expires_at = datetime.utcnow() + timedelta(minutes=lock_duration_minutes)

        new_lock = PostLock(
            post_id=post.id, user_id=current_user_id, expires_at=expires_at
        )
        db.session.add(new_lock)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # main_app.app.logger.error(f"Error creating lock: {str(e)}") # app is not defined here
            print(
                f"Error creating lock: {str(e)}"
            )  # Use print or proper logging setup for api module
            return {"message": f"Error creating lock: {str(e)}"}, 500

        # Emit SocketIO event for lock acquired
        main_app.socketio.emit(
            "post_lock_acquired",
            {  # Use main_app
                "post_id": new_lock.post_id,
                "user_id": new_lock.user_id,
                "username": user.username,
                "expires_at": new_lock.expires_at.isoformat(),
            },
            room=f"post_{new_lock.post_id}",
        )

        return {
            "message": "Post locked successfully.",
            "lock_details": {
                "post_id": new_lock.post_id,
                "locked_by_user_id": new_lock.user_id,
                "locked_by_username": user.username,
                "locked_at": new_lock.locked_at.isoformat(),
                "expires_at": new_lock.expires_at.isoformat(),
            },
        }, 200

    @jwt_required()
    def delete(self, post_id):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return {"message": "User not found for provided token"}, 404

        post = Post.query.get(post_id)
        if not post:
            return {"message": "Post not found"}, 404

        lock_to_delete = PostLock.query.filter_by(post_id=post.id).first()

        if not lock_to_delete:
            return {"message": "Post is not currently locked."}, 404

        if lock_to_delete.user_id != current_user_id:
            # Example: if user.role not in ['admin', 'moderator']:
            return {
                "message": "You are not authorized to unlock this post as it is locked by another user.",
                "locked_by_username": lock_to_delete.user.username,
            }, 403

        db.session.delete(lock_to_delete)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # main_app.app.logger.error(f"Error unlocking post: {str(e)}")
            print(
                f"Error unlocking post: {str(e)}"
            )  # Use print or proper logging setup for api module
            return {"message": f"Error unlocking post: {str(e)}"}, 500

        # Emit SocketIO event for lock released
        main_app.socketio.emit(
            "post_lock_released",
            {  # Use main_app
                "post_id": post_id,
                "released_by_user_id": current_user_id,
                "username": user.username,
            },
            room=f"post_{post_id}",
        )

        return {"message": "Post unlocked successfully."}, 200


# Placeholder for PostResource
class PostResource(Resource):
    def get(self, post_id):
        return {"message": f"Post resource placeholder for post_id {post_id}"}, 200


# Placeholder for EventListResource
class EventListResource(Resource):
    def get(self):
        return {"message": "Event list resource placeholder"}, 200


# Placeholder for EventResource
class EventResource(Resource):
    def get(self, event_id):
        return {"message": f"Event resource placeholder for event_id {event_id}"}, 200


# Placeholder for RecommendationResource
class RecommendationResource(Resource):
    def get(self):
        return {"message": "Recommendation resource placeholder"}, 200


# Placeholder for PersonalizedFeedResource
class PersonalizedFeedResource(Resource):
    def get(self, user_id):
        return {
            "message": f"Personalized feed resource placeholder for user_id {user_id}"
        }, 200


# Placeholder for TrendingHashtagsResource
class TrendingHashtagsResource(Resource):
    def get(self):
        return {"message": "Trending hashtags resource placeholder"}, 200


# Placeholder for OnThisDayResource
class OnThisDayResource(Resource):
    def get(self):
        return {"message": "On This Day resource placeholder"}, 200


# Placeholder for UserStatsResource
class UserStatsResource(Resource):
    def get(self, user_id):
        return {
            "message": f"User stats resource placeholder for user_id {user_id}"
        }, 200


# Placeholder for SeriesListResource
class SeriesListResource(Resource):
    def get(self):
        return {"message": "Series list resource placeholder"}, 200


# Placeholder for SeriesResource
class SeriesResource(Resource):
    def get(self, series_id):
        return {
            "message": f"Series resource placeholder for series_id {series_id}"
        }, 200
