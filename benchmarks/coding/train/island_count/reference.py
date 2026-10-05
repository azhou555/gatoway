def island_count(grid):
    if not grid or not grid[0]: return 0
    rows,cols=len(grid),len(grid[0])
    seen=set()
    count=0
    for r in range(rows):
        for c in range(cols):
            if grid[r][c]!=1 or (r,c) in seen: continue
            count+=1
            stack=[(r,c)]
            seen.add((r,c))
            while stack:
                a,b=stack.pop()
                for x,y in ((a+1,b),(a-1,b),(a,b+1),(a,b-1)):
                    if 0<=x<rows and 0<=y<cols and grid[x][y]==1 and (x,y) not in seen:
                        seen.add((x,y)); stack.append((x,y))
    return count
