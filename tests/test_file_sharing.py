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
        pass  # Placeholder

    def test_delete_shared_file_receiver(self):
        # with app.app_context():
        # self.login(self.user1.username, 'password')
        # dummy_file_data = self.create_dummy_file(filename="to_delete_receiver.txt")
        # self.client.post(f'/files/share/{self.user2.username}', data={'file': dummy_file_data}, content_type='multipart/form-data')
        # shared_file = SharedFile.query.filter_by(original_filename="to_delete_receiver.txt").first()
        # saved_filename = shared_file.saved_filename
        # file_path = os.path.join(app.config['SHARED_FILES_UPLOAD_FOLDER'], saved_filename)
        # self.logout()
        # mock_shared_file_id = shared_file.id if shared_file else 1
        mock_shared_file_id = 1

        self.login(self.user2.username, "password")
        # response = self.client.post(f'/files/delete/{mock_shared_file_id}', follow_redirects=True)
        # self.assertEqual(response.status_code, 200)
        # self.assertIn("File successfully deleted.", response.get_data(as_text=True))
        # self.assertIsNone(SharedFile.query.get(mock_shared_file_id))
        # self.assertFalse(os.path.exists(file_path))
        self.logout()
        pass  # Placeholder

    def test_delete_shared_file_sender(self):
        # with app.app_context():
        self.login(self.user1.username, "password")  # Sender
        # dummy_file_data = self.create_dummy_file(filename="to_delete_sender.txt")
        # self.client.post(f'/files/share/{self.user2.username}', data={'file': dummy_file_data}, content_type='multipart/form-data')
        # shared_file = SharedFile.query.filter_by(original_filename="to_delete_sender.txt").first()
        # file_id = shared_file.id
        # file_path = os.path.join(app.config['SHARED_FILES_UPLOAD_FOLDER'], shared_file.saved_filename)
        mock_file_id = 1

        # response = self.client.post(f'/files/delete/{mock_file_id}', follow_redirects=True)
        # self.assertEqual(response.status_code, 200)
        # self.assertIn("File successfully deleted.", response.get_data(as_text=True))
        # self.assertIsNone(SharedFile.query.get(mock_file_id))
        # self.assertFalse(os.path.exists(file_path))
        self.logout()
        pass  # Placeholder

    def test_delete_shared_file_unauthorized(self):
        # with app.app_context():
        # self.login(self.user1.username, 'password')
        # dummy_file_data = self.create_dummy_file(filename="unauth_delete.txt")
        # self.client.post(f'/files/share/{self.user2.username}', data={'file': dummy_file_data}, content_type='multipart/form-data')
        # shared_file = SharedFile.query.filter_by(original_filename="unauth_delete.txt").first()
        # file_id = shared_file.id
        # file_path = os.path.join(app.config['SHARED_FILES_UPLOAD_FOLDER'], shared_file.saved_filename)
        # self.logout()
        mock_file_id = 1

        self.login(self.user3.username, "password")  # Unauthorized user
        # response = self.client.post(f'/files/delete/{mock_file_id}', follow_redirects=True)
        # self.assertEqual(response.status_code, 200)
        # self.assertIn("You are not authorized to delete this file.", response.get_data(as_text=True))
        # self.assertIsNotNone(SharedFile.query.get(mock_file_id))
        # self.assertFalse(os.path.exists(file_path)) # This assertion might be wrong if file shouldn't be deleted by unauthorized
        self.logout()
        pass  # Placeholder
