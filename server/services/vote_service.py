"""Vote service: opens, collects, and tallies ballots for wolf and day votes."""
import logging
from collections import Counter

from ..models.enums import Phase
from ..models.vote import Vote, TargetBallot
from server.exceptions import WrongPhaseError, NotAllowedError, InvalidTargetError

logger = logging.getLogger(__name__)


class VoteService:
    """Manages one vote round at a time: wolf vote or day vote.

    The orchestrator calls open() at the start of a vote phase,
    cast() is called per player, and close() tallies the result.
    """

    def __init__(self) -> None:
        self._vote: Vote | None = None

    def open(self, phase: Phase, eligible_voters: set[int], candidates: set[int]) -> Vote:
        """Start a new vote round, replacing any previous one.

        Args:
            phase: must be WOLF_VOTE or DAY_VOTE.
            eligible_voters: player ids allowed to cast a ballot.
            candidates: player ids that may be voted for.
        """
        self._vote = Vote(
            phase=phase,
            eligible_voters=eligible_voters,
            candidates=candidates,
            ballots={},
        )
        return self._vote

    def cast(self, voter_id: int, target: int) -> None:
        """Record a ballot; a second call from the same voter replaces the first."""
        if self._vote is None:
            raise WrongPhaseError("no vote is open")
        if voter_id not in self._vote.eligible_voters:
            raise NotAllowedError("player is not eligible to vote")
        if target not in self._vote.candidates:
            raise InvalidTargetError("target is not a valid candidate")

        # Last ballot wins: overwrite any previous ballot from this voter
        self._vote.ballots[voter_id] = TargetBallot(target=target)

    def close(self) -> int | None:
        """Tally the ballots and clear the round.

        Returns the id of the player with the most votes,
        or None if there is a tie or no ballots were cast.
        """
        if self._vote is None:
            raise WrongPhaseError("no vote is open")

        ballots = self._vote.ballots
        self._vote = None

        if not ballots:
            return None

        # Count votes by target
        counts = Counter(b.target for b in ballots.values())
        top_count = counts.most_common(1)[0][1]

        # Tie: more than one candidate shares the top count
        leaders = [pid for pid, c in counts.items() if c == top_count]
        if len(leaders) != 1:
            return None

        return leaders[0]

    @property
    def current_vote(self) -> Vote | None:
        """The in-progress vote, or None. Used by the orchestrator for early-exit checks."""
        return self._vote

    def reset(self) -> None:
        """Clear vote state for a new game."""
        self._vote = None

    def vote_count(self) -> tuple[int, int]:
        """Return (votes_cast, eligible_voters) for logging without revealing who voted."""
        if self._vote is None:
            return 0, 0
        return len(self._vote.ballots), len(self._vote.eligible_voters)
