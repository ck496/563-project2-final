from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..services.player_service import PlayerService
from ..services.auth_service import AuthService
from ..services.presence_service import PresenceService
from .deps_routes import get_auth_service, get_player_service, get_current_player, get_presence_service
from server.config import settings
from server.exceptions import GameFullError, DuplicateNameError, PlayerNotFoundError
import hmac
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["players"])        # tags group endpoints in /docs

class JoinRequest(BaseModel):
    # Only letters, digits, and underscores to prevent terminal escape injection.
    player_name: str = Field(min_length=2, max_length=15, pattern=r"^[A-Za-z0-9_]+$")
    join_code: str = Field(max_length=64)


@router.post("/join/")
async def join_game(req: JoinRequest,
                    player_service: PlayerService = Depends(get_player_service),
                    auth_service: AuthService = Depends(get_auth_service),
                    presence: PresenceService = Depends(get_presence_service)):
    player_name = req.player_name
    # 1. Validate join code (bytes, because the str form rejects non-ASCII input)
    if not hmac.compare_digest(req.join_code.encode(), settings.join_code.encode()):
        logger.warning(f"Join failed: incorrect join code for player_name='{player_name}'")
        raise HTTPException(status_code=403, detail="Incorrect join code")

    # 2. Create player with exception handling
    try:
        player = player_service.add_player(player_name)
    except GameFullError:
        logger.warning(f"Join failed: game is full, rejected player_name='{player_name}'")
        raise HTTPException(status_code=409, detail="Game is full")
    except DuplicateNameError:
        logger.warning(f"Join failed: duplicate name '{player_name}'")
        raise HTTPException(status_code=409, detail="Name already taken")

    # 3. Issue token and start presence tracking so new players are not stale
    token = auth_service.issue_token(player.id)
    presence.touch(player.id)
    logger.info(f"Player joined successfully: player_id={player.id}, player_name='{player_name}'")

    return {"message": "player joined", "player_id": player.id, "token": token}

@router.get("/me/info/")
async def get_my_info(
    player_id: int = Depends(get_current_player),
    player_service: PlayerService = Depends(get_player_service)
):
    # 1. Authenticate via token (get_current_player)
    try:
        player = player_service.get_player(player_id)
    except PlayerNotFoundError:
        logger.error("Info request failed: player not found")
        raise HTTPException(status_code=404, detail="Player not found")

    # 2. Return view_for (role, teammates if wolf) plus the name
    view = player_service.view_for(player_id)
    view["name"] = player.name
    logger.info("info requested")
    return view


@router.get("/players/")
async def list_players(
    _player_id: int = Depends(get_current_player),
    player_service: PlayerService = Depends(get_player_service),
):
    """Public player list: id, name, alive. No roles exposed."""
    # Iterate all assigned ids to include dead players too
    result = []
    for pid in range(player_service.next_id):
        try:
            p = player_service.get_player(pid)
            result.append({"id": p.id, "name": p.name, "alive": p.alive})
        except PlayerNotFoundError:
            continue
    return result


