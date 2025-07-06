import os
import unittest
import json
import io
from unittest.mock import patch, call, ANY

from datetime import (
    datetime,
    timedelta,
)
from werkzeug.security import generate_password_hash

from tests.test_base import AppTestCase


class TestMinimalSanityCheck(unittest.TestCase):
    def test_absolutely_nothing(self):
        self.assertTrue(True)
