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
        func_name = f.__name__
        # Entry Logging
        current_app.logger.debug(f"SocketIO: jwt_required_socketio - Entering '{func_name}'. SID: {request.sid}. Args: {args}, Kwargs: {kwargs}")

        if not args or not isinstance(args[0], dict):
            error_msg = f"SocketIO: Auth decorator expected dict as first arg, got {type(args[0]) if args else 'None'}. Event: '{func_name}', SID: {request.sid}"
            current_app.logger.warning(error_msg)
            emit('auth_error', {'message': 'Invalid event data format for authentication.'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: jwt_required_socketio - Exiting '{func_name}' for SID {request.sid}. Outcome: Authentication Error (Invalid event data format). Returning False.")
            return False

        data = args[0]
        token = data.get('token')

        # Token Presence/Absence
        if not token:
            current_app.logger.info(f"SocketIO: jwt_required_socketio - Missing token for event '{func_name}' from SID {request.sid}. Emitting auth_error.")
            emit('auth_error', {'message': 'Authentication token missing.'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: jwt_required_socketio - Exiting '{func_name}' for SID {request.sid}. Outcome: Authentication Error (Token Missing). Returning False.")
            return False

        # Log partial token before decoding
        current_app.logger.debug(f"SocketIO: jwt_required_socketio - Attempting to decode token for event '{func_name}'. SID: {request.sid}. Token: {token[:20]}...")

        try:
            decoded_token = decode_token(token)
            # Log decoded token details
            current_app.logger.debug(f"SocketIO: jwt_required_socketio - Token decoded successfully for event '{func_name}'. SID: {request.sid}. Decoded claims (sub, exp, iat, jti): {{'sub': {decoded_token.get('sub')}, 'exp': {decoded_token.get('exp')}, 'iat': {decoded_token.get('iat')}, 'jti': {decoded_token.get('jti')}}}")

            user_identity = decoded_token.get('sub')
            if user_identity is None:
                current_app.logger.warning(f"SocketIO: jwt_required_socketio - 'sub' claim missing in token for event '{func_name}' from SID {request.sid}. Decoded token: {decoded_token}. Emitting auth_error.")
                emit('auth_error', {'message': "Token is missing the 'sub' (subject) claim."}, room=request.sid)
                current_app.logger.debug(f"SocketIO: jwt_required_socketio - Exiting '{func_name}' for SID {request.sid}. Outcome: Authentication Error (Missing 'sub' claim). Returning False.")
                return False

            current_app.logger.debug(f"SocketIO: jwt_required_socketio - User identity (sub) from token for event '{func_name}': {user_identity}. SID: {request.sid}")

            try:
                user_id = int(user_identity)
            except ValueError:
                current_app.logger.warning(f"SocketIO: jwt_required_socketio - Invalid user_id format '{user_identity}' in token for event '{func_name}' from SID {request.sid}. Emitting auth_error.")
                emit('auth_error', {'message': 'Invalid user identity format in token.'}, room=request.sid)
                current_app.logger.debug(f"SocketIO: jwt_required_socketio - Exiting '{func_name}' for SID {request.sid}. Outcome: Authentication Error (Invalid user_id format). Returning False.")
                return False

            current_app.logger.debug(f"SocketIO: jwt_required_socketio - Attempting to fetch user from DB for event '{func_name}'. SID: {request.sid}. User ID: {user_id}")
            user = db.session.get(User, user_id)

            if user:
                current_app.logger.debug(f"SocketIO: jwt_required_socketio - User fetched from DB for event '{func_name}'. SID: {request.sid}. User: ID={user.id}, Username={user.username}")
            else:
                current_app.logger.warning(f"SocketIO: jwt_required_socketio - User with ID {user_id} (from token sub) not found in DB for event '{func_name}'. SID: {request.sid}. Emitting auth_error.")
                emit('auth_error', {'message': 'User associated with token not found.'}, room=request.sid)
                current_app.logger.debug(f"SocketIO: jwt_required_socketio - Exiting '{func_name}' for SID {request.sid}. Outcome: Authentication Error (User not found in DB). Returning False.")
                return False

            g.socketio_user = user
            current_app.logger.info(f"SocketIO: jwt_required_socketio - User {user.username} (ID: {user.id}) authenticated for event '{func_name}' via JWT. SID: {request.sid}")

            # Call the actual event handler
            result = f(*args, **kwargs)
            current_app.logger.debug(f"SocketIO: jwt_required_socketio - Exiting '{func_name}' for SID {request.sid}. Outcome: Authenticated. Proceeding with event handler.")
            return result

        except ExpiredSignatureError as e:
            current_app.logger.info(f"SocketIO: jwt_required_socketio - Expired token for event '{func_name}' from SID {request.sid}. Error: {type(e).__name__} - {str(e)}. Emitting auth_error.")
            emit('auth_error', {'message': 'Token has expired.'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: jwt_required_socketio - Exiting '{func_name}' for SID {request.sid}. Outcome: Authentication Error (ExpiredSignatureError). Returning False.")
            return False
        except InvalidTokenError as e:
            current_app.logger.warning(f"SocketIO: jwt_required_socketio - Invalid token for event '{func_name}' from SID {request.sid}. Type: {type(e).__name__}, Error: {str(e)}. Emitting auth_error.")
            emit('auth_error', {'message': f'Invalid token supplied: {str(e)}'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: jwt_required_socketio - Exiting '{func_name}' for SID {request.sid}. Outcome: Authentication Error (InvalidTokenError). Returning False.")
            return False
        except Exception as e:
            current_app.logger.error(f"SocketIO: jwt_required_socketio - Unexpected critical error during JWT processing for event '{func_name}' from SID {request.sid}. Error: {type(e).__name__} - {str(e)}", exc_info=True)
            emit('auth_error', {'message': 'An critical server error occurred during authentication.'}, room=request.sid) # Existing message is fine, using "critical" as per existing
            current_app.logger.debug(f"SocketIO: jwt_required_socketio - Exiting '{func_name}' for SID {request.sid}. Outcome: Authentication Error (Unexpected Exception). Returning False.")
            return False

    return decorated_function
