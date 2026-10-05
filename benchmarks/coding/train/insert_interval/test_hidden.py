import unittest
from solution import insert_interval

class HiddenTests(unittest.TestCase):
    def test_0(self):
        self.assertEqual(insert_interval(*([[1, 3], [6, 9]], [2, 5])), [[1, 5], [6, 9]])
    def test_1(self):
        self.assertEqual(insert_interval(*([], [1, 2])), [[1, 2]])
    def test_2(self):
        self.assertEqual(insert_interval(*([[1, 2], [4, 5]], [2, 4])), [[1, 5]])
    def test_3(self):
        self.assertEqual(insert_interval(*([[2, 3]], [0, 1])), [[0, 1], [2, 3]])
    def test_4(self):
        self.assertEqual(insert_interval(*([[1, 10]], [3, 4])), [[1, 10]])
    def test_5(self):
        self.assertEqual(insert_interval(*([[1, 2]], [4, 6])), [[1, 2], [4, 6]])
