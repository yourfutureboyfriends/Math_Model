/**
 * Business Layer Adapter
 * Normalizes backend API responses to stable frontend types
 */

export interface BackendSummary {
  regime: string;
  conviction: string;
  overall_position: string;
  key_themes: string[];
}

export interface BackendRecommendation {
  asset: string;
  return_1y: number;
  confidence: string;
}

export interface BackendPositionSizing {
  asset: string;
  target: number;
  range: string;
  conviction: string;
}

export interface BackendSignalScorecard {
  signal: string;
  value: number | string;
  status: string;
}

export interface BackendRecommendationsResponse {
  summary: BackendSummary | null;
  expected_returns: BackendRecommendation[];
  position_sizing: BackendPositionSizing[];
  signal_scorecard: BackendSignalScorecard[];
  timestamp: string;
}

// Frontend types (what components expect)
export interface FrontendExpectedReturn {
  asset_class: string;
  expected_return_score: number;
  conviction?: string;
  rationale?: string;
  sharpe_estimate?: number;
}

export interface FrontendPositionSizing {
  asset_class: string;
  recommended_weight: number;
  min_weight?: number;
  max_weight?: number;
  conviction?: string;
  bucket?: string;
  rationale?: string;
}

export interface ParsedRecommendation {
  type: string;
  headline: string;
  detail: string;
  conviction: string;
  positionSize: string;
  supportingSignals: string[];
  opposingSignals: string[];
  riskToView: string;
  dataToWatch: string[];
  businessRelevance: string;
  suggestedAction: string;
}

/**
 * Normalize the recommendations input from backend
 * Backend returns object with regime/conviction/key_themes
 * Frontend component expects parsed recommendations array
 */
export function normalizeRecommendations(
  summary: BackendSummary | string | null | undefined
): ParsedRecommendation[] {
  // Handle null/undefined
  if (!summary) return [];

  // Handle legacy string format (if backend ever sends markdown)
  if (typeof summary === 'string') {
    return parseMarkdownRecommendations(summary);
  }

  // Handle object format (current backend shape)
  if (typeof summary === 'object') {
    const obj = summary as BackendSummary;
    return [{
      type: 'Research',
      headline: `${obj.regime} Regime - ${obj.overall_position}`,
      detail: obj.key_themes?.join('; ') || '',
      conviction: obj.conviction || 'Medium',
      positionSize: 'Market Weight',
      supportingSignals: obj.key_themes || [],
      opposingSignals: [],
      riskToView: `Regime: ${obj.regime}`,
      dataToWatch: obj.key_themes || [],
      businessRelevance: obj.overall_position || '',
      suggestedAction: `Align portfolio with ${obj.regime} regime positioning`,
    }];
  }

  // Unknown format - return empty
  console.warn('[BusinessAdapter] Unknown recommendations format:', summary);
  return [];
}

/**
 * Parse markdown format recommendations (legacy support)
 */
function parseMarkdownRecommendations(markdown: string): ParsedRecommendation[] {
  if (!markdown.trim()) return [];

  const recommendations: ParsedRecommendation[] = [];
  const sections = markdown.split('## ').filter(s => s.trim());

  for (const section of sections) {
    const lines = section.split('\n').filter(l => l.trim());
    if (lines.length === 0) continue;

    const rec: ParsedRecommendation = {
      type: lines[0].replace(' View', '').trim(),
      headline: '',
      detail: '',
      conviction: '',
      positionSize: '',
      supportingSignals: [],
      opposingSignals: [],
      riskToView: '',
      dataToWatch: [],
      businessRelevance: '',
      suggestedAction: '',
    };

    for (const line of lines.slice(1)) {
      const trimmed = line.trim();
      if (trimmed.startsWith('**Headline:**')) rec.headline = trimmed.replace('**Headline:**', '').trim();
      else if (trimmed.startsWith('**Detail:**')) rec.detail = trimmed.replace('**Detail:**', '').trim();
      else if (trimmed.startsWith('**Conviction:**')) rec.conviction = trimmed.replace('**Conviction:**', '').trim();
      else if (trimmed.startsWith('**Position Size:**')) rec.positionSize = trimmed.replace('**Position Size:**', '').trim();
      else if (trimmed.startsWith('**Supporting Signals:**')) {
        const signals = trimmed.replace('**Supporting Signals:**', '').trim();
        rec.supportingSignals = signals.split(',').map(s => s.trim()).filter(s => s && s !== 'None');
      }
      else if (trimmed.startsWith('**Opposing Signals:**')) {
        const signals = trimmed.replace('**Opposing Signals:**', '').trim();
        rec.opposingSignals = signals.split(',').map(s => s.trim()).filter(s => s && s !== 'None');
      }
      else if (trimmed.startsWith('**Risk to View:**')) rec.riskToView = trimmed.replace('**Risk to View:**', '').trim();
      else if (trimmed.startsWith('**Data to Watch:**')) {
        const data = trimmed.replace('**Data to Watch:**', '').trim();
        rec.dataToWatch = data.split(',').map(s => s.trim()).filter(s => s);
      }
      else if (trimmed.startsWith('**Business Relevance:**')) rec.businessRelevance = trimmed.replace('**Business Relevance:**', '').trim();
      else if (trimmed.startsWith('**Suggested Action:**')) rec.suggestedAction = trimmed.replace('**Suggested Action:**', '').trim();
    }

    if (rec.headline) recommendations.push(rec);
  }

  return recommendations;
}

/**
 * Normalize expected returns from backend format to frontend format
 */
export function normalizeExpectedReturns(
  returns: BackendRecommendation[]
): FrontendExpectedReturn[] {
  if (!Array.isArray(returns)) return [];

  return returns.map(item => ({
    asset_class: item.asset,
    expected_return_score: item.return_1y,
    conviction: item.confidence,
    rationale: '',
    sharpe_estimate: undefined,
  }));
}

/**
 * Normalize position sizing from backend format to frontend format
 */
export function normalizePositionSizing(
  positions: BackendPositionSizing[]
): FrontendPositionSizing[] {
  if (!Array.isArray(positions)) return [];

  return positions.map(item => {
    // Parse range like "20-30%" into min/max weights
    const rangeMatch = item.range?.match(/(\d+)-(\d+)%/);
    const minWeight = rangeMatch ? parseInt(rangeMatch[1]) / 100 : undefined;
    const maxWeight = rangeMatch ? parseInt(rangeMatch[2]) / 100 : undefined;

    return {
      asset_class: item.asset,
      recommended_weight: item.target,
      min_weight: minWeight,
      max_weight: maxWeight,
      conviction: item.conviction,
      bucket: 'Neutral',
      rationale: '',
    };
  });
}
