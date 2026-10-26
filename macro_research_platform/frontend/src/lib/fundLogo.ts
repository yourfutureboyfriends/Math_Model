// Fund logos are private (fetched with the signed-in user's token, which an <img src> cannot send): loaded once as
// a blob and shared as an object URL. null while loading or when the fund has no logo.
import { useEffect, useState } from 'react';
import { currentFund } from '@/lib/fund';

const cache = new Map<string, Promise<string | null>>();

function load(fund: string, variant: 'full' | 'mark'): Promise<string | null> {
  const key = `${fund}:${variant}`;
  if (!cache.has(key)) {
    cache.set(key, fetch(`/api/v1/funds/${encodeURIComponent(fund)}/logo?variant=${variant}`)
      .then((r) => (r.ok ? r.blob() : null)).then((b) => (b ? URL.createObjectURL(b) : null)).catch(() => null));
  }
  return cache.get(key)!;
}

export function forgetFundLogo(fund: string) {
  cache.delete(`${fund}:full`);
  cache.delete(`${fund}:mark`);
}

export function useFundLogo(variant: 'full' | 'mark' = 'full', fund: string = currentFund()): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    load(fund, variant).then((u) => { if (live) setUrl(u); });
    return () => { live = false; };
  }, [fund, variant]);
  return url;
}
