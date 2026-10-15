export function minWindowLength(nums: number[], target: number): number {
    let sum=0,left=0,best=Infinity;
    for(let right=0;right<nums.length;right++){
        sum+=nums[right];
        while(sum>=target){
            best=Math.min(best,right-left+1); sum-=nums[left++];
        }
    }
    return best===Infinity?0:best;
}
