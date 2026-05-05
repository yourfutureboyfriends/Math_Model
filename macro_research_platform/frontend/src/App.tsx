// Phase 8 Terminal Redesign — App Entry Point
// Uses TerminalShell for 3-panel institutional layout

import { useState, useEffect } from 'react';
import { TerminalShell } from '@/components/layout/TerminalShell';
import { MasterSignalSection } from '@/components/sections/MasterSignalSection';
import { KeyMetricsSection } from '@/components/sections/KeyMetricsSection';
import { RegimeSection } from '@/components/sections/RegimeSection';
import { SignalStackSection } from '@/components/sections/SignalStackSection';
import { SectorAllocationSection } from '@/components/sections/SectorAllocationSection';
import { FactorRotationSection } from '@/components/sections/FactorRotationSection';
import { RiskIndicatorsSection } from '@/components/sections/RiskIndicatorsSection';
import { NowcastSection } from '@/components/sections/NowcastSection';
import { LiquiditySection } from '@/components/sections/LiquiditySection';
import { SentimentSection } from '@/components/sections/SentimentSection';
import { DebtCycleSection } from '@/components/sections/DebtCycleSection';
import { AdvancedIndicatorsSection } from '@/components/sections/AdvancedIndicatorsSection';
import { GMOForecastsSection } from '@/components/sections/GMOForecastsSection';
import { ReflexivitySection } from '@/components/sections/ReflexivitySection';
import { FactorDecompositionSection } from '@/components/sections/FactorDecompositionSection';
import { HorizonTensionSection } from '@/components/sections/HorizonTensionSection';
import { PortfolioAnalyserSection } from '@/components/sections/PortfolioAnalyserSection';
import { CTATrendSection } from '@/components/sections/CTATrendSection';
import { BusinessLayerSection } from '@/components/sections/BusinessLayerSection';
import { AnomalyDetectionSection } from '@/components/sections/AnomalyDetectionSection';
import { LSTMSection } from '@/components/sections/LSTMSection';
import { EnsembleSection } from '@/components/sections/EnsembleSection';
import { PerformanceTrackingSection } from '@/components/sections/PerformanceTrackingSection';
import { SystemHealthSection } from '@/components/sections/SystemHealthSection';
import { ConnectionStatus } from '@/components/ConnectionStatus';
import { MarketClockBar } from '@/components/MarketClockBar';
import { CorrelationRegimeSection } from '@/components/sections/CorrelationRegimeSection';
import { ExpectedReturnsSection } from '@/components/sections/ExpectedReturnsSection';
import { InternationalMacroSection } from '@/components/sections/InternationalMacroSection';
import { NewsSentimentSection } from '@/components/sections/NewsSentimentSection';
import { MomentumVetoSection } from '@/components/sections/MomentumVetoSection';
import { RegimeTransitionSection } from '@/components/sections/RegimeTransitionSection';
import { RiskParitySection } from '@/components/sections/RiskParitySection';
import { ValuationSection } from '@/components/sections/ValuationSection';
import { DataToWatchSection } from '@/components/sections/DataToWatchSection';
import { ModelAgreementSection } from '@/components/sections/ModelAgreementSection';
import { InvestmentMemoSection } from '@/components/sections/InvestmentMemoSection';
import { TransmissionSection } from '@/components/sections/TransmissionSection';
import { useDashboard } from '@/hooks/useDashboard';
import { useMarketStream } from '@/hooks/useMarketStream';
import { formatDate } from '@/lib/utils';
import { AIChat } from '@/components/AIChat';
import { AlertTriangle, X } from 'lucide-react';

