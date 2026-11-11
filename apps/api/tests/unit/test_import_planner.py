"""Unit and property tests for the pure import planner engine."""

import datetime as dt
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.constants import MAX_TRANSACTIONS_PER_PORTFOLIO
from app.services.import_planner import (
    ExistingSip,
    ExistingTransactionItem,
    PlannedRow,
    compute_plan_fingerprint,
    plan_import,
)
from app.services.import_rows import NormalizedRow


def _make_fund(
    scheme_code: int = 122639, isin: str = "INF879O01018", is_active: bool = True
) -> MagicMock:
    f = MagicMock()
    f.id = uuid4()
    f.scheme_code = scheme_code
    f.isin = isin
    f.name = "Test Fund"
    f.is_active = is_active
    return f


def _make_norm_row(
    row_number: int = 2,
    scheme_code: int | None = 122639,
    isin: str | None = "INF879O01018",
    txn_type: str = "buy",
    txn_date: dt.date = dt.date(2025, 1, 15),
    units: Decimal = Decimal("100.0000"),
    nav: Decimal = Decimal("50.00000000"),
    amount: Decimal = Decimal("5000.00"),
    notes: str | None = None,
    messages: list[dict[str, object]] | None = None,
) -> NormalizedRow:
    return NormalizedRow(
        row_number=row_number,
        scheme_code=scheme_code,
        isin=isin,
        fund_name_in_file="Test Fund",
        txn_type=txn_type,
        txn_date=txn_date,
        units=units,
        nav=nav,
        amount=amount,
        notes=notes,
        raw={},
        messages=messages or [],
    )


def test_multiset_duplicate_combinations() -> None:
    fund = _make_fund()
    fund_id = fund.id
    d = dt.date(2025, 1, 15)
    u = Decimal("10.0000")
    a = Decimal("500.00")
    key = (fund_id, d, "buy", u, a)

    # 1. n=1, m=0 -> 0 duplicate, 1 will_import
    r1 = _make_norm_row(row_number=2, units=u, amount=a, txn_date=d)
    res = plan_import(
        normalized_rows=[r1],
        fund_lookup_by_code={122639: fund},
        fund_lookup_by_isin={"INF879O01018": [fund]},
        existing_ledger_by_fund={},
        existing_duplicate_counts={},
        active_sips=[],
    )
    assert res.rows_total == 1
    assert res.rows_duplicate == 0
    assert res.will_import == 1
    assert res.rows[0].status == "ok"

    # 2. n=1, m=1 -> 1 duplicate, 0 will_import
    res = plan_import(
        normalized_rows=[r1],
        fund_lookup_by_code={122639: fund},
        fund_lookup_by_isin={"INF879O01018": [fund]},
        existing_ledger_by_fund={},
        existing_duplicate_counts={key: 1},
        active_sips=[],
    )
    assert res.rows_duplicate == 1
    assert res.will_import == 0
    assert res.rows[0].status == "duplicate"
    assert any(m["code"] == "DUPLICATE_IN_LEDGER" for m in res.rows[0].messages)

    # 3. n=2 in file, m=1 in ledger -> 1 duplicate, 1 will_import
    r2 = _make_norm_row(row_number=3, units=u, amount=a, txn_date=d)
    res = plan_import(
        normalized_rows=[r1, r2],
        fund_lookup_by_code={122639: fund},
        fund_lookup_by_isin={"INF879O01018": [fund]},
        existing_ledger_by_fund={},
        existing_duplicate_counts={key: 1},
        active_sips=[],
    )
    assert res.rows_duplicate == 1
    assert res.will_import == 1
    assert res.rows[0].status == "duplicate"
    assert res.rows[1].status == "warning"  # DUPLICATE_IN_FILE warning
    assert any(m["code"] == "DUPLICATE_IN_FILE" for m in res.rows[1].messages)

    # 4. n=3 in file, m=2 in ledger -> 2 duplicates, 1 will_import
    r3 = _make_norm_row(row_number=4, units=u, amount=a, txn_date=d)
    res = plan_import(
        normalized_rows=[r1, r2, r3],
        fund_lookup_by_code={122639: fund},
        fund_lookup_by_isin={"INF879O01018": [fund]},
        existing_ledger_by_fund={},
        existing_duplicate_counts={key: 2},
        active_sips=[],
    )
    assert res.rows_duplicate == 2
    assert res.will_import == 1
    assert res.rows[0].status == "duplicate"
    assert res.rows[1].status == "duplicate"
    assert res.rows[2].status == "warning"

    # 5. n=1 in file, m=2 in ledger -> 1 duplicate, 0 will_import
    res = plan_import(
        normalized_rows=[r1],
        fund_lookup_by_code={122639: fund},
        fund_lookup_by_isin={"INF879O01018": [fund]},
        existing_ledger_by_fund={},
        existing_duplicate_counts={key: 2},
        active_sips=[],
    )
    assert res.rows_duplicate == 1
    assert res.will_import == 0


