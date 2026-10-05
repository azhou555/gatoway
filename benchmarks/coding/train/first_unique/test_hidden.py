import unittest
from solution import first_unique

class HiddenTests(unittest.TestCase):
    def test_0(self):
        self.assertEqual(first_unique(*('leetcode',)), 0)
    def test_1(self):
        self.assertEqual(first_unique(*('loveleetcode',)), 2)
    def test_2(self):
        self.assertEqual(first_unique(*('aabb',)), -1)
    def test_3(self):
        self.assertEqual(first_unique(*('',)), -1)
    def test_4(self):
        self.assertEqual(first_unique(*('aA',)), 0)
    def test_5(self):
        self.assertEqual(first_unique(*('ééa',)), 2)
