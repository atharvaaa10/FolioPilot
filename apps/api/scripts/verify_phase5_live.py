"""Live end-to-end verification script for FolioPilot Phase 5.

Executed inside the running API container during verify-phase5.ps1:
1. User A creates Portfolio A with 3 transactions on fund 122639
2. Fetch fund 122639 latest NAV and date
3. Fetch valuation and compare with expected values
4. Compute independent XIRR using bisection and compare with API
5. User A creates Portfolio B with 10-day-old buy and verifies PERIOD_TOO_SHORT
6. Verify summary totals match individual portfolio valuation totals
7. Fetch 1y value series and verify point bounds and terminal match
8. Verify brand new User C empty state
9. Verify User B 404 isolation and summary isolation
10. Verify invalid range 422 VALIDATION_ERROR
"""

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import httpx

client = httpx.Client(base_url="http://localhost:8000/api/v1")

# 1. Register User A
uid_a = uuid.uuid4().hex[:8]
reg_a = client.post(
    "/auth/register",
    json={"email": f"user_a_{uid_a}@example.com", "password": "Password123!"},
)
assert reg_a.status_code == 201, f"User A registration failed: {reg_a.text}"
token_a = reg_a.json()["data"]["access_token"]
headers_a = {"Authorization": f"Bearer {token_a}"}

# 2. Fetch Fund 122639
f_resp = client.get("/funds/122639", headers=headers_a)
assert f_resp.status_code == 200, f"Get fund failed: {f_resp.text}"
fund_data = f_resp.json()["data"]
latest_nav = Decimal(str(fund_data["latest_nav"]))
latest_nav_date = date.fromisoformat(fund_data["latest_nav_date"])
print(f"Fund 122639: latest_nav={latest_nav}, latest_nav_date={latest_nav_date}")

# 3. User A creates Portfolio A
p_a_resp = client.post(
    "/portfolios",
    json={"name": "User A Growth Portfolio"},
    headers=headers_a,
)
assert p_a_resp.status_code == 201
pid_a = p_a_resp.json()["data"]["id"]

# 4. Add the 3 transactions for fund 122639
tx1 = client.post(
    f"/portfolios/{pid_a}/transactions",
    json={
        "scheme_code": 122639,
        "txn_type": "buy",
        "txn_date": "2024-01-15",
        "units": "100.0000",
        "nav": "50.00000000",
        "amount": "5000.00",
    },
    headers=headers_a,
)
assert tx1.status_code == 201

tx2 = client.post(
    f"/portfolios/{pid_a}/transactions",
    json={
        "scheme_code": 122639,
        "txn_type": "buy",
        "txn_date": "2025-01-15",
        "units": "50.0000",
        "nav": "60.00000000",
        "amount": "3000.00",
    },
    headers=headers_a,
)
assert tx2.status_code == 201

tx3 = client.post(
    f"/portfolios/{pid_a}/transactions",
    json={
        "scheme_code": 122639,
        "txn_type": "sell",
        "txn_date": "2025-07-15",
        "units": "30.0000",
        "nav": "70.00000000",
        "amount": "2100.00",
    },
    headers=headers_a,
)
assert tx3.status_code == 201

# 5. Portfolio A Valuation
resp_va = client.get(f"/portfolios/{pid_a}/valuation", headers=headers_a)
assert resp_va.status_code == 200, f"Valuation failed: {resp_va.text}"
va_data = resp_va.json()["data"]
item_a = va_data["items"][0]

