# Phase 5: Portfolio Valuation, Realized & Unrealized Gains, XIRR, and Value Series

## 1. Overview & Core Philosophy

Phase 5 introduces pure compute-on-read valuation, capital gains tracking, XIRR performance metrics, and historical value-over-time series for FolioPilot.

- **No New Tables**: Valuation and performance metrics are computed strictly on read from the append-only transaction ledger and the mutual fund master records.
- **Single Source of Truth**: All HTTP endpoints, asynchronous tasks, and future AI agent tools invoke the identical pure functions located in `app.services.valuation`, `app.services.xirr`, and `app.services.value_series`.
- **Decimal Precision**: All monetary calculations, units, and gain percentages operate in Python `Decimal` context with 28 digits of precision and `ROUND_HALF_UP` quantization.
- **Sums of Rounded Values**: Portfolio-level and summary-level totals are strictly computed as sums of the rounded per-position values, preventing rounding discrepancies between parent totals and child rows.

---

## 2. Price Rule & Staleness Guarantees

Current position value is derived according to deterministic pricing rules:

1. **AMFI Latest Price (`nav_source: "amfi_latest"`)**:
   - Uses `funds.latest_nav` recorded at `funds.latest_nav_date`.
   - `nav_age_days = (today_IST - latest_nav_date)` measured in calendar days using the injectable system clock.
   - Flag `is_stale = nav_age_days > NAV_STALE_DAYS` (where `NAV_STALE_DAYS = 7`).
   - If `latest_nav_date < position.last_txn_date`, the flag `nav_older_than_ledger = True` is raised, and `max(latest_nav_date, last_txn_date)` serves as the position's terminal valuation date for XIRR.

2. **Cost Basis Fallback (`nav_source: "fallback_cost"`)**:
   - If a mutual fund has no live `latest_nav` (e.g. newly tracked fund awaiting historical AMFI synchronization), the position uses its own weighted average cost basis (`avg_cost`) as the price.
   - Positions using `fallback_cost` are flagged and excluded from portfolio-level and overall XIRR calculations, with their count recorded in `totals.xirr.excluded_funds`.

---

## 3. Position Valuation & Realized Capital Gains

### Per-Position Formulas
- **Current Value**: `units * nav` quantized to `0.01` (`ROUND_HALF_UP`).
- **Cost Basis**: Weighted average cost of remaining units, derived during the chronological ledger sweep.
- **Unrealized Gain**: `current_value - cost_basis` quantized to `0.01`.
- **Unrealized Gain Percent**: `(unrealized_gain / cost_basis) * 100` quantized to `0.01`, or `None` if `cost_basis == 0`.
- **Realized Gain**: Accumulated across sell transactions using the average cost method:
  $$\text{realized} += \text{proceeds} - (\text{avg\_cost\_before} \times \text{units\_sold})$$
  computed at full precision and quantized once per sell to `0.01`. Fully closed positions preserve their realized gain total.
- **Total Gain**: `unrealized_gain + realized_gain`.

> [!IMPORTANT]
> **Realized Gain is NOT a Tax Figure**: Realized gain calculated here utilizes the weighted average cost method across transactions. Indian income tax law enforces FIFO tax-lot matching with grandfathering and indexation rules, which will be implemented in Phase 13 (Tax Lots & Capital Gains).

---

## 4. XIRR Cash Flows & Mathematical Solver

### Cash Flow Conventions
- **Buy / Purchases**: Outflow (negative amount, `-amount`).
- **Sell / Redemptions**: Inflow (positive amount, `+amount`).
- **Dividend Reinvestment (`dividend_reinvest`)**: **Not a cash flow** (`DIVIDEND_REINVEST_IS_CASH_FLOW = False`). Units enter the portfolio without investor cash leaving; their value is captured terminal inflow.
- **Terminal Value**: Each open position adds a terminal inflow (`+current_value`) dated on its terminal valuation date.
- **Flow Netting**: Multiple flows occurring on the same calendar date are netted into a single cash flow per date.
- **Day Count**: Actual/365:
  $$t_i = \frac{(d_i - d_0).\text{days}}{\text{DAYS\_PER\_YEAR}} \quad (\text{DAYS\_PER\_YEAR} = 365)$$

### Solver Algorithm
The solver determines $r$ such that Net Present Value equals zero:
$$f(x) = \sum_{i=1}^N cf_i \cdot e^{-x \cdot t_i} = 0 \quad \text{where } x = \ln(1 + r)$$

- **Grid Scan & Bisection**: Scans 1200 grid brackets between $\ln(1 + \text{XIRR\_RATE\_MIN})$ and $\ln(1 + \text{XIRR\_RATE\_MAX})$ ($-0.9999$ to $100.0$) for sign changes, refining roots with bisection.
- **Root Selection**: If multiple roots exist, the root with minimum $|r|$ is selected, and `ambiguous = True` is reported.
- **Verification**: Verifies $|NPV(r)| \le 10^{-6} \times \sum |cf_i|$, returning `NO_SOLUTION` if unverified.
- **Float64 Exception**: The solver utilizes `float64` internally for numerical speed. Returned rates are converted to `Decimal`, quantized to 6 places (`0.000001`), and formatted as fraction strings (e.g. `"0.100000"` represents 10.0000%).

