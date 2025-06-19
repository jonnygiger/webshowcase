from app import db
from models import User, Post, Group, Friendship, Like, Event, EventRSVP, Poll, PollVote
from sqlalchemy import func, or_
# from collections import defaultdict # Not needed

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
    """Suggest posts liked by the current user's friends."""
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

    # Get posts liked by friends
    posts_liked_by_friends = db.session.query(Post, func.count(Like.id).label('like_count')).join(Like, Like.post_id == Post.id).filter(
        Like.user_id.in_(friend_ids),
        Post.user_id != user_id  # Exclude posts created by the current user
    ).group_by(Post.id).order_by(func.count(Like.id).desc()).subquery()

    # Filter out posts already liked by the current user
    user_liked_post_ids = db.session.query(Like.post_id).filter(Like.user_id == user_id).all()
    user_liked_post_ids = {post_id for (post_id,) in user_liked_post_ids}

    suggested_posts_query = db.session.query(
        Post
    ).select_entity_from(posts_liked_by_friends).filter(
        Post.id.notin_(user_liked_post_ids)
    )

    suggested_posts = suggested_posts_query.limit(limit).all()
    return suggested_posts

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