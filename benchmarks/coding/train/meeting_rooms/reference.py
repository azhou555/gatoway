def meeting_rooms(meetings):
    events=[]
    for a,b in meetings:
        events.extend([(a,1),(b,-1)])
    active=best=0
    for _,delta in sorted(events):
        active+=delta
        best=max(best,active)
    return best
