import { act } from 'react';import { createRoot } from 'react-dom/client';import { it,expect,vi } from 'vitest';import { PeSidebar } from './PeSidebar';
it('keeps every PE tool usable when navigation is collapsed',()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);localStorage.clear();const host=document.createElement('div');const root=createRoot(host);
 try{act(()=>root.render(<PeSidebar collapsed/>));expect(host.querySelectorAll('button')).toHaveLength(5);const button=host.querySelector('[aria-label="Deal pipeline"]') as HTMLButtonElement;act(()=>button.click());expect(button.getAttribute('aria-current')).toBe('page');expect(localStorage.getItem('pe_tab')).toBe('pipeline');}finally{act(()=>root.unmount());localStorage.clear();vi.unstubAllGlobals();}
});
