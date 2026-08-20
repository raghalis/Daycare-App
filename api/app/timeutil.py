from datetime import datetime, timezone


def to_utc_iso(dt: datetime | None) -> str | None:
    """
    SQLite drops tzinfo on read even for DateTime(timezone=True) columns -
    every such column is written in UTC (func.now() / datetime.now(timezone.utc)),
    so re-attach it before serializing instead of letting the browser guess
    the offset (it guesses local, which silently mislabels UTC as local).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
