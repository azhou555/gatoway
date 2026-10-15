def group_anagrams(words):
    groups={}
    for word in words:
        groups.setdefault(tuple(sorted(word)), []).append(word)
    return sorted(sorted(group) for group in groups.values())
