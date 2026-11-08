"""Test verifying committed contract fixtures match freshly generated ones."""

import json

from scripts.generate_contract_fixtures import FIXTURE_DIR, generate_fixtures


def _normalize_fixture_value(val: object) -> object:
    """Normalize variable timestamps or dynamic fields for drift comparisons."""
    if isinstance(val, dict):
        normalized: dict[str, object] = {}
        for k, v in val.items():
            time_fields = ("created_at", "updated_at", "last_run_time", "last_success_time")
            if k in time_fields and isinstance(v, str):
                normalized[k] = "TIMESTAMP"
            elif k in ("id", "portfolio_id", "fund_id") and isinstance(v, str):
                normalized[k] = "UUID"
            else:
                normalized[k] = _normalize_fixture_value(v)
        return normalized
    elif isinstance(val, list):
        return [_normalize_fixture_value(item) for item in val]
    return val


def test_contract_fixtures_match_generated() -> None:
    """Fails if committed contract fixtures differ from newly generated schemas."""
    generated = generate_fixtures()

    for filename, fresh_content in generated.items():
        filepath = FIXTURE_DIR / filename
        assert filepath.exists(), f"Committed fixture missing: {filepath}"

        with open(filepath, encoding="utf-8") as f:
            committed_content = json.load(f)

        norm_committed = _normalize_fixture_value(committed_content)
        norm_fresh = _normalize_fixture_value(fresh_content)

        assert norm_committed == norm_fresh, (
            f"Contract drift detected in {filename}! Run 'make contract' to update."
        )
