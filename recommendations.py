from app import db # Added app for logger
from models import User, Post, Group, Friendship, Like, Event, EventRSVP, Poll, PollVote, Comment, SharedPost, TrendingHashtag # Added SharedPost and TrendingHashtag
from sqlalchemy import func, or_, extract
from collections import defaultdict, Counter
from datetime import datetime, timedelta # Ensure datetime and timedelta are imported
from flask import current_app

def suggest_users_to_follow(user_id, limit=5):
    """Suggest users who are friends of the current user's friends."""
    current_user = User.query.get(user_id)
    if not current_user:
        return []

    friends_of_friends = defaultdict(int)

    # Get friends of the current user
    user_friendships = Friendship.query.filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
        Friendship.status == 'accepted'
    ).all()
    friend_ids = set()
    for friendship in user_friendships:
        if friendship.user_id == user_id:
            friend_ids.add(friendship.friend_id)
        else:
            friend_ids.add(friendship.user_id)

    # Get friends of friends
    for friend_id in friend_ids:
        friend_of_friend_friendships = Friendship.query.filter(
            or_(Friendship.user_id == friend_id, Friendship.friend_id == friend_id),
            Friendship.status == 'accepted'
        ).all()
        for fof_friendship in friend_of_friend_friendships:
            fof_id = fof_friendship.friend_id if fof_friendship.user_id == friend_id else fof_friendship.user_id
            if fof_id != user_id and fof_id not in friend_ids:
                # Exclude users with pending/rejected requests
                existing_request = Friendship.query.filter(
                    or_(
                        (Friendship.user_id == user_id) & (Friendship.friend_id == fof_id),
                        (Friendship.user_id == fof_id) & (Friendship.friend_id == user_id)
                    ),
                    Friendship.status.in_(['pending', 'rejected'])
                ).first()
                if not existing_request:
                    friends_of_friends[fof_id] += 1

    # Sort by the number of mutual friends (or any other ranking logic)
    suggested_user_ids = [uid for uid, count in sorted(friends_of_friends.items(), key=lambda item: item[1], reverse=True)]

    # Fetch User objects
    suggested_users = User.query.filter(User.id.in_(suggested_user_ids)).all()

    # Maintain order from sorted list
    ordered_suggested_users = sorted(suggested_users, key=lambda u: suggested_user_ids.index(u.id))

    return ordered_suggested_users[:limit]

