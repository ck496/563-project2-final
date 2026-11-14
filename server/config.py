"""Configuration settings using pydantic-settings"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Game configuration: reads from .env with WW_ prefix
         - Values below are DEFAULTS: override with .env file or environment variables.
         - Usage in other modules: from server.config import settings then settings.max_wolves
    """

    # Game composition
    max_wolves: int = 3
    max_witch: int = 1
    max_town: int = 8

    # Authentication
    join_code: str = "ruffruff982"

    # Phase durations (seconds)
    wolf_chat_seconds: int = 120
    wolf_vote_seconds: int = 60
    witch_vote_seconds: int = 30
    day_chat_seconds: int = 180
    day_vote_seconds: int = 90
    dawn_seconds: int = 20
    dusk_seconds: int = 20

    # Seconds to wait after GAME_OVER before resetting for a new game
    reset_delay_seconds: int = 15

    # Max concurrent SSE streams per player (overlap during reconnect)
    max_streams_per_player: int = 2

    # Presence and liveness
    heartbeat_seconds: int = 10
    presence_grace_seconds: int = 60
    max_days: int = 10

    @property
    def max_players(self) -> int:
        """Total player count"""
        return self.max_wolves + self.max_witch + self.max_town

    class Config:
        env_file = ".env"
        env_prefix = "WW_"  # Environment variables like WW_MAX_WOLVES
        case_sensitive = False


# Singleton instance, fails fast on import if invalid
settings = Settings()

#