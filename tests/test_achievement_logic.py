import unittest
import json
from unittest.mock import patch, ANY
from datetime import datetime
from werkzeug.security import generate_password_hash
from social_app import create_app, db # Removed socketio
from social_app.models.db_models import (
    User,
    Post,
    Comment,
    Achievement,
    UserAchievement,
    Poll,
    PollVote,
    Friendship,
    Bookmark,
)
from social_app.services.achievements import check_and_award_achievements, get_user_stat
from tests.test_base import AppTestCase


def seed_test_achievements():
    achievements_data = [
        {
            "name": "Test First Post",
            "description": "Desc1",
            "icon_url": "icon1",
            "criteria_type": "num_posts",
            "criteria_value": 1,
        },
        {
            "name": "Test 5 Posts",
            "description": "Desc2",
            "icon_url": "icon2",
            "criteria_type": "num_posts",
            "criteria_value": 5,
        },
        {
            "name": "Test First Comment",
            "description": "Desc3",
            "icon_url": "icon3",
            "criteria_type": "num_comments_given",
            "criteria_value": 1,
        },
    ]
    for ach_data in achievements_data:
        existing_achievement = Achievement.query.filter_by(
            name=ach_data["name"]
        ).first()
        if not existing_achievement:
            ach = Achievement(**ach_data)
            db.session.add(ach)
    db.session.commit()

    final_ach_ids = {
        ach_data["name"]: Achievement.query.filter_by(name=ach_data["name"]).first().id
        for ach_data in achievements_data
    }
    return final_ach_ids


