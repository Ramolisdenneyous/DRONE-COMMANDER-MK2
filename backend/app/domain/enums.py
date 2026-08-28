from enum import Enum


class Side(str, Enum):
    FRIENDLY = "friendly"
    OPPOSITION = "opposition"


class SessionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class BattleStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    ACTIVE = "ACTIVE"
    VICTORY = "VICTORY"
    DEFEAT = "DEFEAT"
    DRAW = "DRAW"
    ABORTED = "ABORTED"
    ERROR_RECOVERABLE = "ERROR_RECOVERABLE"


class ActionType(str, Enum):
    STANDARD = "standard"
    MOVE = "move"
    MINOR = "minor"


class UnitCategory(str, Enum):
    COMMANDER = "commander"
    SOLDIER_SQUAD = "soldier_squad"
    DRONE = "drone"


class SizeClass(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    COMMANDER = "commander"


class MovementTrait(str, Enum):
    GROUND = "ground"
    FLYING = "flying"


class CoverType(str, Enum):
    NONE = "none"
    LIGHT = "light"
    HEAVY = "heavy"


class ObjectiveType(str, Enum):
    ANNIHILATION = "annihilation"
