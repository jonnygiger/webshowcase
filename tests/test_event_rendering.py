import unittest
from social_app import db
from social_app.models.db_models import User, Event
from tests.test_base import AppTestCase
from datetime import datetime
from flask import url_for


class TestEventRendering(AppTestCase):

    def test_event_description_nl2br(self):
        with self.app.app_context():
            organizer = User(
                username="event_organizer",
                email="organizer@example.com",
                password_hash="testpassword",
            )
            db.session.add(organizer)
            db.session.commit()

            event_description_with_newlines = (
                "This is line one.\nThis is line two.\nAnd this is line three."
            )
            event_description_with_br = (
                "This is line one.<br>\nThis is line two.<br>\nAnd this is line three."
            )

            event = Event(
                title="Test Event NL2BR",
                description=event_description_with_newlines,
                date=datetime.now(timezone.utc),
                location="Test Location",
                user_id=organizer.id,
            )
            db.session.add(event)
            db.session.commit()
            event_id = event.id

        response = self.client.get(url_for("core.view_event", event_id=event_id))

        self.assertEqual(response.status_code, 200)

        response_data = response.get_data(as_text=True)
        self.assertIn(event_description_with_br, response_data)


if __name__ == "__main__":
    unittest.main()
