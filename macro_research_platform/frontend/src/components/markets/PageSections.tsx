import { useEffect,useRef,useState } from 'react';
function isVisibleSection(element: HTMLElement, container: HTMLElement) {
 for(let node: HTMLElement|null=element;node;node=node.parentElement){
  const style=getComputedStyle(node);
  if(node.hidden||style.display==='none'||style.visibility==='hidden'||style.visibility==='collapse')return false;
  if(node.tagName==='DETAILS'&&!node.hasAttribute('open')&&node!==element)return false;
  if(node===container)break;
 }
 return true;
}
/** A local page outline follows the actual visible sections, including sections revealed by internal tabs. */
export function PageSections({page,compact=false}:{page:string;compact?:boolean}){
 const root=useRef<HTMLElement>(null),[sections,setSections]=useState<{label:string;element:HTMLElement}[]>([]);
 useEffect(()=>{
  if(compact)return;const container=root.current?.parentElement;if(!container)return;let frame=0;
  const scan=()=>{frame=0;const next=Array.from(container.querySelectorAll<HTMLElement>('section[data-panel-title], [data-page-section]')).filter(el=>isVisibleSection(el,container)&&!!el.getAttribute('data-panel-title')).map(element=>({element,label:element.getAttribute('data-panel-title')!}));setSections(old=>old.length===next.length&&old.every((s,i)=>s.element===next[i].element&&s.label===next[i].label)?old:next);};
  const schedule=()=>{if(!frame)frame=requestAnimationFrame(scan);};scan();
  const observer=new MutationObserver(schedule);observer.observe(container,{childList:true,subtree:true,attributes:true,attributeFilter:['hidden','data-panel-title','class','style','open']});
  return()=>{observer.disconnect();cancelAnimationFrame(frame);};
 },[page,compact]);
 return <nav ref={root} aria-label="Sections on this page" className="mkt-page-sections" hidden={compact||sections.length<2}><span>On this page</span>{sections.map((s,i)=><button key={i} title={s.label} onClick={()=>{const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;s.element.scrollIntoView({behavior:reduced?'auto':'smooth',block:'start'});const target=s.element.querySelector<HTMLElement>('h2');if(target){target.tabIndex=-1;target.focus({preventScroll:true});}}}>{s.label}</button>)}</nav>;
}
