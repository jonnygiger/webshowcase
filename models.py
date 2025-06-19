from app import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # uploaded_images can be a relationship if Image is a model, or a JSON/string field
    # For now, let's assume it's not a direct DB relationship in this phase
    uploaded_images = db.Column(db.Text, nullable=True) # Path to images, comma-separated

    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    likes = db.relationship('Like', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='reviewer', lazy=True)
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    polls = db.relationship('Poll', backref='author', lazy=True)
    poll_votes = db.relationship('PollVote', backref='voter', lazy=True)
    events = db.relationship('Event', backref='organizer', lazy=True)
    event_rsvps = db.relationship('EventRSVP', backref='attendee', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_edited = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    comments = db.relationship('Comment', backref='post', lazy=True, cascade="all, delete-orphan")
    likes = db.relationship('Like', backref='post', lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship('Review', backref='post', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Post {self.title}>'

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

class PollOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)

    votes = db.relationship('PollVote', backref='option', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<PollOption {self.text} for Poll {self.poll_id}>'

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

class EventRSVP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(50), nullable=False) # e.g., "Attending", "Maybe", "Not Attending"
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'event_id', name='_user_event_uc'),)

    def __repr__(self):
        return f'<EventRSVP User {self.user_id} for Event {self.event_id} status {self.status}>'

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
