# FolioPilot SIP Subsystem Architecture & Execution Engine

This document defines the architectural invariants, domain rules, schedule mathematics, and ledger integration governing Systematic Investment Plans (SIPs) in FolioPilot (Phase 3B).

---

## 1. Domain Overview & Invariants

A **Systematic Investment Plan (SIP)** is a recurring investment rule belonging to a portfolio that automates scheduled mutual fund purchases.

### Fundamental Principles:
1. **Rule vs. Installment vs. Transaction**:
   - A `Sip` represents the recurring rule (fund, base amount, day of month, start/end dates, step-up percentage).
   - A `Sip` lazily generates `SipInstallment` records for each due date.
   - When an installment executes, it produces exactly one ordinary `buy` `Transaction` in the portfolio ledger.
2. **The Ledger Remains the Source of Truth**:
   - The Phase 3A append-only ledger (`transactions` table) remains the single source of truth for holdings, positions, cash flows, and cost bases.
   - Executed SIP installments do not bypass or duplicate ledger logic; they invoke `TransactionService.add_transaction`.
3. **Managed Transaction Invariant**:
   - Every transaction spawned by an executed installment has a foreign key `sip_installment_id` linking back to its parent `SipInstallment`.
   - Managed transactions **cannot** be edited or deleted directly via the transactions API.
   - Direct mutation attempts return `HTTP 409 Conflict` with `TRANSACTION_MANAGED_BY_SIP`.
   - Removal must be executed through the SIP installment skip API (`POST /sips/{sip_id}/installments/{inst_id}/skip`).

---

## 2. Database Models & Schema

### `sips` Table
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `uuid` | Primary Key, default `gen_random_uuid()` | Unique SIP identifier |
| `portfolio_id` | `uuid` | Foreign Key `portfolios.id` ON DELETE CASCADE, NOT NULL | Parent portfolio |
| `fund_id` | `uuid` | Foreign Key `funds.id` ON DELETE RESTRICT, NOT NULL | Target mutual fund scheme |
| `amount` | `numeric(18, 2)` | NOT NULL, CHECK (`amount >= 100.00` AND `amount <= 10000000.00`) | Monthly investment amount in INR |
| `day_of_month` | `integer` | NOT NULL, CHECK (`day_of_month >= 1` AND `day_of_month <= 28`) | Day of month when installment is due |
| `start_date` | `date` | NOT NULL | First date from which schedule begins |
| `end_date` | `date` | NULLABLE | Optional end date (inclusive) |
| `step_up_percent` | `numeric(5, 2)` | NOT NULL, DEFAULT 0.00, CHECK (`step_up_percent >= 0.00` AND `step_up_percent <= 100.00`) | Annual percentage increase in installment amount |
| `notes` | `varchar(500)` | NULLABLE | User notes |
| `created_at` | `timestamptz` | NOT NULL, default `NOW()` | Creation audit timestamp |
| `updated_at` | `timestamptz` | NOT NULL, default `NOW()` | Last update timestamp |

### `sip_pauses` Table
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `uuid` | Primary Key, default `gen_random_uuid()` | Unique pause identifier |
| `sip_id` | `uuid` | Foreign Key `sips.id` ON DELETE CASCADE, NOT NULL | Parent SIP |
| `paused_on` | `date` | NOT NULL | Date pause became effective (inclusive) |
| `resumed_on` | `date` | NULLABLE | Date SIP was resumed (exclusive); NULL indicates currently paused |
| `created_at` | `timestamptz` | NOT NULL, default `NOW()` | Creation audit timestamp |

- **Partial Unique Index**: `uq_sip_pauses_open_per_sip` on `(sip_id)` WHERE `resumed_on IS NULL`. Enforces that a SIP cannot have more than one active open pause at a time.

### `sip_installments` Table
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `uuid` | Primary Key, default `gen_random_uuid()` | Unique installment identifier |
| `sip_id` | `uuid` | Foreign Key `sips.id` ON DELETE CASCADE, NOT NULL | Parent SIP |
| `due_date` | `date` | NOT NULL | Scheduled calendar due date |
| `planned_amount` | `numeric(18, 2)` | NOT NULL, CHECK (`planned_amount > 0`) | Calculated investment amount including step-up |
| `status` | `varchar(20)` | NOT NULL, CHECK (`status IN ('pending', 'executed', 'skipped')`) | Execution status |
| `nav_date` | `date` | NULLABLE | Date of NAV used for execution |
| `created_at` | `timestamptz` | NOT NULL, default `NOW()` | Creation timestamp |

