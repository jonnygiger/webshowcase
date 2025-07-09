import os
import sys
import unittest
import json
import io
import time
import threading
from unittest.mock import patch, call, ANY

from social_app import create_app, db as app_db, socketio as main_app_socketio
from flask import url_for, Response
import flask

from flask_jwt_extended import JWTManager
from flask_restful import Api

from social_app.models.db_models import (
    Achievement,
    Bookmark,
    Comment,
    Event,
    EventRSVP,
    FriendPostNotification,
    Friendship,
    Group,
    Like,
    Message,
    Notification,
    Poll,
    PollOption,
    PollVote,
    Post,
    PostLock,
    Series,
    SeriesPost,
    SharedFile,
    TrendingHashtag,
    User,
    UserAchievement,
    UserBlock,
    UserStatus,
)
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash


class AppTestCase(unittest.TestCase):
    app = None
    db = None
    socketio_class_level = None

    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.db = app_db
        cls.socketio_class_level = main_app_socketio

        import logging
        cls.app.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        for h_ in cls.app.logger.handlers:
            cls.app.logger.removeHandler(h_)
        cls.app.logger.addHandler(handler)
        cls.app.logger.propagate = False
        logging.getLogger("socketio").setLevel(logging.DEBUG)
        logging.getLogger("engineio").setLevel(logging.DEBUG)

        with cls.app.app_context():
            cls.db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.db.drop_all()

    def setUp(self):
        """
        Set up the test environment before each test case.
        Initializes the Flask test client and a Flask-SocketIO test client.
        It also ensures that the SocketIO client is in a clean state by:
        1. Checking if an implicit connection exists upon client creation.
        2. If so, disconnecting it.
        3. Attempting to clear any residual events from its queue. This is
           important because the test client might retain events from previous
           interactions or states if not properly cleared.
        Finally, it cleans all database tables and sets up base users.
        """
        self.client = self.app.test_client()
        assert (
            self.socketio_class_level is not None
        ), "socketio_class_level is None in setUp instance method!"

        # Initialize the SocketIO test client for this test instance
        self.socketio_client = self.socketio_class_level.test_client(
            self.app, flask_test_client=self.client
        )

        # Handle and clear any implicit connection or residual events
        if self.socketio_client.is_connected(namespace="/"):
            self.app.logger.debug("Implicit SocketIO connection found on new client in setUp. Disconnecting.")
            self.socketio_client.disconnect(namespace="/")
            time.sleep(0.1) # Short pause to allow disconnect to process on server/client side

            # Attempt to clear any events that might have been queued due to the implicit connection
            # or from a previous test's state if the client wasn't perfectly reset.
            self.app.logger.debug("Attempting to clear residual events from SocketIO client in setUp.")
            cleared_event_count = 0
            for i in range(5): # Try up to 5 times to clear
                if not self.socketio_client.is_connected(namespace="/"):
                    # If disconnect happened during server processing or due to an error, stop.
                    self.app.logger.debug("SocketIO client became disconnected during event clearing loop in setUp.")
                    break
                try:
                    events = self.socketio_client.get_received(namespace="/")
                    if not events:
                        self.app.logger.debug(f"SocketIO event queue cleared in setUp after {i+1} attempts.")
                        break
                    cleared_event_count += len(events)
                    self.app.logger.debug(f"Drained {len(events)} events in setUp (attempt {i+1}/5). Total drained so far: {cleared_event_count}.")
                    time.sleep(0.05) # Brief pause to allow event queue to be processed
                except RuntimeError: # Can occur if get_received is called on a fully closed client
                    self.app.logger.debug("SocketIO client reported RuntimeError (likely fully disconnected) during event clearing in setUp.")
                    break
            else: # Executed if the loop completes without a 'break'
                # This means events might still be present or client is still connected.
                if self.socketio_client.is_connected(namespace="/"):
                     self.app.logger.warning(f"SocketIO client event queue in setUp might still have events after 5 clearing attempts (client still connected). Drained {cleared_event_count} events.")
                else:
                     self.app.logger.info(f"SocketIO client event clearing loop in setUp finished; client was or became disconnected. Drained {cleared_event_count} events.")

        # Prepare database: clean tables and set up base users
        with self.app.app_context():
            self._clean_tables_for_setup()
            self._setup_base_users()

    def _clean_tables_for_setup(self):
        self.db.session.remove()
        for table in reversed(self.db.metadata.sorted_tables):
            self.db.session.execute(table.delete())
        self.db.session.commit()

    def tearDown(self):
        """
        Clean up the test environment after each test case.
        Ensures the SocketIO client is disconnected.
        Rolls back any pending database transactions and removes the session.
        Deletes any files created in the shared files upload folder during tests.
        """
        # Ensure the primary SocketIO test client is disconnected
        if hasattr(self, "socketio_client") and self.socketio_client:
            client_sid = getattr(self.socketio_client, "sid", "N/A") # Get SID for logging before potential disconnect
            if self.socketio_client.is_connected():
                self.app.logger.debug(f"Disconnecting main Flask-SocketIO test_client (SID: {client_sid}) in tearDown.")
                self.socketio_client.disconnect()
                # A brief pause can be helpful for the server to fully process the disconnection,
                # preventing potential state carry-over if tests run very quickly.
                time.sleep(0.05)
                if self.socketio_client.is_connected(): # Check if disconnect was successful
                    self.app.logger.warning(f"Main Flask-SocketIO test_client (SID: {client_sid}) still reported as connected after disconnect call in tearDown.")
                else:
                    self.app.logger.debug(f"Main Flask-SocketIO test_client (SID: {client_sid}) successfully disconnected in tearDown.")
            else:
                self.app.logger.debug(f"Main Flask-SocketIO test_client (SID: {client_sid}) in tearDown was already disconnected.")
        else:
            self.app.logger.debug("No 'socketio_client' attribute found or it was None in tearDown.")

        # Clean up database session
        with self.app.app_context():
            self.db.session.rollback() # Rollback any uncommitted transactions
            self.db.session.remove()

        shared_files_folder = self.app.config.get("SHARED_FILES_UPLOAD_FOLDER")
        if shared_files_folder and os.path.exists(shared_files_folder):
            for filename in os.listdir(shared_files_folder):
                file_path = os.path.join(shared_files_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    self.app.logger.error(f"Failed to delete {file_path} in tearDown. Reason: {e}")

    def _setup_base_users(self):
        self.user1 = User(
            username="testuser1",
            email="test1@example.com",
            password_hash=generate_password_hash("password"),
        )
        self.user2 = User(
            username="testuser2",
            email="test2@example.com",
            password_hash=generate_password_hash("password"),
        )
        self.user3 = User(
            username="testuser3",
            email="test3@example.com",
            password_hash=generate_password_hash("password"),
        )
        self.db.session.add_all([self.user1, self.user2, self.user3])
        self.db.session.commit()
        self.db.session.refresh(self.user1)
        self.db.session.refresh(self.user2)
        self.db.session.refresh(self.user3)
        self.user1_id = self.user1.id
        self.user2_id = self.user2.id
        self.user3_id = self.user3.id

    def _ensure_socketio_disconnected(self, client, client_name_for_log="client", namespace="/", timeout=2, sleep_interval=0.05):
        """
        Ensures a SocketIO client is disconnected from a given namespace.
        It first checks if the client is connected. If so, it calls disconnect
        and then polls `is_connected()` until it returns False or a timeout occurs.

        Args:
            client: The SocketIO test client instance.
            client_name_for_log (str): A descriptive name for the client for logging.
            namespace (str): The namespace to check and disconnect from.
            timeout (float): Maximum time in seconds to wait for disconnection.
            sleep_interval (float): Time in seconds to sleep between connection checks.

        Returns:
            bool: True if the client is disconnected, False if it timed out.
        """
        if not client.is_connected(namespace=namespace):
            self.app.logger.debug(f"SocketIO {client_name_for_log} already disconnected from namespace '{namespace}'.")
            return True

        self.app.logger.debug(f"SocketIO {client_name_for_log} is connected to '{namespace}'. Attempting disconnect.")
        client.disconnect(namespace=namespace)

        # Poll for disconnection
        start_time = time.time()
        while client.is_connected(namespace=namespace):
            if time.time() - start_time > timeout:
                self.app.logger.warning(
                    f"SocketIO {client_name_for_log} still connected to namespace '{namespace}' after {timeout}s timeout post-disconnect call."
                )
                return False
            time.sleep(sleep_interval) # Wait before next check

        self.app.logger.debug(f"SocketIO {client_name_for_log} successfully disconnected from namespace '{namespace}'.")
        return True

    def _clear_socketio_events(self, client, client_name_for_log="client", namespace="/", attempts=5, sleep_interval=0.01):
        """
        Clears any pending events from the SocketIO client's internal queue for a namespace.
        This is useful to ensure a clean state before performing actions that expect specific events.
        The Flask-SocketIO test client might retain events even after a disconnect/reconnect cycle.

        Args:
            client: The SocketIO test client instance.
            client_name_for_log (str): A descriptive name for the client for logging.
            namespace (str): The namespace from which to clear events.
            attempts (int): Max number of times to try getting events.
            sleep_interval (float): Time to sleep between attempts to allow event processing.

        Returns:
            int: The total number of events cleared.
        """
        self.app.logger.debug(f"SocketIO {client_name_for_log}: Starting event clearing for namespace '{namespace}'.")
        cleared_in_total = 0
        for i in range(attempts):
            # If client becomes disconnected (e.g., due to server-side action or error), stop trying.
            if not client.is_connected(namespace=namespace):
                self.app.logger.debug(f"SocketIO {client_name_for_log}: Client disconnected during event clearing (attempt {i+1}/{attempts}) for '{namespace}'.")
                break
            try:
                events = client.get_received(namespace=namespace) # Non-blocking if empty
                if not events:
                    # If no events received for a couple of tries, assume queue is clear.
                    # This avoids waiting unnecessarily for all attempts if queue empties quickly.
                    if i > 1:
                        self.app.logger.debug(f"SocketIO {client_name_for_log}: Event queue for '{namespace}' appears empty after {i+1} attempts (no recent events).")
                        break
                else:
                    cleared_in_total += len(events)
                    self.app.logger.debug(f"SocketIO {client_name_for_log}: Drained {len(events)} events on attempt {i+1}/{attempts} for '{namespace}'. Total: {cleared_in_total}.")
                time.sleep(sleep_interval) # Short pause to allow event loop to cycle
            except RuntimeError as e: # Can happen if client is forcefully closed
                self.app.logger.warning(f"SocketIO {client_name_for_log}: Error '{e}' during event clearing (attempt {i+1}) for '{namespace}'. Stopping.")
                break

        if cleared_in_total > 0:
            self.app.logger.info(f"SocketIO {client_name_for_log}: Drained a total of {cleared_in_total} pre-existing events from namespace '{namespace}'.")
        else:
            self.app.logger.info(f"SocketIO {client_name_for_log}: No pre-existing events were drained from namespace '{namespace}'.")
        self.app.logger.debug(f"SocketIO {client_name_for_log}: Finished event clearing for namespace '{namespace}'.")
        return cleared_in_total

    def login(self, username, password, client_instance=None):
        """
        Handles the complete login process for a user, including HTTP session login
        and SocketIO connection authentication.

        Args:
            username (str): The username to log in with.
            password (str): The password for the user.
            client_instance (SocketIOTestClient, optional): The specific SocketIO client
                instance to use. If None, `self.socketio_client` is used.

        Returns:
            flask.Response: The response object from the initial HTTP POST to /login.

        Raises:
            ConnectionError: If SocketIO authentication fails or times out.
            AssertionError: If HTTP login fails or JWT token is not retrieved.
        """
        # Step 1: Perform standard HTTP form login to establish a Flask session.
        # This is necessary for routes protected by traditional session-based auth.
        self.app.logger.info(f"Initiating HTTP login for user '{username}'.")
        login_response = self.client.post(
            "/login",
            data=dict(username=username, password=password),
            follow_redirects=True,
        )
        self.assertEqual(login_response.status_code, 200, f"HTTP login failed for '{username}': {login_response.data.decode()}")
        with self.client.session_transaction() as http_session: # Verify Flask session
            self.assertIn("_user_id", http_session, f"'_user_id' not found in session after HTTP login for '{username}'.")
        self.app.logger.info(f"HTTP login successful for '{username}', Flask session created.")

        # Step 2: Obtain a JWT token for SocketIO authentication.
        # This typically involves a separate API endpoint.
        self.app.logger.debug(f"Fetching JWT token for '{username}'.")
        jwt_token = self._get_jwt_token(username, password)

        # Determine which SocketIO client to use (default or a specific instance)
        socketio_client_to_use = client_instance if client_instance else self.socketio_client
        client_log_name = f"SocketIO client for '{username}'" # For logging context

        # Step 3: Prepare the SocketIO client for a new connection.
        # This involves ensuring it's disconnected and its event queue is clear.
        self.app.logger.info(f"{client_log_name}: Preparing for new connection attempt.")
        self._ensure_socketio_disconnected(socketio_client_to_use, client_log_name)

        # Even after a disconnect, the test client might retain events in its internal queue.
        # Clearing them helps prevent interference from stale events from previous operations.
        self._clear_socketio_events(socketio_client_to_use, client_log_name)

        # Step 4: Connect the SocketIO client using the obtained JWT token for authentication.
        self.app.logger.info(f"{client_log_name}: Attempting to connect and authenticate with JWT token.")
        socketio_client_to_use.connect(
            namespace="/", # Assuming connection to the default namespace
            auth={'token': jwt_token},
            headers={'Authorization': f'Bearer {jwt_token}'} # Common practice for JWT
        )

        # Capture the Session ID (SID) immediately after connect. This SID is crucial for
        # associating subsequent events (like auth confirmation) with THIS connection attempt.
        current_connection_sid = socketio_client_to_use.sid
        if not current_connection_sid:
             # This is unexpected if connect() did not raise an error.
             self.app.logger.error(f"{client_log_name}: Connection initiated but SID is immediately unavailable.")
             raise ConnectionError(f"SocketIO connection for '{username}' failed: SID not available post-connect call.")
        self.app.logger.info(f"{client_log_name}: Connection request sent, assigned SID: {current_connection_sid}. Awaiting authentication confirmation event.")

        # Step 5: Wait for authentication confirmation events from the server.
        # The server should emit an event (e.g., 'confirm_namespace_connected' or 'auth_error')
        # indicating the success or failure of the token-based authentication.
        auth_successful = False
        auth_error_message = None
        confirm_event_timeout = 10  # Max seconds to wait for auth event
        event_wait_start_time = time.time()

        while time.time() - event_wait_start_time < confirm_event_timeout:
            # Check if client disconnected prematurely (e.g., server rejected connection immediately)
            if not socketio_client_to_use.is_connected(namespace="/"):
                self.app.logger.error(f"{client_log_name} (SID: {current_connection_sid}): Disconnected while awaiting authentication confirmation.")
                auth_error_message = "Client disconnected prematurely while awaiting authentication confirmation."
                break
            try:
                # get_received() is non-blocking if the queue is empty for the test client.
                received_events = socketio_client_to_use.get_received(namespace="/")
                for event in received_events:
                    event_name = event.get('name')
                    event_args = event.get('args') # Usually a list with one dict element
                    self.app.logger.debug(f"{client_log_name} (SID: {current_connection_sid}): Event received: Name: '{event_name}', Args: {event_args}")

                    # Critical: Filter events based on SID. Ensures the event is for THIS connection attempt.
                    # Assumes the server includes the client's SID in the auth-related event payload.
                    payload_sid = event_args[0].get('sid') if event_args and isinstance(event_args, list) and len(event_args) > 0 and isinstance(event_args[0], dict) else None

                    if payload_sid != current_connection_sid:
                        self.app.logger.warning(
                            f"{client_log_name}: Received event for SID '{payload_sid}' but expecting SID '{current_connection_sid}'. "
                            f"Event Name: '{event_name}'. Args: {event_args}. Skipping."
                        )
                        continue # Not for us, or SID missing in payload

                    # Process relevant authentication events
                    if event_name == 'confirm_namespace_connected':
                        if event_args and event_args[0].get('status') == 'authenticated':
                            self.app.logger.info(f"{client_log_name} (SID: {current_connection_sid}): Authentication successful ('confirm_namespace_connected' received).")
                            auth_successful = True
                            break # Exit event processing loop
                        elif event_args: # confirm_namespace_connected but status is not 'authenticated'
                            status = event_args[0].get('status', 'N/A')
                            self.app.logger.error(f"{client_log_name} (SID: {current_connection_sid}): Namespace connected but status was '{status}'.")
                            auth_error_message = f"Namespace connected with unauthenticated status: '{status}'"
                            break # Exit event processing loop
                    elif event_name == 'auth_error':
                        raw_error_detail = event_args[0].get('message', str(event_args[0])) if event_args and event_args[0] else "Unknown auth error"
                        self.app.logger.error(f"{client_log_name} (SID: {current_connection_sid}): Authentication failed ('auth_error' received): {raw_error_detail}.")
                        auth_error_message = raw_error_detail
                        break # Exit event processing loop

                if auth_successful or auth_error_message:
                    break # Exit the while loop for waiting
            except RuntimeError as e: # Can happen if get_received is called on a catastrophically failed client
                self.app.logger.error(f"{client_log_name} (SID: {current_connection_sid}): Runtime error while polling for events: {e}. Assuming disconnection.")
                auth_error_message = f"Runtime error during event polling: {e}"
                break # Exit while loop
            time.sleep(0.05) # Brief pause to prevent busy-looping, allows other threads to run

        # Step 6: Finalize login status based on authentication events.
        final_sid = getattr(socketio_client_to_use, "sid", None) # Re-check SID, in case of very quick transparent reconnect

        if auth_error_message: # If any explicit error was captured
            # Ensure client is disconnected if an error occurred during auth.
            if socketio_client_to_use.is_connected(namespace="/"):
                 self.app.logger.debug(f"{client_log_name} (Last SID: {final_sid or current_connection_sid}): Disconnecting due to auth error: {auth_error_message}")
                 self._ensure_socketio_disconnected(socketio_client_to_use, client_log_name, timeout=1) # Quick disconnect attempt
            raise ConnectionError(f"SocketIO authentication failed for '{username}' (Attempted SID: {current_connection_sid}): {auth_error_message}")

        if not auth_successful: # If loop timed out without explicit success or error
            eio_sid_val = "N/A" # For debugging, engineio SID might be informative
            if hasattr(socketio_client_to_use, 'eio_test_client') and socketio_client_to_use.eio_test_client:
                eio_sid_val = getattr(socketio_client_to_use.eio_test_client, 'sid', "N/A (eio_test_client has no sid)")
            is_connected_status = socketio_client_to_use.is_connected(namespace="/")

            if is_connected_status: # If timed out but still connected, disconnect it.
                 self.app.logger.debug(f"{client_log_name} (SID: {final_sid or current_connection_sid}): Disconnecting due to auth event timeout.")
                 self._ensure_socketio_disconnected(socketio_client_to_use, client_log_name, timeout=1)

            error_message = (
                f"SocketIO connection for '{username}' (Attempted SID: {current_connection_sid}) timed out after {confirm_event_timeout}s "
                f"waiting for authentication confirmation ('confirm_namespace_connected' or 'auth_error'). "
                f"Final state - is_connected: {is_connected_status}, final_sid: {final_sid}, eio_sid: {eio_sid_val}."
            )
            self.app.logger.error(error_message)
            raise ConnectionError(error_message)

        if not final_sid:
            # This would mean client disconnected AFTER successful auth event but before this check.
            # This is unusual but possible if server immediately disconnects post-auth.
            error_message = (
                f"SocketIO client for '{username}' (Initial SID: {current_connection_sid}) authenticated but current SID is now missing. "
                "Client may have disconnected immediately after authentication."
            )
            self.app.logger.error(error_message)
            # Depending on strictness, this could be an error or a warning.
            # For now, let's assume if auth_successful was true, it's a transient state.
            # raise ConnectionError(error_message) # Uncomment if this should be a hard failure

        if final_sid != current_connection_sid:
            # This is highly unusual: SID changed after successful authentication for the original SID,
            # without an explicit disconnect/reconnect cycle handled by this login logic.
            # Could indicate a transparent reconnect by the underlying client library.
            self.app.logger.warning(
                f"{client_log_name}: SID mismatch after authentication. Initial SID: {current_connection_sid}, Final SID: {final_sid}. "
                "Connection considered successful for initial SID, but this may indicate unexpected client behavior."
            )
            # Not raising an error, as 'confirm_namespace_connected' was for 'current_connection_sid'.
            # The current connection (new SID) might not be the one we expect to use going forward.
            # This might require further investigation if it occurs frequently.

        self.app.logger.info(f"{client_log_name} (Authenticated SID: {current_connection_sid}, Final/Current SID: {final_sid}): SocketIO login and authentication successful.")
        return login_response

    def logout(self, client_instance=None, username_for_log=None):
        """
        Logs out the user by clearing the HTTP session and disconnecting the SocketIO client.

        Args:
            client_instance (SocketIOTestClient, optional): The specific SocketIO client
                             instance to disconnect. If None, `self.socketio_client` is used.
            username_for_log (str, optional): An optional username string to make log
                                              messages more descriptive.
        Returns:
            flask.Response: The response object from the HTTP GET request to /logout.
        """
        http_client = self.client # Standard Flask test client
        socket_client_to_use = (
            client_instance
            if client_instance
            else getattr(self, "socketio_client", None) # Default to self.socketio_client
        )

        # Determine a descriptive name for the SocketIO client for logging purposes
        client_log_name = "SocketIO client"
        if username_for_log:
            client_log_name = f"SocketIO client for '{username_for_log}'"
        elif socket_client_to_use == self.socketio_client: # Check if it's the default instance
            client_log_name = "default self.socketio_client"
        elif client_instance is not None: # If a specific instance was passed
            client_log_name = "provided client_instance"
        # Else, it remains "SocketIO client" if socket_client_to_use is None or not self.socketio_client

        # Step 1: Disconnect the SocketIO client, if it exists and is connected.
        if socket_client_to_use and hasattr(socket_client_to_use, "is_connected"):
            self.app.logger.info(f"Logout process: Attempting to disconnect {client_log_name}.")
            # Use the robust disconnect helper. Timeout can be short as logout disconnections are usually quick.
            self._ensure_socketio_disconnected(socket_client_to_use, client_log_name, timeout=1.0)
            # Event clearing is usually not necessary on logout, as the client is being discarded or will be
            # re-initialized/re-authenticated for any subsequent use.
            # self._clear_socketio_events(socket_client_to_use, client_log_name)
        else:
            self.app.logger.debug(f"Logout process: {client_log_name} not found, is None, or not a valid client object. Skipping SocketIO disconnect.")

        # Step 2: Perform HTTP session logout.
        user_context_log = f"for '{username_for_log}'" if username_for_log else "for current user"
        self.app.logger.info(f"Logout process: Performing HTTP session logout {user_context_log}.")
        response = http_client.get("/logout", follow_redirects=True) # Standard Flask logout
        self.assertEqual(response.status_code, 200, f"HTTP Logout failed {user_context_log}: {response.data.decode()}")
        self.app.logger.info(f"HTTP session logout successful {user_context_log}.")

        # Step 3: Verify that the Flask session is actually cleared.
        # This is an important check for the integrity of the logout process.
        with http_client.session_transaction() as http_session:
            if "_user_id" in http_session: # '_user_id' is commonly used by Flask-Login
                self.app.logger.warning(f"Session check: '_user_id' still found in session after HTTP logout {user_context_log}. This might indicate an issue with server-side session clearing.")
            else:
                self.app.logger.debug(f"Session check: '_user_id' confirmed removed after HTTP logout {user_context_log}.")

        return response

    def _create_db_message(
        self, sender_id, receiver_id, content, timestamp=None, is_read=False
    ):
        with self.app.app_context():
            msg = Message(
                sender_id=sender_id,
                receiver_id=receiver_id,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
                is_read=is_read,
            )
            self.db.session.add(msg)
            self.db.session.commit()
            return msg

    def _get_jwt_token(self, username, password):
        with self.app.app_context():
            response = self.client.post(
                "/api/login", json={"username": username, "password": password}
            )
        self.assertEqual(
            response.status_code,
            200,
            f"Login failed for token generation: {response.data.decode()}",
        )
        data = json.loads(response.data)
        self.assertIn("access_token", data, "Access token not found in login response.")
        return data["access_token"]

    def create_dummy_file(
        self, filename="test.txt", content=b"hello world", content_type="text/plain"
    ):
        return (io.BytesIO(content), filename, content_type)

    def _create_db_group(
        self, creator_id, name="Test Group", description="A group for testing"
    ):
        with self.app.app_context():
            group = Group(name=name, description=description, creator_id=creator_id)
            self.db.session.add(group)
            self.db.session.commit()
            return self.db.session.get(Group, group.id)

    def _create_db_event(
        self,
        user_id,
        title="Test Event",
        description="An event for testing",
        date_str="2024-12-31",
        time_str="18:00",
        location="Test Location",
        created_at=None,
    ):
        with self.app.app_context():
            event_datetime_obj = datetime.strptime(
                f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
            )
            event = Event(
                user_id=user_id,
                title=title,
                description=description,
                date=event_datetime_obj,
                location=location,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(event)
            self.db.session.commit()
            return self.db.session.get(Event, event.id)

    def _create_db_poll(
        self, user_id, question="Test Poll?", options_texts=None, created_at=None
    ):
        if options_texts is None:
            options_texts = ["Option 1", "Option 2"]
        with self.app.app_context():
            poll = Poll(
                user_id=user_id,
                question=question,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(poll)
            self.db.session.commit()
            for text in options_texts:
                option = PollOption(text=text, poll_id=poll.id)
                self.db.session.add(option)
            self.db.session.commit()
            return self.db.session.get(Poll, poll.id)

    def _create_db_post(
        self, user_id, title="Test Post", content="Test Content", timestamp=None
    ):
        with self.app.app_context():
            post = Post(
                user_id=user_id,
                title=title,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(post)
            self.db.session.commit()
            return self.db.session.get(Post, post.id)

    def _create_db_like(self, user_id, post_id, timestamp=None):
        with self.app.app_context():
            like = Like(
                user_id=user_id,
                post_id=post_id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(like)
            self.db.session.commit()
            return like

    def _create_db_comment(
        self, user_id, post_id, content="Test comment", timestamp=None
    ):
        with self.app.app_context():
            comment = Comment(
                user_id=user_id,
                post_id=post_id,
                content=content,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(comment)
            self.db.session.commit()
            return comment

    def _create_db_event_rsvp(
        self, user_id, event_id, status="Attending", timestamp=None
    ):
        with self.app.app_context():
            rsvp = EventRSVP(
                user_id=user_id,
                event_id=event_id,
                status=status,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(rsvp)
            self.db.session.commit()
            return rsvp.id

    def _create_db_poll_vote(self, user_id, poll_id, poll_option_id, created_at=None):
        with self.app.app_context():
            vote = PollVote(
                user_id=user_id,
                poll_id=poll_id,
                poll_option_id=poll_option_id,
                created_at=created_at or datetime.now(timezone.utc),
            )
            self.db.session.add(vote)
            self.db.session.commit()
            return vote.id

    def _create_series(
        self,
        user_id,
        title="Test Series",
        description="A series for testing.",
        created_at=None,
        updated_at=None,
    ):
        with self.app.app_context():
            series = Series(
                user_id=user_id,
                title=title,
                description=description,
                created_at=created_at or datetime.now(timezone.utc),
                updated_at=updated_at or datetime.now(timezone.utc),
            )
            self.db.session.add(series)
            self.db.session.commit()
            return self.db.session.get(Series, series.id)

    def assertInHTML(self, needle, haystack, achievement_name):
        try:
            ach_name_idx = haystack.find(achievement_name)
            self.assertTrue(
                ach_name_idx != -1,
                f"Achievement name '{achievement_name}' not found in HTML.",
            )
            search_range = haystack[ach_name_idx : ach_name_idx + 300]
            self.assertIn(
                needle,
                search_range,
                f"'{needle}' not found near '{achievement_name}' in HTML: {search_range[:200]}...",
            )
        except AttributeError:
            self.fail("Haystack for assertInHTML was not a string.")

    def _create_db_lock(self, post_id, user_id, minutes_offset=0):
        with self.app.app_context():
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes_offset)
            lock = PostLock(post_id=post_id, user_id=user_id, expires_at=expires_at)
            self.db.session.add(lock)
            self.db.session.commit()
            return self.db.session.get(PostLock, lock.id)

    def _create_db_user(self, username, password="password", email=None, role="user"):
        if email is None:
            email = f"{username}@example.com"
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
        )
        self.db.session.add(user)
        self.db.session.commit()
        self.db.session.refresh(user)
        return user

    def _create_db_series(
        self,
        user_id,
        title="Test Series",
        description="A series for testing.",
        created_at=None,
        updated_at=None,
    ):
        with self.app.app_context():
            series = Series(
                user_id=user_id,
                title=title,
                description=description,
                created_at=created_at or datetime.now(timezone.utc),
                updated_at=updated_at or datetime.now(timezone.utc),
            )
            self.db.session.add(series)
            self.db.session.commit()
            return self.db.session.get(Series, series.id)

    def _create_db_bookmark(self, user_id, post_id, timestamp=None):
        with self.app.app_context():
            bookmark = Bookmark(
                user_id=user_id,
                post_id=post_id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(bookmark)
            self.db.session.commit()
            return bookmark

    def _create_db_block(self, blocker_user_obj, blocked_user_obj, timestamp=None):
        with self.app.app_context():
            block = UserBlock(
                blocker_id=blocker_user_obj.id,
                blocked_id=blocked_user_obj.id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(block)
            self.db.session.commit()
            return block.id

    def _create_db_friendship(
        self, user_obj_1, user_obj_2, status="accepted", timestamp=None
    ):
        with self.app.app_context():
            friendship = Friendship(
                user_id=user_obj_1.id,
                friend_id=user_obj_2.id,
                status=status,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            self.db.session.add(friendship)
            self.db.session.commit()
            self.db.session.refresh(friendship)
            return friendship

    def _remove_db_friendship(self, user_obj_1, user_obj_2):
        with self.app.app_context():
            friendship = Friendship.query.filter(
                (
                    (Friendship.user_id == user_obj_1.id)
                    & (Friendship.friend_id == user_obj_2.id)
                )
                | (
                    (Friendship.user_id == user_obj_2.id)
                    & (Friendship.friend_id == user_obj_1.id)
                )
            ).first()
            if friendship:
                self.db.session.delete(friendship)
                self.db.session.commit()
