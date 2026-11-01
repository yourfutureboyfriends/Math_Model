import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {it,expect,vi} from 'vitest';
import {ExpectationsPanel} from './ExpectationsPanel';
it('distinguishes missing reverse solutions and explains the regional ERP proxy',()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);const host=document.createElement('div');const root=createRoot(host);
 try{act(()=>root.render(<ExpectationsPanel data={{country:'Germany',currency:'EUR',cashflow_currency:'EUR',selected_growth:.08,implied_growth:null,findings:['Terminal dependence requires review'],rate_stress:[{rate_increase:.01,per_share:80,change_vs_base:-.2}]}}/>));
 expect(host.textContent).toContain('Unavailable');expect(host.textContent).toContain('US market proxy');expect(host.textContent).toContain('no bounded solution');expect(host.textContent).toContain('Terminal dependence requires review');expect(host.textContent).toContain('-20.0%');
 }finally{act(()=>root.unmount());vi.unstubAllGlobals();}
});
