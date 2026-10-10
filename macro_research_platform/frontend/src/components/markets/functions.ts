// Markets functions — Bloomberg-style mnemonics with plain-English names. Security functions
// need an instrument (e.g. "AAPL DES"); market functions stand alone (e.g. "WEI").
import { fromTerminal, isExchangeCode } from './bbg';
export interface MktFunction {
  code: string;            // mnemonic, upper case
  name: string;
  desc: string;
  group: 'Security' | 'Markets' | 'Rates & FX' | 'Research' | 'My tools';
  security?: boolean;      // needs an instrument
  equityOnly?: boolean;    // only meaningful for single stocks
  aliases?: string[];
}

export const FUNCTIONS: MktFunction[] = [
  // Security
  { code: 'DES', name: 'Description', desc: 'Price, key stats, business or fund profile, valuation and analyst target.', group: 'Security', security: true },
  { code: 'GP', name: 'Price chart', desc: 'Interactive chart: candles, intervals from 5 minutes to monthly, moving averages, volume.', group: 'Security', security: true, aliases: ['GIP', 'CHART'] },
  { code: 'FA', name: 'Financials', desc: 'Income statement, balance sheet, cash flow and ratios — SEC filings for US companies.', group: 'Security', security: true, equityOnly: true },
  { code: 'ERN', name: 'Earnings & estimates', desc: 'Reported vs expected EPS, beat rate, next date, consensus and revisions.', group: 'Security', security: true, equityOnly: true, aliases: ['EE', 'EEO'] },
  { code: 'ANR', name: 'Analyst ratings', desc: 'Buy/hold/sell mix, price targets and recent upgrades and downgrades.', group: 'Security', security: true, equityOnly: true },
  { code: 'HDS', name: 'Holders', desc: 'Institutional and fund ownership, insider buying and selling.', group: 'Security', security: true, equityOnly: true },
  { code: 'DVD', name: 'Dividends', desc: 'Payment history, growth, streak of increases, yield, payout and splits.', group: 'Security', security: true },
  { code: 'OMON', name: 'Options', desc: 'Option chain with implied vol and Greeks, smile, term structure, put/call, max pain.', group: 'Security', security: true, aliases: ['OV', 'OPT'] },
  { code: 'RV', name: 'Peer comparison', desc: 'Same-industry companies worldwide on valuation, margins and growth (in USD).', group: 'Security', security: true, equityOnly: true, aliases: ['COMPS', 'PEERS'] },
  { code: 'HP', name: 'Price history', desc: 'Daily, weekly or monthly prices as a table — download as CSV.', group: 'Security', security: true },
  { code: 'BETA', name: 'Beta', desc: 'Sensitivity to an index: regression beta, adjusted beta, R², rolling beta.', group: 'Security', security: true },
  { code: 'DCF', name: 'DCF valuation', desc: 'Discounted free-cash-flow value per share with an editable model and sensitivity grid.', group: 'Security', security: true, equityOnly: true },
  { code: 'SEAS', name: 'Seasonality', desc: 'Average return by calendar month over up to 30 years, hit rate and significance.', group: 'Security', security: true, aliases: ['SEASON'] },
  { code: 'OSA', name: 'Option strategies', desc: 'Build spreads, straddles, condors: payoff, breakevens, max profit/loss, chance of profit, Greeks.', group: 'Security', security: true, aliases: ['OSB', 'STRAT'] },
  { code: 'CN', name: 'Company news', desc: 'Latest headlines and official SEC filings for this instrument.', group: 'Security', security: true },
  // Markets
  { code: 'WEI', name: 'World markets', desc: 'Equity indices, rates, currencies, commodities and crypto at a glance.', group: 'Markets', aliases: ['HOME', 'TOP'] },
  { code: 'MOST', name: 'Movers', desc: 'Biggest gainers, losers and most active stocks in 22 markets.', group: 'Markets', aliases: ['MOV'] },
  { code: 'IMAP', name: 'Market heatmap', desc: 'A country’s largest stocks by sector, sized by value, coloured by today’s move.', group: 'Markets', aliases: ['HEAT'] },
  { code: 'CRYPTO', name: 'Crypto', desc: 'Top 100 coins: price, 1h/24h/7d/30d moves, market cap, dominance.', group: 'Markets' },
  { code: 'CMDTY', name: 'Commodities & curves', desc: 'Futures term structures — contango, backwardation and roll yield.', group: 'Markets', aliases: ['CRV', 'FUT'] },
  { code: 'MAP', name: 'World map', desc: 'Every country coloured by its stock market or economy — returns, rates, inflation, growth.', group: 'Markets', aliases: ['BMAP', 'WORLD'] },
  { code: 'CORR', name: 'Correlation matrix', desc: 'Correlations across any instruments, clustered — cross-asset, sectors, indices, currencies.', group: 'Markets', aliases: ['CORREL'] },
  { code: 'RRG', name: 'Relative rotation', desc: 'Sectors, countries, factors or asset classes: leading, weakening, lagging or improving vs the market.', group: 'Markets', aliases: ['ROT'] },
  { code: 'COMP', name: 'Compare', desc: 'Total-return comparison of up to 8 instruments, with risk and correlation.', group: 'Markets', aliases: ['TRA'] },
  // Rates & FX
  { code: 'GC', name: 'Yield curves', desc: 'Government curves for the US, UK, Germany, Japan, Canada and Australia.', group: 'Rates & FX', aliases: ['CURVE'] },
  { code: 'BTMM', name: 'Money markets', desc: 'Fed funds, SOFR, bills, coupons, curve spreads, credit spreads, mortgages.', group: 'Rates & FX', aliases: ['RATES'] },
  { code: 'FRD', name: 'FX forwards', desc: 'Outright forwards and forward points, 1 week to 1 year, from interest-rate parity.', group: 'Rates & FX', aliases: ['FWD', 'FXFC'] },
  { code: 'WCRS', name: 'FX cross rates', desc: 'Matrix of 18 currencies with today’s moves and strength vs the dollar.', group: 'Rates & FX', aliases: ['FX', 'FXC'] },
  // Research
  { code: 'EQS', name: 'Equity screener', desc: 'Screen 22 markets by sector, size, valuation and yield.', group: 'Research', aliases: ['SCREEN'] },
  { code: 'EVTS', name: 'Earnings calendar', desc: 'Who reports this week, with estimates and surprises.', group: 'Research', aliases: ['ERNC', 'CAL'] },
  { code: 'ECO', name: 'Economic calendar', desc: 'Upcoming US data releases with prior values and importance.', group: 'Research' },
  { code: 'N', name: 'News', desc: 'Markets headlines from Bloomberg, CNBC, the FT and more — searchable, with tone.', group: 'Research', aliases: ['TOP', 'NEWS'] },
  // My tools
  { code: 'W', name: 'Watchlists', desc: 'Your lists of instruments with live prices.', group: 'My tools', aliases: ['WATCH', 'MON'] },
  { code: 'ALRT', name: 'Alerts', desc: 'Price and move alerts that notify you in the terminal.', group: 'My tools', aliases: ['ALERT'] },
  { code: 'AI', name: 'AI research assistant', desc: 'Ask anything — answers from the terminal’s data, with the lookups shown. Runs locally.', group: 'My tools', aliases: ['ASK', 'GPT'] },
  { code: 'JRNL', name: 'Trading journal', desc: 'Record trades and ideas with your reasoning; review what worked.', group: 'My tools', aliases: ['NOTES'] },
];

