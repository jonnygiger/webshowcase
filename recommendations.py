from app import db
from models import User, Post, Group, Friendship, Like
from sqlalchemy import func, distinct, or_
from collections import defaultdict

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
