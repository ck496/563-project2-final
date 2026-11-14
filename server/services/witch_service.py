"""Witch service: manages the witch's save/poison/pass decision each night."""
import logging

from ..models.enums import Phase, WitchChoice
from ..models.vote import Vote, WitchBallot
from server.exceptions import WrongPhaseError, NotAllowedError, InvalidTargetError

logger = logging.getLogger(__name__)


class WitchService:
    """Manages the witch's nightly action: save, poison, or pass.

    Tracks potion and poison usage across the entire game.
    The orchestrator calls open() each WITCH_VOTE phase, cast() when the
    witch submits, and close() to resolve the outcome.
    """

    def __init__(self) -> None:
        self._vote: Vote | None = None
        self._victim_id: int | None = None
        # Once-per-game potions: True means still available
        self._has_potion: bool = True
        self._has_poison: bool = True

    def open(
        self,
        witch_id: int | None,
        victim_id: int | None,
        candidates: set[int],
    ) -> set[WitchChoice]:
        """Start the witch phase and return which actions are allowed.

        Args:
            witch_id: the witch's player id, or None if dead.
            victim_id: the wolf vote victim, or None if nobody was voted.
            candidates: living player ids the witch could poison.

        Returns the set of actions the witch may take. Empty if the witch
        is dead, meaning the phase should still run its timer but no ballot
        will arrive.
        """
        self._victim_id = victim_id

        # Build the set of actions available this round
        allowed: set[WitchChoice] = set()
        if witch_id is None:
            # Still create a Vote so cast() raises NotAllowedError (403)
            # for everyone, not WrongPhaseError (409) which would leak witch state
            self._vote = Vote(
                phase=Phase.WITCH_VOTE,
                eligible_voters=set(),
                candidates=set(),
                allowed_actions=set(),
                ballots={},
            )
            return allowed

        # PASS is always available
        allowed.add(WitchChoice.PASS)
        # SAVE only if the potion is unused and there is a victim to save
        if self._has_potion and victim_id is not None:
            allowed.add(WitchChoice.SAVE)
        # POISON only if the poison is unused
        if self._has_poison:
            allowed.add(WitchChoice.POISON)

        self._vote = Vote(
            phase=Phase.WITCH_VOTE,
            eligible_voters={witch_id},
            candidates=candidates,
            allowed_actions=allowed,
            ballots={},
        )
        return allowed

    def cast(self, player_id: int, ballot: WitchBallot) -> None:
        """Record the witch's choice. Replaces a previous ballot if re-cast."""
        if self._vote is None:
            raise WrongPhaseError("witch vote is not open")
        if player_id not in self._vote.eligible_voters:
            raise NotAllowedError("only the witch may cast here")
        if ballot.action not in self._vote.allowed_actions:
            # e.g. trying to SAVE when potion is already used
            raise NotAllowedError(f"{ballot.action} is not available this round")
        if ballot.action == WitchChoice.POISON:
            if ballot.target not in self._vote.candidates:
                raise InvalidTargetError("poison target is not a valid candidate")

        self._vote.ballots[player_id] = ballot

    def close(self) -> tuple[bool, int | None]:
        """Resolve the witch phase and consume any used potion.

        Returns (saved, poison_target):
          - saved: True if the witch used SAVE, meaning the victim survives.
          - poison_target: player id if POISON was used, else None.
        """
        if self._vote is None:
            # Witch was dead: no action taken
            return False, None

        saved = False
        poison_target: int | None = None

        # Only one voter (the witch), so at most one ballot
        if self._vote.ballots:
            ballot: WitchBallot = list(self._vote.ballots.values())[0]  # type: ignore[assignment]
            if ballot.action == WitchChoice.SAVE:
                saved = True
                self._has_potion = False
            elif ballot.action == WitchChoice.POISON:
                poison_target = ballot.target
                self._has_poison = False
            # PASS: nothing consumed

        self._vote = None
        return saved, poison_target

    def reset(self) -> None:
        """Clear witch state for a new game."""
        self._vote = None
        self._victim_id = None
        self._has_potion = True
        self._has_poison = True

    @property
    def current_vote(self) -> Vote | None:
        """The in-progress witch vote, or None. For orchestrator early-exit checks."""
        return self._vote
