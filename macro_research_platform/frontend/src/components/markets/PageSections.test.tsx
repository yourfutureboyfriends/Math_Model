import{act}from'react';import{createRoot}from'react-dom/client';import{it,expect,vi}from'vitest';import{PageSections}from'./PageSections';
it('indexes inner sections and moves focus to their headings',async()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);const scroll=vi.fn();Object.defineProperty(Element.prototype,'scrollIntoView',{configurable:true,value:scroll});const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 try{await act(async()=>root.render(<div><PageSections page="TEST"/><section data-panel-title="History"><h2>History</h2></section><section data-panel-title="Scenarios"><h2>Scenarios</h2></section></div>));expect(host.querySelectorAll('nav button')).toHaveLength(2);act(()=>{(host.querySelectorAll('nav button')[1] as HTMLButtonElement).click();});expect(scroll).toHaveBeenCalled();expect(document.activeElement?.textContent).toBe('Scenarios');}finally{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();}
});
it('excludes hidden tabs and folded sections and refreshes when they open',async()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 try{
  await act(async()=>root.render(<div><PageSections page="VISIBILITY"/><section data-panel-title="Overview"/><div style={{display:'none'}}><section data-panel-title="Inactive tab"/></div><details><summary>Details</summary><section data-panel-title="Folded"/></details><section data-panel-title="Visible"/></div>));
  expect([...host.querySelectorAll('nav button')].map(e=>e.textContent)).toEqual(['Overview','Visible']);
  await act(async()=>{host.querySelector('details')!.open=true;await new Promise(resolve=>setTimeout(resolve,40));});
  expect([...host.querySelectorAll('nav button')].map(e=>e.textContent)).toEqual(['Overview','Folded','Visible']);
  await act(async()=>{(host.querySelector('[style]') as HTMLElement).style.display='block';await new Promise(resolve=>setTimeout(resolve,40));});
  expect([...host.querySelectorAll('nav button')].map(e=>e.textContent)).toEqual(['Overview','Inactive tab','Folded','Visible']);
 }finally{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();}
});
