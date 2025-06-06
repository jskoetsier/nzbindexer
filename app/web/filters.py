"""
Custom template filters for the web interface
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def timeago(dt: Optional[datetime]) -> str:
    """
    Format a datetime as a human-readable string like "2 hours ago"
    """
    if dt is None:
        return "Never"

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days > 1 else ''} ago"
    elif seconds < 2592000:
        weeks = int(seconds / 604800)
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    elif seconds < 31536000:
        months = int(seconds / 2592000)
        return f"{months} month{'s' if months > 1 else ''} ago"
    else:
        years = int(seconds / 31536000)
        return f"{years} year{'s' if years > 1 else ''} ago"


def filesizeformat(size: Optional[int]) -> str:
    """
    Format a file size in bytes as a human-readable string
    """
    if size is None:
        return "0 B"

    # Define units and their respective sizes in bytes
    units = [(1024**4, "TB"), (1024**3, "GB"), (1024**2, "MB"), (1024, "KB"), (1, "B")]

    for factor, unit in units:
        if size >= factor:
            value = size / factor
            if value < 10:
                return f"{value:.2f} {unit}"
            elif value < 100:
                return f"{value:.1f} {unit}"
            else:
                return f"{int(value)} {unit}"

    return f"{size} B"


def get_current_year() -> str:
    """
    Get the current year as a string
    """
    return str(datetime.now().year)


def get_template_context() -> Dict[str, Any]:
    """
    Get common template context variables
    """
    return {"current_year": get_current_year()}
