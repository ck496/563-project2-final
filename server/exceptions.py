"""Custom exceptions for game logic"""


class GameFullError(Exception):
    """Raised when game has reached max players"""
    pass


class DuplicateNameError(Exception):
    """Raised when player name already exists"""
    pass


class PlayerNotFoundError(Exception):
    """Raised when player_id does not exist"""
    pass


class InvalidTokenError(Exception):
    """Raised when token is invalid or not found"""
    pass


class WrongPhaseError(Exception):
    """Raised when action is not allowed in the current phase."""
    pass


class NotAllowedError(Exception):
    """Raised when player is dead, wrong role, or not eligible."""
    pass


class InvalidTargetError(Exception):
    """Raised when vote or poison target is invalid."""
    pass


class RateLimitError(Exception):
    """Raised when a player exceeds the message rate limit."""
    pass