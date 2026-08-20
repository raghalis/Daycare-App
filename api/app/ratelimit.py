from collections import defaultdict
from datetime import datetime, timedelta, timezone

# Process-local, in-memory - fine for a single-container deployment like this
# one. Resets on restart and wouldn't coordinate across replicas, neither of
# which applies here.
WINDOW = timedelta(minutes=15)
MAX_ATTEMPTS_PER_EMAIL = 5
MAX_ATTEMPTS_PER_IP = 20

_email_failures: dict[str, list[datetime]] = defaultdict(list)
_ip_failures: dict[str, list[datetime]] = defaultdict(list)


def _prune(bucket: list[datetime], now: datetime) -> list[datetime]:
    return [t for t in bucket if now - t < WINDOW]


def is_locked_out(email: str, ip: str | None) -> tuple[bool, int]:
    """Returns (locked, seconds_until_retry). Locks out ALL attempts for the
    key once tripped, correct password or not, until the window rolls off -
    that's what makes it a real cooldown instead of just a counter."""
    now = datetime.now(timezone.utc)
    email_key = email.lower()
    _email_failures[email_key] = _prune(_email_failures[email_key], now)
    if ip:
        _ip_failures[ip] = _prune(_ip_failures[ip], now)

    oldest = None
    if len(_email_failures[email_key]) >= MAX_ATTEMPTS_PER_EMAIL:
        oldest = _email_failures[email_key][0]
    elif ip and len(_ip_failures[ip]) >= MAX_ATTEMPTS_PER_IP:
        oldest = _ip_failures[ip][0]

    if oldest is None:
        return False, 0
    return True, max(int((oldest + WINDOW - now).total_seconds()), 1)


def record_failure(email: str, ip: str | None) -> int:
    """Returns the email's failure count in the current window, so the
    caller can tell exactly when a lockout was just triggered (== the
    threshold) versus already in effect (> the threshold, don't re-alert)."""
    now = datetime.now(timezone.utc)
    email_key = email.lower()
    _email_failures[email_key].append(now)
    if ip:
        _ip_failures[ip].append(now)
    return len(_prune(_email_failures[email_key], now))


def clear_failures(email: str) -> None:
    _email_failures.pop(email.lower(), None)
