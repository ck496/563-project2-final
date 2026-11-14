from pydantic import BaseModel, Field, model_validator
from .enums import Phase
from typing import Literal, Annotated
from .enums import WitchChoice


class TargetBallot(BaseModel):
    kind: Literal["target"] = "target"
    target: int


class WitchBallot(BaseModel):
    """Witch ballot: target required for POISON, forbidden otherwise."""
    kind: Literal["witch"] = "witch"
    action: WitchChoice
    target: int | None = None

    @model_validator(mode="after")
    def _check_target(self):
        if self.action == WitchChoice.POISON and self.target is None:
            raise ValueError("target is required for POISON")
        if self.action != WitchChoice.POISON and self.target is not None:
            raise ValueError("target is forbidden unless action is POISON")
        return self


Ballot = Annotated[TargetBallot | WitchBallot, Field(discriminator="kind")]


class Vote(BaseModel):
    phase: Literal[Phase.WOLF_VOTE, Phase.WITCH_VOTE, Phase.DAY_VOTE]
    eligible_voters: set[int]
    candidates: set[int]
    # witch poll only; SAVE removed once potion used
    allowed_actions: set[WitchChoice] = set()
    ballots: dict[int, Ballot] = {}
