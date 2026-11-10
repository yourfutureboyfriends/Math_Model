# Continuous provider supervision

The scheduler checks source eligibility every minute while the backend is running. Existing configured quote adapters refresh context every 15 minutes. Monthly market, FRED macro and news feature builders refresh every six hours; the broad macro panel refreshes daily. No new paid subscription or credential is created. `ML_ONLINE_ENABLED=0` disables the provider supervisor.

Each provider job runs with a timeout in a separate process. Accepted feature payloads must pass schema, finite-value, history, coverage and freshness checks. A rejected update preserves the last good cache and triggers bounded exponential backoff. Content-addressed compressed snapshots record payload identity and first-observed time. Archives have explicit capacity limits and do not silently delete history. They preserve observations going forward, not reconstructed historical release vintages.

Accepted feature changes can request inference using the saved preprocessing and model weights. Context quotes are not substituted into monthly training data. Research eligibility checks run every six hours: newly matured labels may permit daily full refitting, otherwise weekly limits remain. Labels that mature during a cooldown remain pending. Research candidates retain existing promotion gates. These are full refits, not a reproduction of DoubleAdapt or DDG-DA.

The ML overview displays source coverage, acceptance times and errors. The backend must remain running for scheduled work; local app shutdown stops it. Provider availability and configured entitlements still constrain coverage.

Verification: 12 provider/modular tests passed, including invalid-data rejection, archive replay, backoff, matured-label eligibility and cooldown persistence. A real market-feature refresh on 5 November 2026 accepted three series containing 3,028 monthly observations, all current to November 2026, and saved a compressed snapshot. This verifies ingestion mechanics, not forecasting accuracy.

See [paper-to-code review](continual_learning_paper_code_review_2026-11-05.md) for the evidence and the remaining evaluation requirements.
