"""S3 checks: vote tallying, ballot replacement, eligibility, and witch potion limits."""
from server.models.enums import Phase, WitchChoice
from server.services.vote_service import VoteService
from server.services.witch_service import WitchService
from server.models.vote import WitchBallot


def test_most_votes_wins():
    """The candidate with the most ballots is returned by close()."""
    svc = VoteService()
    svc.open(Phase.DAY_VOTE, eligible_voters={1, 2, 3}, candidates={1, 2, 3})
    svc.cast(1, target=3)
    svc.cast(2, target=3)
    svc.cast(3, target=1)
    assert svc.close() == 3


def test_tie_returns_none():
    """A tie between top candidates returns None."""
    svc = VoteService()
    svc.open(Phase.WOLF_VOTE, eligible_voters={1, 2}, candidates={10, 20})
    svc.cast(1, target=10)
    svc.cast(2, target=20)
    assert svc.close() is None


def test_second_ballot_replaces_first():
    """A voter's second ballot overwrites the first (last one counts)."""
    svc = VoteService()
    svc.open(Phase.DAY_VOTE, eligible_voters={1}, candidates={10, 20})
    svc.cast(1, target=10)
    svc.cast(1, target=20)
    assert svc.close() == 20


def test_ineligible_voter_rejected():
    """A player not in the eligible set gets NotAllowedError."""
    import pytest
    from server.exceptions import NotAllowedError

    svc = VoteService()
    svc.open(Phase.DAY_VOTE, eligible_voters={1, 2}, candidates={1, 2})
    with pytest.raises(NotAllowedError):
        svc.cast(99, target=1)


def test_witch_cannot_save_twice():
    """After the witch uses SAVE once, SAVE is not offered the next round."""
    svc = WitchService()

    # Round 1: witch saves
    allowed = svc.open(witch_id=5, victim_id=10, candidates={1, 2, 3})
    assert WitchChoice.SAVE in allowed
    svc.cast(5, WitchBallot(action=WitchChoice.SAVE))
    saved, poison = svc.close()
    assert saved is True
    assert poison is None

    # Round 2: SAVE should no longer be available
    allowed2 = svc.open(witch_id=5, victim_id=11, candidates={1, 2, 3})
    assert WitchChoice.SAVE not in allowed2
