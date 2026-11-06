import {describe,it,expect} from 'vitest';
import {layoutGraph,safeResearchUrl,selectGraph} from './researchGraph';
import type {ResearchGraph} from './researchGraph';
const graph:ResearchGraph={nodes:[{id:'a',kind:'source',label:'FRED',detail:'source'},{id:'b',kind:'feature',label:'Inflation',detail:'CPI'},{id:'c',kind:'forecast',label:'Risk',detail:'forecast'},{id:'d',kind:'paper',label:'Paper',detail:'reference'}],edges:[{id:'ab',source:'a',target:'b',relation:'supplies',detail:'',observed:false},{id:'bc',source:'b',target:'c',relation:'predicts',detail:'',observed:false}],revision:'1',generated_at:'',scope:'',limitations:[]};
describe('research network',()=>{
 it('keeps direct evidence neighbors without inventing links',()=>{const selected=selectGraph(graph,'FRED','all',null);expect(selected.nodes.map(n=>n.id)).toEqual(['a','b']);expect(selected.edges.map(e=>e.id)).toEqual(['ab']);});
 it('handles absent matches and focused neighborhoods',()=>{expect(selectGraph(graph,'missing','all',null).nodes).toEqual([]);expect(selectGraph(graph,'','all','b').nodes.map(n=>n.id)).toEqual(['a','b','c']);});
 it('lays out deterministically and accepts only HTTPS evidence links',()=>{expect(layoutGraph(graph.nodes)).toEqual(layoutGraph(graph.nodes));expect(layoutGraph(graph.nodes).every(n=>Number.isFinite(n.x)&&Number.isFinite(n.y))).toBe(true);expect(safeResearchUrl('javascript:alert(1)')).toBeNull();expect(safeResearchUrl('https://arxiv.org/abs/2201.04038')).toContain('arxiv.org');});
});

it('groups feature paths without duplicated task shortcuts or dangling endpoints',async()=>{
 const {overviewGraph}=await import('./researchGraph');
 const grouped=overviewGraph({...graph,edges:[...graph.edges,{id:'short',source:'b',target:'c',relation:'task_input',detail:'',observed:false}]});
 const ids=new Set(grouped.nodes.map(n=>n.id));
 expect(grouped.nodes.some(n=>n.kind==='factor')).toBe(true);
 expect(grouped.edges.some(e=>e.relation==='task_input')).toBe(false);
 expect(grouped.edges.every(e=>ids.has(e.source)&&ids.has(e.target))).toBe(true);
});