def test_fund_resolution_rules() -> None:
    fund_a = _make_fund(scheme_code=1001, isin="INF001A01011")
    fund_b = _make_fund(scheme_code=1002, isin="INF002B01012")
    inactive_fund = _make_fund(scheme_code=1003, isin="INF003C01013", is_active=False)

    code_map = {1001: fund_a, 1002: fund_b, 1003: inactive_fund}
    isin_map = {
        "INF001A01011": [fund_a],
        "INF002B01012": [fund_b],
        "INF003C01013": [inactive_fund],
        "INF999AMBIG0": [fund_a, fund_b],  # Ambiguous ISIN
    }

    # Match by scheme_code only
    r_code_only = _make_norm_row(row_number=2, scheme_code=1001, isin=None)
    res = plan_import([r_code_only], code_map, isin_map, {}, {}, [])
    assert res.rows[0].status == "ok"
    assert res.rows[0].fund_id == fund_a.id

    # Match by ISIN only
    r_isin_only = _make_norm_row(row_number=3, scheme_code=None, isin="INF001A01011")
    res = plan_import([r_isin_only], code_map, isin_map, {}, {}, [])
    assert res.rows[0].status == "ok"
    assert res.rows[0].fund_id == fund_a.id

    # Ambiguous ISIN
    r_ambig = _make_norm_row(row_number=4, scheme_code=None, isin="INF999AMBIG0")
    res = plan_import([r_ambig], code_map, isin_map, {}, {}, [])
    assert res.rows[0].status == "error"
    assert any(m["code"] == "ISIN_AMBIGUOUS" for m in res.rows[0].messages)

    # Code and ISIN mismatch
    r_mismatch = _make_norm_row(row_number=5, scheme_code=1001, isin="INF002B01012")
    res = plan_import([r_mismatch], code_map, isin_map, {}, {}, [])
    assert res.rows[0].status == "error"
    assert any(m["code"] == "FUND_CODE_ISIN_MISMATCH" for m in res.rows[0].messages)

    # Inactive fund -> warning
    r_inactive = _make_norm_row(row_number=6, scheme_code=1003, isin=None)
    res = plan_import([r_inactive], code_map, isin_map, {}, {}, [])
    assert res.rows[0].status == "warning"
    assert any(m["code"] == "FUND_INACTIVE" for m in res.rows[0].messages)

    # Unknown fund
    r_unknown = _make_norm_row(row_number=7, scheme_code=999999, isin=None)
    res = plan_import([r_unknown], code_map, isin_map, {}, {}, [])
    assert res.rows[0].status == "error"
    assert any(m["code"] == "UNKNOWN_FUND" for m in res.rows[0].messages)