class AchievementLogicTests(AppTestCase):

    def test_get_user_stat_num_posts(self):
        with self.app.app_context():
            user = self.user1
            self._create_db_post(user_id=user.id, title="Post 1")
            self._create_db_post(user_id=user.id, title="Post 2")
            stat = get_user_stat(user, "num_posts")
            self.assertEqual(stat, 2)

    def test_award_first_post_achievement(self):
        with self.app.app_context():
            ach_ids = seed_test_achievements()
            user = self.user2
            self._create_db_post(user_id=user.id, title="First Post by User2")
            check_and_award_achievements(user.id)
            first_post_ach_id = ach_ids["Test First Post"]
            user_ach = UserAchievement.query.filter_by(
                user_id=user.id, achievement_id=first_post_ach_id
            ).first()
            self.assertIsNotNone(user_ach)
            self.assertEqual(user_ach.achievement.name, "Test First Post")

    def test_award_multiple_achievements_incrementally(self):
        with self.app.app_context():
            ach_ids = seed_test_achievements()
            user = self.user3
            first_post_ach_id = ach_ids["Test First Post"]
            five_posts_ach_id = ach_ids["Test 5 Posts"]

            self._create_db_post(user_id=user.id, title="Incremental Post 1")
            check_and_award_achievements(user.id)

            user_ach_first = UserAchievement.query.filter_by(
                user_id=user.id, achievement_id=first_post_ach_id
            ).first()
            self.assertIsNotNone(user_ach_first)

            user_ach_five = UserAchievement.query.filter_by(
                user_id=user.id, achievement_id=five_posts_ach_id
            ).first()
            self.assertIsNone(user_ach_five)

            for i in range(2, 6):
                self._create_db_post(user_id=user.id, title=f"Incremental Post {i}")
            check_and_award_achievements(user.id)

            user_ach_five_updated = UserAchievement.query.filter_by(
                user_id=user.id, achievement_id=five_posts_ach_id
            ).first()
            self.assertIsNotNone(user_ach_five_updated)

            user_ach_first_still_there = UserAchievement.query.filter_by(
                user_id=user.id, achievement_id=first_post_ach_id
            ).first()
            self.assertIsNotNone(user_ach_first_still_there)

    def test_no_duplicate_achievements_awarded(self):
        with self.app.app_context():
            ach_ids = seed_test_achievements()
            user = self.user1
            first_post_ach_id = ach_ids["Test First Post"]

            self._create_db_post(user_id=user.id, title="Duplicate Test Post 1")
            check_and_award_achievements(user.id)

            count_initial = UserAchievement.query.filter_by(
                user_id=user.id, achievement_id=first_post_ach_id
            ).count()
            self.assertEqual(count_initial, 1)

            check_and_award_achievements(user.id)
            count_after_second_call = UserAchievement.query.filter_by(
                user_id=user.id, achievement_id=first_post_ach_id
            ).count()
            self.assertEqual(count_after_second_call, 1)

    def test_display_achievements_on_user_profile(self):
        with self.app.app_context():
            ach_ids = seed_test_achievements()
            user = User(
                username="profile_ach_user",
                email="pau@example.com",
                password_hash=generate_password_hash("password123"),
            )
            db.session.add(user)
            db.session.commit()
            user = User.query.filter_by(username="profile_ach_user").first()

            first_post_ach_id = ach_ids["Test First Post"]
            user_ach = UserAchievement(
                user_id=user.id, achievement_id=first_post_ach_id
            )
            db.session.add(user_ach)
            db.session.commit()

            response = self.client.get(f"/user/{user.username}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Test First Post", response.data.decode())

    def test_no_achievements_message_on_profile(self):
        with self.app.app_context():
            user = User(
                username="no_ach_user_profile",
                email="naup@example.com",
                password_hash=generate_password_hash("password123"),
            )
            db.session.add(user)
            db.session.commit()
            user = User.query.filter_by(username="no_ach_user_profile").first()

            response = self.client.get(f"/user/{user.username}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("No achievements yet", response.data.decode())

    def test_view_user_achievements_page_earned_and_all(self):
        with self.app.app_context():
            ach_ids = seed_test_achievements()
            user = User(
                username="all_ach_user_page",
                email="aaup@example.com",
                password_hash=generate_password_hash("password"),
            )
            db.session.add(user)
            db.session.commit()
            user = User.query.filter_by(username="all_ach_user_page").first()

            first_post_ach_id = ach_ids["Test First Post"]
            user_ach = UserAchievement(
                user_id=user.id, achievement_id=first_post_ach_id
            )
            db.session.add(user_ach)
            db.session.commit()

            self.login("all_ach_user_page", "password")
            response = self.client.get("/user/all_ach_user_page/achievements")
            self.assertEqual(response.status_code, 200)
            html_content = response.data.decode()

            self.assertIn("Test First Post", html_content)
            self.assertInHTML("Test First Post", html_content, "Test First Post")
            self.assertIn("Test 5 Posts", html_content)
            self.logout()

    def test_view_user_achievements_page_no_earned(self):
        with self.app.app_context():
            seed_test_achievements()
            user = User(
                username="no_earned_ach_page",
                email="neaup@example.com",
                password_hash=generate_password_hash("password"),
            )
            db.session.add(user)
            db.session.commit()
            user = User.query.filter_by(username="no_earned_ach_page").first()

            self.login("no_earned_ach_page", "password")
            response = self.client.get("/user/no_earned_ach_page/achievements")
            self.assertEqual(response.status_code, 200)
            html_content = response.data.decode()

            self.assertIn("has not earned any achievements yet", html_content.lower())
            self.assertIn("Test First Post", html_content)
            self.assertIn("Test 5 Posts", html_content)
            self.logout()

    def test_bookworm_achievement_awarded(self):
        with self.app.app_context():
            bookworm_ach_data = {
                "name": "Bookworm",
                "description": "Bookmarked 5 posts.",
                "icon_url": "[BOOKMARK_ICON]",
                "criteria_type": "num_bookmarks_created",
                "criteria_value": 5,
            }
            existing_bookworm = Achievement.query.filter_by(name="Bookworm").first()
            if not existing_bookworm:
                db.session.add(Achievement(**bookworm_ach_data))
                db.session.commit()

            bookworm_achievement_id = (
                Achievement.query.filter_by(name="Bookworm").first().id
            )

            bookmarker_user = self._create_db_user(
                "bookworm_user", "pass", "bw@example.com"
            )

            posts_to_bookmark = [
                self._create_db_post(self.user1_id, f"Bookmark Post {i+1}")
                for i in range(5)
            ]

            for i in range(4):
                self._create_db_bookmark(bookmarker_user.id, posts_to_bookmark[i].id)

            check_and_award_achievements(bookmarker_user.id)
            user_ach_check1 = UserAchievement.query.filter_by(
                user_id=bookmarker_user.id, achievement_id=bookworm_achievement_id
            ).first()
            self.assertIsNone(user_ach_check1)

            self._create_db_bookmark(bookmarker_user.id, posts_to_bookmark[4].id)
            check_and_award_achievements(bookmarker_user.id)

            user_ach_check2 = UserAchievement.query.filter_by(
                user_id=bookmarker_user.id, achievement_id=bookworm_achievement_id
            ).first()
            self.assertIsNotNone(user_ach_check2)
            self.assertEqual(user_ach_check2.achievement.name, "Bookworm")

            check_and_award_achievements(bookmarker_user.id)
            count_after_second_call = UserAchievement.query.filter_by(
                user_id=bookmarker_user.id, achievement_id=bookworm_achievement_id
            ).count()
            self.assertEqual(count_after_second_call, 1)

    def test_well_connected_achievement_awarded(self):
        with self.app.app_context():
            wc_ach_data = {
                "name": "Well-Connected",
                "description": "Built a network of 5 friends.",
                "icon_url": "[NETWORK_ICON]",
                "criteria_type": "num_friends",
                "criteria_value": 5,
            }
            if not Achievement.query.filter_by(name="Well-Connected").first():
                db.session.add(Achievement(**wc_ach_data))
                db.session.commit()
            wc_achievement_id = (
                Achievement.query.filter_by(name="Well-Connected").first().id
            )

            main_user = self._create_db_user("main_networker", "pass", "mn@example.com")
            friends_to_add = [
                self._create_db_user(f"friend_for_wc{i}", "pass", f"fwc{i}@example.com")
                for i in range(5)
            ]

            for i in range(4):
                self._create_db_friendship(
                    main_user, friends_to_add[i], status="accepted"
                )

            check_and_award_achievements(main_user.id)
            user_ach_check1 = UserAchievement.query.filter_by(
                user_id=main_user.id, achievement_id=wc_achievement_id
            ).first()
            self.assertIsNone(user_ach_check1)

            self._create_db_friendship(main_user, friends_to_add[4], status="accepted")
            check_and_award_achievements(main_user.id)

            user_ach_check2 = UserAchievement.query.filter_by(
                user_id=main_user.id, achievement_id=wc_achievement_id
            ).first()
            self.assertIsNotNone(user_ach_check2)
            self.assertEqual(user_ach_check2.achievement.name, "Well-Connected")

            check_and_award_achievements(main_user.id)
            count_after_second_call = UserAchievement.query.filter_by(
                user_id=main_user.id, achievement_id=wc_achievement_id
            ).count()
            self.assertEqual(count_after_second_call, 1)

    def test_opinion_leader_achievement_awarded(self):
        with self.app.app_context():
            ol_ach_data = {
                "name": "Opinion Leader",
                "description": "Voted in 5 different polls.",
                "icon_url": "[VOTER_ICON]",
                "criteria_type": "num_polls_voted",
                "criteria_value": 5,
            }
            if not Achievement.query.filter_by(name="Opinion Leader").first():
                db.session.add(Achievement(**ol_ach_data))
                db.session.commit()
            ol_achievement_id = (
                Achievement.query.filter_by(name="Opinion Leader").first().id
            )

            poll_voter = self._create_db_user(
                "poll_voter_user", "pass", "pv@example.com"
            )
            poll_creator = self.user1

            polls_to_vote_in_ids = []
            for i in range(5):
                poll_initial = self._create_db_poll(
                    user_id=poll_creator.id,
                    question=f"Poll {i+1} for Opinion Leader?",
                    options_texts=["Yes", "No"],
                )
                polls_to_vote_in_ids.append(poll_initial.id)

            for i in range(4):
                current_poll = db.session.get(Poll, polls_to_vote_in_ids[i])
                self.assertIsNotNone(current_poll)
                self.assertTrue(len(current_poll.options) > 0)
                option_to_vote = current_poll.options[0]
                self._create_db_poll_vote(
                    user_id=poll_voter.id,
                    poll_id=current_poll.id,
                    poll_option_id=option_to_vote.id,
                )

            check_and_award_achievements(poll_voter.id)
            user_ach_check1 = UserAchievement.query.filter_by(
                user_id=poll_voter.id, achievement_id=ol_achievement_id
            ).first()
            self.assertIsNone(user_ach_check1)

            fifth_poll_id = polls_to_vote_in_ids[4]
            fifth_poll_obj = db.session.get(Poll, fifth_poll_id)
            self.assertIsNotNone(
                fifth_poll_obj,
                f"Fifth poll with id {fifth_poll_id} not found for Opinion Leader test.",
            )
            self.assertTrue(
                len(fifth_poll_obj.options) > 0,
                f"Fifth poll {fifth_poll_obj.id} has no options.",
            )
            option_to_vote_5 = fifth_poll_obj.options[0]
            self._create_db_poll_vote(
                user_id=poll_voter.id,
                poll_id=fifth_poll_obj.id,
                poll_option_id=option_to_vote_5.id,
            )
            check_and_award_achievements(poll_voter.id)

            user_ach_check2 = UserAchievement.query.filter_by(
                user_id=poll_voter.id, achievement_id=ol_achievement_id
            ).first()
            self.assertIsNotNone(user_ach_check2)
            self.assertEqual(user_ach_check2.achievement.name, "Opinion Leader")

            check_and_award_achievements(poll_voter.id)
            count_after_second_call = UserAchievement.query.filter_by(
                user_id=poll_voter.id, achievement_id=ol_achievement_id
            ).count()
            self.assertEqual(count_after_second_call, 1)
