"""S2 checks: chat delivery, phase gating, dead-player rejection, sanitization."""
from server.config import settings
from server.models.enums import Audience, Phase, Role


def _fill_lobby(join):
    """Join all players and return list of (player_id, headers)."""
    return [join(f"p{i}") for i in range(settings.max_players)]


def _find_by_role(players_svc, players, role):
    """Return (player_id, headers) for the first player with the given role."""
    return next(
        (pid, h) for pid, h in players
        if players_svc.get_player(pid).role == role
    )


def test_wolf_chat_hidden_from_townsperson(client, join):
    """A wolf's WOLF_CHAT message appears in a wolf's history but not a townsperson's."""
    players = _fill_lobby(join)
    # Until S4 exists, set phase directly
    client.app.state.game_state.phase = Phase.WOLF_CHAT
    client.app.state.game_state.day_num = 1

    players_svc = client.app.state.players
    wolf_id, wolf_h = _find_by_role(players_svc, players, Role.WEREWOLF)
    town_id, _ = _find_by_role(players_svc, players, Role.TOWNSPERSON)

    res = client.post("/chat/", json={"text": "eat p3"}, headers=wolf_h)
    assert res.status_code == 202

    events_svc = client.app.state.events
    wolf_hist = events_svc.history_for(wolf_id)
    town_hist = events_svc.history_for(town_id)

    assert any(e.audience == Audience.WOLVES for e in wolf_hist)
    assert not any(e.audience == Audience.WOLVES for e in town_hist)


def test_chat_in_lobby_returns_409(client, join):
    """Posting a chat during LOBBY is rejected with 409 (wrong phase)."""
    _, headers = join("alice")
    # phase is LOBBY by default
    res = client.post("/chat/", json={"text": "hello"}, headers=headers)
    assert res.status_code == 409


def test_dead_player_returns_403(client, join):
    """A dead player cannot chat, even in a chat phase."""
    players = _fill_lobby(join)
    client.app.state.game_state.phase = Phase.DAY_CHAT
    client.app.state.game_state.day_num = 1

    players_svc = client.app.state.players
    pid, headers = players[0]
    players_svc.kill(pid)

    res = client.post("/chat/", json={"text": "from the grave"}, headers=headers)
    assert res.status_code == 403


def test_last_words_in_dusk(client, join):
    """Hanged player can chat in DUSK; living and other dead players cannot."""
    players = _fill_lobby(join)
    state = client.app.state.game_state
    players_svc = client.app.state.players
    state.phase = Phase.DUSK
    state.day_num = 1

    hanged_id, hanged_h = players[0]
    _, living_h = players[1]
    # Kill the hanged player and set hanged_id (mirrors orchestrator)
    players_svc.kill(hanged_id)
    state.hanged_id = hanged_id

    # Kill another player to test that arbitrary dead players are rejected
    other_dead_id, other_dead_h = players[2]
    players_svc.kill(other_dead_id)  # a second dead player, not the hanged one

    # Hanged player gets 202
    res = client.post("/chat/", json={"text": "last words"}, headers=hanged_h)
    assert res.status_code == 202

    # Living player gets 403
    res = client.post("/chat/", json={"text": "nope"}, headers=living_h)
    assert res.status_code == 403

    # Another dead player gets 403
    res = client.post("/chat/", json={"text": "me too"}, headers=other_dead_h)
    assert res.status_code == 403


def test_ansi_escape_stripped(client, join):
    """ANSI escape sequences are stripped from chat text before publishing."""
    players = _fill_lobby(join)
    client.app.state.game_state.phase = Phase.DAY_CHAT
    client.app.state.game_state.day_num = 1

    pid, headers = players[0]

    res = client.post("/chat/", json={"text": "\x1b[2Jhello"}, headers=headers)
    assert res.status_code == 202

    # Check the published event's payload has the escape stripped
    events_svc = client.app.state.events
    chat_events = [
        e for e in events_svc.history_for(pid)
        if e.payload.get("author_id") == pid
    ]
    assert len(chat_events) == 1
    assert "\x1b" not in chat_events[0].payload["text"]
    assert chat_events[0].payload["text"] == "hello"