const BY_CODE: Record<string, MktFunction> = {};
for (const f of FUNCTIONS) {
  BY_CODE[f.code] = f;
  for (const a of f.aliases ?? []) if (!BY_CODE[a]) BY_CODE[a] = f;
}

export function findFunction(code: string | null | undefined): MktFunction | undefined {
  return code ? BY_CODE[String(code).trim().toUpperCase()] : undefined;
}

export const SECURITY_FUNCTIONS = FUNCTIONS.filter((f) => f.security);

export const MARKET_FUNCTIONS = FUNCTIONS.filter((f) => !f.security);

/** Parse a command: "AAPL DES", "DES AAPL", "WEI", "7203.T", "EURUSD=X GP <GO>", and the
 * terminal form "AAPL US Equity DES", "VOD LN Equity GP", "SPX Index", "EURUSD Curncy GP". */
export function parseCommand(input: string): { symbol?: string; fn?: MktFunction; terminal?: boolean } {
  const parts = input.replace(/<go>/gi, '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return {};
  const sectorAt = parts.findIndex((p) => /^(EQUITY|INDEX|CURNCY|COMDTY)$/i.test(p));
  if (sectorAt > 0) {
    const sym = fromTerminal(parts.slice(0, sectorAt + 1).join(' '));
    const tail = parts.slice(sectorAt + 1);
    if (sym) return { symbol: sym, fn: tail.length ? findFunction(tail[0]) : undefined, terminal: true };
  }
  // "VOD LN", "7203 JP GP": ticker + exchange code without the sector key
  if (parts.length >= 2 && parts.length <= 3 && isExchangeCode(parts[1]) && !findFunction(parts[0])) {
    const sym = fromTerminal(`${parts[0]} ${parts[1]}`);
    if (sym && (parts.length === 2 || findFunction(parts[2]))) return { symbol: sym, fn: parts[2] ? findFunction(parts[2]) : undefined, terminal: true };
  }
  let fn: MktFunction | undefined;
  const rest: string[] = [];
  for (const p of parts) {
    const f = !fn ? findFunction(p) : undefined;
    // a token that is BOTH a function and plausibly a ticker (e.g. "GP") counts as the function only when another token exists
    if (f && (parts.length > 1 || !f.security)) fn = f;
    else rest.push(p);
  }
  const symbol = rest.length ? rest.join('').toUpperCase() : undefined;
  return { symbol, fn };
}
