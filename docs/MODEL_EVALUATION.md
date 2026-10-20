# NewsPulse Model Methodology & Evaluation

## 1. Prediction Target and Formula

The forecasting target is the next regular trading session's close-to-close percentage change ($y_{i, t+1}$):

$$y_{i, t+1} = 100 \times \frac{P_{i, t+1} - P_{i, t}}{P_{i, t}}$$

Where:
- $P_{i, t}$ is the reference close of asset $i$ at the cutoff of regular trading session $t$.
- $P_{i, t+1}$ is the close of the next regular trading session $t+1$ (not the next calendar day).

## 2. Outlook Classification Threshold ($\theta$)

Estimated changes are categorized into informational market outlook labels:
- **Bullish**: $\text{Estimate} > +\theta$
- **Bearish**: $\text{Estimate} < -\theta$
- **Neutral**: $-\theta \le \text{Estimate} \le +\theta$

The default threshold is $\theta = 0.25\text{ percentage points}$ (configurable via `NEWSPULSE_THRESHOLD_PP`).

---

## 3. Evaluated Models

1. **Price-Only Baseline**:
   - Features: $ret_{1d}$, $ret_{5d}$, $ret_{10d}$, $vol_{10d}$, $index\_ret_{1d}$, $index\_ret_{5d}$, $is\_index$.
   - Algorithm: Ridge regression with standardized inputs.
2. **News-Aware Model**:
   - Features: Price-only features $+$ news features ($\log(1 + count)$, mean sentiment, positive count, negative count, recency-weighted sentiment, $has\_news$ indicator).
   - Algorithm: Comparable Ridge regression with identical preprocessing and tuning.

---

## 4. Chronological Splitting Protocol

To prevent time-series look-ahead and target leakage:
- Rows are sorted chronologically by reference session.
- **Train period**: Earliest 60% of sessions.
- **Validation period**: Middle 20% of sessions (used strictly for tuning regularization hyperparameter $\alpha$).
- **Held-out Test period**: Final 20% of sessions (frozen until final evaluation).
- Baseline and News-Aware models are evaluated on the exact same held-out test rows.

---

## 5. Measured Evaluation Results

### A. Live Market Data Evaluation (NSE Real Market Data)
- **Database Partition**: `data/newspulse_live.db`
- **Universe**: NIFTY 50 (`^NSEI`) + 8 NSE Equities
- **Test Period**: 2026-10-12 to 2026-10-19 (Held-out 20% chronological split)
- **Evaluated Test Sample Count**: 54 observations evaluated on identical held-out test rows

| Model Architecture | MAE (percentage points) ↓ | Directional Accuracy (%) ↑ | Evaluated Samples |
| :--- | :--- | :--- | :--- |
| **Price-Only Baseline** (`BASELINE_PRICE_RIDGE`) | 1.85 pp | 53.7 % | 54 |
| **News-Aware Model** (`NEWS_AWARE_RIDGE`) | 1.83 pp | 55.6 % | 54 |

**Observed Empirical Findings**:
- The news-aware Ridge model reduced MAE from 1.85 pp to 1.83 pp (-0.02 pp).
- Directional accuracy improved from 53.7% to 55.6% (+1.9 pp) on the held-out test set.
- All metrics are calculated without data leakage, using strictly pre-cutoff headlines and features.

---

### B. Offline Benchmark Evaluation (Deterministic Sample Dataset)
- **Database Partition**: `data/newspulse_sample.db`
- **Universe**: Demo Market 100 (`DM100`) + 8 Fictional Equities
- **Test Period**: 2026-06-29 to 2026-10-16 (Held-out 20% chronological split)
- **Evaluated Test Sample Count**: 720 observations

| Model Architecture | MAE (percentage points) ↓ | Directional Accuracy (%) ↑ | Evaluated Samples |
| :--- | :--- | :--- | :--- |
| **Price-Only Baseline** | 1.2942 pp | 48.9 % | 720 |
| **News-Aware Model** | 1.2953 pp | 49.7 % | 720 |

---

## 6. Academic Research Integrity & Disclaimers

1. **Leakage Prevention**: All features are computed with causal time windows ($T \le \text{cutoff}$). Headlines lacking verified publication timestamps are excluded from feature construction.
2. **Correlation vs Causation**: Association between headline sentiment and market movement does not establish economic causation.
3. **Informational Prototype**: These models are built for empirical research and educational analysis. They do not constitute investment advice or trading recommendations.
