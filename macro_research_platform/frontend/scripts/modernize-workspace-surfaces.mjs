// Idempotent visual/accessibility changes across Macro, Trading, Quant and PE source trees.
import fs from'node:fs';import path from'node:path';import ts from'typescript';import{fileURLToPath}from'node:url';process.chdir(path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'));
const walk=d=>fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(d,e.name)):e.name.endsWith('.tsx')&&!e.name.includes('.test.')?[path.join(d,e.name)]:[]);
const files=[...walk('src/components/sections'),...walk('src/components/pe')];const counts={files:0,controls:0,charts:0,scrollableTables:0,keyboardRows:0,tabGroups:0,metricDefinitions:0};
for(const file of files){const text=fs.readFileSync(file,'utf8'),ast=ts.createSourceFile(file,text,99,true,4),edits=[];
 const visit=node=>{
  if(ts.isJsxElement(node)){
   const opening=node.openingElement,tag=opening.tagName.getText(ast),props=opening.attributes.properties,attrs=opening.attributes.getText(ast),body=node.getText(ast);
   const cls=props.find(a=>ts.isJsxAttribute(a)&&a.name.getText(ast)==='className'&&a.initializer&&ts.isStringLiteral(a.initializer));
   if(cls){const c=cls.initializer.text;let marker='';
    if(tag==='div'&&/\bflex-wrap\b/.test(c)&&!c.includes('workspace-controls')&&body.length<7000&&/<(?:input|select|button)\b/.test(body)&&!/<table\b/.test(body)){marker='workspace-controls';counts.controls++;}
    let owner=node.parent;while(owner&&!ts.isFunctionDeclaration(owner))owner=owner.parent;
    if(tag==='div'&&owner?.name&&/^(Kpi|Stat|Metric|StatBox|KpiBox|StatCard)$/.test(owner.name.text)&&/\bborder\b/.test(c)&&!c.includes('workspace-stat')){marker='workspace-stat';counts.metricDefinitions++;}
    if(marker)edits.push([cls.initializer.getStart(ast)+1,marker+' ']);
   }
   if(tag==='table'){let p=node.parent;while(p&&!ts.isJsxElement(p))p=p.parent;const parent=p?.openingElement.attributes.getText(ast)||'';if(!/overflow|workspace-table-scroll|mkt-table-scroll/.test(parent)){edits.push([node.getStart(ast),'<div className="workspace-table-scroll" tabIndex={0} role="group" aria-label="Scrollable data table">'],[node.end,'</div>']);counts.scrollableTables++;}}
   if(tag==='tr'&&/\bonClick=/.test(attrs)&&!/tabIndex|onKeyDown/.test(attrs)){edits.push([opening.end-1,' tabIndex={0} onKeyDown={e=>{if(e.key===\'Enter\'&&e.target===e.currentTarget){e.preventDefault();e.currentTarget.click();}}}']);counts.keyboardRows++;}
   if(/role="tablist"/.test(attrs)&&!attrs.includes('data-workspace-tabs')){edits.push([opening.end-1,' data-workspace-tabs']);counts.tabGroups++;}
  }
  if(ts.isJsxSelfClosingElement(node)&&['LineChart','PriceChart','CorrelationHeatmap'].includes(node.tagName.getText(ast))){let p=node.parent;while(p&&!ts.isJsxElement(p))p=p.parent;if(!/workspace-chart|mkt-chart-surface/.test(p?.openingElement.attributes.getText(ast)||'')){edits.push([node.getStart(ast),'<div className="workspace-chart">'],[node.end,'</div>']);counts.charts++;}}
  ts.forEachChild(node,visit);
 };visit(ast);if(edits.length){let out=text;for(const[at,value]of edits.sort((a,b)=>b[0]-a[0]))out=out.slice(0,at)+value+out.slice(at);fs.writeFileSync(file,out);counts.files++;}
}
fs.writeFileSync('../docs/workspace_surface_changes_2026-10-29.json',JSON.stringify(counts,null,2)+'\n');console.log(counts);
