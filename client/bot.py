"""Pure bot decision functions: no I/O, no imports beyond stdlib."""
import random


def choose_vote(view: dict) -> int | None:
    """Pick a random living player to vote for, excluding teammates.

    view keys: my_id, role, teammates, alive_ids, phase.
    Returns a player id or None if no valid target.
    """
    my_id = view["my_id"]
    teammates = set(view.get("teammates", []))
    alive = set(view["alive_ids"])
    # Never vote for self, and wolves never vote for fellow wolves
    excluded = {my_id} | teammates
    candidates = alive - excluded
    if not candidates:
        return None
    return random.choice(sorted(candidates))


def choose_witch(view: dict, prompt: dict) -> dict:
    """Pick a random legal witch action.

    prompt keys: victim_id, allowed (list of action strings).
    Returns a dict matching commands.parse output for witch actions.
    """
    allowed = prompt.get("allowed", [])
    if not allowed:
        return {"action": "pass"}
    action = random.choice(allowed)
    if action == "poison":
        # Pick a random alive non-self target
        alive = set(view["alive_ids"])
        targets = alive - {view["my_id"]}
        if not targets:
            return {"action": "pass"}
        target_id = random.choice(sorted(targets))
        return {"action": "poison", "name": str(target_id)}
    return {"action": action}


def choose_chat(view: dict) -> str | None:
    """Maybe say something. Returns a message or None to stay silent."""
    # Bots stay quiet most of the time to avoid noise
    if random.random() < 0.8:
        return None
    lines = [
        "Hmm, interesting.",
        "I think we should vote carefully.",
        "Anyone suspicious?",
        "Let's not rush.",
        "I have a feeling about this.",
    ]
    return random.choice(lines)
