"""Position sizer: Kelly criterion + vol-scaling. Reuses HV20 logic from Week 4."""
import math
import yfinance as yf
from .config import PORTFOLIO_VALUE, MAX_POSITION_VALUE


def get_hv20(ticker: str) -> float:
    data = yf.download(ticker, period="3mo", progress=False, auto_adjust=True)["Close"].squeeze()
    hv20 = data.pct_change().rolling(window=20).std() * math.sqrt(252)
    val = float(hv20.iloc[-1])
    return val if not math.isnan(val) else 0.25


def get_current_price(ticker: str) -> float:
    data = yf.download(ticker, period="5d", progress=False, auto_adjust=True)["Close"].squeeze()
    return float(data.dropna().iloc[-1])


def kelly_size(
    p_win: float,
    expected_return: float,
    hv20: float,
    portfolio_value: float = PORTFOLIO_VALUE,
    max_position: float = MAX_POSITION_VALUE,
) -> dict:
    """
    Half-Kelly with vol-scaling.
    f* = (p*b - q) / b  where b = expected_return (edge per unit risked)
    Vol scalar shrinks size when realized vol exceeds 20% baseline.
    """
    if expected_return <= 0 or p_win <= 0.35:
        return {
            "kelly_fraction": 0.0,
            "vol_scalar": 1.0,
            "position_value": 0.0,
            "hv20": hv20,
            "reason": "Insufficient edge (p_win < 35% or non-positive expected return)",
        }

    b = expected_return
    q = 1.0 - p_win
    full_kelly = max(0.0, (p_win * b - q) / b)
    half_kelly = full_kelly * 0.5  # standard half-Kelly to reduce variance

    vol_scalar = max(0.4, min(1.0, 0.20 / hv20)) if hv20 > 0 else 1.0
    raw = half_kelly * vol_scalar * portfolio_value
    position_value = min(raw, max_position)

    return {
        "kelly_fraction": round(half_kelly, 4),
        "vol_scalar": round(vol_scalar, 4),
        "position_value": round(position_value, 2),
        "hv20": round(hv20, 4),
    }


def compute_shares(position_value: float, price: float) -> int:
    if price <= 0:
        return 0
    return int(position_value // price)
