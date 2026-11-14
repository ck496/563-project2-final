"""Terminal client: join, stream events, and send commands."""
import argparse
import asyncio
import logging
import os
import sys
import time

from client.commlib import CommLib, CommError
from client.controllers import BotController, HumanController

logger = logging.getLogger(__name__)


def _resolve(name: str, player_map: dict[int, dict]) -> int | None:
    """Find player id by case-insensitive name match."""
    low = name.lower()
    for pid, info in player_map.items():
        if info["name"].lower() == low:
            return pid
    return None


# Three async tasks: events, actions, heartbeat
async def _read_events(
    api: CommLib, token: str, my_id: int,
    player_map: dict[int, dict], ctrl: HumanController | BotController,
) -> None:
    """Read the SSE stream and dispatch events to the controller."""
    refreshed = False
    async for event in api.events(token):
        # Refresh player list once at game start so name lookups work
        if not refreshed and event.get("type") in ("role_assigned", "phase_changed"):
            try:
                for p in await asyncio.to_thread(api.players, token):
                    player_map[p["id"]] = p
            except CommError:
                pass
            refreshed = True

        ctrl.on_event(event)

    # SSE stream closed (server reset or crash)
    if isinstance(ctrl, BotController):
        print("[bot] server connection closed, exiting")
        sys.exit(0)
    print("\n  Connection to server lost.")


async def _send_actions(
    api: CommLib, token: str,
    player_map: dict[int, dict], ctrl: HumanController | BotController,
) -> None:
    """Loop: get the next action from the controller, dispatch to the server."""
    while True:
        try:
            cmd, data = await ctrl.next_action()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "empty":
            continue

        is_bot = isinstance(ctrl, BotController)
        try:
            if cmd == "chat":
                await asyncio.to_thread(api.chat, token, data["text"])
                if is_bot:
                    print("[bot] sent chat")
            elif cmd == "vote":
                # Bot sends target_id directly, human sends name to resolve
                target_id = data.get("target_id")
                if target_id is None:
                    target_id = _resolve(data["name"], player_map)
                    if target_id is None:
                        if not is_bot:
                            print(f"  Unknown player: {data['name']}")
                        continue
                await asyncio.to_thread(api.vote, token, target_id)
            elif cmd == "witch":
                target = data.get("target_id")
                if target is None and data.get("name"):
                    target = _resolve(data["name"], player_map)
                    if target is None:
                        if not is_bot:
                            print(f"  Unknown player: {data['name']}")
                        continue
                await asyncio.to_thread(api.witch, token, data["action"], target)
                # Witch actions never printed: reveals who the witch is
            elif cmd == "unknown" and not is_bot:
                print("  Commands: /vote <name>, /save, /poison <name>, /pass")
        except CommError as exc:
            if not is_bot:
                print(f"  Error: {exc.detail}")
            else:
                # Generic failure, no secret detail
                print("[bot] action failed")


async def _heartbeat(api: CommLib, token: str, interval: float = 10.0) -> None:
    """Send a heartbeat every interval seconds to signal liveness."""
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(api.heartbeat, token)
        except CommError:
            # Server may be resetting, keep trying next tick
            pass


# 
# Join helpers
# 

def _friendly_join_error(exc: CommError) -> str:
    """Turn a CommError from /join/ into a one-line message for the player."""
    detail = exc.detail
    if exc.status == 422:
        # detail may be a stringified list of validation errors
        if "player_name" in detail:
            return "Invalid name: only letters, digits, and underscores (2-15 chars)."
        if "join_code" in detail:
            return "Invalid join code."
        return "Invalid input. Check your name and join code."
    return detail if detail else "Unknown error"


def _join_with_retry(api: CommLib, name: str, code: str) -> dict:
    """Join the game, retrying if the server is still resetting between games."""
    for attempt in range(10):
        try:
            return api.join(name, code)
        except CommError as exc:
            if exc.status is None:
                # Transport error
                print("  Server unavailable. Try again later by running:"
                      "\n    uv run python -m client.main")
                sys.exit(1)
            # 409 = game full (server still resetting), retry after a short wait
            if attempt < 9 and exc.status == 409:
                print("  Waiting for server to start a new game...")
                time.sleep(2)
                continue
            raise
    sys.exit(1)


# 
# Entry point
# 

def _get_settings() -> argparse.Namespace:
    """Read settings from flags first, then environment variables."""
    ap = argparse.ArgumentParser(description="Werewolves client")
    ap.add_argument("--url", default=os.environ.get("WW_SERVER_URL", "http://localhost:8000"))
    ap.add_argument("--name", default=os.environ.get("WW_NAME", ""))
    ap.add_argument("--code", default=os.environ.get("WW_JOIN_CODE", ""))
    ap.add_argument("--bot", action="store_true",
                    default=os.environ.get("WW_BOT", "").strip() == "1")
    return ap.parse_args()


def main() -> None:
    """Entry point: join, play, prompt to play again, repeat."""
    args = _get_settings()
    api = CommLib(args.url)
    is_bot = args.bot
    is_tty = sys.stdin.isatty()

    # Get name and code from flags/env, or prompt if interactive
    name = args.name
    code = args.code
    if not name:
        if is_tty and not is_bot:
            name = input("Name: ").strip()
        else:
            print("Error: --name or WW_NAME is required for non-interactive mode.")
            sys.exit(1)
    if not code:
        if is_tty and not is_bot:
            code = input("Join code: ").strip()
        else:
            print("Error: --code or WW_JOIN_CODE is required for non-interactive mode.")
            sys.exit(1)

    while True:
        # Join, re-prompting on validation errors (bad name/code)
        while True:
            try:
                result = _join_with_retry(api, name, code)
                break
            except CommError as exc:
                msg = _friendly_join_error(exc)
                print(f"  {msg}")
                if exc.status != 422:
                    sys.exit(1)
                if is_tty and not is_bot:
                    name = input("Name: ").strip()
                    continue
                sys.exit(1)

        token, my_id = result["token"], result["player_id"]
        try:
            info = api.me(token)
        except CommError as exc:
            print(f"  Error: {exc.detail}")
            sys.exit(1)
        print(f"Joined as {info['name']} (player {my_id}). "
              "Waiting for the game to start...")
        player_map: dict[int, dict] = {}

        # Build the right controller based on bot flag
        if is_bot:
            ctrl: HumanController | BotController = BotController(my_id, player_map)
        else:
            ctrl = HumanController(my_id, player_map)

        # Run three tasks: events, actions, heartbeat
        async def _run() -> None:
            ev_task = asyncio.create_task(
                _read_events(api, token, my_id, player_map, ctrl)
            )
            act_task = asyncio.create_task(
                _send_actions(api, token, player_map, ctrl)
            )
            hb_task = asyncio.create_task(
                _heartbeat(api, token)
            )
            # When the event stream ends (server reset), cancel the others
            try:
                await ev_task
            finally:
                act_task.cancel()
                hb_task.cancel()
                for t in (act_task, hb_task):
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass

        try:
            asyncio.run(_run())
        except KeyboardInterrupt:
            break

        # Bots always try to rejoin; humans get asked
        if is_bot:
            continue
        answer = input("\n  Play again? (Y/N): ").strip().lower()
        if answer != "y":
            print("  Thanks for playing, goodbye!")
            break


if __name__ == "__main__":
    main()
