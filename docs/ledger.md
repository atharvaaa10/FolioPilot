# FolioPilot Ledger Architecture & Position Derivation

This document defines the architectural invariants and contracts governing portfolios, target allocations, the transaction ledger, and position derivation in FolioPilot (Phase 3A).

---

## 1. The Ledger as the Source of Truth

FolioPilot treats the `transactions` table as the sole, immutable, append-only source of truth:
- Positions, cost bases, cumulative invested capital, current valuations, and realized/unrealized gains are **never** stored as mutable columns in separate tables.
- All portfolio views and position summaries are derived deterministically on read by executing an in-memory chronological replay of the portfolio's transactions.
- Historical integrity is preserved: backdated entries, insertions, and deletions re-derive positions deterministically across all downstream time horizons.

---

## 2. Deterministic Ordering Key

To eliminate order ambiguity when replaying transactions, especially across concurrent entries or intraday trades:
- Transactions for each mutual fund scheme within a portfolio are sorted by the deterministic tuple:
  $$\text{Sort Key} = (\text{txn\_date ASC}, \text{type\_rank ASC}, \text{created\_at ASC}, \text{id ASC})$$
- **Intraday Type Precedence**:
  - `BUY` transactions are assigned `type_rank = 0`.
  - `SELL` transactions are assigned `type_rank = 1`.
  - **Rule**: On any given calendar date $D$, all `BUY` events take effect before any `SELL` events. This ensures that purchases and redemptions on the same day never trigger false-positive intraday oversell errors.
- **Tie-Breaking**:
  - Transactions on the same date with the same type are ordered by database creation timestamp (`created_at ASC`).
  - Ties are deterministically broken by the UUID primary key (`id ASC`).

---

## 3. Positive Sign Convention

A strict positive-only invariant is enforced across all layers (API, schemas, and PostgreSQL check constraints):
- `units > 0`, `nav > 0`, and `amount > 0` are mandatory for both `BUY` and `SELL` transactions.
- A sale is denoted strictly by `txn_type = "SELL"`, **never** by negative numbers.
- Submissions with negative or zero quantities are rejected at schema validation time.

---

## 4. Decimal Precision & Serialization

To eliminate floating-point drift across Python `Decimal`, PostgreSQL `numeric`, and JavaScript `Number`:
- **Scale Limits**:
  - `units`: `numeric(18, 4)` (maximum 4 decimal places)
  - `nav`: `numeric(18, 8)` (maximum 8 decimal places)
  - `amount`: `numeric(18, 2)` (maximum 2 decimal places, rounded half-up)
  - `target_pct`: `numeric(5, 2)` (maximum 2 decimal places, range $0.01$ to $100.00$)
- **Serialization Contract**:
  - In all JSON API responses and request payloads, decimal values are serialized strictly as strings (e.g. `"100.5000"`, `"25.25000000"`, `"2537.63"`).
  - Web client parses all financial amounts and target percentages using `decimal.js`, guaranteeing exact decimal arithmetic (e.g. $33.33 + 33.33 + 33.34 = 100.00$).

---

## 5. The Ownership 404 Rule

To prevent resource enumeration and cross-tenant information leakage:
- If an authenticated user queries, updates, or deletes a portfolio or transaction that belongs to another user (or that does not exist):
  - The API **MUST** return `HTTP 404 NOT_FOUND` with error code `PORTFOLIO_NOT_FOUND` or `TRANSACTION_NOT_FOUND`.
  - The API **NEVER** returns `HTTP 403 FORBIDDEN` for resource ID lookups.
  - An attacker cannot determine whether an arbitrary UUID exists in another user's account.

---

## 6. Portfolio-Row Lock Rule for Ledger Mutations

To guarantee consistency under concurrent writes without dirty reads or negative balance race conditions:
1. Every transaction mutation (`POST /api/v1/portfolios/{id}/transactions` or `DELETE /api/v1/portfolios/{id}/transactions/{txn_id}`) begins an atomic database transaction.
2. The transaction immediately acquires a pessimistic row-level exclusive lock on the parent portfolio row:
   ```sql
   SELECT id FROM portfolios WHERE id = :portfolio_id AND user_id = :user_id FOR UPDATE;
   ```
