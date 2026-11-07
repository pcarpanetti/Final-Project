"""Deterministic risk calculations. No agent ever computes a number; they all come from here."""
from __future__ import annotations

import math

import numpy as np

Z99 = 2.3263478740


def weighted_quantile(values: np.ndarray, alpha: float, obs_weights: np.ndarray | None = None) -> float:
    """Smallest x with F(x) >= alpha. With equal weights this is the ceil(n*alpha)-th order statistic."""
    order = np.argsort(values, kind="stable")
    sorted_vals = values[order]
    w = np.full(len(values), 1.0 / len(values)) if obs_weights is None else obs_weights[order] / obs_weights.sum()
    # The tolerance stops 5 * (1/500) landing a hair under 0.01 and moving one order statistic.
    idx = int(np.searchsorted(np.cumsum(w), alpha - 1e-12, side="left"))
    return float(sorted_vals[min(idx, len(values) - 1)])


def age_weights(n: int, decay: float) -> np.ndarray:
    """Boudoukh-Richardson-Whitelaw weights for observations ordered oldest to newest."""
    w = decay ** np.arange(n - 1, -1, -1, dtype=float)
    return w / w.sum()


def value_at_risk(pnl: np.ndarray, conf: float, obs_weights: np.ndarray | None = None) -> float:
    return -weighted_quantile(pnl, 1.0 - conf, obs_weights)


def expected_shortfall(pnl: np.ndarray, conf: float, obs_weights: np.ndarray | None = None) -> float:
    cut = weighted_quantile(pnl, 1.0 - conf, obs_weights)
    tail = pnl <= cut
    if obs_weights is None:
        return float(-pnl[tail].mean())
    return float(-(pnl[tail] * obs_weights[tail]).sum() / obs_weights[tail].sum())


def ewma_cov(returns: np.ndarray, lam: float) -> np.ndarray:
    w = age_weights(len(returns), lam)
    return (returns * w[:, None]).T @ returns


def obs_weights_for(n: int, var_cfg: dict) -> np.ndarray | None:
    if var_cfg["method"] == "historical":
        return None
    if var_cfg["method"] == "age_weighted":
        return age_weights(n, var_cfg["age_decay"])
    raise ValueError(f"unknown VaR method {var_cfg['method']!r}")


def factor_betas(pnl: np.ndarray, factors: dict[str, np.ndarray]) -> dict[str, float]:
    names = list(factors)
    x = np.column_stack([np.ones(len(pnl))] + [factors[n] for n in names])
    coef, *_ = np.linalg.lstsq(x, pnl, rcond=None)
    return dict(zip(names, (float(c) for c in coef[1:])))


def compute_metrics(
    assets: list[str],
    returns: np.ndarray,
    weights: np.ndarray,
    prev_weights: np.ndarray | None,
    factors: dict[str, np.ndarray],
    nav_series: np.ndarray,
    risk_cfg: dict,
) -> dict[str, dict]:
    """Return {metric_id: {value, unit, label}}. `returns` is T x N, oldest row first."""
    var_cfg = risk_cfg["var"]
    pnl = returns[-var_cfg["lookback_days"]:] @ weights
    ow = obs_weights_for(len(pnl), var_cfg)
    nav = float(nav_series[-1])
    metrics: dict[str, dict] = {}

    def put(mid: str, value, unit: str, label: str) -> None:
        metrics[mid] = {"value": value, "unit": unit, "label": label}

    put("nav_usd", nav, "usd", "Net asset value")
    daily = float(returns[-1] @ (weights if prev_weights is None else prev_weights))
    put("daily_return", daily, "pct", "Portfolio return on the day")

    put("var99_1d", value_at_risk(pnl, 0.99, ow), "pct", "1-day 99% VaR")
    put("var95_1d", value_at_risk(pnl, 0.95, ow), "pct", "1-day 95% VaR")
    put("es975_1d", expected_shortfall(pnl, 0.975, ow), "pct", "1-day 97.5% expected shortfall")

    cov = ewma_cov(returns[-risk_cfg["ewma_window"]:], risk_cfg["ewma_lambda"])
    port_var = float(weights @ cov @ weights)
    vol_daily = math.sqrt(port_var)
    put("vol_ann_ewma", vol_daily * math.sqrt(252), "pct", "Annualised EWMA volatility")
    put("var99_param", Z99 * vol_daily, "pct", "1-day 99% parametric VaR (EWMA, normal)")

    contrib = weights * (cov @ weights) / port_var
    top = int(np.argmax(contrib))
    put("top_risk_contrib", float(contrib[top]), "pct", "Largest share of portfolio variance")
    put("top_risk_asset", assets[top], "text", "Sleeve with largest variance share")
    for asset, share in zip(assets, contrib):
        put(f"ctr_{asset}", float(share), "pct", f"Variance share of {asset}")
    for asset, w in zip(assets, weights):
        put(f"w_{asset}", float(w), "pct", f"Weight of {asset}")

    i_max = int(np.argmax(weights))
    put("weight_max", float(weights[i_max]), "pct", "Largest sleeve weight")
    put("weight_max_asset", assets[i_max], "text", "Largest sleeve")
    put("top3_weight", float(np.sort(weights)[-3:].sum()), "pct", "Top three sleeve weights")
    put("effective_n", float(1.0 / (weights ** 2).sum()), "ratio", "Effective number of sleeves")

    beta_n = risk_cfg["beta_window"]
    betas = factor_betas(returns[-beta_n:] @ weights, {k: v[-beta_n:] for k, v in factors.items()})
    for name, beta in betas.items():
        put(f"beta_{name}", beta, "ratio", f"Beta to {name}")

    put("drawdown", 1.0 - nav / float(np.max(nav_series)), "pct", "Drawdown from NAV peak")

    worst_name, worst_loss = "", -math.inf
    for name, shocks in risk_cfg["stress"].items():
        loss = -float(sum(w * shocks[a] for a, w in zip(assets, weights)))
        put(f"stress_{name}", loss, "pct", f"Loss under {name.replace('_', ' ')} scenario")
        if loss > worst_loss:
            worst_name, worst_loss = name, loss
    put("stress_worst", worst_loss, "pct", "Worst stress scenario loss")
    put("stress_worst_name", worst_name.replace("_", " "), "text", "Worst stress scenario")

    liq = risk_cfg["liquidity"]
    days = [w * nav / (liq["adv_usd"][a] * liq["participation"]) for a, w in zip(assets, weights)]
    put("liq_days_max", float(max(days)), "days", "Days to liquidate the slowest sleeve")

    if prev_weights is not None and len(returns) > var_cfg["lookback_days"]:
        old_pnl_window = returns[-var_cfg["lookback_days"] - 1:-1]
        old_ow = obs_weights_for(len(old_pnl_window), var_cfg)
        v_old = value_at_risk(old_pnl_window @ prev_weights, 0.99, old_ow)
        v_mid = value_at_risk(old_pnl_window @ weights, 0.99, old_ow)
        v_new = metrics["var99_1d"]["value"]
        put("var99_change", v_new - v_old, "pct", "Change in VaR since the prior day")
        put("var99_change_positions", v_mid - v_old, "pct", "VaR change from position moves")
        put("var99_change_window", v_new - v_mid, "pct", "VaR change from the market data window")
    return metrics