function App() {
  const { data, loading, error, refetch } = useDashboard();
  const { isConnected, regimeChange } = useMarketStream();
  const [showRegimeModal, setShowRegimeModal] = useState(false);
  const [currentRegimeAlert, setCurrentRegimeAlert] = useState<any>(null);

  // Handle regime change modal
  useEffect(() => {
    if (regimeChange) {
      setCurrentRegimeAlert(regimeChange);
      setShowRegimeModal(true);

      // Auto-dismiss after 10 seconds
      const timer = setTimeout(() => {
        setShowRegimeModal(false);
      }, 10000);

      return () => clearTimeout(timer);
    }
  }, [regimeChange]);

  if (error) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <div className="text-center p-8">
          <div className="text-xl font-bold text-red mb-2 font-mono">ERROR</div>
          <p className="text-text-secondary text-sm mb-4">{error.message}</p>
          <button
            onClick={refetch}
            className="terminal-btn-primary px-4 py-2"
          >
            RETRY
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <TerminalShell
        latestDate={data?.metadata.latestDate ? formatDate(data.metadata.latestDate) : undefined}
        dataStatus={data?.metadata.dataStatus}
        mode={data?.metadata.mode}
        currentRegime={data?.regime.current}
        alertCount={data?.alerts?.active?.length || 0}
        onRefresh={refetch}
        loading={loading}
        data={data}
      >
      {/* WebSocket Status Bar */}
      <div className="px-4 pt-4 pb-0">
        <div className="flex items-center justify-between gap-4 mb-4">
          <ConnectionStatus />
          <div className="text-xs text-text-secondary">
            {isConnected ? (
              <span className="text-green">● WebSocket Connected</span>
            ) : (
              <span className="text-yellow">○ Connecting...</span>
            )}
          </div>
        </div>
        <MarketClockBar />
      </div>

      {/* Regime Change Modal */}
      {showRegimeModal && currentRegimeAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface-1 border border-yellow/30 rounded-lg p-6 max-w-md w-full shadow-2xl">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-yellow/20 rounded-lg">
                  <AlertTriangle className="w-6 h-6 text-yellow" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-text-primary">
                    Regime Change Alert
                  </h3>
                  <p className="text-sm text-text-secondary">
                    Macro regime has shifted
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowRegimeModal(false)}
                className="p-1 hover:bg-surface-2 rounded transition-colors"
              >
                <X className="w-5 h-5 text-text-secondary" />
              </button>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center py-2 border-b border-border">
                <span className="text-text-secondary">New Regime</span>
                <span className="text-xl font-bold text-yellow">
                  {currentRegimeAlert.regime}
                </span>
              </div>

              {currentRegimeAlert.details && (
                <div className="text-sm text-text-secondary space-y-1">
                  <div className="flex justify-between">
                    <span>Confidence</span>
                    <span className="text-text-primary">
                      {(currentRegimeAlert.details.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Timestamp</span>
                    <span className="text-text-primary">
                      {new Date(currentRegimeAlert.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              )}
            </div>

            <div className="mt-6 flex gap-3">
              <button
                onClick={() => setShowRegimeModal(false)}
                className="flex-1 py-2 px-4 bg-yellow/20 hover:bg-yellow/30 text-yellow rounded font-medium transition-colors"
              >
                Acknowledge
              </button>
            </div>
          </div>
        </div>
      )}

      {loading && !data ? (
        <div className="p-4 space-y-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-32 bg-surface-1 border border-border animate-shimmer" />
          ))}
        </div>
      ) : data ? (
        <div className="p-4 space-y-4">
          {/* 01 — Master Signal */}
          <section id="master-signal">
            <MasterSignalSection data={data.ensembleSignal} />
          </section>

          {/* 02 — Key Metrics */}
          <section id="key-metrics">
            <KeyMetricsSection data={data.keyMetrics} />
          </section>

          {/* 03 — Regime Classification */}
          <section id="regime">
            <RegimeSection data={data.regime} />
          </section>

          {/* 04 — ML Layer */}
          <section id="ml-signals" className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <AnomalyDetectionSection data={data.anomalyDetection} />
            <LSTMSection data={data.lstmPrediction} />
          </section>

          {/* 05 — Ensemble & Performance */}
          <section id="ensemble">
            <EnsembleSection data={data.ensembleSignal} />
            <PerformanceTrackingSection data={data.performanceTracking} />
          </section>

          {/* 06 — Signal Stack */}
          <section id="signal-stack">
            <SignalStackSection data={data.signalStackV2 || data.signalStack} />
          </section>

          {/* 07 — Sector Allocation */}
          <section id="sector-allocation">
            <SectorAllocationSection data={data.sectorAllocation} />
          </section>

          {/* 08 — Factor Rotation */}
          <section id="factor-rotation">
            <FactorRotationSection data={data.factorRotation} />
          </section>

          {/* 09 — Risk Indicators */}
          <section id="risk-indicators">
            <RiskIndicatorsSection data={data.riskIndicators} geopoliticalData={data.geopoliticalRisk} />
          </section>

          {/* 10 — Debt Cycle */}
          <section id="debt-cycle">
            <DebtCycleSection data={data.debtCycle} />
          </section>

          {/* 11 — Advanced Indicators */}
          <section id="advanced">
            <AdvancedIndicatorsSection data={data.advancedIndicators} />
          </section>

          {/* 12 — GDP Nowcast */}
          <section id="nowcast">
            <NowcastSection data={data.nowcast} />
          </section>

          {/* 13 — Liquidity */}
          <section id="liquidity">
            <LiquiditySection data={data.liquidity} />
          </section>

          {/* 14 — Sentiment */}
          <section id="sentiment">
            <SentimentSection data={data.sentiment} optionsData={data.optionsIntelligence} />
          </section>

          {/* 15 — GMO Forecasts */}
          <section id="gmo">
            <GMOForecastsSection data={data.gmoForecasts} />
          </section>

          {/* 15a — Valuation */}
          <section id="valuation">
            <ValuationSection data={data.valuation} />
          </section>

          {/* 15b — Expected Returns */}
          <section id="expected-returns">
            <ExpectedReturnsSection data={data.expectedReturns} />
          </section>

          {/* 15c — International Macro */}
          <section id="international-macro">
            <InternationalMacroSection data={data.internationalMacro} />
          </section>

          {/* 16 — Reflexivity */}
          <section id="reflexivity">
            <ReflexivitySection data={data.reflexivity} />
          </section>

          {/* 16a — Transmission */}
          <section id="transmission">
            <TransmissionSection data={data.transmissionAnalysis} />
          </section>

          {/* 16b — Regime Transition */}
          <section id="regime-transition">
            <RegimeTransitionSection data={data.regimeTransitions} />
          </section>

          {/* 16c — Correlation Regime */}
          <section id="correlation-regime">
            <CorrelationRegimeSection data={data.correlationRegime} />
          </section>

          {/* 17 — Factor Decomposition */}
          <section id="factor-decomp">
            <FactorDecompositionSection data={data.factorDecomposition} />
          </section>

          {/* 17a — Risk Parity */}
          <section id="risk-parity">
            <RiskParitySection data={data.riskParityAllocation} />
          </section>

          {/* 17b — Momentum Veto */}
          <section id="momentum-veto">
            <MomentumVetoSection data={data.momentumVeto} />
          </section>

          {/* 18 — Horizon Tensions */}
          <section id="horizon">
            <HorizonTensionSection data={data.horizonAnalysis} />
          </section>

          {/* 18a — Model Agreement */}
          <section id="model-agreement">
            <ModelAgreementSection data={data.modelAgreement} />
          </section>

          {/* 19 — CTA Trends */}
          <section id="cta-trends">
            <CTATrendSection data={data.trendSignals} />
          </section>

          {/* 19a — News Sentiment */}
          <section id="news-sentiment">
            <NewsSentimentSection data={data.newsSentiment} />
          </section>

          {/* 20 — Portfolio */}
          <section id="portfolio-fit">
            <PortfolioAnalyserSection
              data={data.portfolioAnalytics}
              simulationData={data.portfolioSimulation}
            />
          </section>

          {/* 20a — Data to Watch */}
          <section id="data-to-watch">
            <DataToWatchSection data={data.dataToWatch} />
          </section>

          {/* 20b — Investment Memo */}
          <section id="investment-memo">
            <InvestmentMemoSection data={data.investmentMemo} />
          </section>

          {/* 21 — Business Layer */}
          <section id="business-layer">
            <BusinessLayerSection data={data.businessLayer} />
          </section>

          {/* 22 — System Health */}
          <section id="system-health">
            <SystemHealthSection performanceData={data.performanceTracking} />
          </section>
        </div>
      ) : null}
      </TerminalShell>

      {/* AI Chat Widget */}
      <AIChat />
    </>
  );
}

export default App;