def suggest_posts_to_read(user_id, limit=5):
    """Suggest posts liked or commented on by the current user's friends, ranked by recency of interaction."""
    current_user = User.query.get(user_id)
    if not current_user:
        return []

    # 1. Identify Friends
    user_friendships = Friendship.query.filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
        Friendship.status == 'accepted'
    ).all()
    friend_ids = set()
    for friendship in user_friendships:
        if friendship.user_id == user_id:
            friend_ids.add(friendship.friend_id)
        else:
            friend_ids.add(friendship.user_id)

    if not friend_ids:
        return []

    # Store posts and their latest interaction timestamp
    # Using defaultdict to store the latest timestamp for each post
    recommended_posts_with_ts = defaultdict(lambda: None)

    # 2. Fetch Posts Liked by Friends
    likes_by_friends = db.session.query(Like.post_id, Like.timestamp).filter(
        Like.user_id.in_(friend_ids)
    ).all()

    for post_id, like_timestamp in likes_by_friends:
        if recommended_posts_with_ts[post_id] is None or like_timestamp > recommended_posts_with_ts[post_id]:
            recommended_posts_with_ts[post_id] = like_timestamp

    # 3. Fetch Posts Commented on by Friends
    comments_by_friends = db.session.query(Comment.post_id, Comment.timestamp).filter(
        Comment.user_id.in_(friend_ids)
    ).all()

    for post_id, comment_timestamp in comments_by_friends:
        if recommended_posts_with_ts[post_id] is None or comment_timestamp > recommended_posts_with_ts[post_id]:
            recommended_posts_with_ts[post_id] = comment_timestamp

    if not recommended_posts_with_ts:
        return []

    # 4. Combine and Rank Recommendations
    # Exclude posts created by the current user
    # Exclude posts already liked or commented on by the current user
    user_liked_post_ids = {like.post_id for like in Like.query.filter_by(user_id=user_id).all()}
    user_commented_post_ids = {comment.post_id for comment in Comment.query.filter_by(user_id=user_id).all()}

    valid_post_ids = []
    for post_id in recommended_posts_with_ts.keys():
        post = Post.query.get(post_id) # Fetch the post object
        if post: # Ensure post exists
            if post.user_id == user_id:  # Exclude posts by current user
                continue
            if post_id in user_liked_post_ids:  # Exclude posts liked by current user
                continue
            if post_id in user_commented_post_ids:  # Exclude posts commented on by current user
                continue
            valid_post_ids.append(post_id)

    if not valid_post_ids:
        return []

    # 5. Sort and Limit
    # Sort by the interaction timestamp stored in recommended_posts_with_ts
    # We need to sort the valid_post_ids based on their timestamps from recommended_posts_with_ts
    # NEW IMPLEMENTATION STARTS HERE

    # Scoring constants
    SCORE_FRIEND_LIKE = 2
    SCORE_FRIEND_COMMENT = 5
    SCORE_RECENCY_FACTOR = 10  # Adjust based on desired impact
    RECENCY_HALFLIFE_DAYS = 7 # For calculating recency score, e.g. score halves every 7 days
    SCORE_TOTAL_LIKES_FACTOR = 0.1  # Adjust
    SCORE_TOTAL_COMMENTS_FACTOR = 0.2  # Adjust

    # 2. Exclude posts by the current user, already interacted with, or bookmarked
    user_liked_post_ids = {like.post_id for like in Like.query.filter_by(user_id=user_id).all()}
    user_commented_post_ids = {comment.post_id for comment in Comment.query.filter_by(user_id=user_id).all()}
    user_bookmarked_post_ids = {bookmark.post_id for bookmark in current_user.bookmarks} # Assumes Bookmark model is imported and User.bookmarks relationship exists

    # Fetch all posts initially - this could be optimized for very large datasets
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

    # 3. Calculate scores and generate reasons
    scored_posts = []

    # Pre-fetch all likes and comments for efficiency if dealing with many posts
    # This avoids N+1 queries within the loop when accessing post.likes or post.comments
    all_likes_query = db.session.query(Like.post_id, Like.user_id).all()
    post_likes_map = defaultdict(list)
    for post_id, liker_id in all_likes_query:
        post_likes_map[post_id].append(liker_id)

    all_comments_query = db.session.query(Comment.post_id, Comment.user_id).all()
    post_comments_map = defaultdict(list)
    for post_id, commenter_id in all_comments_query:
        post_comments_map[post_id].append(commenter_id)

    # Pre-fetch friend usernames if needed for reason strings to avoid DB calls in loop
    friend_usernames = {friend.id: friend.username for friend in User.query.filter(User.id.in_(friend_ids)).all()}


    for post in potential_posts:
        score = 0
        reason_parts = []

        # Friend Interaction Score
        friend_likers_usernames = []
        friend_commenters_usernames = []

        # Likes by friends
        for liker_id in post_likes_map.get(post.id, []):
            if liker_id in friend_ids:
                score += SCORE_FRIEND_LIKE
                if friend_usernames.get(liker_id): # Add username if available
                    friend_likers_usernames.append(friend_usernames[liker_id])

        # Comments by friends
        for commenter_id in post_comments_map.get(post.id, []):
            if commenter_id in friend_ids:
                score += SCORE_FRIEND_COMMENT
                if friend_usernames.get(commenter_id): # Add username if available
                    friend_commenters_usernames.append(friend_usernames[commenter_id])

        # Post Recency Score
        # Using a simple decay: score = factor / (days_old + 1)
        # More sophisticated decay: factor * (0.5 ^ (days_old / half_life_days))
        days_old = (datetime.utcnow() - post.timestamp).days
        if days_old < 0: days_old = 0 # Handle potential future timestamps gracefully, though unlikely

        # recency_score = SCORE_RECENCY_FACTOR / (days_old + 1)
        # Using exponential decay:
        recency_score = SCORE_RECENCY_FACTOR * (0.5 ** (days_old / RECENCY_HALFLIFE_DAYS))
        score += recency_score

        # Post Popularity Score
        total_likes = len(post_likes_map.get(post.id, []))
        total_comments = len(post_comments_map.get(post.id, []))

        score += SCORE_TOTAL_LIKES_FACTOR * total_likes
        score += SCORE_TOTAL_COMMENTS_FACTOR * total_comments

        # Reason Generation
        if friend_likers_usernames:
            if len(friend_likers_usernames) > 2:
                reason_parts.append(f"Liked by {friend_likers_usernames[0]}, {friend_likers_usernames[1]}, and {len(friend_likers_usernames)-2} others")
            else:
                reason_parts.append(f"Liked by {', '.join(friend_likers_usernames)}")

        if friend_commenters_usernames:
            if len(friend_commenters_usernames) > 2:
                reason_parts.append(f"Commented on by {friend_commenters_usernames[0]}, {friend_commenters_usernames[1]}, and {len(friend_commenters_usernames)-2} others")
            else:
                reason_parts.append(f"Commented on by {', '.join(friend_commenters_usernames)}")

        reason_string = ""
        if reason_parts:
            reason_string = ". ".join(reason_parts) + "."
        else:
            # Fallback reason if no specific friend interactions drove the recommendation strongly
            # We can make this smarter based on which score component was highest
            if recency_score > (SCORE_FRIEND_LIKE + SCORE_FRIEND_COMMENT): # Example condition
                 reason_string = "Trending post."
            elif (SCORE_TOTAL_LIKES_FACTOR * total_likes + SCORE_TOTAL_COMMENTS_FACTOR * total_comments) > (SCORE_FRIEND_LIKE + SCORE_FRIEND_COMMENT): # Example condition
                 reason_string = "Popular post."
            else:
                 reason_string = "Suggested for you."


        scored_posts.append({'post': post, 'score': score, 'reason': reason_string})

    # 4. Sort and Limit
    scored_posts.sort(key=lambda x: x['score'], reverse=True)

    # Prepare final list of (Post, reason_string) tuples
    final_recommendations = [(item['post'], item['reason']) for item in scored_posts[:limit]]

    return final_recommendations

