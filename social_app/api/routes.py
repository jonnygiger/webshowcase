from flask_restful import Resource, reqparse
from flask import request, g, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta, timezone
import os

from ..services.notifications_service import broadcast_new_post
from ..models.db_models import (
    User,
    Post,
    Comment,
    Like,
    Friendship,
    Event,
    EventRSVP,
    Poll,
    PollOption,
    PollVote,
    db,
    PostLock,
    SharedFile,
    UserBlock,
    ChatRoom,
    ChatMessage,
)

class UserListResource(Resource):
    def get(self):
        return {"message": "User list resource placeholder"}, 200


class UserResource(Resource):
    def get(self, user_id):
        return {"message": f"User resource placeholder for user_id {user_id}"}, 200


class PostListResource(Resource):
    @jwt_required()
    def post(self):
        current_user_id = int(get_jwt_identity())
        user = db.session.get(User, current_user_id)
        if not user:
            return {"message": "User not found for provided token"}, 404

        parser = reqparse.RequestParser()
        parser.add_argument("title", required=True, help="Title cannot be blank")
        parser.add_argument("content", required=True, help="Content cannot be blank")
        data = parser.parse_args()

        new_post = Post(title=data["title"], content=data["content"], user_id=user.id)

        db.session.add(new_post)
        db.session.commit()

        post_dict = new_post.to_dict()
        broadcast_new_post(post_dict)

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

        if UserBlock.query.filter_by(
            blocker_id=post.user_id, blocked_id=user.id
        ).first():
            return {
                "message": "You are blocked by the post author and cannot comment."
            }, 403

        parser = reqparse.RequestParser()
        parser.add_argument(
            "content", required=True, help="Comment content cannot be blank"
        )
        data = parser.parse_args()

        new_comment = Comment(content=data["content"], user_id=user.id, post_id=post.id)
        db.session.add(new_comment)
        db.session.commit()

        new_comment_data_for_post_room = {
            "id": new_comment.id,
            "post_id": new_comment.post_id,
            "author_username": new_comment.author.username,
            "content": new_comment.content,
            "timestamp": new_comment.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Dispatch to SSE listeners for this post
        if post_id in current_app.post_event_listeners:
            listeners = list(current_app.post_event_listeners[post_id])
            current_app.logger.debug(f"Dispatching new_comment_event to {len(listeners)} listeners for post {post_id}")
            for q_item in listeners:
                try:
                    sse_data = {"event": "new_comment_event", "data": new_comment_data_for_post_room}
                    q_item.put_nowait(sse_data)
                except Exception as e:
                    current_app.logger.error(f"Error putting new_comment_event to SSE queue for post {post_id}: {e}")
        else:
            current_app.logger.debug(f"No active SSE listeners for post {post_id} to dispatch new_comment_event.")

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

        for option_text in data["options"]:
            if not option_text.strip():
                return {"message": "Poll option text cannot be blank"}, 400
            poll_option = PollOption(
                text=option_text, poll=new_poll
            )
            db.session.add(
                poll_option
            )

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
    ):
        current_user_id = int(get_jwt_identity())
        user = db.session.get(
            User, current_user_id
        )
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
                and existing_lock.expires_at.replace(tzinfo=timezone.utc)
                > datetime.now(timezone.utc)
            ):
                return {
                    "message": "Post is currently locked by another user.",
                    "locked_by_username": existing_lock.user.username,
                    "expires_at": existing_lock.expires_at.isoformat(),
                }, 409
            else:
                db.session.delete(existing_lock)
                db.session.flush()

        lock_duration_minutes = 15
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=lock_duration_minutes
        )

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

        # Dispatch to SSE listeners for this post
        lock_payload_for_sse = {
            "post_id": new_lock.post_id,
            "status": "acquired",
            "user_id": new_lock.user_id,
            "username": user.username,
            "expires_at": new_lock.expires_at.isoformat()
        }
        if new_lock.post_id in current_app.post_event_listeners:
            listeners = list(current_app.post_event_listeners[new_lock.post_id])
            current_app.logger.debug(f"Dispatching post_lock_changed (acquired) to {len(listeners)} listeners for post {new_lock.post_id}")
            for q_item in listeners:
                try:
                    sse_data = {"type": "post_lock_changed", "payload": lock_payload_for_sse}
                    q_item.put_nowait(sse_data)
                except Exception as e:
                    current_app.logger.error(f"Error putting post_lock_changed (acquired) to SSE queue for post {new_lock.post_id}: {e}")

        return {
            "message": "Post locked successfully.",
            "lock_details": {
                "post_id": new_lock.post_id,
                "locked_by_user_id": new_lock.user_id,
                "locked_by_username": user.username,
                "locked_at": (
                    new_lock.locked_at.replace(tzinfo=timezone.utc).isoformat()
                    if new_lock.locked_at.tzinfo is None
                    else new_lock.locked_at.isoformat()
                ),
                "expires_at": (
                    new_lock.expires_at.replace(tzinfo=timezone.utc).isoformat()
                    if new_lock.expires_at.tzinfo is None
                    else new_lock.expires_at.isoformat()
                ),
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

        # Dispatch to SSE listeners for this post
        release_payload_for_sse = {
            "post_id": post_id,
            "status": "released",
            "user_id": current_user_id,
            "username": user.username
        }
        if post_id in current_app.post_event_listeners:
            listeners = list(current_app.post_event_listeners[post_id])
            current_app.logger.debug(f"Dispatching post_lock_changed (released) to {len(listeners)} listeners for post {post_id}")
            for q_item in listeners:
                try:
                    sse_data = {"type": "post_lock_changed", "payload": release_payload_for_sse}
                    q_item.put_nowait(sse_data)
                except Exception as e:
                    current_app.logger.error(f"Error putting post_lock_changed (released) to SSE queue for post {post_id}: {e}")

        return {"message": "Post unlocked successfully."}, 200


class PostResource(Resource):
    def get(self, post_id):
        return {"message": f"Post resource placeholder for post_id {post_id}"}, 200

    # It is recommended to add a PUT/PATCH method here for updating post content
    # and include the SSE dispatch logic for "post_content_updated" within it.
    # For example:
    # @jwt_required()
    # def put(self, post_id):
    #     current_user_id = int(get_jwt_identity())
    #     user = db.session.get(User, current_user_id)
    #     if not user:
    #         return {"message": "User not found"}, 404
    #
    #     post = db.session.get(Post, post_id)
    #     if not post:
    #         return {"message": "Post not found"}, 404
    #
    #     if post.user_id != current_user_id:
    #         # Add check for moderators or other roles if they are allowed to edit
    #         return {"message": "Not authorized to edit this post"}, 403
    #
    #     parser = reqparse.RequestParser()
    #     parser.add_argument("title", type=str, help="Title of the post")
    #     parser.add_argument("content", type=str, help="Content of the post")
    #     parser.add_argument("hashtags", type=str, help="Hashtags for the post")
    #     data = parser.parse_args()
    #
    #     updated = False
    #     if data.get("title") is not None:
    #         post.title = data["title"]
    #         updated = True
    #     if data.get("content") is not None:
    #         post.content = data["content"]
    #         updated = True
    #     if data.get("hashtags") is not None:
    #         post.hashtags = data["hashtags"]
    #         updated = True
    #
    #     if updated:
    #         post.last_edited = datetime.now(timezone.utc)
    #         try:
    #             db.session.commit()
    #
    #             # Dispatch to SSE listeners for post content update
    #             post_data_for_sse = {
    #                 "post_id": post.id,
    #                 "title": post.title,
    #                 "content": post.content,
    #                 "last_edited": post.last_edited.isoformat() if post.last_edited else None,
    #                 "edited_by_user_id": current_user_id,
    #                 "edited_by_username": user.username
    #             }
    #             if post.id in current_app.post_event_listeners:
    #                 listeners = list(current_app.post_event_listeners[post.id])
    #                 current_app.logger.debug(f"Dispatching post_content_updated to {len(listeners)} listeners for post {post.id}")
    #                 for q_item in listeners:
    #                     try:
    #                         sse_data = {"type": "post_content_updated", "payload": post_data_for_sse}
    #                         q_item.put_nowait(sse_data)
    #                     except Exception as e:
    #                         current_app.logger.error(f"Error putting post_content_updated to SSE queue for post {post.id}: {e}")
    #
    #             return {"message": "Post updated successfully", "post": post.to_dict()}, 200
    #         except Exception as e:
    #             db.session.rollback()
    #             current_app.logger.error(f"Error updating post {post_id}: {e}")
    #             return {"message": "Error updating post"}, 500
    #     else:
    #         return {"message": "No update data provided"}, 400


class EventListResource(Resource):
    def get(self):
        return {"message": "Event list resource placeholder"}, 200


class EventResource(Resource):
    def get(self, event_id):
        return {"message": f"Event resource placeholder for event_id {event_id}"}, 200


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

        from ..services.recommendations_service import (
            suggest_posts_to_read,
            suggest_groups_to_join,
            suggest_events_to_attend,
            suggest_users_to_follow,
        )

        limit = 5
        raw_posts = suggest_posts_to_read(user_id, limit=limit)
        raw_groups = suggest_groups_to_join(user_id, limit=limit)
        raw_events = suggest_events_to_attend(user_id, limit=limit)
        raw_users = suggest_users_to_follow(user_id, limit=limit)
        raw_polls = suggest_polls_to_vote(user_id, limit=limit)

        suggested_posts_data = []
        for post_obj, reason_str in raw_posts:
            suggested_posts_data.append(
                {
                    "id": post_obj.id,
                    "title": post_obj.title,
                    "author_username": (
                        post_obj.author.username if post_obj.author else "Unknown"
                    ),
                    "reason": reason_str,
                }
            )

        suggested_groups_data = [
            {
                "id": group_obj.id,
                "name": group_obj.name,
                "creator_username": (
                    group_obj.creator.username if group_obj.creator else "Unknown"
                ),
            }
            for group_obj in raw_groups
        ]

        suggested_events_data = [
            {
                "id": event_obj.id,
                "title": event_obj.title,
                "organizer_username": (
                    event_obj.organizer.username if event_obj.organizer else "Unknown"
                ),
            }
            for event_obj in raw_events
        ]

        suggested_users_data = [
            {"id": user_obj.id, "username": user_obj.username} for user_obj in raw_users
        ]

        suggested_polls_data = []
        for poll_obj in raw_polls:
            options_data = [
                {
                    "id": option.id,
                    "text": option.text,
                    "vote_count": len(
                        option.votes
                    ),
                }
                for option in poll_obj.options
            ]
            suggested_polls_data.append(
                {
                    "id": poll_obj.id,
                    "question": poll_obj.question,
                    "author_username": (
                        poll_obj.author.username if poll_obj.author else "Unknown"
                    ),
                    "options": options_data,
                }
            )

        return {
            "user_id": user_id,
            "suggested_posts": suggested_posts_data,
            "suggested_groups": suggested_groups_data,
            "suggested_events": suggested_events_data,
            "suggested_users_to_follow": suggested_users_data,
            "suggested_polls_to_vote": suggested_polls_data,
        }, 200


from ..services.recommendations_service import get_personalized_feed_posts


class UserFeedResource(Resource):
    @jwt_required()
    def get(self, user_id):
        target_user = db.session.get(User, user_id)
        if not target_user:
            return {"message": "User not found"}, 404

        limit = request.args.get("limit", 20, type=int)

        posts_with_reasons = get_personalized_feed_posts(user_id, limit=limit)

        feed_data = []
        for post, reason in posts_with_reasons:
            post_dict = post.to_dict()
            post_dict["reason_for_recommendation"] = reason
            if "timestamp" in post_dict and isinstance(
                post_dict["timestamp"], datetime
            ):
                post_dict["timestamp"] = (
                    post_dict["timestamp"].isoformat() + "Z"
                )
            if (
                "last_edited" in post_dict
                and post_dict["last_edited"]
                and isinstance(post_dict["last_edited"], datetime)
            ):
                post_dict["last_edited"] = post_dict["last_edited"].isoformat() + "Z"
            feed_data.append(post_dict)

        return {"feed_posts": feed_data}, 200


class PersonalizedFeedResource(Resource):
    @jwt_required()
    def get(self):
        current_user_id = int(get_jwt_identity())
        current_user = db.session.get(User, current_user_id)

        if not current_user:
            return {"message": "User not found"}, 404

        processed_items = {}

        friend_ids = set()
        initiated_friendships = Friendship.query.filter_by(
            user_id=current_user_id, status="accepted"
        ).all()
        for f in initiated_friendships:
            friend_ids.add(f.friend_id)
        accepted_friendships = Friendship.query.filter_by(
            friend_id=current_user_id, status="accepted"
        ).all()
        for f in accepted_friendships:
            friend_ids.add(f.user_id)

        if friend_ids:
            friend_posts = (
                Post.query.filter(Post.user_id.in_(friend_ids))
                .order_by(Post.timestamp.desc())
                .limit(20)
                .all()
            )
            for post in friend_posts:
                item = {
                    "type": "post",
                    "id": post.id,
                    "title": post.title,
                    "content": post.content,
                    "timestamp": post.timestamp,
                    "author_username": post.author.username,
                    "reason": f"Posted by your friend {post.author.username}",
                }
                key = ("post", post.id)
                if (
                    key not in processed_items
                    or item["timestamp"] > processed_items[key]["timestamp"]
                ):
                    processed_items[key] = item

            friend_likes = (
                Like.query.filter(Like.user_id.in_(friend_ids))
                .order_by(Like.timestamp.desc())
                .limit(20)
                .all()
            )
            for like in friend_likes:
                if like.post.user_id == current_user_id:
                    continue
                item = {
                    "type": "post",
                    "id": like.post.id,
                    "title": like.post.title,
                    "content": like.post.content,
                    "timestamp": like.timestamp,
                    "author_username": like.post.author.username,
                    "reason": f"Liked by your friend {like.user.username}",
                }
                key = ("post", like.post.id)
                if (
                    key not in processed_items
                    or item["timestamp"] > processed_items[key]["timestamp"]
                ):
                    processed_items[key] = item

            friend_comments = (
                Comment.query.filter(Comment.user_id.in_(friend_ids))
                .order_by(Comment.timestamp.desc())
                .limit(20)
                .all()
            )
            for comment in friend_comments:
                if comment.post.user_id == current_user_id:
                    continue
                item = {
                    "type": "post",
                    "id": comment.post.id,
                    "title": comment.post.title,
                    "content": comment.post.content,
                    "timestamp": comment.timestamp,
                    "author_username": comment.post.author.username,
                    "reason": f"Commented on by your friend {comment.author.username}",
                }
                key = ("post", comment.post.id)
                if (
                    key not in processed_items
                    or item["timestamp"] > processed_items[key]["timestamp"]
                ):
                    processed_items[key] = item

            friend_events = (
                Event.query.filter(Event.user_id.in_(friend_ids))
                .order_by(Event.created_at.desc())
                .limit(10)
                .all()
            )
            for event in friend_events:
                item = {
                    "type": "event",
                    "id": event.id,
                    "title": event.title,
                    "description": event.description,
                    "date": (
                        event.date.isoformat() if event.date else None
                    ),
                    "timestamp": event.created_at,
                    "organizer_username": event.organizer.username,
                    "reason": f"Organized by your friend {event.organizer.username}",
                }
                key = ("event", event.id)
                if (
                    key not in processed_items
                    or item["timestamp"] > processed_items[key]["timestamp"]
                ):
                    processed_items[key] = item

            friend_rsvps = (
                EventRSVP.query.filter(
                    EventRSVP.user_id.in_(friend_ids), EventRSVP.status == "Attending"
                )
                .order_by(EventRSVP.timestamp.desc())
                .limit(10)
                .all()
            )
            for rsvp in friend_rsvps:
                if rsvp.event.user_id == current_user_id:
                    continue
                item = {
                    "type": "event",
                    "id": rsvp.event.id,
                    "title": rsvp.event.title,
                    "description": rsvp.event.description,
                    "date": (
                        rsvp.event.date.isoformat() if rsvp.event.date else None
                    ),
                    "timestamp": rsvp.timestamp,
                    "organizer_username": rsvp.event.organizer.username,
                    "reason": f"{rsvp.attendee.username} is attending",
                }
                key = ("event", rsvp.event.id)
                if (
                    key not in processed_items
                    or item["timestamp"] > processed_items[key]["timestamp"]
                ):
                    processed_items[key] = item

            friend_polls = (
                Poll.query.filter(Poll.user_id.in_(friend_ids))
                .order_by(Poll.created_at.desc())
                .limit(10)
                .all()
            )
            for poll in friend_polls:
                item = {
                    "type": "poll",
                    "id": poll.id,
                    "question": poll.question,
                    "options": [
                        {"id": o.id, "text": o.text, "vote_count": len(o.votes)}
                        for o in poll.options
                    ],
                    "timestamp": poll.created_at,
                    "creator_username": poll.author.username,
                    "reason": f"Created by your friend {poll.author.username}",
                }
                key = ("poll", poll.id)
                if (
                    key not in processed_items
                    or item["timestamp"] > processed_items[key]["timestamp"]
                ):
                    processed_items[key] = item

            friend_poll_votes = (
                PollVote.query.filter(PollVote.user_id.in_(friend_ids))
                .order_by(PollVote.created_at.desc())
                .limit(10)
                .all()
            )
            for vote in friend_poll_votes:
                if not vote.option or not vote.option.poll:
                    continue
                current_poll = vote.option.poll
                if current_poll.user_id == current_user_id:
                    continue

                item = {
                    "type": "poll",
                    "id": current_poll.id,
                    "question": current_poll.question,
                    "options": [
                        {"id": o.id, "text": o.text, "vote_count": len(o.votes)}
                        for o in current_poll.options
                    ],
                    "timestamp": vote.created_at,
                    "creator_username": current_poll.author.username,
                    "reason": f"Voted on by your friend {vote.voter.username}",
                }
                key = ("poll", current_poll.id)
                if (
                    key not in processed_items
                    or item["timestamp"] > processed_items[key]["timestamp"]
                ):
                    processed_items[key] = item

        feed_items_list = sorted(
            list(processed_items.values()), key=lambda x: x["timestamp"], reverse=True
        )

        for item in feed_items_list:
            if item["timestamp"].tzinfo is None:
                item["timestamp"] = item["timestamp"].isoformat() + "Z"
            else:
                item["timestamp"] = item["timestamp"].isoformat()

        return {"feed_items": feed_items_list}, 200


class TrendingHashtagsResource(Resource):
    def get(self):
        return {"message": "Trending hashtags resource placeholder"}, 200


from ..services.recommendations_service import get_on_this_day_content


class OnThisDayResource(Resource):
    @jwt_required()
    def get(self):
        current_user_id_str = get_jwt_identity()
        try:
            current_user_id = int(current_user_id_str)
        except ValueError:
            return {"message": "Invalid user identity in token"}, 400

        user = db.session.get(User, current_user_id)
        if not user:
            return {"message": "User not found for provided token"}, 404

        content = get_on_this_day_content(current_user_id)

        posts_data = []
        if content.get("posts"):
            for post_obj in content["posts"]:
                posts_data.append(
                    post_obj.to_dict()
                )

        events_data = []
        if content.get("events"):
            for event_obj in content["events"]:
                events_data.append(
                    event_obj.to_dict()
                )

        return {
            "on_this_day_posts": posts_data,
            "on_this_day_events": events_data,
        }, 200


class UserStatsResource(Resource):
    @jwt_required()
    def get(self, user_id):
        current_jwt_user_id = int(get_jwt_identity())

        if current_jwt_user_id != user_id:
            return {"message": "You are not authorized to view these stats."}, 403

        user = db.session.get(User, user_id)
        if not user:
            return {"message": "User not found"}, 404

        stats = user.get_stats()
        if stats.get("join_date") and isinstance(stats["join_date"], datetime):
            stats["join_date"] = stats["join_date"].isoformat() + "Z"

        return stats, 200


class SeriesListResource(Resource):
    def get(self):
        return {"message": "Series list resource placeholder"}, 200


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
            current_app.logger.error(
                f"Invalid user identity format in JWT: {current_user_id_str}"
            )
            return {"message": "Invalid user identity format."}, 400

        shared_file = db.session.get(SharedFile, file_id)

        if not shared_file:
            return {"message": "File not found"}, 404

        db.session.refresh(shared_file)

        if not (
            shared_file.sender_id == current_user_id
            or shared_file.receiver_id == current_user_id
        ):
            return {"message": "You are not authorized to delete this file"}, 403

        try:
            if not shared_file.saved_filename:
                current_app.logger.error(
                    f"File record is incomplete (missing saved_filename) for SharedFile ID: {file_id}"
                )
                return {
                    "message": "File record is incomplete, cannot delete physical file"
                }, 500

            upload_folder = current_app.config.get(
                "SHARED_FILES_UPLOAD_FOLDER", "shared_files_uploads"
            )
            file_path = os.path.join(
                upload_folder, shared_file.saved_filename
            )

            if os.path.exists(file_path):
                os.remove(file_path)
            else:
                current_app.logger.warning(
                    f"Warning: File {file_path} not found on filesystem for SharedFile ID {file_id} but DB record exists."
                )

            db.session.delete(shared_file)
            db.session.commit()

            return {"message": "File deleted successfully"}, 200

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting file ID {file_id}: {str(e)}")
            return {
                "message": f"An error occurred while deleting the file: {str(e)}"
            }, 500


class ChatRoomListResource(Resource):
    @jwt_required()
    def get(self):
        chat_rooms = ChatRoom.query.order_by(ChatRoom.name).all()
        return {"chat_rooms": [room.to_dict() for room in chat_rooms]}, 200

    @jwt_required()
    def post(self):
        current_user_id = int(get_jwt_identity())
        user = db.session.get(User, current_user_id)
        if not user:
            return {"message": "User not found for provided token"}, 404

        parser = reqparse.RequestParser()
        parser.add_argument(
            "name", type=str, required=True, help="Chat room name cannot be blank."
        )
        data = parser.parse_args()

        room_name = data["name"].strip()
        if not room_name:
            return {"message": "Chat room name cannot be empty."}, 400

        existing_room = ChatRoom.query.filter_by(name=room_name).first()
        if existing_room:
            return {
                "message": f"Chat room with name '{room_name}' already exists."
            }, 409

        new_chat_room = ChatRoom(name=room_name, creator_id=current_user_id)
        db.session.add(new_chat_room)
        try:
            db.session.commit()
            return {
                "message": "Chat room created successfully.",
                "chat_room": new_chat_room.to_dict(),
            }, 201
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(
                f"Error creating chat room '{room_name}': {str(e)}"
            )
            return {
                "message": "Failed to create chat room due to an internal error."
            }, 500


class ChatRoomMessagesResource(Resource):
    @jwt_required()
    def get(self, room_id):
        chat_room = db.session.get(ChatRoom, room_id)
        if not chat_room:
            return {"message": "Chat room not found"}, 404

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get(
            "per_page", 20, type=int
        )

        messages_query = ChatMessage.query.filter_by(room_id=room_id).order_by(
            ChatMessage.timestamp.desc(), ChatMessage.id.desc()
        )
        paginated_messages = messages_query.paginate(
            page=page, per_page=per_page, error_out=False
        )

        messages_data = [message.to_dict() for message in paginated_messages.items]

        return {
            "room_id": room_id,
            "room_name": chat_room.name,
            "messages": messages_data,
            "page": paginated_messages.page,
            "per_page": paginated_messages.per_page,
            "total_pages": paginated_messages.pages,
            "total_messages": paginated_messages.total,
        }, 200

    @jwt_required()
    def post(self, room_id):
        current_user_id = int(get_jwt_identity())
        user = db.session.get(User, current_user_id)
        if not user:
            return {"message": "User not found"}, 404

        chat_room = db.session.get(ChatRoom, room_id)
        if not chat_room:
            return {"message": "Chat room not found"}, 404

        parser = reqparse.RequestParser()
        parser.add_argument("message", required=True, help="Message cannot be blank")
        data = parser.parse_args()

        new_message = ChatMessage(
            message=data["message"], user_id=user.id, room_id=chat_room.id
        )
        db.session.add(new_message)
        db.session.commit()

        # Dispatch to SSE listeners for this room
        message_dict_for_sse = new_message.to_dict() # Assuming to_dict() gives a serializable dict
        if room_id in current_app.chat_room_listeners:
            listeners = current_app.chat_room_listeners[room_id]
            if listeners:
                current_app.logger.debug(f"Dispatching message to {len(listeners)} listeners for room {room_id}")
                for q_item in list(listeners): # Iterate over a copy
                    try:
                        # Structure the data as expected by the SSE handler
                        sse_data = {"type": "new_chat_message", "payload": message_dict_for_sse}
                        q_item.put_nowait(sse_data)
                    except Exception as e: # queue.Full or other errors
                        current_app.logger.error(f"Error putting message to SSE queue for room {room_id}: {e}")
            else:
                current_app.logger.debug(f"No active SSE listeners for room {room_id} to dispatch message.")

        return {"message": "Message posted successfully", "chat_message": new_message.to_dict()}, 201


from flask_jwt_extended import create_access_token
from werkzeug.security import check_password_hash

class ApiLoginResource(Resource):
    def post(self):
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return {"message": "Username and password are required"}, 400

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            access_token = create_access_token(identity=str(user.id))
            return {"access_token": access_token}, 200
        else:
            return {"message": "Invalid credentials"}, 401
