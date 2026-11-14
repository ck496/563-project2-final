from pydantic import BaseModel, Field, model_validator
from .enums import Audience, EventType


class Event(BaseModel):
    seq: int
    type: EventType
    payload: dict = Field(default_factory=dict)
    audience: Audience
    to_player_id: int | None = None        # only when audience == PLAYER

    @model_validator(mode="after")
    def _check_target(self):
        if (self.audience is Audience.PLAYER) != (self.to_player_id is not None):
            raise ValueError("to_player is required iff audience is PLAYER")
        return self
