"""Heartbeat route for player liveness."""
import logging

from fastapi import APIRouter, Depends, Response

from ..services.presence_service import PresenceService
from .deps_routes import get_current_player, get_presence_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["presence"])


@router.post("/heartbeat/", status_code=202)
async def heartbeat(
    player_id: int = Depends(get_current_player),
    presence: PresenceService = Depends(get_presence_service),
) -> Response:
    """Record a heartbeat for the authenticated player."""
    presence.touch(player_id)
    return Response(status_code=202)
