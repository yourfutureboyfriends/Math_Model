import { expect,it } from 'vitest';
import { preference,savedViews } from './workspaceState';
it('rejects corrupt storage and malformed destinations',()=>{
  for(const v of [{},'oops',42,null])expect(savedViews(v)).toEqual([]);
  expect(savedViews([null,{id:'x',label:'x',mode:'bad'},{id:'y',label:'y',mode:'markets',hash:'https://example.com'}])).toEqual([]);
  const valid={id:'pe:workbench',label:'PE',mode:'pe',pe:'workbench'};
  expect(savedViews([valid,valid])).toHaveLength(1);
  expect(preference('false')).toBe(false);expect(preference({})).toBe(false);expect(preference(true)).toBe(true);
});
