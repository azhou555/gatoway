def shortest_path(grid):
    from collections import deque
    if not grid or not grid[0] or grid[0][0] or grid[-1][-1]:
        return -1
    rows,cols=len(grid),len(grid[0])
    q=deque([(0,0,0)])
    seen={(0,0)}
    while q:
        r,c,d=q.popleft()
        if (r,c)==(rows-1,cols-1):
            return d
        for a,b in ((r+1,c),(r-1,c),(r,c+1),(r,c-1)):
            if 0<=a<rows and 0<=b<cols and not grid[a][b] and (a,b) not in seen:
                seen.add((a,b))
                q.append((a,b,d+1))
    return -1
