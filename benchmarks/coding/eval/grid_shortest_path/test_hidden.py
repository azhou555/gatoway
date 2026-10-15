import unittest
from solution import shortest_path

class HiddenTests(unittest.TestCase):
    def test_0(self):
        self.assertEqual(shortest_path(*([[0, 0], [1, 0]],)), 2)
    def test_1(self):
        self.assertEqual(shortest_path(*([[0]],)), 0)
    def test_2(self):
        self.assertEqual(shortest_path(*([[1]],)), -1)
    def test_3(self):
        self.assertEqual(shortest_path(*([],)), -1)
    def test_4(self):
        self.assertEqual(shortest_path(*([[0, 1], [1, 0]],)), -1)
    def test_5(self):
        self.assertEqual(shortest_path(*([[0, 0, 0], [1, 1, 0]],)), 3)
    def test_6(self):
        self.assertEqual(shortest_path(*([[0, 0, 0], [0, 1, 0], [0, 0, 0]],)), 4)