def suggest_groups_to_join(user_id, limit=5):
    """Suggest groups that the current user's friends are members of."""
    current_user = User.query.get(user_id)
    if not current_user:
        return []

    # Get friends of the current user
    user_friendships = Friendship.query.filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
        Friendship.status == 'accepted'
    ).all()
    friend_ids = set()
    for friendship in user_friendships:
        if friendship.user_id == user_id:
            friend_ids.add(friendship.friend_id)
        else:
            friend_ids.add(friendship.user_id)

    if not friend_ids:
        return []

    # Get groups joined by friends
    # Assuming Group has a 'members' relationship that is a list of Users
    # and User has a 'groups' relationship.
    # A more direct way if there's a group_members association table:
    # group_members = db.Table('group_members', db.metadata,
    #     db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    #     db.Column('group_id', db.Integer, db.ForeignKey('group.id'))
    # )
    # For now, let's assume `Group.members` exists and is usable for querying.
    # This part might need adjustment based on actual Group membership model.

    # A common way to model group membership is a secondary association table.
    # Let's assume 'group_members' is the name of this table.
    # If models.py defines Group.members as a relationship, this can be simpler.
    # e.g., Group.query.join(Group.members).filter(User.id.in_(friend_ids))

    # Let's use a subquery to count friend memberships per group
    # This assumes 'group_members' is the association table name in your models.py
    # If it's different, this will need to be changed.
    # If Group model has `members = db.relationship("User", secondary=group_members_table, ...)`
    # then we can query through that.

    # Let's assume a direct query on an association table if `Group.members` is not directly queryable this way.
    # For this example, I'll construct it assuming `group_members` is a table object.
    # This will likely need adjustment if `models.py` has a different structure.

    # Get groups current user is already in
    user_groups_ids = {group.id for group in current_user.groups}

    # Find groups friends are in, count members from friend list
    # This query is a bit complex and depends heavily on the Group membership model.
    # A placeholder for the logic:
    # 1. Find all groups that friends are members of.
    # 2. Count how many friends are in each of those groups.
    # 3. Exclude groups the current user is already in.
    # 4. Order by the count of friends, then limit.

    # Get groups current user is already in
    # User.joined_groups is a dynamic relationship, so it's a query builder
    user_groups_ids = {group.id for group in current_user.joined_groups.all()}

    groups_of_friends_counts = defaultdict(int)
    for friend_id in friend_ids:
        friend = User.query.get(friend_id)
        if friend:
            # friend.joined_groups is a query builder due to lazy='dynamic'
            for group in friend.joined_groups.all():
                if group.id not in user_groups_ids:
                    groups_of_friends_counts[group.id] += 1

    # Sort groups by the number of friends who are members, descending
    sorted_group_ids = [
        gid for gid, count in sorted(
            groups_of_friends_counts.items(), key=lambda item: item[1], reverse=True
        )
    ]

    if not sorted_group_ids:
        return []

    # Fetch the actual Group objects
    # We need to ensure the order from sorted_group_ids is preserved
    suggested_groups_unordered = Group.query.filter(Group.id.in_(sorted_group_ids)).all()

    # Create a mapping of id to group object for easy sorting
    group_map = {group.id: group for group in suggested_groups_unordered}

    # Order the groups based on sorted_group_ids
    ordered_suggested_groups = [group_map[gid] for gid in sorted_group_ids if gid in group_map]

    return ordered_suggested_groups[:limit]


