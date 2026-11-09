"""
NSE Exchange Trading Calendar and Market Session Utilities.
Accurately models Indian market sessions, weekends, published official holidays,
special Diwali Muhurat trading sessions, and Asia/Kolkata timezone normalization.
"""

from __future__ import annotations

import datetime
from typing import List, Set

import pytz

IST = pytz.timezone("Asia/Kolkata")

# NSE Official Trading Holidays (Equities Segment)
# Sourced from official National Stock Exchange of India (NSE) circulars for 2024, 2025, and 2026.
NSE_HOLIDAYS: Set[datetime.date] = {
    # 2024 Holidays
    datetime.date(2024, 1, 22),  # Special Holiday (Ayodhya Ram Mandir Pran Pratishtha)
    datetime.date(2024, 1, 26),  # Republic Day (Friday)
    datetime.date(2024, 3, 8),   # Mahashivratri (Friday)
    datetime.date(2024, 3, 25),  # Holi (Monday)
    datetime.date(2024, 3, 29),  # Good Friday (Friday)
    datetime.date(2024, 4, 11),  # Id-Ul-Fitr (Ramzan Id, Thursday)
    datetime.date(2024, 4, 17),  # Shri Ram Navami (Wednesday)
    datetime.date(2024, 5, 1),   # Maharashtra Day (Wednesday)
    datetime.date(2024, 5, 20),  # General Elections - Mumbai constituency (Monday)
    datetime.date(2024, 6, 17),  # Bakri Id / Eid ul-Adha (Monday)
    datetime.date(2024, 7, 17),  # Moharram (Wednesday)
    datetime.date(2024, 8, 15),  # Independence Day (Thursday)
    datetime.date(2024, 10, 2),  # Mahatma Gandhi Jayanti (Wednesday)
    datetime.date(2024, 11, 1),  # Diwali Laxmi Pujan (Evening Muhurat session only)
    datetime.date(2024, 11, 15), # Gurunanak Jayanti (Friday)
    datetime.date(2024, 11, 20), # Maharashtra Assembly Elections (Wednesday)
    datetime.date(2024, 12, 25), # Christmas (Wednesday)

    # 2025 Holidays
    datetime.date(2025, 2, 26),  # Mahashivratri (Wednesday)
    datetime.date(2025, 3, 14),  # Holi (Friday)
    datetime.date(2025, 3, 31),  # Id-Ul-Fitr (Monday)
    datetime.date(2025, 4, 10),  # Shri Mahavir Jayanti (Thursday)
    datetime.date(2025, 4, 14),  # Dr. Baba Saheb Ambedkar Jayanti (Monday)
    datetime.date(2025, 4, 18),  # Good Friday (Friday)
    datetime.date(2025, 5, 1),   # Maharashtra Day (Thursday)
    datetime.date(2025, 6, 7),   # Bakri Id (Saturday - exchange closed)
    datetime.date(2025, 8, 15),  # Independence Day (Friday)
    datetime.date(2025, 8, 27),  # Ganesh Chaturthi (Wednesday)
    datetime.date(2025, 10, 2),  # Mahatma Gandhi Jayanti / Dussehra (Thursday)
    datetime.date(2025, 10, 21), # Diwali Laxmi Pujan (Evening Muhurat session only)
    datetime.date(2025, 10, 22), # Diwali Balipratipada (Wednesday)
    datetime.date(2025, 11, 5),  # Gurunanak Jayanti (Wednesday)
    datetime.date(2025, 12, 25), # Christmas (Thursday)

    # 2026 Official NSE Trading Holidays (Equities Segment)
    # Validated against official circular / exchange schedule:
    datetime.date(2026, 1, 26),  # Republic Day (Monday)
    datetime.date(2026, 2, 15),  # Mahashivratri (Sunday - exchange closed)
    datetime.date(2026, 3, 3),   # Holi (Tuesday)
    datetime.date(2026, 3, 21),  # Id-Ul-Fitr (Saturday - exchange closed)
    datetime.date(2026, 3, 26),  # Shri Ram Navami (Thursday)
    datetime.date(2026, 3, 31),  # Shri Mahavir Jayanti (Tuesday)
    datetime.date(2026, 4, 3),   # Good Friday (Friday)
    datetime.date(2026, 4, 14),  # Dr. Baba Saheb Ambedkar Jayanti (Tuesday)
    datetime.date(2026, 5, 1),   # Maharashtra Day (Friday)
    datetime.date(2026, 5, 28),  # Bakri Id / Eid-ul-Adha (Thursday)
    datetime.date(2026, 6, 26),  # Muharram (Friday)
    datetime.date(2026, 8, 15),  # Independence Day (Saturday - exchange closed)
    datetime.date(2026, 9, 14),  # Ganesh Chaturthi (Monday)
    datetime.date(2026, 10, 2),  # Mahatma Gandhi Jayanti (Friday)
    datetime.date(2026, 10, 20), # Dussehra (Tuesday)
    # Note: Nov 8, 2026 is Sunday (Diwali Laxmi Pujan - Muhurat Trading special session)
    # Note: Nov 9, 2026 is Monday - NORMAL REGULAR TRADING DAY (not a holiday!)
    datetime.date(2026, 11, 10), # Diwali-Balipratipada (Tuesday - exchange holiday)
    datetime.date(2026, 11, 24), # Prakash Gurpurb Sri Guru Nanak Dev Jayanti (Tuesday)
    datetime.date(2026, 12, 25), # Christmas (Friday)
}

