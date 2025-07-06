from ..models.db_models import (
    User,
    Post,
    Comment,
    Friendship,
    Event,
    PollVote,
    Achievement,
    UserAchievement,
    Group,
    Poll,
    Bookmark,
)
from .. import db
from sqlalchemy import func


def get_user_stat(user, stat_type):
    """Helper function to get a specific stat for a user."""
    if stat_type == "num_posts":
        return Post.query.filter_by(user_id=user.id).count()
    elif stat_type == "num_comments_given":
        return Comment.query.filter_by(user_id=user.id).count()
    elif stat_type == "num_friends":
        return len(user.get_friends())
    elif stat_type == "num_events_created":
        return Event.query.filter_by(user_id=user.id).count()
    elif stat_type == "num_polls_created":
        return Poll.query.filter_by(
            user_id=user.id
        ).count()
    elif stat_type == "num_polls_voted":
        return (
            db.session.query(PollVote.poll_id)
            .filter_by(user_id=user.id)
            .distinct()
            .count()
        )
    elif stat_type == "num_likes_received":
        total_likes = 0
        user_posts = Post.query.filter_by(user_id=user.id).all()
        for post in user_posts:
            total_likes += len(post.likes)
        return total_likes
    elif stat_type == "num_groups_joined":
        return user.joined_groups.count()
    elif stat_type == "num_bookmarks_created":
        return Bookmark.query.filter_by(
            user_id=user.id
        ).count()
    return 0


def check_and_award_achievements(user_id):
    """
    Checks all defined achievements for a given user and awards them if criteria are met
    and the user hasn't already received them.
    """
    user = db.session.get(User, user_id)
    if not user:
        return {"error": "User not found"}, 404

    all_achievements = Achievement.query.all()
    awarded_new_achievements = []

    for achievement in all_achievements:
        existing_user_achievement = UserAchievement.query.filter_by(
            user_id=user.id, achievement_id=achievement.id
        ).first()

        if existing_user_achievement:
            continue

        current_stat_value = get_user_stat(user, achievement.criteria_type)

        if current_stat_value >= achievement.criteria_value:
            new_user_achievement = UserAchievement(
                user_id=user.id, achievement_id=achievement.id
            )
            db.session.add(new_user_achievement)
            awarded_new_achievements.append(achievement.name)

    if awarded_new_achievements:
        try:
            db.session.commit()
            print(
                f"User {user.username} awarded achievements: {', '.join(awarded_new_achievements)}"
            )
            return {
                "message": f"Awarded achievements: {', '.join(awarded_new_achievements)}"
            }, 200
        except Exception as e:
            db.session.rollback()
            print(f"Error awarding achievements for user {user.username}: {e}")
            return {"error": f"Error awarding achievements: {str(e)}"}, 500

    return {"message": "No new achievements awarded."}, 200
