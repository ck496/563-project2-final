# werewolves-democracy

Werewolves game (wolves, a witch and townspeople) built as a FastAPI server with one
client per player. Players talk to the server over HTTP and get events over SSE. In Docker,
every player runs in its own container with its own Linux user and resource limits.
See `about.md` for the story behind it.

**Communications library:** `client/commlib.py` (one file, see the API below).

**Join code:** `ruffruff982` (set in `.env` and `docker/.env`)

 Screenshots of a game are in [`game_screenshots/`](game_screenshots/).

## Local Run Guide (5 players default)

The root `.env` sets a 5 seat game: 2 wolves, 1 witch, 2 townspeople. The game starts
when all 5 seats are filled. Edit `.env` to change seats or phase times.

```bash
# 0 Edit the .env for custom game settings for player count, times etc
.env

# 1. Install dependencies the first time
uv sync

# 2. Start the server 
uv run fastapi run --port 8000

# 3. Join as a player, each player needs their own temrinal.. add 4 more for game to start 
uv run python -m client.main --name CK --code ruffruff982

# 3.2. you can also join as a bot. No input needed they make choices from available moves 
uv run python -m client.main --bot --name bot1 --code ruffruff982

# Run the tests
uv run pytest -q
```

---

## How to play

| Command | Who | When |
|---|---|---|
| type any text | wolves at night, everyone in day chat | chat phases |
| `/vote <name>` | wolves at night, everyone alive in the day | vote phases |
| `/save` | witch | witch phase |
| `/poison <name>` | witch | witch phase |
| `/pass` | witch | witch phase |

- Check screenshots for game play

---

## Docker run guide

**Note** Need docker engine to be able to run this.

The compose file defines two **images** (`docker-server` and `docker-player-N`) and multiple **containers**
    `--build` compiles the images from the Dockerfiles.
    `up` creates and starts the containers. Each container is its own isolated Linux environment with its own uid capped resources etc

`docker/.env` sets a 6 seat game: 2 wolves, 1 witch, 3 townspeople.

### Setup

all humans no bots

```bash
# 1. edit the docker .env 
docker/.env
```

```bash
# 2, Build images and start only the server + 6 human containers
docker compose -f docker/compose.yaml up -d --build server \
  player-1 player-2 player-3 player-4 player-5 player-6
```

1. Then attach to each player in a separate terminal:

```bash
docker attach werewolves-player-1   # terminal 2
docker attach werewolves-player-2   # terminal 3
docker attach werewolves-player-3   
docker attach werewolves-player-4
docker attach werewolves-player-5   
docker attach werewolves-player-6   

# Ctrl-P thenCtrl-Q to detach without stopping the container. And you can attatch back and resume 
```

### Stopping and cleaning up

```bash
# Sops containers and removes them and the compose network. 
# Images stay cached so the next `up --build` is fast.
docker compose -f docker/compose.yaml down

# Stop like abovve + deletes the images... next build starts from scratch.
docker compose -f docker/compose.yaml down --rmi all

# Remove just the images (if containers are already stopped)
docker image rm docker-server docker-player-1 

```


### Connecting with Two-machines

Run the server on one host, clients on another:

```bash
# Host A server only
docker compose -f docker/compose.yaml up --build server

# Host B: build the client image, then point it at Host A
docker compose -f docker/compose.yaml build player-1
docker run --rm -it -e WW_SERVER_URL=http://<lan-ip>:8000 \
  -e WW_NAME=robie -e WW_JOIN_CODE=ruffruff982 docker-player-1
```

---

## Communications library: `client/commlib.py`

All client communication goes through the `CommLib` class in this one file. No other
client file imports `httpx`.

| Method | HTTP | Route | Returns |
|---|---|---|---|
| `join(name, join_code)` | POST | `/join/` | `{player_id, token}` |
| `me(token)` | GET | `/me/info/` | `{role, alive, name, teammates}` |
| `players(token)` | GET | `/players/` | `[{id, name, alive}]` |
| `chat(token, text)` | POST | `/chat/` | the chat message |
| `vote(token, target_id)` | POST | `/vote/` | `{status}` |
| `witch(token, action, target)` | POST | `/witch/` | `{status}` |
| `heartbeat(token)` | POST | `/heartbeat/` | `{}` |
| `events(token)` | GET (SSE) | `/events/stream/` | async stream of events |

Every failure is raised as `CommError(status, detail)`.

- **Unicast:** role reveal and the witch prompt go to one player.
- **Multicast:** wolf chat and wolf votes go to the wolves only.
- **Broadcast:** phase changes, deaths and day chat go to everyone.

---

## Files

| Path | What it is |
|---|---|
| `client/commlib.py` | **the communications library** |
| `client/main.py` | client entry point: events, input and heartbeat tasks |
| `client/controllers.py`, `client/bot.py` | human and bot decision makers |
| `client/commands.py` | parses typed commands |
| `server/main.py` | app setup, builds every service once |
| `server/config.py` | all settings, read from `.env` with the `WW_` prefix |
| `server/routes/` | thin HTTP layer |
| `server/services/` | game rules: auth, players, events, chat, votes, witch, presence, game loop |
| `server/models/` | data models |
| `docker/` | Dockerfiles, `compose.yaml`, `.env`, spoofing test |
| `tests/` | pytest suite |
| `about.md` | background and what changed since project 1 |