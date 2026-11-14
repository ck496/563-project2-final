"""Chat message model for wolf and town channels."""
from datetime import datetime

from pydantic import BaseModel

from .enums import ChatChannel, Phase


class Chat(BaseModel):
    """A single chat message, delivered inside an Event payload."""
    day_num: int
    phase: Phase
    channel: ChatChannel
    author_id: int
    author_name: str
    text: str
    time: datetime