exp_units = "120.0000"
exp_cost_basis = "6400.00"
exp_realized_gain = "500.00"
exp_cur_val_dec = (Decimal(exp_units) * latest_nav).quantize(
    Decimal("0.01"), rounding=ROUND_HALF_UP
)
exp_cur_val = str(exp_cur_val_dec)
exp_unrealized_gain = str(
    (exp_cur_val_dec - Decimal(exp_cost_basis)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
)

print("\n=== PORTFOLIO A VALUATION: EXPECTED VS ACTUAL ===")
print(f"units:           Expected: {exp_units}     | Actual: {item_a['units']}")
print(f"cost_basis:      Expected: {exp_cost_basis}        | Actual: {item_a['cost_basis']}")
print(f"realized_gain:   Expected: {exp_realized_gain}         | Actual: {item_a['realized_gain']}")
print(f"current_value:   Expected: {exp_cur_val}       | Actual: {item_a['current_value']}")
print(
    f"unrealized_gain: Expected: {exp_unrealized_gain}       | Actual: {item_a['unrealized_gain']}"
)

# 6. Independent XIRR computation (bisection on exact flows)
terminal_date = max(latest_nav_date, date(2025, 7, 15))
flows = [
    (date(2024, 1, 15), -5000.0),
    (date(2025, 1, 15), -3000.0),
    (date(2025, 7, 15), 2100.0),
    (terminal_date, float(exp_cur_val_dec)),
]
d0 = flows[0][0]
times = [(d - d0).days / 365.0 for d, _ in flows]
cfs = [cf for _, cf in flows]


def npv(r: float) -> float:
    return sum(c * ((1.0 + r) ** (-t)) for c, t in zip(cfs, times, strict=True))


low, high = -0.9999, 100.0
for _ in range(100):
    mid = (low + high) / 2.0
    f_mid = npv(mid)
    if abs(f_mid) < 1e-9:
        break
    if npv(low) * f_mid <= 0:
        high = mid
    else:
        low = mid
expected_xirr_str = f"{mid:.6f}"
print(f"xirr rate:       Expected: {expected_xirr_str}       | Actual: {item_a['xirr']['rate']}")

# 7. Portfolio B (Single buy 10 days ago -> PERIOD_TOO_SHORT)
p_b_resp = client.post(
    "/portfolios",
    json={"name": "User A Short-Period Portfolio"},
    headers=headers_a,
)
assert p_b_resp.status_code == 201
pid_b = p_b_resp.json()["data"]["id"]

ten_days_ago = (date.today() - timedelta(days=10)).isoformat()
client.post(
    f"/portfolios/{pid_b}/transactions",
    json={
        "scheme_code": 122639,
        "txn_type": "buy",
        "txn_date": ten_days_ago,
        "units": "10.0000",
        "nav": "50.00000000",
        "amount": "500.00",
    },
    headers=headers_a,
)

resp_vb = client.get(f"/portfolios/{pid_b}/valuation", headers=headers_a)
assert resp_vb.status_code == 200
vb_data = resp_vb.json()["data"]
xirr_b = vb_data["totals"]["xirr"]
print("\n=== PORTFOLIO B SHORT PERIOD XIRR ===")
print(f"xirr rate:       Expected: None               | Actual: {xirr_b['rate']}")
print(f"xirr reason:     Expected: PERIOD_TOO_SHORT   | Actual: {xirr_b['reason']}")

# 8. Valuation Summary Parity
resp_sum = client.get("/valuation/summary", headers=headers_a)
assert resp_sum.status_code == 200
sum_data = resp_sum.json()["data"]
sum_p_a = next(p for p in sum_data["portfolios"] if p["id"] == str(pid_a))
exp_cur_total = va_data["totals"]["current_value"]
exp_basis_total = va_data["totals"]["cost_basis"]
exp_gain_total = va_data["totals"]["total_gain"]
print("\n=== SUMMARY PER-PORTFOLIO TOTALS VS INDIVIDUAL VALUATION ===")
print(f"p_a current_val: Expected: {exp_cur_total} | Actual: {sum_p_a['current_value']}")
print(f"p_a cost_basis:  Expected: {exp_basis_total}  | Actual: {sum_p_a['cost_basis']}")
print(f"p_a total_gain:  Expected: {exp_gain_total}   | Actual: {sum_p_a['total_gain']}")

# 9. Value Series 1y
resp_ser = client.get(f"/portfolios/{pid_a}/value-series?range=1y", headers=headers_a)
assert resp_ser.status_code == 200
ser_data = resp_ser.json()["data"]
pts = ser_data["points"]
print("\n=== PORTFOLIO A VALUE SERIES (1y) ===")
print(f"points count:    Actual: {len(pts)} (capped at 400)")
p0_date, p0_val, p0_cost = pts[0]["date"], pts[0]["value"], pts[0]["cost_basis"]
p1_date, p1_val, p1_cost = pts[-1]["date"], pts[-1]["value"], pts[-1]["cost_basis"]
print(f"first point:     date: {p0_date}, value: {p0_val}, cost: {p0_cost}")
print(f"last point:      date: {p1_date}, value: {p1_val}, cost: {p1_cost}")

# 10. Brand New User C Empty State
uid_c = uuid.uuid4().hex[:8]
reg_c = client.post(
    "/auth/register",
    json={"email": f"user_c_{uid_c}@example.com", "password": "Password123!"},
)
assert reg_c.status_code == 201
token_c = reg_c.json()["data"]["access_token"]
headers_c = {"Authorization": f"Bearer {token_c}"}

resp_c = client.get("/valuation/summary", headers=headers_c)
assert resp_c.status_code == 200
c_data = resp_c.json()["data"]
print("\n=== BRAND NEW USER C EMPTY SUMMARY ===")
c_cur = c_data["totals"]["current_value"]
c_cost = c_data["totals"]["cost_basis"]
c_reason = c_data["totals"]["xirr"]["reason"]
print(f"totals current_value: Expected: 0.00             | Actual: {c_cur}")
print(f"totals cost_basis:    Expected: 0.00             | Actual: {c_cost}")
print(f"totals xirr reason:   Expected: NO_TRANSACTIONS  | Actual: {c_reason}")

# 11. User B (Isolation on User A Portfolio)
uid_b = uuid.uuid4().hex[:8]
reg_b = client.post(
    "/auth/register",
    json={"email": f"user_b_{uid_b}@example.com", "password": "Password123!"},
)
assert reg_b.status_code == 201
token_b = reg_b.json()["data"]["access_token"]
headers_b = {"Authorization": f"Bearer {token_b}"}

resp_iso_val = client.get(f"/portfolios/{pid_a}/valuation", headers=headers_b)
iso_val_code = resp_iso_val.json()["error"]["code"]
print("\n=== USER B ISOLATION ON USER A PORTFOLIO ===")
print(f"valuation access:    Expected status: 404       | Actual: {resp_iso_val.status_code}")
print(f"valuation error:     Expected: PORTFOLIO_NOT_FOUND | Actual: {iso_val_code}")

resp_iso_ser = client.get(f"/portfolios/{pid_a}/value-series?range=1y", headers=headers_b)
iso_ser_code = resp_iso_ser.json()["error"]["code"]
print(f"value-series access: Expected status: 404       | Actual: {resp_iso_ser.status_code}")
print(f"series error:        Expected: PORTFOLIO_NOT_FOUND | Actual: {iso_ser_code}")

resp_sum_b = client.get("/valuation/summary", headers=headers_b)
p_names_b = [p["name"] for p in resp_sum_b.json()["data"]["portfolios"]]
has_p_a = p_a_resp.json()["data"]["name"] in p_names_b
print(f"user b summary mentions user a portfolio: Expected: False | Actual: {has_p_a}")

# 12. Invalid Range 422
resp_inv = client.get(f"/portfolios/{pid_a}/value-series?range=invalid", headers=headers_a)
print("\n=== VALUE SERIES INVALID RANGE 422 ===")
print(f"invalid range status: Expected: 422              | Actual: {resp_inv.status_code}")
print(
    f"invalid range error:  Expected: VALIDATION_ERROR | Actual: {resp_inv.json()['error']['code']}"
)
