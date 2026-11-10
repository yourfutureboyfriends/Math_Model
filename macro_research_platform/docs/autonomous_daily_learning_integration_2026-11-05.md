# Autonomous daily learning integration — 5 November 2026

## Application wiring

The existing API scheduler checks every ten minutes for an XNYS trading session that closed 20–80 minutes earlier. Exchange holidays and early closes use exchange-calendars. The backend must remain running. Set `ML_AUTONOMOUS_ENABLED=0` to disable this worker. Manual runs retain actual receipt/inference times and do not consume the scheduled daily run identity.

The API process launches an isolated Python worker; it never imports Torch through the supervisor. A cross-process lock prevents overlapping manual, scheduled and command-line work. The worker has bounded training time, extraction/document budgets, timeout and durable state. API restarts retain stored models and evidence.

ML → Overview contains the live learning status, provider, source month, training progress, learning mode, research forecast matrix, cited events and last deployment decision. Authorized PM/quant/admin users can request a cycle. Read and run endpoints are `/api/v1/ml/autonomous/status` and `/api/v1/ml/autonomous/run`.

## Data and model behavior

- Uses existing market/FRED feature adapters and the app's configured AI provider. Initial live verification used Groq `openai/gpt-oss-120b`. Public Fed press, speeches and data-announcement feeds are configured; licensed news access is not supplied.
- Supports RSS 2, RDF/RSS 1 and Atom. Legacy HTTP links on an explicitly allowed official host are requested over HTTPS; arbitrary hosts and unsafe redirects remain rejected.
- Events require structured validation, exact source evidence, source/prompt/extractor hashes and actual post-extraction availability times. Empty event batches are valid. LLM sentiment/confidence are uncalibrated attributes, not forecast labels.
- The graph persists deduplicated events and bounded snapshots. Evidence/co-occurrence weights decay; rolling correlations require enough complete source-observation days. These links do not claim economic causation.
- The new TFT/GAT produces 24 explicit task/horizon cells. Existing six native task horizons are the only deployment scope. Feature group order is stable across saved JSON round trips.
- Historical foundation inputs are currently revised research history. New operational observations, graph snapshots, labels, forecasts and simulated daily returns are frozen as they become known. Historical seed results never count as retroactive prospective evidence.
- New matured outcomes trigger replay/EWC supervised updates. In their absence, newly observed data may train the shadow encoder with masked-feature reconstruction. Forecast heads remain fixed, graph value channels are hidden during reconstruction, and forecast labels are never manufactured.
- Calibration is fitted separately for each checkpoint/cell on a held-out foundation cohort. Insufficient classes produce a raw research output. This reference calibration is not a prospective accuracy result.

## Deployment behavior

The initial registry reference represents actual captured incumbent forecasts; it is not an assertion that TFT has already passed deployment checks. The worker records challenger and incumbent outputs before their outcomes are known. Promotion requires paired prospective evidence, class/sample adequacy, improvement over the reference prior and incumbent, and dependent-block statistical checks. A 30-day diagnostic or 2% Brier point improvement alone cannot promote monthly macro models. Long-horizon and recession evidence can take substantial time to mature.

Only fresh, calibrated forecasts matching the active registry pointer may be served. The currently promoted model is refreshed independently when a new shadow candidate fails. Missing/stale artifacts or failed data checks retain the existing forecast path. No brokerage transaction is performed.

## Verification

Backend coverage includes calendar holidays/early closes, 24 distinct targets and conservative maturation, stable serialized feature routing, registry/calibration serving guards, API import isolation, official feed parsing and HTTPS link upgrading, plus the institutional model/pipeline suites. Frontend coverage includes the status panel and existing research visualizer; TypeScript checking and production build were also run. Live execution and its actual gate outcome are recorded under `data/processed/ml_autonomous/`.

Local immutable files, SQLite ledgers and hashes provide auditability; they are not regulatory WORM storage or high-availability distributed orchestration. Provider outputs and revised upstream histories cannot be reconstructed from vendor model weights that the application does not possess.
