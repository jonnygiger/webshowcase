import unittest
import os
import io
import urllib.parse
import html
from flask import url_for

from unittest.mock import patch, ANY
from datetime import datetime

from social_app.models.db_models import User, SharedFile
from tests.test_base import AppTestCase


class TestFileSharing(AppTestCase):

    def test_share_file_get_page(self):
        self.login(self.user1.username, "password")
        response = self.client.get(f"/files/share/{self.user2.username}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f"Share File with {self.user2.username}", response.get_data(as_text=True)
        )
        self.logout()

    def test_share_file_successful_upload(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            dummy_file_data = self.create_dummy_file(
                filename="upload_test.txt", content=b"Test file content for upload."
            )

            data = {
                "file": dummy_file_data,
                "message": "This is a test message for the shared file.",
            }
            response = self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            # After a successful share, the user is redirected to the inbox.
            # The test now checks for inbox-related content.
            self.assertIn("My Shared Files Inbox", response.get_data(as_text=True))

        with self.app.app_context():
            shared_file_record = SharedFile.query.filter_by(
                sender_id=self.user1.id, receiver_id=self.user2.id
            ).first()
            self.assertIsNotNone(shared_file_record)
            self.assertEqual(shared_file_record.original_filename, "upload_test.txt")
            self.assertEqual(
                shared_file_record.message,
                "This is a test message for the shared file.",
            )
            self.assertEqual(shared_file_record.sender_id, self.user1.id)
            self.assertEqual(shared_file_record.receiver_id, self.user2.id)

            shared_folder = self.app.config["SHARED_FILES_TEST_FOLDER"]
            expected_file_path = os.path.join(
                shared_folder, shared_file_record.saved_filename
            )
            self.assertTrue(os.path.exists(expected_file_path))
            if os.path.exists(expected_file_path):
                os.remove(expected_file_path)

        self.logout()

    def test_share_file_without_message(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")

            dummy_file_data = self.create_dummy_file(
                filename="test_no_message.txt",
                content=b"Test file content without a message.",
            )

            data = {
                "file": dummy_file_data,
                "message": "",  # Explicitly empty, as the form would submit this
            }

            response = self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("My Shared Files Inbox", response.get_data(as_text=True))

        with self.app.app_context():
            shared_file_record = SharedFile.query.filter_by(
                sender_id=self.user1.id,
                receiver_id=self.user2.id,
                original_filename="test_no_message.txt",
            ).first()

            self.assertIsNotNone(shared_file_record)
            self.assertEqual(
                shared_file_record.original_filename, "test_no_message.txt"
            )
            # The model coerces None to empty string if 'message' is in form data
            self.assertEqual(shared_file_record.message, "")

            shared_folder = self.app.config["SHARED_FILES_TEST_FOLDER"]
            expected_file_path = os.path.join(
                shared_folder, shared_file_record.saved_filename
            )
            self.assertTrue(os.path.exists(expected_file_path))

            if os.path.exists(expected_file_path):
                os.remove(expected_file_path)

        self.logout()

    def test_share_file_with_empty_message(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")

            dummy_file_data = self.create_dummy_file(
                filename="test_empty_message.txt",
                content=b"Test file content with an empty message.",
            )

            data = {
                "file": dummy_file_data,
                "message": "",
            }

            response = self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("My Shared Files Inbox", response.get_data(as_text=True))

        with self.app.app_context():
            shared_file_record = SharedFile.query.filter_by(
                sender_id=self.user1.id,
                receiver_id=self.user2.id,
                original_filename="test_empty_message.txt",
            ).first()

            self.assertIsNotNone(shared_file_record)
            self.assertEqual(
                shared_file_record.original_filename, "test_empty_message.txt"
            )
            self.assertEqual(shared_file_record.message, "")

            shared_folder = self.app.config["SHARED_FILES_TEST_FOLDER"]
            expected_file_path = os.path.join(
                shared_folder, shared_file_record.saved_filename
            )
            self.assertTrue(os.path.exists(expected_file_path))

            if os.path.exists(expected_file_path):
                os.remove(expected_file_path)

        self.logout()

    def test_share_file_invalid_file_type(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            dummy_file_data = self.create_dummy_file(
                filename="test.exe",
                content=b"executable content",
                content_type="application/octet-stream",
            )
            data = {"file": dummy_file_data}
            response = self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("File type not allowed", response.get_data(as_text=True))

        with self.app.app_context():
            shared_file_record = SharedFile.query.filter_by(
                original_filename="test.exe"
            ).first()
            self.assertIsNone(shared_file_record)

            shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
            files_in_shared_folder = os.listdir(shared_folder)
            relevant_files = [
                f for f in files_in_shared_folder if not f.startswith(".")
            ]
            self.assertEqual(len(relevant_files), 0)

        self.logout()

    def test_share_file_too_large(self):
        with self.app.app_context():
            original_max_size = self.app.config.get("SHARED_FILES_MAX_SIZE")
            self.login(self.user1.username, "password")
            try:
                self.app.config["SHARED_FILES_MAX_SIZE"] = 10
                dummy_file_data = self.create_dummy_file(
                    filename="large_file.txt",
                    content=b"This content is definitely larger than 10 bytes.",
                )
                data = {"file": dummy_file_data}
                response = self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                    data=data,
                    content_type="multipart/form-data",
                    follow_redirects=True,
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("File is too large", response.get_data(as_text=True))

            finally:
                if original_max_size is not None:
                    self.app.config["SHARED_FILES_MAX_SIZE"] = original_max_size
                else:
                    pass
            with self.app.app_context():
                shared_file_record = SharedFile.query.filter_by(
                    original_filename="large_file.txt"
                ).first()
                self.assertIsNone(shared_file_record)

                shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
                files_in_shared_folder = os.listdir(shared_folder)
                relevant_files = [
                    f for f in files_in_shared_folder if not f.startswith(".")
                ]
                self.assertEqual(len(relevant_files), 0)

            self.logout()

    def test_files_inbox_empty(self):
        self.login(self.user2.username, "password")
        response = self.client.get("/files/inbox")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "You have not received any files yet.", response.get_data(as_text=True)
        )
        self.logout()

    def test_files_inbox_with_files(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            dummy_file_data = self.create_dummy_file(
                filename="inbox_test_file.txt", content=b"Content for inbox."
            )
            share_data = {
                "file": dummy_file_data,
                "message": "Hi! This is for your inbox.",
            }
            response_share = self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=share_data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.assertEqual(response_share.status_code, 200)
            self.assertIn("My Shared Files Inbox", response_share.get_data(as_text=True))
            self.logout()

        # Log in as receiver and check inbox
        with self.app.app_context():
            self.login(self.user2.username, "password")
            response_inbox = self.client.get("/files/inbox")
            self.assertEqual(response_inbox.status_code, 200)

            response_data_text = response_inbox.get_data(as_text=True)
            self.assertIn("inbox_test_file.txt", response_data_text)
            self.assertIn(self.user1.username, response_data_text)
            self.assertIn("Hi! This is for your inbox.", response_data_text)
            self.logout()

    def test_download_shared_file_receiver(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            original_content = b"Downloadable content for receiver."
            dummy_file_data = self.create_dummy_file(
                filename="download_me.txt", content=original_content
            )
            share_data = {"file": dummy_file_data, "message": "File to download"}
            self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=share_data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.logout()

        with self.app.app_context():
            shared_file = SharedFile.query.filter_by(
                sender_id=self.user1.id,
                receiver_id=self.user2.id,
                original_filename="download_me.txt",
            ).first()
            self.assertIsNotNone(shared_file)
            self.assertFalse(shared_file.is_read)
            actual_shared_file_id = shared_file.id

            self.login(self.user2.username, "password")
            response = self.client.get(
                url_for("core.download_shared_file", shared_file_id=actual_shared_file_id)
            )
            self.assertEqual(response.status_code, 200)

            self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
            self.assertIn(
                'filename="download_me.txt"',
                response.headers["Content-Disposition"],
            )
            self.assertEqual(response.data, original_content)

            self.db.session.refresh(shared_file)
            self.assertTrue(shared_file.is_read)

            shared_folder = self.app.config["SHARED_FILES_TEST_FOLDER"]
            expected_file_path = os.path.join(shared_folder, shared_file.saved_filename)
            if os.path.exists(expected_file_path):
                os.remove(expected_file_path)

        self.logout()

    def test_download_shared_file_sender(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            original_content = b"Content for sender download test."
            dummy_file_data = self.create_dummy_file(
                filename="sender_download.txt", content=original_content
            )
            share_data = {
                "file": dummy_file_data,
                "message": "File for sender to download",
            }
            self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=share_data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.logout()

        with self.app.app_context():
            shared_file = SharedFile.query.filter_by(
                sender_id=self.user1.id,
                receiver_id=self.user2.id,
                original_filename="sender_download.txt",
            ).first()
            self.assertIsNotNone(shared_file)
            initial_is_read_status = shared_file.is_read
            self.assertFalse(initial_is_read_status)
            actual_shared_file_id = shared_file.id

            self.login(self.user1.username, "password")
            response = self.client.get(
                url_for("core.download_shared_file", shared_file_id=actual_shared_file_id)
            )
            self.assertEqual(response.status_code, 200)

            self.assertEqual(response.data, original_content)

            self.db.session.refresh(shared_file)
            self.assertEqual(shared_file.is_read, initial_is_read_status)
            self.assertFalse(shared_file.is_read)

            shared_folder = self.app.config["SHARED_FILES_TEST_FOLDER"]
            expected_file_path = os.path.join(shared_folder, shared_file.saved_filename)
            if os.path.exists(expected_file_path):
                os.remove(expected_file_path)

        self.logout()

    def test_download_shared_file_unauthorized(self):
        with self.app.app_context():
            mock_shared_file_id = 1

            self.login(self.user3.username, "password")
            self.logout()
            self.login(self.user1.username, "password")
            dummy_content = b"secret content for unauthorized download test"
            dummy_file_data_unauth = self.create_dummy_file(
                filename="unauth_download.txt", content=dummy_content
            )
            share_data_unauth = {
                "file": dummy_file_data_unauth,
                "message": "Unauthorized access test",
            }
            self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=share_data_unauth,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.logout()

            with self.app.app_context():
                shared_file_unauth = SharedFile.query.filter_by(
                    sender_id=self.user1.id,
                    receiver_id=self.user2.id,
                    original_filename="unauth_download.txt",
                ).first()
                self.assertIsNotNone(shared_file_unauth)
                unauth_file_id = shared_file_unauth.id
                saved_filename_for_cleanup = shared_file_unauth.saved_filename

            self.login(self.user3.username, "password")
            response_unauth = self.client.get(
                url_for("core.download_shared_file", shared_file_id=unauth_file_id),
            )

            self.assertEqual(response_unauth.status_code, 403)

        self.logout()

        with self.app.app_context():
            shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
            expected_file_path = os.path.join(shared_folder, saved_filename_for_cleanup)
            if os.path.exists(expected_file_path):
                os.remove(expected_file_path)

    def test_delete_shared_file_receiver(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            dummy_content = b"File for receiver to delete."
            dummy_file_data = self.create_dummy_file(
                filename="delete_by_receiver.txt", content=dummy_content
            )
            share_data = {
                "file": dummy_file_data,
                "message": "Receiver, please delete this.",
            }
            self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=share_data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.logout()

        file_id_to_delete = None
        file_path = None
        retrieved_saved_filename_before_api_call = None

        with self.app.app_context():
            shared_file_for_test = SharedFile.query.filter_by(
                sender_id=self.user1.id,
                receiver_id=self.user2.id,
                original_filename="delete_by_receiver.txt",
            ).first()
            self.assertIsNotNone(shared_file_for_test)
            self.assertIsNotNone(shared_file_for_test.saved_filename)
            file_id_to_delete = shared_file_for_test.id
            retrieved_saved_filename_before_api_call = (
                shared_file_for_test.saved_filename
            )
            file_path = os.path.join(
                self.app.config["SHARED_FILES_UPLOAD_FOLDER"],
                shared_file_for_test.saved_filename,
            )
            self.assertTrue(os.path.exists(file_path))

        self.login(self.user2.username, "password")
        login_resp = self.client.post(
            "/api/login", json={"username": self.user2.username, "password": "password"}
        )
        access_token = login_resp.get_json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        delete_response = self.client.delete(
            f"/api/files/{file_id_to_delete}", headers=headers
        )

        self.assertEqual(delete_response.status_code, 200)

        with self.app.app_context():
            self.assertFalse(os.path.exists(file_path))
            self.assertIsNone(self.db.session.get(SharedFile, file_id_to_delete))

        self.logout()

    def test_delete_shared_file_sender(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            dummy_content = b"File for sender to delete."
            dummy_file_data = self.create_dummy_file(
                filename="delete_by_sender.txt", content=dummy_content
            )
            share_data = {
                "file": dummy_file_data,
                "message": "Sender, you can delete this.",
            }
            self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=share_data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )

        file_id_to_delete = None
        file_path = None

        with self.app.app_context():
            shared_file = SharedFile.query.filter_by(
                sender_id=self.user1.id,
                receiver_id=self.user2.id,
                original_filename="delete_by_sender.txt",
            ).first()
            self.assertIsNotNone(shared_file)
            file_id_to_delete = shared_file.id
            saved_filename = shared_file.saved_filename
            file_path = os.path.join(
                self.app.config["SHARED_FILES_UPLOAD_FOLDER"], saved_filename
            )
            self.assertTrue(os.path.exists(file_path))

        login_resp = self.client.post(
            "/api/login", json={"username": self.user1.username, "password": "password"}
        )
        access_token = login_resp.get_json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        delete_response = self.client.delete(
            f"/api/files/{file_id_to_delete}", headers=headers
        )

        self.assertEqual(delete_response.status_code, 200)
        response_json = delete_response.get_json()
        self.assertEqual(response_json["message"], "File deleted successfully")

        with self.app.app_context():
            self.assertFalse(os.path.exists(file_path))
            self.assertIsNone(self.db.session.get(SharedFile, file_id_to_delete))

        self.logout()

    def test_delete_shared_file_unauthorized(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            dummy_content = b"File for unauthorized delete attempt."
            dummy_file_data = self.create_dummy_file(
                filename="unauth_delete_attempt.txt", content=dummy_content
            )
            share_data = {
                "file": dummy_file_data,
                "message": "Unauthorized user should not delete this.",
            }
            self.client.post(
                url_for("core.share_file_route", receiver_username=self.user2.username),
                data=share_data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.logout()

        file_id_to_attempt_delete = None
        file_path = None
        original_file_record_exists = False

        with self.app.app_context():
            shared_file = SharedFile.query.filter_by(
                sender_id=self.user1.id,
                receiver_id=self.user2.id,
                original_filename="unauth_delete_attempt.txt",
            ).first()
            self.assertIsNotNone(shared_file)
            file_id_to_attempt_delete = shared_file.id
            saved_filename = shared_file.saved_filename
            file_path = os.path.join(
                self.app.config["SHARED_FILES_UPLOAD_FOLDER"], saved_filename
            )
            self.assertTrue(os.path.exists(file_path))

        self.login(self.user3.username, "password")
        login_resp = self.client.post(
            "/api/login", json={"username": self.user3.username, "password": "password"}
        )
        access_token = login_resp.get_json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        delete_response = self.client.delete(
            f"/api/files/{file_id_to_attempt_delete}", headers=headers
        )

        self.assertEqual(delete_response.status_code, 403)
        response_json = delete_response.get_json()
        self.assertEqual(
            response_json["message"], "You are not authorized to delete this file"
        )

        with self.app.app_context():
            self.assertTrue(os.path.exists(file_path))
            self.assertIsNotNone(
                self.db.session.get(SharedFile, file_id_to_attempt_delete)
            )
            if os.path.exists(file_path):
                os.remove(file_path)

        self.logout()

    def test_share_file_with_special_characters_in_filename(self):
        special_filenames = [
            "你好世界 report.txt",
            "archive.version.1.0.zip",
            "file with spaces.docx",
            "another&strange=name!.pdf",
        ]
        original_content = b"This is the content for the special filename test."

        for original_filename in special_filenames:
            with self.app.app_context():
                self.login(self.user1.username, "password")
                dummy_file_data = self.create_dummy_file(
                    filename=original_filename, content=original_content
                )
                share_data = {
                    "file": dummy_file_data,
                    "message": f"Test message for {original_filename}",
                }
                response_upload = self.client.post(
                    url_for("core.share_file_route", receiver_username=self.user2.username),
                    data=share_data,
                    content_type="multipart/form-data",
                    follow_redirects=True,
                )
                self.assertEqual(response_upload.status_code, 200)
                self.assertIn(
                    "My Shared Files Inbox", response_upload.get_data(as_text=True)
                )

            path_to_clean = None
            file_id = None

            with self.app.app_context():
                shared_file_record = SharedFile.query.filter_by(
                    sender_id=self.user1.id,
                    receiver_id=self.user2.id,
                    original_filename=original_filename,
                ).first()
                self.assertIsNotNone(shared_file_record)
                self.assertEqual(
                    shared_file_record.original_filename, original_filename
                )
                self.assertIsNotNone(shared_file_record.saved_filename)
                self.assertNotEqual(shared_file_record.saved_filename, "")

                shared_folder = self.app.config["SHARED_FILES_TEST_FOLDER"]
                saved_file_path = os.path.join(
                    shared_folder, shared_file_record.saved_filename
                )
                self.assertTrue(os.path.exists(saved_file_path))

                path_to_clean = saved_file_path
                file_id = shared_file_record.id

            self.logout()

            self.login(self.user2.username, "password")
            response_inbox = self.client.get("/files/inbox")
            self.assertEqual(response_inbox.status_code, 200)
            inbox_text = response_inbox.get_data(as_text=True)
            self.assertIn(html.escape(original_filename), inbox_text)
            expected_message_in_inbox = (
                f"Test message for {html.escape(original_filename)}"
            )
            self.assertIn(expected_message_in_inbox, inbox_text)

            response_download = self.client.get(
                url_for("core.download_shared_file", shared_file_id=file_id)
            )
            self.assertEqual(response_download.status_code, 200)

            content_disposition = response_download.headers.get(
                "Content-Disposition", ""
            )
            encoded_filename_for_star = urllib.parse.quote(
                original_filename, safe="!'"
            )
            expected_filename_star = f"filename*=UTF-8''{encoded_filename_for_star}"
            self.assertTrue(
                f'filename="{original_filename}"' in content_disposition
                or expected_filename_star in content_disposition
            )
            self.assertEqual(response_download.data, original_content)
            self.logout()

            if path_to_clean and os.path.exists(path_to_clean):
                os.remove(path_to_clean)
            elif path_to_clean:
                print(
                    f"Warning: File {path_to_clean} was expected but not found during cleanup for {original_filename}."
                )

    def test_share_file_with_self(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            dummy_file_data = self.create_dummy_file(
                filename="self_share_test.txt",
                content=b"Test content for sharing with oneself.",
            )
            data = {
                "file": dummy_file_data,
                "message": "This is a test message for sharing with myself.",
            }
            response = self.client.post(
                url_for("core.share_file_route", receiver_username=self.user1.username),
                data=data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("My Shared Files Inbox", response.get_data(as_text=True))

        with self.app.app_context():
            shared_file_record = SharedFile.query.filter_by(
                sender_id=self.user1.id,
                receiver_id=self.user1.id,
                original_filename="self_share_test.txt",
            ).first()
            self.assertIsNotNone(shared_file_record)
            self.assertEqual(
                shared_file_record.message,
                "This is a test message for sharing with myself.",
            )
            self.assertEqual(shared_file_record.sender_id, self.user1.id)
            self.assertEqual(shared_file_record.receiver_id, self.user1.id)
            shared_folder = self.app.config["SHARED_FILES_TEST_FOLDER"]
            expected_file_path = os.path.join(
                shared_folder, shared_file_record.saved_filename
            )
            self.assertTrue(os.path.exists(expected_file_path))
            if os.path.exists(expected_file_path):
                os.remove(expected_file_path)
        self.logout()

    def test_share_file_with_non_existent_user(self):
        with self.app.app_context():
            self.login(self.user1.username, "password")
            dummy_file_data = self.create_dummy_file(
                filename="test_nonexistent.txt",
                content=b"Test content for sharing with non-existent user.",
            )
            data = {
                "file": dummy_file_data,
                "message": "This is a test message for a non-existent user.",
            }
            non_existent_username = "nonexistentuser123abc"
            response = self.client.post(
                url_for("core.share_file_route", receiver_username=non_existent_username),
                data=data,
                content_type="multipart/form-data",
                follow_redirects=True
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("User not found", response.get_data(as_text=True))
        with self.app.app_context():
            shared_file_record = SharedFile.query.filter_by(
                sender_id=self.user1.id, original_filename="test_nonexistent.txt"
            ).first()
            self.assertIsNone(shared_file_record)
            shared_folder = self.app.config["SHARED_FILES_UPLOAD_FOLDER"]
            files_in_shared_folder = os.listdir(shared_folder)
            relevant_files = [
                f for f in files_in_shared_folder if not f.startswith(".")
            ]
            self.assertEqual(len(relevant_files), 0)
        self.logout()
