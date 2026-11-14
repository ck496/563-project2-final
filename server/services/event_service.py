"""Event bus: publish, filter, and stream game events."""
import asyncio
import logging

from ..models.enums import Audience, EventType, Role
from ..models.event import Event
from ..services.player_service import PlayerService
from server.config import settings

logger = logging.getLogger(__name__)


class EventService:
    """Owns the event log and per-player SSE queues."""

    def __init__(self, players: PlayerService) -> None:
        self._players = players
        self._events: list[Event] = []          # full in-memory event log
        self._next_seq = 1
        # per-player mailboxes: publish() puts, stream_for() awaits get()
        self._queues: dict[int, list[asyncio.Queue[Event]]] = {}

    # -- public API --

    def publish(
        self,
        type: EventType,
        audience: Audience,
        payload: dict | None = None,
        to_player_id: int | None = None,
    ) -> Event:
        """Create an event and push to connected players."""
        event = Event(
            seq=self._next_seq,
            type=type,
            audience=audience,
            payload=payload or {},
            to_player_id=to_player_id,
        )
        self._next_seq += 1
        self._events.append(event)

        # fan out to every connected player allowed to see this event
        for pid, queues in self._queues.items():
            player = self._players.get_player(pid)
            if self.visible_to(event, player):
                for q in queues:
                    q.put_nowait(event)

        # No audience in logs: audience would reveal role-scoped events
        logger.info("event seq=%d type=%s", event.seq, event.type)
        return event

    def visible_to(self, event: Event, player) -> bool:
        """Return True if player is allowed to see this event.
        """
        match event.audience:
            case Audience.ALL:
                return True
            case Audience.WOLVES:
                return player.role == Role.WEREWOLF
            case Audience.WITCH:
                return player.role == Role.WITCH
            case Audience.PLAYER:
                return player.id == event.to_player_id
            case Audience.MOD:
                return False

    def history_for(self, player_id: int, after_seq: int = 0) -> list[Event]:
        """Return past events this player may see, after the given seq."""
        player = self._players.get_player(player_id)
        return [
            e for e in self._events
            if e.seq > after_seq and self.visible_to(e, player)
        ]

    async def stream_for(self, player_id: int, after: int = 0):
        """Async generator: replay history then yield live (n, event) tuples.

        n is the event's 1-based position in this player's visible list.
        after=0 means start from the beginning; after=3 skips the first 3.
        """
        # register queue first so events published during catch-up are not lost
        queue: asyncio.Queue[Event | None] = asyncio.Queue()
        pqs = self._queues.setdefault(player_id, [])
        pqs.append(queue)
        # Cap streams per player: close oldest if over the limit (B4)
        while len(pqs) > settings.max_streams_per_player:
            old = pqs.pop(0)
            old.put_nowait(None)
        try:
            # Catch-up: replay visible history with per-player numbering
            visible = self.history_for(player_id)
            for i, event in enumerate(visible, start=1):
                if i > after:
                    yield i, event
            n = len(visible)  # position counter continues from history
            while True:                                           # live
                event = await queue.get()   # sleeps until publish() puts one in
                if event is None:           # shutdown sentinel
                    break
                n += 1
                yield n, event
        finally:
            # Guard: reset() may have already cleared _queues
            pqs = self._queues.get(player_id)
            if pqs is not None and queue in pqs:
                pqs.remove(queue)
                if not pqs:
                    del self._queues[player_id]

    def shutdown(self) -> None:
        """Push a None sentinel into every queue so SSE streams close cleanly."""
        for queues in self._queues.values():
            for q in queues:
                q.put_nowait(None)

    def reset(self) -> None:
        """Clear event log and sequence counter for a new game.

        Call shutdown() first to close SSE streams, then reset().
        """
        self._events.clear()
        self._next_seq = 1
        # Queues should already be empty after shutdown sentinels
        self._queues.clear()

