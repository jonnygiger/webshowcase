import unittest


class TestSanity(unittest.TestCase):
    def test_absolutely_nothing(self):
        import sys

        print(f"Python path: {sys.path}")
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
