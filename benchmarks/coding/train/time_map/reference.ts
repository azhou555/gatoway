export class TimeMap {
    private data=new Map<string,[number,string][]>();
    set(key:string,value:string,timestamp:number):void {
        const values=this.data.get(key)??[];
        if(values.length && values[values.length-1][0]===timestamp) values[values.length-1][1]=value;
        else values.push([timestamp,value]);
        this.data.set(key,values);
    }
    get(key:string,timestamp:number):string|undefined {
        const values=this.data.get(key)??[];
        let lo=0,hi=values.length;
        while(lo<hi){const mid=(lo+hi)>>1;if(values[mid][0]<=timestamp) lo=mid+1;else hi=mid;}
        return lo?values[lo-1][1]:undefined;
    }
}
