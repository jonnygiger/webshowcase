from flask import request, session, current_app, g
from flask_socketio import emit, join_room
from flask_login import current_user
from flask_jwt_extended import decode_token
from jwt import ExpiredSignatureError, InvalidTokenError
from .. import db, socketio
from ..models.db_models import User, ChatRoom, ChatMessage, Post, PostLock
from functools import wraps
from datetime import datetime, timezone
from ..core.socketio_auth import jwt_required_socketio


@socketio.on("join_chat_room")
@jwt_required_socketio
def handle_join_chat_room_event(data):
    user = g.socketio_user
    func_name = "handle_join_chat_room_event"
    current_app.logger.debug(f"SocketIO: Entering '{func_name}'. SID: {request.sid}. User: {user.username} (ID: {user.id}). Data: {data}")

    room_name = data.get("room_name")
    username = user.username

    if not room_name:
        current_app.logger.error(f"SocketIO: '{func_name}' failed: room_name missing. SID: {request.sid}, User: {username}")
        emit('chat_error', {'message': 'Room name is required.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' due to missing room_name. SID: {request.sid}")
        return

    current_app.logger.debug(f"SocketIO: '{func_name}' - User {username} attempting to join room: '{room_name}'. SID: {request.sid}")
    join_room(room_name)
    current_app.logger.info(f"SocketIO: User '{username}' (ID: {user.id}, SID: {request.sid}) joined chat room: '{room_name}'")

    current_app.logger.debug(f"SocketIO: '{func_name}' - Emitting 'user_joined_chat'. SID: {request.sid}")
    socketio.emit("user_joined_chat", {"username": username, "room": room_name}, room=room_name)
    current_app.logger.debug(f"SocketIO: Exiting '{func_name}'. SID: {request.sid}")


@socketio.on("leave_chat_room")
@jwt_required_socketio
def handle_leave_chat_room_event(data):
    user = g.socketio_user
    func_name = "handle_leave_chat_room_event"
    current_app.logger.debug(f"SocketIO: Entering '{func_name}'. SID: {request.sid}. User: {user.username} (ID: {user.id}). Data: {data}")

    room_name = data.get("room_name")
    username = user.username

    if not room_name:
        current_app.logger.error(f"SocketIO: '{func_name}' failed: room_name missing. SID: {request.sid}, User: {username}")
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' due to missing room_name. SID: {request.sid}")
        return

    current_app.logger.debug(f"SocketIO: '{func_name}' - User {username} attempting to leave room: '{room_name}'. Emitting 'user_left_chat'. SID: {request.sid}")
    socketio.emit("user_left_chat", {"username": username, "room": room_name}, room=room_name)
    current_app.logger.info(f"SocketIO: User '{username}' (ID: {user.id}, SID: {request.sid}) left chat room: '{room_name}' (notified others)")
    current_app.logger.debug(f"SocketIO: Exiting '{func_name}'. SID: {request.sid}")


@socketio.on("send_chat_message")
@jwt_required_socketio
def handle_send_chat_message_event(data):
    user = g.socketio_user
    func_name = "handle_send_chat_message_event"
    current_app.logger.debug(f"SocketIO: Entering '{func_name}'. SID: {request.sid}. User: {user.username} (ID: {user.id}). Data: {data}")

    room_name = data.get("room_name")
    message_text = data.get("message")
    username = user.username
    user_id = user.id

    if not room_name or not message_text:
        current_app.logger.error(f"SocketIO: '{func_name}' failed: room_name='{room_name}', message empty? {not message_text}. SID: {request.sid}, User: {username}")
        emit('chat_error', {'message': 'Room and message are required.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' due to missing room_name or message. SID: {request.sid}")
        return

    current_app.logger.debug(f"SocketIO: '{func_name}' - Room: '{room_name}', Message: '{message_text}'. SID: {request.sid}")

    try:
        room_id_str = room_name.split("_")[-1]
        chat_room_id = int(room_id_str)
        current_app.logger.debug(f"SocketIO: '{func_name}' - Parsed chat_room_id: {chat_room_id}. SID: {request.sid}")
    except (IndexError, ValueError) as e:
        current_app.logger.error(f"SocketIO: '{func_name}' - Could not parse chat_room_id from room_name '{room_name}': {e}. SID: {request.sid}, User: {username}")
        emit('chat_error', {'message': 'Invalid room name format.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' due to invalid room name format. SID: {request.sid}")
        return

    current_app.logger.debug(f"SocketIO: '{func_name}' - Fetching ChatRoom with ID {chat_room_id}. SID: {request.sid}")
    chat_room = db.session.get(ChatRoom, chat_room_id)
    if not chat_room:
        current_app.logger.error(f"SocketIO: '{func_name}' - ChatRoom with id {chat_room_id} not found for message from user {user_id}. SID: {request.sid}")
        emit('chat_error', {'message': f"Chat room {chat_room_id} not found."}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' because chat room not found. SID: {request.sid}")
        return
    current_app.logger.debug(f"SocketIO: '{func_name}' - Found ChatRoom: {chat_room}. SID: {request.sid}")

    try:
        current_app.logger.debug(f"SocketIO: '{func_name}' - Creating ChatMessage object. Room ID: {chat_room_id}, User ID: {user_id}. SID: {request.sid}")
        new_chat_message = ChatMessage(room_id=chat_room_id, user_id=user_id, message=message_text)
        current_app.logger.debug(f"SocketIO: '{func_name}' - Adding ChatMessage to session. SID: {request.sid}")
        db.session.add(new_chat_message)
        current_app.logger.debug(f"SocketIO: '{func_name}' - Committing ChatMessage to DB. SID: {request.sid}")
        db.session.commit()
        current_app.logger.info(f"SocketIO: '{func_name}' - User '{username}' sent message to room '{room_name}': '{message_text}' (ID: {new_chat_message.id}). SID: {request.sid}")

        message_payload = {
            "id": new_chat_message.id, "room_name": room_name, "user_id": new_chat_message.user_id,
            "username": username, "message": new_chat_message.message,
            "timestamp": new_chat_message.timestamp.isoformat(),
        }
        current_app.logger.debug(f"SocketIO: '{func_name}' - Emitting 'new_chat_message' with payload: {message_payload}. SID: {request.sid}")
        socketio.emit("new_chat_message", message_payload, room=room_name)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"SocketIO: '{func_name}' - Error saving/sending chat message for room {room_name} by user {user_id}: {e}. SID: {request.sid}", exc_info=True)
        emit('chat_error', {'message': 'An error occurred sending your message.'}, room=request.sid)
    current_app.logger.debug(f"SocketIO: Exiting '{func_name}'. SID: {request.sid}")


@socketio.on("join_room")
@jwt_required_socketio
def handle_join_room_event(data):
    user = g.socketio_user
    func_name = "handle_join_room_event"
    current_app.logger.debug(f"SocketIO: Entering '{func_name}'. SID: {request.sid}. User: {user.username} (ID: {user.id}). Data: {data}")

    room = data.get("room")
    if not room:
        current_app.logger.warning(f"SocketIO: '{func_name}' event from user {user.username} (SID: {request.sid}) missing 'room' data.")
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' due to missing room data. SID: {request.sid}")
        return

    current_app.logger.debug(f"SocketIO: '{func_name}' - User {user.username} attempting to join generic room: '{room}'. SID: {request.sid}")
    join_room(room)
    current_app.logger.info(f"SocketIO: User {user.username} (SID: {request.sid}) joined generic room: {room}")
    current_app.logger.debug(f"SocketIO: Exiting '{func_name}'. SID: {request.sid}")


@socketio.on("join_group_chat")
@jwt_required_socketio
def handle_join_group_chat_event(data):
    user = g.socketio_user
    func_name = "handle_join_group_chat_event"
    current_app.logger.debug(f"SocketIO: Entering '{func_name}'. SID: {request.sid}. User: {user.username} (ID: {user.id}). Data: {data}")

    group_id = data.get("group_id")
    if not group_id:
        current_app.logger.error(f"SocketIO: '{func_name}' event from {user.username} (SID: {request.sid}) received without group_id")
        emit('error_event', {'message': 'Group ID is missing.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' due to missing group_id. SID: {request.sid}")
        return

    room_name = f"group_chat_{group_id}"
    current_app.logger.debug(f"SocketIO: '{func_name}' - User {user.username} attempting to join group chat room: '{room_name}' (Group ID: {group_id}). SID: {request.sid}")
    join_room(room_name)
    current_app.logger.info(f"SocketIO: User '{user.username}' (SID: {request.sid}) joined group chat room: '{room_name}'")
    current_app.logger.debug(f"SocketIO: Exiting '{func_name}'. SID: {request.sid}")


@socketio.on("send_group_message")
@jwt_required_socketio
def handle_send_group_message_event(data):
    user = g.socketio_user
    func_name = "handle_send_group_message_event"
    current_app.logger.debug(f"SocketIO: Entering '{func_name}'. SID: {request.sid}. User: {user.username} (ID: {user.id}). Data: {data}")

    group_id = data.get("group_id")
    message_content = data.get("message_content")

    if not group_id:
        current_app.logger.error(f"SocketIO: '{func_name}' - User {user.username} (SID: {request.sid}) tried to send group message without group_id.")
        emit('error_event', {'message': 'Group ID is missing.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' due to missing group_id. SID: {request.sid}")
        return
    if not message_content or not message_content.strip():
        current_app.logger.info(f"SocketIO: '{func_name}' - User {user.username} (SID: {request.sid}) tried to send empty message to group {group_id}.")
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' due to empty message. SID: {request.sid}")
        return

    room_name = f"group_chat_{group_id}"
    current_app.logger.debug(f"SocketIO: '{func_name}' - Group ID: {group_id}, Message: '{message_content}', Room: '{room_name}'. SID: {request.sid}")

    message_payload = {
        "message_content": message_content.strip(), "sender_username": user.username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "group_id": group_id, "user_id": user.id,
        "message_id": "temp_id_" + datetime.now(timezone.utc).isoformat(), # Note: This is a temporary ID
    }
    current_app.logger.debug(f"SocketIO: '{func_name}' - Emitting 'receive_group_message' with payload: {message_payload}. SID: {request.sid}")
    socketio.emit("receive_group_message", message_payload, room=room_name)
    current_app.logger.info(f"SocketIO: User '{user.username}' (SID: {request.sid}) sent (unsaved) message to group {group_id}: '{message_content}'")
    current_app.logger.debug(f"SocketIO: Exiting '{func_name}'. SID: {request.sid}")


@socketio.on("edit_post_content")
@jwt_required_socketio
def handle_edit_post_content(data):
    user = g.socketio_user
    user_id_to_auth = user.id # Renaming for clarity in this context
    func_name = "handle_edit_post_content"
    current_app.logger.debug(f"SocketIO: Entering '{func_name}'. SID: {request.sid}. User: {user.username} (ID: {user_id_to_auth}). Data: {data}")

    post_id = data.get("post_id")
    new_content = data.get("new_content")

    if not post_id or new_content is None:
        current_app.logger.warning(f"SocketIO: '{func_name}' - Missing post_id ({post_id}) or new_content (is None: {new_content is None}). SID: {request.sid}")
        emit('edit_error', {'message': 'Post ID and new content are required.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' due to missing data. SID: {request.sid}")
        return

    current_app.logger.debug(f"SocketIO: '{func_name}' - Attempting to edit Post ID: {post_id} with new content. SID: {request.sid}")
    current_app.logger.debug(f"SocketIO: '{func_name}' - Fetching Post with ID {post_id}. SID: {request.sid}")
    post = db.session.get(Post, post_id)

    if not post:
        current_app.logger.warning(f"SocketIO: '{func_name}' - Post with ID {post_id} not found. SID: {request.sid}")
        emit('edit_error', {'message': 'Post not found.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' because post not found. SID: {request.sid}")
        return
    current_app.logger.debug(f"SocketIO: '{func_name}' - Found Post: {post}. SID: {request.sid}")

    lock = post.lock_info
    current_app.logger.debug(f"SocketIO: '{func_name}' - Lock info for Post ID {post_id}: {lock}. SID: {request.sid}")

    if not lock:
        current_app.logger.warning(f"SocketIO: '{func_name}' - Post {post_id} is not locked. Edit rejected. SID: {request.sid}")
        emit('edit_error', {'message': 'Post not locked. Acquire lock first.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' because post not locked. SID: {request.sid}")
        return

    if lock.user_id != user_id_to_auth:
        current_app.logger.warning(f"SocketIO: '{func_name}' - Post {post_id} locked by another user (Lock UserID: {lock.user_id}, Current UserID: {user_id_to_auth}). SID: {request.sid}")
        if lock.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
            current_app.logger.info(f"SocketIO: '{func_name}' - Lock by other user on Post {post_id} has expired. SID: {request.sid}")
            emit('edit_error', {'message': 'Lock by other user expired. Try acquiring.'}, room=request.sid)
        else:
            emit('edit_error', {'message': 'Post locked by another user.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' due to lock mismatch. SID: {request.sid}")
        return

    if lock.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        current_app.logger.info(f"SocketIO: '{func_name}' - User's own lock on Post {post_id} has expired. Lock UserID: {lock.user_id}. SID: {request.sid}")
        current_app.logger.debug(f"SocketIO: '{func_name}' - Deleting expired lock for Post ID {post_id}. SID: {request.sid}")
        db.session.delete(lock)
        try:
            current_app.logger.debug(f"SocketIO: '{func_name}' - Committing deletion of expired lock for Post ID {post_id}. SID: {request.sid}")
            db.session.commit()
            current_app.logger.info(f"SocketIO: '{func_name}' - Expired lock deleted for Post ID {post_id}. Emitting 'post_lock_released'. SID: {request.sid}")
            socketio.emit("post_lock_released", {"post_id": post_id, "username": "System (Expired)"}, room=f"post_{post_id}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"SocketIO: '{func_name}' - Error deleting expired lock for Post {post_id}: {e}. SID: {request.sid}", exc_info=True)
        emit('edit_error', {'message': 'Your lock expired. Acquire new lock.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting '{func_name}' because user's lock expired. SID: {request.sid}")
        return

    current_app.logger.debug(f"SocketIO: '{func_name}' - Updating Post {post_id} content and last_edited timestamp. SID: {request.sid}")
    post.content = new_content
    post.last_edited = datetime.now(timezone.utc)
    try:
        current_app.logger.debug(f"SocketIO: '{func_name}' - Committing post update for Post ID {post_id}. SID: {request.sid}")
        db.session.commit()
        current_app.logger.info(f"SocketIO: '{func_name}' - User {user.username} (ID: {user_id_to_auth}) updated Post {post.id}. SID: {request.sid}")

        editor_username = user.username
        update_payload = {
            "post_id": post.id, "new_content": post.content, "last_edited": post.last_edited.isoformat(),
            "edited_by_user_id": user_id_to_auth,
            "edited_by_username": editor_username,
        }
        current_app.logger.debug(f"SocketIO: '{func_name}' - Emitting 'post_content_updated' with payload: {update_payload}. SID: {request.sid}")
        socketio.emit("post_content_updated", update_payload, room=f"post_{post.id}")
        current_app.logger.info(f"User {user_id_to_auth} updated post {post.id}. Broadcasted.") # This log seems redundant with the one above. Kept for now.
        emit('edit_success', {'message': 'Content updated.', "post_id": post.id}, room=request.sid)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"SocketIO: '{func_name}' - Error committing post update by user {user_id_to_auth} for post {post.id}: {e}. SID: {request.sid}", exc_info=True)
        emit('edit_error', {'message': 'Server error saving changes.'}, room=request.sid)
    current_app.logger.debug(f"SocketIO: Exiting '{func_name}'. SID: {request.sid}")


@socketio.on("connect", namespace="/")
def handle_connect():
    # Log function entry and initial request details
    current_app.logger.debug(
        f"SocketIO: Entering 'handle_connect'. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}, Namespace: {request.namespace}, "
        f"Headers: {dict(request.headers)}, Cookies: {request.cookies}"
    )

    user_to_auth_on_connect = None
    auth_method = "anonymous" # Default auth method

    auth_header = request.namespace.auth # or request.headers.get('Authorization') depending on client
    current_app.logger.debug(f"SocketIO: handle_connect - Auth header received: {auth_header}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")

    if auth_header and isinstance(auth_header, dict) and 'token' in auth_header:
        jwt_token = auth_header.get('token')
        # Log token before decoding
        current_app.logger.debug(f"SocketIO: handle_connect - JWT Auth: Attempting to decode token. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}, Token: {jwt_token[:20]}...")
        try:
            decoded_token = decode_token(jwt_token)
            # Log decoded token
            current_app.logger.debug(f"SocketIO: handle_connect - JWT Auth: Token decoded. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}, Decoded sub: {decoded_token.get('sub')}")

            user_identity = decoded_token.get('sub')
            if user_identity is None:
                current_app.logger.warning(f"SocketIO: JWT Auth - 'sub' claim missing in token. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Token: {decoded_token}")
                current_app.logger.debug(f"SocketIO: Emitting 'auth_error' due to missing 'sub' claim. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
                emit('auth_error', {'message': "Token is missing the 'sub' (subject) claim."}, room=request.sid)
                current_app.logger.debug(f"SocketIO: Exiting 'handle_connect' for SID {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Outcome: JWT Auth Error - Missing 'sub' claim. Returning False.")
                return False

            current_app.logger.debug(f"SocketIO: JWT Auth - User identity (sub): {user_identity}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")

            try:
                user_id = int(user_identity)
                current_app.logger.debug(f"SocketIO: JWT Auth - Parsed user_id: {user_id}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
            except ValueError:
                current_app.logger.warning(f"SocketIO: JWT Auth - Invalid user_id format '{user_identity}'. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
                current_app.logger.debug(f"SocketIO: Emitting 'auth_error' due to invalid user_id format. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
                emit('auth_error', {'message': 'Invalid user identifier format in token.'}, room=request.sid)
                current_app.logger.debug(f"SocketIO: Exiting 'handle_connect' for SID {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Outcome: JWT Auth Error - Invalid user_id format. Returning False.")
                return False

            # Log before DB query for JWT user
            current_app.logger.debug(f"SocketIO: JWT Auth - Attempting to fetch user from DB. User ID: {user_id}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
            jwt_user = db.session.get(User, user_id)
            current_app.logger.debug(f"SocketIO: handle_connect - JWT Auth: DB lookup for user ID {user_id}. User found: {bool(jwt_user)}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
            # Log result of DB query
            if jwt_user:
                current_app.logger.debug(f"SocketIO: JWT Auth - User fetched from DB: ID={jwt_user.id}, Username={jwt_user.username}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
                user_to_auth_on_connect = jwt_user
                auth_method = "jwt"
            else:
                current_app.logger.warning(f"SocketIO: JWT Auth - User ID '{user_id}' not found in DB. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
                current_app.logger.debug(f"SocketIO: Emitting 'auth_error' due to JWT user not found in DB. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
                emit('auth_error', {'message': 'User not found for provided token.'}, room=request.sid)
                current_app.logger.debug(f"SocketIO: Exiting 'handle_connect' for SID {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Outcome: JWT Auth Error - User not found. Returning False.")
                return False

        except ExpiredSignatureError as e:
            current_app.logger.warning(f"SocketIO: JWT Auth - Token expired. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Error: {type(e).__name__} - {e}")
            current_app.logger.debug(f"SocketIO: Emitting 'auth_error' due to ExpiredSignatureError. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
            emit('auth_error', {'message': 'Token has expired.'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: Exiting 'handle_connect' for SID {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Outcome: JWT Auth Error - ExpiredSignatureError. Returning False.")
            return False
        except InvalidTokenError as e:
            current_app.logger.warning(f"SocketIO: JWT Auth - Invalid token. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Error: {type(e).__name__} - {e}")
            current_app.logger.debug(f"SocketIO: Emitting 'auth_error' due to InvalidTokenError. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
            emit('auth_error', {'message': f'Invalid token supplied: {str(e)}'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: Exiting 'handle_connect' for SID {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Outcome: JWT Auth Error - InvalidTokenError. Returning False.")
            return False
        except Exception as e:
            current_app.logger.error(f"SocketIO: JWT Auth - Unexpected error during token processing. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Error: {type(e).__name__} - {e}", exc_info=True)
            current_app.logger.debug(f"SocketIO: Emitting 'auth_error' due to unexpected JWT exception. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
            emit('auth_error', {'message': 'An unexpected error occurred during authentication.'}, room=request.sid)
            current_app.logger.debug(f"SocketIO: Exiting 'handle_connect' for SID {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Outcome: JWT Auth Error - Unexpected Exception. Returning False.")
            return False
    else:
        current_app.logger.debug(f"SocketIO: No JWT in auth header or auth_header is not a dict, attempting session authentication. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")

    # Attempt session authentication if JWT auth was not attempted or failed (and didn't return)
    if not user_to_auth_on_connect:
        current_app.logger.debug(
            f"SocketIO: handle_connect - Session Auth: Checking current_user.is_authenticated ({current_user.is_authenticated}). SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}"
        )
        # Log session data - be careful with sensitive data in logs
        serializable_session = {k: v for k, v in session.items() if isinstance(v, (str, int, float, bool, list, dict))}
        current_app.logger.debug(f"SocketIO: Session Auth - Session contents: {serializable_session}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")

        if current_user.is_authenticated:
            user_to_auth_on_connect = current_user
            auth_method = "session_current_user"
            current_app.logger.debug(f"SocketIO: Session Auth - Authenticated via Flask-Login current_user: {current_user.username}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
        elif "_user_id" in session:
            user_id_from_session = session.get("_user_id")
            current_app.logger.debug(f"SocketIO: handle_connect - Session Auth: Checking session for _user_id ('{user_id_from_session}'). SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
            try:
                user_id = int(user_id_from_session)
                current_app.logger.debug(f"SocketIO: Session Auth - Attempting to fetch user from DB via session _user_id. User ID: {user_id}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
                session_user = db.session.get(User, user_id)
                current_app.logger.debug(f"SocketIO: handle_connect - Session Auth (from _user_id): DB lookup for user ID {user_id}. User found: {bool(session_user)}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
                if session_user:
                    current_app.logger.debug(f"SocketIO: Session Auth - User fetched from DB via _user_id: ID={session_user.id}, Username={session_user.username}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
                    user_to_auth_on_connect = session_user
                    auth_method = "session_underscore_user_id"
                else:
                    current_app.logger.warning(f"SocketIO: Session Auth - User ID '{user_id_from_session}' from session not found in DB. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
            except ValueError:
                current_app.logger.warning(f"SocketIO: Session Auth - Invalid _user_id format in session: '{user_id_from_session}'. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
            except Exception as e: # Catch potential errors from db.session.get or int conversion
                current_app.logger.error(f"SocketIO: Session Auth - Error processing _user_id from session. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Error: {type(e).__name__} - {e}", exc_info=True)


    if user_to_auth_on_connect:
        join_room(f"user_{user_to_auth_on_connect.id}")
        current_app.logger.info(
            f"SocketIO: handle_connect - User {user_to_auth_on_connect.username} (ID: {user_to_auth_on_connect.id}) connected via {auth_method}. Emitting 'confirm_namespace_connected'. "
            f"SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Joined room: user_{user_to_auth_on_connect.id}"
        )
        emit('confirm_namespace_connected', {
            'namespace': request.namespace, 'sid': request.sid, 'status': 'authenticated',
            'username': user_to_auth_on_connect.username, 'user_id': user_to_auth_on_connect.id,
            'auth_method': auth_method
        }, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting 'handle_connect' for SID {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Outcome: User {user_to_auth_on_connect.username} connected via {auth_method}.")
    else:
        current_app.logger.warning(f"SocketIO: handle_connect - Authentication failed. No JWT (via decorator), session user, or other method succeeded. Emitting 'auth_error'. Auth method at end: {auth_method}. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}, Auth Header provided: {bool(auth_header)}, CurrentUserAuthed: {current_user.is_authenticated}, SessionUserID: {session.get('_user_id')}")
        # Log reason for auth error before emitting
        current_app.logger.debug(f"SocketIO: Emitting 'auth_error' due to failed authentication. SID: {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}")
        emit('auth_error', {'message': 'Authentication required and failed.'}, room=request.sid)
        current_app.logger.debug(f"SocketIO: Exiting 'handle_connect' for SID {request.sid}, EIO_SID: {getattr(request, 'eio_sid', 'N/A')}. Outcome: Anonymous connection failed / Authentication required. Returning False.")
        return False # Explicitly return False for failed connection
