# Methodology — Phase 7: Alternative-Data Positioning

_For a PM to read before trusting the numbers._

## What it does
Surfaces positioning/stress signals that often move *before* price, from real data
(yfinance/FRED): the VIX term structure, cross-market correlation breakdowns, and credit
spread stress.

## 1. VIX term structure
Latest VIX9D, VIX (spot), VIX3M, VIX6M. **slope = VIX3M / VIX − 1**:
- **Contango** (slope > +2%, longer-dated vol higher) → calm, complacent.
- **Backwardation** (slope < −2%, spot elevated) → acute near-term stress (buyers of
  short-dated protection).
This is the shape of the volatility curve — a cleaner options-positioning tell than spot VIX alone.

## 2. Cross-market correlation breakdown
For SPY vs Duration (TLT), USD (DXY), Gold (GLD), HY Credit (HYG): the trailing 63-day
correlation is compared to **its own history**. A **breakdown** is flagged when the
current correlation is > 2σ from its historical mean. A normally-negative pair turning
positive (e.g. stocks and bonds falling together) is a classic early regime-change tell.

## 3. Credit-spread stress
ICE BofA OAS from FRED: HY (BAMLH0A0HYM2), IG (BAMLC0A0CM), the HY−IG spread, and the
**z-score / percentile of HY OAS vs its trailing ~1y**. Signal:
- **stress** (z > +1): spreads unusually wide — credit deteriorating.
- **complacent** (z < −1): spreads unusually tight — little cushion for a shock.
Credit often leads equity regime shifts, so tight-and-complacent is a risk flag even when
equities are calm.

## Assumptions & limitations
- **Correlation z-scores use a ~1y window** — a persistent regime shift will eventually
  re-baseline as "normal"; the alert catches the *transition*, not the new steady state.
- **VIX term uses index proxies** (VIX9D/3M/6M), not the full VX futures curve, so it
  captures the shape but not roll yield precisely.
- **Not built (scoped):** full CFTC COT net-positioning z-scores across all futures,
  CDX/iTraxx (not freely available), leveraged-loan issuance and HY fund flows, and
  merging speaker/earnings calendars into one event view — these need paid/again-specific
  data sources beyond yfinance/FRED and are intentionally omitted rather than faked.

## Verification
9 known-answer unit tests (`test_altdata.py`): z-score at the mean is 0; contango vs
backwardation classification; perfect/anti correlation = ±1; a correlation that flips
sign is flagged as a breakdown while a stable one is not. Verified live: VIX in contango
(spot 16.9 < 3M 19.5); SPY-Gold correlation flagged at z=2.2σ; HY-IG 191bps at the ~3rd
percentile → "complacent". 179 backend tests pass.
