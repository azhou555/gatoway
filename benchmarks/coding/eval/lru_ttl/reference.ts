export class LRUCache {
    private entries=new Map<string,{value:number,expires:number}>();
    constructor(private capacity:number){}
    private purge(now:number):void {
        for(const [key,item] of this.entries) if(now>=item.expires) this.entries.delete(key);
    }
    put(key:string,value:number,ttl:number,now:number):void {
        this.purge(now); this.entries.delete(key);
        if(ttl<=0 || this.capacity===0) return;
        while(this.entries.size>=this.capacity) this.entries.delete(this.entries.keys().next().value!);
        this.entries.set(key,{value,expires:now+ttl});
    }
    get(key:string,now:number):number|undefined {
        this.purge(now);
        const item=this.entries.get(key);
        if(!item) return undefined;
        this.entries.delete(key);this.entries.set(key,item);return item.value;
    }
}
