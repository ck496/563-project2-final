# werewolves-democracy

A variant of Werewolves of Miller’s Hollow where citizens vote on who gets hung based on daily discourse, rumors and gossip

**JOIN_CODE**: `ruffruff982` found in .env

## Local Run Guide


```bash
# 0 Edit the .env for custom game settings for player count, times etc
.env

# 1. Install dependencies the first time
uv sync

# 2. Start the server 
uv run fastapi run --port 8000

# 3. Join as a player, each player needs their own temrinal 
uv run python -m client.main --name CK --code JOIN_CODE

# 3.2. you can also join as a bot. No input needed they make choices from available moves 
uv run python -m client.main --bot --name bot1 --code JOIN_CODE

# For a quick test game, shrink the lobby, or update the .env
WW_MAX_WOLVES=1 WW_MAX_WITCH=1 WW_MAX_TOWN=1 uv run fastapi dev
```

---

## Docker run guide

**Note** Need docker engine to be able to run this.

The compose file defines two **images** (`ww-server` and `ww-client`) and multiple **containers**
    `--build` compiles the images from the Dockerfiles.
    `up` creates and starts the containers. Each container is its own isolated Linux environment with its own uid capped resources etc

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
docker attach werewolves-player-5   
docker attach werewolves-player-6   

# Ctrl-Q to detach without stopping the container
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

---

### Connecting with Two-machines

Run the server on one host, clients on another:

```bash
# Host A server only
docker compose -f docker/compose.yaml up --build server

# Host B point clients at the server's LAN IP
WW_SERVER_URL=http://<lan-ip>:8000 docker run --rm -it \
  -e WW_SERVER_URL -e WW_NAME=Chris -e WW_JOIN_CODE=ruffruff982 \
  werewolves-democracy-player-1
```

---

## UV notes

- `pyproject.toml` lists dependencies and entry configs
- `uv.lock` pins their exact versions so every machine installs the same thing

