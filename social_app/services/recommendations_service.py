from flask import current_app

from ..models.db_models import (
    User,
    Post,
    Group,
    Friendship,
    Like,
    Event,
    EventRSVP,
    Poll,
    PollVote,
    Comment,
    SharedPost,
    TrendingHashtag,
)
from .. import db
from sqlalchemy import func, or_, extract
from collections import defaultdict, Counter
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from flask import current_app


def suggest_users_to_follow(user_id, limit=5):
    """Suggest users who are friends of the current user's friends."""
    current_user = db.session.get(User, user_id)
    if not current_user:
        return []

    friends_of_friends = defaultdict(int)

    user_friendships = Friendship.query.filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
        Friendship.status == "accepted",
    ).all()
    friend_ids = set()
    for friendship in user_friendships:
        if friendship.user_id == user_id:
            friend_ids.add(friendship.friend_id)
        else:
            friend_ids.add(friendship.user_id)

    for friend_id in friend_ids:
        friend_of_friend_friendships = Friendship.query.filter(
            or_(Friendship.user_id == friend_id, Friendship.friend_id == friend_id),
            Friendship.status == "accepted",
        ).all()
        for fof_friendship in friend_of_friend_friendships:
            fof_id = (
                fof_friendship.friend_id
                if fof_friendship.user_id == friend_id
                else fof_friendship.user_id
            )
            if fof_id != user_id and fof_id not in friend_ids:
                existing_request = Friendship.query.filter(
                    or_(
                        (Friendship.user_id == user_id)
                        & (Friendship.friend_id == fof_id),
                        (Friendship.user_id == fof_id)
                        & (Friendship.friend_id == user_id),
                    ),
                    Friendship.status.in_(["pending", "rejected"]),
                ).first()
                if not existing_request:
                    friends_of_friends[fof_id] += 1

    suggested_user_ids = [
        uid
        for uid, count in sorted(
            friends_of_friends.items(), key=lambda item: item[1], reverse=True
        )
    ]

    suggested_users = User.query.filter(User.id.in_(suggested_user_ids)).all()

    ordered_suggested_users = sorted(
        suggested_users, key=lambda u: suggested_user_ids.index(u.id)
    )

    return ordered_suggested_users[:limit]


