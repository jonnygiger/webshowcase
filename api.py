# Assuming these are from common Flask libraries and local models
from flask_restful import Resource, reqparse
from flask import request, g, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import os

# import app as main_app  # Removed to break circular dependency
from notifications import broadcast_new_post # Import the moved function
from models import User, Post, Comment, Like, Friendship, Event, EventRSVP, Poll, PollOption, PollVote, db, PostLock, SharedFile, UserBlock


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
        current_user_id = int(get_jwt_identity())
        user = db.session.get(User, current_user_id)  # Use actual User model query
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
        broadcast_new_post(post_dict)  # Call imported function directly

        return {"message": "Post created successfully", "post": post_dict}, 201


class CommentListResource(Resource):
    @jwt_required()
    def post(self, post_id):
        current_user_id = int(get_jwt_identity())
        user = db.session.get(User, current_user_id)
        if not user:
            return {"message": "User not found"}, 404

        post = db.session.get(Post, post_id)
        if not post:
            return {"message": "Post not found"}, 404

        # Placeholder for block check logic
        # Conceptually, this will check if post.author has blocked user (current_user_id)
        # For now, using 'if False:' to avoid breaking existing functionality.
        # This will be replaced with actual logic once UserBlock model and relationships are implemented.
        # Example: if post.author.has_blocked(user):
        # Check if the post author has blocked the current user
        if UserBlock.query.filter_by(blocker_id=post.user_id, blocked_id=user.id).first():
            return {"message": "You are blocked by the post author and cannot comment."}, 403

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
        current_app.extensions['socketio'].emit(
            "new_comment_event", new_comment_data_for_post_room, room=f"post_{post_id}"
        )  # Use current_app

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
        current_user_id = int(get_jwt_identity())
        user = db.session.get(User, current_user_id)
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
        poll = db.session.get(Poll, poll_id)
        if not poll:
            return {"message": "Poll not found"}, 404
        return {"poll": poll.to_dict()}, 200

    @jwt_required()
    def delete(self, poll_id):
        current_user_id = int(get_jwt_identity())
        poll = db.session.get(Poll, poll_id)
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
        current_user_id = int(get_jwt_identity())
        user = db.session.get(User,
            current_user_id
        )  # Query user to ensure they exist, though jwt implies it.
        if not user:
            return {"message": "User not found"}, 404

        poll = db.session.get(Poll, poll_id)
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
        current_user_id = int(get_jwt_identity())
        user = db.session.get(User, current_user_id)
        if not user:
            return {"message": "User not found for provided token"}, 404

        post = db.session.get(Post, post_id)
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
            else: # If same user OR (other user AND expired lock)
                db.session.delete(existing_lock)
                db.session.flush() # Ensure DELETE is processed before potential INSERT

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
            current_app.logger.error(f"Error creating lock: {str(e)}")
            return {"message": f"Error creating lock: {str(e)}"}, 500

        # Emit SocketIO event for lock acquired
        current_app.extensions['socketio'].emit(
            "post_lock_acquired",
            {
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
        current_user_id = int(get_jwt_identity())
        user = db.session.get(User, current_user_id)
        if not user:
            return {"message": "User not found for provided token"}, 404

        post = db.session.get(Post, post_id)
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
            current_app.logger.error(f"Error unlocking post: {str(e)}")
            return {"message": f"Error unlocking post: {str(e)}"}, 500

        # Emit SocketIO event for lock released
        current_app.extensions['socketio'].emit(
            "post_lock_released",
            {
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


# RecommendationResource Implementation
class RecommendationResource(Resource):
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "user_id",
            type=int,
            required=True,
            help="User ID is required and must be an integer.",
            location="args",
        )
        args = parser.parse_args()
        user_id = args["user_id"]

        user = db.session.get(User, user_id)
        if not user:
            return {"message": f"User {user_id} not found"}, 404

        # Import recommendation functions
        from recommendations import (
            suggest_posts_to_read,
            suggest_groups_to_join,
            suggest_events_to_attend,
            suggest_users_to_follow,
            suggest_polls_to_vote,
        )

        # Call recommendation functions
        limit = 5
        raw_posts = suggest_posts_to_read(user_id, limit=limit)
        raw_groups = suggest_groups_to_join(user_id, limit=limit)
        raw_events = suggest_events_to_attend(user_id, limit=limit)
        raw_users = suggest_users_to_follow(user_id, limit=limit)
        raw_polls = suggest_polls_to_vote(user_id, limit=limit)

        # Serialize results
        suggested_posts_data = []
        for post_obj, reason_str in raw_posts:
            suggested_posts_data.append({
                "id": post_obj.id,
                "title": post_obj.title,
                "author_username": post_obj.author.username if post_obj.author else "Unknown",
                "reason": reason_str,
            })

        suggested_groups_data = [
            {
                "id": group_obj.id,
                "name": group_obj.name,
                "creator_username": group_obj.creator.username if group_obj.creator else "Unknown",
            }
            for group_obj in raw_groups
        ]

        suggested_events_data = [
            {
                "id": event_obj.id,
                "title": event_obj.title,
                "organizer_username": event_obj.organizer.username if event_obj.organizer else "Unknown",
            }
            for event_obj in raw_events
        ]

        suggested_users_data = [
            {"id": user_obj.id, "username": user_obj.username}
            for user_obj in raw_users
        ]

        suggested_polls_data = []
        for poll_obj in raw_polls:
            options_data = [
                {
                    "id": option.id,
                    "text": option.text,
                    "vote_count": len(option.votes),  # PollOption.votes is a list of PollVote objects
                }
                for option in poll_obj.options
            ]
            suggested_polls_data.append({
                "id": poll_obj.id,
                "question": poll_obj.question,
                "author_username": poll_obj.author.username if poll_obj.author else "Unknown",
                "options": options_data,
            })

        return {
            "user_id": user_id,
            "suggested_posts": suggested_posts_data,
            "suggested_groups": suggested_groups_data,
            "suggested_events": suggested_events_data,
            "suggested_users_to_follow": suggested_users_data,
            "suggested_polls_to_vote": suggested_polls_data,
        }, 200

# Need User model for UserFeedResource, already imported at the top
# from models import User
from recommendations import get_personalized_feed_posts # Import for UserFeedResource

class UserFeedResource(Resource):
    @jwt_required()
    def get(self, user_id):
        # current_user_id = int(get_jwt_identity()) # Not strictly needed unless for auth checks

        target_user = db.session.get(User, user_id)
        if not target_user:
            return {"message": "User not found"}, 404

        limit = request.args.get('limit', 20, type=int)

        posts_with_reasons = get_personalized_feed_posts(user_id, limit=limit)

        feed_data = []
        for post, reason in posts_with_reasons:
            post_dict = post.to_dict()
            post_dict['reason_for_recommendation'] = reason
            # Ensure timestamp is serialized
            if 'timestamp' in post_dict and isinstance(post_dict['timestamp'], datetime):
                post_dict['timestamp'] = post_dict['timestamp'].isoformat() + "Z" # Assume UTC
            if 'last_edited' in post_dict and post_dict['last_edited'] and isinstance(post_dict['last_edited'], datetime):
                post_dict['last_edited'] = post_dict['last_edited'].isoformat() + "Z"
            feed_data.append(post_dict)

        return {"feed_posts": feed_data}, 200


# PersonalizedFeedResource Implementation
class PersonalizedFeedResource(Resource):
    @jwt_required()
    def get(self):
        current_user_id = int(get_jwt_identity())
        current_user = db.session.get(User, current_user_id)

        if not current_user:
            return {"message": "User not found"}, 404

        processed_items = {} # Using dict to handle duplicates (type, id) -> item

        # Get friend IDs
        friend_ids = set()
        # Friendships initiated by the current user
        initiated_friendships = Friendship.query.filter_by(user_id=current_user_id, status='accepted').all()
        for f in initiated_friendships:
            friend_ids.add(f.friend_id)
        # Friendships accepted by the current user
        accepted_friendships = Friendship.query.filter_by(friend_id=current_user_id, status='accepted').all()
        for f in accepted_friendships:
            friend_ids.add(f.user_id)

        if friend_ids: # Only proceed if the user has friends
            # 1. Posts from Friends
            friend_posts = Post.query.filter(Post.user_id.in_(friend_ids)).order_by(Post.timestamp.desc()).limit(20).all()
            for post in friend_posts:
                item = {
                    "type": "post", "id": post.id, "title": post.title, "content": post.content,
                    "timestamp": post.timestamp, "author_username": post.author.username,
                    "reason": f"Posted by your friend {post.author.username}"
                }
                key = ("post", post.id)
                if key not in processed_items or item["timestamp"] > processed_items[key]["timestamp"]:
                    processed_items[key] = item

            # 2. Posts Liked by Friends
            friend_likes = Like.query.filter(Like.user_id.in_(friend_ids)).order_by(Like.timestamp.desc()).limit(20).all()
            for like in friend_likes:
                if like.post.user_id == current_user_id:
                    continue
                item = {
                    "type": "post", "id": like.post.id, "title": like.post.title, "content": like.post.content,
                    "timestamp": like.timestamp, "author_username": like.post.author.username,
                    "reason": f"Liked by your friend {like.user.username}"
                }
                key = ("post", like.post.id)
                if key not in processed_items or item["timestamp"] > processed_items[key]["timestamp"]:
                    processed_items[key] = item

            # 3. Posts Commented on by Friends
            friend_comments = Comment.query.filter(Comment.user_id.in_(friend_ids)).order_by(Comment.timestamp.desc()).limit(20).all()
            for comment in friend_comments:
                if comment.post.user_id == current_user_id:
                    continue
                item = {
                    "type": "post", "id": comment.post.id, "title": comment.post.title, "content": comment.post.content,
                    "timestamp": comment.timestamp, "author_username": comment.post.author.username,
                    "reason": f"Commented on by your friend {comment.author.username}"
                }
                key = ("post", comment.post.id)
                if key not in processed_items or item["timestamp"] > processed_items[key]["timestamp"]:
                    processed_items[key] = item

            # 4. Events by Friends or Friends Attending
            friend_events = Event.query.filter(Event.user_id.in_(friend_ids)).order_by(Event.created_at.desc()).limit(10).all()
            for event in friend_events:
                item = {
                    "type": "event", "id": event.id, "title": event.title, "description": event.description,
                    "date": event.date.isoformat() if event.date else None, # Serialize event.date
                    "timestamp": event.created_at, # This will be serialized later
                    "organizer_username": event.organizer.username,
                    "reason": f"Organized by your friend {event.organizer.username}"
                }
                key = ("event", event.id)
                if key not in processed_items or item["timestamp"] > processed_items[key]["timestamp"]:
                    processed_items[key] = item

            friend_rsvps = EventRSVP.query.filter(EventRSVP.user_id.in_(friend_ids), EventRSVP.status == 'Attending').order_by(EventRSVP.timestamp.desc()).limit(10).all()
            for rsvp in friend_rsvps:
                if rsvp.event.user_id == current_user_id:
                    continue
                item = {
                    "type": "event", "id": rsvp.event.id, "title": rsvp.event.title, "description": rsvp.event.description,
                    "date": rsvp.event.date.isoformat() if rsvp.event.date else None, # Serialize event.date
                    "timestamp": rsvp.timestamp, # This will be serialized later
                    "organizer_username": rsvp.event.organizer.username,
                    "reason": f"{rsvp.attendee.username} is attending"
                }
                key = ("event", rsvp.event.id)
                if key not in processed_items or item["timestamp"] > processed_items[key]["timestamp"]:
                    processed_items[key] = item

            # 5. Polls by Friends or Friends Voted On
            friend_polls = Poll.query.filter(Poll.user_id.in_(friend_ids)).order_by(Poll.created_at.desc()).limit(10).all()
            for poll in friend_polls:
                item = {
                    "type": "poll", "id": poll.id, "question": poll.question,
                    "options": [{"id": o.id, "text": o.text, "vote_count": len(o.votes)} for o in poll.options],
                    "timestamp": poll.created_at, "creator_username": poll.author.username,
                    "reason": f"Created by your friend {poll.author.username}"
                }
                key = ("poll", poll.id)
                if key not in processed_items or item["timestamp"] > processed_items[key]["timestamp"]:
                    processed_items[key] = item

            friend_poll_votes = PollVote.query.filter(PollVote.user_id.in_(friend_ids)).order_by(PollVote.created_at.desc()).limit(10).all()
            for vote in friend_poll_votes:
                # Access poll through vote.option.poll
                if not vote.option or not vote.option.poll: # Add check for safety
                    continue
                current_poll = vote.option.poll
                if current_poll.user_id == current_user_id:
                    continue

                item = {
                    "type": "poll", "id": current_poll.id, "question": current_poll.question,
                    "options": [{"id": o.id, "text": o.text, "vote_count": len(o.votes)} for o in current_poll.options],
                    "timestamp": vote.created_at, "creator_username": current_poll.author.username,
                    "reason": f"Voted on by your friend {vote.voter.username}" # Changed vote.user to vote.voter based on model
                }
                key = ("poll", current_poll.id)
                if key not in processed_items or item["timestamp"] > processed_items[key]["timestamp"]:
                    processed_items[key] = item

        feed_items_list = sorted(list(processed_items.values()), key=lambda x: x["timestamp"], reverse=True)

        for item in feed_items_list:
            if item["timestamp"].tzinfo is None:
                 item["timestamp"] = item["timestamp"].isoformat() + "Z"
            else:
                 item["timestamp"] = item["timestamp"].isoformat()

        return {"feed_items": feed_items_list}, 200

# Placeholder for TrendingHashtagsResource
class TrendingHashtagsResource(Resource):
    def get(self):
        return {"message": "Trending hashtags resource placeholder"}, 200


from recommendations import get_on_this_day_content # Import the function

# OnThisDayResource Implementation
class OnThisDayResource(Resource):
    @jwt_required()
    def get(self):
        current_user_id_str = get_jwt_identity()
        try:
            current_user_id = int(current_user_id_str)
        except ValueError:
            return {"message": "Invalid user identity in token"}, 400

        # It's good practice to ensure the user exists, though jwt_required handles token validity.
        user = db.session.get(User, current_user_id)
        if not user:
            return {"message": "User not found for provided token"}, 404

        content = get_on_this_day_content(current_user_id)

        posts_data = []
        if content.get("posts"):
            for post_obj in content["posts"]:
                posts_data.append(post_obj.to_dict()) # Assuming Post model has to_dict()

        events_data = []
        if content.get("events"):
            for event_obj in content["events"]:
                events_data.append(event_obj.to_dict()) # Assuming Event model has to_dict()

        return {
            "on_this_day_posts": posts_data,
            "on_this_day_events": events_data,
        }, 200


# UserStatsResource Implementation
class UserStatsResource(Resource):
    @jwt_required() # Ensure this is uncommented and active
    def get(self, user_id):
        current_jwt_user_id = int(get_jwt_identity()) # ID of the logged-in user

        if current_jwt_user_id != user_id:
            # Future: Add admin role check here to allow admins access
            # requesting_user = db.session.get(User, current_jwt_user_id)
            # if not (requesting_user and requesting_user.role == 'admin'):
            return {"message": "You are not authorized to view these stats."}, 403

        user = db.session.get(User, user_id)
        if not user:
            return {"message": "User not found"}, 404

        stats = user.get_stats() # Assumes User model has get_stats() method
        # Ensure all datetime objects in stats are serialized if any
        if stats.get("join_date") and isinstance(stats["join_date"], datetime):
            stats["join_date"] = stats["join_date"].isoformat() + "Z" # Assume UTC

        return stats, 200


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


class SharedFileResource(Resource):
    @jwt_required()
    def delete(self, file_id):
        current_user_id_str = get_jwt_identity()
        try:
            current_user_id = int(current_user_id_str)
        except ValueError:
            current_app.logger.error(f"Invalid user identity format in JWT: {current_user_id_str}")
            return {"message": "Invalid user identity format."}, 400

        shared_file = db.session.get(SharedFile, file_id)

        if not shared_file:
            return {"message": "File not found"}, 404

        # Refresh the object to ensure all attributes are loaded correctly from the DB
        db.session.refresh(shared_file)

        # Authorization check: Current user must be sender or receiver
        if not (shared_file.sender_id == current_user_id or shared_file.receiver_id == current_user_id):
            return {"message": "You are not authorized to delete this file"}, 403

        try:
            # Check if the essential saved_filename attribute is present
            if not shared_file.saved_filename:
                 current_app.logger.error(f"File record is incomplete (missing saved_filename) for SharedFile ID: {file_id}")
                 return {"message": "File record is incomplete, cannot delete physical file"}, 500

            upload_folder = current_app.config.get('SHARED_FILES_UPLOAD_FOLDER', 'shared_files_uploads')
            file_path = os.path.join(upload_folder, shared_file.saved_filename) # Use saved_filename

            if os.path.exists(file_path):
                os.remove(file_path)
            else:
                # Log this inconsistency but proceed to delete DB record
                current_app.logger.warning(f"Warning: File {file_path} not found on filesystem for SharedFile ID {file_id} but DB record exists.")

            db.session.delete(shared_file)
            db.session.commit()

            return {"message": "File deleted successfully"}, 200

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting file ID {file_id}: {str(e)}")
            return {"message": f"An error occurred while deleting the file: {str(e)}"}, 500
