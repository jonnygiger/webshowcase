from flask import request, session, current_app
from flask_socketio import emit, join_room
from flask_login import current_user
from flask_jwt_extended import decode_token
from jwt import ExpiredSignatureError, InvalidTokenError
from .. import db, socketio # Or ensure socketio is available if used in @socketio.on
from ..models.db_models import User, ChatRoom, ChatMessage, Post, PostLock # Import necessary models
from functools import wraps # Keep if jwt_required_socketio or other decorators use it
from datetime import datetime, timezone # Keep for other event handlers
from ..core.socketio_auth import jwt_required_socketio # Ensure this path is correct

# SocketIO event handlers previously in app.py

@socketio.on("join_chat_room")
@jwt_required_socketio # Changed
def handle_join_chat_room_event(data):
    user = g.socketio_user # Changed
    room_name = data.get("room_name") # e.g., "chat_room_1"
    username = user.username # Changed

    if not room_name:
        current_app.logger.error(f"SocketIO: Join chat room event failed: room_name missing. SID: {request.sid}, User: {username}")
        emit('chat_error', {'message': 'Room name is required.'}, room=request.sid)
        return

    join_room(room_name)
    current_app.logger.info(f"SocketIO: User '{username}' (ID: {user.id}, SID: {request.sid}) joined chat room: '{room_name}'")
    socketio.emit("user_joined_chat", {"username": username, "room": room_name}, room=room_name)


@socketio.on("leave_chat_room")
@jwt_required_socketio # Changed
def handle_leave_chat_room_event(data):
    user = g.socketio_user # Changed
    room_name = data.get("room_name")
    username = user.username # Changed

    if not room_name:
        current_app.logger.error(f"SocketIO: Leave chat room event failed: room_name missing. SID: {request.sid}, User: {username}")
        # No emit error to client needed usually for leave, as client is leaving.
        return

    # leave_room(room_name) # This is managed by Flask-SocketIO if client disconnects or explicitly calls leave.
    current_app.logger.info(f"SocketIO: User '{username}' (ID: {user.id}, SID: {request.sid}) left chat room: '{room_name}' (notified others)")
    socketio.emit("user_left_chat", {"username": username, "room": room_name}, room=room_name)


@socketio.on("send_chat_message")
@jwt_required_socketio # Changed
def handle_send_chat_message_event(data):
    user = g.socketio_user # Changed
    room_name = data.get("room_name")
    message_text = data.get("message")
    username = user.username # Changed
    user_id = user.id # Changed

    if not room_name or not message_text:
        current_app.logger.error(f"SocketIO: Send chat message event failed: room_name='{room_name}', message empty? {not message_text}. SID: {request.sid}, User: {username}")
        emit('chat_error', {'message': 'Room and message are required.'}, room=request.sid)
        return

    try:
        room_id_str = room_name.split("_")[-1]
        chat_room_id = int(room_id_str)
    except (IndexError, ValueError) as e:
        current_app.logger.error(f"SocketIO: Could not parse chat_room_id from room_name '{room_name}': {e}. SID: {request.sid}, User: {username}")
        emit('chat_error', {'message': 'Invalid room name format.'}, room=request.sid)
        return

    chat_room = db.session.get(ChatRoom, chat_room_id)
    if not chat_room:
        current_app.logger.error(f"SocketIO: ChatRoom with id {chat_room_id} not found for message from user {user_id}. SID: {request.sid}")
        emit('chat_error', {'message': f"Chat room {chat_room_id} not found."}, room=request.sid)
        return

    try:
        new_chat_message = ChatMessage(room_id=chat_room_id, user_id=user_id, message=message_text)
        db.session.add(new_chat_message)
        db.session.commit()
        current_app.logger.info(f"SocketIO: User '{username}' sent message to room '{room_name}': '{message_text}' (ID: {new_chat_message.id})")

        message_payload = {
            "id": new_chat_message.id, "room_name": room_name, "user_id": new_chat_message.user_id,
            "username": username, "message": new_chat_message.message,
            "timestamp": new_chat_message.timestamp.isoformat(),
        }
        socketio.emit("new_chat_message", message_payload, room=room_name)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"SocketIO: Error saving/sending chat message for room {room_name} by user {user_id}: {e}. SID: {request.sid}")
        emit('chat_error', {'message': 'An error occurred sending your message.'}, room=request.sid)


