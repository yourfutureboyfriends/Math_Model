/** Fixed projection and cached paths: pointer motion and resize never rebuild country geometry. */
import { geoEqualEarth, geoPath, geoGraticule10 } from 'd3-geo';
import { feature } from 'topojson-client';
import { equalEarth, type Topology } from '@/lib/topo';
export const ATLAS_WIDTH=1100;
export const ATLAS_HEIGHT=ATLAS_WIDTH*equalEarth(0,90)[1]/equalEarth(180,0)[0];
export type AtlasCountry={id:string;name:string;path:string;centroid:[number,number];area:number};
export type AtlasGeometry={shapes:AtlasCountry[];graticule:string;sphere:string};
const geometries=new WeakMap<Topology,AtlasGeometry>();
export function atlasGeometry(topo:Topology):AtlasGeometry {
  const cached=geometries.get(topo);if(cached)return cached;
  const projection=geoEqualEarth().scale(ATLAS_WIDTH/2/equalEarth(180,0)[0]).translate([ATLAS_WIDTH/2,ATLAS_HEIGHT/2]).precision(.35);
  const path=geoPath(projection);
  const countries=feature(topo as never,topo.objects.countries as never) as unknown as {features:{id:string;properties?:{name?:string}}[]};
  const shapes=countries.features.filter(f=>String(f.id)!=='010').map(f=>({id:String(f.id),name:f.properties?.name??'',path:path(f as never)??'',centroid:path.centroid(f as never) as [number,number],area:path.area(f as never)}));
  const result={shapes,graticule:path(geoGraticule10())??'',sphere:path({type:'Sphere'})??''};
  geometries.set(topo,result);return result;
}

export type Camera={x:number;y:number;k:number};
export const HOME:Camera={x:0,y:0,k:1};
export function zoomCamera(v:Camera,factor:number,cx=ATLAS_WIDTH/2,cy=ATLAS_HEIGHT/2):Camera {
  const k=Math.min(10,Math.max(1,v.k*factor));if(k===1)return HOME;
  const r=k/v.k;return constrainCamera({k,x:cx-(cx-v.x)*r,y:cy-(cy-v.y)*r});
}
export function constrainCamera(v:Camera):Camera {
  if(v.k<=1)return HOME;
  return {...v,x:Math.max(ATLAS_WIDTH*(1-v.k),Math.min(0,v.x)),y:Math.max(ATLAS_HEIGHT*(1-v.k),Math.min(0,v.y))};
}

// Use the original rings: naive arc simplification can reverse tiny polygon winding and fill the ocean.
export function globeCountries(topo:Topology) {
  return (feature(topo as never,topo.objects.countries as never) as unknown as GeoJSON.FeatureCollection).features;
}