def suggest_posts_to_read(user_id, limit=5):
    """Suggest posts liked or commented on by the current user's friends, ranked by recency of interaction."""
    db_session = current_app.extensions["sqlalchemy"].session
    current_user = db_session.get(User, user_id)
    if not current_user:
        return []

    user_friendships = Friendship.query.filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
        Friendship.status == "accepted",
    ).all()
    friend_ids = set()
    for friendship in user_friendships:
        if friendship.user_id == user_id:
            friend_ids.add(friendship.friend_id)
        else:
            friend_ids.add(friendship.user_id)

    if not friend_ids:
        return []

    recommended_posts_with_ts = defaultdict(lambda: None)

    likes_by_friends = (
        db_session.query(Like.post_id, Like.timestamp)
        .filter(Like.user_id.in_(friend_ids))
        .all()
    )

    for post_id, like_timestamp in likes_by_friends:
        if (
            recommended_posts_with_ts[post_id] is None
            or like_timestamp > recommended_posts_with_ts[post_id]
        ):
            recommended_posts_with_ts[post_id] = like_timestamp

    comments_by_friends = (
        db_session.query(Comment.post_id, Comment.timestamp)
        .filter(Comment.user_id.in_(friend_ids))
        .all()
    )

    for post_id, comment_timestamp in comments_by_friends:
        if (
            recommended_posts_with_ts[post_id] is None
            or comment_timestamp > recommended_posts_with_ts[post_id]
        ):
            recommended_posts_with_ts[post_id] = comment_timestamp

    if not recommended_posts_with_ts:
        return []

    user_liked_post_ids = {
        like.post_id for like in Like.query.filter_by(user_id=user_id).all()
    }
    user_commented_post_ids = {
        comment.post_id for comment in Comment.query.filter_by(user_id=user_id).all()
    }

    valid_post_ids = []
    for post_id in recommended_posts_with_ts.keys():
        post = db_session.get(Post, post_id)
        if post:
            if post.user_id == user_id:
                continue
            if post.id in user_liked_post_ids:
                continue
            if (
                post.id in user_commented_post_ids
            ):
                continue
            valid_post_ids.append(post_id)

    if not valid_post_ids:
        return []

    SCORE_FRIEND_LIKE = 2
    SCORE_FRIEND_COMMENT = 5
    SCORE_RECENCY_FACTOR = 10
    RECENCY_HALFLIFE_DAYS = 7
    SCORE_TOTAL_LIKES_FACTOR = 0.1
    SCORE_TOTAL_COMMENTS_FACTOR = 0.2

    user_bookmarked_post_ids = {
        bookmark.post_id for bookmark in current_user.bookmarks
    }

    all_posts = Post.query.all()

    potential_posts = []
    for post in all_posts:
        if post.user_id == user_id:
            continue
        if post.id in user_liked_post_ids:
            continue
        if post.id in user_commented_post_ids:
            continue
        if post.id in user_bookmarked_post_ids:
            continue
        potential_posts.append(post)

    if not potential_posts:
        return []

    scored_posts = []

    db = current_app.extensions["sqlalchemy"]
    all_likes_query = db.session.query(Like.post_id, Like.user_id).all()
    post_likes_map = defaultdict(list)
    for post_id, liker_id in all_likes_query:
        post_likes_map[post_id].append(liker_id)

    all_comments_query = db.session.query(Comment.post_id, Comment.user_id).all()
    post_comments_map = defaultdict(list)
    for post_id, commenter_id in all_comments_query:
        post_comments_map[post_id].append(commenter_id)

    friend_usernames = {
        friend.id: friend.username
        for friend in User.query.filter(User.id.in_(friend_ids)).all()
    }

    for post in potential_posts:
        score = 0
        reason_parts = []

        friend_likers_usernames = []
        friend_commenters_usernames = []

        for liker_id in post_likes_map.get(post.id, []):
            if liker_id in friend_ids:
                score += SCORE_FRIEND_LIKE
                if friend_usernames.get(liker_id):
                    friend_likers_usernames.append(friend_usernames[liker_id])

        for commenter_id in post_comments_map.get(post.id, []):
            if commenter_id in friend_ids:
                score += SCORE_FRIEND_COMMENT
                if friend_usernames.get(commenter_id):
                    friend_commenters_usernames.append(friend_usernames[commenter_id])

        post_timestamp_aware = post.timestamp.replace(tzinfo=timezone.utc)
        days_old = (datetime.now(timezone.utc) - post_timestamp_aware).days
        if days_old < 0:
            days_old = 0

        recency_score = SCORE_RECENCY_FACTOR * (
            0.5 ** (days_old / RECENCY_HALFLIFE_DAYS)
        )
        score += recency_score

        total_likes = len(post_likes_map.get(post.id, []))
        total_comments = len(post_comments_map.get(post.id, []))

        score += SCORE_TOTAL_LIKES_FACTOR * total_likes
        score += SCORE_TOTAL_COMMENTS_FACTOR * total_comments

        reason_string = ""
        if friend_likers_usernames:
            if len(friend_likers_usernames) > 2:
                reason_parts.append(
                    f"Liked by {friend_likers_usernames[0]}, {friend_likers_usernames[1]}, and {len(friend_likers_usernames)-2} others"
                )
            else:
                reason_parts.append(f"Liked by {', '.join(friend_likers_usernames)}")

        if friend_commenters_usernames:
            if len(friend_commenters_usernames) > 2:
                reason_parts.append(
                    f"Commented on by {friend_commenters_usernames[0]}, {friend_commenters_usernames[1]}, and {len(friend_commenters_usernames)-2} others"
                )
            else:
                reason_parts.append(
                    f"Commented on by {', '.join(friend_commenters_usernames)}"
                )

        if reason_parts:
            reason_string = ". ".join(reason_parts) + "."
        else:
            if recency_score > (
                SCORE_FRIEND_LIKE + SCORE_FRIEND_COMMENT
            ):
                reason_string = "Trending post."
            elif (
                SCORE_TOTAL_LIKES_FACTOR * total_likes
                + SCORE_TOTAL_COMMENTS_FACTOR * total_comments
            ) > (
                SCORE_FRIEND_LIKE + SCORE_FRIEND_COMMENT
            ):
                reason_string = "Popular post."
            else:
                reason_string = "Suggested for you."

        scored_posts.append({"post": post, "score": score, "reason": reason_string})

    scored_posts.sort(key=lambda x: x["score"], reverse=True)

    final_recommendations = [
        (item["post"], item["reason"]) for item in scored_posts[:limit]
    ]

    return final_recommendations


