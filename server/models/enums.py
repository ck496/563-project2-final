from enum import StrEnum, auto


class Role(StrEnum):
    # auto fills in each of the values, since strenum values become "werewolf"
    WEREWOLF = auto()
    WITCH = auto()
    TOWNSPERSON = auto()


class Phase(StrEnum):
    LOBBY = auto()      # Joined players waiting in lobby  for game to start
    WOLF_CHAT = auto()  # Wolf chat to see who they want to kill
    WOLF_VOTE = auto()
    WITCH_VOTE = auto()  # potion (save recently killed) or pick a person to poison
    DAWN = auto()       # Anounce the dead, result of wolf and witch action
    DAY_CHAT = auto()   # All living players chat with eachother
    DAY_VOTE = auto()   # everyone votes on who to kill
    DUSK = auto()       # Get last words from whoever was hung, get ready for night
    GAME_OVER = auto()  # all wolves dead or all non-wolves are dead

# Used in event


class Audience(StrEnum):
    ALL = auto()
    WOLVES = auto()
    WITCH = auto()
    PLAYER = auto()
    MOD = auto()


class ChatChannel(StrEnum):
    TOWN = auto()
    WOLVES = auto()


class EventType(StrEnum):
    PHASE_CHANGED = auto()
    CHAT = auto()
    DEATH = auto()
    ROLE_ASSIGNED = auto()
    WITCH_PROMPT = auto()
    GAME_OVER = auto()
    PLAYER_DISCONNECTED = auto()

# used in vote


class WitchChoice(StrEnum):
    SAVE = auto()
    POISON = auto()
    PASS = auto()
