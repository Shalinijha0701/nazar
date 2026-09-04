from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


INDIA_TZ = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)


def is_market_open(at: datetime) -> bool:
    if at.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    localized = at.astimezone(INDIA_TZ)
    return (
        localized.weekday() < 5
        and SESSION_OPEN <= localized.time() < SESSION_CLOSE
    )


def trading_minutes_between(start: datetime, end: datetime) -> int:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    if end <= start:
        return 0

    local_start = start.astimezone(INDIA_TZ)
    local_end = end.astimezone(INDIA_TZ)
    total = 0
    day = local_start.date()
    while day <= local_end.date():
        if day.weekday() < 5:
            session_start = datetime.combine(day, SESSION_OPEN, INDIA_TZ)
            session_end = datetime.combine(day, SESSION_CLOSE, INDIA_TZ)
            overlap_start = max(local_start, session_start)
            overlap_end = min(local_end, session_end)
            if overlap_end > overlap_start:
                total += int((overlap_end - overlap_start).total_seconds() // 60)
        day += timedelta(days=1)
    return total
