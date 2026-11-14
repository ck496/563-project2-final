""""Authenticate players by issuing token at join, and validating auth headers """""
import hashlib, secrets
from server.exceptions import InvalidTokenError


class AuthService:
    def __init__(self):
        #private obj only auth should touch, maps sha256(token) to player_id
        self._token_map: dict[str, int] = {} 

    #static method: purely a helper function that gets no `self`, doesnt change AuthService's data
    # - its just  here cuz it logically belongs with auth service . 
    # - can be called without crating an obj `hash = AuthService._hash(token)``
    @staticmethod 
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
    
    """ Make raw token, store its hash, return raw which gets passed to player on join"""
    def issue_token(self, player_id: int) -> str:

        #1. make toekn with 32 random bytes from the OS CSPRNG, URL-safe text
        token = secrets.token_urlsafe(32)

        # 2. Map it to player 
        hashed_token = self._hash(token)
        self._token_map[hashed_token] = player_id

        return token

    """ Lookup hashed token and return player_id, raises InvalidTokenError if not found """
    def resolve_token(self, token: str) -> int:
        hashed_token = self._hash(token)
        player_id = self._token_map.get(hashed_token)
        if player_id is None:
            raise InvalidTokenError("invalid or expired token")
        return player_id

    """ Revoke just one token, returns player_id, raises InvalidTokenError if not found """
    def revoke_token(self, token: str) -> int:
        hashed_token = self._hash(token)
        player_id = self._token_map.pop(hashed_token, None)
        if player_id is None:
            raise InvalidTokenError("invalid or expired token")
        return player_id

    def revoke_player(self, player_id: int) -> None:
        """Revoke all tokens belonging to a player (used when kicking)."""
        to_remove = [h for h, pid in self._token_map.items() if pid == player_id]
        for h in to_remove:
            del self._token_map[h]

    def revoke_all_tokens(self) -> None:
        """Revoke all tokens by clearing the map."""
        self._token_map.clear()

    