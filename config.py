class TestingConfig:
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
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = "test_uploads"
    PROFILE_PICS_FOLDER = "test_profile_pics"
    SHARED_FILES_UPLOAD_FOLDER = "shared_files_test_folder"