# Special Diwali Muhurat Trading Sessions (1-hour evening session)
# Sourced from NSE official market circulars.
NSE_MUHURAT_SESSIONS: Set[datetime.date] = {
    datetime.date(2024, 11, 1),  # Diwali Laxmi Pujan 2024 (18:00 to 19:00 IST)
    datetime.date(2025, 10, 21), # Diwali Laxmi Pujan 2025 (18:15 to 19:15 IST)
    datetime.date(2026, 11, 8),  # Diwali Laxmi Pujan 2026 (Sunday, ~18:15 to 19:15 IST)
}


def now_ist() -> datetime.datetime:
    """Current timestamp localized to Asia/Kolkata."""
    return datetime.datetime.now(IST)


def is_regular_trading_day(d: datetime.date) -> bool:
    """
    Return True if the date is a regular Monday-Friday equity trading day
    (neither a weekend nor a recognized official NSE exchange holiday).
    """
    if d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False
    if d in NSE_HOLIDAYS:
        return False
    return True


def is_muhurat_trading_day(d: datetime.date) -> bool:
    """
    Return True if date is designated for an official annual Diwali Muhurat Trading session.
    Muhurat sessions are special 1-hour evening trading sessions that are handled separately
    from ordinary daily swing trading operations.
    """
    return d in NSE_MUHURAT_SESSIONS


def get_market_session_type(d: datetime.date) -> str:
    """
    Classify the market session for a given date:
    - 'REGULAR': Ordinary 09:15-15:30 IST equity trading session.
    - 'MUHURAT': Special 1-hour evening Diwali Muhurat trading session.
    - 'HOLIDAY': Official declared exchange trading holiday.
    - 'WEEKEND': Regular Saturday or Sunday market closure.
    """
    if is_muhurat_trading_day(d):
        return "MUHURAT"
    if d in NSE_HOLIDAYS:
        return "HOLIDAY"
    if d.weekday() >= 5:
        return "WEEKEND"
    return "REGULAR"


def is_trading_day(d: datetime.date, include_special: bool = False) -> bool:
    """
    Primary interface for checking if equity trading occurs on a given date.
    By default (include_special=False), returns True strictly for regular Monday-Friday sessions.
    If include_special=True, also returns True for designated Muhurat trading sessions.
    """
    if include_special and is_muhurat_trading_day(d):
        return True
    return is_regular_trading_day(d)


