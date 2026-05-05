# METHODOLOGY.md

## Macro Regime Model — Technical Documentation

This document provides precise formulas and worked examples for every step of
the macro regime model. It is designed for model validation, replication, and
educational purposes.

---

## Table of Contents

1. [Data Transformations](#1-data-transformations)
2. [Group Scoring](#2-group-scoring)
3. [Regime Classification](#3-regime-classification)
4. [Sector Scoring](#4-sector-scoring)
5. [Portfolio Construction](#5-portfolio-construction)
6. [Recession Model](#6-recession-model)
7. [Inflation Nowcast](#7-inflation-nowcast)
8. [Worked Example](#8-worked-example)

---

## 1. Data Transformations

### 1.1 Z-Score Computation

For each indicator $x_t$ at time $t$, the rolling z-score is:

$$z_t = \frac{x_t - \bar{x}_{t-36:t-1}}{\sigma_{t-36:t-1}}$$

Where:
- $\bar{x}_{t-36:t-1}$ = 36-month rolling mean (excluding current month)
- $\sigma_{t-36:t-1}$ = 36-month rolling standard deviation
- Minimum periods = 12 (z-score available after 12 months of data)

### 1.2 Sign Adjustment

For indicators where higher_is_positive=False (e.g., unemployment):

$$z_t^{adjusted} = -z_t$$

This ensures all indicators contribute consistently to their group's direction.

### 1.3 Direction Calculation

For any score $s_t$:

$$\Delta s = s_t - s_{t-3}$$

Direction classification:
- $\Delta s > +0.10$ → "improving" / "rising" / "loosening"
- $\Delta s < -0.10$ → "deteriorating" / "falling" / "tightening"
- Otherwise → "stable"

---

## 2. Group Scoring

### 2.1 Equal-Weight Group Score

For group $g$ with indicators $i \in I_g$:

$$S_g^{EW} = \frac{1}{|I_g|} \sum_{i \in I_g} z_{i,t}^{adjusted}$$

### 2.2 PCA-Based Group Score

1. Extract z-score matrix $Z_g$ for group $g$ (indicators × time)
2. Compute covariance matrix: $\Sigma = \frac{1}{n-1} Z_g^T Z_g$
3. Find eigenvectors: solve $\Sigma v = \lambda v$
4. First principal component scores: $S_g^{PCA} = Z_g v_1$
5. Normalize: $S_g^{PCA} = \frac{S_g^{PCA} - \mu(S_g^{PCA})}{\sigma(S_g^{PCA})}$

### 2.3 Composite Group Score

$$S_g^{composite} = (1-w) \cdot S_g^{EW} + w \cdot S_g^{PCA}$$

Where $w$ = PCA weight (default 0.3)

---

## 3. Regime Classification

### 3.1 Four-Quadrant Model

|  | Inflation ↑ | Inflation ↓ |
|--|-------------|-------------|
| **Growth ↑** | Reflation | Goldilocks |
| **Growth ↓** | Stagflation | Slowdown |

### 3.2 Classification Rules

```
if growth_direction == "improving":
    if inflation_direction in ["rising", "stable"]:
        regime = "Reflation"
    else:
        regime = "Goldilocks"
else:  # deteriorating or stable
    if inflation_direction == "rising":
        regime = "Stagflation"
    else:
        regime = "Slowdown"
```

### 3.3 Regime Confidence

$$\text{Confidence} = \min(1, \frac{|S_{growth}|}{0.5}) \times \min(1, \frac{|S_{inflation}|}{0.5})$$

Confidence ∈ [0,1], where 1 = strong signal, 0 = borderline

---

## 4. Sector Scoring

### 4.1 Raw Sector Score

For sector $j$ in regime $R$:

$$SS_j = w_R \cdot RW_j^R + w_L \cdot (L \cdot LW_j) + w_K \cdot (K \cdot KW_j) + w_G \cdot (G \cdot GW_j)$$

Where:
- $RW_j^R$ = regime weight for sector $j$ in regime $R$
- $L$ = liquidity score
- $K$ = risk score
- $G$ = growth score
- $LW_j, KW_j, GW_j$ = sector-specific weights
- Default: $w_R=1.0, w_L=0.3, w_K=0.2, w_G=0.2$

### 4.2 Signal Thresholds

| Score | Signal |
|-------|--------|
| $SS_j > +0.5$ | Overweight (OW) |
| $-0.5 \leq SS_j \leq +0.5$ | Neutral (N) |
| $SS_j < -0.5$ | Underweight (UW) |

---

## 5. Portfolio Construction

### 5.1 Base Weights

Equal-weight benchmark with 7 sectors:

$$w_j^{base} = \frac{1}{7} \approx 14.29\%$$

### 5.2 Tilt Application

$$w_j^{tilted} = w_j^{base} + \delta_j \cdot \tau$$

Where:
- $\delta_j$ = +1 for OW, 0 for N, -1 for UW
- $\tau$ = tilt magnitude (default 5% = 0.05)

### 5.3 Constraints

**Maximum constraint:**
$$w_j^{constrained} = \min(w_j^{tilted}, w^{max})$$

**Minimum constraint:**
$$w_j^{final} = \max(w_j^{constrained}, w^{min})$$

Default: $w^{max} = 25\%$, $w^{min} = 5\%$

### 5.4 Normalization

$$w_j = \frac{w_j^{final}}{\sum_k w_k^{final}}$$

---

## 6. Recession Model

### 6.1 Logistic Regression Specification

$$P(\text{recession}) = \frac{1}{1 + e^{-z}}$$

Where:
$$z = \beta_0 + \beta_1 \cdot YC + \beta_2 \cdot CS$$

- $YC$ = yield curve slope (10Y - 2Y) in percentage points
- $CS$ = high-yield credit spreads in basis points

### 6.2 Default Coefficients

| Parameter | Value | Interpretation |
|-----------|-------|----------------|
| $\beta_0$ | -2.5 | Base log-odds |
| $\beta_1$ | -0.8 | Inverted curve increases probability |
| $\beta_2$ | 0.006 | Wider spreads increase probability |

### 6.3 Example Calculation

Given:
- Yield curve = -0.5% (inverted)
- Credit spreads = 400 bps

$$z = -2.5 + (-0.8) \times (-0.5) + 0.006 \times 400 = -2.5 + 0.4 + 2.4 = 0.3$$

$$P = \frac{1}{1 + e^{-0.3}} = \frac{1}{1 + 0.741} = 57\%$$

---

## 7. Inflation Nowcast

### 7.1 Bridge Equation

$$\Delta CPI_t = \alpha + \beta_1 \cdot \Delta PPI_{t-1} + \beta_2 \cdot \Delta Oil_{t-1} + \beta_3 \cdot \Delta CPI_{t-1} + \epsilon_t$$

### 7.2 Default Coefficients

| Parameter | Value |
|-----------|-------|
| $\alpha$ | 0.10 |
| $\beta_1$ (PPI) | 0.15 |
| $\beta_2$ (Oil) | 0.02 |
| $\beta_3$ (Momentum) | 0.50 |

### 7.3 Confidence Interval

$$CI = \hat{y} \pm 0.25$$

Based on historical RMSE of ~0.25 percentage points.

---

## 8. Worked Example

### Example Data (Hypothetical)

**Input indicators (December 2024):**
- PMI = 52.0 (z-score: +0.5)
- Unemployment = 3.8% (z-score: -0.3 → +0.3 after sign flip)
- CPI YoY = 3.2% (z-score: +1.2)
- Fed Funds = 5.5% (z-score: -0.8)
- Yield curve = -0.3% (inverted)

**3 months prior (September 2024):**
- PMI = 50.5 (z-score: +0.2)
- CPI YoY = 3.5% (z-score: +1.4)

### Step-by-Step Calculation

**Step 1: Compute group scores**

Growth score (equal-weight):
$$S_{growth} = \frac{0.5 + 0.3}{2} = 0.4$$

Inflation score:
$$S_{inflation} = 1.2$$ (single indicator shown)

Liquidity score:
$$S_{liquidity} = -0.8$$ (single indicator shown)

**Step 2: Determine directions**

Growth direction: $0.4 - 0.2 = +0.2 > 0.10$ → "improving"
Inflation direction: $1.2 - 1.4 = -0.2 < -0.10$ → "falling"

**Step 3: Classify regime**

Growth ↑ + Inflation ↓ = **Goldilocks**

**Step 4: Compute sector scores**

For Technology in Goldilocks:
$$SS_{tech} = 0.7 + 0.3 \times (-0.8) + 0.2 \times 0.4 = 0.7 - 0.24 + 0.08 = 0.54$$

**Step 5: Assign signals**

$SS_{tech} = 0.54 > 0.5$ → **Overweight**

**Step 6: Construct portfolio**

Base weight: 14.29%
Tilt: +5% for OW
Pre-constraint: 19.29%
Within bounds (5% min, 25% max) ✓

Final weight: 19.29% (rescaled if needed)

**Step 7: Recession probability**

$$z = -2.5 + (-0.8) \times (-0.3) + 0.006 \times 300 = -2.5 + 0.24 + 1.8 = -0.46$$

$$P = \frac{1}{1 + e^{0.46}} = \frac{1}{1.584} = 39\%$$

**Interpretation:**
- Goldilocks regime supports risk assets
- Moderate recession risk (39%) warrants caution
- OW Technology reflects favorable growth/liquidity conditions
- Yield curve inversion tempers enthusiasm

---

## Data Revisions

### Vintages and Real-Time Data

The model uses "vintages" — data as it was known at the time. Important
revisions to monitor:

1. **GDP revisions**: Annual updates can change growth signals
2. **CPI seasonal factors**: Re-estimated annually
3. **Unemployment benchmark**: Population adjustments every January

### Backward Compatibility

When comparing historical model outputs:
- Note the data vintage used
- Report revision dates when known
- Use real-time data for true backtests

---

## References

See `learning_notes.md` for complete reading list and paper annotations.

---

*Document version: 1.0*
*Last updated: 2026-04-26*