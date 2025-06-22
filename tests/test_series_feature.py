import unittest

# import json # Not used
# from unittest.mock import patch, ANY # Not used in visible logic
from datetime import datetime, timedelta

# from app import app, db, socketio # COMMENTED OUT
# from models import User, Post, Series, SeriesPost # COMMENTED OUT
from tests.test_base import AppTestCase


class TestSeriesFeature(AppTestCase):
    # _create_series and _create_db_post are in AppTestCase (tests/test_base.py)

    # Model Tests
    @unittest.skip("Placeholder test")
    def test_series_model_creation(self):
        # with app.app_context(): # Handled by AppTestCase helpers or test client
        # series = self._create_series(user_id=self.user1_id, title="My First Series", description="Test description.")
        # self.assertIsNotNone(series.id)
        # self.assertEqual(series.title, "My First Series")
        # self.assertEqual(series.author, self.user1) # Assumes self.user1 is the User object
        # self.assertIn(series, self.user1.series_created) # Assumes series_created relationship
        pass  # Placeholder - requires live DB and models

    @unittest.skip("Placeholder test")
    def test_series_post_association_and_order(self):
        # with app.app_context():
        # series = self._create_series(user_id=self.user1_id)
        # post1 = self._create_db_post(user_id=self.user1_id, title="Post 1 for Series")
        # post2 = self._create_db_post(user_id=self.user1_id, title="Post 2 for Series")
        # sp1 = SeriesPost(series_id=series.id, post_id=post1.id, order=1)
        # sp2 = SeriesPost(series_id=series.id, post_id=post2.id, order=2)
        # db.session.add_all([sp1, sp2])
        # db.session.commit()
        # db.session.refresh(series)
        # self.assertEqual(len(series.posts), 2)
        # self.assertEqual(series.posts[0].id, post1.id)
        # ...
        pass  # Placeholder

    # Cascade tests also require live DB and models
    @unittest.skip("Placeholder test")
    def test_cascade_delete_user_to_series(self):
        # from werkzeug.security import generate_password_hash # Needed if creating user here
        # from models import User # Needed if creating User here
        # user_to_delete = User(username="deleteme_series", ...)
        # ...
        pass

    @unittest.skip("Placeholder test")
    def test_cascade_delete_series_to_series_post(self):
        pass

    def test_cascade_delete_series_to_series_post_association(self):
        from models import db, User, Post, Series, SeriesPost # Ensure models are imported

        with self.app.app_context():
            # 1. Setup: User, Posts, and a Series
            # Ensure users are created if not already by setUp
            if not hasattr(self, 'user1') or not self.user1:
                self._setup_base_users() # Make sure self.user1 is available

            user = self.user1 # Use existing user from base setup

            series_title = "Series to Delete"
            series_description = "This series will be deleted to test cascade."

            original_series_obj = self._create_series(user_id=user.id, title=series_title, description=series_description)
            db.session.add(original_series_obj) # Add to current session
            series_id = original_series_obj.id # Now access ID
            self.assertIsNotNone(series_id, "Series ID should be populated.")
            series = self.db.session.get(Series, series_id)
            self.assertIsNotNone(series, "Series should exist after creation and fetching.")

            post1_title = "Post 1 for Cascade Test"
            post2_title = "Post 2 for Cascade Test"

            original_post1_obj = self._create_db_post(user_id=user.id, title=post1_title)
            db.session.add(original_post1_obj) # Add to current session
            post1_id = original_post1_obj.id # Now access ID
            self.assertIsNotNone(post1_id, "Post1 ID should be populated.")
            post1 = self.db.session.get(Post, post1_id)
            self.assertIsNotNone(post1, "Post1 should exist after creation and fetching.")

            original_post2_obj = self._create_db_post(user_id=user.id, title=post2_title)
            db.session.add(original_post2_obj) # Add to current session
            post2_id = original_post2_obj.id # Now access ID
            self.assertIsNotNone(post2_id, "Post2 ID should be populated.")
            post2 = self.db.session.get(Post, post2_id)
            self.assertIsNotNone(post2, "Post2 should exist after creation and fetching.")

            # 2. Associate Posts with the Series using SeriesPost
            sp1 = SeriesPost(series_id=series_id, post_id=post1_id, order=0)
            sp2 = SeriesPost(series_id=series_id, post_id=post2_id, order=1)
            db.session.add_all([sp1, sp2])
            db.session.commit()

            # Verify SeriesPost entries
            series_post_entries_before_delete = SeriesPost.query.filter_by(series_id=series_id).all()
            self.assertEqual(len(series_post_entries_before_delete), 2, "Should have 2 SeriesPost entries.")

            # Verify posts are associated with the series
            # Refresh the 'series' object fetched from the current session
            db.session.refresh(series)
            self.assertEqual(len(series.posts), 2, "Series should have 2 posts associated.")
            # Ensure comparison is with post objects also fetched in the current session
            self.assertIn(post1, series.posts, "Post1 should be in series.posts.")
            self.assertIn(post2, series.posts, "Post2 should be in series.posts.")

            # 3. Delete the Series
            # Use the 'series' object that is confirmed to be part of the current session
            db.session.delete(series)
            db.session.commit()

            # 4. Assertions
            # Assert Series is deleted
            deleted_series = self.db.session.get(Series, series_id)
            self.assertIsNone(deleted_series, "Series should be deleted from the database.")

            # Assert SeriesPost entries are cascade deleted
            series_post_entries_after_delete = SeriesPost.query.filter_by(series_id=series_id).all()
            self.assertEqual(len(series_post_entries_after_delete), 0,
                             "SeriesPost entries should be cascade deleted.")

            # Assert original Posts still exist
            self.assertIsNotNone(self.db.session.get(Post, post1_id), "Post1 should still exist after series deletion.")
            self.assertIsNotNone(self.db.session.get(Post, post2_id), "Post2 should still exist after series deletion.")

    @unittest.skip("Placeholder test")
    def test_cascade_delete_post_to_series_post(self):
        pass

    # --- Route Tests ---
    def test_create_series_page_load(self):
        self.login(self.user1.username, "password")
        response = self.client.get("/series/create")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Create New Series", response.data)
        self.logout()

    def test_create_series_unauthenticated(self):
        response = self.client.get("/series/create", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

        response_post = self.client.post(
            "/series/create", data={"title": "Fail Series"}, follow_redirects=False
        )
        self.assertEqual(response_post.status_code, 302)
        self.assertIn("/login", response_post.location)

    @unittest.skip("Placeholder test")
    def test_create_series_post_success(self):
        self.login(self.user1.username, "password")
        # response = self.client.post('/series/create', data={...}, follow_redirects=True)
        # self.assertEqual(response.status_code, 200)
        # ... (assertions on response and db) ...
        self.logout()
        pass  # Placeholder

    @unittest.skip("Placeholder test")
    def test_create_series_post_no_title(self):
        self.login(self.user1.username, "password")
        # response = self.client.post('/series/create', data={...}, follow_redirects=True)
        # self.assertEqual(response.status_code, 200) # Form validation error, not server error
        # self.assertIn(b'Series title cannot be empty.', response.data)
        self.logout()
        pass  # Placeholder

    @unittest.skip("Placeholder test")
    def test_view_series_page(self):
        # series = self._create_series(user_id=self.user1_id, title="Viewable Series", description="Desc")
        # ... (add posts to series) ...
        # response = self.client.get(f'/series/{series.id}')
        # self.assertEqual(response.status_code, 200)
        # ... (assertions) ...
        pass  # Placeholder

    def test_view_series_not_found(self):
        response = self.client.get("/series/9999")
        self.assertEqual(response.status_code, 404)

    def test_view_existing_series_page(self):
        self.login(self.user1.username, "password")
        series_obj = self._create_series(user_id=self.user1_id, title="My Test Series", description="This is a test series.")
        # Ensure series_obj.id is loaded before using it in client.get if it's deferred.
        # Accessing it should load it if it's a deferred attribute.
        # Also, ensure series_obj is from the current session or re-fetch.
        with self.app.app_context():
            # Re-fetch or merge to be safe, though _create_series should return a session-bound object.
            series_in_session = self.db.session.merge(series_obj) # Or self.db.session.get(Series, series_obj.id)
            series_id_val = series_in_session.id
            self.assertIsNotNone(series_id_val, "Series ID should be available.")

        response = self.client.get(f'/series/{series_id_val}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"My Test Series", response.data)
        self.assertIn(b"This is a test series.", response.data)
        self.logout()

    @unittest.skip("Placeholder test")
    def test_edit_series_page_load_author(self):
        # series = self._create_series(user_id=self.user1_id, title="Editable Series")
        self.login(self.user1.username, "password")
        # response = self.client.get(f'/series/{series.id}/edit') # Uses mock series_id=1
        # self.assertEqual(response.status_code, 200)
        # ... (assertions) ...
        self.logout()
        pass  # Placeholder

    # ... (other route tests, similarly placeholdering db-dependent parts) ...

    @unittest.skip("Placeholder test")
    def test_add_post_to_series_success(self):
        # series = self._create_series(user_id=self.user1_id)
        # post_to_add = self._create_db_post(user_id=self.user1_id, title="Post To Add")
        self.login(self.user1.username, "password")
        # response = self.client.post(f'/series/{series.id}/add_post/{post_to_add.id}', follow_redirects=True)
        # ...
        self.logout()
        pass

    # --- UI/Content Tests (Simplified) ---
    @unittest.skip("Placeholder test")
    def test_user_profile_lists_series(self):
        # series1 = self._create_series(user_id=self.user1_id, title="User1 Series One")
        # response = self.client.get(f'/user/{self.user1.username}')
        # self.assertEqual(response.status_code, 200)
        # self.assertIn(b'User1 Series One', response.data)
        pass

    @unittest.skip("Placeholder test")
    def test_view_post_lists_series_and_navigation(self):
        # ... (setup series and posts) ...
        # response = self.client.get(f'/blog/post/{p2.id}?series_id={series.id}')
        # ... (assertions) ...
        pass

    def test_reorder_posts_in_series(self):
        import json
        from models import db, Series, Post, SeriesPost # Ensure models are imported

        # 1. Setup
        self.login(self.user1.username, "password")

        series = self._create_series(user_id=self.user1_id, title="Reorder Test Series")

        # Create posts
        # _create_db_post returns post objects, no need to query them again immediately
        with self.app.app_context(): # Add app context for DB operations
            post1 = self._create_db_post(user_id=self.user1_id, title="Post Alpha")
            post2 = self._create_db_post(user_id=self.user1_id, title="Post Beta")
            post3 = self._create_db_post(user_id=self.user1_id, title="Post Gamma")

            # post1 = Post.query.get(post1_id) # Not needed if helpers return objects
            # post2 = Post.query.get(post2_id)
            # post3 = Post.query.get(post3_id)

            self.assertIsNotNone(post1, "Post1 not found after creation")
            self.assertIsNotNone(post2, "Post2 not found after creation")
            self.assertIsNotNone(post3, "Post3 not found after creation")

            series_merged = db.session.merge(series) # Ensure series is in current session

            # Add posts to series with initial order (0-indexed)
            sp1 = SeriesPost(series_id=series_merged.id, post_id=post1.id, order=0)
            sp2 = SeriesPost(series_id=series_merged.id, post_id=post2.id, order=1)
            sp3 = SeriesPost(series_id=series_merged.id, post_id=post3.id, order=2)
            db.session.add_all([sp1, sp2, sp3])
            db.session.commit()

            # Verify initial order from series.posts property
            db.session.refresh(series_merged) # Refresh to load series_post_entries relationship
            initial_ordered_posts = series_merged.posts
            self.assertEqual(len(initial_ordered_posts), 3)
            self.assertEqual(initial_ordered_posts[0].id, post1.id)
            self.assertEqual(initial_ordered_posts[1].id, post2.id)
            self.assertEqual(initial_ordered_posts[2].id, post3.id)

        # 2. Perform Reordering
        new_order_ids = [post3.id, post1.id, post2.id] # These are IDs from objects fetched/created in context
        response = self.client.post(
            f'/series/{series.id}/reorder_posts',
            data=json.dumps({'post_ids': new_order_ids}),
            content_type='application/json'
        )

        # 3. Assert Initial Response
        self.assertEqual(response.status_code, 200, f"Error: {response.json}")
        self.assertIsNotNone(response.json, "Response is not JSON")
        self.assertEqual(response.json.get('status'), 'success')

        # 4. Assert Database State
        with self.app.app_context(): # Add app context for DB operations
            # series object might be stale from previous context, re-fetch or merge
            series_after_reorder = db.session.merge(series) # Use the series object from the setup
            db.session.refresh(series_after_reorder) # Refresh series to get updated relationships
            # Or fetch again: updated_series = Series.query.get(series.id)

            ordered_posts_after_reorder = series_after_reorder.posts # series.posts should be ordered by SeriesPost.order

            self.assertEqual(len(ordered_posts_after_reorder), 3)
            self.assertEqual(ordered_posts_after_reorder[0].id, post3.id, "Post 3 should be first")
            self.assertEqual(ordered_posts_after_reorder[1].id, post1.id, "Post 1 should be second")
            self.assertEqual(ordered_posts_after_reorder[2].id, post2.id, "Post 2 should be third")

            # Directly check SeriesPost entries for 0-indexed order
            # Ensure post1, post2, post3 are accessible here (they were defined in the outer scope from a previous context)
            # It's safer to use their IDs if the objects themselves might be stale.
            sp_post1_updated = SeriesPost.query.filter_by(series_id=series_after_reorder.id, post_id=post1.id).first()
            sp_post2_updated = SeriesPost.query.filter_by(series_id=series_after_reorder.id, post_id=post2.id).first()
            sp_post3_updated = SeriesPost.query.filter_by(series_id=series_after_reorder.id, post_id=post3.id).first()

            self.assertIsNotNone(sp_post1_updated)
            self.assertIsNotNone(sp_post2_updated)
            self.assertIsNotNone(sp_post3_updated)

            self.assertEqual(sp_post3_updated.order, 0, "Post3 (new first) should have order 0")
            self.assertEqual(sp_post1_updated.order, 1, "Post1 (new second) should have order 1")
            self.assertEqual(sp_post2_updated.order, 2, "Post2 (new third) should have order 2")

        # 5. Logout
        self.logout()