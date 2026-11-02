// Markets functions — Bloomberg-style mnemonics with plain-English names. Security functions
// need an instrument (e.g. "AAPL DES"); market functions stand alone (e.g. "WEI").
import { fromTerminal, isExchangeCode } from './bbg';
export interface MktFunction {
  code: string;            // mnemonic, upper case
  name: string;
  desc: string;
  group: 'Security' | 'Markets' | 'Rates & FX' | 'Economy & policy' | 'Alternative data' | 'Research' | 'My tools';
  security?: boolean;      // needs an instrument
  equityOnly?: boolean;    // only meaningful for single stocks
  aliases?: string[];
}

export const FUNCTIONS: MktFunction[] = [
  { code: 'RDESK', name: 'Research desk', desc: 'Watchlist changes, timestamped captures, thesis reviews, portfolio look-through and exposure-aware earnings events.', group: 'My tools', aliases: ['RESEARCH', 'THESIS'] },
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
  { code: 'VAP', name: 'Volume at price', desc: 'Volume profile: where the instrument traded most, the point of control and the 70% value area.', group: 'Security', security: true, aliases: ['VPROFILE', 'PROFILE'] },
  { code: 'OVME', name: 'Option calculator', desc: 'Black–Scholes value and Greeks for any strike and expiry, scenarios, and implied volatility from a price.', group: 'Security', security: true, aliases: ['BS', 'GREEKS', 'OPTCALC'] },
  { code: 'GE', name: 'P/E history', desc: 'Trailing P/E from SEC-filed earnings over 5–15 years, its average and ±1σ/±2σ bands, and the prices each band implies today.', group: 'Security', security: true, equityOnly: true, aliases: ['PEHIST', 'PEBAND'] },
  { code: 'DS', name: 'Filing search', desc: 'Search the text of the latest 10-K, 10-Qs and 8-K press releases: the passages that answer best, by section, with the filing linked.', group: 'Security', security: true, equityOnly: true, aliases: ['DOCS', 'FILSRCH'] },
  { code: 'EM', name: 'Earnings matrix', desc: 'Diluted EPS and revenue by fiscal quarter and year from SEC filings, with growth on a year earlier.', group: 'Security', security: true, equityOnly: true, aliases: ['EMATRIX'] },
  { code: 'CRPR', name: 'Credit profile', desc: 'Synthetic credit rating from interest coverage (Damodaran), default spread and cost of debt, Altman Z, Piotroski F, leverage and liquidity.', group: 'Security', security: true, equityOnly: true, aliases: ['CREDIT', 'ZSCORE'] },
  { code: 'PROB', name: 'Probability lab', desc: 'The price distribution an option expiry implies: chance of rising, percentiles, probability of any level, and fat tails vs a lognormal.', group: 'Security', security: true, aliases: ['PLAB', 'IMPDIST'] },
  { code: 'DARK', name: 'Off-exchange volume', desc: 'FINRA weekly dark-pool (ATS) and wholesaler volume, its share of all trading, and the venues that traded most.', group: 'Security', security: true, equityOnly: true, aliases: ['ATS', 'OFFEX'] },
  { code: 'TRAN', name: 'Earnings-call transcripts', desc: 'Every earnings call by speaker, the latest first; search four years of calls for what management said about any topic.', group: 'Security', security: true, equityOnly: true, aliases: ['TRANSCRIPT', 'CALLS'] },
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
  { code: 'FUTU', name: 'Futu live market depth', desc: 'Live order book, tick-by-tick trades with buy/sell direction, capital flow by order size and the Hong Kong broker queue — from your FutuOpenD (read-only).', group: 'Security', security: true, aliases: ['DEPTH', 'L2', 'BROKERQ'] },
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
  { code: 'EDGE', name: 'Signal board', desc: 'The most unusual readings right now: crowded positioning, prediction-market jumps, port and trade shocks, fund-flow surges.', group: 'Alternative data', aliases: ['SIG', 'ALPHA', 'IDEAS'] },
  { code: 'RISK', name: 'Risk regime', desc: 'Risk-on / risk-off gauge from credit, volatility, curve, dollar, copper/gold and trend — plus the yield-curve recession probability.', group: 'Markets', aliases: ['REGIME', 'RECESS'] },
  { code: 'VOL', name: 'Volatility', desc: 'VIX term structure, VVIX, SKEW, MOVE, oil and gold vol, implied vs realised volatility.', group: 'Markets', aliases: ['VOLA'] },
  { code: 'BRDT', name: 'Market breadth', desc: 'S&P 500 participation: members above 50/200-day averages, advance/decline line, new highs/lows, McClellan, by sector.', group: 'Markets', aliases: ['BREADTH'] },
  { code: 'IMPM', name: 'Earnings implied moves', desc: 'The move options price through each upcoming report vs the stock’s typical post-earnings reaction.', group: 'Markets', aliases: ['EMOVE', 'STRADDLE'] },
  { code: 'UOA', name: 'Unusual options', desc: 'Contracts trading far above open interest across the most active US names; premium and put/call by name.', group: 'Markets', aliases: ['FLOWOPT', 'SWEEP'] },
  { code: 'COT', name: 'Positioning (COT)', desc: 'CFTC Commitments of Traders: hedge funds, asset managers and managed money in 29 futures — crowded longs and shorts.', group: 'Alternative data', aliases: ['CFTC'] },
  { code: 'ENVR', name: 'All Weather environments', desc: 'Bridgewater’s four growth/inflation environments since 1950: today’s environment and what every asset class earned in each.', group: 'Economy & policy', aliases: ['QUADRANTS', 'ENVIRONMENTS', 'ALLWEATHER'] },
  { code: 'AWP', name: 'All Weather portfolio', desc: 'Bridgewater’s All Weather construction — equal risk per environment, levered to a target vol — backtested vs 60/40.', group: 'Economy & policy', aliases: ['RISKPARITY', 'AWEATHER'] },
  { code: 'DCYC', name: 'Debt cycles', desc: 'Dalio’s debt-cycle framework for ~40 economies (BIS credit gaps, debt service) and the US MP1/MP2/MP3 policy stage.', group: 'Economy & policy', aliases: ['DEBTCYCLE', 'BIGDEBT'] },
  { code: 'HGRL', name: 'Holy Grail diversification', desc: 'Dalio’s Holy Grail: how many independent bets your instruments really are, and the risk-vs-streams curve.', group: 'Economy & policy', aliases: ['HOLYGRAIL', 'DIVERSIFY'] },
  { code: 'WPWR', name: 'World power index', desc: 'Dalio’s Changing World Order: education, innovation, competitiveness, output, trade, military, finance and reserve currency.', group: 'Economy & policy', aliases: ['WORLDORDER', 'EMPIRES'] },
  { code: 'CHART', name: 'Formula charts', desc: 'Chart any formula over instruments and FRED series — AAPL/SPY, {^TNX}-FRED:DGS2, ma(SPY,200), yoy(FRED:CPIAUCSL).', group: 'Markets', aliases: ['FORMULA', 'GRAPH'] },
  { code: 'DATA', name: 'Data grid (BDP / BDH)', desc: 'Any fields for up to 100 instruments, or their price history side by side — download as CSV or copy into Excel.', group: 'Markets', aliases: ['BDP', 'BDH', 'GRID'] },
  { code: 'YAS', name: 'Treasuries & bond calculator', desc: 'Every marketable Treasury priced from TreasuryDirect with yield, duration and DV01; price ↔ yield calculator with a shock grid.', group: 'Rates & FX', aliases: ['TSY', 'BONDS', 'BONDCALC'] },
  { code: 'ILBE', name: 'Inflation expectations', desc: 'TIPS breakevens, 5y5y forward, real yields, Cleveland Fed and Michigan expectations vs actual CPI.', group: 'Rates & FX', aliases: ['BREAKEVENS', 'TIPS', 'INFLEXP'] },
  { code: 'FXCA', name: 'FX carry', desc: 'Carry of 25 currencies vs the dollar from central-bank rates, ranked by carry-to-volatility, with forwards and a carry basket.', group: 'Rates & FX', aliases: ['CARRY'] },
  { code: 'MRGR', name: 'Merger arbitrage', desc: 'Announced US mergers found in SEC filings: offer terms, buyer, target price, deal spread and annualised return.', group: 'Markets', aliases: ['DEALS', 'MNA', 'MERGERS'] },
  { code: 'MEMB', name: 'Index members', desc: 'Constituents and weights of the S&P 500, Dow, Nasdaq-100, FTSE 100, DAX, CAC 40, Euro Stoxx 50 and Hang Seng.', group: 'Markets', aliases: ['MEMBERS', 'CONSTITUENTS'] },
  { code: 'FSRC', name: 'ETF screener', desc: '~200 ETFs by cost, size, yield, returns and beta, plus a two-fund overlap comparison.', group: 'Markets', aliases: ['ETFS', 'FUNDS'] },
  { code: 'DVDC', name: 'Dividend & split calendar', desc: 'Upcoming ex-dividend dates and stock splits across US-listed companies.', group: 'Markets', aliases: ['EXDIV', 'DIVCAL'] },
  { code: 'CDR', name: 'Exchange hours', desc: 'Which of 22 exchanges are open now, sessions in local time, time to open/close and upcoming holidays.', group: 'Markets', aliases: ['EXCH', 'HOURS', 'HOLIDAYS'] },
  { code: 'ETFA', name: 'ETF premium / discount', desc: 'How far ~50 major ETFs trade from the value of their holdings (NAV) — the gap ETF market makers arbitrage — and why some gaps are only timing.', group: 'Markets', aliases: ['ETFARB', 'NAV', 'PREM'] },
  { code: 'SPRD', name: 'Pairs & spreads', desc: 'Any two instruments: hedge ratio, spread z-score, cointegration test, half-life and an out-of-sample mean-reversion backtest.', group: 'Markets', aliases: ['PAIRS', 'SPREAD', 'PAIR'] },
  { code: 'IMOV', name: 'Index movers', desc: 'Which members moved the S&P 500, Nasdaq 100 or Dow: each one\'s contribution in index points, breadth and sectors.', group: 'Markets', aliases: ['CONTRIB', 'INDEXMOVERS'] },
  { code: 'TRA', name: 'Total returns', desc: 'Dividend-reinvested returns from 1 day to 5 years for asset classes, sectors, factors, countries or your symbols.', group: 'Markets', aliases: ['TRAY', 'RETURNS', 'PERF'] },
  { code: 'WPE', name: 'World valuations', desc: 'Trailing P/E, earnings yield and dividend yield by country, ranked against the median market.', group: 'Markets', aliases: ['WORLDPE', 'VALUATIONS'] },
  { code: 'MRR', name: 'Member returns', desc: 'Every member of the S&P 500, Nasdaq 100, Dow, FTSE 100, DAX, CAC 40, Euro Stoxx 50 or Hang Seng ranked by return, against the index and by sector.', group: 'Markets', aliases: ['RANKRET'] },
  { code: 'EARN', name: 'Earnings season', desc: 'This reporting season for the S&P 500, Nasdaq 100 or Dow: beat rate, surprises, share reactions to beats and misses, by sector (Bloomberg EA).', group: 'Markets', aliases: ['EASEASON', 'BEATS'] },
  { code: 'ECFC', name: 'Economic forecasts', desc: 'IMF growth, inflation, jobless, current-account and debt forecasts for ~170 countries, against the latest CPI and policy rate.', group: 'Economy & policy', aliases: ['FORECASTS', 'IMF'] },
  { code: 'BORROW', name: 'Short borrow', desc: 'The costliest liquid US stocks to short and index members with high borrow fees, from IBKR\u2019s stock-loan file.', group: 'Markets', aliases: ['HTB', 'SHORTFEE'] },
  { code: 'LEAG', name: 'M&A adviser league', desc: 'Banks ranked by fairness opinions in US public-company mergers over 6–24 months, with the companies (SEC filings).', group: 'Research', aliases: ['LEAGUE', 'ADVISERS'] },
  { code: 'EXTH', name: 'Pre-market & after hours', desc: 'Biggest pre-market and after-hours gainers and losers, filtered by company size.', group: 'Markets', aliases: ['PREMKT', 'AFTERHOURS', 'AH'] },
  { code: 'CBRT', name: 'Central bank rates', desc: 'Policy rates of ~40 central banks (BIS): level, latest decision, 12-month moves and the global easing/tightening cycle.', group: 'Economy & policy', aliases: ['POLICY', 'CENTRALBANKS', 'CBANKS'] },
  { code: 'ECOS', name: 'Economic data explorer', desc: 'Search and chart any of FRED’s 800,000 series — overlay up to four, as levels, changes, year-on-year or rebased.', group: 'Economy & policy', aliases: ['FRED', 'ECON', 'SERIES'] },
  { code: 'CRED', name: 'Credit spreads', desc: 'IG, BBB, high-yield, CCC, euro and EM corporate spreads — levels, changes, 3-year percentiles and stress signals.', group: 'Rates & FX', aliases: ['CREDIT', 'OAS', 'SPREADS'] },
  { code: 'PORT', name: 'Portfolio risk', desc: 'Your holdings’ exposures, volatility, VaR, risk contributions, correlations, factor loadings, stress tests and crisis replays.', group: 'Markets', aliases: ['PRTU', 'STRESS', 'PORTFOLIO'] },
  { code: 'PRED', name: 'Prediction markets', desc: 'Real-money odds (Polymarket, Kalshi) for Fed decisions, inflation, recession, geopolitics — and today’s biggest moves.', group: 'Economy & policy', aliases: ['ODDS', 'POLY', 'KALSHI'] },
  { code: 'NOW', name: 'Nowcasts & trade', desc: 'GDPNow, Cleveland Fed inflation nowcasts, weekly activity, financial conditions, and world trade from ship data — before the official numbers.', group: 'Economy & policy', aliases: ['NOWCAST', 'GDPNOW'] },
  { code: 'FLOW', name: 'Money flow map', desc: 'Where money is moving: cross-border portfolio flows (TIC), bank lending (BIS), ETF creations and money flow, stablecoins, Fed liquidity.', group: 'Alternative data', aliases: ['MONEY', 'CAPF', 'TIC'] },
  { code: 'SHIP', name: 'Shipping tracker', desc: 'Every vessel worldwide (live AIS + satellite), port congestion, ship photos, and traffic through 28 chokepoints.', group: 'Alternative data', aliases: ['AIS', 'VSL', 'CHOKE'] },
  { code: 'FLY', name: 'Flight tracker', desc: 'Every aircraft in the world; zoom in for live detail, routes, airframes, photos and tracks flown.', group: 'Alternative data', aliases: ['PLANE', 'ADSB'] },
  { code: 'QUAK', name: 'Earthquakes', desc: 'Magnitude 4.5+ quakes this week, flagged when near a major port or shipping chokepoint.', group: 'Alternative data', aliases: ['QUAKE', 'HAZ'] },
  { code: 'EIA', name: 'Oil & gas inventories', desc: 'Weekly US crude, gasoline, distillate, SPR and Cushing stocks, and natural-gas storage (EIA).', group: 'Alternative data', aliases: ['DOE', 'INV'] },
  { code: 'WETR', name: 'Weather & energy demand', desc: '16-day heating and cooling degree days vs 10-year normals for US demand centres.', group: 'Alternative data', aliases: ['WEATHER', 'HDD'] },
  { code: 'COMP', name: 'Compare', desc: 'Total-return comparison of up to 8 instruments, with risk and correlation.', group: 'Markets' },
  // Rates & FX
  { code: 'GC', name: 'Yield curves', desc: 'Government curves for the US, UK, Germany, Japan, Canada and Australia.', group: 'Rates & FX', aliases: ['CURVE'] },
  { code: 'BTMM', name: 'Money markets', desc: 'Fed funds, SOFR, bills, coupons, curve spreads, credit spreads, mortgages.', group: 'Rates & FX', aliases: ['RATES'] },
  { code: 'FRD', name: 'FX forwards', desc: 'Outright forwards and forward points, 1 week to 1 year, from interest-rate parity.', group: 'Rates & FX', aliases: ['FWD', 'FXFC'] },
  { code: 'WB', name: 'World bonds', desc: '10-year government yields in ~35 markets: spreads to Treasuries and Bunds, policy rate, real yield, 2s10s and rating.', group: 'Rates & FX', aliases: ['WBOND', 'GOVTS'] },
  { code: 'FOMC', name: 'Fed portal', desc: 'Target range, every decision since 2008, the FOMC\u2019s projections (dots) and how futures pricing compares with them.', group: 'Rates & FX', aliases: ['FED'] },
  { code: 'FWCV', name: 'Forward curves', desc: 'Forward rates implied by government curves (1y1y, 2y1y, 5y5y, 10y10y) for the US, Germany, euro area, UK, Japan, Canada and Australia.', group: 'Rates & FX', aliases: ['FORWARDS', 'CURVF'] },
  { code: 'SWAP', name: 'Swap curves', desc: 'SOFR, \u20acSTR, Euribor, SONIA, TONA and CORRA par swap rates from the day\u2019s reported trades, with US swap spreads to Treasuries.', group: 'Rates & FX', aliases: ['USSW', 'IRS', 'ICVS'] },
  { code: 'CDSX', name: 'Credit indices (CDS)', desc: 'CDX IG, HY and EM and iTraxx Main, Crossover and financials: levels, daily change and history from reported trades.', group: 'Rates & FX', aliases: ['CDX', 'ITRAXX', 'CDS'] },
  { code: 'CDSA', name: 'Single-name CDS activity', desc: 'Which companies\u2019 and countries\u2019 default swaps traded most over recent sessions.', group: 'Rates & FX', aliases: ['SNCDS'] },
  { code: 'WIRP', name: 'Fed rate probabilities', desc: 'Odds of a hike, hold or cut at each FOMC meeting from fed funds futures (FedWatch method).', group: 'Rates & FX', aliases: ['FEDW'] },
  { code: 'AUCT', name: 'Treasury auctions', desc: 'Bills, notes, bonds, TIPS: yield, bid-to-cover vs average, foreign/investor and dealer take-up.', group: 'Rates & FX', aliases: ['AUCTION'] },
  { code: 'WCRS', name: 'FX cross rates', desc: 'Matrix of 18 currencies with today’s moves and strength vs the dollar.', group: 'Rates & FX', aliases: ['FX', 'FXC'] },
  // Research
  { code: 'EQS', name: 'Equity screener', desc: 'Screen 22 markets by sector, size, valuation and yield.', group: 'Research', aliases: ['SCREEN'] },
  { code: '13F', name: 'Investor holdings (13F)', desc: 'What Buffett, Dalio, Ackman, Burry and others own — quarterly 13F filings with changes.', group: 'Research', aliases: ['HFND', 'GURU'] },
  { code: 'IPO', name: 'IPO calendar', desc: 'Upcoming and recent IPOs: date, price range, shares, deal size and status (Finnhub).', group: 'Research', aliases: ['IPOS', 'NEWISSUE'] },
  { code: 'ACTN', name: 'Analyst & company actions', desc: 'Market-wide upgrades, downgrades, initiations and price-target changes with the named analyst, plus company guidance raised or lowered (Benzinga).', group: 'Research', aliases: ['UPGRADES', 'DOWNGRADES', 'GUIDANCE', 'RATINGS'] },
  { code: 'EVTS', name: 'Earnings calendar', desc: 'Who reports this week, with estimates and surprises.', group: 'Research', aliases: ['ERNC', 'CAL'] },
  { code: 'ECO', name: 'Economic calendar', desc: 'Global releases with consensus, previous and actual (US as first published) and the surprise.', group: 'Economy & policy' },
  { code: 'ECST', name: 'Economic surprises', desc: 'US data surprise index since 2010: releases vs their own trend, as first published.', group: 'Economy & policy', aliases: ['CESI', 'SURP'] },
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