def suggest_groups_to_join(user_id, limit=5):
    """Suggest groups that the current user's friends are members of."""
    current_user = db.session.get(User, user_id)
    if not current_user:
        return []

    user_friendships = Friendship.query.filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
        Friendship.status == "accepted",
    ).all()
    friend_ids = set()
    for friendship in user_friendships:
        if friendship.user_id == user_id:
            friend_ids.add(friendship.friend_id)
        else:
            friend_ids.add(friendship.user_id)

    if not friend_ids:
        return []

    user_groups_ids = {group.id for group in current_user.joined_groups.all()}

    groups_of_friends_counts = defaultdict(int)
    for friend_id in friend_ids:
        friend = db.session.get(User, friend_id)
        if friend:
            for group in friend.joined_groups.all():
                if group.id not in user_groups_ids:
                    groups_of_friends_counts[group.id] += 1

    sorted_group_ids = [
        gid
        for gid, count in sorted(
            groups_of_friends_counts.items(), key=lambda item: item[1], reverse=True
        )
    ]

    if not sorted_group_ids:
        return []

    suggested_groups_unordered = Group.query.filter(
        Group.id.in_(sorted_group_ids)
    ).all()

    group_map = {group.id: group for group in suggested_groups_unordered}

    ordered_suggested_groups = [
        group_map[gid] for gid in sorted_group_ids if gid in group_map
    ]

    return ordered_suggested_groups[:limit]


def suggest_events_to_attend(user_id, limit=5):
    db_ext = current_app.extensions["sqlalchemy"]
    current_user = db_ext.session.get(User, user_id)
    if not current_user:
        return []

    user_friendships = Friendship.query.filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
        Friendship.status == "accepted",
    ).all()
    friend_ids = set()
    for friendship in user_friendships:
        if friendship.user_id == user_id:
            friend_ids.add(friendship.friend_id)
        else:
            friend_ids.add(friendship.user_id)

    user_rsvpd_event_ids = {
        rsvp.event_id for rsvp in EventRSVP.query.filter_by(user_id=user_id).all()
    }
    user_organized_event_ids = {
        event.id for event in Event.query.filter_by(user_id=user_id).all()
    }
    excluded_event_ids = user_rsvpd_event_ids.union(user_organized_event_ids)

    recommendations = {}

    if friend_ids:
        events_by_friends_rsvps = (
            db.session.query(
                EventRSVP.event_id,
                func.count(EventRSVP.user_id).label("friend_rsvp_count"),
            )
            .filter(
                EventRSVP.user_id.in_(friend_ids),
                EventRSVP.status.in_(["Attending", "Maybe"]),
            )
            .group_by(EventRSVP.event_id)
            .all()
        )

        for event_id, count in events_by_friends_rsvps:
            if event_id not in excluded_event_ids:
                recommendations[event_id] = recommendations.get(event_id, 0) + count * 2

    popular_events_rsvps = (
        db.session.query(
            EventRSVP.event_id, func.count(EventRSVP.user_id).label("total_rsvp_count")
        )
        .filter(EventRSVP.status.in_(["Attending", "Maybe"]))
        .group_by(EventRSVP.event_id)
        .all()
    )

    for event_id, count in popular_events_rsvps:
        if event_id not in excluded_event_ids:
            recommendations[event_id] = recommendations.get(event_id, 0) + count

    sorted_recommended_event_ids = [
        event_id
        for event_id, score in sorted(
            recommendations.items(), key=lambda item: item[1], reverse=True
        )
    ]

    final_event_ids = sorted_recommended_event_ids[:limit]

    if not final_event_ids:
        return []

    event_map = {
        event.id: event
        for event in Event.query.filter(Event.id.in_(final_event_ids)).all()
    }
    suggested_events = [event_map[eid] for eid in final_event_ids if eid in event_map]

    return suggested_events


