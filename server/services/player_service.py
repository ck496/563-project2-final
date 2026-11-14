"""Player Service to handle all player interactions"""
from ..models.player import Player
from ..models.enums import Role
from server.config import settings
from server.exceptions import GameFullError, DuplicateNameError, PlayerNotFoundError
import random


class PlayerService:
    def __init__(self):
        self._players: dict[int, Player] = {}
        self.next_id = 0
        self.roles_pool: list[Role] = self._build_roles_pool()

    def _build_roles_pool(self) -> list[Role]:
        pool = (
            [Role.WEREWOLF] * settings.max_wolves + 
            [Role.WITCH] * settings.max_witch + 
            [Role.TOWNSPERSON] * settings.max_town
        )
        random.shuffle(pool)

        return pool
    
    def add_player(self, name: str) -> Player:
        """Add players to game"""
        if not self.roles_pool:
            raise GameFullError("game is full")

        if any(player.name.casefold() == name.casefold() for player in self._players.values()):
            raise DuplicateNameError("name already exists")

        role = self.roles_pool.pop()
        player = Player(
            id = self.next_id,
            name = name,
            role = role
        )
        self._players[self.next_id] = player
        self.next_id += 1

        return player


    def get_player(self, player_id: int) -> Player:
        """Get player by ID"""

        if player_id not in self._players:
            raise PlayerNotFoundError("invalid player_id")

        return self._players[player_id]


    def kill(self, player_id: int) -> Player:
        """Mark player as dead"""
        if player_id not in self._players:
            raise PlayerNotFoundError("invalid player_id")

        self._players[player_id].alive = False

        return self._players[player_id]


    def revive(self, player_id: int) -> Player:
        """Mark player as alive (witch potion)"""
        if player_id not in self._players:
            raise PlayerNotFoundError("invalid player_id")

        self._players[player_id].alive = True

        return self._players[player_id]


    def get_alive_players(self) -> list[Player]:
        """Return all living players"""
        return [p for p in self._players.values() if p.alive]


    def get_wolves(self) -> list[int]:
        """Return player IDs of all werewolves"""
        return [pid for pid, p in self._players.items() if p.role == Role.WEREWOLF]


    def view_for(self, player_id: int) -> dict:
        """Return what this player should know (role, teammates if wolf)"""
        player = self.get_player(player_id)

        view = {
            "player_id": player_id,
            "role": player.role,
            "alive": player.alive
        }
        # Wolves know each other
        if player.role == Role.WEREWOLF:
            view["teammates"] = [pid for pid in self.get_wolves() if pid != player_id]

        return view


    def remove_player(self, player_id: int) -> None:
        """Remove one player and return their role to the pool."""
        if player_id not in self._players:
            raise PlayerNotFoundError("invalid player_id")
        player = self._players.pop(player_id)
        self.roles_pool.append(player.role)

    def remove_all_players(self) -> None:
        """Clear all players (for testing/reset)."""
        self._players.clear()
        self.next_id = 0
        self.roles_pool = self._build_roles_pool()

        




