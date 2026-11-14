"""SSE stream route for game events."""
import json
import logging

from fastapi import APIRouter, Depends, Header
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ..services.event_service import EventService
from .deps_routes import get_current_player, get_event_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])


@router.get("/events/stream/", response_class=EventSourceResponse)
async def event_stream(
    player_id: int = Depends(get_current_player),
    events: EventService = Depends(get_event_service),
    last_event_id: int = Header(default=0, alias="Last-Event-ID"),
):
    """SSE stream: replays history then pushes live events."""
    if last_event_id > 0:
        logger.info("stream reconnected after=%d", last_event_id)
    else:
        logger.info("stream opened")
    async for n, event in events.stream_for(player_id, after=last_event_id):
        # Send per-player position, not global seq (global seq leaks event count)
        yield ServerSentEvent(
            data=json.dumps(event.model_dump(mode="json", exclude={"seq"})),
            event=event.type,
            id=str(n),
        )
