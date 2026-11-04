import { afterEach, expect, it, vi } from 'vitest';
import { fetchJSONWithDeadline } from './fetchDeadline';
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});
it('bounds stalled body reads and aborts the transport',async()=>{
 vi.useFakeTimers();let signal:AbortSignal;
 vi.stubGlobal('fetch',vi.fn(async(_url,init)=>{signal=init.signal;return {json:()=>new Promise(()=>{})};}));
 const request=fetchJSONWithDeadline('/slow',new AbortController().signal,1000);
 const result=expect(request).rejects.toThrow('timed out');
 await vi.advanceTimersByTimeAsync(1000);await result;expect(signal!.aborted).toBe(true);
});
it('cancels even when the transport ignores abort',async()=>{
 vi.stubGlobal('fetch',vi.fn(()=>new Promise(()=>{})));
 const controller=new AbortController();const request=fetchJSONWithDeadline('/slow',controller.signal);
 const result=expect(request).rejects.toMatchObject({name:'AbortError'});controller.abort();await result;
});
it('cleans deadlines after successful responses',async()=>{
 vi.useFakeTimers();vi.stubGlobal('fetch',vi.fn(async()=>({json:async()=>({value:1})})));
 const result=await fetchJSONWithDeadline('/ok',new AbortController().signal);
 expect(result.json).toEqual({value:1});expect(vi.getTimerCount()).toBe(0);
});
