# Learning Notes — Macro Regime Investing

This file is your self-study companion for the model.  It explains the conceptual
foundations so you understand not just what the model does, but why macro investors
think this way.

---

## 1. What are macro regime models?

A **macro regime model** classifies the current economic environment into a small
number of distinct "states" so you can make better decisions about sector and
asset allocation.

The idea comes from the observation that different assets behave differently
depending on the macro backdrop.  Banks are not hurt by rising rates in the same
way technology companies are.  Utilities are not hurt by recession the way
industrials are.

Rather than trying to predict the exact level of GDP or inflation, regime models
ask a simpler question: **which direction are the key macro forces moving?**

**Why is this useful?**
- It simplifies complexity (20+ indicators → 4 categories → 1 regime).
- It provides a shared language for investment committee discussion.
- It gives structure to what might otherwise be ad hoc macroeconomic storytelling.

**What it is NOT:**
- A prediction machine.
- A mechanical trading strategy (without backtesting and risk management).
- A replacement for fundamental analysis of individual securities.

---

## 2. Why are growth and inflation the two main axes?

Almost every major macro framework uses growth and inflation as the primary
dimensions.  Why?

**Growth** determines whether corporate earnings are expanding or contracting.
It drives revenue, employment, and confidence.  Rising growth = earnings revisions
up = equity multiples supported.

**Inflation** determines what central banks do.  High inflation → rate hikes →
higher discount rates → lower present value of future earnings → equity multiples
compress.  Low inflation → rate cuts → loose conditions → valuation expansion.

Together, these two forces capture most of the variation in asset returns across
macro environments.  The cross (rising/falling growth) × (rising/falling inflation)
creates four distinct regimes with meaningfully different return distributions.

**A useful mental model:** think of growth as the "fuel" for the economy and
inflation as the "temperature."  Too cold (deflation) = stagnation.  Too hot
(hyperinflation) = monetary chaos.  The sweet spot is warm: 2-3% inflation with
2-4% real growth.

---

## 3. Why does liquidity matter for asset prices?

**Liquidity** refers to how easy and cheap it is to borrow money and take risk.
It matters because:

1. **Discount rates:** Asset prices are the present value of future cash flows.
   Lower interest rates = lower discount rate = higher present value.  When the
   Fed cuts rates, every asset that generates future cash flows becomes more
   valuable, all else equal.

2. **Credit availability:** Cheap credit enables businesses to invest, hire, and
   expand.  Tight credit (wide spreads, restrictive bank lending) is a drag on
   economic activity.

3. **Risk appetite:** When liquidity is ample, investors feel safe taking more
   risk.  Capital flows from safe assets (government bonds) into risky assets
   (equities, high yield, emerging markets).

**The key insight:** liquidity can temporarily "override" fundamentals.  A weak
economy with extremely loose monetary policy can see asset prices rise, because the
discount rate effect dominates.  This is why "bad news is good news" — weak
economic data can signal more rate cuts, which boosts asset prices.

---

## 4. Why are credit spreads and yield curves important?

### Yield curves

The **yield curve** is the difference between long-term and short-term government
bond yields (typically 10Y minus 2Y).

A **normal (positive) curve** means long-term rates > short-term rates.  This
is healthy: investors earn more for taking long-term risk, and banks profit from
borrowing short and lending long (the basis of banking).

An **inverted (negative) curve** means short-term rates > long-term rates.  This
happens when central banks have hiked short rates aggressively while long-run growth
and inflation expectations remain subdued.  An inverted curve:
- Squeezes bank margins (borrowing cost rises, lending rate falls).
- Signals that markets expect future rate cuts (i.e., recession + easing).
- Has preceded every US recession since 1970, with a 12-18 month lag.

### Credit spreads

**Credit spreads** measure the extra yield investors demand for corporate bonds
over government bonds.  They compensate for default risk.

Tight spreads = investors confident companies will repay debt → risk-on.
Wide spreads = investors worried about defaults → risk-off.

**Why are they one of the best leading indicators?**
Credit markets are usually smarter and faster than equity markets.  Spreads often
widen before equities fall, because leveraged companies are most vulnerable to
macro deterioration.  "Watch credit, trade equities" is a common maxim.

---

## 5. Why is momentum used as confirmation, not the whole model?

**Price momentum** (an asset trending up or down) is a robust anomaly: assets that
have performed well over the past 12 months tend to continue performing well over
the next 1-3 months (Moskowitz, Ooi & Pedersen, 2012).

However, using momentum alone as a macro model is problematic:
1. **It is backward-looking:** momentum reflects what already happened.
2. **It can persist through regime changes:** trend-following misses inflection points.
3. **Crowded momentum trades unwind sharply:** when everyone is long momentum,
   small shocks cause large reversals.

