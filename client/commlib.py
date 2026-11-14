"""Communications library: the only file that imports httpx."""
import asyncio
import json

import httpx
from httpx_sse import aconnect_sse


class CommError(Exception):
    """Unified error for all HTTP failures."""

    def __init__(self, status: int | None, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(detail)


def _raise_comm(exc: httpx.HTTPStatusError) -> None:
    """Convert an httpx status error into a CommError."""
    try:
        body = exc.response.json()
        detail = body.get("detail", str(exc))
        # 422 validation errors come as a list of dicts
        if isinstance(detail, list):
            detail = str(detail)
    except Exception:
        detail = str(exc)
    raise CommError(exc.response.status_code, detail) from exc


class CommLib:
    """Wraps every server endpoint; the only client file that touches httpx."""

    def __init__(self, base_url: str) -> None:
        self._base = base_url
        self._http = httpx.Client(base_url=base_url, timeout=5.0)

    def _auth(self, token: str) -> dict[str, str]:
        """Bearer header for authenticated requests."""
        return {"Authorization": f"Bearer {token}"}

    # -- sync request methods (one per route) --

    def join(self, name: str, join_code: str) -> dict:
        """POST /join/: returns {player_id, token}."""
        try:
            r = self._http.post(
                "/join/", json={"player_name": name, "join_code": join_code}
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            _raise_comm(exc)
        except httpx.TransportError as exc:
            raise CommError(None, str(exc)) from exc
        return {}  # unreachable, satisfies type checker

    def me(self, token: str) -> dict:
        """GET /me/info/: returns role, alive, name, and teammates if wolf."""
        try:
            r = self._http.get("/me/info/", headers=self._auth(token))
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            _raise_comm(exc)
        except httpx.TransportError as exc:
            raise CommError(None, str(exc)) from exc
        return {}

    def players(self, token: str) -> list[dict]:
        """GET /players/: returns [{id, name, alive}]."""
        try:
            r = self._http.get("/players/", headers=self._auth(token))
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            _raise_comm(exc)
        except httpx.TransportError as exc:
            raise CommError(None, str(exc)) from exc
        return []

    def chat(self, token: str, text: str) -> dict:
        """POST /chat/: send a chat message."""
        try:
            r = self._http.post(
                "/chat/", json={"text": text}, headers=self._auth(token)
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            _raise_comm(exc)
        except httpx.TransportError as exc:
            raise CommError(None, str(exc)) from exc
        return {}

    def vote(self, token: str, target_id: int) -> dict:
        """POST /vote/: cast a wolf or day vote."""
        try:
            r = self._http.post(
                "/vote/", json={"target": target_id}, headers=self._auth(token)
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            _raise_comm(exc)
        except httpx.TransportError as exc:
            raise CommError(None, str(exc)) from exc
        return {}

    def witch(self, token: str, action: str, target: int | None = None) -> dict:
        """POST /witch/: cast a witch ballot (save/poison/pass)."""
        body: dict = {"kind": "witch", "action": action}
        if target is not None:
            body["target"] = target
        try:
            r = self._http.post("/witch/", json=body, headers=self._auth(token))
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            _raise_comm(exc)
        except httpx.TransportError as exc:
            raise CommError(None, str(exc)) from exc
        return {}

    def heartbeat(self, token: str) -> dict:
        """POST /heartbeat/: signal liveness."""
        try:
            r = self._http.post("/heartbeat/", headers=self._auth(token))
            r.raise_for_status()
            return {}
        except httpx.HTTPStatusError as exc:
            _raise_comm(exc)
        except httpx.TransportError as exc:
            raise CommError(None, str(exc)) from exc
        return {}

    # -- async SSE stream --

    async def events(self, token: str):
        """Async generator: yields parsed events, reconnecting on drops."""
        last_id = 0
        retries = 0
        max_retries = 5

        while True:
            headers = self._auth(token)
            if last_id > 0:
                headers["Last-Event-ID"] = str(last_id)
            try:
                async with httpx.AsyncClient(
                    base_url=self._base, timeout=None
                ) as client:
                    async with aconnect_sse(
                        client,
                        "GET",
                        "/events/stream/",
                        headers=headers,
                    ) as source:
                        async for sse in source.aiter_sse():
                            retries = 0  # connection is healthy
                            if sse.id:
                                last_id = int(sse.id)
                            if sse.data:
                                parsed = json.loads(sse.data)
                                if isinstance(parsed, str):
                                    parsed = json.loads(parsed)
                                yield parsed
                # Stream ended cleanly (server reset), stop
                return
            except httpx.TransportError:
                retries += 1
                if retries > max_retries:
                    return
                await asyncio.sleep(2.0)
