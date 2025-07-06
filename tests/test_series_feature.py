import unittest
from datetime import datetime, timedelta
from flask import url_for
from tests.test_base import AppTestCase
import json


class TestSeriesFeature(AppTestCase):

    @unittest.skip("Placeholder test")
    def test_series_model_creation(self):
        pass

    @unittest.skip("Placeholder test")
    def test_series_post_association_and_order(self):
        pass

    @unittest.skip("Placeholder test")
    def test_cascade_delete_user_to_series(self):
        pass

    @unittest.skip("Placeholder test")
    def test_cascade_delete_series_to_series_post(self):
        pass

    def test_cascade_delete_series_to_series_post_association(self):
        from social_app import db
        from social_app.models.db_models import (
            User,
            Post,
            Series,
            SeriesPost,
        )

        with self.app.app_context():
            user = self.user1

            series_title = "Series to Delete"
            series_description = "This series will be deleted to test cascade."

            original_series_obj = self._create_series(
                user_id=user.id, title=series_title, description=series_description
            )
            db.session.add(original_series_obj)
            series_id = original_series_obj.id
            self.assertIsNotNone(series_id)
            series = self.db.session.get(Series, series_id)
            self.assertIsNotNone(series)

            post1_title = "Post 1 for Cascade Test"
            post2_title = "Post 2 for Cascade Test"

            original_post1_obj = self._create_db_post(
                user_id=user.id, title=post1_title
            )
            db.session.add(original_post1_obj)
            post1_id = original_post1_obj.id
            self.assertIsNotNone(post1_id)
            post1 = self.db.session.get(Post, post1_id)
            self.assertIsNotNone(post1)

            original_post2_obj = self._create_db_post(
                user_id=user.id, title=post2_title
            )
            db.session.add(original_post2_obj)
            post2_id = original_post2_obj.id
            self.assertIsNotNone(post2_id)
            post2 = self.db.session.get(Post, post2_id)
            self.assertIsNotNone(post2)

            sp1 = SeriesPost(series_id=series_id, post_id=post1_id, order=0)
            sp2 = SeriesPost(series_id=series_id, post_id=post2_id, order=1)
            db.session.add_all([sp1, sp2])
            db.session.commit()

            series_post_entries_before_delete = SeriesPost.query.filter_by(
                series_id=series_id
            ).all()
            self.assertEqual(len(series_post_entries_before_delete), 2)

            db.session.refresh(series)
            self.assertEqual(len(series.posts), 2)
            self.assertIn(post1, series.posts)
            self.assertIn(post2, series.posts)

            series_obj_reloaded = db.session.get(Series, series_id)
            self.assertIsNotNone(series_obj_reloaded)
            author_username = series_obj_reloaded.author.username

            response = self.client.post(
                url_for("core.delete_series", series_id=series_id), follow_redirects=True
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.request.path.endswith(f"/user/{author_username}"))

            deleted_series = self.db.session.get(Series, series_id)
            self.assertIsNone(deleted_series)
            series_post_entries_after_delete = SeriesPost.query.filter_by(
                series_id=series_id
            ).all()
            self.assertEqual(len(series_post_entries_after_delete), 0)
            self.assertIsNotNone(self.db.session.get(Post, post1_id))
            self.assertIsNotNone(self.db.session.get(Post, post2_id))

    @unittest.skip("Placeholder test")
    def test_cascade_delete_post_to_series_post(self):
        pass

    def test_create_series_page_load(self):
        self.login(self.user1.username, "password")
        response = self.client.get(url_for('core.create_series'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Create New Series", response.data)
        self.logout()

    def test_create_series_unauthenticated(self):
        response = self.client.get(url_for('core.create_series'), follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn(url_for('core.login'), response.location)

        response_post = self.client.post(
            url_for('core.create_series'), data={"title": "Fail Series"}, follow_redirects=False
        )
        self.assertEqual(response_post.status_code, 302)
        self.assertIn(url_for('core.login'), response_post.location)

    @unittest.skip("Placeholder test")
    def test_create_series_post_success(self):
        self.login(self.user1.username, "password")
        self.logout()
        pass

    @unittest.skip("Placeholder test")
    def test_create_series_post_no_title(self):
        self.login(self.user1.username, "password")
        self.logout()
        pass

    @unittest.skip("Placeholder test")
    def test_view_series_page(self):
        pass

    def test_view_series_not_found(self):
        response = self.client.get(url_for('core.view_series', series_id=9999))
        self.assertEqual(response.status_code, 404)

    def test_view_existing_series_page(self):
        self.login(self.user1.username, "password")
        series_obj = self._create_series(
            user_id=self.user1_id,
            title="My Test Series",
            description="This is a test series.",
        )
        with self.app.app_context():
            series_in_session = self.db.session.merge(series_obj)
            series_id_val = series_in_session.id
            self.assertIsNotNone(series_id_val)

        response = self.client.get(url_for('core.view_series', series_id=series_id_val))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"My Test Series", response.data)
        self.assertIn(b"This is a test series.", response.data)
        self.logout()

    @unittest.skip("Placeholder test")
    def test_edit_series_page_load_author(self):
        self.login(self.user1.username, "password")
        self.logout()
        pass

    @unittest.skip("Placeholder test")
    def test_add_post_to_series_success(self):
        self.login(self.user1.username, "password")
        self.logout()
        pass

    @unittest.skip("Placeholder test")
    def test_user_profile_lists_series(self):
        pass

    @unittest.skip("Placeholder test")
    def test_view_post_lists_series_and_navigation(self):
        pass

    def test_reorder_posts_in_series(self):
        from social_app import db
        from social_app.models.db_models import Series, Post, SeriesPost

        self.login(self.user1.username, "password")
        series = self._create_series(user_id=self.user1_id, title="Reorder Test Series")

        with self.app.app_context():
            post1 = self._create_db_post(user_id=self.user1_id, title="Post Alpha")
            post2 = self._create_db_post(user_id=self.user1_id, title="Post Beta")
            post3 = self._create_db_post(user_id=self.user1_id, title="Post Gamma")

            self.assertIsNotNone(post1)
            self.assertIsNotNone(post2)
            self.assertIsNotNone(post3)

            series_merged = db.session.merge(series)

            sp1 = SeriesPost(series_id=series_merged.id, post_id=post1.id, order=0)
            sp2 = SeriesPost(series_id=series_merged.id, post_id=post2.id, order=1)
            sp3 = SeriesPost(series_id=series_merged.id, post_id=post3.id, order=2)
            db.session.add_all([sp1, sp2, sp3])
            db.session.commit()

            db.session.refresh(series_merged)
            initial_ordered_posts = series_merged.posts
            self.assertEqual(len(initial_ordered_posts), 3)
            self.assertEqual(initial_ordered_posts[0].id, post1.id)
            self.assertEqual(initial_ordered_posts[1].id, post2.id)
            self.assertEqual(initial_ordered_posts[2].id, post3.id)

        new_order_ids = [post3.id, post1.id, post2.id]
        response = self.client.post(
            url_for('core.reorder_series_posts', series_id=series.id),
            data=json.dumps({"post_ids": new_order_ids}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, f"Error: {response.json}")
        self.assertIsNotNone(response.json)
        self.assertEqual(response.json.get("status"), "success")

        with self.app.app_context():
            series_after_reorder = db.session.merge(series)
            db.session.refresh(series_after_reorder)
            ordered_posts_after_reorder = series_after_reorder.posts

            self.assertEqual(len(ordered_posts_after_reorder), 3)
            self.assertEqual(ordered_posts_after_reorder[0].id, post3.id)
            self.assertEqual(ordered_posts_after_reorder[1].id, post1.id)
            self.assertEqual(ordered_posts_after_reorder[2].id, post2.id)

            sp_post1_updated = SeriesPost.query.filter_by(
                series_id=series_after_reorder.id, post_id=post1.id
            ).first()
            sp_post2_updated = SeriesPost.query.filter_by(
                series_id=series_after_reorder.id, post_id=post2.id
            ).first()
            sp_post3_updated = SeriesPost.query.filter_by(
                series_id=series_after_reorder.id, post_id=post3.id
            ).first()

            self.assertIsNotNone(sp_post1_updated)
            self.assertIsNotNone(sp_post2_updated)
            self.assertIsNotNone(sp_post3_updated)

            self.assertEqual(sp_post3_updated.order, 0)
            self.assertEqual(sp_post1_updated.order, 1)
            self.assertEqual(sp_post2_updated.order, 2)

        self.logout()
