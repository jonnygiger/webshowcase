from app import db
from datetime import datetime

# Association table for User-Group many-to-many relationship
group_members = db.Table('group_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('group.id'), primary_key=True)
)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to User (creator)
    creator = db.relationship('User', back_populates='created_groups')

    # Relationship to User (members) via association table
    members = db.relationship('User', secondary=group_members,
                              lazy='dynamic', # Allows for further querying
                              back_populates='joined_groups')

    # Relationship to GroupMessage
    # messages = db.relationship('GroupMessage', backref='group', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Group '{self.name}'>"

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'creator_id': self.creator_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'creator_username': self.creator.username if self.creator else None
        }

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True) # Added email field
    password_hash = db.Column(db.String(128), nullable=False)
    profile_picture = db.Column(db.String(255), nullable=True)  # Path to profile picture
    # uploaded_images can be a relationship if Image is a model, or a JSON/string field
    # For now, let's assume it's not a direct DB relationship in this phase
    uploaded_images = db.Column(db.Text, nullable=True) # Path to images, comma-separated
    bio = db.Column(db.Text, nullable=True) # User's biography

    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    likes = db.relationship('Like', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='reviewer', lazy=True)
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    bookmarks = db.relationship('Bookmark', backref='user', lazy=True, cascade="all, delete-orphan")
    polls = db.relationship('Poll', backref='author', lazy=True)
    poll_votes = db.relationship('PollVote', backref='voter', lazy=True)
    events = db.relationship('Event', backref='organizer', lazy=True)
    event_rsvps = db.relationship('EventRSVP', backref='attendee', lazy=True)
    reactions = db.relationship('Reaction', backref='user', lazy=True, cascade="all, delete-orphan")
    activities = db.relationship('UserActivity', backref='user', lazy=True) # Added UserActivity relationship

    # Friendship relationships
    sent_friend_requests = db.relationship(
        'Friendship',
        foreign_keys='Friendship.user_id',
        backref='requester', # This will add a 'requester' attribute to Friendship instances
        lazy='dynamic',
        cascade='all, delete-orphan' # If a User is deleted, their sent requests are deleted
    )
    received_friend_requests = db.relationship(
        'Friendship',
        foreign_keys='Friendship.friend_id',
        backref='requested', # This will add a 'requested' attribute to Friendship instances
        lazy='dynamic',
        cascade='all, delete-orphan' # If a User is deleted, their received requests are deleted
    )

    # Group relationships
    created_groups = db.relationship('Group', back_populates='creator', lazy=True, foreign_keys='Group.creator_id')
    joined_groups = db.relationship('Group', secondary=group_members,
                                    lazy='dynamic', # Allows for further querying
                                    back_populates='members')

    # Role field
    role = db.Column(db.String(80), nullable=False, default='user') # Added role field

    # FlaggedContent relationships
    flags_submitted = db.relationship('FlaggedContent', foreign_keys='FlaggedContent.flagged_by_user_id', back_populates='flagged_by_user', lazy='dynamic')
    flags_moderated = db.relationship('FlaggedContent', foreign_keys='FlaggedContent.moderator_id', back_populates='moderator', lazy='dynamic')

    # Relationship to GroupMessage
    # group_messages = db.relationship('GroupMessage', backref='user', lazy='dynamic', cascade="all, delete-orphan")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email, # Added email to dict
            'profile_picture': self.profile_picture,
            'uploaded_images': self.uploaded_images,
            'bio': self.bio
            # Add other fields if they are simple and non-sensitive
        }

    def get_stats(self):
        likes_received_count = 0
        for post in self.posts:
            likes_received_count += len(post.likes)

        return {
            'posts_count': len(self.posts),
            'comments_count': len(self.comments),
            'likes_received_count': likes_received_count,
            'friends_count': len(self.get_friends()),
            'join_date': self.created_at.isoformat() if self.created_at else None,
        }

    def get_friends(self):
        friends = []
        # Friendships this user initiated and were accepted
        # Accessing User model via fs.requested.id (or fs.requested directly)
        accepted_sent_requests = Friendship.query.filter_by(user_id=self.id, status='accepted').all()
        for fs in accepted_sent_requests:
            friends.append(fs.requested) # fs.requested should be the User instance

        # Friendships this user received and accepted
        # Accessing User model via fs.requester.id (or fs.requester directly)
        accepted_received_requests = Friendship.query.filter_by(friend_id=self.id, status='accepted').all()
        for fs in accepted_received_requests:
            friends.append(fs.requester) # fs.requester should be the User instance

        # Deduplicate in case of any unforeseen issues, though logic should prevent it
        return list(set(friends))

class UserActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)  # e.g., "new_post", "new_comment", "new_event"
    related_id = db.Column(db.Integer, nullable=True)  # e.g., post_id, comment_id, event_id
    content_preview = db.Column(db.Text, nullable=True)  # e.g., a snippet of the post or comment
    link = db.Column(db.String(255), nullable=True)  # e.g., URL to the post or event
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<UserActivity {self.id} - User {self.user_id}, Type: {self.activity_type}>'

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_edited = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    hashtags = db.Column(db.Text, nullable=True) # Stores comma-separated hashtags
    is_featured = db.Column(db.Boolean, default=False)
    featured_at = db.Column(db.DateTime, nullable=True)

    comments = db.relationship('Comment', backref='post', lazy=True, cascade="all, delete-orphan")
    likes = db.relationship('Like', backref='post', lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship('Review', backref='post', lazy=True, cascade="all, delete-orphan")
    reactions = db.relationship('Reaction', backref='post', lazy=True, cascade="all, delete-orphan")
    bookmarked_by = db.relationship('Bookmark', backref='post', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Post {self.title}>'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'last_edited': self.last_edited.isoformat() if self.last_edited else None,
            'user_id': self.user_id,
            'author_username': self.author.username if self.author else None,
            'hashtags': self.hashtags,
            'is_featured': self.is_featured,
            'featured_at': self.featured_at.isoformat() if self.featured_at else None
            # Consider adding comment count or like count if simple to compute
        }

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    def __repr__(self):
        return f'<Comment {self.id} by User {self.user_id} on Post {self.post_id}>'

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='_user_post_uc'),)

    def __repr__(self):
        return f'<Like User {self.user_id} Post {self.post_id}>'

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=False) # Assuming 1-5
    review_text = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    def __repr__(self):
        return f'<Review {self.id} by User {self.user_id} for Post {self.post_id}>'

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<Message {self.id} from {self.sender_id} to {self.receiver_id}>'

class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Author of the poll

    options = db.relationship('PollOption', backref='poll', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Poll {self.question}>'

    def to_dict(self):
        return {
            'id': self.id,
            'question': self.question,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'author_username': self.author.username if self.author else None,
            'options': [option.to_dict() for option in self.options]
        }

class PollOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)

    votes = db.relationship('PollVote', backref='option', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<PollOption {self.text} for Poll {self.poll_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'text': self.text,
            'vote_count': len(self.votes)
        }

class PollVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    poll_option_id = db.Column(db.Integer, db.ForeignKey('poll_option.id'), nullable=False)

    # To ensure a user can vote only once per poll, we need a constraint.
    # This can be achieved by a unique constraint on (user_id, poll_id derived through poll_option_id).
    # A direct unique constraint on (user_id, poll_id) is cleaner if poll_id is directly on PollVote.
    # Let's add poll_id to PollVote for easier constraint definition.
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'poll_id', name='_user_poll_uc'),)

    def __repr__(self):
        return f'<PollVote by User {self.user_id} for Option {self.poll_option_id} in Poll {self.poll_id}>'

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    date = db.Column(db.String(50), nullable=False) # Storing as string, consider DateTime if complex queries needed
    time = db.Column(db.String(50), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Organizer

    rsvps = db.relationship('EventRSVP', backref='event', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Event {self.title}>'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'date': self.date,
            'time': self.time,
            'location': self.location,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user_id': self.user_id,
            'organizer_username': self.organizer.username if self.organizer else None
        }

class EventRSVP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(50), nullable=False) # e.g., "Attending", "Maybe", "Not Attending"
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'event_id', name='_user_event_uc'),)

    def __repr__(self):
        return f'<EventRSVP User {self.user_id} for Event {self.event_id} status {self.status}>'

class Reaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    emoji = db.Column(db.String(10), nullable=False)  # Emoji character
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    # Relationships are defined in User and Post models via backref

    def __repr__(self):
        return f'<Reaction {self.emoji} by User {self.user_id} on Post {self.post_id}>'

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    type = db.Column(db.String(50), nullable=False) # e.g., 'new_post', 'new_event'
    related_id = db.Column(db.Integer, nullable=True) # e.g., post_id, event_id
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    # If notifications can be user-specific (which they often are)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Nullable if system-wide, or target all users

    def __repr__(self):
        return f'<Notification {self.id} type {self.type}>'

class TodoItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task = db.Column(db.String(255), nullable=False)
    is_done = db.Column(db.Boolean, default=False, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    due_date = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.String(50), nullable=True)

    user = db.relationship('User', backref=db.backref('todo_items', lazy=True, cascade="all, delete-orphan"))

    def __repr__(self):
        return f'<TodoItem {self.id}: {self.task[:30]}>'

# Note: The `uploaded_images` field in User and image handling in general might need a dedicated Image model
# if images have metadata, need to be queried independently, etc. For now, it's a comma-separated string.
# The `generate_password_hash` and `check_password_hash` would be methods on the User model or helpers used during user registration/login.
# `session` related logic remains in `app.py` routes.
# `app.config` settings remain in `app.py`.
# The scheduler and SocketIO setup remain in `app.py`.
# Global counters like `app.blog_post_id_counter` will be replaced by auto-incrementing primary keys.
# The `generate_activity_summary` function will need to be updated to query the database.
# Login_required decorator remains the same.
# Route logic will change significantly to use DB queries.

class Bookmark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='_user_post_bookmark_uc'),)

    def __repr__(self):
        return f'<Bookmark User {self.user_id} Post {self.post_id}>'


class SharedPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    shared_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shared_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    sharing_user_comment = db.Column(db.Text, nullable=True)

    # Relationship to the original Post
    original_post = db.relationship('Post', backref=db.backref('shares', lazy='dynamic'))
    # Relationship to the User who shared the post
    sharing_user = db.relationship('User', backref=db.backref('shared_posts', lazy='dynamic'))

    def __repr__(self):
        return f'<SharedPost id={self.id} original_post_id={self.original_post_id} shared_by_user_id={self.shared_by_user_id}>'


class Friendship(db.Model):
    __tablename__ = 'friendship' # Explicitly name the table
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending') # e.g., pending, accepted, rejected
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # To prevent a user from being their own friend or having duplicate requests
    __table_args__ = (
        db.UniqueConstraint('user_id', 'friend_id', name='uq_user_friend'),
        db.CheckConstraint('user_id != friend_id', name='ck_user_not_friend_self')
    )

    def __repr__(self):
        return f'<Friendship {self.user_id} to {self.friend_id} - {self.status}>'


class FlaggedContent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(50), nullable=False)  # e.g., 'post', 'comment'
    content_id = db.Column(db.Integer, nullable=False)  # ID of the flagged post or comment
    flagged_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='pending')  # e.g., 'pending', 'approved', 'rejected'
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    moderator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # User who resolved it
    moderator_comment = db.Column(db.Text, nullable=True) # Why it was approved/rejected
    resolved_at = db.Column(db.DateTime, nullable=True)

    # Relationships to User
    flagged_by_user = db.relationship('User', foreign_keys=[flagged_by_user_id], back_populates='flags_submitted')
    moderator = db.relationship('User', foreign_keys=[moderator_id], back_populates='flags_moderated')

    def __repr__(self):
        return f'<FlaggedContent {self.id} ({self.content_type} {self.content_id}) by User {self.flagged_by_user_id} - Status: {self.status}>'


class FriendPostNotification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # User receiving the notification
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)  # The post that was created
    poster_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # User who created the post
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('friend_post_notifications', lazy=True))
    post = db.relationship('Post', foreign_keys=[post_id], backref=db.backref('related_friend_notifications', lazy=True))
    poster = db.relationship('User', foreign_keys=[poster_id], backref=db.backref('triggered_friend_post_notifications', lazy=True))

    def __repr__(self):
        return f'<FriendPostNotification id={self.id} user_id={self.user_id} post_id={self.post_id} poster_id={self.poster_id} is_read={self.is_read}>'


class TrendingHashtag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hashtag = db.Column(db.String, nullable=False, unique=True)
    score = db.Column(db.Float, nullable=False, default=0.0)
    rank = db.Column(db.Integer, nullable=True)
    calculated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<TrendingHashtag {self.hashtag} (Rank: {self.rank}, Score: {self.score})>'

    def to_dict(self):
        return {
            'id': self.id,
            'hashtag': self.hashtag,
            'score': self.score,
            'rank': self.rank,
            'calculated_at': self.calculated_at.isoformat() if self.calculated_at else None,
        }
