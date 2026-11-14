from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..services.auth_service import AuthService
from ..services.chat_service import ChatService
from ..services.player_service import PlayerService
from ..services.event_service import EventService
from ..services.vote_service import VoteService
from ..services.witch_service import WitchService
from ..services.game_orchestrator import GameOrchestrator
from ..services.presence_service import PresenceService
from ..models.game_state import GameState
from server.exceptions import InvalidTokenError

bearer = HTTPBearer()

def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth           # the instance built in lifespan

def get_player_service(request: Request) -> PlayerService:
    return request.app.state.players

def get_event_service(request: Request) -> EventService:
    return request.app.state.events

def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat

def get_vote_service(request: Request) -> VoteService:
    return request.app.state.votes

def get_witch_service(request: Request) -> WitchService:
    return request.app.state.witch

def get_game_state(request: Request) -> GameState:
    return request.app.state.game_state

def get_presence_service(request: Request) -> PresenceService:
    return request.app.state.presence

def get_game_orchestrator(request: Request) -> GameOrchestrator:
    return request.app.state.orchestrator

def get_current_player(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    auth: AuthService = Depends(get_auth_service),
) -> int:
    try:
        return auth.resolve_token(creds.credentials)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")