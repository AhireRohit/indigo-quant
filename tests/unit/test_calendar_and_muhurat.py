"""
Automated Unit and Regression Tests for NSE Trading Calendar & Muhurat Session Handling.
Validates the official 2026 NSE equity trading calendar, special Diwali Muhurat sessions,
and calendar-aware scheduler behavior.
"""

import datetime

from indigo_quant.data.calendar import (
    IST,
    NSE_HOLIDAYS,
    get_market_session_type,
    get_next_trading_day,
    get_previous_trading_day,
    get_trading_days_between,
    is_market_open,
    is_muhurat_trading_day,
    is_regular_trading_day,
    is_trading_day,
)


def test_diwali_2026_calendar_sequence():
    """
    Verify the mandatory test cases around Diwali 2026:
    - November 6, 2026: trading day.
    - November 7, 2026: weekend.
    - November 8, 2026: special Diwali Muhurat session; handled separately from ordinary trading.
    - November 9, 2026: normal trading day.
    - November 10, 2026: trading holiday (Diwali-Balipratipada).
    - November 11, 2026: normal trading day.
    """
    nov_6 = datetime.date(2026, 11, 6)   # Friday
    nov_7 = datetime.date(2026, 11, 7)   # Saturday
    nov_8 = datetime.date(2026, 11, 8)   # Sunday (Diwali Laxmi Pujan)
    nov_9 = datetime.date(2026, 11, 9)   # Monday (Regular Trading Day)
    nov_10 = datetime.date(2026, 11, 10) # Tuesday (Diwali-Balipratipada Holiday)
    nov_11 = datetime.date(2026, 11, 11) # Wednesday (Regular Trading Day)

    # 1. November 6, 2026: trading day
    assert is_trading_day(nov_6) is True
    assert is_regular_trading_day(nov_6) is True
    assert is_muhurat_trading_day(nov_6) is False
    assert get_market_session_type(nov_6) == "REGULAR"

    # 2. November 7, 2026: weekend
    assert is_trading_day(nov_7) is False
    assert is_regular_trading_day(nov_7) is False
    assert is_muhurat_trading_day(nov_7) is False
    assert get_market_session_type(nov_7) == "WEEKEND"

    # 3. November 8, 2026: special Diwali Muhurat session
    assert is_regular_trading_day(nov_8) is False  # Not an ordinary trading session
    assert is_muhurat_trading_day(nov_8) is True    # Special Muhurat session
    assert get_market_session_type(nov_8) == "MUHURAT"
    assert is_trading_day(nov_8, include_special=False) is False
    assert is_trading_day(nov_8, include_special=True) is True

    # 4. November 9, 2026: normal trading day
    assert is_trading_day(nov_9) is True
    assert is_regular_trading_day(nov_9) is True
    assert is_muhurat_trading_day(nov_9) is False
    assert get_market_session_type(nov_9) == "REGULAR"
    assert nov_9 not in NSE_HOLIDAYS

    # 5. November 10, 2026: trading holiday (Diwali-Balipratipada)
    assert is_trading_day(nov_10) is False
    assert is_regular_trading_day(nov_10) is False
    assert is_muhurat_trading_day(nov_10) is False
    assert get_market_session_type(nov_10) == "HOLIDAY"
    assert nov_10 in NSE_HOLIDAYS

    # 6. November 11, 2026: normal trading day
    assert is_trading_day(nov_11) is True
    assert is_regular_trading_day(nov_11) is True
    assert is_muhurat_trading_day(nov_11) is False
    assert get_market_session_type(nov_11) == "REGULAR"


def test_trading_day_stepping_and_intervals():
    """Verify navigation functions correctly skip weekends, holidays, and handle Muhurat."""
    nov_6 = datetime.date(2026, 11, 6)
    nov_9 = datetime.date(2026, 11, 9)
    nov_10 = datetime.date(2026, 11, 10)
    nov_11 = datetime.date(2026, 11, 11)

    # Next trading day from Friday Nov 6 skips Saturday (7th) and Sunday Muhurat (8th) to Monday Nov 9
    assert is_trading_day(nov_10) is False
    assert get_next_trading_day(nov_6) == nov_9

    # Next trading day from Monday Nov 9 skips Tuesday holiday (10th) to Wednesday Nov 11
    assert get_next_trading_day(nov_9) == nov_11

    # Previous trading day stepping
    assert get_previous_trading_day(nov_11) == nov_9
    assert get_previous_trading_day(nov_9) == nov_6

    # Between range
    trading_days = get_trading_days_between(nov_6, nov_11)
    assert trading_days == [nov_6, nov_9, nov_11]


def test_muhurat_special_session_hours():
    """Verify market open detection separates Muhurat evening hours from regular morning hours."""
    nov_8 = datetime.date(2026, 11, 8)
    nov_9 = datetime.date(2026, 11, 9)

    # Sunday morning during regular market hours: Market CLOSED on Muhurat day
    dt_sun_morning = IST.localize(datetime.datetime.combine(nov_8, datetime.time(10, 0)))
    assert is_market_open(dt_sun_morning) is False

    # Sunday evening during Muhurat session (18:15 to 19:15 IST): Market OPEN
    dt_sun_muhurat = IST.localize(datetime.datetime.combine(nov_8, datetime.time(18, 30)))
    assert is_market_open(dt_sun_muhurat) is True

    # Monday morning during regular market hours: Market OPEN
    dt_mon_open = IST.localize(datetime.datetime.combine(nov_9, datetime.time(10, 0)))
    assert is_market_open(dt_mon_open) is True

    # Monday after market close: Market CLOSED
    dt_mon_closed = IST.localize(datetime.datetime.combine(nov_9, datetime.time(16, 0)))
    assert is_market_open(dt_mon_closed) is False


def test_full_2026_official_nse_holidays():
    """Verify all 15 official trading holidays published by the National Stock Exchange for 2026."""
    official_2026_holidays = {
        datetime.date(2026, 1, 26),  # Republic Day (Monday)
        datetime.date(2026, 3, 3),   # Holi (Tuesday)
        datetime.date(2026, 3, 26),  # Shri Ram Navami (Thursday)
        datetime.date(2026, 3, 31),  # Shri Mahavir Jayanti (Tuesday)
        datetime.date(2026, 4, 3),   # Good Friday (Friday)
        datetime.date(2026, 4, 14),  # Dr. Ambedkar Jayanti (Tuesday)
        datetime.date(2026, 5, 1),   # Maharashtra Day (Friday)
        datetime.date(2026, 5, 28),  # Bakri Id (Thursday)
        datetime.date(2026, 6, 26),  # Muharram (Friday)
        datetime.date(2026, 9, 14),  # Ganesh Chaturthi (Monday)
        datetime.date(2026, 10, 2),  # Mahatma Gandhi Jayanti (Friday)
        datetime.date(2026, 10, 20), # Dussehra (Tuesday)
        datetime.date(2026, 11, 10), # Diwali-Balipratipada (Tuesday)
        datetime.date(2026, 11, 24), # Gurunanak Jayanti (Tuesday)
        datetime.date(2026, 12, 25), # Christmas (Friday)
    }

    for h in official_2026_holidays:
        assert h in NSE_HOLIDAYS, f"Expected holiday {h} missing from NSE_HOLIDAYS"
        assert is_regular_trading_day(h) is False

    # Assert November 9, 2026 is NOT an exchange holiday
    assert datetime.date(2026, 11, 9) not in NSE_HOLIDAYS
    assert is_regular_trading_day(datetime.date(2026, 11, 9)) is True
