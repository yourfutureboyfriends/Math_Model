import{expect,it}from'vitest';import{readLboDraft}from'./peDraft';
it('rejects corrupt or incomplete drafts before they replace active inputs',()=>{for(const d of ['{','null','{}',JSON.stringify({inputs:{years:5},deal:{name:'x'}}),JSON.stringify({inputs:{years:5,tranches:[null]},deal:{name:'x'}})])expect(()=>readLboDraft(d)).toThrow();});
it('restores valid debt and deal inputs without converting missing sources to a non-object',()=>{const d={inputs:{years:5,tranches:[{name:'Loan',kind:'tlb'}]},deal:{name:'Case'},sources:null};expect(readLboDraft(JSON.stringify(d))).toEqual(d);});
