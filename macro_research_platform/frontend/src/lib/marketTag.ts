// Short market tag for a listing: "JP·DM", "KR·EM", … for equities; the instrument type for
// indices, currencies, futures and crypto (which have no MSCI market class).
export interface MarketInfo {
  asset_type?: string | null;
  country?: string | null;
  country_name?: string | null;
  market_class?: string | null;
  region?: string | null;
}

const CLASS_ABBR: Record<string, string> = { Developed: 'DM', Emerging: 'EM', Frontier: 'FM', Standalone: 'SA' };

export function marketTag(r: MarketInfo): string {
  const t = r.asset_type;
  if (t && t !== 'Equity' && t !== 'ETF') return r.country ? `${t}·${r.country}` : t;
  const cls = CLASS_ABBR[r.market_class ?? ''] ?? '—';
  return `${r.country ?? '—'}·${cls}${t === 'ETF' ? '·ETF' : ''}`;
}

export function marketTitle(r: MarketInfo & { exchange?: string | null }): string {
  const t = r.asset_type;
  if (t && t !== 'Equity' && t !== 'ETF') return `${t}${r.country_name && r.country ? ` · ${r.country_name}` : ''}`;
  return [r.country_name ?? r.country, r.market_class ? `${r.market_class} market` : null, r.region, r.exchange, t === 'ETF' ? 'ETF' : null]
    .filter(Boolean).join(' · ');
}
