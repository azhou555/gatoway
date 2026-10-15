export function dailyTemperatures(temperatures: number[]): number[] {
    const out=temperatures.map(()=>0),stack:number[]=[];
    temperatures.forEach((t,i)=>{
        while(stack.length && t>temperatures[stack[stack.length-1]]){
            const j=stack.pop()!;out[j]=i-j;
        }
        stack.push(i);
    });
    return out;
}
