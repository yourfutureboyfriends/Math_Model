// Static coverage inventory: run with node scripts/audit-markets.mjs from frontend.
import ts from 'typescript';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
process.chdir(path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'));
const auditDate=process.argv[2] || new Date().toISOString().slice(0,10);
if(!/^\d{4}-\d{2}-\d{2}$/.test(auditDate))throw new Error('Expected YYYY-MM-DD');
const dir='src/components/markets';
const files=[...fs.readdirSync(dir).filter(n=>/\.tsx?$/.test(n)&&!n.includes('.test.')).map(n=>`${dir}/${n}`),'src/pages/MarketsPage.tsx','src/components/ui/PriceChart.tsx'];
const sources=files.map(file=>({file,ast:ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX)}));
const functions=new Map();
for(const {file,ast}of sources){const walk=node=>{if(ts.isFunctionDeclaration(node)&&node.name){const text=node.getText(ast);const jsx=[...text.matchAll(/<([A-Z]\w*)\b/g)].map(m=>m[1]);const calls=[...text.matchAll(/\b([a-zA-Z]\w*)\(/g)].map(m=>m[1]);functions.set(node.name.text,{name:node.name.text,file,line:ast.getLineAndCharacterOfPosition(node.pos).line+1,text,children:[...new Set([...jsx,...calls])]});}ts.forEachChild(node,walk);};walk(ast);}
const source=fs.readFileSync(`${dir}/functions.ts`,'utf8');
const registry=[...source.matchAll(/\{ code: '([^']+)', name: '([^']+)', desc: '((?:\\.|[^'])*)', group: '([^']+)'([^\n]*)/g)].map(m=>({code:m[1],name:m[2],group:m[4],security:m[5].includes('security: true')}));
const page=fs.readFileSync('src/pages/MarketsPage.tsx','utf8');
const rows=registry.map(f=>{
 const lines=[];for(const {ast,file}of sources.filter(s=>s.file==='src/pages/MarketsPage.tsx')){const scan=node=>{if(ts.isJsxExpression(node)&&new RegExp(`^code\\s*===\\s*'${f.code}'\\s*&&`).test(node.expression?.getText(ast)||''))lines.push(node.getText(ast));ts.forEachChild(node,scan);};scan(ast);}
 const entry=[...new Set(lines.flatMap(l=>[...l.matchAll(/<([A-Z]\w*)\b/g)].map(m=>m[1])).filter(n=>functions.has(n)))];
 if(f.code==='LP')entry.push('LaunchpadGrid');
 const visited=new Set();const follow=name=>{if(visited.has(name)||!functions.has(name))return;visited.add(name);functions.get(name).children.forEach(follow);};entry.forEach(follow);
 const nodes=[...visited].map(n=>functions.get(n));const text=nodes.map(n=>n.text).join('\n');
 return {...f,nestedSections:[...new Set([...text.matchAll(/(?:title|aria-label)="([^"]+)"/g)].map(m=>m[1]))],entries:entry,files:[...new Set(nodes.map(n=>n.file))],components:nodes.map(({name,file,line})=>({name,file,line})),endpoints:[...new Set([...text.matchAll(/(?:['"`])(\/api\/[^'"`\s]+)/g)].map(m=>m[1]))],signals:{tables:(text.match(/<table\b/g)||[]).length,panels:(text.match(/<Panel\b/g)||[]).length,loading:/\bLoading\b|\.loading/.test(text),errors:/\bErrorBox\b|\.error/.test(text),empty:/no data|no .{0,20}found|\.length === 0|\.length===0|empty|not available/i.test(text),customRequests:/\bfetch\(/.test(text),canvas:/<canvas|<LiveMap|<Globe3D|<Chart\b/.test(text)}};
});
const output={date:auditDate,method:'Static registry → route body → transitive local component graph. Signals are review aids, not proof of runtime behaviour.',total:rows.length,filesReviewed:sources.length,unmapped:rows.filter(r=>!r.entries.length).map(r=>r.code),pages:rows};
fs.writeFileSync(`../docs/markets_page_inventory_${auditDate}.json`,JSON.stringify(output,null,2)+'\n');
console.log(JSON.stringify({total:rows.length,files:sources.length,unmapped:output.unmapped,customRequests:rows.filter(r=>r.signals.customRequests).map(r=>r.code),noExplicitError:rows.filter(r=>!r.signals.errors).map(r=>r.code)},null,2));
