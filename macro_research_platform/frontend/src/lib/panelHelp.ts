// Plain-English help for every dashboard panel, keyed by panelId() (lib/focusMode).
// Shown by the "?" button DashboardPage adds to each panel header: what the panel shows,
// how to read it, and what to do with it — so a new PM or analyst can use any panel
// without knowing the model behind it.

export interface PanelHelp {
  what: string;              // what the panel shows
  read: string;              // how to read it
  use?: string;              // what to do with it
  terms?: [string, string][]; // jargon used on the panel
}

const SHARPE: [string, string] = ['Sharpe', 'Return per unit of volatility (above cash). ~0.5 is typical for a market, >1 is strong.'];
const DD: [string, string] = ['Max drawdown', 'Worst peak-to-trough loss over the period.'];
const Z: [string, string] = ['z-score / σ', 'How many standard deviations a value is from its own history. Beyond ±2 is unusual.'];
const REGIME: [string, string] = ['Regime', 'Growth/inflation quadrant: Goldilocks (growth↑ inflation↓), Reflation (both↑), Stagflation (growth↓ inflation↑), Slowdown/Deflation (both↓).'];

export const PANEL_HELP: Record<string, PanelHelp> = {
  'my-desk': {
    what: 'Your personal start page: open tasks for your role, the book’s key numbers, and shortcuts.',
    read: 'The queue lists things that need attention (new data releases, big market moves, stale accounts). The tiles summarise NAV, P&L, risk and the current regime.',
    use: 'Work the queue top to bottom; click a shortcut to jump to the panel.',
  },
  'macro-model': {
    what: 'The systematic macro model end to end: economic state → regime odds next month → expected returns & target portfolio → backtest → orders.',
    read: 'Step 1 charts the growth and inflation factors. Step 2 gives the probability of each regime next month. Step 3 turns those into expected returns and a target allocation.',
    use: 'Use the target weights as the strategic anchor; stage orders from the last step (they go through four-eyes approval).',
    terms: [REGIME, ['Factor', 'A single number summarising many economic series (here: growth and inflation).']],
  },
  'morning-brief': {
    what: 'Today’s one-screen summary: the regime, top priorities, key risks this week and the highest-conviction ideas.',
    read: 'Priorities are generated from what changed in the data; risks list scheduled events and stretched readings.',
    use: 'Read it first each morning, then drill into the panels it mentions.',
  },
  'master-signal': {
    what: 'The single composite signal: one score from strong risk-off to strong risk-on.',
    read: 'The marker on the scale is the current reading. Conviction and agreement say how much the inputs agree; risk budget scales position sizes (1.0× = normal).',
    use: 'Treat it as the default stance; size up when conviction is high, down when the inputs disagree.',
  },
  'key-metrics': {
    what: 'The core macro readings: growth, inflation, financial conditions, risk appetite, recession odds and how long the regime has lasted.',
    read: 'Scores run 0–1 (higher = stronger growth, hotter inflation, looser conditions, more risk appetite). Arrows show the recent direction; the sparkline is the history.',
    use: 'A quick health check; hover a tile for its source and formula.',
  },
  'anomalies-wrap': {
    what: 'Markets moving unusually far from their normal range today.',
    read: 'Each chip shows the asset, the price and how many standard deviations the move is (e.g. −3.3σ). Only moves beyond ±2σ appear.',
    use: 'Check whether an anomaly has a news reason before acting; repeated anomalies often precede regime change.',
    terms: [Z],
  },
  regime: {
    what: 'The current market regime from the signal model, with its confidence and how long it has lasted.',
    read: 'The factor table shows which inputs drive the call; the history strip shows recent classifications.',
    use: 'Sets the playbook used by allocation, sectors and trade ideas.',
    terms: [REGIME],
  },
  'regime-playbook': {
    what: 'What to own in the current regime: tactical asset-class ranges and factor preferences.',
    read: 'Green = favoured, red = avoid; the range is the suggested weight band. Returns by regime come from history, not a forecast.',
    use: 'Check your portfolio sits inside these bands.',
  },
  'market-clock': {
    what: 'Which major exchanges are open right now, in UTC and local time.',
    read: 'Green = open. Liquidity is thinnest when only one region is open.',
  },
  'global-markets': {
    what: 'Major equity indices around the world with today’s change.',
    read: 'Click any index to open its chart.',
  },
  'global-correlation': {
    what: 'How closely world markets, currencies and commodities move together.',
    read: 'Blue = move together, orange = move opposite. Darker = stronger. Hover any cell for a plain-English reading.',
    use: 'Diversification comes from combining assets with low or negative correlation.',
    terms: [['Correlation', 'From −1 (always opposite) through 0 (unrelated) to +1 (always together).']],
  },
  'regional-macro': {
    what: 'Policy rates, inflation, unemployment and growth for ~25 economies, plus recent central-bank moves.',
    read: 'Real policy rate = policy rate − inflation: positive means policy is restrictive. Inflation vs target shows who is above (red) or below (blue) their goal. Off-scale bars are cut with a break mark.',
    use: 'Countries far above target with negative real rates are candidates for hikes; the reverse for cuts.',
  },
  ensemble: {
    what: 'An equal-weighted vote of the main models (growth, recession, risk appetite, liquidity).',
    read: 'The score is the average (0–1); bars show each model’s contribution. Agreement is the share of models pointing the same way.',
    use: 'High agreement = more reliable signal.',
  },
  'signal-stack': {
    what: 'The layered signal stack — each layer (growth, inflation, liquidity, risk, regime) and its vote.',
    read: 'Layers are listed in priority order; the bar shows each layer’s confidence. The top box is the combined call.',
  },
  'signal-scorecard': {
    what: 'How well each signal has actually predicted returns, tested walk-forward (no look-ahead).',
    read: 'Hit rate = share of calls that were right (50% = coin flip). The rows show average forward return when the signal was bullish, neutral or bearish.',
    use: 'Trust signals with hit rates clearly above 50% and a positive bullish-minus-bearish spread.',
    terms: [SHARPE, DD],
  },
  'signal-story-wrap': {
    what: 'Why each signal reads what it does — the underlying data behind growth, inflation, liquidity and risk.',
    read: 'Each card names the inputs and the latest values that produced the score.',
  },
  signals: {
    what: 'The four core signals with their latest level, 3-month change and history.',
    read: 'Scores run 0–1; the arrow shows direction over 3 months.',
  },
  'alt-data': {
    what: 'Alternative data: VIX futures curve, cross-market correlations and credit stress.',
    read: 'Contango (later VIX futures higher) is normal and calm; backwardation signals stress. Credit spreads widening = rising default fear.',
  },
  'stream-agreement': {
    what: 'Whether the independent signal streams (macro, inter-market, capital flows) agree.',
    read: 'More streams agreeing = higher conviction, and a larger allowed risk budget.',
  },
  'factor-validation': {
    what: 'Out-of-sample test of the equity factors (value, momentum, quality, size, low-vol).',
    read: 'IS = in-sample fit, OOS = how it did on data it wasn’t fitted to. A big drop from IS to OOS means the factor may be overfitted and is flagged unstable.',
    terms: [['R²', 'Share of variation explained (0–1).'], DD],
  },
  'model-agreement': {
    what: 'Whether the different models reach the same conclusion.',
    read: '1.00 = full agreement. Disagreements are listed underneath.',
  },
  'sector-allocation': {
    what: 'Sector over/underweights for the current regime, adjusted for each sector’s relative strength.',
    read: 'Score from −1 to +1 (positive = favoured). Signal combines the regime playbook with recent performance vs the S&P 500.',
    use: 'Tilt equity exposure toward overweight sectors.',
  },
  'factor-rotation': {
    what: 'Which equity style (growth, quality, momentum, value) is currently leading.',
    read: 'Scores 0–1 = how strong the style’s recent outperformance is vs its past year.',
  },
  'cot-positioning': {
    what: 'How speculators are positioned in futures (CFTC Commitments of Traders, weekly).',
    read: 'Net position as % of open interest. Extreme readings (top/bottom 10% of history) are highlighted — crowded trades can reverse sharply.',
    use: 'Be cautious joining an extremely crowded trade.',
  },
  'cta-trend': {
    what: 'What trend-following funds (CTAs) are likely doing across major futures.',
    read: 'Returns over 1, 3 and 12 months; green = up-trend. “Confirmed” means the horizons agree.',
    use: 'Strong agreed trends tend to persist; a break often triggers forced selling.',
  },
  'news-sentiment': {
    what: 'Tone of the latest financial headlines (Bloomberg, CNBC, FT), scored with a finance word list.',
    read: 'Score from −100 (very negative) to +100. Themes need at least 3 headlines to get a score. Click headlines to see the extremes.',
    use: 'A contrarian input at extremes; a divergence from the regime is a heads-up, not a signal on its own.',
  },
  'risk-indicators': {
    what: 'Headline market-risk gauges: VIX, yield curve and credit spreads.',
    read: 'Risk appetite runs 0–1 (high = risk-on). Each indicator is graded low/medium/high risk.',
  },
  'fund-cockpit': {
    what: 'The fund at a glance: NAV, P&L, exposure, risk limits, rebalancing and orders.',
    read: 'Tabs switch between track record, risk limits, rebalance proposals, the order blotter and the model scorecard.',
    use: 'Check limits are green before trading.',
    terms: [SHARPE, DD, ['Beta $', 'How many dollars the book moves for a 1% market move.']],
  },
  'cycle-risk': {
    what: 'Slow-moving systemic and cycle-risk measures from academic research (recession spread, bond premium, turbulence, absorption).',
    read: 'Each card cites its source paper. Turbulence and absorption spike before crises; the bond premium falls when credit is complacent.',
  },
  'risk-analytics': {
    what: 'Portfolio risk statistics: returns, drawdowns, correlations, stress tests and scenarios.',
    read: 'Use the tabs. VaR = loss not exceeded on 95% of days; CVaR = average loss on the worst 5%.',
    terms: [SHARPE, DD, ['Sortino', 'Like Sharpe but only penalises downside volatility.'], ['Calmar', 'Annual return ÷ max drawdown.']],
  },
  'var-stress': {
    what: 'How much the book could lose: Value-at-Risk three ways, historical crisis replays and custom shocks.',
    read: 'VaR 95% 1-day = a loss you should exceed only 1 day in 20. Stress rows replay real crises on today’s positions.',
    use: 'Type shocks into the custom scenario to test a view.',
  },
  'factor-exposure': {
    what: 'How exposed the book is to broad market factors (equity beta, rates, USD, momentum…).',
    read: 'Bars show sensitivity; red = negative exposure.',
  },
  'horizon-tension': {
    what: 'Upcoming high-impact economic events over the next 7, 30 and 90 days.',
    read: 'Risk density counts high-impact events per horizon; the table lists them by date.',
  },
  correlation: {
    what: 'Whether stocks and bonds are moving together or opposite (the key to whether bonds hedge equities).',
    read: 'Negative = bonds hedge stocks (normal since 2000). Positive = they fall together, so a 60/40 portfolio is less diversified.',
    use: 'When positive, the panel suggests a risk-parity adjustment.',
  },
  'correlation-matrix-wrap': {
    what: 'Correlation between the main asset classes over a chosen window (3M / 6M / 1Y).',
    read: 'Blue = move together, orange = move opposite. Hover a cell for a plain-English reading.',
  },
  'debt-cycle': {
    what: 'Where the long-term debt cycle stands: total, private and public debt to GDP and the debt-service burden.',
    read: 'Rising debt with a rising service ratio = late cycle; falling = deleveraging.',
  },
  'factor-decomposition': {
    what: 'What actually drives the Nasdaq 100: market, size, value, momentum, quality and rates.',
    read: 'Dots show each factor exposure with a 95% confidence interval; “highly significant” factors genuinely matter. Model fit (R²) is how much is explained.',
    terms: [['t-stat', 'Above ~2 means the exposure is statistically real, not noise.']],
  },
  'risk-parity': {
    what: 'A risk-parity portfolio: weights set so each asset contributes equal risk.',
    read: 'Volatile assets get smaller weights. The donut shows target weights; leverage scales the book to the volatility target.',
  },
  'risk-parity-compare': {
    what: 'Several risk-parity methods compared with a 60/40 portfolio, walk-forward.',
    read: '“Beats” means the method had a higher Sharpe than 60/40. The bands show how close each asset is to equal risk.',
    terms: [SHARPE, DD],
  },
  advanced: {
    what: 'Leading indicators of recession and the cycle: Sahm rule, credit impulse, leading index.',
    read: 'Sahm rule ≥ 0.50 has marked the start of every US recession since 1970. Credit impulse = change in new credit as % of GDP.',
  },
  valuation: {
    what: 'Whether major assets look cheap or expensive vs their own history.',
    read: 'Z-score > +1 = expensive (for yields: bonds cheap), < −1 = cheap.',
    terms: [Z],
  },
  nowcast: {
    what: 'Real-time estimate of this quarter’s US GDP growth (Atlanta Fed GDPNow).',
    read: 'Annualised % growth; it updates as data is released through the quarter.',
  },
  'yield-curve': {
    what: 'Government bond yields across maturities for the US and other countries, today vs 1 month and 1 year ago.',
    read: 'An upward slope is normal. Inverted (short rates above long) has preceded recessions. 2s10s = 10-year minus 2-year yield.',
  },
  liquidity: {
    what: 'Financial conditions: how easy or tight money and credit are.',
    read: 'Score 0–1 (high = loose / supportive). The donut shows which inputs drive the score.',
  },
  sentiment: {
    what: 'Market sentiment from volatility, the VIX term structure and cross-asset momentum.',
    read: 'Risk appetite 0–100. Extreme fear is often a contrarian buy signal; extreme greed a warning.',
  },
  'expected-returns': {
    what: 'Expected return for the coming year, weighted across the regime scenarios.',
    read: 'Each scenario shows its probability and historical return range; the headline is the probability-weighted average.',
  },
  'gmo-forecasts': {
    what: 'Long-run (7–10 year) return assumptions per asset class from building blocks.',
    read: 'Equities = earnings yield + inflation; bonds = current yield. Bars split the return into its parts.',
    use: 'For strategic allocation, not trading.',
  },
  'regime-transition': {
    what: 'How likely each regime is to switch to another next month, from history.',
    read: 'Each row is “from”, each column “to”. The diagonal is the chance of staying put.',
    terms: [REGIME],
  },
  'regime-outlook-wrap': {
    what: 'Next-month probabilities for the growth/inflation quadrant.',
    read: 'Bars show the probability of each quadrant next month starting from today’s.',
  },
  quadrants: {
    what: 'Where we sit on the growth/inflation map and what tends to work there.',
    read: 'The highlighted box is today’s quadrant; favoured and unfavoured assets are listed.',
    terms: [REGIME],
  },
  'event-vol-wrap': {
    what: 'How much the S&P 500 typically moves around the next big release (e.g. CPI).',
    read: 'Compares realised volatility around past releases with normal days.',
    use: 'Size positions down before high-impact events if the event window is much more volatile.',
  },
  portfolios: {
    what: 'Your two books: My Portfolio (stocks you pick, reviewed by the model) and the Auto Portfolio (paper-traded by the model), plus the optimiser.',
    read: 'Auto Portfolio fills at the next market open with a stop (2.5× ATR), a target (2R) and a 63-day time limit. It is simulated — no real orders.',
    use: 'Use Backtest & research to see how the auto rules did historically, and the Optimiser to size a basket.',
    terms: [['ATR', 'Average True Range — the typical daily move; stops are set as a multiple of it.'], ['R', 'Risk unit = distance from entry to stop. 2R target = twice the risk.']],
  },
  'strategy-lab': {
    what: 'Five research-backed strategies (trend, sector momentum, low-vol, residual momentum, auto book) and an equal-risk combination of them.',
    read: 'The chart shows growth of $1 for each. The combined book usually has the best risk-adjusted return because the strategies are lowly correlated.',
    terms: [SHARPE, DD],
  },
  'stock-ideas': {
    what: 'Stocks that pass the model screen today, split into buy-now and wait-for-pullback.',
    read: 'Each card shows trend, momentum, entry zone, stop, target and the reward/risk ratio. Tags flag weaknesses (e.g. weak profitability).',
    use: 'Click “Full analysis” before acting.',
  },
  'stock-timing': {
    what: 'Look up any stock and see whether the entry model says buy, wait or avoid — and why.',
    read: 'Type a ticker or name, then read each check (trend, momentum, earnings, quality).',
  },
  'stock-backtest': {
    what: 'How the stock entry model performed historically across ~1,500 stocks and 20+ years.',
    read: 'Compares the model with no-signal, risk-on-only and equal-weight controls. Findings say plainly whether each rule helped.',
    terms: [SHARPE, DD],
  },
  'trade-ideas': {
    what: 'Active trade ideas generated from the current regime, with entry, target and stop.',
    read: 'R:R = reward-to-risk; above 1.5× is attractive. “Regime valid” means the idea still fits today’s regime.',
  },
  'trade-recommendations': {
    what: 'Allocation recommendations: stance, key themes and long-run expected returns per asset class.',
    read: 'Themes explain the reasoning; expected returns are annualised building-block estimates.',
  },
  'trade-workflow': {
    what: 'Pre-trade check and order workflow: test a trade’s impact, then submit for approval.',
    read: 'The what-if shows how the trade changes risk before you place it. Orders need a second approver (four-eyes).',
  },
  'scenario-analysis': {
    what: 'The main scenarios for the next period with their probabilities and expected returns.',
    read: 'Dots show the expected return with its 95% range; the donut shows the probabilities.',
  },
  'momentum-veto': {
    what: 'A momentum safety check: blocks adding equity risk when 12-month momentum is negative.',
    read: 'PASS = momentum supports the position; VETO = trend is against it.',
  },
  'portfolio-positions': {
    what: 'Your live positions with P&L, exposure by book and asset class.',
    read: 'Gross = longs + shorts; net = longs − shorts. Use “Add / Import” to load positions.',
  },
  portfolio: {
    what: 'The model’s target portfolio and how far current holdings drift from it.',
    read: 'Drift bars: right = overweight vs target, left = underweight.',
    use: 'Rebalance when drift exceeds your tolerance.',
  },
  'performance-attribution': {
    what: 'Where the P&L came from: market factors vs stock selection, by book and by position.',
    read: 'Systematic = explained by factor exposure; idiosyncratic = stock-specific (selection skill).',
  },
  'equity-research': {
    what: 'Sector ratings for the current regime, based on relative strength.',
    read: 'Overweight / Neutral / Underweight per sector.',
  },
  'business-layer': {
    what: 'Strategy summary: live recommendations with supporting evidence, risks and actions.',
    read: 'Expand each section for expected returns, position sizing, the signal scorecard and the decision log.',
  },
  'fx-monitor': {
    what: 'Major currency pairs with daily, weekly and monthly changes and trend.',
    read: 'Prices use market quoting conventions (EUR/USD 4 decimals, USD/JPY 2). Click a pair to chart it. Refreshes every 5 minutes.',
  },
  'commodities-dashboard': {
    what: 'Energy, metals and agriculture prices with macro read-throughs (copper/gold ratio, oil trend).',
    read: 'Copper/gold rising = growth optimism. Refreshes every 5 minutes.',
  },
  'fixed-income-dashboard': {
    what: 'Treasury yields across the curve, credit spreads and inflation expectations.',
    read: 'Spreads = extra yield over Treasuries; widening means more credit stress. Breakeven = market-implied inflation.',
  },
  international: {
    what: 'Equity regime for the US, Europe, UK and Japan, and how in-sync they are.',
    read: 'Divergence shows how far each region is from the others. High sync = less regional diversification.',
  },
  reflexivity: {
    what: 'Self-reinforcing feedback loops across markets (e.g. falling stocks → wider credit spreads → more selling).',
    read: 'Active loops amplify moves; inactive loops are monitored with their trigger levels.',
  },
  transmission: {
    what: 'Whether monetary policy is getting through to the economy, channel by channel.',
    read: 'Active = the channel is transmitting policy; mixed = partial; restricted = blocked.',
  },
  'economic-calendar': {
    what: 'Upcoming US data releases with prior values.',
    read: 'H/M/L = expected market impact. Filter by importance with the buttons at the top right.',
  },
  'investment-memo': {
    what: 'An auto-written investment memo: regime summary, key points, risks and opportunities.',
    read: 'Generated from the live data; use it as a first draft for a written view.',
  },
  'system-health': {
    what: 'Whether data feeds and models are up and data is fresh.',
    read: 'Green = live and loaded. Freshness counts series current with their release calendar.',
  },
  'data-providers-wrap': {
    what: 'The data vendors behind the terminal and how each is performing.',
    read: 'Lower priority number = tried first; the router falls back automatically if one fails.',
  },
  'system-audit': {
    what: 'Audit trail: every decision and setting change, plus point-in-time snapshots of the system state.',
    read: 'Log a decision with a rationale for compliance. Pick a snapshot to see what the system showed at that time.',
  },
  'data-explorer': {
    what: 'The raw data behind the dashboard, section by section.',
    read: 'Expand a section to inspect the exact values the panels are drawing.',
  },
};
