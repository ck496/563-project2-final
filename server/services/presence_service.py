"""Presence tracker: monotonic timestamps per player."""
import time


class PresenceService:
    """Tracks last heartbeat time for each player."""

    def __init__(self) -> None:
        self._last_seen: dict[int, float] = {}

    def touch(self, player_id: int) -> None:
        """Record the current monotonic time for a player."""
        self._last_seen[player_id] = time.monotonic()

    def stale(self, grace_seconds: float) -> list[int]:
        """Return player ids whose last heartbeat is older than grace_seconds."""
        cutoff = time.monotonic() - grace_seconds
        return [pid for pid, ts in self._last_seen.items() if ts < cutoff]

    def forget(self, player_id: int) -> None:
        """Remove a player from tracking."""
        self._last_seen.pop(player_id, None)

    def reset(self) -> None:
        """Clear all presence data for a new game."""
        self._last_seen.clear()