def suggest_events_to_attend(user_id, limit=5):
    current_user = User.query.get(user_id)
    if not current_user:
        return []

    user_friendships = Friendship.query.filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
        Friendship.status == 'accepted'
    ).all()
    friend_ids = set()
    for friendship in user_friendships:
        if friendship.user_id == user_id:
            friend_ids.add(friendship.friend_id)
        else:
            friend_ids.add(friendship.user_id)

    user_rsvpd_event_ids = {rsvp.event_id for rsvp in EventRSVP.query.filter_by(user_id=user_id).all()}
    user_organized_event_ids = {event.id for event in Event.query.filter_by(user_id=user_id).all()}
    excluded_event_ids = user_rsvpd_event_ids.union(user_organized_event_ids)

    recommendations = {}

    if friend_ids:
        events_by_friends_rsvps = db.session.query(
                EventRSVP.event_id,
                func.count(EventRSVP.user_id).label('friend_rsvp_count')
            ).filter(
                EventRSVP.user_id.in_(friend_ids),
                EventRSVP.status.in_(['Attending', 'Maybe'])
            ).group_by(EventRSVP.event_id).all()

        for event_id, count in events_by_friends_rsvps:
            if event_id not in excluded_event_ids:
                 recommendations[event_id] = recommendations.get(event_id, 0) + count * 2

    popular_events_rsvps = db.session.query(
            EventRSVP.event_id,
            func.count(EventRSVP.user_id).label('total_rsvp_count')
        ).filter(
            EventRSVP.status.in_(['Attending', 'Maybe'])
        ).group_by(EventRSVP.event_id).all()

    for event_id, count in popular_events_rsvps:
        if event_id not in excluded_event_ids:
            recommendations[event_id] = recommendations.get(event_id, 0) + count

    sorted_recommended_event_ids = [
        event_id for event_id, score in sorted(recommendations.items(), key=lambda item: item[1], reverse=True)
    ] # No need to filter by excluded_event_ids again here, as it was done when populating recommendations

    final_event_ids = sorted_recommended_event_ids[:limit]

    if not final_event_ids:
        return []

    event_map = {event.id: event for event in Event.query.filter(Event.id.in_(final_event_ids)).all()}
    suggested_events = [event_map[eid] for eid in final_event_ids if eid in event_map]

    return suggested_events


def suggest_polls_to_vote(user_id, limit=5):
    current_user = User.query.get(user_id)
    if not current_user:
        return []

    user_friendships = Friendship.query.filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
        Friendship.status == 'accepted'
    ).all()
    friend_ids = set()
    for friendship in user_friendships:
        if friendship.user_id == user_id:
            friend_ids.add(friendship.friend_id)
        else:
            friend_ids.add(friendship.user_id)

    user_voted_poll_ids = {vote.poll_id for vote in PollVote.query.filter_by(user_id=user_id).all()}
    user_created_poll_ids = {poll.id for poll in Poll.query.filter_by(user_id=user_id).all()}
    excluded_poll_ids = user_voted_poll_ids.union(user_created_poll_ids)

    recommended_poll_scores = {} # poll_id -> score

    # 1. Polls created by friends
    if friend_ids:
        friend_created_polls = Poll.query.filter(
            Poll.user_id.in_(friend_ids),
            Poll.id.notin_(excluded_poll_ids)
        ).all()
        for poll in friend_created_polls:
            recommended_poll_scores[poll.id] = recommended_poll_scores.get(poll.id, 0) + 5 # High score for friend's poll

    # 2. Popular polls by vote count
    popular_poll_votes = db.session.query(
            PollVote.poll_id,
            func.count(PollVote.id).label('vote_count')
        ).group_by(PollVote.poll_id).order_by(func.count(PollVote.id).desc()).all()

    for poll_id, vote_count in popular_poll_votes:
        if poll_id not in excluded_poll_ids:
            # Add to score; if already present (e.g. friend's popular poll), this enhances its score
            recommended_poll_scores[poll_id] = recommended_poll_scores.get(poll_id, 0) + vote_count

    # Sort recommended poll IDs by score
    sorted_recommended_poll_ids = [
        pid for pid, score in sorted(recommended_poll_scores.items(), key=lambda item: item[1], reverse=True)
    ]

    final_poll_ids = sorted_recommended_poll_ids[:limit]

    if not final_poll_ids:
        return []

    poll_map = {poll.id: poll for poll in Poll.query.filter(Poll.id.in_(final_poll_ids)).all()}
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
            tags = [tag.strip() for tag in post.hashtags.split(',') if tag.strip()]
            hashtag_counts.update(tags)

    if not hashtag_counts:
        return []

    user_posts = Post.query.filter_by(user_id=user_id).all()
    user_hashtags = set()
    if user_posts:
        for post in user_posts:
            if post.hashtags:
                tags = [tag.strip() for tag in post.hashtags.split(',') if tag.strip()]
                for tag in tags:
                    user_hashtags.add(tag)

    # Get hashtags sorted by popularity
    popular_hashtags = [tag for tag, count in hashtag_counts.most_common()]

    # Filter out hashtags already used by the user
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
        if post.hashtags: # Ensure hashtags field is not None or empty
            # Split by comma, strip whitespace, convert to lowercase, and filter out empty strings
            tags = [tag.strip().lower() for tag in post.hashtags.split(',') if tag.strip()]
            if tags:
                hashtag_counts.update(tags)

    if not hashtag_counts:
        return []

    # Get the top_n hashtags along with their counts
    top_hashtags_with_counts = hashtag_counts.most_common(top_n)

    # Extract just the hashtag strings
    trending_hashtags = [tag for tag, count in top_hashtags_with_counts]

    return trending_hashtags


