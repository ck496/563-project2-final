"""Vote routes: accept wolf/day ballots and witch decisions."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..models.vote import WitchBallot
from ..services.vote_service import VoteService
from ..services.witch_service import WitchService
from .deps_routes import get_vote_service, get_witch_service, get_current_player
from server.exceptions import WrongPhaseError, NotAllowedError, InvalidTargetError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["votes"])


class VoteRequest(BaseModel):
    """Body for POST /vote/: target only, identity comes from the token."""
    target: int = Field(description="Player id to vote for")


@router.post("/vote/", status_code=202)
async def post_vote(
    req: VoteRequest,
    player_id: int = Depends(get_current_player),
    votes: VoteService = Depends(get_vote_service),
):
    """Cast or replace a wolf-vote or day-vote ballot."""
    # 1. Delegate to VoteService; it checks eligibility and target
    try:
        votes.cast(player_id, req.target)
    except WrongPhaseError:
        raise HTTPException(status_code=409, detail="No vote is open")
    except NotAllowedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except InvalidTargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 2. Log without vote count (count of secret voters leaks info)
    logger.info("vote received")
    return {"message": "recorded"}


@router.post("/witch/", status_code=202)
async def post_witch(
    ballot: WitchBallot,
    player_id: int = Depends(get_current_player),
    witch: WitchService = Depends(get_witch_service),
):
    """Cast or replace the witch's save/poison/pass decision."""
    # 1. Delegate to WitchService
    try:
        witch.cast(player_id, ballot)
    except WrongPhaseError:
        raise HTTPException(status_code=409, detail="Witch vote is not open")
    except NotAllowedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except InvalidTargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 2. No identity in logs to prevent leaking who voted
    logger.info("witch action received")
    return {"message": "recorded"}