def test_sip_overlap_warning() -> None:
    fund = _make_fund()
    active_sip = ExistingSip(
        fund_id=fund.id,
        start_date=dt.date(2025, 1, 1),
        end_date=dt.date(2025, 12, 31),
    )

    # Buy within SIP window -> warning
    r_buy_in = _make_norm_row(row_number=2, txn_type="buy", txn_date=dt.date(2025, 5, 10))
    res = plan_import([r_buy_in], {122639: fund}, {"INF879O01018": [fund]}, {}, {}, [active_sip])
    assert res.rows[0].status == "warning"
    assert any(m["code"] == "POSSIBLE_SIP_OVERLAP" for m in res.rows[0].messages)

    # Buy outside SIP window -> ok
    r_buy_out = _make_norm_row(row_number=3, txn_type="buy", txn_date=dt.date(2026, 1, 10))
    res = plan_import([r_buy_out], {122639: fund}, {"INF879O01018": [fund]}, {}, {}, [active_sip])
    assert res.rows[0].status == "ok"
    assert not any(m["code"] == "POSSIBLE_SIP_OVERLAP" for m in res.rows[0].messages)

    # Sell within SIP window -> ok (SIPs are buys)
    r_sell_in = _make_norm_row(row_number=4, txn_type="sell", txn_date=dt.date(2025, 5, 10))
    # Give existing balance so sell doesn't fail ledger check
    ex_txn = ExistingTransactionItem(
        id=uuid4(),
        fund_id=fund.id,
        txn_type="buy",
        txn_date=dt.date(2025, 1, 1),
        units=Decimal("1000.0000"),
        nav=Decimal("50.00000000"),
        amount=Decimal("50000.00"),
        created_at=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
    )
    res = plan_import(
        [r_sell_in],
        {122639: fund},
        {"INF879O01018": [fund]},
        {fund.id: [ex_txn]},
        {},
        [active_sip],
    )
    assert res.rows[0].status == "ok"
    assert not any(m["code"] == "POSSIBLE_SIP_OVERLAP" for m in res.rows[0].messages)


def test_ledger_conflict_resolution() -> None:
    fund = _make_fund()

    # 1. Sell without balance -> INSUFFICIENT_UNITS
    r_sell = _make_norm_row(
        row_number=2,
        txn_type="sell",
        txn_date=dt.date(2025, 1, 15),
        units=Decimal("50.0000"),
    )
    res = plan_import([r_sell], {122639: fund}, {"INF879O01018": [fund]}, {}, {}, [])
    assert res.rows[0].status == "error"
    assert any(m["code"] == "INSUFFICIENT_UNITS" for m in res.rows[0].messages)

    # 2. Buy on same day as sell -> buy processed first (rank 0 vs 1), both succeed
    r_buy_same = _make_norm_row(
        row_number=2,
        txn_type="buy",
        txn_date=dt.date(2025, 1, 15),
        units=Decimal("50.0000"),
    )
    r_sell_same = _make_norm_row(
        row_number=3,
        txn_type="sell",
        txn_date=dt.date(2025, 1, 15),
        units=Decimal("50.0000"),
    )
    res = plan_import(
        [r_sell_same, r_buy_same], {122639: fund}, {"INF879O01018": [fund]}, {}, {}, []
    )
    assert res.rows_error == 0
    assert res.will_import == 2

    # 3. Two sells: first fits balance, second exceeds -> second sell rejected, first accepted
    r_buy = _make_norm_row(
        row_number=2,
        txn_type="buy",
        txn_date=dt.date(2025, 1, 1),
        units=Decimal("100.0000"),
    )
    r_sell_1 = _make_norm_row(
        row_number=3,
        txn_type="sell",
        txn_date=dt.date(2025, 1, 10),
        units=Decimal("60.0000"),
    )
    r_sell_2 = _make_norm_row(
        row_number=4,
        txn_type="sell",
        txn_date=dt.date(2025, 1, 20),
        units=Decimal("50.0000"),
    )
    res = plan_import(
        [r_buy, r_sell_1, r_sell_2], {122639: fund}, {"INF879O01018": [fund]}, {}, {}, []
    )
    assert res.rows[0].status == "ok"
    assert res.rows[1].status == "ok"
    assert res.rows[2].status == "error"
    assert any(m["code"] == "INSUFFICIENT_UNITS" for m in res.rows[2].messages)


