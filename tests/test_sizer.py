from signal_to_ticket.sizer import kelly_size, compute_shares


def test_zero_position_when_no_edge():
    result = kelly_size(p_win=0.30, expected_return=0.05, hv20=0.25)
    assert result["position_value"] == 0.0
    assert result["kelly_fraction"] == 0.0


def test_zero_position_when_negative_expected_return():
    result = kelly_size(p_win=0.70, expected_return=-0.02, hv20=0.25)
    assert result["position_value"] == 0.0


def test_half_kelly_math():
    # p=0.6, b=0.10 -> full kelly = (0.6*0.10 - 0.4) / 0.10 = -3.4 -> clamped to 0
    result = kelly_size(p_win=0.60, expected_return=0.10, hv20=0.20)
    assert result["kelly_fraction"] == 0.0

    # p=0.8, b=0.50 -> full kelly = (0.8*0.5 - 0.2) / 0.5 = 0.4 -> half = 0.2
    result = kelly_size(p_win=0.80, expected_return=0.50, hv20=0.20)
    assert abs(result["kelly_fraction"] - 0.2) < 1e-9


def test_max_position_cap():
    result = kelly_size(
        p_win=0.90, expected_return=0.80, hv20=0.10,
        portfolio_value=10_000_000, max_position=500_000,
    )
    assert result["position_value"] == 500_000


def test_vol_scalar_bounds():
    # Very high vol -> scalar floors at 0.4
    high_vol = kelly_size(p_win=0.80, expected_return=0.50, hv20=1.0)
    assert high_vol["vol_scalar"] == 0.4

    # Low vol -> scalar caps at 1.0 (never sizes up)
    low_vol = kelly_size(p_win=0.80, expected_return=0.50, hv20=0.05)
    assert low_vol["vol_scalar"] == 1.0


def test_compute_shares():
    assert compute_shares(10_000, 100.0) == 100
    assert compute_shares(10_050, 100.0) == 100  # floors, never rounds up
    assert compute_shares(10_000, 0) == 0
    assert compute_shares(10_000, -5) == 0
