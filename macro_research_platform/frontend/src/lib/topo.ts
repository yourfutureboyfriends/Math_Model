// Minimal TopoJSON → SVG path rendering with the Equal Earth projection (Šavrič, Patterson
// & Jenny 2018) — an equal-area world map, so country sizes are honest. No dependencies.
export interface Topology {
  type: 'Topology';
  transform?: { scale: [number, number]; translate: [number, number] };
  arcs: number[][][];
  objects: Record<string, { type: string; geometries: { type: string; id?: string; arcs: any; properties?: Record<string, any> }[] }>;
}

function decodeArcs(t: Topology): [number, number][][] {
  const s = t.transform?.scale ?? [1, 1], tr = t.transform?.translate ?? [0, 0];
  return t.arcs.map((arc) => {
    let x = 0, y = 0;
    return arc.map(([dx, dy]) => {
      if (t.transform) { x += dx; y += dy; return [x * s[0] + tr[0], y * s[1] + tr[1]] as [number, number]; }
      return [dx, dy] as [number, number];
    });
  });
}

const A1 = 1.340264, A2 = -0.081106, A3 = 0.000893, A4 = 0.003796, M = Math.sqrt(3) / 2;
export function equalEarth(lon: number, lat: number): [number, number] {
  const l = (lon * Math.PI) / 180, p = (lat * Math.PI) / 180;
  const th = Math.asin(M * Math.sin(p)), t2 = th * th, t6 = t2 * t2 * t2;
  const x = (l * Math.cos(th)) / (M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)));
  const y = th * (A1 + A2 * t2 + t6 * (A3 + A4 * t2));
  return [x, y];
}
const X_MAX = equalEarth(180, 0)[0], Y_MAX = equalEarth(0, 90)[1];

export interface CountryShape { id: string; name: string; path: string; centroid: [number, number] }

/** Country outlines as SVG paths for a width × (width × 0.487) canvas. */
export function countryPaths(t: Topology, width: number): { shapes: CountryShape[]; height: number } {
  const arcs = decodeArcs(t);
  const height = width * (Y_MAX / X_MAX);
  const sx = (width / 2) / X_MAX, sy = (height / 2) / Y_MAX;
  const proj = ([lon, lat]: [number, number]): [number, number] => {
    const [x, y] = equalEarth(lon, lat);
    return [width / 2 + x * sx, height / 2 - y * sy];
  };
  const ring = (idxs: number[]) => {
    const pts: [number, number][] = [];
    for (const i of idxs) {
      const a = i >= 0 ? arcs[i] : [...arcs[~i]].reverse();
      for (let k = pts.length ? 1 : 0; k < a.length; k++) pts.push(a[k]);
    }
    return pts;
  };
  const shapes: CountryShape[] = [];
  for (const g of t.objects.countries.geometries) {
    const polys: number[][][] = g.type === 'Polygon' ? [g.arcs] : g.type === 'MultiPolygon' ? g.arcs : [];
    let d = '', bestArea = 0, cx = 0, cy = 0;
    for (const poly of polys) {
      for (let r = 0; r < poly.length; r++) {
        const pts = ring(poly[r]).map(proj);
        if (pts.length < 3) continue;
        // skip polygons that wrap across the antimeridian (avoid horizontal streaks)
        let jump = false;
        for (let k = 1; k < pts.length; k++) if (Math.abs(pts[k][0] - pts[k - 1][0]) > width / 2) { jump = true; break; }
        if (jump) continue;
        d += 'M' + pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('L') + 'Z';
        if (r === 0) {
          let area = 0, mx = 0, my = 0;
          for (let k = 0; k < pts.length; k++) {
            const [x1, y1] = pts[k], [x2, y2] = pts[(k + 1) % pts.length];
            const f = x1 * y2 - x2 * y1;
            area += f; mx += (x1 + x2) * f; my += (y1 + y2) * f;
          }
          if (Math.abs(area) > bestArea) { bestArea = Math.abs(area); cx = mx / (3 * area); cy = my / (3 * area); }
        }
      }
    }
    if (d) shapes.push({ id: String(g.id ?? ''), name: g.properties?.name ?? '', path: d, centroid: [cx, cy] });
  }
  return { shapes, height };
}

// ISO 3166-1 numeric (as used by world-atlas) → alpha-2, for the countries the data covers.
export const NUMERIC_TO_ISO2: Record<string, string> = {
  '840': 'US', '124': 'CA', '484': 'MX', '076': 'BR', '032': 'AR', '152': 'CL', '604': 'PE', '170': 'CO', '826': 'GB', '276': 'DE',
  '250': 'FR', '380': 'IT', '724': 'ES', '528': 'NL', '756': 'CH', '752': 'SE', '578': 'NO', '208': 'DK', '246': 'FI', '056': 'BE',
  '040': 'AT', '372': 'IE', '616': 'PL', '792': 'TR', '376': 'IL', '682': 'SA', '784': 'AE', '634': 'QA', '710': 'ZA', '818': 'EG',
  '566': 'NG', '356': 'IN', '156': 'CN', '344': 'HK', '158': 'TW', '410': 'KR', '392': 'JP', '702': 'SG', '458': 'MY', '764': 'TH',
  '360': 'ID', '608': 'PH', '704': 'VN', '036': 'AU', '554': 'NZ', '586': 'PK', '300': 'GR', '620': 'PT', '643': 'RU', '203': 'CZ',
  '348': 'HU', '642': 'RO', '804': 'UA', '862': 'VE', '012': 'DZ', '504': 'MA', '404': 'KE', '050': 'BD', '398': 'KZ',
};
