import math

import numpy as np
import pytest

from riskwatch.risk import backtest
from riskwatch.risk.engine import (
    age_weights,
    compute_metrics,
    expected_shortfall,
    value_at_risk,
    weighted_quantile,
)
from riskwatch.risk.limits import evaluate_limits


def test_quantile_is_the_ceil_n_alpha_order_statistic():
    values = np.arange(1.0, 501.0)
    assert weighted_quantile(values, 0.01) == 5.0
    assert weighted_quantile(values, 0.05) == 25.0


def test_var_and_es_on_a_known_loss_ladder():
    pnl = -np.arange(1.0, 101.0) / 100.0
    # n * alpha = 1, so the 99% quantile is the single worst observation.
    assert value_at_risk(pnl, 0.99) == pytest.approx(1.00)
    assert value_at_risk(pnl, 0.98) == pytest.approx(0.99)
    assert expected_shortfall(pnl, 0.98) == pytest.approx((1.00 + 0.99) / 2)


def test_age_weighting_reacts_to_recent_losses_more_than_equal_weighting():
    pnl = np.r_[np.full(490, 0.001), np.full(10, -0.05)]
    assert value_at_risk(pnl, 0.99, age_weights(500, 0.97)) >= value_at_risk(pnl, 0.99)
    calm_then_old_shock = pnl[::-1].copy()
    assert value_at_risk(calm_then_old_shock, 0.99, age_weights(500, 0.97)) < 0.0


def _toy_inputs():
    rng = np.random.default_rng(7)
    assets = ["A", "B", "C"]
    returns = rng.normal(0, 0.01, (600, 3))
    factors = {"MktRF": rng.normal(0, 0.01, 600)}
    cfg = {
        "var": {"method": "historical", "lookback_days": 500, "age_decay": 0.99},
        "ewma_lambda": 0.94,
        "ewma_window": 250,
        "beta_window": 250,
        "stress": {"down": {"A": -0.1, "B": -0.2, "C": -0.3}},
        "liquidity": {"participation": 0.1, "adv_usd": {"A": 1e6, "B": 2e6, "C": 4e6}},
    }
    return assets, returns, factors, cfg


def test_metrics_are_consistent():
    assets, returns, factors, cfg = _toy_inputs()
    w = np.array([0.5, 0.3, 0.2])
    m = compute_metrics(assets, returns, w, w, factors, np.array([100.0, 120.0, 90.0]), cfg)
    assert m["weight_max"]["value"] == 0.5 and m["weight_max_asset"]["value"] == "A"
    assert m["drawdown"]["value"] == pytest.approx(0.25)
    assert m["stress_down"]["value"] == pytest.approx(0.05 + 0.06 + 0.06)
    assert sum(m[f"ctr_{a}"]["value"] for a in assets) == pytest.approx(1.0)
    assert m["var99_change"]["value"] == pytest.approx(
        m["var99_change_positions"]["value"] + m["var99_change_window"]["value"]
    )


def test_future_rows_cannot_change_the_answer_when_sliced_at_the_cutoff():
    assets, returns, factors, cfg = _toy_inputs()
    w = np.array([0.5, 0.3, 0.2])
    nav = np.array([100.0])
    base = compute_metrics(assets, returns[:550], w, w, {"MktRF": factors["MktRF"][:550]}, nav, cfg)
    tampered = returns.copy()
    tampered[550:] = 9.99
    again = compute_metrics(assets, tampered[:550], w, w, {"MktRF": factors["MktRF"][:550]}, nav, cfg)
    assert base == again


def test_limit_statuses():
    metrics = {"x": {"value": 0.05}, "y": {"value": 0.03}, "z": {"value": 0.01}}
    limits = [
        {"id": "lx", "metric": "x", "label": "x", "warn": 0.03, "hard": 0.05},
        {"id": "ly", "metric": "y", "label": "y", "warn": 0.03, "hard": 0.05},
        {"id": "lz", "metric": "z", "label": "z", "warn": 0.03, "hard": 0.05},
    ]
    assert [r["status"] for r in evaluate_limits(metrics, limits)] == ["breach", "warning", "ok"]


def test_kupiec_matches_hand_calculation():
    # 10 exceptions in 250 at p=0.01: the textbook LR is about 12.96.
    out = backtest.kupiec_pof(10, 250, 0.01)
    expected = -2 * (240 * math.log(0.99) + 10 * math.log(0.01)
                     - 240 * math.log(0.96) - 10 * math.log(0.04))
    assert out["lr"] == pytest.approx(expected)
    assert out["p_value"] < 0.01


def test_basel_zones_and_clustered_hits_fail_independence():
    assert [backtest.basel_zone(n) for n in (4, 5, 9, 10)] == ["green", "yellow", "yellow", "red"]
    clustered = [0] * 100 + [1] * 6 + [0] * 100
    spread = ([0] * 33 + [1]) * 6
    assert backtest.christoffersen_independence(clustered)["p_value"] < 0.01
    assert backtest.christoffersen_independence(spread)["p_value"] > 0.05
