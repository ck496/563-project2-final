"""Chat service: validates, sanitizes, and publishes chat messages."""
import re
import time
import logging
from datetime import datetime, timezone

from ..models.chat import Chat
from ..models.enums import Audience, ChatChannel, EventType, Phase, Role
from ..models.game_state import GameState
from ..services.event_service import EventService
from ..services.player_service import PlayerService
from server.exceptions import NotAllowedError, RateLimitError, WrongPhaseError

logger = logging.getLogger(__name__)

# Phases where chat is open, mapped to who may post and which channel is used
_CHAT_PHASES: dict[Phase, tuple[str, ChatChannel]] = {
    Phase.WOLF_CHAT: ("wolves", ChatChannel.WOLVES),
    Phase.DAY_CHAT:  ("alive",  ChatChannel.TOWN),
    Phase.DUSK:      ("hanged", ChatChannel.TOWN),
}

# Matches ANSI escape sequences and all C0/C1 control characters
_STRIP_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|[\x00-\x1f\x7f-\x9f]")

MAX_CHAT_LEN = 300
_RATE_LIMIT_SECONDS = 1.0


class ChatService:
    """Owns chat validation and rate limiting; delegates delivery to EventService."""

    def __init__(
        self, state: GameState, players: PlayerService, events: EventService
    ) -> None:
        self._state = state
        self._players = players
        self._events = events
        # player_id -> monotonic timestamp of their last accepted message
        self._last_post: dict[int, float] = {}

    def post(self, player_id: int, text: str) -> Chat:
        """Validate, sanitize, and publish a chat message.

        Raises WrongPhaseError, NotAllowedError, or RateLimitError.
        Returns the Chat model that was published.
        """
        phase = self._state.phase

        # 1. Phase must allow chat
        if phase not in _CHAT_PHASES:
            raise WrongPhaseError(f"chat not allowed in {phase}")

        eligibility, channel = _CHAT_PHASES[phase]
        player = self._players.get_player(player_id)

        # 2. Player must be eligible to post in this phase
        #    The hanged player (dead) is the one person who may speak in DUSK.
        #    Check hanged first so the alive gate below does not block last words.
        if eligibility == "hanged":
            if player.id != self._state.hanged_id:
                raise NotAllowedError("only the hanged player may speak during dusk")
        else:
            # Dead players cannot chat in any other phase
            if not player.alive:
                raise NotAllowedError("dead players cannot chat")
            if eligibility == "wolves" and player.role != Role.WEREWOLF:
                raise NotAllowedError("only wolves can chat at night")

        # 3. Rate limit: 1 message per second per player
        now = time.monotonic()
        last = self._last_post.get(player_id, 0.0)
        if now - last < _RATE_LIMIT_SECONDS:
            raise RateLimitError("1 message per second")

        # 4. Sanitize: strip ANSI escapes and control chars, then cap length
        clean = _STRIP_RE.sub("", text).strip()[:MAX_CHAT_LEN]

        # 5. Build the Chat payload and publish through EventService
        chat = Chat(
            day_num=self._state.day_num,
            phase=phase,
            channel=channel,
            author_id=player.id,
            author_name=player.name,
            text=clean,
            time=datetime.now(timezone.utc),
        )

        # WOLVES channel -> only wolves see it; TOWN -> everyone sees it
        audience = Audience.WOLVES if channel == ChatChannel.WOLVES else Audience.ALL
        self._events.publish(
            type=EventType.CHAT,
            audience=audience,
            payload=chat.model_dump(mode="json"),
        )

        # Record timestamp after successful publish
        self._last_post[player_id] = now
        # No player_id or channel in logs to avoid leaking identity
        logger.info("chat posted phase=%s", phase)
        return chat

    def reset(self) -> None:
        """Clear rate-limit state for a new game."""
        self._last_post.clear()
