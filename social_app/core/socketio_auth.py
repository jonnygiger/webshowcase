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
        # Log function name, arguments, and keyword arguments
        current_app.logger.debug(f"SocketIO: Entering '{f.__name__}'. SID: {request.sid}. Args: {args}, Kwargs: {kwargs}")

        if not args or not isinstance(args[0], dict):
            error_msg = f"SocketIO: Auth decorator expected dict as first arg, got {type(args[0]) if args else 'None'}. Event: '{f.__name__}', SID: {request.sid}"
            current_app.logger.warning(error_msg)
            emit('auth_error', {'message': 'Invalid event data format for authentication.'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: Exiting '{f.__name__}' due to invalid event data format. SID: {request.sid}. Outcome: Authentication Error")
            return False

        data = args[0]
        token = data.get('token')

        # Log token before decoding
        current_app.logger.debug(f"SocketIO: Token received for event '{f.__name__}' from SID {request.sid}: {token}")

        if not token:
            error_msg = f"SocketIO: Missing token for event '{f.__name__}' from SID {request.sid}."
            current_app.logger.info(error_msg)
            emit('auth_error', {'message': 'Authentication token missing.'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: Exiting '{f.__name__}' due to missing token. SID: {request.sid}. Outcome: Authentication Error")
            return False

        try:
            # Log before decoding token
            current_app.logger.debug(f"SocketIO: Attempting to decode token for event '{f.__name__}'. SID: {request.sid}. Token: {token}")
            decoded_token = decode_token(token)
            # Log decoded token
            current_app.logger.debug(f"SocketIO: Token decoded successfully for event '{f.__name__}'. SID: {request.sid}. Decoded token: {decoded_token}")

            user_identity = decoded_token.get('sub') # Use .get for safer access
            if user_identity is None:
                error_msg = f"SocketIO: 'sub' claim missing in token for event '{f.__name__}' from SID {request.sid}. Decoded token: {decoded_token}"
                current_app.logger.warning(error_msg)
                emit('auth_error', {'message': "Token is missing the 'sub' (subject) claim."}, room=request.sid)
                current_app.logger.debug(f"SocketIO: Exiting '{f.__name__}' due to missing 'sub' claim. SID: {request.sid}. Outcome: Authentication Error")
                return False

            current_app.logger.debug(f"SocketIO: User identity (sub) from token for event '{f.__name__}': {user_identity}. SID: {request.sid}")

            try:
                user_id = int(user_identity)
            except ValueError:
                error_msg = f"SocketIO: Invalid user identity format (not an int) '{user_identity}' in token for event '{f.__name__}' from SID {request.sid}."
                current_app.logger.warning(error_msg)
                emit('auth_error', {'message': 'Invalid user identity format in token.'}, room=request.sid)
                current_app.logger.debug(f"SocketIO: Exiting '{f.__name__}' due to invalid user_id format. SID: {request.sid}. Outcome: Authentication Error")
                return False

            # Log user_id before database query
            current_app.logger.debug(f"SocketIO: Attempting to fetch user from DB for event '{f.__name__}'. SID: {request.sid}. User ID: {user_id}")
            user = db.session.get(User, user_id)

            # Log user object after database query
            if user:
                current_app.logger.debug(f"SocketIO: User fetched from DB for event '{f.__name__}'. SID: {request.sid}. User: ID={user.id}, Username={user.username}")
            else:
                current_app.logger.warning(f"SocketIO: User with ID {user_id} (from token sub) not found in DB for event '{f.__name__}'. SID: {request.sid}.")
                emit('auth_error', {'message': 'User associated with token not found.'}, room=request.sid)
                current_app.logger.debug(f"SocketIO: Exiting '{f.__name__}' because user not found in DB. SID: {request.sid}. Outcome: Authentication Error")
                return False

            g.socketio_user = user
            current_app.logger.debug(f"SocketIO: User {user.username} authenticated for event '{f.__name__}' via JWT. SID: {request.sid}")

            # Log before returning from successful authentication
            current_app.logger.debug(f"SocketIO: Exiting '{f.__name__}' after successful authentication. SID: {request.sid}. Outcome: Authenticated")
            return f(*args, **kwargs)

        except ExpiredSignatureError as e:
            error_msg = f"SocketIO: Expired token for event '{f.__name__}' from SID {request.sid}. Error: {type(e).__name__} - {e}"
            current_app.logger.info(error_msg)
            emit('auth_error', {'message': 'Token has expired.'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: Exiting '{f.__name__}' due to ExpiredSignatureError. SID: {request.sid}. Outcome: Authentication Error")
            return False
        except InvalidTokenError as e:
            error_msg = f"SocketIO: Invalid token for event '{f.__name__}' from SID {request.sid}. Type: {type(e).__name__}, Error: {e}"
            current_app.logger.warning(error_msg)
            emit('auth_error', {'message': f'Invalid token supplied: {str(e)}'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: Exiting '{f.__name__}' due to InvalidTokenError. SID: {request.sid}. Outcome: Authentication Error")
            return False
        except Exception as e:
            error_msg = f"SocketIO: Unexpected critical error during JWT processing for event '{f.__name__}' from SID {request.sid}. Error: {type(e).__name__} - {str(e)}"
            current_app.logger.error(error_msg, exc_info=True)
            emit('auth_error', {'message': 'An critical server error occurred during authentication.'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: Exiting '{f.__name__}' due to an unexpected exception. SID: {request.sid}. Outcome: Authentication Error")
            return False

    return decorated_function