3. The mutation is staged in the session.
4. The full transaction history for the affected scheme is fetched under the lock and replayed.
5. If cumulative units drop below $0$ at any historical point, the mutation is rejected with `HTTP 409 Conflict` (`LEDGER_OVERSELL_REJECTED`) and the entire transaction rolls back.
6. Only if the ledger invariant holds does the transaction commit and release the lock.

---

## 7. Position Derivation: Average Cost Method

In Phase 3A, positions and cost bases are calculated using the **Weighted Average Cost Basis** method (FIFO tax lot matching and capital gains grandfathering will be introduced in a future phase):

### State Variables per Fund:
- $\text{units} = 0$
- $\text{invested} = 0$
- $\text{avg\_nav} = 0$
- $\text{realized\_gain} = 0$

### Rules on Replay:
1. **On BUY($u, n, a$)**:
   $$\text{units}_{\text{new}} = \text{units} + u$$
   $$\text{invested}_{\text{new}} = \text{invested} + a$$
   $$\text{avg\_nav} = \frac{\text{invested}_{\text{new}}}{\text{units}_{\text{new}}}$$

2. **On SELL($u, n, a$)**:
   - Check: $u \le \text{units}$ (otherwise abort with `LEDGER_OVERSELL_REJECTED`).
   $$\text{cost\_of\_sold} = u \times \text{avg\_nav}$$
   $$\text{realized\_gain} = \text{realized\_gain} + (a - \text{cost\_of\_sold})$$
   $$\text{units}_{\text{new}} = \text{units} - u$$
   $$\text{invested}_{\text{new}} = \text{invested} - \text{cost\_of\_sold}$$
   - If $\text{units}_{\text{new}} = 0$: $\text{invested} = 0$ and $\text{avg\_nav} = 0$.

3. **On Valuation**:
   $$\text{current\_value} = \text{units} \times \text{latest\_nav}$$
   $$\text{unrealized\_gain} = \text{current\_value} - \text{invested}$$

---

## 8. New Phase 3A Error Codes

The table below lists all new error codes, their HTTP status, and error condition:

| Error Code | HTTP Status | Description |
|:---|:---:|:---|
| `PORTFOLIO_LIMIT_EXCEEDED` | `409 Conflict` | User reached maximum portfolio limit (`MAX_PORTFOLIOS_PER_USER = 20`). |
| `PORTFOLIO_NAME_CONFLICT` | `409 Conflict` | Portfolio with the same name already exists for this user. |
| `PORTFOLIO_NOT_FOUND` | `404 Not Found` | Portfolio does not exist or belongs to another user (Ownership 404 rule). |
| `TRANSACTION_NOT_FOUND` | `404 Not Found` | Transaction does not exist or belongs to another user's portfolio. |
| `TRANSACTION_LIMIT_EXCEEDED` | `409 Conflict` | Portfolio reached maximum transaction count (`MAX_TRANSACTIONS_PER_PORTFOLIO = 10,000`). |
| `TARGETS_INVALID` | `422 Unprocessable Entity` | Target allocations failed validation (exceeds 5 rows, duplicate asset classes, percentages not summing to exactly 100.00%, or invalid precision). |
| `TRANSACTION_AMOUNTS_INVALID` | `422 Unprocessable Entity` | Fewer than 2 of {units, nav, amount} provided, or supplied amount violates tolerance ($|u \times n - a| > \max(1.00, 0.002 \times a)$). |
| `TRANSACTION_DATE_INVALID` | `422 Unprocessable Entity` | Transaction date is earlier than 1990-01-01 or later than current calendar date. |
| `LEDGER_OVERSELL_REJECTED` | `409 Conflict` | SELL transaction or deletion of a prior BUY causes cumulative units to drop below zero. |

