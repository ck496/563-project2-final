"""Tests for client command parsing."""
from client.commands import parse


def test_vote():
    """Slash vote with a name returns a vote tuple."""
    assert parse("/vote Ana") == ("vote", {"name": "Ana"})


def test_witch_commands():
    """Save, poison, and pass all produce witch tuples."""
    assert parse("/save") == ("witch", {"action": "save"})
    assert parse("/poison Ana") == ("witch", {"action": "poison", "name": "Ana"})
    assert parse("/pass") == ("witch", {"action": "pass"})


def test_chat():
    """Bare text is treated as a chat message."""
    assert parse("I think its chris!") == ("chat", {"text": "I think its chris!"})


def test_unknown_command():
    """Unrecognized slash commands return unknown."""
    assert parse("/foo") == ("unknown", {})
    # Missing arg for /vote also counts as unknown
    assert parse("/vote") == ("unknown", {})
