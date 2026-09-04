"""Hermetic tests for the broker-true risk aggregation (risk_book)."""
import sys
sys.path.insert(0, "agent")
from risk_book import build_risk_metrics, black_scholes_greeks


def _pos(symbol, qty, price, mval=None, side="buy"):
    return {"symbol": symbol, "qty": qty, "current_price": price,
            "market_value": mval if mval is not None else abs(price * qty),
            "side": side}


def test_equity_only():
    r = build_risk_metrics([_pos("SPY", 5, 762.0)], 10000)
    assert r["gross_exposure"] == 3810
    assert r["net_exposure"] == 3810
    assert r["n_positions"] == 1
    assert r["concentration"][0]["ticker"] == "SPY"
    assert r["exposure_source"] == "broker_book"


def test_long_short_spread_offsets():
    """Long 10x AAPL 330C + short 10x AAPL 332.5C."""
    r = build_risk_metrics([
        _pos("AAPL260904C00330000", 10, 1.29, 1290.0, "buy"),
        _pos("AAPL260904C00332500", -10, 0.72, 720.0, "sell"),
    ], 100000)
    assert r["gross_exposure"] == 2010.0
    assert r["net_exposure"] == 1290.0 - 720.0
    assert r["n_positions"] == 2
    assert len(r["option_book"]) == 2
    # both legs group under AAPL concentration
    aapl = [c for c in r["concentration"] if c["ticker"] == "AAPL"][0]
    assert aapl["mkt_val"] == 2010.0


def test_crypto_leg():
    r = build_risk_metrics([_pos("BTCUSD", 0.0005985, 81051.0, 48.51)], 100000)
    assert r["gross_exposure"] == 48.51
    assert r["option_book"] == []
    assert r["concentration"][0]["ticker"] == "BTCUSD"


def test_bs_greeks_delta_bounds():
    # Deep ITM call delta near 1, OTM near 0; put mirrors negative.
    call_itm = black_scholes_greeks(100, 50, 30 / 365, 0.3)["delta"]
    call_otm = black_scholes_greeks(100, 150, 30 / 365, 0.3)["delta"]
    put_otm = black_scholes_greeks(100, 50, 30 / 365, 0.3, right="P")["delta"]
    put_itm = black_scholes_greeks(100, 150, 30 / 365, 0.3, right="P")["delta"]
    assert 0.90 < call_itm <= 1.0
    assert 0.0 < call_otm < 0.30
    assert -0.20 < put_otm < 0.0
    assert -1.0 < put_itm < -0.90


def test_zero_safe():
    r = build_risk_metrics([], 0)
    assert r["gross_exposure"] == 0 and r["n_positions"] == 0
    g = black_scholes_greeks(0, 0, 0, 0)
    assert all(v == 0.0 for v in g.values())
