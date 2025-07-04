import unittest
from app import app, db
from models import User, Event
from tests.test_base import AppTestCase
from datetime import datetime


class TestEventRendering(AppTestCase):

    def test_event_description_nl2br(self):
        with self.app.app_context():  # Add app context wrapper
            # 1. Create a test user (organizer)
            organizer = User(
                username="event_organizer",
                email="organizer@example.com",
                password_hash="testpassword",
            )
            db.session.add(organizer)
            db.session.commit()

            # 2. Create an event with a multi-line description
            event_description_with_newlines = (
                "This is line one.\nThis is line two.\nAnd this is line three."
            )
            event_description_with_br = (
                "This is line one.<br>\nThis is line two.<br>\nAnd this is line three."
            )

            event = Event(
                title="Test Event NL2BR",
                description=event_description_with_newlines,
                date=datetime.utcnow(),
                location="Test Location",
                user_id=organizer.id,
            )
            db.session.add(event)
            db.session.commit()
            event_id = event.id  # Store event_id while in context

        # 3. Log in as a user (can be the organizer or another user)
        #    For simplicity, we'll access the page as an unauthenticated user if possible,
        #    or log in if the page requires it. The view_event route itself doesn't require login
        #    to see the event, only for RSVP status etc.

        # 4. Make a GET request to the event view page
        response = self.client.get(f"/event/{event_id}")  # Use stored event_id

        # 5. Assert that the response status code is 200
        self.assertEqual(response.status_code, 200)

        # 6. Assert that the rendered HTML contains the event description with <br> tags
        response_data = response.get_data(as_text=True)
        self.assertIn(event_description_with_br, response_data)
        # Also check that the original newline characters (without <br>) are not directly present
        # in a way that would indicate the filter didn't work.
        # This is a bit tricky because the <br> tag itself contains \n if we formatted it that way.
        # The key is that "line one.\nThis is line two" (raw) should NOT be there.
        # The check for `event_description_with_br` already implies this.


if __name__ == "__main__":
    unittest.main()