def suggest_polls_to_vote(user_id, limit=5):
    db_ext = current_app.extensions["sqlalchemy"]
    current_user = db_ext.session.get(User, user_id)
    if not current_user:
        return []

    user_friendships = Friendship.query.filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
        Friendship.status == "accepted",
    ).all()
    friend_ids = set()
    for friendship in user_friendships:
        if friendship.user_id == user_id:
            friend_ids.add(friendship.friend_id)
        else:
            friend_ids.add(friendship.user_id)

    user_voted_poll_ids = {
        vote.poll_id for vote in PollVote.query.filter_by(user_id=user_id).all()
    }
    user_created_poll_ids = {
        poll.id for poll in Poll.query.filter_by(user_id=user_id).all()
    }
    excluded_poll_ids = user_voted_poll_ids.union(user_created_poll_ids)

    recommended_poll_scores = {}

    if friend_ids:
        friend_created_polls = Poll.query.filter(
            Poll.user_id.in_(friend_ids), Poll.id.notin_(excluded_poll_ids)
        ).all()
        for poll in friend_created_polls:
            recommended_poll_scores[poll.id] = (
                recommended_poll_scores.get(poll.id, 0) + 5
            )

    popular_poll_votes = (
        db.session.query(PollVote.poll_id, func.count(PollVote.id).label("vote_count"))
        .group_by(PollVote.poll_id)
        .order_by(func.count(PollVote.id).desc())
        .all()
    )

    for poll_id, vote_count in popular_poll_votes:
        if poll_id not in excluded_poll_ids:
            recommended_poll_scores[poll_id] = (
                recommended_poll_scores.get(poll_id, 0) + vote_count
            )

    sorted_recommended_poll_ids = [
        pid
        for pid, score in sorted(
            recommended_poll_scores.items(), key=lambda item: item[1], reverse=True
        )
    ]

    final_poll_ids = sorted_recommended_poll_ids[:limit]

    if not final_poll_ids:
        return []

    poll_map = {
        poll.id: poll for poll in Poll.query.filter(Poll.id.in_(final_poll_ids)).all()
    }
    suggested_polls = [poll_map[pid] for pid in final_poll_ids if pid in poll_map]

    return suggested_polls


def suggest_hashtags(user_id, limit=5):
    """Suggest popular hashtags not yet used by the user."""
    all_posts = Post.query.all()
    if not all_posts:
        return []

    hashtag_counts = Counter()
    for post in all_posts:
        if post.hashtags:
            tags = [tag.strip() for tag in post.hashtags.split(",") if tag.strip()]
            hashtag_counts.update(tags)

    if not hashtag_counts:
        return []

    user_posts = Post.query.filter_by(user_id=user_id).all()
    user_hashtags = set()
    if user_posts:
        for post in user_posts:
            if post.hashtags:
                tags = [tag.strip() for tag in post.hashtags.split(",") if tag.strip()]
                for tag in tags:
                    user_hashtags.add(tag)

    popular_hashtags = [tag for tag, count in hashtag_counts.most_common()]

    suggested_tags = [tag for tag in popular_hashtags if tag not in user_hashtags]

    return suggested_tags[:limit]


def get_trending_hashtags(top_n=10):
    """
    Queries all posts, counts hashtag occurrences, and returns the top N trending hashtags.
    """
    all_posts = Post.query.all()
    if not all_posts:
        return []

    hashtag_counts = Counter()
    for post in all_posts:
        if post.hashtags:
            tags = [
                tag.strip().lower() for tag in post.hashtags.split(",") if tag.strip()
            ]
            if tags:
                hashtag_counts.update(tags)

    if not hashtag_counts:
        return []

    top_hashtags_with_counts = hashtag_counts.most_common(top_n)

    trending_hashtags = [tag for tag, count in top_hashtags_with_counts]

    return trending_hashtags


WEIGHT_RECENT_LIKE = 1
WEIGHT_RECENT_COMMENT = 3
WEIGHT_RECENT_SHARE = 2
TRENDING_POST_AGE_FACTOR_SCALE = 5


