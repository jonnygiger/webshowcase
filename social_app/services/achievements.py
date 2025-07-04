from ..models.db_models import ( # Corrected model import path
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
from .. import db # Import db from social_app package
from sqlalchemy import func # Ensure func is imported


def get_user_stat(user, stat_type):
    """Helper function to get a specific stat for a user."""
    if stat_type == "num_posts":
        return Post.query.filter_by(user_id=user.id).count()
    elif stat_type == "num_comments_given":
        return Comment.query.filter_by(user_id=user.id).count()
    elif stat_type == "num_friends":
        # This relies on the User.get_friends() method being accurate
        return len(user.get_friends())
    elif stat_type == "num_events_created":
        return Event.query.filter_by(user_id=user.id).count()
    elif stat_type == "num_polls_created":
        return Poll.query.filter_by(
            user_id=user.id
        ).count()  # Assuming Poll model has user_id
    elif stat_type == "num_polls_voted":
        # Counts distinct polls a user has voted in
        return (
            db.session.query(PollVote.poll_id)
            .filter_by(user_id=user.id)
            .distinct()
            .count()
        )
    elif stat_type == "num_likes_received":
        # Sum of likes on all posts by the user
        total_likes = 0
        user_posts = Post.query.filter_by(user_id=user.id).all()
        for post in user_posts:
            total_likes += len(post.likes)  # Relies on Post.likes relationship
        return total_likes
    elif stat_type == "num_groups_joined":
        # User.joined_groups is a dynamic query
        return user.joined_groups.count()
    elif stat_type == "num_bookmarks_created":
        return Bookmark.query.filter_by(
            user_id=user.id
        ).count()  # Assuming Bookmark model exists
    # Add more stat types as needed
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
        # Check if user already has this achievement
        existing_user_achievement = UserAchievement.query.filter_by(
            user_id=user.id, achievement_id=achievement.id
        ).first()

        if existing_user_achievement:
            continue  # User already has this achievement

        # Get the current stat value for the user based on achievement criteria
        current_stat_value = get_user_stat(user, achievement.criteria_type)

        if current_stat_value >= achievement.criteria_value:
            # Award the achievement
            new_user_achievement = UserAchievement(
                user_id=user.id, achievement_id=achievement.id
            )
            db.session.add(new_user_achievement)
            awarded_new_achievements.append(achievement.name)
            # Potentially emit a notification here (e.g., via SocketIO)

    if awarded_new_achievements:
        try:
            db.session.commit()
            print(
                f"User {user.username} awarded achievements: {', '.join(awarded_new_achievements)}"
            )
            # TODO: Consider returning info about awarded achievements for immediate feedback/notification
            return {
                "message": f"Awarded achievements: {', '.join(awarded_new_achievements)}"
            }, 200
        except Exception as e:
            db.session.rollback()
            print(f"Error awarding achievements for user {user.username}: {e}")
            return {"error": f"Error awarding achievements: {str(e)}"}, 500

    return {"message": "No new achievements awarded."}, 200


# Example of how this might be extended or used:
# def check_first_post_achievement(user):
#     if Post.query.filter_by(user_id=user.id).count() >= 1:
#         award_achievement_if_not_earned(user, "First Post")

# def award_achievement_if_not_earned(user, achievement_name):
#     achievement = Achievement.query.filter_by(name=achievement_name).first()
#     if not achievement:
#         print(f"Achievement '{achievement_name}' not found in DB.")
#         return
#     existing = UserAchievement.query.filter_by(user_id=user.id, achievement_id=achievement.id).first()
#     if not existing:
#         new_award = UserAchievement(user_id=user.id, achievement_id=achievement.id)
#         db.session.add(new_award)
#         db.session.commit() # Commit immediately or batch commits
#         print(f"Awarded '{achievement_name}' to {user.username}")
#         # Optionally, send a notification to the user
