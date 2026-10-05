export function maxWindowSum(nums: number[], k: number): number | null {
    if(k<=0 || k>nums.length) return null;
    let sum=nums.slice(0,k).reduce((a,b)=>a+b,0),best=sum;
    for(let i=k;i<nums.length;i++){
        sum+=nums[i]-nums[i-k]; best=Math.max(best,sum);
    }
    return best;
}
