"""Game orchestrator: drives the phase loop from LOBBY to GAME_OVER."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from ..models.enums import Audience, EventType, Phase, Role
from ..models.game_state import GameState
from ..services.auth_service import AuthService
from ..services.chat_service import ChatService
from ..services.player_service import PlayerService
from ..services.event_service import EventService
from ..services.vote_service import VoteService
from ..services.witch_service import WitchService
from ..services.presence_service import PresenceService
from server.config import settings

logger = logging.getLogger(__name__)

# Duration of each timed phase, keyed by phase
_DURATIONS: dict[Phase, str] = {
    Phase.WOLF_CHAT:  "wolf_chat_seconds",
    Phase.WOLF_VOTE:  "wolf_vote_seconds",
    Phase.WITCH_VOTE: "witch_vote_seconds",
    Phase.DAWN:       "dawn_seconds",
    Phase.DAY_CHAT:   "day_chat_seconds",
    Phase.DAY_VOTE:   "day_vote_seconds",
    Phase.DUSK:       "dusk_seconds",
}


class GameOrchestrator:
    """Runs the game loop: waits for a full lobby, then cycles phases until a winner."""

    def __init__(
        self,
        state: GameState,
        players: PlayerService,
        events: EventService,
        votes: VoteService,
        witch: WitchService,
        auth: AuthService,
        chat: ChatService,
        presence: PresenceService,
    ) -> None:
        self._state = state
        self._players = players
        self._events = events
        self._votes = votes
        self._witch = witch
        self._auth = auth
        self._chat = chat
        self._presence = presence
        # Track wolf victim across the WOLF_VOTE -> WITCH_VOTE boundary
        self._wolf_victim_id: int | None = None
        # All player ids, populated when leaving LOBBY (for GAME_OVER reveal)
        self._all_player_ids: list[int] = []

    # -- public API --

    def advance(self) -> Phase:
        """Execute one phase transition: close current, open next. No awaits."""
        leaving = self._state.phase

        # 0. Prune stale players at every phase boundary (R-11, R-13)
        self._prune_stale(leaving)

        # 1. Close the phase we are leaving
        next_phase = self._close_phase(leaving)

        # 2. If close_phase determined GAME_OVER, enter it
        if next_phase == Phase.GAME_OVER:
            self._enter_game_over()
            return Phase.GAME_OVER

        # 3. Enter the next phase
        self._open_phase(next_phase)
        return next_phase

    async def run(self) -> None:
        """Main game loop: lobby -> play -> game over -> reset -> repeat."""
        while True:
            await self._run_one_game()

    async def _run_one_game(self) -> None:
        """Run one full game. Resets on unexpected errors so the server stays up."""
        try:
            # Wait for a full lobby, pruning stale players each tick (R-13)
            while len(self._players.get_alive_players()) < settings.max_players:
                self._prune_stale(Phase.LOBBY)
                await asyncio.sleep(1.0)

            # Leave LOBBY
            self.advance()

            # Phase loop: sleep in 0.5s ticks, check early-exit each iteration (L-4)
            while self._state.phase != Phase.GAME_OVER:
                remaining = self._seconds_remaining()
                if remaining <= 0 or self._early_exit():
                    self.advance()
                else:
                    await asyncio.sleep(min(0.5, remaining))

            # Let clients read the game-over reveal, then reset for a new game
            await asyncio.sleep(settings.reset_delay_seconds)
        except Exception:
            # Log traceback but no player data (L-6), then reset for a new game
            logger.exception("game loop failed, resetting")
        self._reset_all()

    # -- private: phase transitions --

    def _close_phase(self, leaving: Phase) -> Phase:
        """Handle exit logic for the phase we are leaving. Returns the next phase."""
        if leaving == Phase.LOBBY:
            # Assign roles and bump day_num (R-2)
            self._state.day_num = 1
            # Capture all player ids for the GAME_OVER reveal
            self._all_player_ids = [p.id for p in self._players.get_alive_players()]
            for p in self._players.get_alive_players():
                self._events.publish(
                    type=EventType.ROLE_ASSIGNED,
                    audience=Audience.PLAYER,
                    payload=self._players.view_for(p.id),
                    to_player_id=p.id,
                )
            return Phase.WOLF_CHAT

        if leaving == Phase.WOLF_CHAT:
            # Open wolf vote: living wolves vote for a living non-wolf (R-3)
            all_wolves = set(self._players.get_wolves())
            alive = {p.id for p in self._players.get_alive_players()}
            alive_wolves = all_wolves & alive
            candidates = alive - all_wolves
            self._votes.open(Phase.WOLF_VOTE, alive_wolves, candidates)
            return Phase.WOLF_VOTE

        if leaving == Phase.WOLF_VOTE:
            # Close wolf vote, store victim for WITCH_VOTE close, open witch
            victim_id = self._votes.close()
            self._wolf_victim_id = victim_id
            alive = {p.id for p in self._players.get_alive_players()}
            # Find the witch (may be dead)
            witch_id = self._find_witch_id()
            allowed = self._witch.open(witch_id, victim_id, alive)
            # Publish prompt to the witch (if alive)
            if witch_id is not None:
                self._events.publish(
                    type=EventType.WITCH_PROMPT,
                    audience=Audience.WITCH,
                    payload={
                        "victim_id": victim_id,
                        "allowed": sorted(allowed),
                    },
                )
            return Phase.WITCH_VOTE

        if leaving == Phase.WITCH_VOTE:
            # Close witch, kill the dead (R-6)
            saved, poison_target = self._witch.close()
            # Use the victim stored when we closed the wolf vote
            wolf_victim = self._wolf_victim_id
            # Deduplicate: if the wolf victim is also poisoned, kill once
            deaths: list[int] = []
            if wolf_victim is not None and not saved:
                self._players.kill(wolf_victim)
                deaths.append(wolf_victim)
            if poison_target is not None and poison_target not in deaths:
                self._players.kill(poison_target)
                deaths.append(poison_target)
            # Announce each death once (R-6: roles not revealed until GAME_OVER)
            for pid in deaths:
                p = self._players.get_player(pid)
                self._events.publish(
                    type=EventType.DEATH,
                    audience=Audience.ALL,
                    payload={"player_id": pid, "name": p.name},
                )
            return Phase.DAWN

        if leaving == Phase.DAWN:
            # Win check (R-8)
            winner = self._check_winner()
            if winner is not None:
                self._state.winner = winner
                return Phase.GAME_OVER
            return Phase.DAY_CHAT

        if leaving == Phase.DAY_CHAT:
            # Open day vote: all living players vote for a living player (R-3)
            alive = {p.id for p in self._players.get_alive_players()}
            self._votes.open(Phase.DAY_VOTE, alive, alive)
            return Phase.DAY_VOTE

        if leaving == Phase.DAY_VOTE:
            # Close day vote, kill and announce, set hanged_id (R-7)
            hanged_id = self._votes.close()
            if hanged_id is not None:
                self._players.kill(hanged_id)
                p = self._players.get_player(hanged_id)
                self._events.publish(
                    type=EventType.DEATH,
                    audience=Audience.ALL,
                    payload={"player_id": hanged_id, "name": p.name},
                )
            self._state.hanged_id = hanged_id
            return Phase.DUSK

        if leaving == Phase.DUSK:
            # Clear hanged_id, win check, else next night (R-8, R-2)
            self._state.hanged_id = None
            winner = self._check_winner()
            if winner is not None:
                self._state.winner = winner
                return Phase.GAME_OVER
            # Safety cap: draw after max_days with no winner (R-14, D-13)
            if self._state.day_num >= settings.max_days:
                self._state.draw = True
                return Phase.GAME_OVER
            self._state.day_num += 1
            return Phase.WOLF_CHAT

        # Should never reach here
        return Phase.GAME_OVER

    def _open_phase(self, phase: Phase) -> None:
        """Set state and publish PHASE_CHANGED (L-3)."""
        self._state.phase = phase
        seconds = getattr(settings, _DURATIONS[phase])
        duration = timedelta(seconds=seconds)
        self._state.phase_ends_at = datetime.now(timezone.utc) + duration

        self._events.publish(
            type=EventType.PHASE_CHANGED,
            audience=Audience.ALL,
            payload={
                "phase": phase,
                "day_num": self._state.day_num,
                "ends_at": self._state.phase_ends_at.isoformat(),
            },
        )
        logger.info("phase=%s day=%d", phase, self._state.day_num)

    def _enter_game_over(self) -> None:
        """Publish GAME_OVER with winner and all roles."""
        self._state.phase = Phase.GAME_OVER
        self._state.phase_ends_at = None

        # Build role reveal for every player (ids captured when leaving LOBBY)
        roles = []
        for pid in self._all_player_ids:
            p = self._players.get_player(pid)
            roles.append({"player_id": p.id, "name": p.name, "role": p.role})

        self._events.publish(
            type=EventType.GAME_OVER,
            audience=Audience.ALL,
            payload={
                "winner": self._state.winner,
                "draw": self._state.draw,
                "players": roles,
            },
        )
        logger.info("game_over winner=%s draw=%s", self._state.winner, self._state.draw)

    def _reset_all(self) -> None:
        """Reset every service and GameState for a new game. No awaits (D-7)."""
        # 1. Close SSE streams so clients disconnect cleanly
        self._events.shutdown()
        # 2. Reset services (all are idle after GAME_OVER)
        self._players.remove_all_players()
        self._auth.revoke_all_tokens()
        self._votes.reset()
        self._witch.reset()
        self._chat.reset()
        self._presence.reset()
        self._events.reset()
        # 3. Reset GameState (D-1: only orchestrator writes to it)
        self._state.phase = Phase.LOBBY
        self._state.day_num = 0
        self._state.phase_ends_at = None
        self._state.winner = None
        self._state.hanged_id = None
        self._state.draw = False
        # 4. Reset orchestrator's own tracking state
        self._wolf_victim_id = None
        self._all_player_ids = []
        logger.info("all services reset, ready for new game")

    # -- private: presence --

    def _prune_stale(self, phase: Phase) -> None:
        """Remove or kill stale players at a phase boundary."""
        stale_ids = self._presence.stale(settings.presence_grace_seconds)
        for pid in stale_ids:
            if phase == Phase.LOBBY:
                # Return seat and role to the pool (R-13)
                self._players.remove_player(pid)
                self._auth.revoke_player(pid)
                self._presence.forget(pid)
                logger.info("stale player removed from lobby")
            else:
                # Kill disconnected players during the game (R-11)
                p = self._players.get_player(pid)
                if not p.alive:
                    # Already dead, just clean presence
                    self._presence.forget(pid)
                    continue
                # Announce disconnect before the kill so players know why
                self._events.publish(
                    type=EventType.PLAYER_DISCONNECTED,
                    audience=Audience.ALL,
                    payload={"player_id": pid, "name": p.name},
                )
                self._players.kill(pid)
                self._presence.forget(pid)
                self._events.publish(
                    type=EventType.DEATH,
                    audience=Audience.ALL,
                    payload={"player_id": pid, "name": p.name},
                )
                logger.info("stale player killed")

    # -- private: helpers --

    def _find_witch_id(self) -> int | None:
        """Return the witch's player id if alive, else None."""
        for p in self._players.get_alive_players():
            if p.role == Role.WITCH:
                return p.id
        return None

    def _check_winner(self) -> Role | None:
        """R-8: no living wolves -> town wins; no living non-wolves -> wolves win."""
        alive = self._players.get_alive_players()
        wolves_alive = [p for p in alive if p.role == Role.WEREWOLF]
        non_wolves_alive = [p for p in alive if p.role != Role.WEREWOLF]

        if not wolves_alive:
            return Role.TOWNSPERSON
        if not non_wolves_alive:
            return Role.WEREWOLF
        return None

    def _seconds_remaining(self) -> float:
        """Seconds until the current phase expires."""
        if self._state.phase_ends_at is None:
            return 0.0
        delta = self._state.phase_ends_at - datetime.now(timezone.utc)
        return max(delta.total_seconds(), 0.0)

    def _early_exit(self) -> bool:
        """L-4: check if the current phase can end early."""
        phase = self._state.phase

        # Vote phases: all eligible voters have cast
        if phase in (Phase.WOLF_VOTE, Phase.DAY_VOTE):
            vote = self._votes.current_vote
            if vote is None:
                return False
            return vote.eligible_voters == set(vote.ballots.keys())

        # L-4 changed: WITCH_VOTE always runs its full time
        # (ending early would reveal whether the witch is alive or has acted)

        # Chat, dawn, dusk: no early exit
        return False
