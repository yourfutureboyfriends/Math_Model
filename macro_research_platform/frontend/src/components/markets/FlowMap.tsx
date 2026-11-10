/** Money-flow map on the shared ECharts GeoMap: countries shaded by the selected flow layer (green buying / more,
 *  red selling / less, intensity by size), and for the TIC layers curved arrows to or from the US with particles
 *  moving in the direction the money goes. Click a country to select it; hover for its value. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { GeoMap, loadWorld, type GeoLine, type GeoMapHandle } from '@/components/charts/GeoMap';
import { NUMERIC_TO_ISO2 } from '@/lib/topo';

type Layer = 'into_us' | 'out_of_us' | 'bis' | 'etf' | 'pressure';

const shade = (v: number | null | undefined, max: number) => {
  if (v == null || !max) return undefined;
  const k = Math.min(1, Math.sqrt(Math.abs(v) / max));
  return v >= 0 ? `rgb(var(--c-green) / ${0.12 + 0.55 * k})` : `rgb(var(--c-red) / ${0.12 + 0.55 * k})`;
};

export function FlowMap({ layer, values, max, selected, onSelect, onHover, nameOf, fmtV, animate = true, height = 470 }: {
  layer: Layer; values: Record<string, number>; max: number; selected: string | null; onSelect: (iso: string) => void;
  onHover?: (iso: string | null) => void; nameOf: (iso: string) => string; fmtV: (v: number | null | undefined) => string; animate?: boolean; height?: number;
}) {
  const map = useRef<GeoMapHandle>(null);
  const [centroids, setCentroids] = useState<Record<string, [number, number]> | null>(null);
  useEffect(() => { loadWorld().then(setCentroids).catch(() => setCentroids({})); }, []);
  // numeric id ↔ ISO-2 (the largest polygon wins when a code repeats)
  const isoToNum = useMemo(() => { const m: Record<string, string> = {}; for (const [num, iso] of Object.entries(NUMERIC_TO_ISO2)) if (!m[iso]) m[iso] = num; return m; }, []);
  const tic = layer === 'into_us' || layer === 'out_of_us';
  const fills = useMemo(() => {
    const f: Record<string, string> = {};
    for (const [num, iso] of Object.entries(NUMERIC_TO_ISO2)) { const c = shade(values[iso], max); if (c) f[num] = c; }
    if (tic && isoToNum.US) f[isoToNum.US] = 'rgb(var(--c-bloomberg) / 0.4)';
    return f;
  }, [values, max, tic, isoToNum]);
  const lines = useMemo<GeoLine[]>(() => {
    const us = centroids?.[isoToNum.US];
    if (!tic || !us || !centroids) return [];
    const ranked = Object.entries(values).filter(([iso, v]) => iso !== 'US' && v !== 0 && centroids[isoToNum[iso]]).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 14);
    const amax = Math.max(1, ...ranked.map(([, v]) => Math.abs(v)));
    return ranked.map(([iso, v]) => {
      const c = centroids[isoToNum[iso]];
      // into the US: a positive value is money moving country → US; out of the US: US → country; negatives reverse
      const toUs = layer === 'into_us' ? v >= 0 : v < 0;
      return { id: iso, from: toUs ? c : us, to: toUs ? us : c, color: v >= 0 ? 'rgb(var(--c-green))' : 'rgb(var(--c-red))',
        width: 0.8 + 3.6 * Math.sqrt(Math.abs(v) / amax), tip: `<b>${nameOf(iso)}</b><br/>${fmtV(v)}` };
    });
  }, [centroids, tic, values, layer, isoToNum, nameOf, fmtV]);
  return <GeoMap ref={map} height={height} ariaLabel="Money flow map" fills={fills} lines={lines} animate={animate}
    selected={selected ? isoToNum[selected] ?? null : null}
    regionTip={(num, name) => { const iso = NUMERIC_TO_ISO2[num]; return `<b>${iso ? nameOf(iso) : name}</b><br/>${iso && values[iso] != null ? fmtV(values[iso]) : 'no data'}`; }}
    onRegionClick={(num) => { const iso = NUMERIC_TO_ISO2[num]; if (iso) onSelect(iso); }}
    onRegionHover={(num) => onHover?.(num ? NUMERIC_TO_ISO2[num] ?? null : null)} />;
}
