// Fund logos are private (fetched with the signed-in user's token, which an <img src> cannot send): loaded once as
// a blob and shared as an object URL. null while loading or when the fund has no logo.
import { useEffect, useState } from 'react';
import { currentFund } from '@/lib/fund';
import { loadFunds } from '@/lib/fundBrand';

const cache = new Map<string, Promise<string | null>>();

export type LogoVariant = 'full' | 'mark' | 'mark_mask' | 'word_mask';

function load(fund: string, variant: LogoVariant): Promise<string | null> {
  const key = `${fund}:${variant}`;
  if (!cache.has(key)) {
    cache.set(key, loadFunds().then((fs) => fs.find((f) => f.id === fund)?.logo_version ?? 0)
      .then((ver) => fetch(`/api/v1/funds/${encodeURIComponent(fund)}/logo?variant=${variant}&v=${ver}`))
      .then((r) => (r.ok ? r.blob() : null)).then((b) => (b ? URL.createObjectURL(b) : null)).catch(() => null)
      .then((u) => { if (!u) cache.delete(key); return u; }));   // a failure (401, network blip) is not remembered
  }
  return cache.get(key)!;
}

export function forgetFundLogo(fund: string) {
  for (const v of ['full', 'mark', 'mark_mask', 'word_mask']) cache.delete(`${fund}:${v}`);
}

export function useFundLogo(variant: LogoVariant = 'full', fund: string = currentFund()): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let live = true, tries = 0;
    let t: ReturnType<typeof setTimeout> | undefined;
    const go = () => load(fund, variant).then((u) => {
      if (!live) return;
      setUrl(u);
      if (!u && ++tries < 4) t = setTimeout(go, 4000 * tries);   // retry: 4 s, 8 s, 12 s
    });
    go();
    return () => { live = false; clearTimeout(t); };
  }, [fund, variant]);
  return url;
}

const ratios = new Map<string, number>();

/** A logo variant with its aspect ratio (width / height), for sizing a mask to a given height. */
export function useFundShape(variant: LogoVariant, fund: string = currentFund()): { url: string; ratio: number } | null {
  const url = useFundLogo(variant, fund);
  const [ratio, setRatio] = useState<number | null>(url ? ratios.get(url) ?? null : null);
  useEffect(() => {
    if (!url) return;
    if (ratios.has(url)) { setRatio(ratios.get(url)!); return; }
    const im = new Image();
    im.onload = () => { const r = im.naturalWidth / Math.max(1, im.naturalHeight); ratios.set(url, r); setRatio(r); };
    im.src = url;
  }, [url]);
  return url && ratio ? { url, ratio } : null;
}
