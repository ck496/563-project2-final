"""Shared fixtures: a small game, a test client, and a join helper."""
import pytest
from fastapi.testclient import TestClient

from server.config import settings
from server.main import app


@pytest.fixture
def client(monkeypatch):
    """Test client for a 5 player game (2 wolves, 1 witch, 2 town)."""
    # set sizes before the lifespan runs, since services read settings when built
    monkeypatch.setattr(settings, "max_wolves", 2)
    monkeypatch.setattr(settings, "max_witch", 1)
    monkeypatch.setattr(settings, "max_town", 2)
    # the with block runs the lifespan, so app.state holds fresh services per test
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def join(client):
    """Returns join(name): joins a player and gives back (player_id, auth headers)."""
    def _join(name: str) -> tuple[int, dict]:
        res = client.post("/join/", json={"player_name": name, "join_code": settings.join_code})
        body = res.json()
        return body["player_id"], {"Authorization": f"Bearer {body['token']}"}
    return _join
