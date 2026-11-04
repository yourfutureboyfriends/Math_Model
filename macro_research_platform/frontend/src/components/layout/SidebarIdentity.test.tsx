import { act } from 'react';import { createRoot } from 'react-dom/client';import { it,expect,vi } from 'vitest';import { SidebarIdentity } from './SidebarIdentity';
const state=vi.hoisted(()=>({name:'Moriah Capital Partners'}));
vi.mock('@/lib/fundBrand',()=>({useCurrentFund:()=>({name:state.name,logo_masks:true,brand:{mark_fill:'gradient',tagline:'Investment research'}})}));
vi.mock('@/lib/fundLogo',()=>({useFundShape:()=>({url:'/test-brand-mask.svg',ratio:2}),useFundLogo:()=>null}));
it('uses the current fund identity in expanded and collapsed workspace headers',()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);const host=document.createElement('div');const root=createRoot(host);
 try{act(()=>root.render(<SidebarIdentity/>));expect(host.querySelectorAll('[role="img"]')).toHaveLength(2);expect(host.querySelector('[role="img"]')?.getAttribute('aria-label')).toBe(state.name);state.name='BIFS';act(()=>root.render(<SidebarIdentity collapsed/>));expect(host.querySelectorAll('[role="img"]')).toHaveLength(1);expect(host.querySelector('[role="img"]')?.getAttribute('aria-label')).toBe('BIFS');expect(host.querySelector('select')).toBeNull();}finally{act(()=>root.unmount());state.name='Moriah Capital Partners';vi.unstubAllGlobals();}
});
