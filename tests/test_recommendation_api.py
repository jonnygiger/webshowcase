import unittest
import json
from unittest.mock import patch, ANY
from datetime import datetime, timedelta
# from app import app, db, socketio # COMMENTED OUT
# from models import User, Post, Group, Event, Poll, PollOption, Like, Comment, EventRSVP, PollVote # COMMENTED OUT
from tests.test_base import AppTestCase

class TestRecommendationAPI(AppTestCase):

    # _create_db_group, _create_db_event, _create_db_poll, _create_db_like,
    # _create_db_comment, _create_db_event_rsvp, _create_db_poll_vote
    # are now in AppTestCase (tests/test_base.py)

    def setUp(self):
        super().setUp() # Call parent setUp to get base users (self.user1, self.user2, self.user3)
        # self.user1 is the target user for recommendations
        # self.user2 will create content
        # self.user3 is the "lonely" user

        # Create some content by user2 that user1 might be recommended
        # These helpers are now in AppTestCase
        self.post_by_user2 = self._create_db_post(user_id=self.user2_id, title="User2's Post")
        self.group_by_user2 = self._create_db_group(creator_id=self.user2_id, name="User2's Group")
        # Ensure _create_db_event in AppTestCase uses date_str and handles created_at
        self.event_by_user2 = self._create_db_event(user_id=self.user2_id, title="User2's Event", date_str=(datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d'))
        self.poll_by_user2 = self._create_db_poll(user_id=self.user2_id, question="User2's Poll?")

        # User1 joins a different group (not by user2) to test suggest_groups_to_join logic (won't recommend this one)
        # self.other_group_user1_member_of = self._create_db_group(creator_id=self.user3_id, name="Other Group")
        # self.other_group_user1_member_of.members.append(self.user1) # This assumes Group model has a 'members' relationship
        # db.session.commit()


    def test_get_recommendations_success(self):
        # with app.app_context(): # Handled by test client / AppTestCase
            response = self.client.get(f'/api/recommendations?user_id={self.user1_id}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, 'application/json')

            data = json.loads(response.data)

            self.assertIn('user_id', data)
            self.assertEqual(data['user_id'], self.user1_id)

            self.assertIn('suggested_posts', data)
            self.assertIsInstance(data['suggested_posts'], list)
            if data['suggested_posts']:
                post = data['suggested_posts'][0]
                self.assertIn('id', post)
                self.assertIn('title', post)
                self.assertIn('author_username', post)

            self.assertIn('suggested_groups', data)
            self.assertIsInstance(data['suggested_groups'], list)
            if data['suggested_groups']:
                group = data['suggested_groups'][0]
                self.assertIn('id', group)
                self.assertIn('name', group)
                self.assertIn('creator_username', group)

            self.assertIn('suggested_events', data)
            self.assertIsInstance(data['suggested_events'], list)
            if data['suggested_events']:
                event = data['suggested_events'][0]
                self.assertIn('id', event)
                self.assertIn('title', event)
                self.assertIn('organizer_username', event)

            self.assertIn('suggested_users_to_follow', data)
            self.assertIsInstance(data['suggested_users_to_follow'], list)
            if data['suggested_users_to_follow']:
                user = data['suggested_users_to_follow'][0]
                self.assertIn('id', user)
                self.assertIn('username', user)

            self.assertIn('suggested_polls_to_vote', data)
            self.assertIsInstance(data['suggested_polls_to_vote'], list)
            if data['suggested_polls_to_vote']:
                poll = data['suggested_polls_to_vote'][0]
                self.assertIn('id', poll)
                self.assertIn('question', poll)
                self.assertIn('author_username', poll)
                self.assertIn('options', poll)
                self.assertIsInstance(poll['options'], list)
                if poll['options']:
                    option = poll['options'][0]
                    self.assertIn('id', option)
                    self.assertIn('text', option)
                    self.assertIn('vote_count', option)

    def test_get_recommendations_invalid_user_id(self):
        # with app.app_context():
            response = self.client.get('/api/recommendations?user_id=99999')
            self.assertEqual(response.status_code, 404)
            data = json.loads(response.data)
            self.assertIn('message', data)
            # The message might be "User 99999 not found" or "User not found"
            self.assertTrue('not found' in data['message'].lower())


    def test_get_recommendations_missing_user_id(self):
        # with app.app_context():
            response = self.client.get('/api/recommendations')
            self.assertEqual(response.status_code, 400)
            data = json.loads(response.data)
            self.assertIn('message', data)
            # Example: {'message': {'user_id': 'User ID is required and must be an integer.'}}
            # Exact message depends on reqparse error formatting
            self.assertIn('user_id', data['message'])
            self.assertTrue('required' in data['message']['user_id'].lower())


    def test_get_recommendations_no_suggestions(self):
        # self.user3 is set up by AppTestCase.setUp -> _setup_base_users()
        # It has no specific content or interactions created in this class's setUp,
        # so it should get minimal to no recommendations.
        # with app.app_context():
            response = self.client.get(f'/api/recommendations?user_id={self.user3_id}')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)

            self.assertEqual(data['user_id'], self.user3_id)
            self.assertEqual(data['suggested_posts'], [])
            self.assertEqual(data['suggested_groups'], [])
            self.assertEqual(data['suggested_events'], [])
            # user3 might be recommended user1 and user2 if the suggestion logic is simple
            # For now, let's assert it's a list. More specific checks depend on recommendation logic.
            self.assertIsInstance(data['suggested_users_to_follow'], list)
            self.assertEqual(data['suggested_polls_to_vote'], [])

    # _get_jwt_token is in AppTestCase

    # Helpers for creating likes, comments, RSVPs, votes are in AppTestCase
    # _create_db_like, _create_db_comment, _create_db_event_rsvp, _create_db_poll_vote
    # are inherited from AppTestCase
