import unittest
from solution import two_sum_pairs

class HiddenTests(unittest.TestCase):
    def test_0(self):
        self.assertEqual(two_sum_pairs(*([2, 7, 11, 15], 9)), [[0, 1]])
    def test_1(self):
        self.assertEqual(two_sum_pairs(*([3, 3, 3], 6)), [[0, 1], [0, 2], [1, 2]])
    def test_2(self):
        self.assertEqual(two_sum_pairs(*([], 0)), [])
    def test_3(self):
        self.assertEqual(two_sum_pairs(*([0, 0, 0, 0], 0)), [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]])
    def test_4(self):
        self.assertEqual(two_sum_pairs(*([-2, 0, 2, 4], 2)), [[0, 3], [1, 2]])
    def test_5(self):
        self.assertEqual(two_sum_pairs(*([1], 2)), [])
    def test_6(self):
        self.assertEqual(two_sum_pairs(*([1, 2, 3, 4], 20)), [])

    def test_does_not_mutate_input(self):
        nums = [4, 1, 3, 0]
        original = nums[:]
        two_sum_pairs(nums, 4)
        self.assertEqual(nums, original)
