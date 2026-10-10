// Dashboard information architecture: panel groups in trading-day order. Shared by the
// sidebar, the workspace tabs and the command palette.

export interface NavItem {
  id: string;
  label: string;
  icon: string;
  permission: string;
  highlight?: boolean;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

// UPGRADE-9: Reorganized navigation for hedge fund workflow
// FIXED (PART 3): Sidebar reorganized per user spec
// Phase 3 IA redesign — grouped by the trading-day workflow (Brief → Signals → Risk →
// Forecasts → Decide → Positions → System), not by data category. Key fix: DECIDE (execution)
// is split out from POSITIONS (holdings/review). All panel ids preserved; see IA_CURRENT.md.
export const navigation: NavSection[] = [
  {
    title: 'OVERVIEW',
    items: [
      { id: 'macro-model', label: 'Macro Model', icon: '◆', permission: 'master_signal', highlight: true },
      { id: 'morning-brief', label: 'Morning Brief', icon: '☀', permission: 'master_signal', highlight: true },
      { id: 'economic-calendar', label: 'Economic Calendar', icon: '◆', permission: 'economic_calendar', highlight: true },
      { id: 'master-signal', label: 'Master Ensemble', icon: '◆', permission: 'master_signal', highlight: true },
      { id: 'key-metrics', label: 'Key Metrics', icon: '◆', permission: 'key_metrics' },
      { id: 'anomalies', label: 'Anomalies', icon: '◆', permission: 'master_signal' },
      { id: 'regime', label: 'Regime Engine', icon: '◇', permission: 'regime_engine', highlight: true },
      { id: 'regime-playbook', label: 'Regime Playbook', icon: '◇', permission: 'regime_engine', highlight: true },
      { id: 'market-clock', label: 'Market Clock', icon: '◆', permission: 'master_signal' },
      { id: 'global-markets', label: 'Global Markets', icon: '◆', permission: 'master_signal' },
      { id: 'global-correlation', label: 'Global Correlations', icon: '◆', permission: 'master_signal' },
      { id: 'regional-macro', label: 'Global Macro', icon: '◈', permission: 'master_signal', highlight: true },
    ],
  },
  {
    title: 'SIGNALS',
    items: [
      // Actionable consensus first, raw breakdowns below.
      { id: 'ensemble', label: 'Ensemble', icon: '◆', permission: 'ensemble', highlight: true },
      { id: 'signal-stack', label: 'Signal Stack', icon: '◆', permission: 'signal_stack' },
      { id: 'signal-scorecard', label: 'Signal Scorecard', icon: '◆', permission: 'signal_stack', highlight: true },
      { id: 'signal-story', label: 'Signal Storytelling', icon: '◆', permission: 'signal_stack' },
      { id: 'signals', label: 'Signal Interpretation', icon: '◆', permission: 'ml_signals' },
      { id: 'alt-data', label: 'Alt-Data Positioning', icon: '◈', permission: 'signal_stack', highlight: true },
      { id: 'stream-agreement', label: 'Stream Agreement', icon: '◆', permission: 'signal_stack' },
      { id: 'factor-validation', label: 'Factor OOS Validation', icon: '◆', permission: 'factor_decomp' },
      { id: 'model-agreement', label: 'Model Agreement', icon: '◆', permission: 'model_agreement' },
      { id: 'sector-allocation', label: 'Sector Allocation', icon: '◆', permission: 'sector_allocation' },
      { id: 'factor-rotation', label: 'Factor Rotation', icon: '◆', permission: 'factor_rotation' },
      { id: 'cot-positioning', label: 'COT Positioning', icon: '◆', permission: 'signal_stack' },
      { id: 'cta-trend', label: 'CTA Trends', icon: '◆', permission: 'cta_trends' },
      { id: 'news-sentiment', label: 'News Sentiment', icon: '◆', permission: 'news_sentiment' },
    ],
  },
  {
    title: 'RISK',
    items: [
      { id: 'fund-cockpit', label: 'Fund Cockpit', icon: '▣', permission: 'var_drawdown', highlight: true },
      { id: 'cycle-risk', label: 'Cycle & Systemic Risk', icon: '◆', permission: 'var_drawdown', highlight: true },
      { id: 'risk-indicators', label: 'Risk Indicators', icon: '◆', permission: 'risk_indicators', highlight: true },
      { id: 'risk-analytics', label: 'Risk Analytics', icon: '◆', permission: 'var_drawdown', highlight: true },
      { id: 'var-stress', label: 'VaR & Stress', icon: '◆', permission: 'var_drawdown', highlight: true },
      { id: 'factor-exposure', label: 'Factor Exposure', icon: '◆', permission: 'factor_decomp', highlight: true },
      { id: 'horizon-tension', label: 'Horizon Tensions', icon: '◆', permission: 'horizon_tensions', highlight: true },
      { id: 'correlation', label: 'Correlation Regime', icon: '◆', permission: 'correlation' },
      { id: 'correlation-matrix', label: 'Correlation Matrix', icon: '◆', permission: 'correlation' },
      { id: 'debt-cycle', label: 'Debt Cycle', icon: '◆', permission: 'debt_cycle' },
      { id: 'factor-decomposition', label: 'Factor Decomposition', icon: '◆', permission: 'factor_decomp' },
      { id: 'risk-parity', label: 'Risk Parity', icon: '◆', permission: 'risk_parity' },
      { id: 'risk-parity-compare', label: 'Risk Parity Compare', icon: '◆', permission: 'risk_parity' },
      { id: 'advanced', label: 'Advanced Indicators', icon: '◆', permission: 'advanced_indicators' },
    ],
  },
  {
    title: 'FORECASTS',
    items: [
      { id: 'valuation', label: 'Valuation Filter', icon: '◆', permission: 'valuation' },
      { id: 'nowcast', label: 'GDP Nowcast', icon: '◆', permission: 'gdp_nowcast' },
      { id: 'yield-curve', label: 'Yield Curve', icon: '◆', permission: 'master_signal' },
      { id: 'liquidity', label: 'Liquidity Conditions', icon: '◆', permission: 'liquidity' },
      { id: 'sentiment', label: 'Sentiment', icon: '◆', permission: 'sentiment' },
      { id: 'expected-returns', label: 'Expected Returns', icon: '◆', permission: 'expected_returns', highlight: true },
      { id: 'gmo-forecasts', label: 'Long-Run Return Assumptions', icon: '◆', permission: 'gmo_7year' },
      { id: 'regime-transition', label: 'Transition Matrix', icon: '◆', permission: 'regime_transition' },
      { id: 'regime-outlook', label: 'Regime Outlook', icon: '◆', permission: 'regime_transition' },
      { id: 'quadrants', label: 'Four Quadrants', icon: '◆', permission: 'regime_transition' },
      { id: 'event-vol', label: 'Event Volatility', icon: '◆', permission: 'economic_calendar' },
    ],
  },
  {
    title: 'TRADING',
    items: [
      // The IA fix: execution/decision surfaces, split out of Portfolio.
      { id: 'portfolios', label: 'Portfolios', icon: '◆', permission: 'trade_ideas', highlight: true },
      { id: 'strategy-lab', label: 'Strategy Lab', icon: '⚗', permission: 'trade_ideas', highlight: true },
      { id: 'quant-lab', label: 'Quant Lab (build algos)', icon: '⚗', permission: 'trade_ideas', highlight: true },
      { id: 'stock-ideas', label: 'Stock Ideas', icon: '◆', permission: 'trade_ideas', highlight: true },
      { id: 'stock-timing', label: 'Stock Entry Signals', icon: '◆', permission: 'trade_ideas', highlight: true },
      { id: 'stock-backtest', label: 'Entry Model Backtest', icon: '⚗', permission: 'trade_ideas' },
      { id: 'trade-ideas', label: 'Trade Ideas', icon: '◆', permission: 'trade_ideas', highlight: true },
      { id: 'trade-recommendations', label: 'Trade Recommendations', icon: '◆', permission: 'trade_recommendations', highlight: true },
      { id: 'trade-workflow', label: 'Trade Workflow', icon: '⚗', permission: 'trade_ideas', highlight: true },
      { id: 'scenario-analysis', label: 'Scenario Analysis', icon: '◆', permission: 'master_signal' },
      { id: 'momentum-veto', label: 'Momentum Veto', icon: '◆', permission: 'momentum_veto' },
    ],
  },
  {
    title: 'PORTFOLIO',
    items: [
      { id: 'portfolio-positions', label: 'Positions', icon: '▦', permission: 'portfolio_fit', highlight: true },
      { id: 'portfolio', label: 'Model Portfolio', icon: '◆', permission: 'portfolio_fit', highlight: true },
      { id: 'performance-attribution', label: 'Performance Attribution', icon: '◆', permission: 'performance_tracking', highlight: true },
      { id: 'equity-research', label: 'Equity Research', icon: '◆', permission: 'equity_research', highlight: true },
      { id: 'business-layer', label: 'Business Layer', icon: '◆', permission: 'business_layer' },
      { id: 'fx-monitor', label: 'FX Monitor', icon: '◆', permission: 'master_signal' },
      { id: 'commodities-dashboard', label: 'Commodities', icon: '◆', permission: 'master_signal' },
      { id: 'fixed-income-dashboard', label: 'Fixed Income', icon: '◆', permission: 'master_signal' },
      { id: 'international', label: 'International Macro', icon: '◆', permission: 'international_macro' },
      { id: 'reflexivity', label: 'Reflexivity', icon: '◆', permission: 'reflexivity' },
      { id: 'transmission', label: 'Transmission', icon: '◆', permission: 'transmission' },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { id: 'investment-memo', label: 'Investment Memo', icon: '◆', permission: 'investment_memo' },
      { id: 'system-health', label: 'System Health', icon: '◆', permission: 'system_health' },
      { id: 'data-providers', label: 'Data Providers', icon: '◆', permission: 'system_health' },
      { id: 'system-audit', label: 'Audit & Compliance', icon: '◆', permission: 'system_health', highlight: true },
      { id: 'data-explorer', label: 'Data Explorer', icon: '◆', permission: 'system_health' },
    ],
  },
];

/** Workspace (group title) that contains a panel id, or null. */
export function groupOf(id: string): string | null {
  return navigation.find((s) => s.items.some((i) => i.id === id))?.title ?? null;
}