### Reason Codes (Evaluated in Strict Priority)
1. `NO_TRANSACTIONS`: No cash flows in scope.
2. `NO_NAV_DATA`: Open positions exist but none possesses a live NAV and no closed flows exist.
3. `INSUFFICIENT_FLOWS`: Fewer than two distinct dates after netting, or all flows have identical sign.
4. `PERIOD_TOO_SHORT`: Date span between first and last flow is under 30 calendar days (`XIRR_MIN_DAYS = 30`).
5. `NO_SOLUTION`: No mathematical root bracketed within rate bounds, or NPV verification failed.

Flag `short_period = True` is reported whenever the span is under 365 days (`XIRR_SHORT_PERIOD_DAYS = 365`).

---

## 5. Historical Value-Over-Time Series

The value series evaluates portfolio wealth progression over standard ranges (`1m`, `6m`, `1y`, `3y`, `5y`, `max`):

- **Single $O(T + D)$ Sweep**: Ledger transactions and sampled dates are traversed in a single chronological sweep, forward-filling running units and average cost.
- **Price Point Precedence**:
  1. Official daily AMFI historical NAV records (`nav_history`).
  2. Fund `latest_nav` at `latest_nav_date`.
  3. Ledger transaction NAVs.
  *On identical dates, official AMFI NAV strictly wins.*
- **Point Sampling & Cap**: Points are sampled at range-specific intervals (daily for 1m, weekly for 1y, etc.) and capped at 400 points (`MAX_SERIES_POINTS`), ensuring the final date (today IST) is always included.
- **Query Efficiency**: Three constant queries load in-range NAVs, the last NAV before range start (`DISTINCT ON`), and ledger transactions without N+1 overhead.

---

## 6. Worked Hand-Computed Examples

### Example A: XIRR Closed Forms
- Flows: `-1000` on `2025-01-01`, `-1000` on `2026-01-01`, `+2310` on `2027-01-01` $\implies$ `rate = 0.100000` (10.0000%).
- Flows: `-1000` on `2025-01-01`, `+1100` on `2026-01-01` $\implies$ `rate = 0.100000`.
- Flows: `-1000` on `2025-01-01`, `+900` on `2026-01-01` $\implies$ `rate = -0.100000` (-10.0000%).
- Flows: `-1000` on `2024-01-01`, `+1210` on `2025-12-31` (730 days / 2 leap years) $\implies$ `rate = 0.100000`.
- Multiple Roots: `-1000` on `2025-01-01`, `+2300` on `2026-01-01`, `-1320` on `2027-01-01` has roots at 10% and 20% $\implies$ selects `rate = 0.100000`, `ambiguous = True`.

### Example B: Valuation & XIRR Integration
- Buy `2025-01-01`: 10 units at 100.00 (Amount: 1,000.00)
- Buy `2026-01-01`: 10 units at 100.00 (Amount: 1,000.00)
- Fund `latest_nav = 115.5000` on `2027-01-01`:
  - `current_value`: $20 \times 115.50 = 2,310.00$
  - `cost_basis`: $1,000.00 + 1,000.00 = 2,000.00$
  - `unrealized_gain`: $2,310.00 - 2,000.00 = 310.00$
  - `unrealized_gain_pct`: $15.50\%$
  - `xirr.rate`: `"0.100000"`

### Example C: Realized Gain Tracking
- Buy `2025-01-10`: 100 units at 50.00 (Amount: 5,000.00)
- Buy `2025-02-10`: 50 units at 60.00 (Amount: 3,000.00)
- Sell `2025-03-10`: 30 units at 70.00 (Proceeds: 2,100.00)
- Fund `latest_nav = 80.0000`:
  - Avg cost before sell: $8,000 / 150 = 53.3333...$
  - Cost basis of sold units: $30 \times (8,000 / 150) = 1,600.00$
  - Realized gain: $2,100.00 - 1,600.00 = 500.00$
  - Remaining units: 120.0000, `cost_basis`: $6,400.00$
  - `current_value`: $120 \times 80.00 = 9,600.00$
  - `unrealized_gain`: $9,600.00 - 6,400.00 = 3,200.00$ (50.00%)
  - `total_gain`: $3,200.00 + 500.00 = 3,700.00$

### Example D: Value Series Precedence
- Ledger buy 100@50 on 2025-01-10, buy 50@60 on 2025-02-10, sell 30@70 on 2025-03-10.
- On `2025-02-15`: value is $150 \times 60 = 9,000.00$, cost basis $8,000.00$.
- On `2025-03-10` with ledger NAV only: value is $120 \times 70 = 8,400.00$, cost basis $6,400.00$.
- With official NAV $69.0000$ on `2025-03-10`: official NAV wins, value is $120 \times 69 = 8,280.00$.
- With official NAV $72.0000$ on `2025-03-20`: value is $120 \times 72 = 8,640.00$.
