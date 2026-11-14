"""S4 checks: orchestrator drives a full game from LOBBY to GAME_OVER."""
import asyncio
import random

from server.config import settings
from server.models.enums import Audience, EventType, Phase, Role, WitchChoice
from server.models.game_state import GameState
from server.models.vote import WitchBallot
from server.services.auth_service import AuthService
from server.services.chat_service import ChatService
from server.services.event_service import EventService
from server.services.game_orchestrator import GameOrchestrator
from server.services.player_service import PlayerService
from server.services.vote_service import VoteService
from server.services.presence_service import PresenceService
from server.services.witch_service import WitchService


def _make_game(monkeypatch, tmp_path):
    """Build services and 5 players with deterministic roles.

    No-shuffle gives pool [WOLF, WOLF, WITCH, TOWN, TOWN], pop() assigns:
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
    return state, players, events, votes, witch, orch


def test_full_game_town_wins(monkeypatch, tmp_path):
    """advance() in a loop with scripted votes reaches GAME_OVER, town wins."""
    state, players, events, votes, witch, orch = _make_game(monkeypatch, tmp_path)

    # LOBBY -> WOLF_CHAT (night 1)
    assert orch.advance() == Phase.WOLF_CHAT
    assert state.day_num == 1

    # WOLF_CHAT -> WOLF_VOTE
    assert orch.advance() == Phase.WOLF_VOTE
    votes.cast(3, target=0)
    votes.cast(4, target=0)

    # WOLF_VOTE -> WITCH_VOTE (victim=0)
    assert orch.advance() == Phase.WITCH_VOTE
    # Witch saves player 0
    witch.cast(2, WitchBallot(action=WitchChoice.SAVE))

    # WITCH_VOTE -> DAWN (saved, no deaths)
    assert orch.advance() == Phase.DAWN
    assert players.get_player(0).alive

    # DAWN -> DAY_CHAT
    assert orch.advance() == Phase.DAY_CHAT

    # DAY_CHAT -> DAY_VOTE
    assert orch.advance() == Phase.DAY_VOTE
    # Town hangs wolf 3
    votes.cast(0, target=3)
    votes.cast(1, target=3)
    votes.cast(2, target=3)
    votes.cast(4, target=3)

    # DAY_VOTE -> DUSK (wolf 3 hanged)
    assert orch.advance() == Phase.DUSK
    assert not players.get_player(3).alive
    assert state.hanged_id == 3

    # DUSK -> WOLF_CHAT (night 2, wolf 4 still alive)
    assert orch.advance() == Phase.WOLF_CHAT
    assert state.day_num == 2
    assert state.hanged_id is None

    # WOLF_CHAT -> WOLF_VOTE
    assert orch.advance() == Phase.WOLF_VOTE
    votes.cast(4, target=0)

    # WOLF_VOTE -> WITCH_VOTE (victim=0)
    assert orch.advance() == Phase.WITCH_VOTE
    # Witch poisons wolf 4 (save already used)
    witch.cast(2, WitchBallot(action=WitchChoice.POISON, target=4))

    # WITCH_VOTE -> DAWN (player 0 dies, wolf 4 poisoned)
    assert orch.advance() == Phase.DAWN
    assert not players.get_player(0).alive
    assert not players.get_player(4).alive

    # DAWN -> GAME_OVER (no wolves alive, town wins)
    assert orch.advance() == Phase.GAME_OVER
    assert state.winner == Role.TOWNSPERSON


def test_phase_changed_events_to_all(monkeypatch, tmp_path):
    """Every advance() publishes PHASE_CHANGED to ALL."""
    state, players, events, votes, witch, orch = _make_game(monkeypatch, tmp_path)

    # Run through several phases
    orch.advance()  # WOLF_CHAT
    orch.advance()  # WOLF_VOTE
    votes.cast(3, target=0)
    orch.advance()  # WITCH_VOTE
    witch.cast(2, WitchBallot(action=WitchChoice.PASS))
    orch.advance()  # DAWN
    orch.advance()  # DAY_CHAT

    # Check via history_for: player 0 (townsperson) sees all ALL-audience events
    history = events.history_for(0)
    phase_events = [e for e in history if e.type == EventType.PHASE_CHANGED]
    assert len(phase_events) == 5
    for e in phase_events:
        assert e.audience == Audience.ALL


def test_players_route_no_roles(client, join):
    """GET /players/ returns id, name, alive for each player (no roles exposed)."""
    pid, headers = join("Tester")
    res = client.get("/players/", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert any(p["id"] == pid and p["name"] == "Tester" for p in body)
    # No role field exposed
    for p in body:
        assert "role" not in p


def test_reset_clears_state(monkeypatch, tmp_path):
    """_reset_all() returns all services to fresh state for a new game."""
    state, players, events, votes, witch, orch = _make_game(monkeypatch, tmp_path)

    # Play to GAME_OVER using a quick path: no votes each round
    orch.advance()  # LOBBY -> WOLF_CHAT
    orch.advance()  # WOLF_CHAT -> WOLF_VOTE
    # No wolf votes cast, so no victim
    orch.advance()  # WOLF_VOTE -> WITCH_VOTE
    orch.advance()  # WITCH_VOTE -> DAWN (no deaths)
    orch.advance()  # DAWN -> DAY_CHAT (no winner yet)
    orch.advance()  # DAY_CHAT -> DAY_VOTE
    # No day votes cast, nobody hanged
    orch.advance()  # DAY_VOTE -> DUSK
    # Hang wolves manually to end the game
    players.kill(3)
    players.kill(4)
    orch.advance()  # DUSK -> GAME_OVER (no wolves alive)
    assert state.phase == Phase.GAME_OVER
    assert state.winner == Role.TOWNSPERSON

    # Reset
    orch._reset_all()

    # Verify fresh state
    assert state.phase == Phase.LOBBY
    assert state.day_num == 0
    assert state.winner is None
    assert state.hanged_id is None
    assert state.phase_ends_at is None
    assert len(players.get_alive_players()) == 0
    assert len(players.roles_pool) == settings.max_players


def test_failed_transition_resets_game(monkeypatch, tmp_path):
    """B5: if advance() raises, _run_one_game logs and resets to LOBBY."""
    state, players, events, votes, witch, orch = _make_game(monkeypatch, tmp_path)

    # Lobby is full (5 players added by _make_game), so the lobby wait exits immediately.
    # Patch advance to raise on the first call (leaving LOBBY).
    monkeypatch.setattr(orch, "advance", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    # _run_one_game should not propagate the exception
    asyncio.run(orch._run_one_game())

    # After the failure, reset_all should have run
    assert state.phase == Phase.LOBBY
    assert state.day_num == 0
    assert len(players.get_alive_players()) == 0