def is_market_open(dt: datetime.datetime | None = None) -> bool:
    """
    Check if the Indian equity market is currently within active trading hours.
    - Regular trading day: 09:15 to 15:30 IST.
    - Special Muhurat trading session: 18:15 to 19:15 IST.
    """
    if dt is None:
        dt = now_ist()
    elif dt.tzinfo is None:
        dt = IST.localize(dt)
    else:
        dt = dt.astimezone(IST)

    d = dt.date()
    t = dt.time()

    # Special Muhurat session handling
    if is_muhurat_trading_day(d):
        muhurat_open = datetime.time(18, 15)
        muhurat_close = datetime.time(19, 15)
        return muhurat_open <= t <= muhurat_close

    if not is_regular_trading_day(d):
        return False

    market_open = datetime.time(9, 15)
    market_close = datetime.time(15, 30)
    return market_open <= t <= market_close


def is_eod_data_ready(dt: datetime.datetime | None = None, ready_hour: int = 18, ready_minute: int = 30) -> bool:
    """
    Check if the expected End-of-Day data publication time has passed.
    Default: 18:30 IST on regular trading days.
    On Muhurat trading sessions: 19:30 IST (after 19:15 session close).
    On non-trading days: True (previous completed session's data is already final).
    """
    if dt is None:
        dt = now_ist()
    elif dt.tzinfo is None:
        dt = IST.localize(dt)
    else:
        dt = dt.astimezone(IST)

    d = dt.date()
    if is_muhurat_trading_day(d):
        return dt.time() >= datetime.time(19, 30)

    if not is_regular_trading_day(d):
        return True

    eod_ready_time = datetime.time(ready_hour, ready_minute)
    return dt.time() >= eod_ready_time


def get_latest_completed_trading_day(ref_dt: datetime.datetime | None = None, include_special: bool = False) -> datetime.date:
    """
    Return the date of the most recent completed trading session.
    If today is a trading day and it's after EOD ready time, returns today.
    Otherwise, steps backward to find the prior completed trading day.
    """
    if ref_dt is None:
        ref_dt = now_ist()
    elif ref_dt.tzinfo is None:
        ref_dt = IST.localize(ref_dt)
    else:
        ref_dt = ref_dt.astimezone(IST)

    today = ref_dt.date()
    is_today_session = is_regular_trading_day(today) or (include_special and is_muhurat_trading_day(today))
    if is_today_session and is_eod_data_ready(ref_dt):
        return today

    candidate = today - datetime.timedelta(days=1)
    while True:
        if is_regular_trading_day(candidate) or (include_special and is_muhurat_trading_day(candidate)):
            return candidate
        candidate -= datetime.timedelta(days=1)


def get_previous_trading_day(d: datetime.date, include_special: bool = False) -> datetime.date:
    """Get the trading day strictly prior to d."""
    candidate = d - datetime.timedelta(days=1)
    while not (is_regular_trading_day(candidate) or (include_special and is_muhurat_trading_day(candidate))):
        candidate -= datetime.timedelta(days=1)
    return candidate


def get_next_trading_day(d: datetime.date, include_special: bool = False) -> datetime.date:
    """Get the next trading day strictly after d."""
    candidate = d + datetime.timedelta(days=1)
    while not (is_regular_trading_day(candidate) or (include_special and is_muhurat_trading_day(candidate))):
        candidate += datetime.timedelta(days=1)
    return candidate


def get_trading_days_between(
    start_date: datetime.date, end_date: datetime.date, include_special: bool = False
) -> List[datetime.date]:
    """Return all valid trading days in [start_date, end_date] inclusive."""
    days = []
    curr = start_date
    while curr <= end_date:
        if is_trading_day(curr, include_special=include_special):
            days.append(curr)
        curr += datetime.timedelta(days=1)
    return days
