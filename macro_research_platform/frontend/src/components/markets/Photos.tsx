// Photos of a vessel or an aircraft, shown in the terminal with their credit line (Wikimedia
// Commons images are freely licensed; airframe photos come from airport-data.com via adsbdb).
import { useState } from 'react';
import { useJSON } from './shared';

export function Photos({ kind, imo, name, hex, registration }: { kind: 'ship' | 'aircraft'; imo?: string | number | null; name?: string | null; hex?: string; registration?: string | null }) {
  const q = kind === 'ship'
    ? (imo ? `kind=ship&imo=${encodeURIComponent(String(imo))}${name ? `&name=${encodeURIComponent(name)}` : ''}` : null)
    : `kind=aircraft&hex_id=${encodeURIComponent(hex ?? '')}${registration ? `&registration=${encodeURIComponent(registration)}` : ''}`;
  const { data, loading } = useJSON<any>(q ? `/api/v1/mkt/photos?${q}` : null);
  const [i, setI] = useState(0);
  const [broken, setBroken] = useState<Set<string>>(new Set());
  const photos: any[] = (data?.photos ?? []).filter((p: any) => !broken.has(p.url));
  if (!q) return <p className="text-[10px] text-text-tertiary">No IMO number on record, so no photo can be matched.</p>;
  if (loading && !data) return <div className="h-40 bg-surface-3 animate-pulse" aria-label="Loading photo" />;
  if (!photos.length) return <p className="text-[10px] text-text-tertiary">{data?.note ?? 'No photo found.'}</p>;
  const p = photos[Math.min(i, photos.length - 1)];
  return (
    <figure className="space-y-1">
      <div className="relative bg-black">
        <img key={p.url} src={p.url} alt={p.title} loading="lazy" referrerPolicy="no-referrer" className="w-full max-h-52 object-contain"
          onError={() => setBroken((b) => new Set(b).add(p.url))} />
        {photos.length > 1 && <div className="absolute bottom-1 right-1 flex gap-1">{photos.map((x, j) => (
          <button key={x.url} onClick={() => setI(j)} aria-label={`Photo ${j + 1}`} className={`w-2 h-2 rounded-full ${j === i ? 'bg-bloomberg' : 'bg-white/50'}`} />))}</div>}
      </div>
      <figcaption className="text-[10px] text-text-tertiary truncate" title={p.title}>
        {p.author ? `Photo: ${p.author}` : p.title}{p.license ? ` · ${p.license}` : ''}{p.date ? ` · ${String(p.date).slice(0, 10)}` : ''} · {p.source}</figcaption>
    </figure>
  );
}
