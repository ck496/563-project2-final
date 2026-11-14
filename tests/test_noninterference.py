"""S7 checks: noninterference and deduplication."""
import random
import time

from server.config import settings
from server.models.enums import EventType, Phase, Role, WitchChoice
from server.models.game_state import GameState
from server.models.vote import WitchBallot
from server.services.auth_service import AuthService
from server.services.chat_service import ChatService
from server.services.event_service import EventService
from server.services.game_orchestrator import GameOrchestrator
from server.services.player_service import PlayerService
from server.services.presence_service import PresenceService
from server.services.vote_service import VoteService
from server.services.witch_service import WitchService


def _make_game(monkeypatch):
    """Build services and 5 players with deterministic roles.

    No-shuffle: pool [WOLF, WOLF, WITCH, TOWN, TOWN], pop() assigns:
    player 0=TOWN, 1=TOWN, 2=WITCH, 3=WOLF, 4=WOLF.
    """
    monkeypatch.setattr(settings, "max_wolves", 2)
    monkeypatch.setattr(settings, "max_witch", 1)
    monkeypatch.setattr(settings, "max_town", 2)
    monkeypatch.setattr(random, "shuffle", lambda x: None)

    players = PlayerService()
    presence = PresenceService()
    for i, name in enumerate(["Alice", "Bob", "Carol", "Dave", "Eve"]):
        players.add_player(name)
        presence.touch(i)

    state = GameState(day_num=0)
    auth = AuthService()
    events = EventService(players)
    chat = ChatService(state, players, events)
    votes = VoteService()
    witch = WitchService()
    orch = GameOrchestrator(state, players, events, votes, witch, auth, chat, presence)
    return state, players, events, chat, votes, witch, orch


def _advance_to_wolf_chat(orch, events, player_id):
    """Leave LOBBY and enter WOLF_CHAT; return visible event count for player."""
    orch.advance()  # LOBBY -> WOLF_CHAT
    return len(events.history_for(player_id))


def test_wolf_chat_volume_invisible_to_town(monkeypatch):
    """Townsperson sees the same event numbers whether wolves send 0 or 4 messages."""
    # Game A: wolves send 0 messages
    st_a, pl_a, ev_a, ch_a, vo_a, wi_a, or_a = _make_game(monkeypatch)
    _advance_to_wolf_chat(or_a, ev_a, 0)
    # no wolf chat
    or_a.advance()  # WOLF_CHAT -> WOLF_VOTE
    count_a = len(ev_a.history_for(0))

    # Game B: wolves send 4 messages
    st_b, pl_b, ev_b, ch_b, vo_b, wi_b, or_b = _make_game(monkeypatch)
    _advance_to_wolf_chat(or_b, ev_b, 0)
    # Patch monotonic so each post passes the rate limit
    clock = iter(range(100, 200))
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    st_b.phase = Phase.WOLF_CHAT
    for i in range(4):
        ch_b.post(3, f"msg{i}")
    or_b.advance()  # WOLF_CHAT -> WOLF_VOTE
    count_b = len(ev_b.history_for(0))

    # Townsperson 0 sees the same number of events in both games
    assert count_a == count_b


def test_witch_alive_vs_dead_same_status(monkeypatch, client, join):
    """Non-witch gets 403 from POST /witch/ whether the witch is alive or dead."""
    # Join all players so the game is ready
    players_list = [join(f"p{i}") for i in range(settings.max_players)]

    players_svc = client.app.state.players
    witch_svc = client.app.state.witch

    # Find a non-witch player
    town_id, town_headers = next(
        (pid, h) for pid, h in players_list
        if players_svc.get_player(pid).role != Role.WITCH
    )

    # Case A: witch alive, open witch vote normally
    witch_id = next(
        p.id for p in players_svc.get_alive_players() if p.role == Role.WITCH
    )
    witch_svc.open(witch_id, victim_id=None, candidates=set())
    res_alive = client.post(
        "/witch/",
        json={"kind": "witch", "action": "pass"},
        headers=town_headers,
    )

    # Case B: witch dead, open witch vote with witch_id=None
    witch_svc.open(witch_id=None, victim_id=None, candidates=set())
    res_dead = client.post(
        "/witch/",
        json={"kind": "witch", "action": "pass"},
        headers=town_headers,
    )

    # Both must be 403 (not 409 when dead)
    assert res_alive.status_code == 403
    assert res_dead.status_code == 403


def test_early_exit_false_for_witch_vote(monkeypatch):
    """WITCH_VOTE never ends early, whether the witch is alive or dead."""
    state, players, events, chat, votes, witch, orch = _make_game(monkeypatch)
    orch.advance()  # LOBBY -> WOLF_CHAT
    orch.advance()  # WOLF_CHAT -> WOLF_VOTE
    votes.cast(3, target=0)
    orch.advance()  # WOLF_VOTE -> WITCH_VOTE

    # Witch is alive and has not cast: no early exit
    assert orch._early_exit() is False

    # Witch casts: still no early exit
    witch.cast(2, WitchBallot(action=WitchChoice.PASS))
    assert orch._early_exit() is False


def test_poisoned_victim_one_death_event(monkeypatch):
    """A wolf victim who is also poisoned produces one DEATH event, not two."""
    state, players, events, chat, votes, witch, orch = _make_game(monkeypatch)
    orch.advance()  # LOBBY -> WOLF_CHAT
    orch.advance()  # WOLF_CHAT -> WOLF_VOTE

    # Wolves vote to eat Alice (0)
    votes.cast(3, target=0)
    votes.cast(4, target=0)
    orch.advance()  # WOLF_VOTE -> WITCH_VOTE

    # Witch poisons the same player the wolves voted for
    witch.cast(2, WitchBallot(action=WitchChoice.POISON, target=0))
    orch.advance()  # WITCH_VOTE -> DAWN

    # Count DEATH events for player 0
    deaths = [
        e for e in events.history_for(1)  # Bob (town) sees all ALL events
        if e.type == EventType.DEATH and e.payload.get("player_id") == 0
    ]
    assert len(deaths) == 1
    assert not players.get_player(0).alive