In this model, equity momentum (12-month equity return) is one signal inside the
**risk group**, not a standalone regime classifier.  It confirms whether current
market sentiment is consistent with the macro regime — a useful sanity check.

**The right way to think about momentum:** it adds CONFIDENCE to a macro view, not
the view itself.  If the model says Goldilocks and equities are trending up, that
is more conviction than Goldilocks with equities trending down.

---

## 6. Why bad economic data does not always mean stocks go down

This is one of the most confusing things about macro investing.

**The key principle:** Asset prices reflect EXPECTATIONS, not current reality.

If everyone already expects GDP to fall 2%, and it actually falls 1.5%, that is a
POSITIVE SURPRISE.  Equities can rally on "bad" absolute data if the data beat
a pessimistic consensus.

**The "priced in" concept:**
- When bad news is "fully priced in," there is no more selling pressure — buyers
  emerge at cheap valuations.
- When good news is "fully priced in," even better-than-expected data causes
  "sell the news" reactions.

**Central bank expectations matter enormously:**
- Weak jobs data → market expects Fed to cut rates → lower discount rates → equities
  rally even though employment just weakened.
- This is the paradox of "bad news is good news" in a hiking cycle.

**Implication for this model:**
The model scores ACTUAL data, not market expectations or surprises.  This means it
will sometimes point one way while markets move the other way.  Adding a "surprise
index" (actual vs consensus estimate) would help — see Future Improvements.

---

## 7. How to improve this model: research directions

### Signal improvements
- Replace simple averages with PCA (Principal Component Analysis) to extract the
  dominant factor from each group.
- Add country-level data to build a global version.
- Add earnings revision momentum (analyst upgrades vs downgrades).
- Add positioning data (CFTC futures positioning, fund flows).

### Regime improvements
- Use Hidden Markov Models (Hamilton, 1989) to probabilistically assign regime
  membership rather than hard classification.
- Add recession probability model using yield curve + credit spreads as inputs.
- Add inflation regime sub-classification (demand-pull vs cost-push).

### Portfolio improvements
- Backtest sector allocation signals to validate that the regime → sector mapping
  actually worked historically.
- Add valuation filters: only overweight a sector if the regime is positive AND it
  is not expensive vs history.
- Add risk management: volatility targeting, position limits, drawdown controls.

---

## 8. Reading list

### Books

#### Olivier Blanchard — *Macroeconomics* (any recent edition)
**What it teaches:** The canonical graduate-level macroeconomics textbook.
Covers the IS-LM model, aggregate demand/supply, monetary policy, and open-economy
macro in a rigorous but accessible way.
**How it improves the model:** Gives you the theoretical foundations for why growth
and inflation interact the way they do, and why central bank policy matters.
**Variable it adds:** Understanding of the output gap — the difference between actual
and potential GDP — which is a key variable for inflation forecasting.

---

#### Frederic Mishkin — *The Economics of Money, Banking and Financial Markets*
**What it teaches:** How banks work, how the money supply is created, how monetary
policy transmission works from the central bank to the real economy.
**How it improves the model:** Helps you understand why credit spreads and the yield
curve matter, and how to interpret central bank communications.
**Variable it adds:** Monetary policy transmission lags — understanding that rate
hikes take 12-18 months to fully feed through to the economy.

---

#### Antti Ilmanen — *Expected Returns* (2011, Wiley)
**What it teaches:** A comprehensive framework for thinking about long-run expected
returns across asset classes.  Covers the role of macro factors, risk premia,
valuation, and behavioural factors.
**How it improves the model:** The chapter on business cycle investing directly
maps to what this model does.  Ilmanen provides empirical evidence for which asset
classes outperform in each regime.
**Variable it adds:** Valuation-adjusted expected returns — not just "regime is X"
but "regime is X and sector is cheap/expensive, so expected return is Y."

---

#### Ruey Tsay — *Analysis of Financial Time Series* (3rd ed)
**What it teaches:** Statistical methods for financial time series: ARIMA, GARCH,
VAR models, state-space models.  Rigorous but accessible with R examples.
**How it improves the model:** If you want to move beyond simple z-scores and build
a proper econometric regime model (Markov-switching, dynamic factor models), this is
the technical foundation.
**Variable it adds:** Time-varying volatility estimation (GARCH) — useful for
building a volatility-targeting risk management layer.

---

#### Hyndman & Athanasopoulos — *Forecasting: Principles and Practice* (free online)
**What it teaches:** Practical forecasting methods: ETS, ARIMA, dynamic regression,
neural networks.  Very applied, with R/Python code.
**How it improves the model:** Lets you move from "scoring current data" to
"forecasting what data will look like in 3 months" — turning the model from
contemporaneous to leading.
**Variable it adds:** PMI nowcast, inflation forecast — predict the regime 1-2
quarters ahead rather than just classifying the current environment.