# Define constants for suggest_trending_posts
WEIGHT_RECENT_LIKE = 1
WEIGHT_RECENT_COMMENT = 3
WEIGHT_RECENT_SHARE = 2 # New weight for recent shares
TRENDING_POST_AGE_FACTOR_SCALE = 5 # Scales the impact of post age

def suggest_trending_posts(user_id, limit=5, since_days=7):
    """
    Suggests trending posts based on recent activity (likes, comments) and post recency.
    Excludes posts by the user, or already interacted with/bookmarked by the user.
    """
    current_user = User.query.get(user_id)
    if not current_user:
        return []

    cutoff_date = datetime.utcnow() - timedelta(days=since_days)

    # 1. Exclusions: Posts by the user, liked, commented, or bookmarked by the user
    user_liked_post_ids = {like.post_id for like in Like.query.filter_by(user_id=user_id).all()}
    user_commented_post_ids = {comment.post_id for comment in Comment.query.filter_by(user_id=user_id).all()}
    user_bookmarked_post_ids = {bookmark.post_id for bookmark in current_user.bookmarks}

    excluded_post_ids = user_liked_post_ids.union(user_commented_post_ids).union(user_bookmarked_post_ids)

    # 2. Identify candidate posts:
    #    - Created within since_days OR
    #    - Having likes within since_days OR
    #    - Having comments within since_days OR
    #    - Having shares within since_days

    # Posts created recently
    recent_posts_query = Post.query.filter(Post.timestamp >= cutoff_date)

    # Posts with recent likes
    posts_with_recent_likes_ids = db.session.query(Like.post_id).filter(Like.timestamp >= cutoff_date).distinct()

    # Posts with recent comments
    posts_with_recent_comments_ids = db.session.query(Comment.post_id).filter(Comment.timestamp >= cutoff_date).distinct()

    # Posts with recent shares
    posts_with_recent_shares_ids = db.session.query(SharedPost.original_post_id).filter(SharedPost.shared_at >= cutoff_date).distinct()

    # Combine IDs of all potentially relevant posts
    candidate_post_ids = set()
    for post in recent_posts_query.all():
        candidate_post_ids.add(post.id)
    for r_like_id in posts_with_recent_likes_ids:
        candidate_post_ids.add(r_like_id[0]) # query returns tuples
    for r_comment_id in posts_with_recent_comments_ids:
        candidate_post_ids.add(r_comment_id[0]) # query returns tuples
    for r_share_id in posts_with_recent_shares_ids:
        candidate_post_ids.add(r_share_id[0]) # query returns tuples

    # Filter out posts by the current user and other exclusions upfront
    # Also filter out posts that are older than since_days if they have no recent activity (implicit in how candidate_post_ids is built)
    valid_candidate_post_ids = []
    if candidate_post_ids:
        # Fetch actual post objects to check author
        candidate_posts_q = Post.query.filter(Post.id.in_(list(candidate_post_ids)))
        for post in candidate_posts_q:
            if post.user_id == user_id:
                continue
            if post.id in excluded_post_ids:
                continue
            valid_candidate_post_ids.append(post.id)

    if not valid_candidate_post_ids:
        return []

    # 3. Fetch recent interaction counts for valid candidate posts
    recent_likes_counts = db.session.query(
        Like.post_id, func.count(Like.id).label('like_count')
    ).filter(
        Like.post_id.in_(valid_candidate_post_ids),
        Like.timestamp >= cutoff_date
    ).group_by(Like.post_id).all()
    likes_map = {post_id: count for post_id, count in recent_likes_counts}

    recent_comments_counts = db.session.query(
        Comment.post_id, func.count(Comment.id).label('comment_count')
    ).filter(
        Comment.post_id.in_(valid_candidate_post_ids),
        Comment.timestamp >= cutoff_date
    ).group_by(Comment.post_id).all()
    comments_map = {post_id: count for post_id, count in recent_comments_counts}

    recent_shares_counts = db.session.query(
        SharedPost.original_post_id, func.count(SharedPost.id).label('share_count')
    ).filter(
        SharedPost.original_post_id.in_(valid_candidate_post_ids),
        SharedPost.shared_at >= cutoff_date
    ).group_by(SharedPost.original_post_id).all()
    shares_map = {post_id: count for post_id, count in recent_shares_counts}

    # 4. Calculate scores for each valid candidate post
    scored_posts = []
    # Fetch the post objects we will score
    posts_to_score = Post.query.filter(Post.id.in_(valid_candidate_post_ids)).all()

    for post in posts_to_score:
        score = 0

        # Interaction score
        score += likes_map.get(post.id, 0) * WEIGHT_RECENT_LIKE
        score += comments_map.get(post.id, 0) * WEIGHT_RECENT_COMMENT
        score += shares_map.get(post.id, 0) * WEIGHT_RECENT_SHARE

        # Post age factor: higher for newer posts within the window
        # This gives a small bonus to newer posts.
        # The score is higher if the post is more recent (smaller age_in_days_within_window)
        # We consider the age from the start of the window (cutoff_date) or its actual creation if newer.
        # Or simply its age from now, normalized by since_days.

        post_age_days = (datetime.utcnow() - post.timestamp).days
        if post_age_days < 0: post_age_days = 0 # Should not happen

        # Simple recency bonus: more points if post_age_days is small.
        # Max score if post_age_days = 0, min score if post_age_days = since_days
        # We want factor to be higher for newer posts.
        if post_age_days <= since_days: # Only apply strong recency if within the window
             # Normalized age factor: (since_days - post_age_days) / since_days
             # This gives 1 for brand new, 0 for post at the edge of since_days
             # Multiplied by a scaling factor
            age_factor_bonus = ((since_days - post_age_days) / float(since_days)) * TRENDING_POST_AGE_FACTOR_SCALE if since_days > 0 else 0
            score += age_factor_bonus
        # else: older posts get no specific "newness" bonus from this factor,
        # but can still trend if they have many recent likes/comments.

        # Only consider posts that have some activity or are recent enough
        # A post older than `since_days` must have recent likes/comments to have a score > 0 here (already filtered by candidate_post_ids logic)
        if score > 0 :
             scored_posts.append({'post': post, 'score': score})

    # 5. Sort and Limit
    scored_posts.sort(key=lambda x: x['score'], reverse=True)

    final_posts = [item['post'] for item in scored_posts[:limit]]
    return final_posts