- **Unique Constraint**: `uq_sip_installments_sip_due_date` on `(sip_id, due_date)`. Prevents duplicate installment generation for the same schedule date.

### `transactions` Table Link
- Added column: `sip_installment_id uuid NULLABLE REFERENCES sip_installments(id) ON DELETE SET NULL`.
- Unique Index: `uq_transactions_sip_installment_id` on `(sip_installment_id)`. Enforces that at most one transaction can ever be linked to an installment.

---

## 3. SIP Status Derivation

SIP status is derived deterministically at query time:
1. `ended`: If `end_date` is not NULL and `today > end_date`.
2. `paused`: If an open pause row exists (`resumed_on IS NULL`) and `today >= paused_on`.
3. `scheduled`: If `start_date > today`.
4. `active`: If none of the above conditions apply.

---

## 4. Schedule Generation & Step-Up Math

### Recurrence Rules:
- Frequency is strictly monthly on `day_of_month`.
- `day_of_month` is restricted to $1 \le \text{day} \le 28$. This guarantees that every calendar month has that day, completely avoiding 29th, 30th, 31st and leap-year edge cases.
- First due date calculation:
  $$\text{first\_due\_date}(\text{start\_date}, \text{day}) = \begin{cases} (Y, M, \text{day}) & \text{if } \text{start\_date.day} \le \text{day} \\ (Y, M + 1, \text{day}) & \text{if } \text{start\_date.day} > \text{day} \end{cases}$$

### Step-Up Math & Pause Invariant:
Step-up increases the monthly investment amount annually by $s\%$ (`step_up_percent`):
$$A_k = \text{round}\left(A_0 \cdot \left(1 + \frac{s}{100}\right)^k, 2\right)$$
where $k$ is the number of full years elapsed:
$$k = \left\lfloor \frac{m - 1}{12} \right\rfloor$$
and $m \ge 1$ is the 1-based installment index counted from the original schedule origin date ($\text{first\_due\_date}$).

**Pause Invariant for Step-Up**:
Pausing a SIP skips installment execution during $[ \text{paused\_on}, \text{resumed\_on} )$, but does **not** reset or shift the step-up calendar. $k$ is always computed relative to the true schedule origin date, ensuring annual step-ups remain synchronized with anniversary months.

---

## 5. Execution Engine & NAV Selection

Installment generation and execution run periodically (via Celery beat at 22:15 IST and 06:30 IST) or on-demand (`make run-sips` or trigger hooks after NAV backfill and SIP creation):

### Execution Workflow:
1. **Lazy Installment Generation**:
   `SipExecutor.generate_due_installments` queries all non-ended SIPs, computes due dates up to today, and inserts pending installments using PostgreSQL `ON CONFLICT (sip_id, due_date) DO NOTHING`.
2. **NAV Point Resolution**:
   For each pending installment with `due_date <= today`:
   - `pick_nav(due_date, today, points)` selects the NAV point on `due_date` if present.
   - If `due_date` was a non-trading day (weekend/holiday), it selects the most recent prior trading day's NAV.
   - Under no circumstances does it use a forward-looking NAV (future date).
   - If no historical NAV is available on or prior to `due_date`, the installment remains `pending` and execution is deferred until backfill completes.
3. **Isolated Database Transactions with Pessimistic Row Locking**:
   Each installment executes in its own database transaction:
   - Acquires pessimistic exclusive lock on the portfolio row: `SELECT * FROM portfolios WHERE id = :p_id FOR UPDATE`.
   - Re-selects the installment row `FOR UPDATE` and asserts `status == 'pending'`.
   - Creates a `buy` transaction via `TransactionService.add_transaction`, passing `sip_installment_id`.
   - Calculates units with exact 4-decimal precision: $\text{units} = \text{round}\left(\frac{\text{amount}}{\text{nav}}, 4\right)$.
   - Updates installment `status = 'executed'` and `nav_date = chosen_nav_date`.
   - Commits transaction.
4. **Fault Isolation**:
   If an installment encounters an error (e.g. `TRANSACTION_LIMIT_REACHED`), it is logged and the installment remains `pending`. Other installments proceed unaffected.

