"""
XIRR Solver
===========
Pure-Python XIRR (Excel-compatible extended internal rate of return) with
no external numerical dependencies.

Definition
----------
Given a series of dated cashflows (negative = money out of investor's
pocket, positive = money back to investor), XIRR is the annualised rate r
that satisfies:

    sum( CF_i / (1 + r) ** ((date_i - date_0) / 365) ) == 0

Algorithm: Newton-Raphson with a bisection fallback (bounded to
-99% .. +1000% annualised) so a bad initial guess never raises or hangs.
"""

from datetime import date
from typing import List, Optional, Sequence, Tuple

Cashflow = Tuple[date, float]

_MAX_NEWTON_ITER = 100
_MAX_BISECT_ITER = 200
_LOW_RATE_BOUND = -0.999
_HIGH_RATE_BOUND = 10.0
_TOLERANCE = 1e-6


def _xnpv(rate: float, cashflows: Sequence[Cashflow]) -> float:
    t0 = cashflows[0][0]
    return sum(
        cf / (1.0 + rate) ** ((d - t0).days / 365.0)
        for d, cf in cashflows
    )


def _xnpv_derivative(rate: float, cashflows: Sequence[Cashflow]) -> float:
    t0 = cashflows[0][0]
    total = 0.0
    for d, cf in cashflows:
        t = (d - t0).days / 365.0
        if t == 0:
            continue
        total += -t * cf / (1.0 + rate) ** (t + 1)
    return total


def _bisect(cashflows: Sequence[Cashflow]) -> Optional[float]:
    lo, hi = _LOW_RATE_BOUND, _HIGH_RATE_BOUND
    f_lo = _xnpv(lo, cashflows)
    f_hi = _xnpv(hi, cashflows)
    if abs(f_lo) < _TOLERANCE:
        return lo
    if abs(f_hi) < _TOLERANCE:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        return None  # no sign change across the bracket: cannot solve

    for _ in range(_MAX_BISECT_ITER):
        mid = (lo + hi) / 2
        f_mid = _xnpv(mid, cashflows)
        if abs(f_mid) < _TOLERANCE:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def xirr(cashflows: List[Cashflow], guess: float = 0.1) -> Optional[float]:
    """
    Solve for XIRR given [(date, amount), ...].

    Returns the annualised rate as a decimal (0.12 == 12%), or None if the
    cashflows cannot produce a solvable rate (fewer than 2 points, all
    same sign, or no convergence).
    """
    if len(cashflows) < 2:
        return None

    ordered = sorted(cashflows, key=lambda x: x[0])
    amounts = [cf for _, cf in ordered]
    if not (any(a > 0 for a in amounts) and any(a < 0 for a in amounts)):
        return None

    rate = guess
    for _ in range(_MAX_NEWTON_ITER):
        f = _xnpv(rate, ordered)
        df = _xnpv_derivative(rate, ordered)
        if df == 0:
            rate = None
            break
        new_rate = rate - f / df
        if new_rate <= _LOW_RATE_BOUND:
            new_rate = (rate + _LOW_RATE_BOUND) / 2
        if abs(new_rate - rate) < 1e-9:
            rate = new_rate
            break
        rate = new_rate
    else:
        rate = None

    if rate is not None and abs(_xnpv(rate, ordered)) < 1e-3:
        return rate

    return _bisect(ordered)
