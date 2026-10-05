import unittest
from solution import meeting_rooms

class HiddenTests(unittest.TestCase):
    def test_0(self):
        self.assertEqual(meeting_rooms(*([[0, 30], [5, 10], [15, 20]],)), 2)
    def test_1(self):
        self.assertEqual(meeting_rooms(*([[7, 10], [2, 4]],)), 1)
    def test_2(self):
        self.assertEqual(meeting_rooms(*([],)), 0)
    def test_3(self):
        self.assertEqual(meeting_rooms(*([[1, 2], [2, 3]],)), 1)
    def test_4(self):
        self.assertEqual(meeting_rooms(*([[1, 5], [1, 5], [1, 5]],)), 3)
    def test_5(self):
        self.assertEqual(meeting_rooms(*([[-2, 2], [0, 1]],)), 2)
