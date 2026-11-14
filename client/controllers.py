"""Controllers: HumanController (terminal) and BotController (random moves)."""
import asyncio
import logging
from typing import Protocol, runtime_checkable

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from client.bot import choose_chat, choose_vote, choose_witch
from client.commands import parse

logger = logging.getLogger(__name__)

BANNER_W = 50

# Display name and time-of-day label for each timed phase
_PHASE_INFO: dict[str, tuple[str, str]] = {
    "wolf_chat":  ("WOLF CHAT",  "Night"),
    "wolf_vote":  ("WOLF VOTE",  "Night"),
    "witch_vote": ("WITCH VOTE", "Night"),
    "dawn":       ("DAWN",       "Day"),
    "day_chat":   ("DAY CHAT",   "Day"),
    "day_vote":   ("DAY VOTE",   "Day"),
    "dusk":       ("DUSK",       "Day"),
}

# Static moderator narration
_MOD_LINE: dict[str, str] = {
    "wolf_chat":  "Wolves, the town sleeps. Discuss your target.",
    "wolf_vote":  "Wolves, time to vote. /vote <name>",
    "witch_vote": "The witch stirs...",
    "day_chat":   "The town gathers. Speak freely!",
    "day_vote":   "Time to decide. /vote <name>",
}

# Closing line printed when a phase ends
_CLOSING_LINE: dict[str, str] = {
    "wolf_chat":  "The wolves have finished deliberating...",
    "wolf_vote":  "The wolves have cast their vote...",
    "witch_vote": "The witch has finished casting their vote...",
    "day_chat":   "Discussion is over...",
    "day_vote":   "The townspeople have cast their votes...",
    "dawn":       "The town braces for the day ahead...",
    "dusk":       "Night falls over the village...",
}


