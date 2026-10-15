export function longestUnique(text: string): number {
    const chars=Array.from(text), seen=new Map<string,number>();
    let left=0,best=0;
    chars.forEach((c,i)=>{
        if(seen.has(c)) left=Math.max(left,seen.get(c)!+1);
        seen.set(c,i); best=Math.max(best,i-left+1);
    });
    return best;
}