def update_trending_hashtags(top_n=10, since_days=7):
    """
    Calculates hashtag frequencies from recent posts, deletes existing trending
    hashtags, and populates the TrendingHashtag table with the new top N hashtags.
    """
    current_app.logger.info(f"Starting update_trending_hashtags job. Top N: {top_n}, Since Days: {since_days}")
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=since_days)
        recent_posts = Post.query.filter(Post.timestamp >= cutoff_date).all()

        if not recent_posts:
            current_app.logger.info("No recent posts found to update trending hashtags.")
            # Clear existing hashtags if no recent posts, or decide to keep old ones
            try:
                db.session.begin_nested() # Start a nested transaction
                num_deleted = TrendingHashtag.query.delete()
                db.session.commit() # Commit the deletion
                current_app.logger.info(f"Cleared {num_deleted} existing trending hashtags as no recent posts were found.")
            except Exception as e:
                db.session.rollback() # Rollback in case of error
                current_app.logger.error(f"Error clearing trending hashtags: {e}")
            return

        hashtag_counts = Counter()
        for post in recent_posts:
            if post.hashtags:
                tags = [tag.strip().lower() for tag in post.hashtags.split(',') if tag.strip()]
                if tags:
                    hashtag_counts.update(tags)

        if not hashtag_counts:
            current_app.logger.info("No hashtags found in recent posts.")
            try:
                db.session.begin_nested()
                num_deleted = TrendingHashtag.query.delete()
                db.session.commit()
                current_app.logger.info(f"Cleared {num_deleted} existing trending hashtags as no new ones were found.")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error clearing trending hashtags: {e}")
            return

        top_hashtags_with_scores = hashtag_counts.most_common(top_n)

        with db.session.begin_nested(): # Using begin_nested for more control if outer transaction exists
            TrendingHashtag.query.delete() # Clear old hashtags

            for rank, (tag, score) in enumerate(top_hashtags_with_scores, 1):
                new_trending_hashtag = TrendingHashtag(
                    hashtag=tag,
                    score=float(score),
                    rank=rank,
                    calculated_at=datetime.utcnow()
                )
                db.session.add(new_trending_hashtag)

        db.session.commit() # Commit the transaction
        current_app.logger.info(f"Successfully updated {len(top_hashtags_with_scores)} trending hashtags.")

    except Exception as e:
        db.session.rollback() # Rollback on any exception during the process
        current_app.logger.error(f"Error in update_trending_hashtags job: {e}")


