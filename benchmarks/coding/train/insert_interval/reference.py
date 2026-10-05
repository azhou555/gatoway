def insert_interval(intervals, new_interval):
    out=[]
    for a,b in sorted(intervals+[new_interval]):
        if out and a<=out[-1][1]:
            out[-1][1]=max(out[-1][1],b)
        else:
            out.append([a,b])
    return out
