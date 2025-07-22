import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "you-should-change-this"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or "super-secret-jwt"
    UPLOAD_FOLDER = "uploads"
    PROFILE_PICS_FOLDER = "static/profile_pics"
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
    SHARED_FILES_UPLOAD_FOLDER = "shared_files_uploads"
    SHARED_FILES_ALLOWED_EXTENSIONS = {
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
    }
    SHARED_FILES_MAX_SIZE = 16 * 1024 * 1024


class DefaultConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///site.db"


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key"
    JWT_SECRET_KEY = "test-jwt-secret-key"
    WTF_CSRF_ENABLED = False
    SOCKETIO_MESSAGE_QUEUE = None
    SERVER_NAME = "localhost"
    APPLICATION_ROOT = "/"
    PREFERRED_URL_SCHEME = "http"
    SESSION_COOKIE_NAME = "session"
    SESSION_COOKIE_DOMAIN = "localhost"
    # SQLALCHEMY_TRACK_MODIFICATIONS is already False in Config
    UPLOAD_FOLDER = "test_uploads"
    PROFILE_PICS_FOLDER = "test_profile_pics"
    PROFILE_PICS_TEST_FOLDER = "test_profile_pics"
    SHARED_FILES_UPLOAD_FOLDER = "shared_files_test_folder"
    SHARED_FILES_TEST_FOLDER = "shared_files_test_folder"
