import unittest
import json
from unittest.mock import patch, ANY
from datetime import datetime
from werkzeug.security import generate_password_hash
from app import app, db, socketio
from models import User, Post, Comment, Achievement, UserAchievement
from achievements_logic import check_and_award_achievements, get_user_stat
from tests.test_base import AppTestCase

# Helper function to seed achievements for tests
def seed_test_achievements():
    # This function requires live DB and Achievement model.
    achievements_data = [
        {"name": "Test First Post", "description": "Desc1", "icon_url": "icon1", "criteria_type": "num_posts", "criteria_value": 1},
        {"name": "Test 5 Posts", "description": "Desc2", "icon_url": "icon2", "criteria_type": "num_posts", "criteria_value": 5},
        {"name": "Test First Comment", "description": "Desc3", "icon_url": "icon3", "criteria_type": "num_comments_given", "criteria_value": 1},
    ]
    # ach_ids = {} # Not strictly needed with the new logic, but harmless if left for now
    for ach_data in achievements_data:
        existing_achievement = Achievement.query.filter_by(name=ach_data["name"]).first()
        if not existing_achievement:
            ach = Achievement(**ach_data)
            db.session.add(ach)
    db.session.commit() # Commit all new achievements at once

    # Query for IDs after potential creation and commit
    final_ach_ids = {ach_data['name']: Achievement.query.filter_by(name=ach_data['name']).first().id for ach_data in achievements_data}
    return final_ach_ids

