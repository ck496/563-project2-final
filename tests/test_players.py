"""Join and identity: the key paths of player_routes."""
from server.config import settings


def test_join_then_me_returns_own_player(client, join):
    player_id, headers = join("ana")
    res = client.get("/me/info/", headers=headers)
    assert res.status_code == 200
    assert res.json()["player_id"] == player_id


def test_wrong_join_code_is_rejected(client):
    res = client.post("/join/", json={"player_name": "ana", "join_code": "wrong"})
    assert res.status_code == 403


def test_bad_token_is_rejected(client):
    res = client.get("/me/info/", headers={"Authorization": "Bearer nope"})
    assert res.status_code == 401


def test_game_full_is_rejected(client, join):
    for i in range(settings.max_players):
        join(f"player{i}")
    res = client.post("/join/", json={"player_name": "late", "join_code": settings.join_code})
    assert res.status_code == 409


def test_non_ascii_join_code_is_rejected(client):
    """Non-ASCII join code returns 403, not 500 (B3)."""
    res = client.post("/join/", json={"player_name": "ana", "join_code": "caf\u00e9"})
    assert res.status_code == 403


def test_bad_names_are_rejected(client):
    """Names with escapes, control chars, spaces, or hyphens get 422."""
    code = settings.join_code
    for bad in ["a\x1b[2J", "a\rz", "  ", "Ana Maria", "a-b"]:
        res = client.post("/join/", json={"player_name": bad, "join_code": code})
        assert res.status_code == 422, f"expected 422 for {bad!r}, got {res.status_code}"
    # A valid name still works
    res = client.post("/join/", json={"player_name": "good_name", "join_code": code})
    assert res.status_code == 200
