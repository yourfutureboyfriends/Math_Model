import {act} from 'react';import {createRoot} from 'react-dom/client';import {it,expect,vi} from 'vitest';
import {MacroDataQuality} from './MacroDataQuality';
it('shows actual coverage and distinguishes revised-data history from point-in-time evidence',()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);const host=document.createElement('div');const root=createRoot(host);
 try{act(()=>root.render(<MacroDataQuality data={{status:'review_required',decision_month:'2026-09',target_month:'2026-10',used_inputs:12,configured_inputs:17,warnings:['Five inputs excluded'],drivers:[{key:'INDPRO',label:'Industrial production',block:'growth',loading:.52,available_month:'2026-09'}],interpretation:'Historical tests use revised data, not vintage-accurate releases.'}}/>));
 expect(host.textContent).toContain('12/17');expect(host.textContent).toContain('Five inputs excluded');expect(host.textContent).toContain('Industrial production');expect(host.textContent).toContain('not causal impact');expect(host.textContent).toContain('revised data');
 }finally{act(()=>root.unmount());vi.unstubAllGlobals();}
});
