import os
import unittest
import json  # For checking JSON responses
import io  # For BytesIO
from unittest.mock import patch, call, ANY
from app import (
    app,
    db,
    socketio,
)  # Import socketio from app ## COMMENTED OUT FOR TIMEOUT DEBUGGING
from models import (
    User,
    Message,
    Post,
    Friendship,
    FriendPostNotification,
    Group,
    Event,
    Poll,
    PollOption,
    TrendingHashtag,
    SharedFile,
    UserStatus,
    Achievement,
    UserAchievement,
    Comment,
    Series,
    SeriesPost,
    Notification,
    Like,
    EventRSVP,
    PollVote,
    PostLock,
)  # COMMENTED OUT - Added EventRSVP, PollVote, PostLock
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash


class AppTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Configuration that applies to the entire test class
        app.config["TESTING"] = True  ## app IS NOT AVAILABLE
        app.config["WTF_CSRF_ENABLED"] = False  ## app IS NOT AVAILABLE
        app.config["SQLALCHEMY_DATABASE_URI"] = (
            "sqlite:///:memory:"  ## app IS NOT AVAILABLE
        )
        app.config["SECRET_KEY"] = "test-secret-key"  ## app IS NOT AVAILABLE
        app.config["SOCKETIO_MESSAGE_QUEUE"] = None  ## app IS NOT AVAILABLE
        with app.app_context():
            db.create_all()  # Create tables once per class
        # pass # Simplified for timeout debugging

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            db.drop_all()  # Drop tables once after all tests in the class
        # pass # Simplified for timeout debugging

    def setUp(self):
        """Set up for each test."""
        self.client = app.test_client()  ## app IS NOT AVAILABLE
        with app.app_context():
            self._clean_tables_for_setup()
            self._setup_base_users()  # This would require live User model and db session
        # Mock base users if db is not live
        # self.user1 = unittest.mock.MagicMock(id=1, username='testuser1', email='test1@example.com', profile_picture=None)
        # self.user1_id = 1
        # self.user2 = unittest.mock.MagicMock(id=2, username='testuser2', email='test2@example.com', profile_picture=None)
        # self.user2_id = 2
        # self.user3 = unittest.mock.MagicMock(id=3, username='testuser3', email='test3@example.com', profile_picture=None)
        # self.user3_id = 3
        # pass

    def _clean_tables_for_setup(self):
        """Clears data from tables before each test's user setup."""
        db.session.remove()
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()
        # pass

    def tearDown(self):
        """Executed after each test."""
        db.session.remove()
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()

        shared_files_folder = app.config.get(
            "SHARED_FILES_UPLOAD_FOLDER"
        )  # temp replacement for app.config.get('SHARED_FILES_UPLOAD_FOLDER')
        if shared_files_folder and os.path.exists(shared_files_folder):
            for filename in os.listdir(shared_files_folder):
                file_path = os.path.join(shared_files_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}")

    def _setup_base_users(self):
        # This method is problematic without live User model and db session.
        # Called in setUp, which is now simplified. Kept for reference.
        self.user1 = User(
            username="testuser1",
            email="test1@example.com",
            password_hash=generate_password_hash("password"),
        )
        self.user2 = User(
            username="testuser2",
            email="test2@example.com",
            password_hash=generate_password_hash("password"),
        )
        self.user3 = User(
            username="testuser3",
            email="test3@example.com",
            password_hash=generate_password_hash("password"),
        )
        db.session.add_all([self.user1, self.user2, self.user3])
        db.session.commit()
        self.user1_id = self.user1.id
        self.user2_id = self.user2.id
        self.user3_id = self.user3.id
        # pass

    def _create_friendship(self, user1_id, user2_id, status="accepted"):
        # Requires live Friendship model and db session
        friendship = Friendship(user_id=user1_id, friend_id=user2_id, status=status)
        db.session.add(friendship)
        db.session.commit()
        return friendship
        # return unittest.mock.MagicMock(user_id=user1_id, friend_id=user2_id, status=status)

    def _create_db_post(
        self, user_id, title="Test Post", content="Test Content", timestamp=None
    ):
        # Requires live Post model and db session
        post = Post(
            user_id=user_id,
            title=title,
            content=content,
            timestamp=timestamp or datetime.utcnow(),
        )
        db.session.add(post)
        db.session.commit()
        return post
        # mock_post = unittest.mock.MagicMock(id=unittest.mock.sentinel.post_id, user_id=user_id, title=title, content=content, timestamp=timestamp or datetime.utcnow())
        # mock_post.author = unittest.mock.MagicMock(username=f"user{user_id}") # Simulate author relationship
        # return mock_post

    def _make_post_via_route(
        self, username, password, title="Test Post", content="Test Content", hashtags=""
    ):
        self.login(username, password)
        response = self.client.post(
            "/blog/create",
            data=dict(title=title, content=content, hashtags=hashtags),
            follow_redirects=True,
        )
        self.logout()
        return response

    def login(self, username, password):
        return self.client.post(
            "/login",
            data=dict(username=username, password=password),
            follow_redirects=True,
        )

    def logout(self):
        return self.client.get("/logout", follow_redirects=True)

    def _create_db_message(
        self, sender_id, receiver_id, content, timestamp=None, is_read=False
    ):
        # Requires live Message model and db session
        msg = Message(
            sender_id=sender_id,
            receiver_id=receiver_id,
            content=content,
            timestamp=timestamp or datetime.utcnow(),
            is_read=is_read,
        )
        db.session.add(msg)
        db.session.commit()
        return msg
        # return unittest.mock.MagicMock(sender_id=sender_id, receiver_id=receiver_id, content=content)

    def _get_jwt_token(self, username, password):
        response = self.client.post(
            "/login_api", json={"username": username, "password": password}
        )
        self.assertEqual(
            response.status_code,
            200,
            f"Login failed for token generation: {response.data.decode()}",
        )
        data = json.loads(response.data)
        self.assertIn("access_token", data, "Access token not found in login response.")
        return data["access_token"]

    def create_dummy_file(
        self, filename="test.txt", content=b"hello world", content_type="text/plain"
    ):
        return (io.BytesIO(content), filename, content_type)

    def _create_db_group(
        self, creator_id, name="Test Group", description="A group for testing"
    ):
        # Requires live Group model and db session
        group = Group(name=name, description=description, creator_id=creator_id)
        db.session.add(group)
        db.session.commit()
        return group
        # return unittest.mock.MagicMock(id=unittest.mock.sentinel.group_id, name=name, creator_id=creator_id)

    def _create_db_event(
        self,
        user_id,
        title="Test Event",
        description="An event for testing",
        date_str="2024-12-31",
        time="18:00",
        location="Test Location",
        created_at=None,
    ):
        # Requires live Event model and db session
        event_datetime = datetime.strptime(f"{date_str} {time}", "%Y-%m-%d %H:%M")
        event = Event(
            user_id=user_id,
            title=title,
            description=description,
            date=event_datetime,
            location=location,
            created_at=created_at or datetime.utcnow(),
        )
        db.session.add(event)
        db.session.commit()
        return event
        # return unittest.mock.MagicMock(id=unittest.mock.sentinel.event_id, title=title, user_id=user_id, date=date_str, created_at=created_at or datetime.utcnow())

    def _create_db_poll(
        self, user_id, question="Test Poll?", options_texts=None, created_at=None
    ):
        if options_texts is None:
            options_texts = ["Option 1", "Option 2"]
        # Requires live Poll, PollOption models and db session
        poll = Poll(
            user_id=user_id,
            question=question,
            created_at=created_at or datetime.utcnow(),
        )
        db.session.add(poll)
        db.session.commit()  # Commit to get poll.id
        for text in options_texts:
            option = PollOption(text=text, poll_id=poll.id)
            db.session.add(option)
        db.session.commit()
        return poll
        # mock_poll = unittest.mock.MagicMock(id=unittest.mock.sentinel.poll_id, question=question, user_id=user_id, options=[])
        # for i, text in enumerate(options_texts):
        # mock_option = unittest.mock.MagicMock(id=i+1, text=text, poll_id=mock_poll.id, vote_count=0)
        # mock_poll.options.append(mock_option)
        # return mock_poll

    def _create_db_like(self, user_id, post_id, timestamp=None):
        from models import Like  # Local import to avoid circular if not using live DB

        like = Like(
            user_id=user_id, post_id=post_id, timestamp=timestamp or datetime.utcnow()
        )
        db.session.add(like)
        db.session.commit()
        return like
        # return unittest.mock.MagicMock(user_id=user_id, post_id=post_id)

    def _create_db_comment(
        self, user_id, post_id, content="Test comment", timestamp=None
    ):
        from models import Comment

        comment = Comment(
            user_id=user_id,
            post_id=post_id,
            content=content,
            timestamp=timestamp or datetime.utcnow(),
        )
        db.session.add(comment)
        db.session.commit()
        return comment
        # return unittest.mock.MagicMock(id=unittest.mock.sentinel.comment_id, user_id=user_id, post_id=post_id, content=content)

    def _create_db_event_rsvp(
        self, user_id, event_id, status="Attending", timestamp=None
    ):
        from models import EventRSVP

        rsvp = EventRSVP(
            user_id=user_id,
            event_id=event_id,
            status=status,
            timestamp=timestamp or datetime.utcnow(),
        )
        db.session.add(rsvp)
        db.session.commit()
        return rsvp
        # return unittest.mock.MagicMock(user_id=user_id, event_id=event_id, status=status)

    def _create_db_poll_vote(self, user_id, poll_id, poll_option_id, created_at=None):
        from models import PollVote

        vote = PollVote(
            user_id=user_id,
            poll_id=poll_id,
            poll_option_id=poll_option_id,
            created_at=created_at or datetime.utcnow(),
        )
        db.session.add(vote)
        db.session.commit()
        return vote
        # return unittest.mock.MagicMock(user_id=user_id, poll_id=poll_id, poll_option_id=poll_option_id)

    def _create_series(
        self,
        user_id,
        title="Test Series",
        description="A series for testing.",
        created_at=None,
        updated_at=None,
    ):
        # Requires Series model and db session
        series = Series(
            user_id=user_id,
            title=title,
            description=description,
            created_at=created_at or datetime.utcnow(),
            updated_at=updated_at or datetime.utcnow(),
        )
        db.session.add(series)
        db.session.commit()
        return series
        # return unittest.mock.MagicMock(id=unittest.mock.sentinel.series_id, title=title, user_id=user_id)

    def assertInHTML(self, needle, haystack, achievement_name):
        try:
            ach_name_idx = haystack.find(achievement_name)
            self.assertTrue(
                ach_name_idx != -1,
                f"Achievement name '{achievement_name}' not found in HTML.",
            )
            search_range = haystack[ach_name_idx : ach_name_idx + 300]
            self.assertIn(
                needle,
                search_range,
                f"'{needle}' not found near '{achievement_name}' in HTML: {search_range[:200]}...",
            )
        except AttributeError:
            self.fail("Haystack for assertInHTML was not a string.")

    def _create_db_lock(self, post_id, user_id, minutes_offset=0):
        from models import PostLock

        expires_at = datetime.utcnow() + timedelta(minutes=minutes_offset)
        lock = PostLock(post_id=post_id, user_id=user_id, expires_at=expires_at)
        db.session.add(lock)
        db.session.commit()
        return lock
        # return unittest.mock.MagicMock(post_id=post_id, user_id=user_id)
