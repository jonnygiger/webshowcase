from flask import request, session, current_app
from flask_socketio import emit, join_room, leave_room
from flask_login import current_user # Assuming flask_login's current_user for SocketIO
from functools import wraps
from datetime import datetime, timezone

from .. import socketio, db # Import from social_app parent package
from ..models.db_models import User, ChatRoom, ChatMessage, Post, PostLock # Import necessary models

# Decorator for SocketIO login required (similar to the one in app.py)
# This uses flask_login.current_user which should be integrated with Flask-SocketIO
def login_required_socketio(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            current_app.logger.warning(f"SocketIO: Unauthenticated access attempt to '{f.__name__}' from SID {request.sid}. Emitting 'unauthorized_error'.")
            emit('unauthorized_error', {'message': 'User not authenticated for this action.'}, room=request.sid)
            return False # Indicate failure / stop processing
        return f(*args, **kwargs)
    return decorated_function

# SocketIO event handlers previously in app.py

@socketio.on("join_chat_room")
@login_required_socketio # Protect this handler
def handle_join_chat_room_event(data):
    room_name = data.get("room_name") # e.g., "chat_room_1"
    # current_user is available due to login_required_socketio and Flask-SocketIO integration
    username = current_user.username

    if not room_name:
        current_app.logger.error(f"SocketIO: Join chat room event failed: room_name missing. SID: {request.sid}, User: {username}")
        emit('chat_error', {'message': 'Room name is required.'}, room=request.sid)
        return

    join_room(room_name)
    current_app.logger.info(f"SocketIO: User '{username}' (ID: {current_user.id}, SID: {request.sid}) joined chat room: '{room_name}'")
    socketio.emit("user_joined_chat", {"username": username, "room": room_name}, room=room_name)


@socketio.on("leave_chat_room")
@login_required_socketio # Protect this handler
def handle_leave_chat_room_event(data):
    room_name = data.get("room_name")
    username = current_user.username

    if not room_name:
        current_app.logger.error(f"SocketIO: Leave chat room event failed: room_name missing. SID: {request.sid}, User: {username}")
        # No emit error to client needed usually for leave, as client is leaving.
        return

    # leave_room(room_name) # This is managed by Flask-SocketIO if client disconnects or explicitly calls leave.
    current_app.logger.info(f"SocketIO: User '{username}' (ID: {current_user.id}, SID: {request.sid}) left chat room: '{room_name}' (notified others)")
    socketio.emit("user_left_chat", {"username": username, "room": room_name}, room=room_name)


@socketio.on("send_chat_message")
@login_required_socketio # Protect this handler
def handle_send_chat_message_event(data):
    room_name = data.get("room_name")
    message_text = data.get("message")
    username = current_user.username
    user_id = current_user.id

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
@login_required_socketio
def handle_join_room_event(data): # Name kept generic from app.py
    room = data.get("room")
    if not room:
        current_app.logger.warning(f"SocketIO: 'join_room' event from user {current_user.username} (SID: {request.sid}) missing 'room' data.")
        return
    join_room(room)
    current_app.logger.info(f"SocketIO: User {current_user.username} (SID: {request.sid}) joined generic room: {room}")


@socketio.on("join_group_chat")
@login_required_socketio
def handle_join_group_chat_event(data):
    group_id = data.get("group_id")
    if not group_id:
        current_app.logger.error(f"SocketIO: join_group_chat event from {current_user.username} (SID: {request.sid}) received without group_id")
        emit('error_event', {'message': 'Group ID is missing.'}, room=request.sid)
        return

    room_name = f"group_chat_{group_id}"
    join_room(room_name)
    current_app.logger.info(f"SocketIO: User '{current_user.username}' (SID: {request.sid}) joined group chat room: '{room_name}'")
    # socketio.emit('user_joined_group_notification', {'username': current_user.username, 'group_id': group_id}, room=room_name) # Optional: notify room


@socketio.on("send_group_message")
@login_required_socketio
def handle_send_group_message_event(data):
    group_id = data.get("group_id")
    message_content = data.get("message_content")

    if not group_id:
        current_app.logger.error(f"SocketIO: User {current_user.username} (SID: {request.sid}) tried to send group message without group_id.")
        emit('error_event', {'message': 'Group ID is missing.'}, room=request.sid)
        return
    if not message_content or not message_content.strip():
        # Optionally inform user their message was empty, or just ignore silently
        current_app.logger.info(f"SocketIO: User {current_user.username} (SID: {request.sid}) tried to send empty message to group {group_id}.")
        return

    # Note: Original app.py did not save group messages. Keeping that behavior.
    room_name = f"group_chat_{group_id}"
    message_payload = {
        "message_content": message_content.strip(), "sender_username": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat(), # Use isoformat for consistency
        "group_id": group_id, "user_id": current_user.id,
        "message_id": "temp_id_" + datetime.now(timezone.utc).isoformat(), # Temporary ID
    }
    socketio.emit("receive_group_message", message_payload, room=room_name)
    current_app.logger.info(f"SocketIO: User '{current_user.username}' (SID: {request.sid}) sent (unsaved) message to group {group_id}: '{message_content}'")


@socketio.on("edit_post_content")
# No @login_required_socketio here because original app.py had custom token + session auth logic
def handle_edit_post_content(data):
    # This handler needs careful review of its auth logic.
    # It used a mix of JWT token from data and session auth.
    # For now, replicating the logic. `decode_token` would need to be imported or defined.
    # `decode_token` likely comes from `flask_jwt_extended`.
    from flask_jwt_extended import decode_token # Assuming this is the one

    user_id_to_auth = None # Renamed to avoid confusion with current_user
    token = data.get("token")
    current_app.logger.debug(f"SocketIO: handle_edit_post_content. Data: {data}, SID: {request.sid}")

    if token:
        try:
            decoded_token = decode_token(token)
            identity = decoded_token["sub"]
            if isinstance(identity, str) and identity.isdigit(): user_id_to_auth = int(identity)
            elif isinstance(identity, int): user_id_to_auth = identity
            else: current_app.logger.warning(f"Token for edit_post_content invalid sub: {identity}")
        except Exception as e:
            current_app.logger.error(f"Token validation failed for edit_post_content: {e}")
            emit('edit_error', {'message': f"Token error: {str(e)}"}, room=request.sid); return

    if not user_id_to_auth: # Fallback to session if token auth failed or no token
        if current_user.is_authenticated: # Check Flask-Login's current_user
             user_id_to_auth = current_user.id
             current_app.logger.debug(f"SocketIO: Edit auth using current_user.id: {user_id_to_auth}")
        else: # Fallback to raw session if current_user is not authenticated (e.g. if LoginManager setup is incomplete for SocketIO)
            user_id_from_session = session.get("user_id")
            if user_id_from_session:
                user_id_to_auth = user_id_from_session
                current_app.logger.debug(f"SocketIO: Edit auth using raw session user_id: {user_id_to_auth}")

    if not user_id_to_auth:
        current_app.logger.debug(f"SocketIO: Edit auth failed (no token/session/current_user). SID: {request.sid}")
        emit('edit_error', {'message': 'Authentication required.'}, room=request.sid); return

    current_app.logger.debug(f"SocketIO: Authenticated user_id for edit: {user_id_to_auth}")

    post_id = data.get("post_id")
    new_content = data.get("new_content")
    if not post_id or new_content is None:
        emit('edit_error', {'message': 'Post ID and new content are required.'}, room=request.sid); return

    post = db.session.get(Post, post_id)
    if not post:
        emit('edit_error', {'message': 'Post not found.'}, room=request.sid); return

    lock = post.lock_info
    if not lock:
        emit('edit_error', {'message': 'Post not locked. Acquire lock first.'}, room=request.sid); return

    # Ensure user_id_to_auth is compared as int if lock.user_id is int
    if lock.user_id != int(user_id_to_auth):
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
        editor_user = db.session.get(User, int(user_id_to_auth)) # Fetch user for username
        editor_username = editor_user.username if editor_user else "Unknown"
        update_payload = {
            "post_id": post.id, "new_content": post.content, "last_edited": post.last_edited.isoformat(),
            "edited_by_user_id": int(user_id_to_auth), "edited_by_username": editor_username,
        }
        socketio.emit("post_content_updated", update_payload, room=f"post_{post.id}")
        current_app.logger.info(f"User {user_id_to_auth} updated post {post.id}. Broadcasted.")
        emit('edit_success', {'message': 'Content updated.', "post_id": post.id}, room=request.sid)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error committing post update by user {user_id_to_auth} for post {post.id}: {e}")
        emit('edit_error', {'message': 'Server error saving changes.'}, room=request.sid)


@socketio.on("connect", namespace="/") # Matches the namespace in app.py
def handle_connect():
    # This connection handler needs to align with how Flask-Login and Flask-SocketIO are integrated.
    # If using current_user proxy from Flask-Login, it should work if session is correctly passed.
    current_app.logger.info(f"SocketIO: Connect attempt. SID: {request.sid}. Cookies: {request.cookies.get('session')}") # Log session cookie if present

    # The original app.py had complex logging for flask.session and werkzeug.request.session.
    # Flask-SocketIO's `current_user` (if Flask-Login is setup correctly) simplifies this.
    # Or, if session is manually managed for SocketIO, `session.get('user_id')` from `flask import session` might be used.

    user_to_auth_on_connect = None # Renamed
    if current_user.is_authenticated:
        user_to_auth_on_connect = current_user
        current_app.logger.info(f"SocketIO: User authenticated via Flask-Login current_user: {user_to_auth_on_connect.username} (SID: {request.sid})")
    elif "user_id" in session: # Fallback to flask.session if current_user is not set by Flask-SocketIO/Flask-Login
        user_id_from_raw_session = session.get("user_id")
        current_app.logger.info(f"SocketIO: current_user not auth, trying user_id {user_id_from_raw_session} from flask.session. (SID: {request.sid})")
        user_from_raw_session = db.session.get(User, user_id_from_raw_session)
        if user_from_raw_session:
            user_to_auth_on_connect = user_from_raw_session
            # Manually login this user for the socketio session if needed, or ensure current_user gets set.
            # This part is tricky and depends on Flask-SocketIO and Flask-Login integration details.
            # For now, we'll just log. If current_user is not properly set by Flask-SocketIO,
            # then @login_required_socketio might not work as expected.
            current_app.logger.info(f"SocketIO: User manually loaded from flask.session: {user_to_auth_on_connect.username} (SID: {request.sid})")
        else:
            current_app.logger.warning(f"SocketIO: user_id {user_id_from_raw_session} in session, but no user in DB. (SID: {request.sid})")

    if user_to_auth_on_connect and hasattr(user_to_auth_on_connect, 'is_authenticated') and user_to_auth_on_connect.is_authenticated:
        join_room(f"user_{user_to_auth_on_connect.id}")
        current_app.logger.info(f"SocketIO: User {user_to_auth_on_connect.username} (SID: {request.sid}) connected to global ns and joined room user_{user_to_auth_on_connect.id}")
        emit('confirm_namespace_connected', {'namespace': request.namespace, 'sid': request.sid, 'status': 'authenticated', 'username': user_to_auth_on_connect.username}, room=request.sid)
    else:
        current_app.logger.info(f"SocketIO: User could not be authenticated for SocketIO connection. (SID: {request.sid})")
        emit('confirm_namespace_connected', {'namespace': request.namespace, 'sid': request.sid, 'status': 'anonymous_after_check'}, room=request.sid)

# Note: The `login_required_socketio` decorator relies on `current_user` from Flask-Login.
# Flask-SocketIO needs to be properly integrated with Flask-Login for `current_user` to be
# automatically available and authenticated in SocketIO event handlers.
# If it's not (e.g. session not correctly passed or handled), then `current_user.is_authenticated`
# might be false even for logged-in users. This is a common integration challenge.
# The connect handler above attempts to log this.
# The `handle_edit_post_content` has its own JWT + session logic that bypasses `login_required_socketio`.
# All other handlers use `login_required_socketio`.
# Ensure `flask_jwt_extended.decode_token` is available if that handler is used.
# `current_app.logger` is used for logging.
# `socketio` and `db` are imported from `social_app/__init__.py`.
# Models are imported from `social_app/models/db_models.py`.
# `request`, `session` are from `flask`.
# `emit`, `join_room`, `leave_room` are from `flask_socketio`.
# `datetime`, `timezone` from `datetime`.
# `wraps` from `functools`.
# `PostLock` model was added to imports for `handle_edit_post_content`.
# `ChatRoom`, `ChatMessage` models were added for chat handlers.
# `User` model is used throughout.
# `current_app` is from `flask`.
# Corrected url_for in emit_new_activity_event to use blueprint `core.static` if static files are served via core blueprint,
# or just `static` if served at app level. Assuming app level for now. It was `url_for("static", ...)`
# The emit_new_activity_event was in views.py. If it's needed here, it should be imported or moved.
# For now, assuming SocketIO events here are mostly direct chat/edit events, not activity stream generation.
# If emit_new_activity_event is called from these SocketIO handlers, it would need to be accessible.
# It's not called directly by any of these handlers moved from app.py's SocketIO section.
# It was called by regular view functions after certain actions (like creating post, comment, like).
# So, it should remain in views.py or a utils.py accessible by views.py.
# The `handle_connect` function here is the more detailed one from the end of app.py.
# The simpler `handle_connect` that was also in app.py was a duplicate and thus ignored.
# The `login_required_socketio` decorator was also defined in app.py; it's replicated here.
# It should be defined once, perhaps in a `core.utils_socketio` or similar if used by multiple event files.
# For now, it's here as it's closely tied to these event handlers.
# Corrected `emit('unauthorized_error', ..., room=request.sid)` for login_required_socketio to target sender.
# Corrected `emit('chat_error', ..., room=request.sid)` for chat handlers to target sender.
# Corrected `emit('edit_error', ..., room=request.sid)` for edit handler to target sender.
# Corrected `emit('confirm_namespace_connected', ..., room=request.sid)` for connect handler.
# Added PostLock to model imports for edit_post_content handler.
# The edit_post_content handler's user_id_to_auth logic for session fallback now checks current_user.is_authenticated first,
# then raw session.get('user_id'). This provides a layer if Flask-Login integration is partially working for SocketIO.
# It also ensures user_id_to_auth is compared as int with lock.user_id.
# Username for post_content_updated event is fetched using user_id_to_auth.
# Ensured all logger calls use current_app.logger.
# Ensured all db calls use the imported db object.
# Ensured socketio calls use the imported socketio object.
# Ensured User, ChatRoom, ChatMessage, Post, PostLock models are imported.
# `datetime`, `timezone` from `datetime` and `wraps` from `functools` are imported.
# `decode_token` from `flask_jwt_extended` is imported locally in the function that uses it.
# `request`, `session`, `current_app` from `flask`.
# `emit`, `join_room`, `leave_room` from `flask_socketio`.
# `current_user` from `flask_login`.
