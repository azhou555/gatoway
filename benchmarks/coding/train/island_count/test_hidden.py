import unittest
from solution import island_count

class HiddenTests(unittest.TestCase):
    def test_0(self):
        self.assertEqual(island_count(*([[1, 1, 0], [0, 1, 0], [1, 0, 1]],)), 3)
    def test_1(self):
        self.assertEqual(island_count(*([],)), 0)
    def test_2(self):
        self.assertEqual(island_count(*([[0, 0]],)), 0)
    def test_3(self):
        self.assertEqual(island_count(*([[1, 1], [1, 1]],)), 1)
    def test_4(self):
        self.assertEqual(island_count(*([[1, 0], [0, 1]],)), 2)
    def test_5(self):
        self.assertEqual(island_count(*([[1, 0, 1, 0, 1]],)), 3)
