import { useCallback, useState, type SetStateAction } from 'react';
export type InputHistory<T> = { current: T; past: T[]; future: T[] };
export function inputHistory<T>(state: InputHistory<T>, action: {type:'set';value:SetStateAction<T>}|{type:'undo'|'redo'}): InputHistory<T> {
  if(action.type==='undo') return state.past.length ? {current:state.past[state.past.length-1],past:state.past.slice(0,-1),future:[state.current,...state.future]} : state;
  if(action.type==='redo') return state.future.length ? {current:state.future[0],past:[...state.past,state.current].slice(-40),future:state.future.slice(1)} : state;
  if(action.type!=='set')return state;
  const next=typeof action.value==='function'?(action.value as (v:T)=>T)(state.current):action.value;
  if(next===state.current || JSON.stringify(next)===JSON.stringify(state.current))return state;
  return {current:next,past:state.current==null?state.past:[...state.past,state.current].slice(-40),future:[]};
}
export function useInputHistory<T>(initial:T) {
  const [state,update]=useState<InputHistory<T>>({current:initial,past:[],future:[]});
  const set=useCallback((value:SetStateAction<T>)=>update(s=>inputHistory(s,{type:'set',value})),[]);
  const undo=useCallback(()=>update(s=>inputHistory(s,{type:'undo'})),[]);
  const redo=useCallback(()=>update(s=>inputHistory(s,{type:'redo'})),[]);
  return [state.current,set,undo,redo,state.past.length>0,state.future.length>0] as const;
}
