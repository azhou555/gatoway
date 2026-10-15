def two_sum_pairs(nums, target):
    seen = {}
    pairs = []
    for j, value in enumerate(nums):
        for i in seen.get(target-value, []):
            pairs.append([i, j])
        seen.setdefault(value, []).append(j)
    return sorted(pairs)
