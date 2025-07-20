import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_restful import Api as FlaskRestfulApi
from flask_jwt_extended import JWTManager
from flask_login import LoginManager
from apscheduler.schedulers.background import BackgroundScheduler

from config import DefaultConfig, TestingConfig

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
login_manager = LoginManager()
scheduler = BackgroundScheduler()


def create_app(config_class=None):
    """Creates and configures the Flask application."""
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    app.config.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///site.db")
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    app.config.setdefault("SECRET_KEY", "default-secret-key")
    app.config.setdefault("JWT_SECRET_KEY", "default-jwt-secret-key")
    app.config.setdefault("UPLOAD_FOLDER", os.path.join(app.root_path, "uploads"))
    app.config.setdefault(
        "PROFILE_PICS_FOLDER", os.path.join(app.root_path, "static", "profile_pics")
    )
    app.config.setdefault("ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "gif"})
    app.config.setdefault(
        "SHARED_FILES_UPLOAD_FOLDER",
        os.path.join(app.root_path, "shared_files_uploads"),
    )
    app.config.setdefault(
        "SHARED_FILES_ALLOWED_EXTENSIONS",
        {
            "txt",
            "pdf",
            "png",
            "jpg",
            "jpeg",
            "gif",
            "zip",
            "doc",
            "docx",
            "xls",
            "xlsx",
            "ppt",
            "pptx",
        },
    )
    app.config.setdefault("SHARED_FILES_MAX_SIZE", 16 * 1024 * 1024)

    if isinstance(config_class, str):
        if config_class == "default":
            app.config.from_object(DefaultConfig)
        elif config_class == "testing":
            app.config.from_object(TestingConfig)
        # If it's another string, it might be an error or a future config name
        # For now, we'll let it pass through and potentially be caught by from_object if it's not a valid path/module
        # or rely on setdefault if it's not handled.
        # A more robust way would be to raise an error for unknown string keys.
        # However, the prompt implies config_class could be an actual class object.
    elif config_class is not None:  # It's an actual class object
        app.config.from_object(config_class)
    else:  # config_class is None, so load default
        app.config.from_object(DefaultConfig)

    db.init_app(app)
    migrate.init_app(app, db)
    fr_api = FlaskRestfulApi(app)
    jwt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "core.login"

    app.sse_listeners = {}
    app.user_notification_queues = {}
    app.chat_room_listeners = {}
    app.post_event_listeners = {}

    from .core import views as core_views

    # from .core import events as core_events # This line was removed in a previous commit, ensuring it stays removed or is handled if logic changes
    from .api import routes as api_routes_module
    from .api.routes import (
        UserListResource,
        UserResource,
        PostListResource,
        PostResource,
        EventListResource,
        EventResource,
        RecommendationResource,
        PersonalizedFeedResource,
        TrendingHashtagsResource,
        OnThisDayResource,
        UserStatsResource,
        SeriesListResource,
        SeriesResource,
        CommentListResource,
        PollListResource,
        PollResource,
        PollVoteResource,
        PostLockResource,
        SharedFileResource,
        UserFeedResource,
        ChatRoomListResource,
        ChatRoomMessagesResource,
        ApiLoginResource,
        PostLikeResource,
        EventRSVPResource,
        SharedFileListResource,
    )

    app.register_blueprint(core_views.core_bp)

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
    fr_api.add_resource(SharedFileResource, "/api/files/<int:file_id>")
    fr_api.add_resource(UserFeedResource, "/api/users/<int:user_id>/feed")
    fr_api.add_resource(ChatRoomListResource, "/api/chat/rooms")
    fr_api.add_resource(
        ChatRoomMessagesResource, "/api/chat/rooms/<int:room_id>/messages"
    )
    fr_api.add_resource(ApiLoginResource, "/api/login")
    fr_api.add_resource(PostLikeResource, "/api/posts/<int:post_id>/like")
    fr_api.add_resource(EventRSVPResource, "/api/events/<int:event_id>/rsvp")
    fr_api.add_resource(SharedFileListResource, "/api/files")

    from .models.db_models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    for folder_key in [
        "UPLOAD_FOLDER",
        "PROFILE_PICS_FOLDER",
        "SHARED_FILES_UPLOAD_FOLDER",
    ]:
        folder_path = app.config.get(folder_key)
        if folder_path and not os.path.exists(folder_path):
            os.makedirs(folder_path)
            app.logger.info(f"Created folder: {folder_path}")

    return app
