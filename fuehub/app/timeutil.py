from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

"""Every DateTime column in this app is naive and stored as UTC by
convention (everything is written with dt.datetime.utcnow()). This is the
one place that gets converted to a clinic's local timezone for display --
service/scoring/scheduling logic should keep comparing naive UTC values
directly rather than converting back and forth.
"""


def to_clinic_local(value: dt.datetime, timezone: str) -> dt.datetime:
    aware_utc = value.replace(tzinfo=ZoneInfo("UTC"))
    try:
        return aware_utc.astimezone(ZoneInfo(timezone))
    except Exception:
        return aware_utc


def from_clinic_local(naive_local: dt.datetime, timezone: str) -> dt.datetime:
    """Inverse of to_clinic_local -- interprets a naive datetime (e.g. from
    a staff-facing <input type=datetime-local>) as clinic-local time and
    returns the naive-UTC value to store."""
    aware_local = naive_local.replace(tzinfo=ZoneInfo(timezone))
    return aware_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
