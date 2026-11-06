import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { expect, it, vi } from 'vitest';
import { MasterSignalSection } from './MasterSignalSection';
it('leaves the navigation anchor on its dashboard owner', () => {
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
 const host=document.createElement('div'), root=createRoot(host);
 try {
  act(()=>root.render(<div id="master-signal"><MasterSignalSection data={{ensembleScore:0.5} as any}/></div>));
  expect(host.querySelectorAll('#master-signal')).toHaveLength(1);
  expect(host.textContent).toContain('COMPOSITE SIGNAL');
 } finally { act(()=>root.unmount());vi.unstubAllGlobals(); }
});
