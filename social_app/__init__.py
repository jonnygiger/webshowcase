import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_restful import Api as FlaskRestfulApi
from flask_jwt_extended import JWTManager
from flask_login import LoginManager
from apscheduler.schedulers.background import BackgroundScheduler

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO(async_mode="threading")
jwt = JWTManager()
login_manager = LoginManager()
scheduler = BackgroundScheduler()

# Import models here to avoid circular imports in other modules that need `db`
# These are imported from social_app.models.db_models now
# from .models.db_models import User, Post, Comment, Like, Review, Message, Poll, PollOption, PollVote, Event, EventRSVP, Notification, TodoItem, Group, Reaction, Bookmark, Friendship, SharedPost, UserActivity, FlaggedContent, FriendPostNotification, TrendingHashtag, SharedFile, UserStatus, UserAchievement, Achievement, Series, SeriesPost, UserBlock, ChatRoom, ChatMessage


def create_app(config_class=None):
    """Creates and configures the Flask application."""
    # Correctly set template_folder and static_folder to point to the project root
    app = Flask(__name__, template_folder='../templates', static_folder='../static')

    # Configuration
    # Default configuration (can be overridden by config_class or instance config)
    app.config.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///site.db")
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    app.config.setdefault("SECRET_KEY", "default-secret-key") # Replace with a strong key
    app.config.setdefault("JWT_SECRET_KEY", "default-jwt-secret-key") # Replace with a strong key
    app.config.setdefault("UPLOAD_FOLDER", os.path.join(app.root_path, "uploads"))
    app.config.setdefault("PROFILE_PICS_FOLDER", os.path.join(app.root_path, "static", "profile_pics"))
    app.config.setdefault("ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "gif"})
    app.config.setdefault("SHARED_FILES_UPLOAD_FOLDER", os.path.join(app.root_path, "shared_files_uploads"))
    app.config.setdefault("SHARED_FILES_ALLOWED_EXTENSIONS", {"txt", "pdf", "png", "jpg", "jpeg", "gif", "zip", "doc", "docx", "xls", "xlsx", "ppt", "pptx"})
    app.config.setdefault("SHARED_FILES_MAX_SIZE", 16 * 1024 * 1024) # 16MB

    if isinstance(config_class, str) and config_class == 'testing':
        try:
            from config import TestingConfig
            config_class = TestingConfig
        except ImportError:
            # This case should ideally not happen in our controlled environment
            # but good to be aware of.
            # We can log an error or re-raise if needed.
            # For now, if it fails, it will proceed and likely fail at from_object,
            # which is the original behavior for a missing module.
            pass

    if config_class:
        app.config.from_object(config_class)
    else:
        # Load instance config if it exists, e.g., config.py
        app.config.from_pyfile('config.py', silent=True) # You might want to create a config.py

    # Initialize Flask extensions with the app
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app) # Removed manage_session=False, default is True
    fr_api = FlaskRestfulApi()
    fr_api.init_app(app)
    jwt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "core.login" # Adjusted to new blueprint structure

    # SSE and Notification Queues (app-specific, not standard extensions)
    app.sse_listeners = {}
    app.user_notification_queues = {}
    # new_post_sse_queues needs to be initialized here if it's used by the app globally
    # For now, assuming it will be handled by the relevant service/module that uses it.
    # from .services.notifications_service import new_post_sse_queues # Example of where it might come from

    # Import and register blueprints, API resources, etc.
    # This is where you'd import parts of your app like views, models (if not already done), api resources
    from .core import views as core_views
    from .core import events as core_events
    from .api import routes as api_routes_module # Renamed to avoid conflict with 'api' object
    from .api.routes import ( # Importing all resources for registration
        UserListResource, UserResource, PostListResource, PostResource, EventListResource, EventResource,
        RecommendationResource, PersonalizedFeedResource, TrendingHashtagsResource, OnThisDayResource,
        UserStatsResource, SeriesListResource, SeriesResource, CommentListResource, PollListResource,
        PollResource, PollVoteResource, PostLockResource, SharedFileResource, UserFeedResource,
        ChatRoomListResource, ChatRoomMessagesResource, ApiLoginResource # Added ApiLoginResource
    )

    # Register Blueprints
    app.register_blueprint(core_views.core_bp)
    # If you have other blueprints (e.g., an api_bp from api_routes_module), register them too.
    # app.register_blueprint(api_routes_module.api_bp, url_prefix='/api') # Example if api_bp exists

    # API resources registration
    # These were originally added to `api = Api(app)` in app.py. Now `api` is initialized globally and then `init_app(app)`.
    # So, we use the global `api` object.
    fr_api.add_resource(UserListResource, "/api/users")
    fr_api.add_resource(UserResource, "/api/users/<int:user_id>")
    fr_api.add_resource(PostListResource, "/api/posts")
    fr_api.add_resource(PostResource, "/api/posts/<int:post_id>")
    fr_api.add_resource(EventListResource, "/api/events")
    fr_api.add_resource(EventResource, "/api/events/<int:event_id>")
    fr_api.add_resource(RecommendationResource, "/api/recommendations")
    fr_api.add_resource(PersonalizedFeedResource, "/api/personalized-feed")
    fr_api.add_resource(TrendingHashtagsResource, "/api/trending_hashtags")
    fr_api.add_resource(OnThisDayResource, "/api/onthisday")
    fr_api.add_resource(UserStatsResource, "/api/users/<int:user_id>/stats")
    fr_api.add_resource(SeriesListResource, "/api/series")
    fr_api.add_resource(SeriesResource, "/api/series/<int:series_id>")
    fr_api.add_resource(CommentListResource, "/api/posts/<int:post_id>/comments")
    fr_api.add_resource(PollListResource, "/api/polls")
    fr_api.add_resource(PollResource, "/api/polls/<int:poll_id>")
    fr_api.add_resource(PollVoteResource, "/api/polls/<int:poll_id>/vote")
    fr_api.add_resource(PostLockResource, "/api/posts/<int:post_id>/lock")
    fr_api.add_resource(SharedFileResource, "/api/files/<int:file_id>") # Corrected from app.py
    fr_api.add_resource(UserFeedResource, "/api/users/<int:user_id>/feed")
    fr_api.add_resource(ChatRoomListResource, "/api/chat/rooms")
    fr_api.add_resource(ChatRoomMessagesResource, "/api/chat/rooms/<int:room_id>/messages")
    fr_api.add_resource(ApiLoginResource, "/api/login") # Registered ApiLoginResource

    # Login manager user loader
    # Models need to be imported before this is defined
    from .models.db_models import User # Ensure User is imported
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Create database tables if they don't exist (optional, migrations are preferred)
    # with app.app_context():
    #     db.create_all() # Consider if this is needed or if migrations handle everything

    # Ensure upload folders exist
    for folder_key in ['UPLOAD_FOLDER', 'PROFILE_PICS_FOLDER', 'SHARED_FILES_UPLOAD_FOLDER']:
        folder_path = app.config.get(folder_key)
        if folder_path and not os.path.exists(folder_path):
            os.makedirs(folder_path)
            app.logger.info(f"Created folder: {folder_path}")

    return app