def _banner(label: str, ch: str = "-") -> str:
    """Center a label inside a line of repeated chars."""
    inner = f" [ {label} ] "
    pad = max(BANNER_W - len(inner), 0)
    return ch * (pad // 2) + inner + ch * (pad - pad // 2)


def _pname(pid: int, player_map: dict[int, dict]) -> str:
    """Look up a player name by id, falling back to #<id>."""
    return player_map.get(pid, {}).get("name", f"#{pid}")


# 
# Controller protocol
# 

@runtime_checkable
class Controller(Protocol):
    """Interface shared by human and bot controllers."""

    def on_event(self, event: dict) -> None:
        """Update internal state, maybe print."""
        ...

    async def next_action(self) -> tuple[str, dict]:
        """Return the same (cmd, data) tuples as commands.parse."""
        ...


# 
# HumanController
# 

class HumanController:
    """Terminal player: prints events, reads prompt_toolkit input."""

    def __init__(self, my_id: int, player_map: dict[int, dict]) -> None:
        self._my_id = my_id
        self._player_map = player_map
        self._session: PromptSession = PromptSession()
        self._my_role = ""
        self._my_teammates: list[int] = []
        self._my_alive = True
        self._pending_deaths: list[str] = []
        self._pending_witch_prompt: dict | None = None
        self._current_phase = ""
        self._prev_phase = ""

    # -- Controller interface --

    def on_event(self, event: dict) -> None:
        """Format and print a game event."""
        etype = event.get("type", "")

        # Track role and teammates
        if etype == "role_assigned":
            self._my_role = event.get("payload", {}).get("role", "?").upper()
            self._my_teammates = event.get("payload", {}).get("teammates", [])

        # Print disconnect notice immediately (not buffered like deaths)
        if etype == "player_disconnected":
            name = event.get("payload", {}).get("name", "?")
            print(f"  Moderator :> {name} has disconnected.")
            return

        # Track deaths: buffer for DAWN/DUSK banners
        if etype == "death":
            pid = event.get("payload", {}).get("player_id")
            if pid in self._player_map:
                self._player_map[pid]["alive"] = False
            if pid == self._my_id:
                self._my_alive = False
            self._pending_deaths.append(event.get("payload", {}).get("name", "?"))
            return

        # Buffer witch prompt for WITCH_VOTE banner
        if etype == "witch_prompt":
            self._pending_witch_prompt = event.get("payload", {})
            return

        text = self._format_event(event)

        if etype == "phase_changed":
            self._prev_phase = self._current_phase
            self._current_phase = event.get("payload", {}).get("phase", "")
            self._pending_deaths.clear()
            self._pending_witch_prompt = None

        if text:
            print(text)

    async def next_action(self) -> tuple[str, dict]:
        """Read a line from the terminal and parse it."""
        with patch_stdout():
            line = await self._session.prompt_async("> ")
        return parse(line)

    # -- private formatting --

    def _format_event(self, event: dict) -> str | None:
        """Render one SSE event as terminal text, or None to skip."""
        etype = event.get("type", "")
        p = event.get("payload", {})

        if etype == "phase_changed":
            return self._format_phase_changed(p)

        if etype == "chat":
            name = p.get("author_name", "?")
            tag = " (me)" if p.get("author_id") == self._my_id else ""
            return f"  {name}{tag}: {p.get('text', '')}"

        if etype == "role_assigned":
            role = p.get("role", "?").upper()
            lines = [f"  Moderator :>> Your role is: {role}"]
            mates = p.get("teammates", [])
            if mates:
                names = ", ".join(_pname(m, self._player_map) for m in mates)
                lines.append(f"  Moderator :>> Your fellow wolves: {names}")
            return "\n".join(lines)

        if etype == "game_over":
            winner = p.get("winner", "")
            msg = "The town wins!" if winner == "townsperson" else "The wolves win!"
            lines = [f"\n{_banner('GAME OVER', '=')}", f"  Moderator :> {msg}", ""]
            for pl in p.get("players", []):
                pid = pl.get("player_id")
                alive = self._player_map.get(pid, {}).get("alive", True)
                tag = "(alive)" if alive else "(dead)"
                lines.append(f"    {pl['name']:<15} {pl.get('role', '?'):<15} {tag}")
            return "\n".join(lines)

        return None

    def _format_phase_changed(self, p: dict) -> str:
        """Render a phase_changed event with banners and narration."""
        phase = p.get("phase", "")
        day = p.get("day_num", 0)
        disp, period = _PHASE_INFO.get(phase, (phase.upper(), ""))
        dead_tag = " (DEAD)" if not self._my_alive else ""
        label = f"{disp} - {period} {day}" if period else disp
        deaths = self._pending_deaths

        lines: list[str] = []
        closing = _CLOSING_LINE.get(self._current_phase, "")
        if closing:
            lines.append(f"  Moderator :> {closing}")
        lines.append(f"\n{_banner(label)}")
        # Role line with teammates if applicable
        if self._my_role:
            role_parts = [f"Role: {self._my_role}"]
            if self._my_teammates:
                mate_names = ", ".join(
                    _pname(m, self._player_map) for m in self._my_teammates
                )
                role_parts.append(f"Team: {mate_names}")
            if dead_tag:
                role_parts.append("DEAD")
            lines.append(f" [{', '.join(role_parts)}]")
        # Player roster: name (dead) for each player, no roles shown
        if self._player_map:
            roster = []
            for pid, info in sorted(self._player_map.items()):
                name = info.get("name", f"#{pid}")
                if not info.get("alive", True):
                    name += " (dead)"
                roster.append(name)
            lines.append(f" [Players: {', '.join(roster)}]")

        if phase == "dawn":
            lines.append("  Moderator :> The sun rises over the village.")
            if deaths:
                names = " and ".join(deaths)
                verb = "has" if len(deaths) == 1 else "have"
                lines.append(
                    f"  Moderator :> Outcome: Unfortunately, {names} {verb} been KILLED!")
            else:
                lines.append(
                    "  Moderator :> Outcome: Fortunately, no one was killed :)")
        elif phase == "dusk":
            lines.append("  Moderator :> The votes are counted.")
            if deaths:
                names = " and ".join(deaths)
                verb = "has" if len(deaths) == 1 else "have"
                lines.append(
                    f"  Moderator :> Outcome: {names} {verb} been KILLED!")
            else:
                lines.append("  Moderator :> Outcome: No one was hanged.")
        else:
            mod = _MOD_LINE.get(phase, "")
            if mod:
                lines.append(f"  Moderator :> {mod}")

        # Buffered witch prompt after WITCH_VOTE banner
        if phase == "witch_vote" and self._pending_witch_prompt is not None:
            vid = self._pending_witch_prompt.get("victim_id")
            if vid is None:
                lines.append(
                    "  Moderator :>> Nobody was attacked. /poison <name> or /pass")
            else:
                nm = _pname(vid, self._player_map)
                lines.append(
                    f"  Moderator :>> The wolves attacked {nm}. /save, /poison <name>, or /pass")

        lines.append("")
        return "\n".join(lines)


# 
# BotController
# 

class BotController:
    """Automated player: keeps a small view, delegates decisions to bot.py."""

    def __init__(self, my_id: int, player_map: dict[int, dict]) -> None:
        self._my_id = my_id
        self._player_map = player_map
        self._role = ""
        self._teammates: list[int] = []
        self._alive = True
        self._phase = ""
        self._witch_prompt: dict | None = None
        # Flag set when we have a new phase to act on
        self._phase_changed = asyncio.Event()
        self._acted_this_phase = False

    @property
    def _view(self) -> dict:
        """Snapshot of what the bot knows, passed to bot.py functions."""
        alive_ids = [
            pid for pid, info in self._player_map.items() if info.get("alive", True)
        ]
        return {
            "my_id": self._my_id,
            "role": self._role,
            "teammates": self._teammates,
            "alive_ids": alive_ids,
            "phase": self._phase,
        }

    # -- Controller interface --

    def on_event(self, event: dict) -> None:
        """Update the bot's view of the game."""
        etype = event.get("type", "")
        p = event.get("payload", {})

        if etype == "role_assigned":
            self._role = p.get("role", "")
            self._teammates = p.get("teammates", [])
            # No role/team print: visible on a shared screen would leak identity

        if etype == "death":
            pid = p.get("player_id")
            if pid in self._player_map:
                self._player_map[pid]["alive"] = False
            if pid == self._my_id:
                self._alive = False
            # Deaths printed only at DAWN/DUSK by the server, not here

        if etype == "witch_prompt":
            self._witch_prompt = p

        if etype == "phase_changed":
            self._phase = p.get("phase", "")
            self._acted_this_phase = False
            self._phase_changed.set()
            # Only show day-side phases (public knowledge)
            if self._phase in ("dawn", "day_chat", "day_vote", "dusk"):
                print(f"[bot] phase={self._phase} day={p.get('day_num', 0)}")
            else:
                print(f"[bot] phase=night day={p.get('day_num', 0)}")

        if etype == "game_over":
            winner = p.get("winner", "?")
            print(f"[bot] game_over winner={winner}")

    async def next_action(self) -> tuple[str, dict]:
        """Wait for a phase change, then return a random legal action."""
        while True:
            await self._phase_changed.wait()
            self._phase_changed.clear()

            if self._acted_this_phase or not self._alive:
                continue

            # Small delay so the bot doesn't act instantly
            await asyncio.sleep(1.0)
            self._acted_this_phase = True

            view = self._view
            phase = self._phase

            # Wolf vote: vote for a non-wolf
            if phase == "wolf_vote" and self._role == "werewolf":
                target = choose_vote(view)
                if target is not None:
                    return ("vote", {"target_id": target})

            # Day vote: everyone votes
            if phase == "day_vote":
                target = choose_vote(view)
                if target is not None:
                    return ("vote", {"target_id": target})

            # Witch vote: only the witch acts
            if phase == "witch_vote" and self._role == "witch":
                prompt = self._witch_prompt or {"victim_id": None, "allowed": ["pass"]}
                result = choose_witch(view, prompt)
                return ("witch", result)

            # Chat phases: maybe say something
            if phase in ("wolf_chat", "day_chat"):
                msg = choose_chat(view)
                if msg:
                    return ("chat", {"text": msg})
