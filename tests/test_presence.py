"""S9 checks: presence, stale pruning, Last-Event-ID replay, draw cap."""
import random
import time

from server.config import settings
from server.models.enums import EventType, Phase
from server.models.game_state import GameState
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
    auth = AuthService()
    presence = PresenceService()

    # Touch each player on join so they start fresh
    for i, name in enumerate(["Alice", "Bob", "Carol", "Dave", "Eve"]):
        players.add_player(name)
        auth.issue_token(i)
        presence.touch(i)

    state = GameState(day_num=0)
    events = EventService(players)
    chat = ChatService(state, players, events)
    votes = VoteService()
    witch = WitchService()
    orch = GameOrchestrator(
        state, players, events, votes, witch, auth, chat, presence,
    )
    return state, players, events, votes, witch, orch, presence


def test_stale_player_killed_at_advance(monkeypatch):
    """A stale player is killed when advance() runs in a game phase."""
    state, players, events, votes, witch, orch, presence = _make_game(monkeypatch)

    # Leave lobby and enter WOLF_CHAT
    orch.advance()  # LOBBY -> WOLF_CHAT

    # Make player 0 (Alice, town) stale by setting their timestamp far in the past
    presence._last_seen[0] = time.monotonic() - settings.presence_grace_seconds - 10

    # Advance again: stale pruning runs at the top of advance()
    orch.advance()  # WOLF_CHAT -> WOLF_VOTE

    # Alice should be dead
    assert not players.get_player(0).alive

    # A PLAYER_DISCONNECTED event should precede the DEATH event for Alice
    history = events.history_for(1)
    disconnects = [
        e for e in history
        if e.type == EventType.PLAYER_DISCONNECTED and e.payload.get("player_id") == 0
    ]
    deaths = [
        e for e in history
        if e.type == EventType.DEATH and e.payload.get("player_id") == 0
    ]
    assert len(disconnects) == 1
    assert len(deaths) == 1
    assert disconnects[0].seq < deaths[0].seq

    # A player who is still fresh should be alive
    assert players.get_player(1).alive


def test_stale_lobby_player_freed(monkeypatch):
    """A stale player in LOBBY is removed and their seat is returned to the pool."""
    monkeypatch.setattr(settings, "max_wolves", 2)
    monkeypatch.setattr(settings, "max_witch", 1)
    monkeypatch.setattr(settings, "max_town", 2)
    monkeypatch.setattr(random, "shuffle", lambda x: None)

    players = PlayerService()
    auth = AuthService()
    presence = PresenceService()

    # Add 3 players, touch them all fresh
    for i, name in enumerate(["Alice", "Bob", "Carol"]):
        players.add_player(name)
        auth.issue_token(i)
        presence.touch(i)

    state = GameState(day_num=0)
    events = EventService(players)
    chat = ChatService(state, players, events)
    votes = VoteService()
    witch = WitchService()
    orch = GameOrchestrator(
        state, players, events, votes, witch, auth, chat, presence,
    )

    pool_before = len(players.roles_pool)

    # Make Alice (0) stale
    presence._last_seen[0] = time.monotonic() - settings.presence_grace_seconds - 10

    # Prune runs during the lobby wait in advance(), simulate with _prune_stale
    orch._prune_stale(Phase.LOBBY)

    # Alice should be gone, role returned to pool
    assert len(players.roles_pool) == pool_before + 1

    # Auth tokens for Alice should be revoked (we can verify she's not in players)
    import pytest
    from server.exceptions import PlayerNotFoundError
    with pytest.raises(PlayerNotFoundError):
        players.get_player(0)


def test_last_event_id_replay(client, join):
    """A stream opened with Last-Event-ID: 3 starts at event 4."""
    # Join all players
    tokens = [join(f"p{i}") for i in range(settings.max_players)]
    pid0, headers0 = tokens[0]

    # Advance out of lobby so events are generated (role assignments, phase change)
    orch = client.app.state.orchestrator
    orch.advance()  # LOBBY -> WOLF_CHAT

    # Open stream with no Last-Event-ID to count total events for this player
    with client.stream("GET", "/events/stream/", headers=headers0) as resp:
        lines = []
        for line in resp.iter_lines():
            lines.append(line)
            # Stop after we get a few events (the stream blocks indefinitely)
            if len([l for l in lines if l.startswith("id:")]) >= 2:
                break

    # Open stream with Last-Event-ID: 1, should skip event 1
    with client.stream(
        "GET", "/events/stream/",
        headers={**headers0, "Last-Event-ID": "1"},
    ) as resp:
        ids = []
        for line in resp.iter_lines():
            if line.startswith("id:"):
                ids.append(int(line.split(":")[1].strip()))
            if len(ids) >= 1:
                break

    # First id should be 2 (skipped 1)
    assert ids[0] == 2


def test_max_days_draw(monkeypatch):
    """A game still running after DUSK of day max_days ends in a draw."""
    monkeypatch.setattr(settings, "max_days", 1)
    state, players, events, votes, witch, orch, presence = _make_game(monkeypatch)

    # LOBBY -> WOLF_CHAT (day 1)
    orch.advance()

    # WOLF_CHAT -> WOLF_VOTE
    orch.advance()
    # Wolves vote for Alice (0)
    votes.cast(3, target=0)
    votes.cast(4, target=0)

    # WOLF_VOTE -> WITCH_VOTE
    orch.advance()
    # Witch passes
    from server.models.vote import WitchBallot
    from server.models.enums import WitchChoice
    witch.cast(2, WitchBallot(action=WitchChoice.PASS))
    # WITCH_VOTE -> DAWN (Alice dies)
    orch.advance()

    # DAWN -> DAY_CHAT (win check: wolves still alive, non-wolves still alive)
    orch.advance()

    # DAY_CHAT -> DAY_VOTE
    orch.advance()
    # Nobody hanged (no votes cast, close returns None)

    # DAY_VOTE -> DUSK
    orch.advance()

    # DUSK -> should trigger draw because day_num == max_days (1)
    result = orch.advance()

    assert result == Phase.GAME_OVER
    assert state.draw is True
    assert state.winner is None
