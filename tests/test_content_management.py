import unittest
from flask import url_for, jsonify
from tests.test_base import AppTestCase
from models import db, User, Post, Series, SeriesPost
from datetime import datetime, timezone, timedelta

class TestContentManagement(AppTestCase):

    def test_add_and_remove_post_from_series(self):
        with self.app.app_context():
            author = self.user1
            self.login(author.username, "password")

            # Create a series
            series_obj = self._create_db_series(user_id=author.id, title="My Test Series")

            # Create posts
            post1 = self._create_db_post(user_id=author.id, title="Post Alpha")
            post2 = self._create_db_post(user_id=author.id, title="Post Beta")
            post3 = self._create_db_post(user_id=author.id, title="Post Gamma")

            # Add Post1 to series
            self.client.post(url_for('add_post_to_series', series_id=series_obj.id, post_id=post1.id))
            # Add Post2 to series
            self.client.post(url_for('add_post_to_series', series_id=series_obj.id, post_id=post2.id))
            # Add Post3 to series
            self.client.post(url_for('add_post_to_series', series_id=series_obj.id, post_id=post3.id))

            series_reloaded = db.session.get(Series, series_obj.id)
            self.assertEqual(len(series_reloaded.posts), 3)
            self.assertEqual(series_reloaded.posts[0].id, post1.id) # Added first
            self.assertEqual(series_reloaded.posts[1].id, post2.id) # Added second
            self.assertEqual(series_reloaded.posts[2].id, post3.id) # Added third

            # Remove Post2 (the middle one)
            self.client.post(url_for('remove_post_from_series', series_id=series_obj.id, post_id=post2.id))

            series_reloaded_after_remove = db.session.get(Series, series_obj.id)
            self.assertEqual(len(series_reloaded_after_remove.posts), 2)
            # Check order is maintained and re-indexed
            self.assertEqual(series_reloaded_after_remove.posts[0].id, post1.id)
            self.assertEqual(series_reloaded_after_remove.posts[0].series_post_entries.filter_by(series_id=series_obj.id).first().order, 1)
            self.assertEqual(series_reloaded_after_remove.posts[1].id, post3.id)
            self.assertEqual(series_reloaded_after_remove.posts[1].series_post_entries.filter_by(series_id=series_obj.id).first().order, 2)

            self.logout()

    def test_reorder_posts_in_series(self):
        with self.app.app_context():
            author = self.user1
            self.login(author.username, "password")

            series_obj = self._create_db_series(user_id=author.id, title="Reorder Series")
            post1 = self._create_db_post(user_id=author.id, title="First")
            post2 = self._create_db_post(user_id=author.id, title="Second")
            post3 = self._create_db_post(user_id=author.id, title="Third")

            # Add posts in order: post1, post2, post3
            self._add_post_to_series_direct_db(series_id=series_obj.id, post_id=post1.id, order=0)
            self._add_post_to_series_direct_db(series_id=series_obj.id, post_id=post2.id, order=1)
            self._add_post_to_series_direct_db(series_id=series_obj.id, post_id=post3.id, order=2)

            db.session.commit() # Commit direct DB changes

            series_reloaded = db.session.get(Series, series_obj.id)
            initial_post_ids = [p.id for p in series_reloaded.posts]
            self.assertEqual(initial_post_ids, [post1.id, post2.id, post3.id])

            # New order: post3, post1, post2
            new_order_ids = [post3.id, post1.id, post2.id]
            response = self.client.post(
                url_for('reorder_series_posts', series_id=series_obj.id),
                json={'post_ids': new_order_ids}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['status'], 'success')

            series_reordered = db.session.get(Series, series_obj.id)
            final_post_ids = [p.id for p in series_reordered.posts]
            self.assertEqual(final_post_ids, new_order_ids)

            # Check the 'order' attribute in SeriesPost
            for i, post_id in enumerate(new_order_ids):
                sp_entry = SeriesPost.query.filter_by(series_id=series_obj.id, post_id=post_id).first()
                self.assertIsNotNone(sp_entry)
                self.assertEqual(sp_entry.order, i) # In app.py, reorder starts index from 0

            self.logout()

    def _add_post_to_series_direct_db(self, series_id, post_id, order):
        # Helper for direct DB manipulation for setup, not using app routes
        sp_entry = SeriesPost(series_id=series_id, post_id=post_id, order=order)
        db.session.add(sp_entry)
        # db.session.commit() # Commit outside or after all additions

    def test_delete_series_removes_associations_not_posts(self):
        with self.app.app_context():
            author = self.user1
            self.login(author.username, "password")

            series_obj = self._create_db_series(user_id=author.id, title="To Be Deleted Series")
            post1 = self._create_db_post(user_id=author.id, title="Post in Deleted Series")
            post2 = self._create_db_post(user_id=author.id, title="Another Post in Deleted Series")

            self._add_post_to_series_direct_db(series_id=series_obj.id, post_id=post1.id, order=0)
            self._add_post_to_series_direct_db(series_id=series_obj.id, post_id=post2.id, order=1)
            db.session.commit()

            series_id = series_obj.id
            post1_id = post1.id
            post2_id = post2.id

            # Re-fetch series_obj to ensure it's session-bound before accessing author
            series_obj_reloaded = db.session.get(Series, series_id)
            self.assertIsNotNone(series_obj_reloaded, "Failed to reload series object.")
            author_username = series_obj_reloaded.author.username # Get username before deletion

            # Verify associations exist
            self.assertEqual(SeriesPost.query.filter_by(series_id=series_id).count(), 2)

            # Delete the series
            response = self.client.post(url_for('delete_series', series_id=series_id), follow_redirects=True)
            self.assertEqual(response.status_code, 200) # Redirects to user profile
            # Ensure the redirect went to the correct user's profile page
            self.assertTrue(response.request.path.endswith(f'/user/{author_username}'))


            # Verify series is deleted
            self.assertIsNone(db.session.get(Series, series_id))
            # Verify SeriesPost associations are deleted (due to cascade)
            self.assertEqual(SeriesPost.query.filter_by(series_id=series_id).count(), 0)
            # Verify posts themselves still exist
            self.assertIsNotNone(db.session.get(Post, post1_id))
            self.assertIsNotNone(db.session.get(Post, post2_id))

            self.logout()

    def test_cannot_add_another_users_post_to_series(self):
        with self.app.app_context():
            series_owner = self.user1
            other_user = self.user2
            self.login(series_owner.username, "password")

            series_obj = self._create_db_series(user_id=series_owner.id, title="My Exclusive Series")
            # Post created by another user
            post_by_other = self._create_db_post(user_id=other_user.id, title="Other User's Post")

            response = self.client.post(
                url_for('add_post_to_series', series_id=series_obj.id, post_id=post_by_other.id),
                follow_redirects=True
            )
            self.assertEqual(response.status_code, 200) # The route redirects
            # Check for flash message
            self.assertIn(b"You can only add your own posts to your series.", response.data)

            # Verify post was not added
            series_reloaded = db.session.get(Series, series_obj.id)
            self.assertEqual(len(series_reloaded.posts), 0)

            self.logout()

    def test_edit_post_updates_title_content_and_last_edited(self):
        with self.app.app_context():
            author = self.user1
            self.login(author.username, "password")

            original_timestamp = datetime.now(timezone.utc) - timedelta(days=1)
            post_obj = self._create_db_post(user_id=author.id, title="Original Title", content="Original Content", timestamp=original_timestamp)
            post_id = post_obj.id

            # Ensure last_edited is initially None
            self.assertIsNone(post_obj.last_edited)
            # And that the original timestamp is preserved (with tolerance for DB precision)
            # Make post_obj.timestamp (naive from DB) aware of UTC for comparison
            self.assertAlmostEqual(post_obj.timestamp.replace(tzinfo=timezone.utc), original_timestamp, delta=timedelta(seconds=1))

            new_title = "Updated Super Title"
            new_content = "This is the new, updated content for the post."
            new_hashtags = "#updated,#awesome"

            # Allow a small time difference for the update
            time_before_edit = datetime.now(timezone.utc) - timedelta(seconds=1)

            response = self.client.post(url_for('edit_post', post_id=post_id), data={
                'title': new_title,
                'content': new_content,
                'hashtags': new_hashtags
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200) # Redirects to view_post

            time_after_edit = datetime.now(timezone.utc) + timedelta(seconds=1)

            # Verify on view_post page
            self.assertIn(bytes(new_title, 'utf-8'), response.data)
            self.assertIn(bytes(new_content, 'utf-8'), response.data)
            self.assertIn(b"#updated", response.data) # Check for hashtag in rendered page

            # Verify in DB
            edited_post = db.session.get(Post, post_id)
            self.assertEqual(edited_post.title, new_title)
            self.assertEqual(edited_post.content, new_content)
            self.assertEqual(edited_post.hashtags, new_hashtags)
            self.assertIsNotNone(edited_post.last_edited)
            # Make edited_post.last_edited (naive from DB) aware for comparison
            edited_post_last_edited_aware = edited_post.last_edited.replace(tzinfo=timezone.utc)
            self.assertTrue(time_before_edit <= edited_post_last_edited_aware <= time_after_edit)
            self.assertNotEqual(edited_post.timestamp.replace(tzinfo=timezone.utc), edited_post_last_edited_aware) # Compare aware datetimes

            self.logout()

if __name__ == '__main__':
    unittest.main()