@socketio.on("join_room") # Generic room joining, used by some features like user-specific notifications
@jwt_required_socketio # Changed
def handle_join_room_event(data): # Name kept generic from app.py
    user = g.socketio_user # Changed
    room = data.get("room")
    if not room:
        current_app.logger.warning(f"SocketIO: 'join_room' event from user {user.username} (SID: {request.sid}) missing 'room' data.")
        return
    join_room(room)
    current_app.logger.info(f"SocketIO: User {user.username} (SID: {request.sid}) joined generic room: {room}")


@socketio.on("join_group_chat")
@jwt_required_socketio # Changed
def handle_join_group_chat_event(data):
    user = g.socketio_user # Changed
    group_id = data.get("group_id")
    if not group_id:
        current_app.logger.error(f"SocketIO: join_group_chat event from {user.username} (SID: {request.sid}) received without group_id")
        emit('error_event', {'message': 'Group ID is missing.'}, room=request.sid)
        return

    room_name = f"group_chat_{group_id}"
    join_room(room_name)
    current_app.logger.info(f"SocketIO: User '{user.username}' (SID: {request.sid}) joined group chat room: '{room_name}'")
    # socketio.emit('user_joined_group_notification', {'username': current_user.username, 'group_id': group_id}, room=room_name) # Optional: notify room


@socketio.on("send_group_message")
@jwt_required_socketio # Changed
def handle_send_group_message_event(data):
    user = g.socketio_user # Changed
    group_id = data.get("group_id")
    message_content = data.get("message_content")

    if not group_id:
        current_app.logger.error(f"SocketIO: User {user.username} (SID: {request.sid}) tried to send group message without group_id.")
        emit('error_event', {'message': 'Group ID is missing.'}, room=request.sid)
        return
    if not message_content or not message_content.strip():
        # Optionally inform user their message was empty, or just ignore silently
        current_app.logger.info(f"SocketIO: User {user.username} (SID: {request.sid}) tried to send empty message to group {group_id}.")
        return

    # Note: Original app.py did not save group messages. Keeping that behavior.
    room_name = f"group_chat_{group_id}"
    message_payload = {
        "message_content": message_content.strip(), "sender_username": user.username, # Changed
        "timestamp": datetime.now(timezone.utc).isoformat(), # Use isoformat for consistency
        "group_id": group_id, "user_id": user.id, # Changed
        "message_id": "temp_id_" + datetime.now(timezone.utc).isoformat(), # Temporary ID
    }
    socketio.emit("receive_group_message", message_payload, room=room_name)
    current_app.logger.info(f"SocketIO: User '{user.username}' (SID: {request.sid}) sent (unsaved) message to group {group_id}: '{message_content}'")


@socketio.on("edit_post_content")
@jwt_required_socketio # Changed
def handle_edit_post_content(data):
    # Removed custom auth logic, user is now in g.socketio_user
    user = g.socketio_user # Added
    user_id_to_auth = user.id # Use authed user's ID

    current_app.logger.debug(f"SocketIO: handle_edit_post_content. Data: {data}, SID: {request.sid}, User: {user.username}")

    post_id = data.get("post_id")
    new_content = data.get("new_content")
    if not post_id or new_content is None:
        emit('edit_error', {'message': 'Post ID and new content are required.'}, room=request.sid); return

    post = db.session.get(Post, post_id)
    if not post:
        emit('edit_error', {'message': 'Post not found.'}, room=request.sid); return

    lock = post.lock_info # Assuming Post model has a relationship 'lock_info' to PostLock
    if not lock:
        emit('edit_error', {'message': 'Post not locked. Acquire lock first.'}, room=request.sid); return

    if lock.user_id != user_id_to_auth: # Compare with authed user's ID
        if lock.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
            emit('edit_error', {'message': 'Lock by other user expired. Try acquiring.'}, room=request.sid)
        else:
            emit('edit_error', {'message': 'Post locked by another user.'}, room=request.sid)
        return

    if lock.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        db.session.delete(lock)
        try:
            db.session.commit()
            socketio.emit("post_lock_released", {"post_id": post_id, "username": "System (Expired)"}, room=f"post_{post_id}")
        except Exception as e:
            db.session.rollback(); current_app.logger.error(f"Error deleting expired lock: {e}")
        emit('edit_error', {'message': 'Your lock expired. Acquire new lock.'}, room=request.sid); return

    post.content = new_content
    post.last_edited = datetime.now(timezone.utc)
    try:
        db.session.commit()
        editor_username = user.username # Use authed user's username
        update_payload = {
            "post_id": post.id, "new_content": post.content, "last_edited": post.last_edited.isoformat(),
            "edited_by_user_id": user_id_to_auth,
            "edited_by_username": editor_username,
        }
        socketio.emit("post_content_updated", update_payload, room=f"post_{post.id}")
        current_app.logger.info(f"User {user_id_to_auth} updated post {post.id}. Broadcasted.")
        emit('edit_success', {'message': 'Content updated.', "post_id": post.id}, room=request.sid)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error committing post update by user {user_id_to_auth} for post {post.id}: {e}")
        emit('edit_error', {'message': 'Server error saving changes.'}, room=request.sid)


