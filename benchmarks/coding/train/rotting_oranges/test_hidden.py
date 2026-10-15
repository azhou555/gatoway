import unittest
from solution import rotting_oranges

class HiddenTests(unittest.TestCase):
    def test_0(self):
        self.assertEqual(rotting_oranges(*([[2, 1, 1], [1, 1, 0], [0, 1, 1]],)), 4)
    def test_1(self):
        self.assertEqual(rotting_oranges(*([[2, 1, 1], [0, 1, 1], [1, 0, 1]],)), -1)
    def test_2(self):
        self.assertEqual(rotting_oranges(*([[0, 2]],)), 0)
    def test_3(self):
        self.assertEqual(rotting_oranges(*([],)), 0)
    def test_4(self):
        self.assertEqual(rotting_oranges(*([[1]],)), -1)
    def test_5(self):
        self.assertEqual(rotting_oranges(*([[2, 1, 1, 2]],)), 1)
