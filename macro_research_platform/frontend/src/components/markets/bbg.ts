// Terminal-style security identifiers ("AAPL US Equity", "VOD LN Equity", "SPX Index",
// "EURUSD Curncy", "CL1 Comdty") ⇄ the Yahoo symbols the data layer uses.

// exchange code → Yahoo suffix
const EXCH: Record<string, string> = {
  US: '', UN: '', UQ: '', UW: '', UA: '', UP: '', LN: '.L', JP: '.T', JT: '.T', GR: '.DE', GY: '.DE', FP: '.PA', NA: '.AS',
  SM: '.MC', IM: '.MI', SW: '.SW', SE: '.SW', SS: '.ST', NO: '.OL', DC: '.CO', FH: '.HE', BB: '.BR', AV: '.VI', ID: '.IR',
  PL: '.LS', HK: '.HK', KS: '.KS', KQ: '.KQ', TT: '.TW', AU: '.AX', AT: '.AX', IN: '.NS', IB: '.BO', IS: '.NS', SP: '.SI',
  CN: '.TO', CT: '.TO', MM: '.MX', BZ: '.SA', BS: '.SA', SJ: '.JO', AB: '.SR', TI: '.IS', NZ: '.NZ', TB: '.BK', MK: '.KL', IJ: '.JK',
};
const SUFFIX_TO_EXCH: Record<string, string> = {
  '': 'US', '.L': 'LN', '.T': 'JP', '.DE': 'GR', '.PA': 'FP', '.AS': 'NA', '.MC': 'SM', '.MI': 'IM', '.SW': 'SW', '.ST': 'SS',
  '.OL': 'NO', '.CO': 'DC', '.HE': 'FH', '.BR': 'BB', '.VI': 'AV', '.IR': 'ID', '.LS': 'PL', '.HK': 'HK', '.KS': 'KS', '.KQ': 'KQ',
  '.TW': 'TT', '.AX': 'AU', '.NS': 'IN', '.BO': 'IB', '.SI': 'SP', '.TO': 'CN', '.MX': 'MM', '.SA': 'BZ', '.JO': 'SJ', '.SR': 'AB',
  '.IS': 'TI', '.NZ': 'NZ', '.BK': 'TB', '.KL': 'MK', '.JK': 'IJ', '.SS': 'CH', '.SZ': 'CH', '.F': 'GF',
};
const INDEX: Record<string, string> = {
  SPX: '^GSPC', INDU: '^DJI', NDX: '^NDX', CCMP: '^IXIC', RTY: '^RUT', VIX: '^VIX', UKX: '^FTSE', DAX: '^GDAXI', CAC: '^FCHI',
  SX5E: '^STOXX50E', NKY: '^N225', HSI: '^HSI', SHCOMP: '000001.SS', KOSPI: '^KS11', TWSE: '^TWII', SENSEX: '^BSESN', AS51: '^AXJO',
  SPTSX: '^GSPTSE', IBOV: '^BVSP', MEXBOL: '^MXX', USGG10YR: '^TNX', USGG30YR: '^TYX', USGG5YR: '^FVX', USGG3M: '^IRX',
  DXY: 'DX-Y.NYB', MOVE: '^MOVE', SMI: '^SSMI', IBEX: '^IBEX', FTSEMIB: 'FTSEMIB.MI', AEX: '^AEX', STI: '^STI',
};
const INDEX_REV = Object.fromEntries(Object.entries(INDEX).map(([k, v]) => [v, k]));
const COMDTY: Record<string, string> = {
  CL1: 'CL=F', CO1: 'BZ=F', NG1: 'NG=F', HO1: 'HO=F', XB1: 'RB=F', GC1: 'GC=F', SI1: 'SI=F', HG1: 'HG=F', PL1: 'PL=F',
  C1: 'ZC=F', W1: 'ZW=F', S1: 'ZS=F', KC1: 'KC=F', CT1: 'CT=F', SB1: 'SB=F', CC1: 'CC=F', LC1: 'LE=F',
  ES1: 'ES=F', NQ1: 'NQ=F', DM1: 'YM=F', RTY1: 'RTY=F', TY1: 'ZN=F', US1: 'ZB=F', FV1: 'ZF=F', TU1: 'ZT=F', VX1: 'VX=F',
};
const COMDTY_REV = Object.fromEntries(Object.entries(COMDTY).map(([k, v]) => [v, k]));
const CRYPTO: Record<string, string> = { XBT: 'BTC', XET: 'ETH', XSO: 'SOL', XRP: 'XRP', XDG: 'DOGE' };
const CRYPTO_REV = Object.fromEntries(Object.entries(CRYPTO).map(([k, v]) => [v, k]));