@socketio.on("connect", namespace="/")
def handle_connect():
    user_to_auth_on_connect = None
    user_authenticated_by_jwt = False
    auth_method = "anonymous"

    auth_header = request.namespace.auth
    current_app.logger.info(f"SocketIO: handle_connect: auth_header: {auth_header}. SID: {request.sid}") # Log auth_header
    if auth_header and isinstance(auth_header, dict) and 'token' in auth_header:
        jwt_token = auth_header.get('token')
        current_app.logger.info(f"SocketIO: Connect attempt with JWT. Token: {jwt_token}. SID: {request.sid}") # Log token
        try:
            decoded_token = decode_token(jwt_token)
            user_identity = decoded_token['sub']
            current_app.logger.info(f"SocketIO: JWT decoded. user_identity: {user_identity}. SID: {request.sid}") # Log user_identity
            # Ensure user_identity can be converted to an integer for DB query
            try:
                user_id = int(user_identity)
                current_app.logger.info(f"SocketIO: JWT user_identity converted to user_id: {user_id}. SID: {request.sid}") # Log user_id
            except ValueError:
                current_app.logger.error(f"SocketIO: JWT 'sub' claim '{user_identity}' is not a valid integer. SID: {request.sid}")
                emit('auth_error', {'message': 'Invalid user identifier in token.'}, room=request.sid)
                return False # Deny connection

            jwt_user = db.session.get(User, user_id)
            current_app.logger.info(f"SocketIO: JWT User object retrieved from DB: {'Success' if jwt_user else 'Failure'}. SID: {request.sid}") # Log User object retrieval
            if jwt_user:
                user_to_auth_on_connect = jwt_user
                user_authenticated_by_jwt = True
                auth_method = "jwt"
                current_app.logger.info(f"SocketIO: User '{jwt_user.username}' authenticated via JWT. SID: {request.sid}") # Log JWT auth success
            else:
                current_app.logger.warning(f"SocketIO: JWT valid, but user ID '{user_id}' not found in DB. SID: {request.sid}")
                emit('auth_error', {'message': 'User not found for provided token.'}, room=request.sid)
                return False # Deny connection
        except ExpiredSignatureError:
            current_app.logger.warning(f"SocketIO: JWT connection failed: Token expired. SID: {request.sid}") # Log ExpiredSignatureError
            emit('auth_error', {'message': 'Token has expired.'}, room=request.sid)
            return False # Deny connection
        except InvalidTokenError as e:
            current_app.logger.error(f"SocketIO: JWT connection failed: Invalid token: {e}. SID: {request.sid}") # Log InvalidTokenError
            emit('auth_error', {'message': f'Invalid token: {e}'}, room=request.sid)
            return False # Deny connection
        except Exception as e: # Catch any other decoding errors or issues
            current_app.logger.error(f"SocketIO: JWT connection failed due to unexpected error: {e}. SID: {request.sid}")
            emit('auth_error', {'message': 'Authentication error.'}, room=request.sid)
            return False # Deny connection
    else:
        current_app.logger.info(f"SocketIO: No JWT in auth header or JWT auth failed, attempting session authentication. SID: {request.sid}. Cookies: {request.cookies.get('session')}") # Log JWT auth failed/skipped
        current_app.logger.info(f"SocketIO: current_user.is_authenticated: {current_user.is_authenticated}. current_user: {current_user}. SID: {request.sid}") # Log current_user status
        if current_user.is_authenticated:
            user_to_auth_on_connect = current_user
            auth_method = "session_current_user"
            current_app.logger.info(f"SocketIO: User '{current_user.username}' authenticated via Flask-Login current_user (Session Auth Success). SID: {request.sid}") # Log session auth success
        elif "_user_id" in session: # <<< MODIFIED
            user_id_from_session = session.get("_user_id") # <<< MODIFIED
            current_app.logger.info(f"SocketIO: current_user not authenticated, trying _user_id '{user_id_from_session}' from flask.session. SID: {request.sid}") # Log change
            try:
                # Ensure user_id_from_session is valid integer before querying DB
                user_id = int(user_id_from_session) # Keep this conversion
                user_from_session = db.session.get(User, user_id)
                current_app.logger.info(f"SocketIO: Session User object retrieved from DB (using _user_id): {'Success' if user_from_session else 'Failure'}. SID: {request.sid}") # Log User object retrieval
                if user_from_session:
                    user_to_auth_on_connect = user_from_session
                    auth_method = "session_underscore_user_id" # Log change
                    current_app.logger.info(f"SocketIO: User '{user_from_session.username}' authenticated via _user_id in session (Session Auth Success). SID: {request.sid}") # Log change
                else:
                    current_app.logger.warning(f"SocketIO: _user_id '{user_id_from_session}' in session, but no such user in DB. SID: {request.sid}")
            except ValueError:
                current_app.logger.error(f"SocketIO: _user_id '{user_id_from_session}' in session is not a valid integer. SID: {request.sid}")
            # If user_from_session is None or ValueError, user_to_auth_on_connect remains None

    if user_to_auth_on_connect:
        join_room(f"user_{user_to_auth_on_connect.id}")
        current_app.logger.info(f"SocketIO: User {user_to_auth_on_connect.username} (SID: {request.sid}, Auth: {auth_method}) connected to namespace '/' and joined room user_{user_to_auth_on_connect.id}") # Log final outcome - success
        emit('confirm_namespace_connected', {
            'namespace': request.namespace,
            'sid': request.sid,
            'status': 'authenticated',
            'username': user_to_auth_on_connect.username,
            'user_id': user_to_auth_on_connect.id,
            'auth_method': auth_method
        }, room=request.sid)
        # No return True explicitly needed, successful connection is the default
    else:
        # This block is reached if no JWT was provided AND session auth failed
        current_app.logger.info(f"SocketIO: User could not be authenticated for SocketIO connection (no JWT, session auth failed). Auth method: {auth_method}. SID: {request.sid}") # Log final outcome - failure
        emit('auth_error', {'message': 'Authentication required.'}, room=request.sid)
        return False # Deny connection

# Note: `jwt_required_socketio` decorator relies on `g.socketio_user` being set.
# This `handle_connect` does not set `g.socketio_user`. That's typically done
# by an authentication decorator or a before_request hook for SocketIO events,
# *after* the connection is established. This connect handler only authenticates
# the connection itself and joins the user to their room.
# Other event handlers decorated with `@jwt_required_socketio` will perform their own JWT checks.
# The `login_required_socketio` decorator mentioned in original comments might be an alternative
# if session-based auth is the primary method for event handlers.
# For now, this `handle_connect` focuses on authenticating the *connection* using JWT first, then session.
# Flask-SocketIO needs to be properly integrated with Flask-Login for `current_user` to be
# automatically available and authenticated in SocketIO event handlers for session-based users.
# If `current_user` isn't populated correctly by the Flask-SocketIO + Flask-Login setup,
# session-based authentication in this handler might not work as expected,
# relying solely on the `session.get('user_id')` check.