def suggest_trending_posts(user_id, limit=5, since_days=7):
    """
    Suggests trending posts based on recent activity (likes, comments) and post recency.
    Excludes posts by the user, or already interacted with/bookmarked by the user.
    """
    db_ext = current_app.extensions["sqlalchemy"]
    current_user = None
    if user_id is not None:
        current_user = db_ext.session.get(User, user_id)

    cutoff_date_aware = datetime.now(timezone.utc) - timedelta(days=since_days)
    cutoff_date_naive = cutoff_date_aware.replace(tzinfo=None)

    user_liked_post_ids = set()
    user_commented_post_ids = set()
    user_bookmarked_post_ids = set()

    if user_id is not None:
        user_liked_post_ids = {
            like.post_id for like in Like.query.filter_by(user_id=user_id).all()
        }
        user_commented_post_ids = {
            comment.post_id
            for comment in Comment.query.filter_by(user_id=user_id).all()
        }
        if current_user:
            user_bookmarked_post_ids = {
                bookmark.post_id for bookmark in current_user.bookmarks
            }

    excluded_post_ids = user_liked_post_ids.union(user_commented_post_ids).union(
        user_bookmarked_post_ids
    )

    recent_posts_query = Post.query.filter(Post.timestamp >= cutoff_date_naive)

    posts_with_recent_likes_ids = (
        db.session.query(Like.post_id)
        .filter(Like.timestamp >= cutoff_date_naive)
        .distinct()
    )

    posts_with_recent_comments_ids = (
        db.session.query(Comment.post_id)
        .filter(Comment.timestamp >= cutoff_date_naive)
        .distinct()
    )

    posts_with_recent_shares_ids = (
        db.session.query(SharedPost.original_post_id)
        .filter(SharedPost.shared_at >= cutoff_date_naive)
        .distinct()
    )

    candidate_post_ids = set()
    for post in recent_posts_query.all():
        candidate_post_ids.add(post.id)
    for r_like_id in posts_with_recent_likes_ids:
        candidate_post_ids.add(r_like_id[0])
    for r_comment_id in posts_with_recent_comments_ids:
        candidate_post_ids.add(r_comment_id[0])
    for r_share_id in posts_with_recent_shares_ids:
        candidate_post_ids.add(r_share_id[0])

    valid_candidate_post_ids = []
    if candidate_post_ids:
        candidate_posts_q = Post.query.filter(Post.id.in_(list(candidate_post_ids)))
        for post in candidate_posts_q:
            if post.user_id == user_id:
                continue
            if post.id in excluded_post_ids:
                continue
            valid_candidate_post_ids.append(post.id)

    if not valid_candidate_post_ids:
        return []

    recent_likes_counts = (
        db.session.query(Like.post_id, func.count(Like.id).label("like_count"))
        .filter(
            Like.post_id.in_(valid_candidate_post_ids),
            Like.timestamp >= cutoff_date_naive,
        )
        .group_by(Like.post_id)
        .all()
    )
    likes_map = {post_id: count for post_id, count in recent_likes_counts}

    recent_comments_counts = (
        db.session.query(Comment.post_id, func.count(Comment.id).label("comment_count"))
        .filter(
            Comment.post_id.in_(valid_candidate_post_ids),
            Comment.timestamp >= cutoff_date_naive,
        )
        .group_by(Comment.post_id)
        .all()
    )
    comments_map = {post_id: count for post_id, count in recent_comments_counts}

    recent_shares_counts = (
        db.session.query(
            SharedPost.original_post_id, func.count(SharedPost.id).label("share_count")
        )
        .filter(
            SharedPost.original_post_id.in_(valid_candidate_post_ids),
            SharedPost.shared_at >= cutoff_date_naive,
        )
        .group_by(SharedPost.original_post_id)
        .all()
    )
    shares_map = {post_id: count for post_id, count in recent_shares_counts}

    scored_posts = []
    posts_to_score = Post.query.filter(Post.id.in_(valid_candidate_post_ids)).all()

    for post in posts_to_score:
        score = 0

        score += likes_map.get(post.id, 0) * WEIGHT_RECENT_LIKE
        score += comments_map.get(post.id, 0) * WEIGHT_RECENT_COMMENT
        score += shares_map.get(post.id, 0) * WEIGHT_RECENT_SHARE

        post_age_days = (
            datetime.utcnow() - post.timestamp
        ).days
        if post_age_days < 0:
            post_age_days = 0

        if (
            post_age_days <= since_days
        ):
            age_factor_bonus = (
                ((since_days - post_age_days) / float(since_days))
                * TRENDING_POST_AGE_FACTOR_SCALE
                if since_days > 0
                else 0
            )
            score += age_factor_bonus

        if score > 0:
            scored_posts.append({"post": post, "score": score})

    scored_posts.sort(key=lambda x: x["score"], reverse=True)

    final_posts = [item["post"] for item in scored_posts[:limit]]
    return final_posts


