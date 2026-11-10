import { expect,it } from 'vitest';
import { filteredRows,tableCSV,visibleTables } from './tableData';
it('filters terms across columns without changing the source',()=>{
  const table={title:'Deals',headers:['Name','IRR'],rows:[['Alpha UK','20%'],['Beta US','15%']],truncated:false};
  expect(filteredRows(table,'uk 20')).toEqual([['Alpha UK','20%']]);expect(table.rows).toHaveLength(2);
});
it('quotes CSV safely and prevents spreadsheet formula execution',()=>{
  const csv=tableCSV(['Name','Value'],[['A, "quoted"','=HYPERLINK("example")'],['Plain','-12.5'],['Text','@SUM(A1)']]);
  expect(csv).toContain('"A, ""quoted"""');expect(csv).toContain('"\'=HYPERLINK');expect(csv).toContain('"-12.5"');expect(csv).toContain('"\'@SUM');
});
it('ignores hidden tables and preserves displayed column values',()=>{
  const root=document.createElement('div');root.innerHTML='<table><tr><th>Name</th><th>Value</th></tr><tr><td>Alpha</td><td>1.2×</td></tr></table><div hidden><table><tr><td>Hidden</td></tr><tr><td>Private</td></tr></table></div>';
  const tables=visibleTables(root);expect(tables).toHaveLength(1);expect(tables[0].headers).toEqual(['Name','Value']);expect(tables[0].rows).toEqual([['Alpha','1.2×']]);
});

it('does not discard the first data row when a table has no header',()=>{
 const root=document.createElement('div');root.innerHTML='<table><tr><td>Alpha</td><td>1</td></tr><tr><td>Beta</td><td>2</td></tr></table>';
 const table=visibleTables(root)[0];expect(table.headers).toEqual(['Column 1','Column 2']);expect(table.rows).toHaveLength(2);
});