def get_personalized_feed_posts(user_id, limit=20):
    """
    Generates a personalized feed of posts for a given user.
    Combines posts from followed users, friends' activity, trending posts, and user's groups.
    Ensures posts are not duplicated and are ranked appropriately.
    """
    current_user = User.query.get(user_id)
    if not current_user:
        current_app.logger.warning(f"get_personalized_feed_posts: User with ID {user_id} not found.")
        return []

    # --- Scoring Constants ---
    SCORE_SOURCE_FOLLOWED = 1000
    SCORE_SOURCE_FRIEND_ACTIVITY = 500
    SCORE_SOURCE_GROUP = 300
    SCORE_SOURCE_TRENDING = 100
    # Recency decay factor (e.g., score halves every N days)
    RECENCY_HALFLIFE_DAYS = 7
    RECENCY_MAX_SCORE = 100 # Max possible score from recency alone

    # --- Store for deduplicated posts: {post_id: {'post': Post, 'score': float, 'reason': str}} ---
    feed_candidates = {}

    # --- Pre-fetch user's interactions to exclude posts ---
    user_authored_post_ids = {post.id for post in Post.query.filter_by(user_id=user_id).with_entities(Post.id).all()}
    user_liked_post_ids = {like.post_id for like in Like.query.filter_by(user_id=user_id).with_entities(Like.post_id).all()}
    user_commented_post_ids = {comment.post_id for comment in Comment.query.filter_by(user_id=user_id).with_entities(Comment.post_id).all()}
    # Assuming User.bookmarks is a relationship yielding Bookmark objects
    user_bookmarked_post_ids = {bookmark.post_id for bookmark in current_user.bookmarks}

    excluded_post_ids = user_authored_post_ids.union(user_liked_post_ids).union(user_commented_post_ids).union(user_bookmarked_post_ids)

    def calculate_recency_score(post_timestamp):
        days_old = (datetime.utcnow() - post_timestamp).days
        if days_old < 0: days_old = 0
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

        if post.id not in feed_candidates or final_score > feed_candidates[post.id]['score']:
            feed_candidates[post.id] = {'post': post, 'score': final_score, 'reason': reason}

    # --- 1. Posts from users the current user follows (Friends in this context) ---
    # Assuming get_friends() returns a list of User objects.
    # This part might need adjustment based on how "following" is truly modeled.
    # For now, using the concept of "friends" as "followed".
    friends = current_user.get_friends() # Assuming this method exists and returns User objects
    friend_ids = {friend.id for friend in friends}
    if friend_ids:
        # Fetch more posts initially, they will be ranked and limited later
        posts_from_followed = Post.query.filter(
            Post.user_id.in_(friend_ids),
            Post.id.notin_(excluded_post_ids) # Pre-filter
        ).order_by(Post.timestamp.desc()).limit(limit * 3).all()
        for post in posts_from_followed:
            author_username = post.author.username if post.author else "Unknown"
            add_candidate(post, SCORE_SOURCE_FOLLOWED, "From user you follow", author_username)

    # --- 2. Posts liked or commented on by friends (adapting suggest_posts_to_read) ---
    # suggest_posts_to_read returns (Post, reason_string)
    # It already handles some exclusions (user's own posts, posts user interacted with)
    # We pass a larger limit as it will be combined and re-ranked.
    # The 'reason' from suggest_posts_to_read is more specific about which friend interacted.
    friend_activity_posts = suggest_posts_to_read(user_id, limit=limit * 3)
    for post, reason in friend_activity_posts:
        if post.id in excluded_post_ids: # Double check exclusion
            continue
        # The reason from suggest_posts_to_read is good, use it directly.
        # The base score is SCORE_SOURCE_FRIEND_ACTIVITY, recency added in add_candidate.
        # We need to ensure `add_candidate` can take a pre-formed reason.

        # Simplified add_candidate for this source if reason is already good:
        recency_score = calculate_recency_score(post.timestamp)
        final_score = SCORE_SOURCE_FRIEND_ACTIVITY + recency_score
        if post.id not in feed_candidates or final_score > feed_candidates[post.id]['score']:
            feed_candidates[post.id] = {'post': post, 'score': final_score, 'reason': reason}


    # --- 3. Trending posts (adapting suggest_trending_posts) ---
    # suggest_trending_posts returns Post objects and handles some exclusions.
    trending = suggest_trending_posts(user_id, limit=limit * 2, since_days=14) # Wider window for feed
    for post in trending:
        if post.id in excluded_post_ids: # Double check exclusion
            continue
        add_candidate(post, SCORE_SOURCE_TRENDING, "Trending post")

    # --- 4. Posts from groups the user is a member of ---
    # Assuming User.joined_groups relationship exists and Post has a group_id
    # This section depends on Post model having a 'group_id' field.
    # If Post.group_id doesn't exist, this source cannot be used.
    if hasattr(Post, 'group_id'):
        user_groups = current_user.joined_groups.all() # Returns list of Group objects
        group_ids = {group.id for group in user_groups}
        if group_ids:
            posts_from_groups = Post.query.filter(
                Post.group_id.in_(group_ids),
                Post.id.notin_(excluded_post_ids) # Pre-filter
            ).order_by(Post.timestamp.desc()).limit(limit * 3).all()
            for post in posts_from_groups:
                # Find group name for reason string - requires post to have group relationship or query Group
                group_name = "Unknown Group"
                if post.group_id: # Check if group_id is set
                    group = Group.query.get(post.group_id) # Potential N+1 if not careful, better to join if displaying many group posts
                    if group:
                        group_name = group.name
                add_candidate(post, SCORE_SOURCE_GROUP, "From your group", group_name)
    else:
        current_app.logger.info(f"get_personalized_feed_posts: Post model does not have 'group_id'. Skipping group posts source for user {user_id}.")


    # --- Combine, Sort, and Limit ---
    if not feed_candidates:
        return []

    # Convert dictionary to list of dictionaries
    final_candidate_list = list(feed_candidates.values())

    # Sort by score (descending), then by post timestamp (descending) for tie-breaking
    final_candidate_list.sort(key=lambda x: (x['score'], x['post'].timestamp), reverse=True)

    # Extract Post objects for the final list, respecting the limit
    # The subtask asks for a list of Post objects. If (Post, reason) is needed, change here.

    # For debugging or future use, one might want to return reasons too:
    result_with_reasons = [(item['post'], item['reason']) for item in final_candidate_list[:limit]]

    current_app.logger.info(f"get_personalized_feed_posts: Generated {len(result_with_reasons)} posts for user {user_id}. Candidates found: {len(feed_candidates)}")
    return result_with_reasons


def get_on_this_day_content(user_id):
    """
    Retrieves posts and events created by the user on the current month and day from previous years.
    """
    today = datetime.utcnow()
    current_month = today.month
    current_day = today.day
    current_year = today.year

    # Fetch posts from previous years on this day
    posts_on_this_day = Post.query.filter(
        Post.user_id == user_id,
        extract('month', Post.timestamp) == current_month,
        extract('day', Post.timestamp) == current_day,
        extract('year', Post.timestamp) != current_year
    ).all()

    # Fetch events from previous years on this day
    # Event.date is a string, e.g., "YYYY-MM-DD"
    all_user_events = Event.query.filter(
        Event.user_id == user_id
    ).all()

    events_on_this_day = []
    for event in all_user_events:
        try:
            event_date_obj = datetime.strptime(event.date, '%Y-%m-%d')
            if event_date_obj.month == current_month and \
               event_date_obj.day == current_day and \
               event_date_obj.year != current_year:
                events_on_this_day.append(event)
        except ValueError:
            # Handle cases where event.date might not be in the expected format
            current_app.logger.error(f"Could not parse date string for event ID {event.id}: {event.date}")
            continue

    return {
        "posts": posts_on_this_day,
        "events": events_on_this_day
    }
