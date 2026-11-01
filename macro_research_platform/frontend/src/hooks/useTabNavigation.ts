import { useEffect } from 'react';
/** Native-feeling keyboard navigation for nested tab groups throughout the five workspaces. */
export function useTabNavigation(){
 useEffect(()=>{
  const move=(event:KeyboardEvent)=>{
   if(event.defaultPrevented||event.altKey||event.ctrlKey||event.metaKey)return;
   const target=event.target as HTMLElement|null,tab=target?.closest<HTMLElement>('[role="tab"]'),list=tab?.closest('[role="tablist"]');
   if(!tab||!list||target?.closest('input,textarea,select,button:not([role="tab"])'))return;
   const vertical=list.getAttribute('aria-orientation')==='vertical',nextKey=vertical?'ArrowDown':'ArrowRight',previousKey=vertical?'ArrowUp':'ArrowLeft';
   if(![nextKey,previousKey,'Home','End'].includes(event.key))return;
   const tabs=Array.from(list.querySelectorAll<HTMLElement>('[role="tab"]')).filter(t=>t.closest('[role="tablist"]')===list&&!t.hasAttribute('disabled')&&t.getAttribute('aria-disabled')!=='true'&&!t.closest('[hidden]'));
   const index=tabs.indexOf(tab);if(index<0||!tabs.length)return;
   const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key===nextKey?1:tabs.length-1))%tabs.length;
   event.preventDefault();tabs[next].focus();tabs[next].click();
  };
  window.addEventListener('keydown',move);return()=>window.removeEventListener('keydown',move);
 },[]);
}
