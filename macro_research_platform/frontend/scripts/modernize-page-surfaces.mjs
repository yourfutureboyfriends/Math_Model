// Idempotent source transformation for existing page surfaces; calculations and handlers are unchanged.
import fs from 'node:fs';import ts from 'typescript';import path from 'node:path';import{fileURLToPath}from'node:url';process.chdir(path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'));
const dir='src/components/markets';let controls=0,stats=0,charts=0;
for(const name of fs.readdirSync(dir).filter(n=>n.endsWith('.tsx')&&!n.includes('.test')&&!['shared.tsx','Chrome.tsx','PageSections.tsx'].includes(n))){const file=`${dir}/${name}`,text=fs.readFileSync(file,'utf8'),source=ts.createSourceFile(file,text,99,true,4),edits=[];
 const visit=node=>{
  if(ts.isJsxElement(node)){
   const tag=node.openingElement.tagName.getText(source),attrs=node.openingElement.attributes.properties;
   const cls=attrs.find(a=>ts.isJsxAttribute(a)&&a.name.getText(source)==='className'&&a.initializer&&ts.isStringLiteral(a.initializer));
   if(cls){let marker='';const c=cls.initializer.text,body=node.getText(source);
    if(tag==='div'&&/\bflex\b/.test(c)&&/flex-wrap/.test(c)&&!c.includes('mkt-controls')&&body.length<7000&&/<(?:select|input|button)\b/.test(body)&&!/<(?:table|Panel)\b/.test(body)&&!node.parent?.getText(source).startsWith('<td')){marker='mkt-controls';controls++;}
    let owner=node.parent;while(owner&&!ts.isFunctionDeclaration(owner))owner=owner.parent;
    if(tag==='div'&&owner?.name&&/^(Kpi|Stat|Metric)$/.test(owner.name.text)&&/\bborder\b/.test(c)&&!c.includes('mkt-stat-card')){marker='mkt-stat-card';stats++;}
    if(marker)edits.push([cls.initializer.getStart(source)+1,`${marker} `]);
   }
  }
  if(ts.isJsxSelfClosingElement(node)&&['LineChart','PriceChart','CorrelationHeatmap'].includes(node.tagName.getText(source))){let parent=node.parent;while(parent&&!ts.isJsxElement(parent))parent=parent.parent;const attrs=parent?.openingElement.attributes.getText(source)||'';if(!attrs.includes('mkt-chart-surface')){edits.push([node.getStart(source),'<div className="mkt-chart-surface">'],[node.end,'</div>']);charts++;}}
  ts.forEachChild(node,visit);
 };visit(source);if(edits.length){let out=text;for(const[at,value]of edits.sort((a,b)=>b[0]-a[0]))out=out.slice(0,at)+value+out.slice(at);fs.writeFileSync(file,out);}
}
console.log({controlSurfaces:controls,statCards:stats,chartSurfaces:charts});
