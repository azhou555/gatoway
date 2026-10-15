export class MinStack {
    private values:number[]=[];
    private mins:number[]=[];
    push(value:number):void {
        this.values.push(value);
        this.mins.push(this.mins.length?Math.min(value,this.mins[this.mins.length-1]):value);
    }
    pop():number|undefined { this.mins.pop();return this.values.pop(); }
    top():number|undefined { return this.values[this.values.length-1]; }
    getMin():number|undefined { return this.mins[this.mins.length-1]; }
}
