import { act } from 'react';import { createRoot,type Root } from 'react-dom/client';import { beforeEach,afterEach,it,expect,vi } from 'vitest';
import { useJSON,SourceScope,SourcesBar,Panel,useSort } from './shared';
let host:HTMLDivElement,root:Root;const response=(data:unknown,status=200)=>({ok:status<400,status,json:async()=>data});
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.useRealTimers();vi.unstubAllGlobals();});
function Probe({url,interval=0}:{url:string;interval?:number}){const s=useJSON<{value:string}>(url,interval);return <><output>{s.data?.value??'empty'}</output><span data-error>{s.error??s.refreshError}</span><button onClick={s.retry}>Reload</button></>;}
it('aborts old requests and never shows an old response under a new URL',async()=>{
 const pending=new Map<string,{resolve:(r:unknown)=>void;signal:AbortSignal}>();vi.stubGlobal('fetch',vi.fn((url:string,init:RequestInit)=>new Promise(resolve=>pending.set(url,{resolve,signal:init.signal as AbortSignal}))));
 await act(async()=>root.render(<Probe url="/one"/>));const first=pending.get('/one')!;
 await act(async()=>root.render(<Probe url="/two"/>));expect(first.signal.aborted).toBe(true);expect(host.querySelector('output')?.textContent).toBe('empty');
 await act(async()=>{pending.get('/two')!.resolve(response({value:'second'}));});await act(async()=>{first.resolve(response({value:'first'}));});expect(host.querySelector('output')?.textContent).toBe('second');
});
it('keeps old data after refresh failure and surfaces a retry control',async()=>{
 const fetcher=vi.fn().mockResolvedValueOnce(response({value:'saved',source:'Test feed'})).mockResolvedValueOnce(response({detail:'Unavailable'},503)).mockResolvedValue(response({value:'fresh',source:'Test feed'}));vi.stubGlobal('fetch',fetcher);
 await act(async()=>root.render(<SourceScope><SourcesBar/><Probe url="/feed"/></SourceScope>));
 await act(async()=>{Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Reload')!.click();});expect(host.querySelector('output')?.textContent).toBe('saved');expect(host.textContent).toContain('unavailable');
 await act(async()=>{Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Retry feeds')!.click();});expect(host.querySelector('output')?.textContent).toBe('fresh');expect(host.querySelector('[data-error]')?.textContent).toBe('');
});
it('does not overlap polling requests and cancels on unmount',async()=>{
 vi.useFakeTimers();const fetcher=vi.fn(()=>new Promise(()=>{}));vi.stubGlobal('fetch',fetcher);await act(async()=>root.render(<Probe url="/slow" interval={1000}/>));await act(async()=>vi.advanceTimersByTime(5000));expect(fetcher).toHaveBeenCalledTimes(1);
 const signal=fetcher.mock.calls[0][1]?.signal; // fetch receives an AbortSignal for cleanup.
 act(()=>root.unmount());expect((signal as AbortSignal).aborted).toBe(true);root=createRoot(host);
});
it('collapses a panel without unmounting its inputs and sorts using keyboard',async()=>{
 function Table(){const s=useSort([{value:2},{value:1}]);return <Panel title="Prices"><input defaultValue="kept"/><table><thead><tr>{s.th('value','Value')}</tr></thead><tbody>{s.rows.map(r=><tr key={r.value}><td>{r.value}</td></tr>)}</tbody></table></Panel>;}
 await act(async()=>root.render(<Table/>));const input=host.querySelector('input');act(()=>{host.querySelector('button')!.click();});expect(host.querySelector('input')).toBe(input);expect(host.querySelector('[hidden]')).not.toBeNull();act(()=>{host.querySelector('button')!.click();});
 act(()=>{host.querySelector('th')!.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));});expect(host.querySelector('th')?.getAttribute('aria-sort')).toBe('descending');
 act(()=>{host.querySelector('th')!.dispatchEvent(new KeyboardEvent('keydown',{key:' ',bubbles:true}));});expect(host.querySelector('tbody td')?.textContent).toBe('1');
});

it('distinguishes observation dates from retrieval times and unknown delays', async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response({value:'ok',source:'Official filings',as_of:'2026-09-30'})));
 await act(async()=>root.render(<SourceScope><SourcesBar/><Probe url="/filing"/></SourceScope>));
 expect(host.textContent).toContain('Source details & freshness');
 expect(host.textContent).toContain('2026-09-30');
 expect(host.textContent).toContain('Delay not supplied');
 expect(host.querySelector('a')?.getAttribute('href')).toBe('/filing');
});
it('recovers from a timed-out refresh without discarding previous data',async()=>{
 vi.useFakeTimers();const fetcher=vi.fn().mockResolvedValueOnce(response({value:'saved',source:'Feed'})).mockImplementationOnce(()=>new Promise(()=>{})).mockResolvedValue(response({value:'fresh',source:'Feed'}));vi.stubGlobal('fetch',fetcher);
 await act(async()=>root.render(<SourceScope><SourcesBar/><Probe url="/feed"/></SourceScope>));
 await act(async()=>{Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Reload')!.click();});
 await act(async()=>vi.advanceTimersByTimeAsync(60000));
 expect(host.querySelector('output')?.textContent).toBe('saved');expect(host.textContent).toContain('timed out');
 await act(async()=>{Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Retry feeds')!.click();});
 expect(host.querySelector('output')?.textContent).toBe('fresh');
});
