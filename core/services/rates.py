"""Rate-based payout calculations (KK) for DEF and CAST activity."""
import logging
from datetime import time
from decimal import Decimal

from core.models import CastRate, Rate

logger = logging.getLogger(__name__)

DAY_MINUTES = Decimal("1440")


def rate_at(t: time):
    """Return the KK rate active at time t, or None if no Rate covers it.

    A rate interval [start_time, end_time] is INCLUSIVE of end_time and wraps
    past midnight when end_time <= start_time.
    """
    minute = Decimal(t.hour * 60 + t.minute)
    for rate in Rate.objects.filter(active=True):
        start = Decimal(rate.start_time.hour * 60 + rate.start_time.minute)
        end = Decimal(rate.end_time.hour * 60 + rate.end_time.minute)
        if end <= start:
            if minute >= start or minute <= end:
                return rate.rate_kk
        elif start <= minute <= end:
            return rate.rate_kk
    return None


def _payment_from_rates(rates, wave_start: time, duration_hours: Decimal) -> Decimal:
    """Compute the prorated payout in KK over the given active rate rows."""
    pieces = []
    for rate in rates:
        start = Decimal(rate.start_time.hour * 60 + rate.start_time.minute)
        end = Decimal(rate.end_time.hour * 60 + rate.end_time.minute)
        if end <= start:
            pieces.append((start, DAY_MINUTES - 1, rate.rate_kk))
            pieces.append((Decimal("0"), end, rate.rate_kk))
        else:
            pieces.append((start, end, rate.rate_kk))

    wave_min = Decimal(wave_start.hour * 60 + wave_start.minute)
    duration_min = duration_hours * 60
    last = wave_min + duration_min - 1

    if last < DAY_MINUTES:
        intervals = [(wave_min, last)]
    else:
        intervals = [(wave_min, DAY_MINUTES - 1), (Decimal("0"), last - DAY_MINUTES)]

    total_kk = Decimal("0")
    covered_minutes = Decimal("0")
    for ss, ee in intervals:
        for rs, re, rate_kk in pieces:
            overlap = max(Decimal("0"), min(ee, re) - max(ss, rs) + 1)
            covered_minutes += overlap
            total_kk += overlap * rate_kk / 60

    if covered_minutes < duration_min:
        logger.warning(
            "Rate gap for wave_start=%s duration_hours=%s "
            "covered_minutes=%s total_minutes=%s",
            wave_start,
            duration_hours,
            covered_minutes,
            duration_min,
        )

    return total_kk.quantize(Decimal("0.01"))


def payment_kk(wave_start: time, duration_hours: Decimal) -> Decimal:
    """Compute the prorated payout in KK for a DEF wave (inclusive intervals)."""
    return _payment_from_rates(
        Rate.objects.filter(active=True),
        wave_start,
        duration_hours,
    )


def payment_cast_kk(wave_start: time, duration_hours: Decimal) -> Decimal:
    """Compute the prorated payout in KK for a CAST wave.

    Reads strictly from CastRate; there is no fallback to the DEF Rate
    table. The no-rate behavior mirrors :func:`payment_kk`.
    """
    return _payment_from_rates(
        CastRate.objects.filter(active=True),
        wave_start,
        duration_hours,
    )