---

### Research Papers

#### Chen, Roll & Ross (1986) — *Economic Forces and the Stock Market*
**Journal of Business, 59(3)**
**What it teaches:** The foundational paper showing that macro variables (inflation,
industrial production, yield spreads, term structure) explain a significant portion
of cross-sectional stock returns.
**How it improves the model:** Validates the approach of using macro factor z-scores
to explain asset returns.  Provides a rigorous empirical basis for our indicator
selection.
**Variable it adds:** Term spread and default spread as explicit risk factors — this
paper showed yield curve and credit spreads matter before it became conventional
wisdom.

---

#### Fama & French (1989) — *Business Conditions and Expected Returns on Stocks and Bonds*
**Journal of Financial Economics, 25(1)**
**What it teaches:** Predictability in stock and bond returns over the business
cycle.  Expected returns are higher when business conditions are poor (recession)
and lower when conditions are good — the risk premium varies with the cycle.
**How it improves the model:** Suggests adding a valuation overlay: in Slowdown
regimes (high risk premia), expected returns for equities are actually HIGHER than
in Goldilocks (low risk premia) — even though the current environment is weaker.
**Variable it adds:** Dividend yield and credit spread as expected return predictors.

---

#### Hamilton (1989) — *A New Approach to the Economic Analysis of Nonstationary Time Series*
**Econometrica, 57(2)**
**What it teaches:** The Markov-switching model — a statistical technique for
identifying hidden regime switches in economic time series.  Shows that US GDP
growth can be decomposed into "expansion" and "recession" regimes.
**How it improves the model:** Provides the rigorous statistical foundation for
probabilistic regime classification.  Instead of hard rules (growth improving =
regime A), you get probabilities (75% probability we are in Goldilocks).
**Variable it adds:** Regime transition probabilities — and early warning when the
model probability is shifting (e.g. Goldilocks probability falling from 80% to 55%).

---

#### Moskowitz, Ooi & Pedersen (2012) — *Time Series Momentum*
**Journal of Financial Economics, 104(2)**
**What it teaches:** Documents robust time-series momentum across equity indices,
currencies, commodities, and bonds.  Holding assets with positive 12-month trailing
returns and shorting negative ones generates strong Sharpe ratios.
**How it improves the model:** Provides the evidence base for using equity momentum
as a confirmation signal.  Also suggests adding commodity momentum to the inflation
and energy sector signals.
**Variable it adds:** Cross-asset momentum scores — using bond, commodity, and FX
momentum alongside equity momentum for a richer risk assessment.

---

#### Campbell & Shiller (1991) — *Yield Spreads and Interest Rate Movements: A Bird's Eye View*
**Review of Economic Studies, 58(3)**
**What it teaches:** The term structure of interest rates contains information about
future short-term rates and economic activity.  Yield spreads forecast long-run
real activity.
**How it improves the model:** Provides the empirical and theoretical basis for
the yield curve indicator.  Shows that the yield curve slope has historically been
one of the best recession predictors.
**Variable it adds:** Yield curve as a formal recession probability input —
converting the raw yield curve number into a historical recession probability.

---

#### Cochrane & Piazzesi (2005) — *Bond Risk Premia*
**American Economic Review, 95(1)**
**What it teaches:** A single "tent-shaped" combination of forward rates predicts
excess bond returns with an R² of 44% — much higher than standard yield curve
models.  Bond risk premia are time-varying.
**How it improves the model:** Suggests that not just the slope of the yield curve
but the entire shape matters.  Time-varying bond risk premia affect the relative
attractiveness of bonds vs equities — important for the liquidity score calibration.
**Variable it adds:** Forward rate factor — a more sophisticated yield curve signal
that captures more information than the simple 10Y-2Y spread.

---

## 9. PCA in macro factor models

**What is PCA?**
Principal Component Analysis (PCA) is a dimensionality reduction technique that
finds the directions of maximum variance in high-dimensional data. In macro
factor models, it extracts the "common factor" that drives multiple correlated
indicators.

**Why use PCA for macro scoring?**
1. **Noise reduction**: Equal-weight averages can be dominated by volatile
   individual indicators. PCA extracts the signal common to all indicators.
2. **Correlation handling**: When PMI and industrial production are both
   improving, PCA recognizes they reflect the same underlying growth factor.
3. **Dynamic weighting**: Indicators that consistently move together get
   higher effective weight — they're measuring the same thing.

**Limitations:**
- PCA is sensitive to outliers and regime changes
- First component explains ~60-70% of variance in macro indicators
- Remaining components may contain useful but orthogonal information
- Interpretability: "what does PC1 represent?" requires domain expertise

**When to use PCA vs equal-weighting:**
- Use PCA when you have many correlated indicators (10+)
- Use equal-weighting when indicators are independent or you want
  interpretability over optimization
