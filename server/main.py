from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging

import asyncio

from .config import settings
from .services.auth_service import AuthService
from .services.chat_service import ChatService
from .services.player_service import PlayerService
from .services.event_service import EventService
from .services.vote_service import VoteService
from .services.witch_service import WitchService
from .services.game_orchestrator import GameOrchestrator
from .services.presence_service import PresenceService
from .models.game_state import GameState
from .routes import player_routes, event_routes, chat_routes, vote_routes, presence_routes



# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s - %(name)s:: %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager: runs once at startup and once at shutdown.
    - Code before yield runs when FastAPI starts (before accepting requests)
    - Code after yield runs when FastAPI shuts down (after all requests finish)
    - app.state: FastAPI's state object for storing shared instances (services, DB connections, etc.)
      These instances are accessible in routes via dependency injection
    """
    # Startup: build services in dependency order (one process = one game)
    app.state.players = PlayerService()
    app.state.auth = AuthService()
    app.state.game_state = GameState(day_num=0)
    app.state.events = EventService(app.state.players)
    app.state.chat = ChatService(
        app.state.game_state, app.state.players, app.state.events
    )
    app.state.votes = VoteService()
    app.state.witch = WitchService()
    app.state.presence = PresenceService()
    # Orchestrator is last because it depends on all other services
    app.state.orchestrator = GameOrchestrator(
        app.state.game_state,
        app.state.players,
        app.state.events,
        app.state.votes,
        app.state.witch,
        app.state.auth,
        app.state.chat,
        app.state.presence,
    )
    logger.info("Services initialized")

    logger.info(f"GAME SETTINGS: max_wolves:{settings.max_wolves}, max_witch:{settings.max_witch}, max_town:{settings.max_town}... Total:{settings.max_players}")

    # Start the game loop as a background task
    game_task = asyncio.create_task(app.state.orchestrator.run())
    yield
    # Shutdown: close SSE streams first so uvicorn can finish requests
    app.state.events.shutdown()
    game_task.cancel()
    try:
        await game_task
    except asyncio.CancelledError:
        pass
    app.state.auth.revoke_all_tokens()
    logger.info("Services cleaned up")


def create_app() -> FastAPI:
    """App factory pattern for dependency injection and clean separation"""
    app = FastAPI(title="Werewolves Democracy", lifespan=lifespan)

    # Register routers
    app.include_router(player_routes.router)
    app.include_router(event_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(vote_routes.router)
    app.include_router(presence_routes.router)

    return app



app = create_app()


@app.get("/")
async def root():
    return {"message": "Welcome to Werewolves Democracy!"}

# run:  uv run fastapi dev
# # Self-docs available at http://127.0.0.1:8000/docs or /redoc    