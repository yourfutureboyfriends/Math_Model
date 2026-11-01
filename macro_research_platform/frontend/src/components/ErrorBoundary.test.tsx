import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { expect,it,vi } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';
it('contains a rendering error and allows a successful retry',()=>{
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);
  const log=vi.spyOn(console,'error').mockImplementation(()=>{});
  const host=document.createElement('div');document.body.append(host);const root=createRoot(host);let fail=true;
  function Example(){if(fail)throw new Error('Test render fault');return <p>Recovered workspace</p>;}
  try{
    act(()=>root.render(<ErrorBoundary sectionName="Test view"><Example/></ErrorBoundary>));
    expect(host.textContent).toContain('Test render fault');
    fail=false;act(()=>{(Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Retry this view') as HTMLButtonElement).click();});
    expect(host.textContent).toContain('Recovered workspace');
  }finally{act(()=>root.unmount());host.remove();log.mockRestore();vi.unstubAllGlobals();}
});
