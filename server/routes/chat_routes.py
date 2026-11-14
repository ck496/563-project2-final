"""Chat route: accept a message and publish it through ChatService."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..services.chat_service import ChatService
from .deps_routes import get_chat_service, get_current_player
from server.exceptions import NotAllowedError, RateLimitError, WrongPhaseError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    """Body for POST /chat/: text only, identity comes from the token."""
    text: str = Field(min_length=1, max_length=500)


@router.post("/chat/", status_code=202)
async def post_chat(
    req: ChatRequest,
    player_id: int = Depends(get_current_player),
    chat: ChatService = Depends(get_chat_service),
):
    """Accept a chat message from the authenticated player."""
    # 1. Delegate validation and publishing to ChatService
    try:
        chat.post(player_id, req.text)
    except WrongPhaseError:
        raise HTTPException(status_code=409, detail="Chat not allowed in this phase")
    except NotAllowedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RateLimitError:
        raise HTTPException(status_code=429, detail="Rate limit: 1 message per second")

    # 2. Return acknowledgment only, never echo other players' state
    return {"message": "sent"}