def update_trending_hashtags(top_n=10, since_days=7):
    """
    Calculates hashtag frequencies from recent posts, deletes existing trending
    hashtags, and populates TrendingHashtag table with the new top N hashtags.
    """
    db = current_app.extensions["sqlalchemy"]
    current_app.logger.info(
        f"Starting update_trending_hashtags job. Top N: {top_n}, Since Days: {since_days}"
    )
    try:
        cutoff_date_aware = datetime.now(timezone.utc) - timedelta(days=since_days)
        cutoff_date_naive = cutoff_date_aware.replace(tzinfo=None)
        recent_posts = Post.query.filter(Post.timestamp >= cutoff_date_naive).all()

        if not recent_posts:
            current_app.logger.info(
                "No recent posts found to update trending hashtags."
            )
            try:
                db.session.begin_nested()
                num_deleted = TrendingHashtag.query.delete()
                db.session.commit()
                current_app.logger.info(
                    f"Cleared {num_deleted} existing trending hashtags as no recent posts were found."
                )
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error clearing trending hashtags: {e}")
            return

        hashtag_counts = Counter()
        for post in recent_posts:
            if post.hashtags:
                tags = [
                    tag.strip().lower()
                    for tag in post.hashtags.split(",")
                    if tag.strip()
                ]
                if tags:
                    hashtag_counts.update(tags)

        if not hashtag_counts:
            current_app.logger.info("No hashtags found in recent posts.")
            try:
                db.session.begin_nested()
                num_deleted = TrendingHashtag.query.delete()
                db.session.commit()
                current_app.logger.info(
                    f"Cleared {num_deleted} existing trending hashtags as no new ones were found."
                )
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error clearing trending hashtags: {e}")
            return

        top_hashtags_with_scores = hashtag_counts.most_common(top_n)

        with db.session.begin_nested():
            TrendingHashtag.query.delete()

            for rank, (tag, score) in enumerate(top_hashtags_with_scores, 1):
                new_trending_hashtag = TrendingHashtag(
                    hashtag=tag,
                    score=float(score),
                    rank=rank,
                    calculated_at=datetime.now(timezone.utc),
                )
                db.session.add(new_trending_hashtag)

        db.session.commit()
        current_app.logger.info(
            f"Successfully updated {len(top_hashtags_with_scores)} trending hashtags."
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in update_trending_hashtags job: {e}")


def get_personalized_feed_posts(user_id, limit=20):
    """
    Generates a personalized feed of posts for a given user.
    Combines posts from followed users, friends' activity, trending posts, and user's groups.
    Ensures posts are not duplicated and are ranked appropriately.
    """
    current_user = db.session.get(User, user_id)
    if not current_user:
        current_app.logger.warning(
            f"get_personalized_feed_posts: User with ID {user_id} not found."
        )
        return []

    SCORE_SOURCE_FOLLOWED = 1000
    SCORE_SOURCE_FRIEND_ACTIVITY = 500
    SCORE_SOURCE_GROUP = 300
    SCORE_SOURCE_TRENDING = 100
    RECENCY_HALFLIFE_DAYS = 7
    RECENCY_MAX_SCORE = 100

    feed_candidates = {}

    user_authored_post_ids = {
        post.id
        for post in Post.query.filter_by(user_id=user_id).with_entities(Post.id).all()
    }
    user_liked_post_ids = {
        like.post_id
        for like in Like.query.filter_by(user_id=user_id)
        .with_entities(Like.post_id)
        .all()
    }
    user_commented_post_ids = {
        comment.post_id
        for comment in Comment.query.filter_by(user_id=user_id)
        .with_entities(Comment.post_id)
        .all()
    }
    user_bookmarked_post_ids = {bookmark.post_id for bookmark in current_user.bookmarks}

    excluded_post_ids = (
        user_authored_post_ids.union(user_liked_post_ids)
        .union(user_commented_post_ids)
        .union(user_bookmarked_post_ids)
    )

    def calculate_recency_score(post_timestamp):
        post_timestamp_aware = post_timestamp.replace(tzinfo=timezone.utc)
        days_old = (datetime.now(timezone.utc) - post_timestamp_aware).days
        if days_old < 0:
            days_old = 0
        score = RECENCY_MAX_SCORE * (0.5 ** (days_old / RECENCY_HALFLIFE_DAYS))
        return score

    def add_candidate(post, source_score, reason_prefix, entity_name=""):
        if post.id in excluded_post_ids:
            return

        recency_score = calculate_recency_score(post.timestamp)
        final_score = source_score + recency_score

        reason = reason_prefix
        if entity_name:
            reason = f"{reason_prefix}: {entity_name}"

        if (
            post.id not in feed_candidates
            or final_score > feed_candidates[post.id]["score"]
        ):
            feed_candidates[post.id] = {
                "post": post,
                "score": final_score,
                "reason": reason,
            }

    friends = current_user.get_friends()
    friend_ids = {friend.id for friend in friends}
    if friend_ids:
        posts_from_followed = (
            Post.query.filter(
                Post.user_id.in_(friend_ids),
                Post.id.notin_(excluded_post_ids),
            )
            .order_by(Post.timestamp.desc())
            .limit(limit * 3)
            .all()
        )
        for post in posts_from_followed:
            author_username = post.author.username if post.author else "Unknown"
            add_candidate(
                post, SCORE_SOURCE_FOLLOWED, "From user you follow", author_username
            )

    friend_activity_posts = suggest_posts_to_read(user_id, limit=limit * 3)
    for post, reason in friend_activity_posts:
        if post.id in excluded_post_ids:
            continue
        recency_score = calculate_recency_score(post.timestamp)
        final_score = SCORE_SOURCE_FRIEND_ACTIVITY + recency_score
        if (
            post.id not in feed_candidates
            or final_score > feed_candidates[post.id]["score"]
        ):
            feed_candidates[post.id] = {
                "post": post,
                "score": final_score,
                "reason": reason,
            }

    trending = suggest_trending_posts(
        user_id, limit=limit * 2, since_days=14
    )
    for post in trending:
        if post.id in excluded_post_ids:
            continue
        add_candidate(post, SCORE_SOURCE_TRENDING, "Trending post")

    if hasattr(Post, "group_id"):
        user_groups = current_user.joined_groups.all()
        group_ids = {group.id for group in user_groups}
        if group_ids:
            posts_from_groups = (
                Post.query.filter(
                    Post.group_id.in_(group_ids),
                    Post.id.notin_(excluded_post_ids),
                )
                .order_by(Post.timestamp.desc())
                .limit(limit * 3)
                .all()
            )
            for post in posts_from_groups:
                group_name = "Unknown Group"
                if post.group_id:
                    group = Group.query.get(post.group_id)
                    if group:
                        group_name = group.name
                add_candidate(post, SCORE_SOURCE_GROUP, "From your group", group_name)
    else:
        current_app.logger.info(
            f"get_personalized_feed_posts: Post model does not have 'group_id'. Skipping group posts source for user {user_id}."
        )

    if not feed_candidates:
        return []

    final_candidate_list = list(feed_candidates.values())

    final_candidate_list.sort(
        key=lambda x: (x["score"], x["post"].timestamp), reverse=True
    )

    result_with_reasons = [
        (item["post"], item["reason"]) for item in final_candidate_list[:limit]
    ]

    current_app.logger.info(
        f"get_personalized_feed_posts: Generated {len(result_with_reasons)} posts for user {user_id}. Candidates found: {len(feed_candidates)}"
    )
    return result_with_reasons


def get_on_this_day_content(user_id):
    """
    Retrieves posts and events created by the user on the current month and day from previous years.
    """
    today = datetime.now(timezone.utc)
    current_month = today.month
    current_day = today.day
    current_year = today.year

    posts_on_this_day = Post.query.filter(
        Post.user_id == user_id,
        extract("month", Post.timestamp) == current_month,
        extract("day", Post.timestamp) == current_day,
        extract("year", Post.timestamp) != current_year,
    ).all()

    all_user_events = Event.query.filter(Event.user_id == user_id).all()

    events_on_this_day = []
    for event in all_user_events:
        if event.date:
            if (
                event.date.month == current_month
                and event.date.day == current_day
                and event.date.year != current_year
            ):
                events_on_this_day.append(event)
        else:
            current_app.logger.warning(
                f"Event ID {event.id} has no date attribute or it is None."
            )

    return {"posts": posts_on_this_day, "events": events_on_this_day}
