import unittest


class TestSanity(unittest.TestCase):
    def test_absolutely_nothing(self):
        import sys

        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
