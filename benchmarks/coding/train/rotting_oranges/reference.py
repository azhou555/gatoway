def rotting_oranges(grid):
    from collections import deque
    if not grid or not grid[0]: return 0
    grid=[row[:] for row in grid]
    q=deque()
    fresh=0
    for r,row in enumerate(grid):
        for c,v in enumerate(row):
            if v==2: q.append((r,c,0))
            if v==1: fresh+=1
    minutes=0
    while q:
        r,c,minutes=q.popleft()
        for a,b in ((r+1,c),(r-1,c),(r,c+1),(r,c-1)):
            if 0<=a<len(grid) and 0<=b<len(grid[0]) and grid[a][b]==1:
                grid[a][b]=2; fresh-=1; q.append((a,b,minutes+1))
    return minutes if fresh==0 else -1
