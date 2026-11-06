/** Browser drafts are untrusted: validate before handing them to the financial editor. */
export function readLboDraft(raw:string){
 const d=JSON.parse(raw);const object=(v:any)=>v!==null&&typeof v==='object'&&!Array.isArray(v);
 if(!object(d)||!object(d.inputs)||!object(d.deal)||typeof d.deal.name!=='string'||!Number.isInteger(d.inputs.years)||d.inputs.years<1||d.inputs.years>30||!Array.isArray(d.inputs.tranches)||!d.inputs.tranches.every((t:any)=>object(t)&&typeof t.name==='string'&&typeof t.kind==='string')||!(d.sources==null||object(d.sources)&&Object.values(d.sources).every(v=>typeof v==='string')))throw new Error('Draft is incomplete or damaged. Current inputs were kept.');
 return {inputs:d.inputs,sources:d.sources??null,deal:d.deal};
}
