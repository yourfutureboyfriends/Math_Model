import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { beforeEach, afterEach, it, expect, vi } from 'vitest';
import { WorkspaceTools } from './WorkspaceTools';
import { setHubMode } from '@/lib/hubMode';
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({user:{username:'tester'}})}));
let container:HTMLDivElement;let root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);localStorage.clear();window.location.hash='';vi.spyOn(window,'scrollTo').mockImplementation(()=>{});container=document.createElement('div');document.body.append(container);root=createRoot(container);});
afterEach(()=>{act(()=>root.unmount());container.remove();vi.restoreAllMocks();vi.unstubAllGlobals();});
it('pins and restores a workspace across modes without navigating away from the app',()=>{
  act(()=>root.render(<WorkspaceTools onCommand={()=>{}} onHelp={()=>{}} onSidebar={()=>{}}/>));
  act(()=>{(container.querySelector('[title="Pin this workspace"]') as HTMLButtonElement).click();});
  expect(container.querySelector('[aria-label="Pinned workspaces"]')?.textContent).toContain('Macro');
  act(()=>setHubMode('pe'));
  const select=container.querySelector('[aria-label="Pinned workspaces"]') as HTMLSelectElement;
  act(()=>{select.value=select.options[1].value;select.dispatchEvent(new Event('change',{bubbles:true}));});
  expect(localStorage.getItem('hub_mode')).toBe('macro');
});
it('applies shared readable-table preferences and reports offline status',()=>{
  act(()=>root.render(<WorkspaceTools onCommand={()=>{}} onHelp={()=>{}} onSidebar={()=>{}}/>));
  const labels=Array.from(container.querySelectorAll('label'));
  act(()=>{(labels.find(x=>x.textContent?.includes('Readable tables'))?.querySelector('input') as HTMLInputElement).click();});
  expect(document.documentElement.classList.contains('terminal-readable')).toBe(true);
  vi.spyOn(navigator,'onLine','get').mockReturnValue(false);
  act(()=>window.dispatchEvent(new Event('offline')));
  expect(container.textContent).toContain('You’re offline');
});

it('survives valid JSON with an invalid saved-workspace shape',()=>{
  localStorage.setItem('terminal.views:tester:main:pins','{"broken":true}');
  localStorage.setItem('terminal.views:tester:main:recent','[null,42]');
  act(()=>root.render(<WorkspaceTools onCommand={()=>{}} onHelp={()=>{}} onSidebar={()=>{}}/>));
  expect(container.textContent).toContain('Pinned (0)');
});
