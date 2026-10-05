import unittest
from solution import group_anagrams

class HiddenTests(unittest.TestCase):
    def test_0(self):
        self.assertEqual(group_anagrams(*(['eat', 'tea', 'tan', 'ate', 'nat', 'bat'],)), [['ate', 'eat', 'tea'], ['bat'], ['nat', 'tan']])
    def test_1(self):
        self.assertEqual(group_anagrams(*([],)), [])
    def test_2(self):
        self.assertEqual(group_anagrams(*(['', ''],)), [['', '']])
    def test_3(self):
        self.assertEqual(group_anagrams(*(['a', 'a', 'A'],)), [['A'], ['a', 'a']])
    def test_4(self):
        self.assertEqual(group_anagrams(*(['ab', 'ba', 'abc'],)), [['ab', 'ba'], ['abc']])
