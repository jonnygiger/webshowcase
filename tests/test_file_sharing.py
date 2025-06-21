import unittest
import os
import io

# Removed json (wasn't used)
from unittest.mock import patch, ANY  # Kept patch, ANY for now, though not visibly used
from datetime import datetime  # Removed timedelta

# from app import app, db, socketio # COMMENTED OUT
from models import User, SharedFile # COMMENTED OUT - Actually, uncommenting this
from tests.test_base import AppTestCase


class TestFileSharing(AppTestCase):
    # create_dummy_file is already in AppTestCase (tests/test_base.py)

    def test_share_file_get_page(self):
        # with app.app_context(): # Handled by test client
        self.login(self.user1.username, "password")
        response = self.client.get(f"/files/share/{self.user2.username}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f"Share File with {self.user2.username}", response.get_data(as_text=True)
        )
        self.logout()

    def test_share_file_successful_upload(self):
        # with app.app_context():
        self.login(self.user1.username, "password")
        dummy_file_data = self.create_dummy_file(
            filename="upload_test.txt", content=b"Test file content for upload."
        )

        data = {
            "file": dummy_file_data,
            "message": "This is a test message for the shared file.",
        }
        # This test requires app.config['SHARED_FILES_UPLOAD_FOLDER'] to be set
        # and SharedFile model + db to be live.
        response = self.client.post(f'/files/share/{self.user2.username}', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("File successfully shared!", response.get_data(as_text=True))

        # Query for the SharedFile record
        # Note: using self.user1.id and self.user2.id as per AppTestCase setup
        shared_file_record = SharedFile.query.filter_by(sender_id=self.user1.id, receiver_id=self.user2.id).first()
        self.assertIsNotNone(shared_file_record)
        self.assertEqual(shared_file_record.original_filename, "upload_test.txt")
        self.assertEqual(shared_file_record.message, "This is a test message for the shared file.")
        self.assertEqual(shared_file_record.sender_id, self.user1.id)
        self.assertEqual(shared_file_record.receiver_id, self.user2.id)

        # Verify the file exists in the shared files folder
        shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
        expected_file_path = os.path.join(shared_folder, shared_file_record.saved_filename)
        self.assertTrue(os.path.exists(expected_file_path))

        self.logout()

    def test_share_file_invalid_file_type(self):
        # with app.app_context():
        self.login(self.user1.username, "password")
        dummy_file_data = self.create_dummy_file(
            filename="test.exe",
            content=b"executable content",
            content_type="application/octet-stream",
        )
        data = {"file": dummy_file_data}
        response = self.client.post(f'/files/share/{self.user2.username}', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("File type not allowed", response.get_data(as_text=True))

        shared_file_record = SharedFile.query.filter_by(original_filename="test.exe").first()
        self.assertIsNone(shared_file_record)

        # Verify that no file was saved to the shared folder
        shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
        files_in_shared_folder = os.listdir(shared_folder)
        # Filter out potential .gitkeep or other persistent files if any
        relevant_files = [f for f in files_in_shared_folder if not f.startswith('.')]
        self.assertEqual(len(relevant_files), 0, "No file should have been saved to the shared folder for a disallowed type.")

        self.logout()

    def test_share_file_too_large(self):
        # with app.app_context():
        original_max_size = self.app.config.get('SHARED_FILES_MAX_SIZE')
        self.login(self.user1.username, "password")
        try:
            self.app.config['SHARED_FILES_MAX_SIZE'] = 10  # 10 bytes
            dummy_file_data = self.create_dummy_file(
                filename="large_file.txt",
                content=b"This content is definitely larger than 10 bytes.",
            )
            data = {"file": dummy_file_data}
            response = self.client.post(f'/files/share/{self.user2.username}', data=data, content_type='multipart/form-data', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("File is too large", response.get_data(as_text=True))

            shared_file_record = SharedFile.query.filter_by(original_filename="large_file.txt").first()
            self.assertIsNone(shared_file_record)

            # Verify that no file was saved to the shared folder
            shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
            files_in_shared_folder = os.listdir(shared_folder)
            relevant_files = [f for f in files_in_shared_folder if not f.startswith('.')]
            self.assertEqual(len(relevant_files), 0, "No file should have been saved for a too-large file.")

            self.logout()
        finally:
            # Restore original max size
            if original_max_size is not None:
                self.app.config['SHARED_FILES_MAX_SIZE'] = original_max_size
            else:
                # If it was None, and we set it, we might want to remove it.
                # However, app.py should set an initial value, so this case is unlikely.
                # For now, if it was None, we don't try to set it back to None,
                # we assume it should have had a value.
                # A more robust approach might be to check if 'SHARED_FILES_MAX_SIZE' was in self.app.config
                # before .get, and if not, del it in finally if we added it.
                # Given app.py sets it, this should be fine.
                pass

    def test_files_inbox_empty(self):
        # with app.app_context():
        self.login(self.user2.username, "password")
        response = self.client.get("/files/inbox")
        self.assertEqual(response.status_code, 200)
        self.assertIn("You have not received any files.", response.get_data(as_text=True)) # Checked template
        self.logout()

    def test_files_inbox_with_files(self):
        # Part 1: user1 shares a file with user2
        self.login(self.user1.username, 'password')
        dummy_file_data = self.create_dummy_file(filename="inbox_test_file.txt", content=b"Content for inbox.")
        share_data = {
            'file': dummy_file_data,
            'message': 'Hi! This is for your inbox.'
        }
        response_share = self.client.post(
            f'/files/share/{self.user2.username}',
            data=share_data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        self.assertEqual(response_share.status_code, 200)
        self.assertIn("File successfully shared!", response_share.get_data(as_text=True))
        self.logout()

        # Part 2: user2 logs in and checks inbox
        self.login(self.user2.username, "password")
        response_inbox = self.client.get("/files/inbox")
        self.assertEqual(response_inbox.status_code, 200)

        response_data_text = response_inbox.get_data(as_text=True)
        self.assertIn("inbox_test_file.txt", response_data_text)
        self.assertIn(self.user1.username, response_data_text) # Check for sender's username
        self.assertIn("Hi! This is for your inbox.", response_data_text) # Check for the message

        self.logout()

    def test_download_shared_file_receiver(self):
        # with app.app_context():
        # self.login(self.user1.username, 'password')
        # dummy_file_data = self.create_dummy_file(filename="download_me.txt", content=b"Downloadable content.")
        # self.client.post(f'/files/share/{self.user2.username}', data={'file': dummy_file_data}, content_type='multipart/form-data')
        # shared_file = SharedFile.query.filter_by(original_filename="download_me.txt").first()
        # Part 1: User1 shares the file
        self.login(self.user1.username, 'password')
        original_content = b"Downloadable content for receiver."
        dummy_file_data = self.create_dummy_file(filename="download_me.txt", content=original_content)
        share_data = {'file': dummy_file_data, 'message': 'File to download'}
        self.client.post(
            f'/files/share/{self.user2.username}',
            data=share_data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        self.logout()

        # Part 2: Retrieve SharedFile ID
        shared_file = SharedFile.query.filter_by(
            sender_id=self.user1.id,
            receiver_id=self.user2.id,
            original_filename="download_me.txt"
        ).first()
        self.assertIsNotNone(shared_file, "Shared file record should exist in DB.")
        self.assertFalse(shared_file.is_read, "File should initially be unread.")
        mock_shared_file_id = shared_file.id  # Using actual ID

        # Part 3: User2 (receiver) downloads the file
        self.login(self.user2.username, "password")
        response = self.client.get(f'/files/download/{mock_shared_file_id}')
        self.assertEqual(response.status_code, 200)

        # Part 4: Assertions
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertIn('filename="download_me.txt"', response.headers['Content-Disposition'])
        self.assertEqual(response.data, original_content)

        # Check is_read status (must refresh the object from the DB session)
        self.db.session.refresh(shared_file) # Use self.db from AppTestCase
        self.assertTrue(shared_file.is_read, "File should be marked as read after receiver downloads.")

        self.logout()

    def test_download_shared_file_sender(self):
        # with app.app_context():
        # self.login(self.user1.username, 'password')
        # dummy_file_data = self.create_dummy_file(filename="sender_download.txt")
        # self.client.post(f'/files/share/{self.user2.username}', data={'file': dummy_file_data}, content_type='multipart/form-data')
        # shared_file = SharedFile.query.filter_by(original_filename="sender_download.txt").first()
        # Part 1: User1 shares the file with User2
        self.login(self.user1.username, 'password')
        original_content = b"Content for sender download test."
        dummy_file_data = self.create_dummy_file(filename="sender_download.txt", content=original_content)
        share_data = {'file': dummy_file_data, 'message': 'File for sender to download'}
        self.client.post(
            f'/files/share/{self.user2.username}',
            data=share_data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        # User1 remains logged in

        # Part 2: Retrieve SharedFile ID and initial is_read status
        shared_file = SharedFile.query.filter_by(
            sender_id=self.user1.id,
            receiver_id=self.user2.id,
            original_filename="sender_download.txt"
        ).first()
        self.assertIsNotNone(shared_file, "Shared file record should exist in DB for sender test.")
        initial_is_read_status = shared_file.is_read
        self.assertFalse(initial_is_read_status, "File should initially be unread for sender test.")
        actual_shared_file_id = shared_file.id

        # Part 3: User1 (sender) downloads the file
        # User1 is already logged in
        response = self.client.get(f'/files/download/{actual_shared_file_id}')
        self.assertEqual(response.status_code, 200)

        # Part 4: Assertions
        self.assertEqual(response.data, original_content)

        # Check is_read status (it should NOT have changed)
        self.db.session.refresh(shared_file) # Use self.db from AppTestCase
        self.assertEqual(shared_file.is_read, initial_is_read_status, "is_read status should not change when sender downloads.")
        self.assertFalse(shared_file.is_read, "is_read status should still be False after sender download.")

        self.logout() # Logout user1 at the end

    def test_download_shared_file_unauthorized(self):
        # with app.app_context():
        # self.login(self.user1.username, 'password')
        # dummy_file_data = self.create_dummy_file(filename="unauth_download.txt")
        # self.client.post(f'/files/share/{self.user2.username}', data={'file': dummy_file_data}, content_type='multipart/form-data')
        # shared_file = SharedFile.query.filter_by(original_filename="unauth_download.txt").first()
        # self.logout()
        # mock_shared_file_id = shared_file.id if shared_file else 1
        mock_shared_file_id = 1

        self.login(self.user3.username, "password")  # Unauthorized user
        # response = self.client.get(f'/files/download/{mock_shared_file_id}', follow_redirects=True)
        # self.assertEqual(response.status_code, 200)
        # self.assertIn("You are not authorized to download this file.", response.get_data(as_text=True))
        self.logout()
        # Test for unauthorized download - User3 tries to download User1's file shared with User2
        # Step 1: User1 shares a file with User2
        self.login(self.user1.username, 'password')
        dummy_content = b"secret content for unauthorized download test"
        dummy_file_data_unauth = self.create_dummy_file(filename="unauth_download.txt", content=dummy_content)
        share_data_unauth = {'file': dummy_file_data_unauth, 'message': 'Unauthorized access test'}
        self.client.post(
            f'/files/share/{self.user2.username}',
            data=share_data_unauth,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        self.logout()

        # Step 2: Get the shared file ID
        shared_file_unauth = SharedFile.query.filter_by(
            sender_id=self.user1.id,
            receiver_id=self.user2.id,
            original_filename="unauth_download.txt"
        ).first()
        self.assertIsNotNone(shared_file_unauth, "File for unauth download test should exist.")
        unauth_file_id = shared_file_unauth.id

        # Step 3: User3 (unauthorized) attempts to download
        self.login(self.user3.username, "password")
        response_unauth = self.client.get(f'/files/download/{unauth_file_id}', follow_redirects=False) # Test redirect itself

        self.assertEqual(response_unauth.status_code, 302) # Expecting a redirect
        # Check if redirected to inbox, as per app.py logic for unauthorized download
        self.assertTrue(response_unauth.location.endswith(self.app.url_for('files_inbox')))

        # Optionally, check for flash message if your test client setup supports it easily
        # For example, by enabling session_transactions for the client or checking response data for flash message text
        # For now, checking redirect is a good indicator of the auth failure.
        # To check flash message content, you might need to follow the redirect and inspect the resulting page,
        # or use `with self.client.session_transaction() as sess:` if that's how your test setup handles flashes.
        # Let's try to check the flash message after redirect:
        response_redirected = self.client.get(f'/files/download/{unauth_file_id}', follow_redirects=True)
        self.assertIn("You are not authorized to download this file.", response_redirected.get_data(as_text=True))

        self.logout()

    def test_delete_shared_file_receiver(self):
        # Step 1: User1 shares a file with User2
        self.login(self.user1.username, 'password')
        dummy_content = b"File for receiver to delete."
        dummy_file_data = self.create_dummy_file(filename="delete_by_receiver.txt", content=dummy_content)
        share_data = {'file': dummy_file_data, 'message': 'Receiver, please delete this.'}
        self.client.post(
            f'/files/share/{self.user2.username}',
            data=share_data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        self.logout()

        # Step 2: Get shared file details
        shared_file = SharedFile.query.filter_by(
            sender_id=self.user1.id,
            receiver_id=self.user2.id,
            original_filename="delete_by_receiver.txt"
        ).first()
        self.assertIsNotNone(shared_file, "Shared file for receiver deletion test should exist.")
        file_id_to_delete = shared_file.id
        saved_filename = shared_file.saved_filename
        file_path = os.path.join(self.app.config['SHARED_FILES_UPLOAD_FOLDER'], saved_filename)
        self.assertTrue(os.path.exists(file_path), "Physical file should exist before deletion attempt.")

        # Step 3: User2 (receiver) logs in and deletes the file via API
        self.login(self.user2.username, "password")
        # Need to get a JWT token for API access
        login_resp = self.client.post('/api/login', json={'username': self.user2.username, 'password': 'password'})
        access_token = login_resp.get_json()['access_token']
        headers = {'Authorization': f'Bearer {access_token}'}

        delete_response = self.client.delete(f'/api/files/{file_id_to_delete}', headers=headers)

        # Step 4: Assertions
        self.assertEqual(delete_response.status_code, 200)
        response_json = delete_response.get_json()
        self.assertEqual(response_json['message'], "File deleted successfully")

        self.assertFalse(os.path.exists(file_path), "Physical file should be deleted from filesystem.")
        self.assertIsNone(SharedFile.query.get(file_id_to_delete), "DB record should be deleted.")

        self.logout()

    def test_delete_shared_file_sender(self):
        # Step 1: User1 shares a file with User2
        self.login(self.user1.username, 'password')
        dummy_content = b"File for sender to delete."
        dummy_file_data = self.create_dummy_file(filename="delete_by_sender.txt", content=dummy_content)
        share_data = {'file': dummy_file_data, 'message': 'Sender, you can delete this.'}
        self.client.post(
            f'/files/share/{self.user2.username}',
            data=share_data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        # User1 remains logged in for API call

        # Step 2: Get shared file details
        shared_file = SharedFile.query.filter_by(
            sender_id=self.user1.id,
            receiver_id=self.user2.id,
            original_filename="delete_by_sender.txt"
        ).first()
        self.assertIsNotNone(shared_file, "Shared file for sender deletion test should exist.")
        file_id_to_delete = shared_file.id
        saved_filename = shared_file.saved_filename
        file_path = os.path.join(self.app.config['SHARED_FILES_UPLOAD_FOLDER'], saved_filename)
        self.assertTrue(os.path.exists(file_path), "Physical file should exist before deletion by sender.")

        # Step 3: User1 (sender) deletes the file via API
        login_resp = self.client.post('/api/login', json={'username': self.user1.username, 'password': 'password'})
        access_token = login_resp.get_json()['access_token']
        headers = {'Authorization': f'Bearer {access_token}'}

        delete_response = self.client.delete(f'/api/files/{file_id_to_delete}', headers=headers)

        # Step 4: Assertions
        self.assertEqual(delete_response.status_code, 200)
        response_json = delete_response.get_json()
        self.assertEqual(response_json['message'], "File deleted successfully")

        self.assertFalse(os.path.exists(file_path), "Physical file should be deleted by sender.")
        self.assertIsNone(SharedFile.query.get(file_id_to_delete), "DB record should be deleted by sender.")

        self.logout()

    def test_delete_shared_file_unauthorized(self):
        # Step 1: User1 shares a file with User2
        self.login(self.user1.username, 'password')
        dummy_content = b"File for unauthorized delete attempt."
        dummy_file_data = self.create_dummy_file(filename="unauth_delete_attempt.txt", content=dummy_content)
        share_data = {'file': dummy_file_data, 'message': 'Unauthorized user should not delete this.'}
        self.client.post(
            f'/files/share/{self.user2.username}',
            data=share_data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        self.logout()

        # Step 2: Get shared file details
        shared_file = SharedFile.query.filter_by(
            sender_id=self.user1.id,
            receiver_id=self.user2.id,
            original_filename="unauth_delete_attempt.txt"
        ).first()
        self.assertIsNotNone(shared_file, "Shared file for unauthorized deletion test should exist.")
        file_id_to_attempt_delete = shared_file.id
        saved_filename = shared_file.saved_filename
        file_path = os.path.join(self.app.config['SHARED_FILES_UPLOAD_FOLDER'], saved_filename)
        self.assertTrue(os.path.exists(file_path), "Physical file should exist before unauthorized deletion attempt.")

        # Step 3: User3 (unauthorized) logs in and attempts to delete the file via API
        self.login(self.user3.username, "password")
        login_resp = self.client.post('/api/login', json={'username': self.user3.username, 'password': 'password'})
        access_token = login_resp.get_json()['access_token']
        headers = {'Authorization': f'Bearer {access_token}'}

        delete_response = self.client.delete(f'/api/files/{file_id_to_attempt_delete}', headers=headers)

        # Step 4: Assertions
        self.assertEqual(delete_response.status_code, 403) # Forbidden
        response_json = delete_response.get_json()
        self.assertEqual(response_json['message'], "You are not authorized to delete this file")

        self.assertTrue(os.path.exists(file_path), "Physical file should NOT be deleted by unauthorized user.")
        self.assertIsNotNone(SharedFile.query.get(file_id_to_attempt_delete), "DB record should NOT be deleted by unauthorized user.")

        self.logout()

    def test_share_file_with_special_characters_in_filename(self):
        special_filenames = [
            "你好世界 report.txt",
            "archive.version.1.0.zip",
            "file with spaces.docx",
            "another&strange=name!.pdf",
            "a'file'with\"quotes & stuff.log"
        ]
        original_content = b"This is the content for the special filename test."

        for original_filename in special_filenames:
            # Ensure a clean state for each filename - primarily for uploaded file records and physical files
            # This might involve cleaning up files from previous iterations if a shared cleanup mechanism isn't used
            # For now, we rely on unique filenames per test run or careful manual cleanup if issues arise.
            # A more robust solution might use unique sub-folder for this test or ensure generated saved_filenames are unique.

            # 1. User1 uploads the file
            self.login(self.user1.username, "password")
            dummy_file_data = self.create_dummy_file(
                filename=original_filename, content=original_content
            )
            share_data = {
                "file": dummy_file_data,
                "message": f"Test message for {original_filename}",
            }
            response_upload = self.client.post(
                f"/files/share/{self.user2.username}",
                data=share_data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.assertEqual(response_upload.status_code, 200, f"Upload failed for {original_filename}")
            self.assertIn("File successfully shared!", response_upload.get_data(as_text=True), f"Success message not found for {original_filename}")

            # 2. Verify SharedFile record in the database
            # with self.app.app_context(): # Not needed with test client and AppTestCase
            shared_file_record = SharedFile.query.filter_by(
                sender_id=self.user1.id,
                receiver_id=self.user2.id,
                original_filename=original_filename,
            ).first()
            self.assertIsNotNone(shared_file_record, f"SharedFile record not found for {original_filename}")
            self.assertEqual(shared_file_record.original_filename, original_filename, f"Original filename mismatch for {original_filename}")
            # saved_filename should be a secured, unique name. We can't predict its exact form,
            # but we can check it's not empty and different from original_filename if original_filename is unsafe.
            self.assertIsNotNone(shared_file_record.saved_filename, f"Saved filename is None for {original_filename}")
            self.assertNotEqual(shared_file_record.saved_filename, "", f"Saved filename is empty for {original_filename}")

            # 3. Verify the physical file exists
            shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
            saved_file_path = os.path.join(shared_folder, shared_file_record.saved_filename)
            self.assertTrue(os.path.exists(saved_file_path), f"Saved file does not exist for {original_filename} at {saved_file_path}")

            # Store file_id and path for cleanup
            file_id_to_clean = shared_file_record.id
            path_to_clean = saved_file_path

            self.logout() # Logout User1

            # 4. User2 sees the file in their inbox
            self.login(self.user2.username, "password")
            response_inbox = self.client.get("/files/inbox")
            self.assertEqual(response_inbox.status_code, 200, f"Inbox failed for {original_filename}")
            inbox_text = response_inbox.get_data(as_text=True)
            self.assertIn(original_filename, inbox_text, f"Original filename not in inbox for {original_filename}")
            self.assertIn(f"Test message for {original_filename}", inbox_text, f"Message not in inbox for {original_filename}")

            # 5. User2 downloads the file
            # Need the file ID, which we got from shared_file_record
            file_id = shared_file_record.id
            response_download = self.client.get(f"/files/download/{file_id}")
            self.assertEqual(response_download.status_code, 200, f"Download failed for {original_filename}")

            # 6. Verify downloaded file's name and content
            # The filename in Content-Disposition should be the original_filename
            # It might be URL-encoded or quoted, so check carefully.
            # Example: filename="你好世界 report.txt" or filename*=UTF-8''%E4%BD%A0%E5%A5%BD...
            content_disposition = response_download.headers.get("Content-Disposition", "")
            self.assertIn(f'filename="{original_filename}"', content_disposition, f"Incorrect filename in download header for {original_filename}. Got: {content_disposition}")
            self.assertEqual(response_download.data, original_content, f"File content mismatch for {original_filename}")

            self.logout() # Logout User2

            # 7. Cleanup: Remove the physical file and DB record (optional, but good practice)
            # This part is tricky because the test is designed to run within a transaction that rolls back.
            # However, physical files are not part of that transaction.
            # A common pattern is to clean up files created during tests.
            # For DB, AppTestCase likely handles rollback. Let's ensure physical file is cleaned.
            if os.path.exists(path_to_clean):
                os.remove(path_to_clean)

            # Optional: delete the DB record explicitly if not handled by test runner's transaction rollback
            # with self.app.app_context():
            # record_to_delete = SharedFile.query.get(file_id_to_clean)
            # if record_to_delete:
            # self.db.session.delete(record_to_delete)
            # self.db.session.commit()
            # Typically, the test framework's DB handling (like Flask-SQLAlchemy in tests)
            # will roll back changes after each test, so manual DB cleanup might not be needed.
            # Let's rely on AppTestCase for DB cleanup.

        # Final check: ensure shared folder is clean (or back to its original state)
        # This is a bit broad, depends on what else runs.
        # For now, focused cleanup of files created in *this* test.

    def test_share_file_with_self(self):
        # Log in as user1
        self.login(self.user1.username, "password")

        # Create a dummy file
        dummy_file_data = self.create_dummy_file(
            filename="self_share_test.txt",
            content=b"Test content for sharing with oneself."
        )

        data = {
            "file": dummy_file_data,
            "message": "This is a test message for sharing with myself.",
        }

        # user1 shares file with user1
        response = self.client.post(
            f'/files/share/{self.user1.username}', # Sharing with self.user1
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )

        # Assert successful response
        self.assertEqual(response.status_code, 200)
        self.assertIn("File successfully shared!", response.get_data(as_text=True))

        with self.app.app_context(): # Add app context here
            # Verify SharedFile record
            shared_file_record = SharedFile.query.filter_by(
                sender_id=self.user1.id,
                receiver_id=self.user1.id, # Receiver is also user1
                original_filename="self_share_test.txt"
            ).first()

            self.assertIsNotNone(shared_file_record, "SharedFile record should be created for self-share.")
            self.assertEqual(shared_file_record.message, "This is a test message for sharing with myself.")
            self.assertEqual(shared_file_record.sender_id, self.user1.id)
            self.assertEqual(shared_file_record.receiver_id, self.user1.id)

            # Verify the file exists in the shared files folder
            shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
            expected_file_path = os.path.join(shared_folder, shared_file_record.saved_filename)
            self.assertTrue(os.path.exists(expected_file_path), "Physical file should exist for self-share.")

            # Clean up: remove the created file
            if os.path.exists(expected_file_path):
                os.remove(expected_file_path)

        self.logout()
    def test_share_file_with_non_existent_user(self):
        # Log in as user1
        self.login(self.user1.username, "password")

        # Create a dummy file
        dummy_file_data = self.create_dummy_file(
            filename="test_nonexistent.txt",
            content=b"Test content for sharing with non-existent user."
        )

        data = {
            "file": dummy_file_data,
            "message": "This is a test message for a non-existent user.",
        }

        non_existent_username = "nonexistentuser123abc"

        # Attempt to share the file with the non-existent user
        response = self.client.post(
            f'/files/share/{non_existent_username}',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Recipient user not found.", response.get_data(as_text=True))

        shared_file_record = SharedFile.query.filter_by(
            sender_id=self.user1.id,
            original_filename="test_nonexistent.txt"
        ).first()
        self.assertIsNone(shared_file_record, "SharedFile record should not be created for a non-existent recipient.")

        shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
        files_in_shared_folder = os.listdir(shared_folder)
        # Filter out potential .gitkeep or other persistent files if any
        relevant_files = [f for f in files_in_shared_folder if not f.startswith('.')]
        self.assertEqual(len(relevant_files), 0, "No file should have been saved to the shared folder for a non-existent user.")

        self.logout()