export const isExchangeCode = (s: string) => /^[A-Z]{2}$/.test(s) && s in EXCH;

export const YELLOW_KEYS = ['EQUITY', 'INDEX', 'CURNCY', 'COMDTY', 'GOVT', 'CORP', 'MTGE', 'M-MKT', 'MUNI', 'PFD'] as const;

/** Parse a terminal-style identifier. Returns a Yahoo symbol, or null if it isn't one. */
export function fromTerminal(input: string): string | null {
  const t = input.trim().toUpperCase().replace(/<GO>/g, '').replace(/\s+/g, ' ').trim();
  const m = /^(.+?)\s+(EQUITY|INDEX|CURNCY|COMDTY|GOVT|CORP)$/.exec(t);
  const body = m ? m[1].trim() : t;
  const sector = m?.[2];
  if (sector === 'INDEX' || (!sector && INDEX[body])) return INDEX[body.replace(/\s/g, '')] ?? (sector ? `^${body.replace(/\s/g, '')}` : null);
  if (sector === 'COMDTY' || (!sector && COMDTY[body.replace(/\s/g, '')])) return COMDTY[body.replace(/\s/g, '')] ?? null;
  if (sector === 'CURNCY') {
    const p = body.replace(/\s/g, '');
    if (p.length === 6) {
      const a = p.slice(0, 3), b = p.slice(3);
      if (CRYPTO[a]) return `${CRYPTO[a]}-${b}`;
      return a === 'USD' ? `${b}=X` : `${a}${b}=X`;
    }
    return null;
  }
  if (sector === 'GOVT' || sector === 'CORP') return null;          // bond lookups go to GC / BTMM
  const eq = /^([A-Z0-9.\-/]+)\s+([A-Z]{2})$/.exec(body);
  if (eq && eq[2] in EXCH) {
    let [, sym, ex] = eq;
    if (ex === 'HK' && /^\d+$/.test(sym)) sym = sym.padStart(4, '0');
    if (ex === 'CH') return /^6/.test(sym) ? `${sym}.SS` : `${sym}.SZ`;
    return `${sym.replace('/', '-')}${EXCH[ex]}`;
  }
  if (sector === 'EQUITY') return `${body.replace(/\s/g, '')}`;
  return null;
}

/** Terminal-style label for a Yahoo symbol, e.g. "AAPL US Equity", "7203 JP Equity". */
export function toTerminal(symbol: string, type?: string): string {
  const s = symbol.toUpperCase();
  if (INDEX_REV[s]) return `${INDEX_REV[s]} Index`;
  if (COMDTY_REV[s]) return `${COMDTY_REV[s]} Comdty`;
  if (s.endsWith('=F')) return `${s.slice(0, -2)}1 Comdty`;
  if (s.endsWith('=X')) { const p = s.slice(0, -2); return `${p.length === 3 ? `USD${p}` : p} Curncy`; }
  const cr = /^([A-Z]+)-(USD|EUR|GBP)$/.exec(s);
  if (cr) return `${CRYPTO_REV[cr[1]] ?? cr[1]}${cr[2]} Curncy`;
  if (s.startsWith('^')) return `${s.slice(1)} Index`;
  const dot = s.lastIndexOf('.');
  const suffix = dot > 0 ? s.slice(dot) : '';
  const base = dot > 0 ? s.slice(0, dot) : s;
  const ex = SUFFIX_TO_EXCH[suffix];
  if (ex) return `${base.replace(/^0+(?=\d)/, '')} ${ex} ${type === 'Index' ? 'Index' : 'Equity'}`;
  return s;
}
