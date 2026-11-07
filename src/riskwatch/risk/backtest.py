"""VaR backtests: Kupiec coverage, Christoffersen independence, Basel traffic light."""
from __future__ import annotations

import math


def chi2_sf_1df(x: float) -> float:
    return math.erfc(math.sqrt(max(x, 0.0) / 2.0))


def _xlogy(x: float, y: float) -> float:
    return 0.0 if x == 0 else x * math.log(y)


def kupiec_pof(exceptions: int, n: int, p: float) -> dict:
    if n == 0:
        return {"lr": 0.0, "p_value": 1.0}
    phat = exceptions / n
    ll_null = _xlogy(n - exceptions, 1 - p) + _xlogy(exceptions, p)
    ll_alt = _xlogy(n - exceptions, 1 - phat) + _xlogy(exceptions, phat)
    lr = max(-2.0 * (ll_null - ll_alt), 0.0)
    return {"lr": lr, "p_value": chi2_sf_1df(lr)}


def christoffersen_independence(hits: list[int]) -> dict:
    n00 = n01 = n10 = n11 = 0
    for a, b in zip(hits, hits[1:]):
        if a == 0:
            n00, n01 = n00 + (b == 0), n01 + (b == 1)
        else:
            n10, n11 = n10 + (b == 0), n11 + (b == 1)
    if n01 + n11 == 0 or n00 + n01 == 0 or n10 + n11 == 0:
        return {"lr": 0.0, "p_value": 1.0}
    p01, p11 = n01 / (n00 + n01), n11 / (n10 + n11)
    p = (n01 + n11) / (n00 + n01 + n10 + n11)
    ll_null = _xlogy(n00 + n10, 1 - p) + _xlogy(n01 + n11, p)
    ll_alt = _xlogy(n00, 1 - p01) + _xlogy(n01, p01) + _xlogy(n10, 1 - p11) + _xlogy(n11, p11)
    lr = max(-2.0 * (ll_null - ll_alt), 0.0)
    return {"lr": lr, "p_value": chi2_sf_1df(lr)}


def basel_zone(exceptions_250: int) -> str:
    if exceptions_250 <= 4:
        return "green"
    return "yellow" if exceptions_250 <= 9 else "red"


def summarise(hits: list[int], p: float = 0.01) -> dict:
    """`hits` are 0/1 exceedances, oldest first; a day is scored only once its outcome is published."""
    recent = hits[-250:]
    exceptions = sum(recent)
    return {
        "observations": len(recent),
        "exceptions": exceptions,
        "expected": len(recent) * p,
        "kupiec": kupiec_pof(exceptions, len(recent), p),
        "independence": christoffersen_independence(recent),
        "zone": basel_zone(exceptions),
    }
