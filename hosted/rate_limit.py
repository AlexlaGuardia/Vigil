"""Per-tenant rate limiting — sliding window counter.

Simple in-memory rate limiter. Each project gets a deque of request timestamps.
Oldest entries outside the window are pruned on check.

No external deps, no Redis, no persistence — restarts reset counters (by design).
"""

import time
from collections import defaultdict, deque


class RateLimiter:
    """Sliding window rate limiter.

    Args:
        window_seconds: Time window for counting requests (default: 60)
    """

    def __init__(self, window_seconds: int = 60):
        self.window = window_seconds
        self._counters: dict[str, deque] = defaultdict(deque)

    def check(self, project_id: str, limit: int) -> tuple[bool, dict]:
        """Check if a request is allowed.

        Args:
            project_id: Tenant identifier
            limit: Max requests per window (0 = unlimited)

        Returns:
            (allowed, info) where info has: remaining, limit, reset_at
        """
        if limit <= 0:
            return True, {"remaining": -1, "limit": 0, "retry_after": 0}

        now = time.monotonic()
        window_start = now - self.window
        counter = self._counters[project_id]

        # Prune old entries
        while counter and counter[0] < window_start:
            counter.popleft()

        current = len(counter)
        remaining = max(0, limit - current)

        if current >= limit:
            # Calculate retry-after from oldest entry in window
            retry_after = int(counter[0] - window_start) + 1 if counter else 1
            return False, {
                "remaining": 0,
                "limit": limit,
                "retry_after": max(1, retry_after),
            }

        # Allow and record
        counter.append(now)
        return True, {
            "remaining": remaining - 1,
            "limit": limit,
            "retry_after": 0,
        }

    @property
    def tracked_projects(self) -> int:
        return len(self._counters)
