# FolioPilot: Excel Transaction Import Specification

Phase 4 introduces Excel transaction import built directly on top of the Phase 3A transaction ledger and Phase 3B SIP foundations.

---

## 1. Lifecycle & Architecture

The import process is fully transactional, previewable, and undoable:

```
[User Excel File (.xlsx)]
          │
          ▼
┌──────────────────────────────────┐
│ 1. Upload & ASGI Stream Limiter  │  -> Intercepts raw stream, aborts at 2 MB
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│ 2. Inspection & Security Guards  │  -> Zip bomb guards, macro check, OLE check, defusedxml
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│ 3. Row Normalization & Parsing   │  -> Date formats, aliases, float noise cleanup, fund lookup
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│ 4. Planner & Duplicate Detection │  -> Multiset duplicate rule, SIP overlap warning, fingerprint
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│ 5. DB Preview Storage            │  -> Stored in transaction_imports & transaction_import_rows
└─────────────────┬────────────────┘
                  │
         ┌────────┴────────┐
         ▼                 ▼
┌─────────────────┐ ┌───────────────┐
│ Commit          │ │ Discard / TTL │
│ (FOR UPDATE)    │ │ Auto-purge    │
└────────┬────────┘ └───────────────┘
         │
         ▼
┌─────────────────┐
│ Ledger Applied  │
│ (import_id FK)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Undo            │
│ (Ledger check)  │
└─────────────────┘
```

---

## 2. Template Specification

The official template is generated dynamically by `GET /api/v1/portfolios/{id}/imports/template` with two sheets:
1. `Transactions`: Data entry sheet with validated headers, data-validation dropdowns, and formatting.
2. `Instructions`: Guidance on accepted formats, aliases, fund identifiers, and error codes.

### Columns & Aliases

| Canonical Column | Accepted Variations | Type | Notes |
|---|---|---|---|
| `txn_date` | `Date`, `Transaction Date`, `Trade Date` | Date | ISO YYYY-MM-DD, DD/MM/YYYY, or Excel date cell |
| `scheme_code` | `Scheme Code`, `Fund Code`, `Code` | Integer | AMFI scheme code (e.g. 122639) |
| `isin` | `ISIN`, `ISIN Code` | String | 12-char alphanumeric (e.g. INF879O01018) |
| `txn_type` | `Type`, `Transaction Type`, `Action` | String | `buy`, `sell` (aliases: `purchase`, `redemption`, `allotted`, etc.) |
| `units` | `Units`, `Quantity`, `Qty` | Decimal | Up to 3 decimal places |
| `nav` | `NAV`, `Price`, `Rate` | Decimal | Up to 4 decimal places |
| `amount` | `Amount`, `Total Amount`, `Gross Amount` | Decimal | Up to 2 decimal places (rupees/paisa) |
| `notes` | `Notes`, `Remarks`, `Comment` | String | Max 500 chars, rendered safely without execution |
| `fund_name` | `Fund Name`, `Scheme Name` | String | Optional informational/hint column |

Either `scheme_code` or `isin` is required to resolve the mutual fund from the fund master.

---

## 3. Math & Derivation Rules

If 2 of (`units`, `nav`, `amount`) are supplied, the 3rd is derived:
- $\text{Amount} = \text{round}(\text{units} \times \text{nav}, 2)$ (half-up, nearest paisa)
- $\text{Units} = \text{round}(\text{amount} / \text{nav}, 3)$
- $\text{NAV} = \text{round}(\text{amount} / \text{units}, 4)$

If all 3 are supplied, they must be consistent:
$$|\text{units} \times \text{nav} - \text{amount}| \le 0.01$$
Discrepancies greater than 1 paisa are rejected with `CALCULATION_MISMATCH`.

---

## 4. Multiset Duplicate Detection

Duplicate detection prevents double-counting upon re-import while supporting legitimate identical multiple transactions (e.g., dual SIP installments or parallel lump sums):

Let:
- $n = \text{number of matching transaction records in existing ledger}$
- $m = \text{number of matching rows within the uploaded import batch}$

A match is defined on the exact tuple: `(fund_id, txn_date, txn_type, units, nav, amount)`.

**Rule**:
- Exactly $\min(n, m)$ rows in the batch are marked as `duplicate` (`DUPLICATE_IN_LEDGER`) and excluded from `will_import`.
- The remaining $\max(0, m - n)$ rows are treated as new transactions and included in `will_import`.

---

## 5. Security & Upload Size Enforcement

### Framework & Disk Spooling Behavior
- Starlette / FastAPI multipart parsing buffers small files in memory and spools parts exceeding 1 MB to `tempfile.SpooledTemporaryFile` on disk.
- To prevent denial-of-service from large uploads, FolioPilot implements `ImportUploadSizeLimitMiddleware` at the pure ASGI level.
- The middleware counts incoming raw stream bytes before multipart body parsing begins. If bytes exceed `IMPORT_MAX_FILE_BYTES` (2 MB), the request is cut off immediately with `413 IMPORT_FILE_TOO_LARGE`.
- Any temporary files created by Starlette during request parsing are unpersisted, unlinked, and automatically deleted upon request completion.

### Package & File Guards
- **Not a zip**: Non-zip payloads are rejected with `IMPORT_FILE_INVALID`.
- **OLE Header**: Legacy binary `.xls` files (starting with `\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1`) are rejected with `IMPORT_FILE_INVALID`.
- **Macro Content**: Files containing `vbaProject.bin` or macro content types (`application/vnd.ms-excel.sheet.macroEnabled.main+xml`) are rejected with `IMPORT_FILE_INVALID`.
- **Zip Bomb Protections**: Maximum 100 zip entries; maximum 20 MB uncompressed size; maximum 5,000 data rows.
- **XML Parsing**: Uses `defusedxml` to prevent billion laughs / quadratic expansion attacks.

---

## 6. Concurrency & Integrity

- **Row Locks**: Both `commit` and `undo` acquire an exclusive row lock on the portfolio (`SELECT FOR UPDATE FROM portfolios WHERE id = ...`).
- **Plan Fingerprint**: A deterministic SHA-256 hash of the normalized plan (`plan_fingerprint`) must accompany commit requests. If any underlying ledger state changed since preview, the commit is aborted with `IMPORT_STALE`.
- **Single Active Preview**: A partial unique index `(portfolio_id) WHERE status = 'previewed'` guarantees at most one active preview per portfolio at any time.
- **Undo Ledger Check**: An undo operation will reject with `LEDGER_INCONSISTENT` if undoing the batch would cause any subsequent holding units to drop below zero.

---

## 7. Celery Beat Purge Task

Uncommitted import previews older than 24 hours are purged automatically:
- **Task**: `foliopilot.purge_expired_import_previews`
- **Schedule**: Daily at 04:00 IST (22:30 UTC)
- **Time Agreement Test**: `test_import_purge_beat_schedule_times` ensures IST and UTC constants stay in sync.