- Hybrid approach (composite score) combines both benefits

---

## 10. Recession probability models

**The yield curve as a recession predictor:**
An inverted yield curve (10Y < 2Y) has preceded every US recession since 1970
with a lead time of 12-18 months. The mechanism is simple:
- Banks borrow short and lend long
- Inverted curve means lending is unprofitable
- Banks tighten credit → investment falls → recession

**Why add credit spreads?**
The yield curve alone has false positives (e.g., 1998). Adding HY credit spreads
improves specificity because:
- Spreads reflect actual default risk pricing
- Wide spreads = "credit crunch" conditions
- Spreads often lead the yield curve inversion

**Logistic regression approach:**
Our model uses logit: P(recession) = 1 / (1 + exp(-z))
where z = β₀ + β₁×(yield curve) + β₂×(credit spreads)

This yields a probability bounded between 0 and 100%.

**Calibration considerations:**
- Rare events (recessions) require careful handling
- Class imbalance: only ~15% of months are in recession
- Model should be recalibrated quarterly with new NBER dates

---

## 11. Nowcasting: dynamic factor models and bridge equations

**What is nowcasting?**
Nowcasting = "now forecasting" — predicting the present before official data
is released. CPI is published mid-month for the prior month. A nowcast
predicts it using leading indicators available sooner.

**Bridge equations:**
Simple regressions that "bridge" leading indicators to the target:
CPI(t) = α + β₁×PPI(t-1) + β₂×Oil(t-1) + β₃×CPI(t-1) + ε

**Dynamic factor models (advanced):**
Extract common factors from hundreds of high-frequency series (daily shipping,
credit card spending, job postings) to predict GDP/inflation. These are
used by central banks (Federal Reserve, ECB) for real-time assessment.

**Accuracy expectations:**
- RMSE typically 0.2-0.3 percentage points for CPI
- Nowcast beats naive "unchanged" forecast 60-70% of the time
- Model breaks during structural shifts (pandemic, new price regimes)

---

## 12. Backtesting pitfalls

**Lookahead bias:**
Using data not available at the time of the decision. Example: computing a
z-score using the full sample mean when only historical data was known.

**Survivorship bias:**
Testing only on companies/sectors that still exist. Defunct sectors disappear
from historical data, inflating performance.

**Data snooping / overfitting:**
Testing many strategies and reporting only the best. With enough combinations,
some will look good by chance.

**Transaction costs:**
Real-world returns = gross returns - slippage - commissions - market impact.
High-turnover strategies look better before costs.

**Regime changes:**
Relationships that held historically may break. 1970s inflation model wouldn't
work in 1990s Great Moderation.

**Best practices:**
1. Walk-forward analysis: retrain model at each point with only prior data
2. Out-of-sample testing: validate on data not used for development
3. Multiple regimes: test across different macro environments
4. Realistic costs: assume 10-20bps per trade minimum

---

## 13. Additional Research Papers

#### Estrella & Mishkin (1998) — *Predicting U.S. Recessions: A Dynamic Probit Approach*
**Review of Economics and Statistics, 81(1)**
**What it teaches:** Formal econometric framework for recession prediction using
the yield curve and other financial variables. Shows yield curve outperforms
other leading indicators.
**How it improves the model:** Provides the methodology for our recession
probability model — logistic regression on yield curve + credit spreads.
**Variable it adds:** Formal recession probability score (0-100%) as a gauge
on the dashboard.

---

#### Stock & Watson (2002) — *Forecasting Output and Inflation: The Role of Asset Prices*
**Journal of Economic Literature, 40(3)**
**What it teaches:** Diffusion indexes — tracking how many indicators are
improving vs deteriorating — provide robust business cycle signals.
**How it improves the model:** Validates our diffusion index approach for
each macro group (what % of growth indicators are positive?).
**Variable it adds:** Diffusion indices for growth, inflation, liquidity,
and risk as alternative scoring methods.

---

#### Ang & Bekaert (2002) — *Regime Switches in Interest Rates*
**Journal of Business and Economic Statistics, 20(2)**
**What it teaches:** How to identify and model regime switches in interest
rates using Hamilton-style Markov-switching models. Rates behave differently
in "high volatility" vs "low volatility" regimes.
**How it improves the model:** Provides theoretical foundation for
probabilistic regime classification. Instead of "we are in Goldilocks,"
the model can say "65% Goldilocks, 25% Reflation, 10% other."
**Variable it adds:** Regime probabilities and transition matrices that
quantify the likelihood of moving from one regime to another.

---

## Future improvements

See `README.md` for the full future improvements roadmap.

---

*This document was generated as part of the macro_model project for educational purposes.
Update it as you learn more and as the model evolves.*
