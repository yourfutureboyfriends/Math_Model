import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {AnalystScenarios,DevelopedMarketContext} from './AnalystScenarios';
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();});
describe('Valuation evidence',()=>{
 it('shows local rates, tax and proxy caveats',()=>{
  act(()=>root.render(<DevelopedMarketContext data={{country:'Singapore',cashflow_currency:'SGD',marginal_tax:.17,terminal_growth_ceiling:.04,risk_free_source:'Inflation differential proxy',notes:['Verify operating-country exposure.'],classification_as_of:'2026-10-06'}}/>));
  expect(host.textContent).toContain('Singapore · SGD');
  expect(host.textContent).toContain('17.0%');
  expect(host.textContent).toContain('Inflation differential proxy');
 });
 it('withholds incomplete expected value and labels reverse assumptions',()=>{
  act(()=>root.render(<AnalystScenarios data={{complete_probability_mass:false,risk:{beta:1},matrix:[],profile:{}}}/>));
  expect(host.textContent).toContain('Expected value withheld');
  expect(host.textContent).toContain('Implied fixed-cash-flow WACC');
  expect(host.textContent).toContain('Implied revenue growth');
 });
});
