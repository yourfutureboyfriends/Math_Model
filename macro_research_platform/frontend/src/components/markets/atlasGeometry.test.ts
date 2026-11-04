import { describe,it,expect } from 'vitest';
import topology from '../../../public/world-atlas/countries-50m.json';
import { atlasGeometry,globeCountries,zoomCamera,constrainCamera,HOME,ATLAS_WIDTH,ATLAS_HEIGHT } from './atlasGeometry';
import { geoArea,geoContains } from 'd3-geo';
import type { Topology } from '@/lib/topo';
const topo=topology as unknown as Topology;
describe('atlas geometry',()=>{
 it('caches projection geometry and keeps dateline countries drawable',()=>{
  const geo=atlasGeometry(topo);expect(atlasGeometry(topo)).toBe(geo);
  for(const id of ['840','643','242','554']){const shape=geo.shapes.find(s=>s.id===id);expect(shape?.path.length).toBeGreaterThan(10);expect(shape?.path).not.toContain('NaN');}
  expect(geo.shapes.length).toBeGreaterThan(230);
 });
 it('keeps original polygon winding so countries never flood the ocean',()=>{
  const countries=globeCountries(topo);expect(countries.length).toBeGreaterThan(230);
  for(const c of countries)expect(geoArea(c),String(c.properties?.name)).toBeLessThan(Math.PI*2);
  for(const p of [[-30,0],[-140,0],[80,-30]] as [number,number][])expect(countries.some(c=>geoContains(c,p))).toBe(false);
  expect(countries.some(c=>geoContains(c,[2.35,48.86]))).toBe(true);
 });
 it('keeps camera bounds valid and zoom anchored at the pointer',()=>{
  expect(zoomCamera(HOME,.5)).toEqual(HOME);
  const v=zoomCamera(HOME,2,300,200);expect(v).toEqual({k:2,x:-300,y:-200});
  expect(zoomCamera(v,.5)).toEqual(HOME);
  expect(constrainCamera({k:2,x:100,y:-10000})).toEqual({k:2,x:0,y:-ATLAS_HEIGHT});
  expect(zoomCamera(HOME,100).k).toBe(10);expect(zoomCamera(HOME,2).x).toBe(-ATLAS_WIDTH/2);
 });
});
