import unittest
from solution import merge_intervals

class HiddenTests(unittest.TestCase):
    def test_0(self):
        self.assertEqual(merge_intervals(*([[1, 3], [2, 6], [8, 10], [15, 18]],)), [[1, 6], [8, 10], [15, 18]])
    def test_1(self):
        self.assertEqual(merge_intervals(*([[5, 7], [1, 5]],)), [[1, 7]])
    def test_2(self):
        self.assertEqual(merge_intervals(*([],)), [])
    def test_3(self):
        self.assertEqual(merge_intervals(*([[1, 10], [2, 3], [4, 8]],)), [[1, 10]])
    def test_4(self):
        self.assertEqual(merge_intervals(*([[-3, -1], [-1, 0], [2, 2]],)), [[-3, 0], [2, 2]])
    def test_5(self):
        self.assertEqual(merge_intervals(*([[1, 1]],)), [[1, 1]])
