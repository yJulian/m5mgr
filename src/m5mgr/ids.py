"""Run ID generation.

Format: <UTC timestamp>-<6 random chars>, e.g. 20260818T231955Z-4TZK9P.

Sortable by creation time, short enough to type, and collision-safe (the
random suffix means two runs started in the same second still get distinct
ids). The alphabet excludes visually ambiguous characters (0/O, 1/I/L).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(6))
    return f"{timestamp}-{suffix}"
