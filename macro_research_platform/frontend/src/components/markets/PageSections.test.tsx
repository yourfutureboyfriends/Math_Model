import{act}from'react';import{createRoot}from'react-dom/client';import{it,expect,vi}from'vitest';import{PageSections}from'./PageSections';
it('indexes inner sections and moves focus to their headings',async()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);const scroll=vi.fn();Object.defineProperty(Element.prototype,'scrollIntoView',{configurable:true,value:scroll});const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 try{await act(async()=>root.render(<div><PageSections page="TEST"/><section data-panel-title="History"><h2>History</h2></section><section data-panel-title="Scenarios"><h2>Scenarios</h2></section></div>));expect(host.querySelectorAll('nav button')).toHaveLength(2);act(()=>{(host.querySelectorAll('nav button')[1] as HTMLButtonElement).click();});expect(scroll).toHaveBeenCalled();expect(document.activeElement?.textContent).toBe('Scenarios');}finally{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();}
});
