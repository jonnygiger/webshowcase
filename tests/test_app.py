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
        with self.app.app_context():
            # The tables should be created as part of the app setup in AppTestCase
            # We can check if a known table exists
            from social_app.models.db_models import User  # Import a model to check its table
            self.assertTrue(db.engine.has_table(User.__tablename__))
