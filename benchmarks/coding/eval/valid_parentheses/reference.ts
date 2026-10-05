export function validParentheses(text: string): boolean {
    const stack:string[]=[],pairs:Record<string,string>={')':'(',']':'[','}':'{'};
    for(const c of text){
        if('([{'.includes(c)) stack.push(c);
        else if(!(c in pairs) || stack.pop()!==pairs[c]) return false;
    }
    return stack.length===0;
}
