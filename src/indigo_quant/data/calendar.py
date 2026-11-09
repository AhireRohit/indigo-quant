"""
NSE Exchange Trading Calendar and Market Session Utilities.
Accurately models Indian market sessions, weekends, published official holidays,
and Asia/Kolkata timezone normalization.
"""

from __future__ import annotations

import datetime
from typing import List, Set

import pytz

IST = pytz.timezone("Asia/Kolkata")

# NSE Official Trading Holidays (Equities Segment)
# Sourced from NSE official trading calendar circulars for 2024, 2025, and 2026
NSE_HOLIDAYS: Set[datetime.date] = {
    # 2024 Holidays
    datetime.date(2024, 1, 22),  # Special Holiday (Ayodhya Ram Mandir Pran Pratishtha)
    datetime.date(2024, 1, 26),  # Republic Day
    datetime.date(2024, 3, 8),   # Mahashivratri
    datetime.date(2024, 3, 25),  # Holi
    datetime.date(2024, 3, 29),  # Good Friday
    datetime.date(2024, 4, 11),  # Id-Ul-Fitr (Ramzan Id)
    datetime.date(2024, 4, 17),  # Shri Ram Navami
    datetime.date(2024, 5, 1),   # Maharashtra Day
    datetime.date(2024, 5, 20),  # General Elections (Mumbai constituency)
    datetime.date(2024, 6, 17),  # Bakri Id / Eid ul-Adha
    datetime.date(2024, 7, 17),  # Moharram
    datetime.date(2024, 8, 15),  # Independence Day
    datetime.date(2024, 10, 2),  # Mahatma Gandhi Jayanti
    datetime.date(2024, 11, 1),  # Diwali Laxmi Pujan (Muhurat trading evening only)
    datetime.date(2024, 11, 15), # Gurunanak Jayanti
    datetime.date(2024, 11, 20), # Maharashtra Assembly Elections
    datetime.date(2024, 12, 25), # Christmas

    # 2025 Holidays
    datetime.date(2025, 2, 26),  # Mahashivratri
    datetime.date(2025, 3, 14),  # Holi
    datetime.date(2025, 3, 31),  # Id-Ul-Fitr
    datetime.date(2025, 4, 10),  # Mahavir Jayanti
    datetime.date(2025, 4, 14),  # Dr. Baba Saheb Ambedkar Jayanti
    datetime.date(2025, 4, 18),  # Good Friday
    datetime.date(2025, 5, 1),   # Maharashtra Day
    datetime.date(2025, 6, 7),   # Bakri Id
    datetime.date(2025, 8, 15),  # Independence Day
    datetime.date(2025, 8, 27),  # Ganesh Chaturthi
    datetime.date(2025, 10, 2),  # Mahatma Gandhi Jayanti / Dussehra
    datetime.date(2025, 10, 21), # Diwali Laxmi Pujan (Muhurat session only)
    datetime.date(2025, 10, 22), # Diwali Balipratipada
    datetime.date(2025, 11, 5),  # Gurunanak Jayanti
    datetime.date(2025, 12, 25), # Christmas

    # 2026 Holidays
    datetime.date(2026, 1, 26),  # Republic Day
    datetime.date(2026, 2, 16),  # Mahashivratri
    datetime.date(2026, 3, 4),   # Holi
    datetime.date(2026, 3, 20),  # Id-Ul-Fitr
    datetime.date(2026, 4, 3),   # Good Friday
    datetime.date(2026, 4, 14),  # Dr. Baba Saheb Ambedkar Jayanti
    datetime.date(2026, 5, 1),   # Maharashtra Day
    datetime.date(2026, 5, 27),  # Bakri Id
    datetime.date(2026, 6, 26),  # Muharram
    datetime.date(2026, 8, 15),  # Independence Day (Saturday)
    datetime.date(2026, 9, 14),  # Ganesh Chaturthi
    datetime.date(2026, 10, 2),  # Mahatma Gandhi Jayanti
    datetime.date(2026, 10, 20), # Dussehra
    datetime.date(2026, 11, 8),  # Diwali (Sunday)
    datetime.date(2026, 11, 9),  # Diwali Balipratipada
    datetime.date(2026, 11, 24), # Gurunanak Jayanti
    datetime.date(2026, 12, 25), # Christmas
}


def now_ist() -> datetime.datetime:
    """Current timestamp localized to Asia/Kolkata."""
    return datetime.datetime.now(IST)


def is_trading_day(d: datetime.date) -> bool:
    """Return True if the date is a regular Monday-Friday trading day (not weekend or holiday)."""
    if d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False
    if d in NSE_HOLIDAYS:
        return False
    return True


def is_market_open(dt: datetime.datetime | None = None) -> bool:
    """
    Check if the Indian equity market is currently within regular trading hours:
    09:15 to 15:30 IST on a valid trading day.
    """
    if dt is None:
        dt = now_ist()
    elif dt.tzinfo is None:
        dt = IST.localize(dt)
    else:
        dt = dt.astimezone(IST)

    d = dt.date()
    if not is_trading_day(d):
        return False

    current_time = dt.time()
    market_open = datetime.time(9, 15)
    market_close = datetime.time(15, 30)

    return market_open <= current_time <= market_close


def is_eod_data_ready(dt: datetime.datetime | None = None, ready_hour: int = 18, ready_minute: int = 30) -> bool:
    """
    Check if the expected End-of-Day data publication time has passed.
    Default: 18:30 IST on trading days.
    """
    if dt is None:
        dt = now_ist()
    elif dt.tzinfo is None:
        dt = IST.localize(dt)
    else:
        dt = dt.astimezone(IST)

    d = dt.date()
    if not is_trading_day(d):
        # On weekends/holidays, previous completed session's data is already final
        return True

    eod_ready_time = datetime.time(ready_hour, ready_minute)
    return dt.time() >= eod_ready_time


def get_latest_completed_trading_day(ref_dt: datetime.datetime | None = None) -> datetime.date:
    """
    Return the date of the most recent completed trading session.
    If today is a trading day and it's before 18:30 IST, returns yesterday's (or prior) session.
    """
    if ref_dt is None:
        ref_dt = now_ist()
    elif ref_dt.tzinfo is None:
        ref_dt = IST.localize(ref_dt)
    else:
        ref_dt = ref_dt.astimezone(IST)

    today = ref_dt.date()
    if is_trading_day(today) and is_eod_data_ready(ref_dt):
        return today

    # Otherwise, step backward to find prior trading day
    candidate = today - datetime.timedelta(days=1)
    while not is_trading_day(candidate):
        candidate -= datetime.timedelta(days=1)
    return candidate


def get_previous_trading_day(d: datetime.date) -> datetime.date:
    """Get the trading day strictly prior to d."""
    candidate = d - datetime.timedelta(days=1)
    while not is_trading_day(candidate):
        candidate -= datetime.timedelta(days=1)
    return candidate


def get_next_trading_day(d: datetime.date) -> datetime.date:
    """Get the next trading day strictly after d."""
    candidate = d + datetime.timedelta(days=1)
    while not is_trading_day(candidate):
        candidate += datetime.timedelta(days=1)
    return candidate


def get_trading_days_between(start_date: datetime.date, end_date: datetime.date) -> List[datetime.date]:
    """Return all valid trading days in [start_date, end_date] inclusive."""
    days = []
    curr = start_date
    while curr <= end_date:
        if is_trading_day(curr):
            days.append(curr)
        curr += datetime.timedelta(days=1)
    return days
