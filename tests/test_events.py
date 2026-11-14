"""S1 checks: audience filtering and stream cap."""

import asyncio
import pytest
from server.config import settings
from server.models.enums import Audience, EventType, Role


def test_wolves_event_hidden_from_townsperson(client, join):
    """A townsperson's history must not contain a WOLVES event."""
    # join all 5 players so roles are assigned
    players = [join(f"p{i}") for i in range(settings.max_players)]

    events_svc = client.app.state.events
    players_svc = client.app.state.players

    # publish a wolves-only event
    events_svc.publish(EventType.CHAT, Audience.WOLVES, {"text": "secret"})

    # find a townsperson
    town_id = next(
        pid for pid, _ in players
        if players_svc.get_player(pid).role == Role.TOWNSPERSON
    )
    # find a wolf
    wolf_id = next(
        pid for pid, _ in players
        if players_svc.get_player(pid).role == Role.WEREWOLF
    )

    town_history = events_svc.history_for(town_id)
    wolf_history = events_svc.history_for(wolf_id)

    assert not any(e.audience == Audience.WOLVES for e in town_history)
    assert any(e.audience == Audience.WOLVES for e in wolf_history)


def test_player_event_reaches_only_target(client, join):
    """A PLAYER event reaches only the targeted player."""
    p0_id, _ = join("alpha")
    p1_id, _ = join("bravo")

    events_svc = client.app.state.events
    events_svc.publish(
        EventType.ROLE_ASSIGNED, Audience.PLAYER,
        payload={"role": "werewolf"}, to_player_id=p0_id,
    )

    assert len(events_svc.history_for(p0_id)) == 1
    assert len(events_svc.history_for(p1_id)) == 0


def test_stream_cap_closes_oldest(client, join, monkeypatch):
    """B4: opening a third stream closes the oldest one."""
    monkeypatch.setattr(settings, "max_streams_per_player", 2)
    pid, _ = join("alpha")
    events_svc = client.app.state.events

    async def _run():
        g1 = events_svc.stream_for(pid)
        g2 = events_svc.stream_for(pid)
        g3 = events_svc.stream_for(pid)

        # Each generator registers its queue on first advance.
        # Run them as tasks so they block concurrently on queue.get().
        t1 = asyncio.ensure_future(g1.__anext__())
        await asyncio.sleep(0)  # let t1 register its queue
        t2 = asyncio.ensure_future(g2.__anext__())
        await asyncio.sleep(0)  # let t2 register its queue
        t3 = asyncio.ensure_future(g3.__anext__())
        await asyncio.sleep(0)  # t3 registers, evicts g1's queue with None

        # g1 received the sentinel so t1 should raise StopAsyncIteration
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(t1, timeout=0.5)

        # Two queues remain
        assert len(events_svc._queues[pid]) == 2

        # g2 and g3 are still alive (stream_for now yields (n, event) tuples)
        events_svc.publish(EventType.CHAT, Audience.ALL, {"text": "hi"})
        n2, e2 = await asyncio.wait_for(t2, timeout=0.5)
        n3, e3 = await asyncio.wait_for(t3, timeout=0.5)
        assert e2.seq == e3.seq

    asyncio.run(_run())


