export type TableSnapshot = {title:string; headers:string[]; rows:string[][]; truncated:boolean};
export function filteredRows(table:TableSnapshot, query:string) {
  const terms=query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  return table.rows.filter(row=>terms.every(term=>row.join(' ').toLocaleLowerCase().includes(term)));
}
/** Protect text beginning with spreadsheet formula operators when opened in Excel. */
export function tableCSV(headers:string[],rows:string[][]) {
  const escape=(value:string)=>{
    const safe=/^[\s]*[=+@-]/.test(value) && !/^\s*-?\d+(?:[.,]\d+)?%?\s*$/.test(value) ? `'${value}` : value;
    return '"'+safe.replace(/"/g,'""')+'"';
  };
  return [headers,...rows].map(row=>row.map(escape).join(',')).join('\r\n');
}
export function visibleTables(root:ParentNode):TableSnapshot[] {
  return Array.from(root.querySelectorAll('table')).filter(table=>!table.closest('[hidden]') && getComputedStyle(table).display!=='none').map((table,i)=>{
    const sourceRows=Array.from(table.rows).filter(row=>!row.hidden && getComputedStyle(row).display!=='none');
    const cells=(row:HTMLTableRowElement)=>Array.from(row.cells).map(cell=>(cell.innerText||cell.textContent||'').trim().replace(/\s+/g,' '));
    const header=sourceRows.find(row=>row.closest('thead')||Array.from(row.cells).some(cell=>cell.tagName==='TH'));
    const rows=sourceRows.filter(row=>row!==header&&!row.closest('thead')).map(cells);
    const width=Math.max(0,...rows.map(row=>row.length));
    const headers=header?cells(header):Array.from({length:width},(_,i)=>`Column ${i+1}`);
    const section=table.closest('section, .terminal-section, [data-panel-title]');
    const heading=section?.querySelector('h1,h2,h3,h4')?.textContent?.trim();
    return {title:table.caption?.textContent?.trim()||`${heading?heading+' · ':''}Table ${i+1}: ${headers.slice(0,3).join(' / ')}`, headers, rows:rows.slice(0,5000),truncated:rows.length>5000};
  }).filter(table=>table.headers.length && table.rows.length);
}
