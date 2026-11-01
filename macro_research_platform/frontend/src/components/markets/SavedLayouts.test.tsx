import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {it,expect,vi} from 'vitest';
import {SavedLayouts,validResearchLayout,readSavedLayouts} from './SavedLayouts';
it('rejects malformed and recursively nested saved layouts',()=>{
 expect(validResearchLayout({layout:'2x2',panes:[{fn:'LP'}]})).toBe(false);
 expect(validResearchLayout({layout:'2x2',panes:[{fn:'GP',link:'unknown'}]})).toBe(false);
 localStorage.setItem('mkt.savedResearchLayouts.v1','broken');expect(readSavedLayouts()).toEqual([]);localStorage.clear();
});
it('saves, restores and reversibly removes a named layout',async()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);localStorage.clear();const host=document.createElement('div');document.body.append(host);const root=createRoot(host),restore=vi.fn();
 const value={layout:'2x2',panes:[{fn:'GP',symbol:'MSFT',link:'blue' as const}]};
 try{
  await act(async()=>root.render(<SavedLayouts value={value} onRestore={restore}/>));
  const input=host.querySelector('input')!;
  await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,'US earnings');input.dispatchEvent(new Event('input',{bubbles:true}));});
  const click=async(text:string)=>act(async()=>Array.from(host.querySelectorAll('button')).find(b=>b.textContent===text)!.click());
  await click('Save current');expect(readSavedLayouts()[0].name).toBe('US earnings');
  await click('Restore');expect(restore).toHaveBeenCalledWith(value);
  await click('Remove');expect(readSavedLayouts()).toEqual([]);
  await click('Undo removal');expect(readSavedLayouts()).toHaveLength(1);
 }finally{act(()=>root.unmount());host.remove();localStorage.clear();vi.unstubAllGlobals();}
});
