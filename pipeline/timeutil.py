"""America/Chicago stamps. Every public timestamp should go through here."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CHI = ZoneInfo("America/Chicago")


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return dt


def stamp(dt: datetime) -> str:
    """Example: Nov 23, 2026, 8:00 AM CT (America/Chicago)."""
    local = ensure_aware(dt).astimezone(CHI)
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return (
        f"{local.strftime('%b')} {local.day}, {local.year}, "
        f"{hour}:{local.minute:02d} {ampm} CT (America/Chicago)"
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return ensure_aware(dt).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
