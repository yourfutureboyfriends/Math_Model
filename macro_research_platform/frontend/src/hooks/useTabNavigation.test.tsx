import{act}from'react';import{createRoot}from'react-dom/client';import{it,expect,vi}from'vitest';import{useTabNavigation}from'./useTabNavigation';
it('navigates nested tab groups, skips disabled tabs and cleans up',()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);const host=document.createElement('div');document.body.append(host);const root=createRoot(host),pick=vi.fn();function Tabs(){useTabNavigation();return <div role="tablist"><button role="tab" onClick={()=>pick('one')}>One</button><button role="tab" disabled>Disabled</button><button role="tab" onClick={()=>pick('three')}>Three</button></div>;}
 try{act(()=>root.render(<Tabs/>));const first=host.querySelector('button')!;act(()=>{first.focus();first.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));});expect(pick).toHaveBeenCalledWith('three');expect(document.activeElement?.textContent).toBe('Three');act(()=>document.activeElement!.dispatchEvent(new KeyboardEvent('keydown',{key:'Home',bubbles:true,cancelable:true})));expect(document.activeElement).toBe(first);
 }finally{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();}
});
