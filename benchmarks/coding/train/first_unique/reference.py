def first_unique(text):
    from collections import Counter
    counts=Counter(text)
    return next((i for i,c in enumerate(text) if counts[c]==1), -1)
