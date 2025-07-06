from functools import wraps
from flask import current_app, g, request
from flask_socketio import emit
from flask_jwt_extended import decode_token
from jwt import ExpiredSignatureError, InvalidTokenError

from social_app import db
from social_app.models.db_models import User

def jwt_required_socketio(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not args or not isinstance(args[0], dict):
            current_app.logger.warning(f"SocketIO: Auth decorator expected dict as first arg, got {type(args[0]) if args else 'None'}. SID: {request.sid}")
            emit('auth_error', {'message': 'Invalid event data format for authentication.'}, room=request.sid)
            return False

        data = args[0]
        token = data.get('token')

        if not token:
            current_app.logger.info(f"SocketIO: Missing token for event '{f.__name__}' from SID {request.sid}.")
            emit('auth_error', {'message': 'Authentication token missing.'}, room=request.sid)
            return False

        try:
            decoded_token = decode_token(token)
            user_identity = decoded_token['sub']

            try:
                user_id = int(user_identity)
            except ValueError:
                current_app.logger.warning(f"SocketIO: Invalid user identity format '{user_identity}' in token for SID {request.sid}.")
                emit('auth_error', {'message': 'Invalid user identity in token.'}, room=request.sid)
                return False

            user = db.session.get(User, user_id)

            if not user:
                current_app.logger.warning(f"SocketIO: User with ID {user_id} (from token sub) not found in DB. SID: {request.sid}.")
                emit('auth_error', {'message': 'User associated with token not found.'}, room=request.sid) # Changed message for clarity
                return False

            g.socketio_user = user
            current_app.logger.debug(f"SocketIO: User {user.username} authenticated for event '{f.__name__}' via JWT. SID: {request.sid}") # Added debug log

            return f(*args, **kwargs)

        except ExpiredSignatureError:
            current_app.logger.info(f"SocketIO: Expired token for event '{f.__name__}' from SID {request.sid}.")
            emit('auth_error', {'message': 'Token has expired.'}, room=request.sid)
            return False
        except InvalidTokenError as e:
            current_app.logger.warning(f"SocketIO: Invalid token for event '{f.__name__}' from SID {request.sid}. Type: {type(e).__name__}, Error: {e}") # Enhanced log
            emit('auth_error', {'message': f'Invalid token supplied: {str(e)}'}, room=request.sid) # Changed message
            return False
        except Exception as e:
            current_app.logger.error(f"SocketIO: Unexpected critical error during JWT processing for event '{f.__name__}' from SID {request.sid}. Error: {str(e)}", exc_info=True) # Enhanced log
            emit('auth_error', {'message': 'An critical server error occurred during authentication.'}, room=request.sid) # Changed message
            return False

    return decorated_function
