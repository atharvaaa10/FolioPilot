from app.services.rate_limit import compute_fixed_window


def test_compute_fixed_window() -> None:
    # 60 second window
    bucket1, retry1 = compute_fixed_window(now_timestamp=100, window_seconds=60)
    assert bucket1 == 1  # 100 // 60
    assert retry1 == 20  # (2 * 60) - 100

    bucket2, retry2 = compute_fixed_window(now_timestamp=119, window_seconds=60)
    assert bucket2 == 1
    assert retry2 == 1  # (2 * 60) - 119

    bucket3, retry3 = compute_fixed_window(now_timestamp=120, window_seconds=60)
    assert bucket3 == 2  # 120 // 60
    assert retry3 == 60  # (3 * 60) - 120
