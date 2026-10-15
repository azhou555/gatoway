export function evaluateRpn(tokens: string[]): number {
    const stack:number[]=[];
    for(const t of tokens){
        if(['+','-','*','/'].includes(t)){
            const b=stack.pop()!,a=stack.pop()!;
            stack.push(t==='+'?a+b:t==='-'?a-b:t==='*'?a*b:Math.trunc(a/b));
        } else stack.push(Number(t));
    }
    const result=stack[0]; return result===0?0:result;
}
