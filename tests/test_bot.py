"""Tests for bot decision functions (S8)."""
from client.bot import choose_vote, choose_witch


def _wolf_view() -> dict:
    """A wolf with two wolf teammates and five alive players."""
    return {
        "my_id": 1,
        "role": "werewolf",
        "teammates": [2, 3],
        "alive_ids": [1, 2, 3, 4, 5],
        "phase": "wolf_vote",
    }


def _town_view() -> dict:
    """A townsperson with five alive players."""
    return {
        "my_id": 4,
        "role": "townsperson",
        "teammates": [],
        "alive_ids": [1, 2, 3, 4, 5],
        "phase": "day_vote",
    }


def test_wolf_never_votes_for_wolf():
    """A wolf bot never picks a fellow wolf or itself as the target."""
    view = _wolf_view()
    wolves = {1, 2, 3}
    # Run enough trials to be confident
    for _ in range(200):
        target = choose_vote(view)
        assert target is not None
        assert target not in wolves, f"wolf voted for wolf {target}"


def test_bot_never_votes_for_dead():
    """A bot never votes for a dead player (they are not in alive_ids)."""
    view = _town_view()
    # Player 5 is dead: not in alive_ids
    view["alive_ids"] = [1, 2, 3, 4]
    for _ in range(200):
        target = choose_vote(view)
        assert target is not None
        assert target != 5, "voted for dead player 5"
        assert target != 4, "voted for self"


def test_witch_only_picks_allowed_action():
    """A witch bot only returns an action from the allowed list."""
    view = {"my_id": 6, "role": "witch", "teammates": [], "alive_ids": [1, 2, 3, 6],
            "phase": "witch_vote"}
    # Allowed: save and pass (no poison)
    prompt = {"victim_id": 1, "allowed": ["save", "pass"]}
    for _ in range(200):
        result = choose_witch(view, prompt)
        assert result["action"] in ("save", "pass"), f"illegal action: {result}"


def test_witch_poison_picks_valid_target():
    """When poison is allowed, the bot picks a living non-self target."""
    view = {"my_id": 6, "role": "witch", "teammates": [], "alive_ids": [1, 2, 3, 6],
            "phase": "witch_vote"}
    prompt = {"victim_id": 1, "allowed": ["poison"]}
    for _ in range(200):
        result = choose_witch(view, prompt)
        assert result["action"] == "poison"
        # name is a stringified player id
        target = int(result["name"])
        assert target != 6, "witch poisoned self"
        assert target in (1, 2, 3), f"witch poisoned non-alive {target}"
