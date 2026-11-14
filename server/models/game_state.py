from pydantic import BaseModel
from .enums import Phase, Role
from datetime import datetime


class GameState(BaseModel):
    phase: Phase = Phase.LOBBY  # defaults to lobby
    day_num: int
    # moment the current phase ends.. None for phase Lobby
    phase_ends_at: datetime | None = None
    winner: Role | None = None  # either role or none, defaults to none
    hanged_id: int | None = None  # set during DUSK for last words
    draw: bool = False  # True when max_days reached with no winner


# orchestrator, when entering a phase:
# duration = timedelta(seconds=settings.day_chat_seconds)
# state.phase_ends_at = datetime.now(timezone.utc) + duration
# await asyncio.sleep(duration.total_seconds())    # this is the real timer