def test_plan_fingerprint_determinism() -> None:
    fund_id = uuid4()
    p1 = PlannedRow(
        row_number=2,
        status="ok",
        fund_id=fund_id,
        fund=None,
        fund_name_in_file="Fund",
        txn_type="buy",
        txn_date=dt.date(2025, 1, 15),
        units=Decimal("10.0000"),
        nav=Decimal("50.00000000"),
        amount=Decimal("500.00"),
        notes="hello",
        raw={},
        messages=[],
    )
    fp1 = compute_plan_fingerprint([p1])
    fp2 = compute_plan_fingerprint([p1])
    assert fp1 == fp2

    # Altering notes changes fingerprint
    p2 = PlannedRow(
        row_number=2,
        status="ok",
        fund_id=fund_id,
        fund=None,
        fund_name_in_file="Fund",
        txn_type="buy",
        txn_date=dt.date(2025, 1, 15),
        units=Decimal("10.0000"),
        nav=Decimal("50.00000000"),
        amount=Decimal("500.00"),
        notes="different",
        raw={},
        messages=[],
    )
    assert compute_plan_fingerprint([p2]) != fp1


def test_portfolio_transaction_limit_check() -> None:
    fund = _make_fund()
    r = _make_norm_row(row_number=2)
    # Current txns + will_import > max -> blocking error
    res = plan_import(
        normalized_rows=[r],
        fund_lookup_by_code={122639: fund},
        fund_lookup_by_isin={"INF879O01018": [fund]},
        existing_ledger_by_fund={},
        existing_duplicate_counts={},
        active_sips=[],
        current_portfolio_txn_count=MAX_TRANSACTIONS_PER_PORTFOLIO,
    )
    assert "TRANSACTION_LIMIT_REACHED" in res.blocking_errors


# --- Hypothesis Property Tests ---


@settings(max_examples=30, deadline=None)
@given(
    txn_actions=st.lists(
        st.tuples(
            st.sampled_from(["buy", "sell"]),
            st.integers(min_value=1, max_value=30),  # day offset in Jan 2025
            st.decimals(min_value=Decimal("1.0000"), max_value=Decimal("50.0000"), places=4),
        ),
        min_size=1,
        max_size=15,
    )
)
def test_hypothesis_ledger_validity_post_plan(
    txn_actions: list[tuple[str, int, Decimal]],
) -> None:
    fund = _make_fund()
    rows: list[NormalizedRow] = []
    for idx, (t_type, day, units) in enumerate(txn_actions, start=2):
        rows.append(
            _make_norm_row(
                row_number=idx,
                txn_type=t_type,
                txn_date=dt.date(2025, 1, day),
                units=units,
                nav=Decimal("10.00000000"),
                amount=(units * Decimal("10.00")).quantize(Decimal("0.01")),
            )
        )

    res = plan_import(
        normalized_rows=rows,
        fund_lookup_by_code={122639: fund},
        fund_lookup_by_isin={"INF879O01018": [fund]},
        existing_ledger_by_fund={},
        existing_duplicate_counts={},
        active_sips=[],
    )

    # Verify that the accepted candidates never violate running balance
    accepted = [r for r in res.rows if r.status in ("ok", "warning")]
    # Sort chronologically as ledger would
    accepted.sort(
        key=lambda r: (
            r.txn_date or dt.date.min,
            0 if r.txn_type in ("buy", "dividend_reinvest") else 1,
            r.row_number,
        )
    )

    running_bal = Decimal("0")
    for r in accepted:
        assert r.units is not None
        if r.txn_type in ("buy", "dividend_reinvest"):
            running_bal += r.units
        elif r.txn_type == "sell":
            running_bal -= r.units
            assert running_bal >= Decimal("0"), (
                f"Ledger invariant violated: negative balance {running_bal}"
            )