---

## 6. Managed Transactions & Skip Semantics

### Protection:
- The transactions table enforces data integrity via `sip_installment_id`.
- Modifying (`PATCH /portfolios/{p_id}/transactions/{id}`) or deleting (`DELETE /portfolios/{p_id}/transactions/{id}`) a managed transaction is rejected with `HTTP 409 Conflict` and error code `TRANSACTION_MANAGED_BY_SIP`.

### Skip Semantics:
- An installment can be skipped via `POST /portfolios/{p_id}/sips/{sip_id}/installments/{inst_id}/skip`.
- **Pending Installment**: Status is updated directly from `pending` to `skipped`. No ledger transaction exists.
- **Executed Installment**:
  1. The API locates the linked ledger transaction.
  2. It deletes the transaction through `TransactionService.delete_transaction`.
  3. `TransactionService` replays the ledger under the portfolio lock. If subsequent `sell` transactions rely on the units provided by this buy, the operation fails with `HTTP 409 Conflict` and error code `LEDGER_INCONSISTENT`.
  4. If the ledger remains valid, the buy transaction is deleted, the installment status is set to `skipped`, and the session commits.

---

## 7. Error Codes & HTTP Statuses

| Error Code | HTTP Status | Description |
| :--- | :--- | :--- |
| `PORTFOLIO_NOT_FOUND` | `404 Not Found` | Portfolio does not exist or belongs to another user (Ownership 404 rule). |
| `SIP_NOT_FOUND` | `404 Not Found` | SIP does not exist or belongs to another user. |
| `INSTALLMENT_NOT_FOUND` | `404 Not Found` | Installment does not exist or does not belong to the SIP. |
| `FUND_INACTIVE` | `409 Conflict` | Attempted to create a SIP on an inactive mutual fund. |
| `SIP_LIMIT_REACHED` | `409 Conflict` | Portfolio already has 50 active/scheduled SIPs. |
| `SIP_ALREADY_PAUSED` | `409 Conflict` | Attempted to pause a SIP that already has an open pause. |
| `SIP_NOT_PAUSED` | `409 Conflict` | Attempted to resume a SIP that is not currently paused. |
| `SIP_ALREADY_ENDED` | `409 Conflict` | Attempted to pause, resume, or end a SIP that has already ended. |
| `SIP_INVALID_SCHEDULE` | `422 Unprocessable Entity` | Schedule generates zero execution dates (e.g. end date before first due date). |
| `INSTALLMENT_NOT_SKIPPABLE` | `409 Conflict` | Installment has already been skipped. |
| `TRANSACTION_MANAGED_BY_SIP` | `409 Conflict` | Direct edit or delete attempted on a SIP-managed transaction. |
| `LEDGER_INCONSISTENT` | `409 Conflict` | Skipping an executed installment would result in negative holdings downstream. |

---

## 8. Worked Example Walkthrough

### Configuration:
- **Fund**: Scheme `160005` ("Worked Example Fund")
- **Base Amount**: ₹5,000.00 / month
- **Day of Month**: 10
- **Start Date**: `2025-01-05`
- **Step-Up**: 10.00%
- **Clock**: Evaluated as of `2025-06-20`

### NAV Schedule:
| Due Date | Trading Date Used | NAV (₹) | Planned Amount (₹) | Units Acquired | Cumulative Units |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2025-01-10 | 2025-01-10 | 50.0000 | 5,000.00 | 100.0000 | 100.0000 |
| 2025-02-10 | 2025-02-10 | 55.0000 | 5,000.00 | 90.9091 | 190.9091 |
| 2025-03-10 | 2025-03-10 | 60.0000 | 5,000.00 | 83.3333 | 274.2424 |
| 2025-04-10 | 2025-04-10 | 62.5000 | 5,000.00 | 80.0000 | 354.2424 |
| 2025-05-10 | 2025-05-12 (Mon) | 65.0000 | 5,000.00 | 76.9231 | 431.1655 |
| 2025-06-10 | 2025-06-10 | 70.0000 | 5,000.00 | 71.4286 | 502.5941 |

### Summary Verification:
- **Total Installments Executed**: 6
- **Total Invested Cost Basis**: ₹30,000.00
- **Total Units Acquired**: 502.5941
- **Average Cost per Unit**: ₹59.6903
