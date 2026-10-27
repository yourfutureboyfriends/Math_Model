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
  { code: 'TECH', name: 'Technical analysis', desc: 'RSI, MACD, moving averages, Bollinger, ADX and more with a buy/sell summary, support & resistance, and how each signal has actually worked on this stock.', group: 'Security', security: true, aliases: ['TA', 'TECHNICALS', 'INDICATORS'] },
  { code: 'OVDV', name: 'Volatility surface', desc: 'Implied vol by strike and expiry (solved from option quotes), term structure, skew, implied vs realised and IV rank.', group: 'Security', security: true, aliases: ['VOLSURF', 'SKEW', 'IVOL'] },
  { code: 'CACS', name: 'Corporate actions', desc: 'Dividend history, growth and streak, upcoming ex-dates and earnings, and splits.', group: 'Security', security: true, aliases: ['ACTIONS', 'SPLITS'] },
  { code: 'MGMT', name: 'Management', desc: 'Officers, pay and age, ISS governance risk scores, insider ownership and Form 4 trades.', group: 'Security', security: true, equityOnly: true, aliases: ['OFFICERS', 'EXECS'] },
  { code: 'PGEO', name: 'Segments & regions', desc: 'Revenue and operating margin by business segment, product line and region, from the 10-K’s XBRL.', group: 'Security', security: true, equityOnly: true, aliases: ['SEGMENTS', 'SEG', 'BREAKDOWN'] },
  { code: 'DDIS', name: 'Debt maturities', desc: 'Maturity ladder of long-term debt from filings, with cash coverage, interest cover and leverage.', group: 'Security', security: true, equityOnly: true, aliases: ['DEBT', 'MATURITIES'] },
  { code: 'CF', name: 'Company filings', desc: 'Every SEC filing with 8-K events decoded and red flags marked, the stock’s reaction to each, and the documents readable in the terminal.', group: 'Security', security: true, equityOnly: true, aliases: ['FILINGS', 'SEC', 'EDGAR'] },
  { code: 'FAC', name: 'Factor exposures', desc: 'Fama–French 5 + momentum loadings — market, size, value, quality, investment, momentum — full period and rolling.', group: 'Security', security: true, equityOnly: true, aliases: ['FACTORS', 'STYLE'] },
  { code: 'VAL', name: 'Valuation hub', desc: 'Fair value from DCF, dividend model and peers in one place — pre-filled; move the few drivers that matter, see bear/base/bull and a 24-month price path.', group: 'Security', security: true, equityOnly: true, aliases: ['VALUE', 'FAIRVALUE', 'DDM'] },
  { code: 'DCF', name: 'DCF valuation', desc: 'Discounted free-cash-flow value per share with an editable model and sensitivity grid.', group: 'Security', security: true, equityOnly: true },
  { code: 'SEAS', name: 'Seasonality', desc: 'Average return by calendar month over up to 30 years, hit rate and significance.', group: 'Security', security: true, aliases: ['SEASON'] },
  { code: 'OSA', name: 'Option strategies', desc: 'Build spreads, straddles, condors: payoff, breakevens, max profit/loss, chance of profit, Greeks.', group: 'Security', security: true, aliases: ['OSB', 'STRAT'] },
  { code: 'SI', name: 'Short selling', desc: 'Short interest and FINRA daily short-sale volume (US); regulator short positions for UK (FCA), Hong Kong (SFC) and Japan (JPX).', group: 'Security', security: true, aliases: ['SHORT'] },
  { code: 'SPLC', name: 'Supply chain', desc: 'Suppliers and competitors found in SEC annual reports (companies naming it as a customer or rival).', group: 'Security', security: true, equityOnly: true, aliases: ['SUPPLY'] },
  { code: 'INSD', name: 'Insider trades', desc: 'Every Form 4 filing parsed: who bought or sold, how much, at what price (SEC EDGAR).', group: 'Security', security: true, equityOnly: true, aliases: ['FORM4', 'INSIDER'] },
  { code: 'CN', name: 'Company news', desc: 'Latest headlines and official SEC filings for this instrument.', group: 'Security', security: true },
  // Markets
  { code: 'WEI', name: 'World markets', desc: 'Equity indices, rates, currencies, commodities and crypto at a glance.', group: 'Markets', aliases: ['HOME', 'TOP'] },
  { code: 'RMON', name: 'Regional monitor', desc: 'Every country in the selected region: index, currency, 10Y, policy rate, inflation, growth, rating — plus movers, news, releases.', group: 'Markets', aliases: ['REGION', 'RGN', 'EMEA', 'APAC', 'AMER'] },
  { code: 'CTRY', name: 'Country page', desc: 'One country: index and currency charts, largest companies, yields, policy, IMF economy, risk, news and releases. e.g. CTRY JP.', group: 'Markets', aliases: ['COUNTRY'] },
  { code: 'LP', name: 'Launchpad (multi-window)', desc: 'Up to six windows side by side, each running any function with its own command line.', group: 'Markets', aliases: ['BLP', 'GRID', 'LAUNCH'] },
  { code: 'MOST', name: 'Movers', desc: 'Biggest gainers, losers and most active stocks in 22 markets.', group: 'Markets', aliases: ['MOV'] },
  { code: 'IMAP', name: 'Market heatmap', desc: 'A country’s largest stocks by sector, sized by value, coloured by today’s move.', group: 'Markets', aliases: ['HEAT'] },
  { code: 'CRYPTO', name: 'Crypto', desc: 'Top 100 coins: price, 1h/24h/7d/30d moves, market cap, dominance.', group: 'Markets' },
  { code: 'CMDTY', name: 'Commodities & curves', desc: 'Futures term structures — contango, backwardation and roll yield.', group: 'Markets', aliases: ['CRV', 'FUT'] },
  { code: 'MAP', name: 'World map', desc: 'Every country coloured by its stock market or economy — returns, rates, inflation, growth.', group: 'Markets', aliases: ['BMAP', 'WORLD'] },
  { code: 'CORR', name: 'Correlation matrix', desc: 'Correlations across any instruments, clustered — cross-asset, sectors, indices, currencies.', group: 'Markets', aliases: ['CORREL'] },
  { code: 'RRG', name: 'Relative rotation', desc: 'Sectors, countries, factors or asset classes: leading, weakening, lagging or improving vs the market.', group: 'Markets', aliases: ['ROT'] },
  { code: 'EDGE', name: 'Signal board', desc: 'The most unusual readings right now: crowded positioning, prediction-market jumps, port and trade shocks, fund-flow surges.', group: 'Markets', aliases: ['SIG', 'ALPHA', 'IDEAS'] },
  { code: 'RISK', name: 'Risk regime', desc: 'Risk-on / risk-off gauge from credit, volatility, curve, dollar, copper/gold and trend — plus the yield-curve recession probability.', group: 'Markets', aliases: ['REGIME', 'RECESS'] },
  { code: 'VOL', name: 'Volatility', desc: 'VIX term structure, VVIX, SKEW, MOVE, oil and gold vol, implied vs realised volatility.', group: 'Markets', aliases: ['VOLA'] },
  { code: 'BRDT', name: 'Market breadth', desc: 'S&P 500 participation: members above 50/200-day averages, advance/decline line, new highs/lows, McClellan, by sector.', group: 'Markets', aliases: ['BREADTH'] },
  { code: 'IMPM', name: 'Earnings implied moves', desc: 'The move options price through each upcoming report vs the stock’s typical post-earnings reaction.', group: 'Markets', aliases: ['EMOVE', 'STRADDLE'] },
  { code: 'UOA', name: 'Unusual options', desc: 'Contracts trading far above open interest across the most active US names; premium and put/call by name.', group: 'Markets', aliases: ['FLOWOPT', 'SWEEP'] },
  { code: 'COT', name: 'Positioning (COT)', desc: 'CFTC Commitments of Traders: hedge funds, asset managers and managed money in 29 futures — crowded longs and shorts.', group: 'Markets', aliases: ['CFTC'] },
  { code: 'ENVR', name: 'All Weather environments', desc: 'Bridgewater’s four growth/inflation environments since 1950: today’s environment and what every asset class earned in each.', group: 'Markets', aliases: ['QUADRANTS', 'ENVIRONMENTS', 'ALLWEATHER'] },
  { code: 'AWP', name: 'All Weather portfolio', desc: 'Bridgewater’s All Weather construction — equal risk per environment, levered to a target vol — backtested vs 60/40.', group: 'Markets', aliases: ['RISKPARITY', 'AWEATHER'] },
  { code: 'DCYC', name: 'Debt cycles', desc: 'Dalio’s debt-cycle framework for ~40 economies (BIS credit gaps, debt service) and the US MP1/MP2/MP3 policy stage.', group: 'Markets', aliases: ['DEBTCYCLE', 'BIGDEBT'] },
  { code: 'HGRL', name: 'Holy Grail diversification', desc: 'Dalio’s Holy Grail: how many independent bets your instruments really are, and the risk-vs-streams curve.', group: 'Markets', aliases: ['HOLYGRAIL', 'DIVERSIFY'] },
  { code: 'WPWR', name: 'World power index', desc: 'Dalio’s Changing World Order: education, innovation, competitiveness, output, trade, military, finance and reserve currency.', group: 'Markets', aliases: ['WORLDORDER', 'EMPIRES'] },
  { code: 'CHART', name: 'Formula charts', desc: 'Chart any formula over instruments and FRED series — AAPL/SPY, {^TNX}-FRED:DGS2, ma(SPY,200), yoy(FRED:CPIAUCSL).', group: 'Markets', aliases: ['FORMULA', 'GRAPH'] },
  { code: 'DATA', name: 'Data grid (BDP / BDH)', desc: 'Any fields for up to 100 instruments, or their price history side by side — download as CSV or copy into Excel.', group: 'Markets', aliases: ['BDP', 'BDH', 'GRID'] },
  { code: 'YAS', name: 'Treasuries & bond calculator', desc: 'Every marketable Treasury priced from TreasuryDirect with yield, duration and DV01; price ↔ yield calculator with a shock grid.', group: 'Markets', aliases: ['TSY', 'BONDS', 'BONDCALC'] },
  { code: 'ILBE', name: 'Inflation expectations', desc: 'TIPS breakevens, 5y5y forward, real yields, Cleveland Fed and Michigan expectations vs actual CPI.', group: 'Markets', aliases: ['BREAKEVENS', 'TIPS', 'INFLEXP'] },
  { code: 'FXCA', name: 'FX carry', desc: 'Carry of 25 currencies vs the dollar from central-bank rates, ranked by carry-to-volatility, with forwards and a carry basket.', group: 'Markets', aliases: ['CARRY'] },
  { code: 'MRGR', name: 'Merger arbitrage', desc: 'Announced US mergers found in SEC filings: offer terms, buyer, target price, deal spread and annualised return.', group: 'Markets', aliases: ['DEALS', 'MNA', 'MERGERS'] },
  { code: 'MEMB', name: 'Index members', desc: 'Constituents and weights of the S&P 500, Dow, Nasdaq-100, FTSE 100, DAX, CAC 40, Euro Stoxx 50 and Hang Seng.', group: 'Markets', aliases: ['MEMBERS', 'CONSTITUENTS'] },
  { code: 'FSRC', name: 'ETF screener', desc: '~200 ETFs by cost, size, yield, returns and beta, plus a two-fund overlap comparison.', group: 'Markets', aliases: ['ETFS', 'FUNDS'] },
  { code: 'DVDC', name: 'Dividend & split calendar', desc: 'Upcoming ex-dividend dates and stock splits across US-listed companies.', group: 'Markets', aliases: ['EXDIV', 'DIVCAL'] },
  { code: 'CDR', name: 'Exchange hours', desc: 'Which of 22 exchanges are open now, sessions in local time, time to open/close and upcoming holidays.', group: 'Markets', aliases: ['EXCH', 'HOURS', 'HOLIDAYS'] },
  { code: 'ETFA', name: 'ETF premium / discount', desc: 'How far ~50 major ETFs trade from the value of their holdings (NAV) — the gap ETF market makers arbitrage — and why some gaps are only timing.', group: 'Markets', aliases: ['ETFARB', 'NAV', 'PREM'] },
  { code: 'SPRD', name: 'Pairs & spreads', desc: 'Any two instruments: hedge ratio, spread z-score, cointegration test, half-life and an out-of-sample mean-reversion backtest.', group: 'Markets', aliases: ['PAIRS', 'SPREAD', 'PAIR'] },
  { code: 'CBRT', name: 'Central bank rates', desc: 'Policy rates of ~40 central banks (BIS): level, latest decision, 12-month moves and the global easing/tightening cycle.', group: 'Markets', aliases: ['POLICY', 'CENTRALBANKS', 'CBANKS'] },
  { code: 'ECOS', name: 'Economic data explorer', desc: 'Search and chart any of FRED’s 800,000 series — overlay up to four, as levels, changes, year-on-year or rebased.', group: 'Markets', aliases: ['FRED', 'ECON', 'SERIES'] },
  { code: 'CRED', name: 'Credit spreads', desc: 'IG, BBB, high-yield, CCC, euro and EM corporate spreads — levels, changes, 3-year percentiles and stress signals.', group: 'Markets', aliases: ['CREDIT', 'OAS', 'SPREADS'] },
  { code: 'PORT', name: 'Portfolio risk', desc: 'Your holdings’ exposures, volatility, VaR, risk contributions, correlations, factor loadings, stress tests and crisis replays.', group: 'Markets', aliases: ['PRTU', 'STRESS', 'PORTFOLIO'] },
  { code: 'PRED', name: 'Prediction markets', desc: 'Real-money odds (Polymarket, Kalshi) for Fed decisions, inflation, recession, geopolitics — and today’s biggest moves.', group: 'Markets', aliases: ['ODDS', 'POLY', 'KALSHI'] },
  { code: 'NOW', name: 'Nowcasts & trade', desc: 'GDPNow, Cleveland Fed inflation nowcasts, weekly activity, financial conditions, and world trade from ship data — before the official numbers.', group: 'Markets', aliases: ['NOWCAST', 'GDPNOW'] },
  { code: 'FLOW', name: 'Money flow map', desc: 'Where money is moving: cross-border portfolio flows (TIC), bank lending (BIS), ETF creations and money flow, stablecoins, Fed liquidity.', group: 'Markets', aliases: ['MONEY', 'CAPF', 'TIC'] },
  { code: 'SHIP', name: 'Shipping tracker', desc: 'Every vessel worldwide (live AIS + satellite), port congestion, ship photos, and traffic through 28 chokepoints.', group: 'Markets', aliases: ['AIS', 'VSL', 'CHOKE'] },
  { code: 'FLY', name: 'Flight tracker', desc: 'Every aircraft in the world; zoom in for live detail, routes, airframes, photos and tracks flown.', group: 'Markets', aliases: ['PLANE', 'ADSB'] },
  { code: 'QUAK', name: 'Earthquakes', desc: 'Magnitude 4.5+ quakes this week, flagged when near a major port or shipping chokepoint.', group: 'Markets', aliases: ['QUAKE', 'HAZ'] },
  { code: 'EIA', name: 'Oil & gas inventories', desc: 'Weekly US crude, gasoline, distillate, SPR and Cushing stocks, and natural-gas storage (EIA).', group: 'Markets', aliases: ['DOE', 'INV'] },
  { code: 'WETR', name: 'Weather & energy demand', desc: '16-day heating and cooling degree days vs 10-year normals for US demand centres.', group: 'Markets', aliases: ['WEATHER', 'HDD'] },
  { code: 'COMP', name: 'Compare', desc: 'Total-return comparison of up to 8 instruments, with risk and correlation.', group: 'Markets', aliases: ['TRA'] },
  // Rates & FX
  { code: 'GC', name: 'Yield curves', desc: 'Government curves for the US, UK, Germany, Japan, Canada and Australia.', group: 'Rates & FX', aliases: ['CURVE'] },
  { code: 'BTMM', name: 'Money markets', desc: 'Fed funds, SOFR, bills, coupons, curve spreads, credit spreads, mortgages.', group: 'Rates & FX', aliases: ['RATES'] },
  { code: 'FRD', name: 'FX forwards', desc: 'Outright forwards and forward points, 1 week to 1 year, from interest-rate parity.', group: 'Rates & FX', aliases: ['FWD', 'FXFC'] },
  { code: 'WIRP', name: 'Fed rate probabilities', desc: 'Odds of a hike, hold or cut at each FOMC meeting from fed funds futures (FedWatch method).', group: 'Rates & FX', aliases: ['FEDW', 'FOMC'] },
  { code: 'AUCT', name: 'Treasury auctions', desc: 'Bills, notes, bonds, TIPS: yield, bid-to-cover vs average, foreign/investor and dealer take-up.', group: 'Rates & FX', aliases: ['AUCTION'] },
  { code: 'WCRS', name: 'FX cross rates', desc: 'Matrix of 18 currencies with today’s moves and strength vs the dollar.', group: 'Rates & FX', aliases: ['FX', 'FXC'] },
  // Research
  { code: 'EQS', name: 'Equity screener', desc: 'Screen 22 markets by sector, size, valuation and yield.', group: 'Research', aliases: ['SCREEN'] },
  { code: '13F', name: 'Investor holdings (13F)', desc: 'What Buffett, Dalio, Ackman, Burry and others own — quarterly 13F filings with changes.', group: 'Research', aliases: ['HFND', 'GURU'] },
  { code: 'IPO', name: 'IPO calendar', desc: 'Upcoming and recent IPOs: date, price range, shares, deal size and status (Finnhub).', group: 'Research', aliases: ['IPOS', 'NEWISSUE'] },
  { code: 'EVTS', name: 'Earnings calendar', desc: 'Who reports this week, with estimates and surprises.', group: 'Research', aliases: ['ERNC', 'CAL'] },
  { code: 'ECO', name: 'Economic calendar', desc: 'Global releases with consensus, previous and actual (US as first published) and the surprise.', group: 'Research' },
  { code: 'ECST', name: 'Economic surprises', desc: 'US data surprise index since 2010: releases vs their own trend, as first published.', group: 'Research', aliases: ['CESI', 'SURP'] },
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
  // One token: a function if it is one ("NOW" opens nowcasts, as on a terminal), else a security.
  if (parts.length === 1) {
    const f = findFunction(parts[0]);
    return f && !f.security ? { fn: f } : { symbol: parts[0].toUpperCase(), fn: f && f.security ? undefined : f };
  }
  // Several tokens: the usual order is SECURITY FUNCTION, so a trailing function wins — that keeps
  // tickers which are also function codes working ("NOW DES" = ServiceNow, "AI GP" = C3.ai).
  // Otherwise a leading function ("DES AAPL").
  const last = findFunction(parts[parts.length - 1]);
  if (last) return { symbol: parts.slice(0, -1).join('').toUpperCase(), fn: last };
  const first = findFunction(parts[0]);
  if (first) return { symbol: parts.slice(1).join('').toUpperCase(), fn: first };
  return { symbol: parts.join('').toUpperCase() };
}
