import unittest
from flask import Flask
from social_app import create_app, db
from tests.test_base import AppTestCase

print("Executing tests/test_app.py")

class TestApp(AppTestCase):
    def test_app_creation(self):
        """Test if the Flask app is created and is an instance of Flask."""
        self.assertIsInstance(self.app, Flask)

    def test_app_config(self):
        """Test if the app is in 'testing' mode."""
        self.assertTrue(self.app.config['TESTING'])

    def test_database_initialization(self):
        """Test if the database is initialized and tables are created."""
        from sqlalchemy import inspect
        from social_app.models.db_models import User, Post
        with self.app.app_context():
            inspector = inspect(db.engine)
            self.assertTrue(inspector.has_table(User.__tablename__))
            self.assertTrue(inspector.has_table(Post.__tablename__))