class AchievementLogicTests(AppTestCase):
    # These tests heavily depend on live DB, models (User, Post, Comment, Achievement, UserAchievement),
    # and logic functions (get_user_stat, check_and_award_achievements).
    # They are placeholdered for the refactoring task.

    def test_get_user_stat_num_posts(self):
        with app.app_context():
            user = self.user1
            self._create_db_post(user_id=user.id, title="Post 1")
            self._create_db_post(user_id=user.id, title="Post 2")
            stat = get_user_stat(user, 'num_posts')
            self.assertEqual(stat, 2)

    def test_award_first_post_achievement(self):
        with app.app_context():
            ach_ids = seed_test_achievements() # Helper defined above
            user = self.user2
            self._create_db_post(user_id=user.id, title="First Post by User2")
            check_and_award_achievements(user.id)
            first_post_ach_id = ach_ids["Test First Post"]
            user_ach = UserAchievement.query.filter_by(user_id=user.id, achievement_id=first_post_ach_id).first()
            self.assertIsNotNone(user_ach, "User should have been awarded the 'Test First Post' achievement.")
            self.assertEqual(user_ach.achievement.name, "Test First Post")

    def test_award_multiple_achievements_incrementally(self):
        with app.app_context():
            ach_ids = seed_test_achievements()
            user = self.user3 # Assuming self.user3 is setup by AppTestCase
            first_post_ach_id = ach_ids["Test First Post"]
            five_posts_ach_id = ach_ids["Test 5 Posts"]

            # First stage (1 post)
            self._create_db_post(user_id=user.id, title="Incremental Post 1")
            check_and_award_achievements(user.id)

            user_ach_first = UserAchievement.query.filter_by(user_id=user.id, achievement_id=first_post_ach_id).first()
            self.assertIsNotNone(user_ach_first, "User should have 'Test First Post' after 1 post.")

            user_ach_five = UserAchievement.query.filter_by(user_id=user.id, achievement_id=five_posts_ach_id).first()
            self.assertIsNone(user_ach_five, "User should NOT have 'Test 5 Posts' after 1 post.")

            # Second stage (5 posts)
            for i in range(2, 6): # Create 4 more posts
                self._create_db_post(user_id=user.id, title=f"Incremental Post {i}")
            check_and_award_achievements(user.id)

            user_ach_five_updated = UserAchievement.query.filter_by(user_id=user.id, achievement_id=five_posts_ach_id).first()
            self.assertIsNotNone(user_ach_five_updated, "User should have 'Test 5 Posts' after 5 posts.")

            user_ach_first_still_there = UserAchievement.query.filter_by(user_id=user.id, achievement_id=first_post_ach_id).first()
            self.assertIsNotNone(user_ach_first_still_there, "'Test First Post' should still be awarded.")

    def test_no_duplicate_achievements_awarded(self):
        with app.app_context():
            ach_ids = seed_test_achievements()
            user = self.user1 # Assuming self.user1 is setup by AppTestCase
            first_post_ach_id = ach_ids["Test First Post"]

            # First call to award
            self._create_db_post(user_id=user.id, title="Duplicate Test Post 1")
            check_and_award_achievements(user.id)

            count_initial = UserAchievement.query.filter_by(user_id=user.id, achievement_id=first_post_ach_id).count()
            self.assertEqual(count_initial, 1, "Achievement should be awarded once initially.")

            # Second call (no new activity)
            check_and_award_achievements(user.id) # Call again
            count_after_second_call = UserAchievement.query.filter_by(user_id=user.id, achievement_id=first_post_ach_id).count()
            self.assertEqual(count_after_second_call, 1, "Achievement should not be awarded again if already earned.")

    def test_display_achievements_on_user_profile(self):
        with app.app_context():
            ach_ids = seed_test_achievements()
            user = User(username='profile_ach_user', email='pau@example.com', password_hash=generate_password_hash('password123'))
            db.session.add(user)
            db.session.commit()
            user = User.query.filter_by(username='profile_ach_user').first() # Re-fetch

            first_post_ach_id = ach_ids["Test First Post"]
            user_ach = UserAchievement(user_id=user.id, achievement_id=first_post_ach_id)
            db.session.add(user_ach)
            db.session.commit()

            response = self.client.get(f'/user/{user.username}')
            self.assertEqual(response.status_code, 200)
            self.assertIn("Test First Post", response.data.decode(), "Achievement name should be on the profile page.")
            # self.assertInHTML("Test First Post", response.data.decode(), "Test First Post") # Alternative

    def test_no_achievements_message_on_profile(self):
        with app.app_context():
            user = User(username='no_ach_user_profile', email='naup@example.com', password_hash=generate_password_hash('password123'))
            db.session.add(user)
            db.session.commit()
            user = User.query.filter_by(username='no_ach_user_profile').first() # Re-fetch

            response = self.client.get(f'/user/{user.username}')
            self.assertEqual(response.status_code, 200)
            self.assertIn("No achievements yet", response.data.decode(), "Should display a message for no achievements.")

    def test_view_user_achievements_page_earned_and_all(self):
        with app.app_context():
            ach_ids = seed_test_achievements()
            user = User(username='all_ach_user_page', email='aaup@example.com', password_hash=generate_password_hash('password'))
            db.session.add(user)
            db.session.commit()
            user = User.query.filter_by(username='all_ach_user_page').first() # Re-fetch

            first_post_ach_id = ach_ids["Test First Post"]
            user_ach = UserAchievement(user_id=user.id, achievement_id=first_post_ach_id)
            db.session.add(user_ach)
            db.session.commit()

            self.login('all_ach_user_page', 'password')
            response = self.client.get('/achievements')
            self.assertEqual(response.status_code, 200)
            html_content = response.data.decode()

            self.assertIn("Test First Post", html_content)
            # Assuming assertInHTML checks for "Test First Post" within a structure that indicates it's earned
            # For example, if earned achievements have a special class or text like "(Earned)"
            # This might need adjustment based on actual HTML structure.
            # For now, a simple check for name and a placeholder for "Earned" status:
            self.assertInHTML("Test First Post", html_content, "Test First Post") # Checks if name is present
            # A more specific check for earned status might be:
            # self.assertIn("Test First Post (Earned)", html_content) # Or check for a specific CSS class

            self.assertIn("Test 5 Posts", html_content) # Check unearned is also listed
            # self.assertNotIn("Test 5 Posts (Earned)", html_content) # Check it's not marked as earned
            self.logout()

    def test_view_user_achievements_page_no_earned(self):
        with app.app_context():
            seed_test_achievements()
            user = User(username='no_earned_ach_page', email='neaup@example.com', password_hash=generate_password_hash('password'))
            db.session.add(user)
            db.session.commit()
            user = User.query.filter_by(username='no_earned_ach_page').first() # Re-fetch

            self.login('no_earned_ach_page', 'password')
            response = self.client.get('/achievements')
            self.assertEqual(response.status_code, 200)
            html_content = response.data.decode()

            # The instruction "You haven't earned any achievements yet" might be too specific,
            # a general "No achievements earned" or similar is also acceptable.
            # Using a less strict check:
            self.assertIn("haven't earned any achievements yet", html_content, "Should display message for no earned achievements.")

            self.assertIn("Test First Post", html_content) # Check available achievements are listed
            self.assertIn("Test 5 Posts", html_content)
            self.logout()

    # assertInHTML is in AppTestCase
