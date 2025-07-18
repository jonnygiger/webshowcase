import unittest
from social_app.core.utils import is_armstrong_number

class TestUtils(unittest.TestCase):

    def test_is_armstrong_number(self):
        self.assertTrue(is_armstrong_number(9))
        self.assertTrue(is_armstrong_number(153))
        self.assertFalse(is_armstrong_number(100))
        self.assertTrue(is_armstrong_number(370))
        self.assertTrue(is_armstrong_number(371))
        self.assertTrue(is_armstrong_number(407))
        self.assertFalse(is_armstrong_number(123))
        self.assertTrue(is_armstrong_number(1634))
        self.assertFalse(is_armstrong_number(2000))

if __name__ == '__main__':
    unittest.main()
