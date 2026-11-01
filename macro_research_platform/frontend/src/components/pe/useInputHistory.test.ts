import { describe, it, expect } from 'vitest';
import { inputHistory, type InputHistory } from './useInputHistory';
describe('deal input history',()=>{
  it('undoes and redoes edits without modifying saved snapshots',()=>{
    const original={revenue:100};let s:InputHistory<typeof original>={current:original,past:[],future:[]};
    s=inputHistory(s,{type:'set',value:p=>({...p,revenue:120})});
    expect(original.revenue).toBe(100);
    s=inputHistory(s,{type:'undo'});expect(s.current.revenue).toBe(100);
    s=inputHistory(s,{type:'redo'});expect(s.current.revenue).toBe(120);
  });
  it('clears redo on a new branch and caps session history',()=>{
    let s:InputHistory<number>={current:0,past:[],future:[]};
    s=inputHistory(s,{type:'set',value:1});s=inputHistory(s,{type:'undo'});
    s=inputHistory(s,{type:'set',value:2});expect(s.future).toEqual([]);
    for(let i=0;i<60;i++)s=inputHistory(s,{type:'set',value:i});
    expect(s.past.length).toBe(40);
  });
  it('does not return to the initial unloaded state',()=>{
    let s:InputHistory<number|null>={current:null,past:[],future:[]};
    s=inputHistory(s,{type:'set',value:1});expect(inputHistory(s,{type:'undo'}).current).toBe(1);
  });
});
