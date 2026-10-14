"""Data models and operations for the Atari 8-bit Scene Editor."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Optional


class ModelValidationError(Exception):
    """Raised when scene model validation fails."""
    pass


class DuplicateElementIdError(ModelValidationError):
    """Raised when an element with a duplicate ID is added."""
    pass


class SingleSourceViolationError(ModelValidationError):
    """Raised when an element violates the single tile graphic constraint."""
    pass


class HardwareResourceLimitError(ModelValidationError):
    """Raised when hardware limits (max 3 sprites, 4 missiles per row) are exceeded."""
    pass


class InvalidPlatformPositionError(ModelValidationError):
    """Raised when platform y position does not satisfy y % 16 == 8 or exceeds scene height."""
    pass


class InvalidPlatformDimensionError(ModelValidationError):
    """Raised when platform width or height does not match allowed hardware sizes."""
    pass


class PlatformCollisionError(ModelValidationError):
    """Raised when two platforms overlap (collide)."""
    pass


class SceneObjectError(ModelValidationError):
    """Base error for scene object (enemy/treasure) validation."""
    pass


class ObjectLimitExceededError(SceneObjectError):
    """Raised when adding/moving an object exceeds the 3 objects per platform row limit."""
    pass


class InvalidPlatformAssignmentError(SceneObjectError):
    """Raised when an object is placed without a valid platform assignment."""
    pass


class InvalidObjectPropertyError(SceneObjectError):
    """Raised when an object has invalid speed, strategy, or attributes."""
    pass


@dataclass
class Rect:
    """Rectangle defining a sub-region in source coordinates."""
    x: int
    y: int
    width: int
    height: int

    def validate(self) -> None:
        if not isinstance(self.x, int) or not isinstance(self.y, int):
            raise ModelValidationError("Rect coordinates must be integers.")
        if not isinstance(self.width, int) or not isinstance(self.height, int):
            raise ModelValidationError("Rect dimensions must be integers.")
        if self.x < 0 or self.y < 0:
            raise ModelValidationError(f"Rect coordinates must be non-negative: ({self.x}, {self.y})")
        if self.width <= 0 or self.height <= 0:
            raise ModelValidationError(f"Rect dimensions must be strictly positive: {self.width}x{self.height}")

    def clone(self) -> Rect:
        return Rect(int(self.x), int(self.y), int(self.width), int(self.height))

    def to_dict(self) -> dict[str, int]:
        return {
            "x": int(self.x),
            "y": int(self.y),
            "width": int(self.width),
            "height": int(self.height),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rect:
        if not isinstance(data, dict):
            raise ModelValidationError("Rect data must be a dictionary.")
        for key in ("x", "y", "width", "height"):
            if key not in data:
                raise ModelValidationError(f"Missing required Rect field '{key}'.")
        rect = cls(
            x=int(data["x"]),
            y=int(data["y"]),
            width=int(data["width"]),
            height=int(data["height"]),
        )
        rect.validate()
        return rect


@dataclass
class Position:
    """Position on the scene canvas (in Atari screen pixels)."""
    x: int
    y: int

    def clone(self) -> Position:
        return Position(int(self.x), int(self.y))

    def validate(self) -> None:
        if not isinstance(self.x, int) or not isinstance(self.y, int):
            raise ModelValidationError("Position coordinates must be integers.")

    def to_dict(self) -> dict[str, int]:
        return {
            "x": int(self.x),
            "y": int(self.y),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        if not isinstance(data, dict):
            raise ModelValidationError("Position data must be a dictionary.")
        for key in ("x", "y"):
            if key not in data:
                raise ModelValidationError(f"Missing required Position field '{key}'.")
        pos = cls(
            x=int(data["x"]),
            y=int(data["y"]),
        )
        pos.validate()
        return pos


@dataclass
class SceneElement:
    """An independent element placed on the 160x96 Atari scene."""
    id: str
    source: str
    source_rect: Rect
    position: Position
    flip_x: bool = False
    z_index: int = 0

    @property
    def width(self) -> int:
        return self.source_rect.width

    @property
    def height(self) -> int:
        return self.source_rect.height

    def validate(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ModelValidationError("Element ID must be a non-empty string.")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ModelValidationError("Element source must be a non-empty path string.")
        if not isinstance(self.flip_x, bool):
            raise ModelValidationError(f"flip_x must be a boolean, got {type(self.flip_x).__name__}.")
        self.source_rect.validate()
        self.position.validate()

    def clone(self) -> SceneElement:
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source.replace("\\", "/"),
            "source_rect": self.source_rect.to_dict(),
            "position": self.position.to_dict(),
            "flip_x": bool(self.flip_x),
            "z_index": int(self.z_index),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneElement:
        if not isinstance(data, dict):
            raise ModelValidationError("SceneElement data must be a dictionary.")
        for key in ("id", "source", "source_rect", "position"):
            if key not in data:
                raise ModelValidationError(f"Missing required SceneElement field '{key}'.")

        elem = cls(
            id=str(data["id"]),
            source=str(data["source"]).replace("\\", "/"),
            source_rect=Rect.from_dict(data["source_rect"]),
            position=Position.from_dict(data["position"]),
            flip_x=bool(data.get("flip_x", False)),
            z_index=int(data.get("z_index", 0)),
        )
        elem.validate()
        return elem


# Hardware Platform Constants
PLATFORM_TYPE_SPRITE = "sprite"
PLATFORM_TYPE_MISSILE = "missile"
PLATFORM_TYPES = (PLATFORM_TYPE_SPRITE, PLATFORM_TYPE_MISSILE)

SPRITE_WIDTHS = (4, 8, 12, 16, 20, 24, 28, 32)
MISSILE_WIDTHS = (4, 8)
PLATFORM_HEIGHT = 4

MAX_SPRITES_PER_ROW = 3
MAX_MISSILES_PER_ROW = 4


def is_valid_platform_y(y: int, scene_height: Optional[int] = None) -> bool:
    """Return True if y satisfies Atari platform row rules: y % 16 == 8 and y >= 8."""
    if not isinstance(y, int):
        return False
    if y < 8 or y % 16 != 8:
        return False
    if scene_height is not None and (y + PLATFORM_HEIGHT) > scene_height:
        return False
    return True


def get_row_index(y: int) -> int:
    """Return 0-indexed row number from y coordinate (row 0 is y=8, row 1 is y=24, etc.)."""
    return (y - 8) // 16


def get_row_y_from_index(index: int) -> int:
    """Return y coordinate for a given 0-indexed row number."""
    return 8 + index * 16


def get_allowed_platform_rows(scene_height: int) -> list[int]:
    """Return list of all valid y coordinates that fit completely within the scene height."""
    return [y for y in range(8, scene_height - PLATFORM_HEIGHT + 1, 16)]


def get_allowed_widths(platform_type: str) -> tuple[int, ...]:
    """Return tuple of allowed pixel widths for the given platform type."""
    if platform_type == PLATFORM_TYPE_SPRITE:
        return SPRITE_WIDTHS
    elif platform_type == PLATFORM_TYPE_MISSILE:
        return MISSILE_WIDTHS
    return ()


def get_row_resource_usage(
    platforms: list[PlatformElement],
    y: int,
    exclude_id: Optional[str] = None,
) -> tuple[int, int]:
    """Return (sprite_count, missile_count) for row y in the given platform list."""
    sprites = 0
    missiles = 0
    for p in platforms:
        if exclude_id and p.id == exclude_id:
            continue
        if p.position.y == y:
            if p.type == PLATFORM_TYPE_SPRITE:
                sprites += 1
            elif p.type == PLATFORM_TYPE_MISSILE:
                missiles += 1
    return sprites, missiles


def can_add_platform_to_row(
    platforms: list[PlatformElement],
    platform_type: str,
    y: int,
    exclude_id: Optional[str] = None,
    scene_height: Optional[int] = None,
) -> tuple[bool, str]:
    """Check if adding/moving a platform of platform_type to row y is within hardware limits and bounds."""
    if not is_valid_platform_y(y, scene_height=scene_height):
        if scene_height is not None and (y + PLATFORM_HEIGHT) > scene_height:
            return (
                False,
                f"Row y={y} exceeds scene height {scene_height} (platform height is {PLATFORM_HEIGHT}).",
            )
        return (
            False,
            f"Invalid platform row y={y}. Platforms must start at y % 16 == 8 (e.g. y=8, 24, 40...).",
        )

    sprites, missiles = get_row_resource_usage(platforms, y, exclude_id=exclude_id)
    if platform_type == PLATFORM_TYPE_SPRITE:
        if sprites >= MAX_SPRITES_PER_ROW:
            return (
                False,
                f"Row y={y} already uses {sprites}/{MAX_SPRITES_PER_ROW} sprites. Maximum limit reached.",
            )
    elif platform_type == PLATFORM_TYPE_MISSILE:
        if missiles >= MAX_MISSILES_PER_ROW:
            return (
                False,
                f"Row y={y} already uses {missiles}/{MAX_MISSILES_PER_ROW} missiles. Maximum limit reached.",
            )
    else:
        return (
            False,
            f"Unknown platform type: '{platform_type}'. Must be 'sprite' or 'missile'.",
        )
    return True, ""


def platforms_overlap(
    x1: int, y1: int, w1: int, h1: int,
    x2: int, y2: int, w2: int, h2: int,
) -> bool:
    """Return True if two rectangular platform areas overlap (strictly share pixels).

    Platform edges that touch without sharing pixels (e.g. x1 + w1 == x2) do NOT overlap.
    """
    x_overlap = max(x1, x2) < min(x1 + w1, x2 + w2)
    y_overlap = max(y1, y2) < min(y1 + h1, y2 + h2)
    return x_overlap and y_overlap


def check_platform_collision(
    platforms: list[PlatformElement],
    candidate_rect: tuple[int, int, int, int],  # (x, y, width, height)
    exclude_id: Optional[str] = None,
) -> Optional[PlatformElement]:
    """Check if candidate rectangle collides with any platform in platforms list.

    Returns the first colliding PlatformElement if found, else None.
    """
    cx, cy, cw, ch = candidate_rect
    for p in platforms:
        if exclude_id and p.id == exclude_id:
            continue
        if platforms_overlap(cx, cy, cw, ch, p.position.x, p.position.y, p.width, p.height):
            return p
    return None


@dataclass
class PlatformElement:
    """An Atari 8-bit hardware platform (Sprite or Missile) with fixed 4-line height."""
    id: str
    type: str  # "sprite" or "missile"
    position: Position
    width: int
    height: int = PLATFORM_HEIGHT

    @property
    def row_index(self) -> int:
        return get_row_index(self.position.y)

    def validate(self, scene_height: Optional[int] = None) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ModelValidationError("Platform ID must be a non-empty string.")
        if self.type not in PLATFORM_TYPES:
            raise ModelValidationError(
                f"Invalid platform type '{self.type}'. Must be one of {PLATFORM_TYPES}."
            )
        if not isinstance(self.height, int) or self.height != PLATFORM_HEIGHT:
            raise InvalidPlatformDimensionError(
                f"Platform height must be exactly {PLATFORM_HEIGHT} lines, got {self.height}."
            )
        allowed_w = get_allowed_widths(self.type)
        if not isinstance(self.width, int) or self.width not in allowed_w:
            raise InvalidPlatformDimensionError(
                f"Invalid width {self.width} for {self.type}. Allowed widths: {list(allowed_w)} px."
            )
        self.position.validate()
        if not is_valid_platform_y(self.position.y, scene_height=scene_height):
            if scene_height is not None and (self.position.y + PLATFORM_HEIGHT) > scene_height:
                raise InvalidPlatformPositionError(
                    f"Platform at y={self.position.y} (height {PLATFORM_HEIGHT}) exceeds scene height {scene_height}."
                )
            raise InvalidPlatformPositionError(
                f"Platform y={self.position.y} is invalid. Must satisfy y % 16 == 8 (e.g. 8, 24, 40...)."
            )

    def clone(self) -> PlatformElement:
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "position": self.position.to_dict(),
            "width": int(self.width),
            "height": int(self.height),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlatformElement:
        if not isinstance(data, dict):
            raise ModelValidationError("PlatformElement data must be a dictionary.")
        for key in ("id", "type", "position", "width"):
            if key not in data:
                raise ModelValidationError(f"Missing required PlatformElement field '{key}'.")

        raw_h = int(data.get("height", PLATFORM_HEIGHT))
        # Transparently migrate legacy scenes where platforms were stored with height 8
        if raw_h == 8:
            raw_h = PLATFORM_HEIGHT

        p = cls(
            id=str(data["id"]),
            type=str(data["type"]),
            position=Position.from_dict(data["position"]),
            width=int(data["width"]),
            height=raw_h,
        )
        p.validate()
        return p


# -----------------------------------------------------------------------------
# Scene Object (Enemies and Treasures) Constants & Model
# -----------------------------------------------------------------------------
MAX_OBJECTS_PER_ROW = 3

OBJECT_TYPE_ENEMY = "enemy"
OBJECT_TYPE_SECRET = "secret"
OBJECT_TYPE_TREASURE = "secret"  # Backward compatibility alias
OBJECT_TYPES = (OBJECT_TYPE_ENEMY, OBJECT_TYPE_SECRET)

ENEMY_SPEED_SLOW = "slow"
ENEMY_SPEED_MEDIUM = "medium"
ENEMY_SPEED_FAST = "fast"
ENEMY_SPEEDS = (ENEMY_SPEED_SLOW, ENEMY_SPEED_MEDIUM, ENEMY_SPEED_FAST)

STRATEGY_STATIONARY = "stationary"
STRATEGY_LEFT_RIGHT = "left_right"
STRATEGY_RIGHT_LEFT = "right_left"
STRATEGY_LEFT_PAUSE_RIGHT = "left_pause_right"
STRATEGY_RIGHT_PAUSE_LEFT = "right_pause_left"
MOVEMENT_STRATEGIES = (
    STRATEGY_STATIONARY,
    STRATEGY_LEFT_RIGHT,
    STRATEGY_RIGHT_LEFT,
    STRATEGY_LEFT_PAUSE_RIGHT,
    STRATEGY_RIGHT_PAUSE_LEFT,
)

ENEMY_SPEED_LABELS = {
    ENEMY_SPEED_SLOW: "Slow",
    ENEMY_SPEED_MEDIUM: "Medium",
    ENEMY_SPEED_FAST: "Fast",
}

MOVEMENT_STRATEGY_LABELS = {
    STRATEGY_STATIONARY: "Stationary",
    STRATEGY_LEFT_RIGHT: "Left - Right",
    STRATEGY_RIGHT_LEFT: "Right - Left",
    STRATEGY_LEFT_PAUSE_RIGHT: "Left - Pause - Right",
    STRATEGY_RIGHT_PAUSE_LEFT: "Right - Pause - Left",
}


class SceneObjectElement:
    """A game object instance (Enemy or Secret) placed on a platform referencing a catalogue definition."""

    def __init__(
        self,
        id: str,
        type: str,
        *args: Any,
        platform_id: str = "",
        x: int = 0,
        definition_id: str = "",
        source: Optional[str] = None,
        source_rect: Optional[Rect] = None,
        speed: Optional[str] = None,
        movement_strategy: Optional[str] = None,
        custom_width: int = 8,
        custom_height: int = 8,
        **kwargs: Any,
    ) -> None:
        raw_id = id
        if isinstance(raw_id, int) and not isinstance(raw_id, bool):
            self.id: int | str = raw_id
        else:
            try:
                self.id = int(str(raw_id).strip())
            except (ValueError, TypeError):
                self.id = str(raw_id).strip()
        norm_type = str(type).lower().strip()
        if norm_type == OBJECT_TYPE_TREASURE:
            norm_type = OBJECT_TYPE_SECRET
        self.type = norm_type

        # Handle positional args for legacy signatures
        if len(args) >= 2 and isinstance(args[1], Rect):
            # Signature: (id, type, source, source_rect, platform_id, x, ...)
            source = args[0]
            source_rect = args[1]
            if len(args) >= 3:
                platform_id = args[2]
            if len(args) >= 4:
                x = args[3]
        elif len(args) >= 1:
            # Signature: (id, type, platform_id, x, ...)
            platform_id = args[0]
            if len(args) >= 2:
                x = args[1]

        self.platform_id = str(platform_id or kwargs.get("platform_id", "")).strip()
        self.x = int(x if x is not None else kwargs.get("x", 0))

        raw_def_id = definition_id if definition_id is not None else (kwargs.get("definition_id") or kwargs.get("enemy_id") or kwargs.get("secret_id"))
        if raw_def_id is not None and str(raw_def_id).strip() != "":
            try:
                self.definition_id: int | str = int(raw_def_id)
            except (ValueError, TypeError):
                self.definition_id = str(raw_def_id).strip()
        else:
            self.definition_id = ""

        self.source = source or kwargs.get("source")
        self.source_rect = (source_rect or kwargs.get("source_rect")).clone() if (source_rect or kwargs.get("source_rect")) else None

        if self.type == OBJECT_TYPE_ENEMY:
            self.speed = speed or kwargs.get("speed") or ENEMY_SPEED_MEDIUM
            self.movement_strategy = movement_strategy or kwargs.get("movement_strategy") or STRATEGY_STATIONARY
        else:
            self.speed = speed or kwargs.get("speed")
            self.movement_strategy = movement_strategy or kwargs.get("movement_strategy")
        self.custom_width = int(custom_width)
        self.custom_height = int(custom_height)

    @property
    def width(self) -> int:
        if self.source_rect is not None:
            return self.source_rect.width
        return self.custom_width

    @property
    def height(self) -> int:
        if self.source_rect is not None:
            return self.source_rect.height
        return self.custom_height

    def validate(self, scene: Optional[Scene] = None) -> None:
        if isinstance(self.id, int) and not isinstance(self.id, bool):
            if not (1 <= self.id <= 255):
                raise ModelValidationError(f"Object ID '{self.id}' out of range. Must be 1-255.")
        elif not isinstance(self.id, str) or not self.id.strip():
            raise ModelValidationError("Object ID must be a non-empty string or integer in range 1-255.")
        if self.type not in (OBJECT_TYPE_ENEMY, OBJECT_TYPE_SECRET, OBJECT_TYPE_TREASURE):
            raise InvalidObjectPropertyError(
                f"Invalid object type '{self.type}'. Must be 'enemy' or 'secret'."
            )

        if self.source_rect is not None:
            self.source_rect.validate()

        if not isinstance(self.platform_id, str) or not self.platform_id.strip():
            raise InvalidPlatformAssignmentError("Object must be assigned to a valid platform_id.")

        if self.type == OBJECT_TYPE_ENEMY:
            if self.speed not in ENEMY_SPEEDS:
                raise InvalidObjectPropertyError(
                    f"Enemy speed '{self.speed}' is invalid. Must be one of {ENEMY_SPEEDS}."
                )
            if self.movement_strategy not in MOVEMENT_STRATEGIES:
                raise InvalidObjectPropertyError(
                    f"Enemy movement strategy '{self.movement_strategy}' is invalid. "
                    f"Must be one of {MOVEMENT_STRATEGIES}."
                )
        elif self.type in (OBJECT_TYPE_SECRET, OBJECT_TYPE_TREASURE):
            if self.speed is not None:
                raise InvalidObjectPropertyError("Secret cannot have speed parameter.")
            if self.movement_strategy is not None:
                raise InvalidObjectPropertyError("Secret cannot have movement_strategy parameter.")

        if scene is not None:
            plat = scene.get_platform(self.platform_id)
            if plat is None:
                raise InvalidPlatformAssignmentError(
                    f"Platform '{self.platform_id}' does not exist in scene."
                )
            if self.x < 0 or (self.x + self.width) > scene.width:
                raise InvalidPlatformAssignmentError(
                    f"Object '{self.id}' horizontal position x={self.x} (width={self.width}) "
                    f"exceeds scene bounds (width={scene.width})."
                )
            # Object must rest on the platform (must horizontally touch/overlap platform)
            if not (max(self.x, plat.position.x) < min(self.x + self.width, plat.position.x + plat.width)):
                raise InvalidPlatformAssignmentError(
                    f"Object '{self.id}' at x={self.x} (width={self.width}) does not rest on "
                    f"assigned platform '{plat.id}' at x={plat.position.x} (width={plat.width})."
                )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "definition_id": self.definition_id,
            "platform_id": self.platform_id,
            "x": int(self.x),
        }
        if self.type == OBJECT_TYPE_ENEMY:
            d["speed"] = self.speed
            d["movement_strategy"] = self.movement_strategy
        if self.source:
            d["source"] = self.source.replace("\\", "/")
        if self.source_rect:
            d["source_rect"] = self.source_rect.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneObjectElement:
        if not isinstance(data, dict):
            raise ModelValidationError("Object data must be a dictionary.")
        obj_id = str(data.get("id", ""))
        raw_type = str(data.get("type", OBJECT_TYPE_ENEMY)).lower()
        obj_type = OBJECT_TYPE_SECRET if raw_type in ("secret", "treasure") else OBJECT_TYPE_ENEMY
        raw_def_id = (
            data.get("definition_id")
            or data.get("enemy_id")
            or data.get("secret_id")
            or ""
        )
        if raw_def_id is not None and str(raw_def_id).strip() != "":
            try:
                definition_id: int | str = int(raw_def_id)
            except (ValueError, TypeError):
                definition_id = str(raw_def_id).strip()
        else:
            definition_id = ""
        platform_id = str(data.get("platform_id", ""))
        x = int(data.get("x", 0))

        speed = data.get("speed")
        if speed is not None:
            speed = str(speed)
        strategy = data.get("movement_strategy")
        if strategy is not None:
            strategy = str(strategy)

        if obj_type == OBJECT_TYPE_ENEMY:
            if not speed:
                speed = ENEMY_SPEED_MEDIUM
            if not strategy:
                strategy = STRATEGY_STATIONARY

        source = data.get("source")
        source_rect = None
        if "source_rect" in data and isinstance(data["source_rect"], dict):
            source_rect = Rect.from_dict(data["source_rect"])

        return cls(
            id=obj_id,
            type=obj_type,
            platform_id=platform_id,
            x=x,
            definition_id=definition_id,
            speed=speed if obj_type == OBJECT_TYPE_ENEMY else None,
            movement_strategy=strategy if obj_type == OBJECT_TYPE_ENEMY else None,
            source=source,
            source_rect=source_rect,
        )

    def clone(self) -> SceneObjectElement:
        return copy.deepcopy(self)


DEFAULT_SCENE_WIDTH = 160
DEFAULT_SCENE_HEIGHT = 192
MIN_SCENE_WIDTH = 1
MIN_SCENE_HEIGHT = 1
MAX_SCENE_WIDTH = 4096
MAX_SCENE_HEIGHT = 4096


@dataclass
class Scene:
    """Scene model representing an Atari 8-bit game screen with configurable resolution."""
    name: str = "untitled"
    schema_version: int = 1
    width: int = DEFAULT_SCENE_WIDTH
    height: int = DEFAULT_SCENE_HEIGHT
    tile_source: Optional[str] = None
    elements: list[SceneElement] = field(default_factory=list)
    platforms: list[PlatformElement] = field(default_factory=list)
    objects: list[SceneObjectElement] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._sync_z_indices()

    def _sync_z_indices(self) -> None:
        """Ensure z_index reflects the exact list order."""
        for idx, elem in enumerate(self.elements):
            elem.z_index = idx

    def get_sources(self) -> list[str]:
        """Return list of unique normalized sources used by elements and objects in order of appearance."""
        seen: set[str] = set()
        sources: list[str] = []
        for elem in self.elements:
            if elem.source:
                norm = elem.source.replace("\\", "/")
                if norm not in seen:
                    seen.add(norm)
                    sources.append(norm)
        for obj in self.objects:
            if obj.source:
                norm = obj.source.replace("\\", "/")
                if norm not in seen:
                    seen.add(norm)
                    sources.append(norm)
        return sources

    def validate(self) -> None:
        """Validate scene dimensions, elements, hardware platforms, and scene objects."""
        if not isinstance(self.width, int) or not isinstance(self.height, int):
            raise ModelValidationError("Scene width and height must be integers.")
        if self.width < MIN_SCENE_WIDTH or self.height < MIN_SCENE_HEIGHT:
            raise ModelValidationError(
                f"Scene dimensions must be strictly positive (min {MIN_SCENE_WIDTH}x{MIN_SCENE_HEIGHT}), got {self.width}x{self.height}."
            )
        if self.width > MAX_SCENE_WIDTH or self.height > MAX_SCENE_HEIGHT:
            raise ModelValidationError(
                f"Scene dimensions exceed maximum allowable limit ({MAX_SCENE_WIDTH}x{MAX_SCENE_HEIGHT}), got {self.width}x{self.height}."
            )
        if not isinstance(self.name, str) or not self.name.strip():
            raise ModelValidationError("Scene name must be a non-empty string.")

        # Validate elements
        seen_ids: set[str] = set()
        for elem in self.elements:
            elem.validate()
            if elem.id in seen_ids:
                raise DuplicateElementIdError(f"Duplicate element ID detected: '{elem.id}'.")
            seen_ids.add(elem.id)

        # Validate platforms and row hardware limits
        seen_platform_ids: set[str] = set()
        row_counts: dict[int, dict[str, int]] = {}
        for p in self.platforms:
            p.validate(scene_height=self.height)
            if p.id in seen_platform_ids:
                raise DuplicateElementIdError(f"Duplicate platform ID detected: '{p.id}'.")
            seen_platform_ids.add(p.id)

            counts = row_counts.setdefault(
                p.position.y,
                {PLATFORM_TYPE_SPRITE: 0, PLATFORM_TYPE_MISSILE: 0},
            )
            counts[p.type] += 1
            if counts[PLATFORM_TYPE_SPRITE] > MAX_SPRITES_PER_ROW:
                raise HardwareResourceLimitError(
                    f"Row y={p.position.y} exceeds sprite limit ({counts[PLATFORM_TYPE_SPRITE]}/{MAX_SPRITES_PER_ROW})."
                )
            if counts[PLATFORM_TYPE_MISSILE] > MAX_MISSILES_PER_ROW:
                raise HardwareResourceLimitError(
                    f"Row y={p.position.y} exceeds missile limit ({counts[PLATFORM_TYPE_MISSILE]}/{MAX_MISSILES_PER_ROW})."
                )

        # Validate pairwise platform collisions
        for i in range(len(self.platforms)):
            p1 = self.platforms[i]
            for j in range(i + 1, len(self.platforms)):
                p2 = self.platforms[j]
                if platforms_overlap(
                    p1.position.x, p1.position.y, p1.width, p1.height,
                    p2.position.x, p2.position.y, p2.width, p2.height,
                ):
                    raise PlatformCollisionError(
                        f"Platform '{p1.id}' ({p1.type}, x={p1.position.x}..{p1.position.x+p1.width}, y={p1.position.y}) "
                        f"collides with platform '{p2.id}' ({p2.type}, x={p2.position.x}..{p2.position.x+p2.width}, y={p2.position.y})."
                    )

        # Validate scene objects and hardware row limits (max 3 objects per platform row)
        seen_object_ids: set[str] = set()
        row_object_counts: dict[int, int] = {}
        for obj in self.objects:
            obj.validate(scene=self)
            if obj.id in seen_object_ids:
                raise DuplicateElementIdError(f"Duplicate object ID detected: '{obj.id}'.")
            seen_object_ids.add(obj.id)

            plat = self.get_platform(obj.platform_id)
            if plat is not None:
                row_y = plat.position.y
                row_object_counts[row_y] = row_object_counts.get(row_y, 0) + 1
                if row_object_counts[row_y] > MAX_OBJECTS_PER_ROW:
                    raise ObjectLimitExceededError(
                        f"Platform row y={row_y} exceeds maximum object limit "
                        f"({row_object_counts[row_y]}/{MAX_OBJECTS_PER_ROW})."
                    )

    def resize(self, new_width: int, new_height: int) -> None:
        """Resize scene canvas dimensions (does not scale or reposition elements)."""
        if not isinstance(new_width, int) or not isinstance(new_height, int):
            raise ModelValidationError("Scene dimensions must be integers.")
        if new_width < MIN_SCENE_WIDTH or new_height < MIN_SCENE_HEIGHT:
            raise ModelValidationError(
                f"Scene dimensions must be strictly positive, got {new_width}x{new_height}."
            )
        if new_width > MAX_SCENE_WIDTH or new_height > MAX_SCENE_HEIGHT:
            raise ModelValidationError(
                f"Scene dimensions exceed maximum limit of {MAX_SCENE_WIDTH}x{MAX_SCENE_HEIGHT}, got {new_width}x{new_height}."
            )
        self.width = new_width
        self.height = new_height

    def get_out_of_bounds_elements(self) -> list[str]:
        """Return list of element IDs that are partially or fully outside current scene bounds."""
        out_ids: list[str] = []
        for elem in self.elements:
            if (
                elem.position.x < 0
                or elem.position.y < 0
                or (elem.position.x + elem.width) > self.width
                or (elem.position.y + elem.height) > self.height
            ):
                out_ids.append(elem.id)
        return out_ids

    def set_tile_source(self, source: Optional[str]) -> None:
        """Set tile source metadata (optional backward compatibility)."""
        self.tile_source = source.replace("\\", "/") if source else None

    def add_element(self, element: SceneElement, index: Optional[int] = None) -> None:
        """Add an element to the scene, checking ID uniqueness."""
        element.validate()

        if any(e.id == element.id for e in self.elements):
            raise DuplicateElementIdError(f"Element with ID '{element.id}' already exists.")

        if index is None or index >= len(self.elements):
            self.elements.append(element)
        elif index <= 0:
            self.elements.insert(0, element)
        else:
            self.elements.insert(index, element)

        self._sync_z_indices()

    def remove_element(self, element_id: str) -> Optional[SceneElement]:
        """Remove an element by ID."""
        for idx, elem in enumerate(self.elements):
            if elem.id == element_id:
                removed = self.elements.pop(idx)
                self._sync_z_indices()
                return removed
        return None

    def get_element(self, element_id: str) -> Optional[SceneElement]:
        """Find an element by its ID."""
        for elem in self.elements:
            if elem.id == element_id:
                return elem
        return None

    def get_element_index(self, element_id: str) -> int:
        """Return the index of an element, or -1 if not found."""
        for idx, elem in enumerate(self.elements):
            if elem.id == element_id:
                return idx
        return -1

    def move_element(self, element_id: str, x: int, y: int) -> None:
        """Set position of an element."""
        elem = self.get_element(element_id)
        if elem is None:
            raise KeyError(f"Element '{element_id}' not found.")
        elem.position.x = int(x)
        elem.position.y = int(y)

    def set_element_flip(self, element_id: str, flip_x: bool) -> None:
        """Toggle or set horizontal flip."""
        elem = self.get_element(element_id)
        if elem is None:
            raise KeyError(f"Element '{element_id}' not found.")
        elem.flip_x = bool(flip_x)

    def reorder_element(self, element_id: str, new_index: int) -> None:
        """Move element to a new index in draw order."""
        curr_idx = self.get_element_index(element_id)
        if curr_idx < 0:
            raise KeyError(f"Element '{element_id}' not found.")
        target_idx = max(0, min(new_index, len(self.elements) - 1))
        if curr_idx == target_idx:
            return
        elem = self.elements.pop(curr_idx)
        self.elements.insert(target_idx, elem)
        self._sync_z_indices()

    def bring_to_front(self, element_id: str) -> None:
        """Move element to the top of the draw stack (rendered last/on top)."""
        self.reorder_element(element_id, len(self.elements) - 1)

    def send_to_back(self, element_id: str) -> None:
        """Move element to the bottom of the draw stack (rendered first/at bottom)."""
        self.reorder_element(element_id, 0)

    def raise_element(self, element_id: str) -> None:
        """Move element one layer up."""
        curr = self.get_element_index(element_id)
        if curr >= 0 and curr < len(self.elements) - 1:
            self.reorder_element(element_id, curr + 1)

    def lower_element(self, element_id: str) -> None:
        """Move element one layer down."""
        curr = self.get_element_index(element_id)
        if curr > 0:
            self.reorder_element(element_id, curr - 1)

    # -------------------------------------------------------------------------
    # Hardware Platforms Management
    # -------------------------------------------------------------------------
    def add_platform(self, platform: PlatformElement) -> None:
        """Add a hardware platform to the scene after validating limits and collisions."""
        platform.validate(scene_height=self.height)
        if any(p.id == platform.id for p in self.platforms):
            raise DuplicateElementIdError(f"Platform with ID '{platform.id}' already exists.")

        ok, msg = can_add_platform_to_row(
            self.platforms, platform.type, platform.position.y, scene_height=self.height
        )
        if not ok:
            raise HardwareResourceLimitError(msg)

        colliding = check_platform_collision(
            self.platforms,
            (platform.position.x, platform.position.y, platform.width, platform.height),
        )
        if colliding:
            raise PlatformCollisionError(
                f"Platform '{platform.id}' collides with existing platform '{colliding.id}' "
                f"at ({colliding.position.x}, {colliding.position.y})."
            )

        self.platforms.append(platform)

    def remove_platform(self, platform_id: str) -> Optional[PlatformElement]:
        """Remove a platform by ID, also removing any attached objects to prevent orphaned objects."""
        for idx, p in enumerate(self.platforms):
            if p.id == platform_id:
                self.objects = [o for o in self.objects if o.platform_id != platform_id]
                return self.platforms.pop(idx)
        return None

    def get_platform(self, platform_id: str) -> Optional[PlatformElement]:
        """Find a platform by its ID."""
        for p in self.platforms:
            if p.id == platform_id:
                return p
        return None

    def move_platform(self, platform_id: str, new_x: int, new_y: int) -> None:
        """Move a platform to new coordinates, enforcing row constraints, limits, and collisions."""
        p = self.get_platform(platform_id)
        if p is None:
            raise KeyError(f"Platform '{platform_id}' not found.")

        target_x = int(new_x)
        target_y = int(new_y)
        attached_objs = [o for o in self.objects if o.platform_id == platform_id]

        if target_y != p.position.y:
            if not is_valid_platform_y(target_y, scene_height=self.height):
                raise InvalidPlatformPositionError(
                    f"Target row y={target_y} is invalid or exceeds scene height {self.height}."
                )
            ok, msg = can_add_platform_to_row(
                self.platforms, p.type, target_y, exclude_id=platform_id, scene_height=self.height
            )
            if not ok:
                raise HardwareResourceLimitError(msg)

            # Check if moving attached objects to target_y exceeds the 3-object row limit
            target_row_objs = [o for o in self.get_row_objects(target_y) if o.platform_id != platform_id]
            if len(target_row_objs) + len(attached_objs) > MAX_OBJECTS_PER_ROW:
                raise ObjectLimitExceededError(
                    f"Moving platform '{platform_id}' to row y={target_y} exceeds object limit: "
                    f"target row would have {len(target_row_objs) + len(attached_objs)} objects "
                    f"(hardware limit is {MAX_OBJECTS_PER_ROW} per row)."
                )

        colliding = check_platform_collision(
            self.platforms,
            (target_x, target_y, p.width, p.height),
            exclude_id=platform_id,
        )
        if colliding:
            raise PlatformCollisionError(
                f"Moving platform '{platform_id}' to ({target_x}, {target_y}) collides with "
                f"platform '{colliding.id}' at ({colliding.position.x}, {colliding.position.y})."
            )

        dx = target_x - p.position.x
        p.position.x = target_x
        p.position.y = target_y
        for obj in attached_objs:
            obj.x += dx

    def resize_platform(self, platform_id: str, new_width: int) -> None:
        """Change platform width to another allowed hardware width without collisions."""
        p = self.get_platform(platform_id)
        if p is None:
            raise KeyError(f"Platform '{platform_id}' not found.")
        allowed = get_allowed_widths(p.type)
        if new_width not in allowed:
            raise InvalidPlatformDimensionError(
                f"Invalid width {new_width} for {p.type}. Allowed widths: {list(allowed)} px."
            )

        colliding = check_platform_collision(
            self.platforms,
            (p.position.x, p.position.y, int(new_width), p.height),
            exclude_id=platform_id,
        )
        if colliding:
            raise PlatformCollisionError(
                f"Resizing platform '{platform_id}' to width {new_width} collides with "
                f"platform '{colliding.id}' at ({colliding.position.x}, {colliding.position.y})."
            )

        p.width = int(new_width)

    def set_platform_type(
        self, platform_id: str, new_type: str, new_width: Optional[int] = None
    ) -> None:
        """Change platform type (sprite <-> missile), checking row limits and collisions."""
        p = self.get_platform(platform_id)
        if p is None:
            raise KeyError(f"Platform '{platform_id}' not found.")
        if new_type not in PLATFORM_TYPES:
            raise ModelValidationError(f"Invalid platform type '{new_type}'.")

        allowed = get_allowed_widths(new_type)
        if new_width is not None and new_width in allowed:
            target_w = new_width
        elif p.width in allowed:
            target_w = p.width
        else:
            target_w = allowed[-1]

        if new_type != p.type:
            ok, msg = can_add_platform_to_row(
                self.platforms, new_type, p.position.y, exclude_id=platform_id, scene_height=self.height
            )
            if not ok:
                raise HardwareResourceLimitError(msg)

        colliding = check_platform_collision(
            self.platforms,
            (p.position.x, p.position.y, target_w, p.height),
            exclude_id=platform_id,
        )
        if colliding:
            raise PlatformCollisionError(
                f"Changing platform '{platform_id}' to {new_type} with width {target_w} collides with "
                f"platform '{colliding.id}' at ({colliding.position.x}, {colliding.position.y})."
            )

        p.type = new_type
        p.width = target_w

    def get_platform_row_usage(
        self, y: int, exclude_id: Optional[str] = None
    ) -> tuple[int, int]:
        """Return (sprites_used, missiles_used) for row y."""
        return get_row_resource_usage(self.platforms, y, exclude_id=exclude_id)

    # -------------------------------------------------------------------------
    # Scene Objects Management (Enemies & Treasures)
    # -------------------------------------------------------------------------
    def get_object(self, object_id: Any) -> Optional[SceneObjectElement]:
        """Find a scene object by its ID."""
        for obj in self.objects:
            if obj.id == object_id or str(obj.id) == str(object_id):
                return obj
        return None

    def get_row_objects(
        self, y: int, exclude_id: Optional[Any] = None
    ) -> list[SceneObjectElement]:
        """Return all objects on platforms located at row y."""
        row_platform_ids = {p.id for p in self.platforms if p.position.y == y}
        result: list[SceneObjectElement] = []
        for obj in self.objects:
            if exclude_id and (obj.id == exclude_id or str(obj.id) == str(exclude_id)):
                continue
            if obj.platform_id in row_platform_ids:
                result.append(obj)
        return result

    def can_add_object_to_platform(
        self,
        platform_id: str,
        exclude_id: Optional[Any] = None,
        exclude_obj_id: Optional[Any] = None,
    ) -> tuple[bool, str]:
        """Check if adding an object to the specified platform satisfies the 3-object row limit."""
        eff_exclude = exclude_id if exclude_id is not None else exclude_obj_id
        plat = self.get_platform(platform_id)
        if plat is None:
            return False, f"Platform '{platform_id}' not found."
        row_objs = self.get_row_objects(plat.position.y, exclude_id=eff_exclude)
        if len(row_objs) >= MAX_OBJECTS_PER_ROW:
            return (
                False,
                f"Row y={plat.position.y} already has {len(row_objs)}/{MAX_OBJECTS_PER_ROW} objects. "
                f"Hardware limit reached for this platform row.",
            )
        return True, ""

    def add_object(self, obj: SceneObjectElement) -> None:
        """Add a scene object after validating platform assignment and hardware row limit."""
        if any(o.id == obj.id or str(o.id) == str(obj.id) for o in self.objects):
            raise DuplicateElementIdError(f"Object with ID '{obj.id}' already exists.")

        plat = self.get_platform(obj.platform_id)
        if plat is None:
            raise InvalidPlatformAssignmentError(
                f"Cannot add object '{obj.id}': assigned platform '{obj.platform_id}' does not exist."
            )

        ok, msg = self.can_add_object_to_platform(obj.platform_id)
        if not ok:
            raise ObjectLimitExceededError(msg)

        obj.validate(scene=self)
        self.objects.append(obj)

    def remove_object(self, object_id: Any) -> Optional[SceneObjectElement]:
        """Remove a scene object by ID."""
        for idx, obj in enumerate(self.objects):
            if obj.id == object_id or str(obj.id) == str(object_id):
                return self.objects.pop(idx)
        return None

    def move_object(
        self, object_id: str, new_x: int, new_platform_id: Optional[str] = None
    ) -> None:
        """Move a scene object horizontally and/or reassign to another platform."""
        obj = self.get_object(object_id)
        if obj is None:
            raise KeyError(f"Object '{object_id}' not found.")

        target_plat_id = new_platform_id or obj.platform_id
        target_plat = self.get_platform(target_plat_id)
        if target_plat is None:
            raise InvalidPlatformAssignmentError(f"Platform '{target_plat_id}' not found.")

        if target_plat_id != obj.platform_id:
            ok, msg = self.can_add_object_to_platform(target_plat_id, exclude_id=object_id)
            if not ok:
                raise ObjectLimitExceededError(msg)

        old_plat = obj.platform_id
        old_x = obj.x
        obj.platform_id = target_plat_id
        obj.x = int(new_x)

        try:
            obj.validate(scene=self)
        except Exception:
            obj.platform_id = old_plat
            obj.x = old_x
            raise

    def update_object_props(
        self,
        object_id: str,
        new_type: Optional[str] = None,
        new_definition_id: Optional[str] = None,
        new_platform_id: Optional[str] = None,
        new_source: Optional[str] = None,
        new_source_rect: Optional[Rect] = None,
        new_speed: Optional[str] = None,
        new_strategy: Optional[str] = None,
    ) -> None:
        """Update properties of an existing object with validation."""
        obj = self.get_object(object_id)
        if obj is None:
            raise KeyError(f"Object '{object_id}' not found.")

        old_type = obj.type
        old_def_id = obj.definition_id
        old_platform_id = obj.platform_id
        old_source = obj.source
        old_rect = obj.source_rect.clone() if obj.source_rect is not None else None
        old_speed = obj.speed
        old_strategy = obj.movement_strategy

        if new_platform_id is not None and new_platform_id != obj.platform_id:
            target_plat = self.get_platform(new_platform_id)
            if target_plat is None:
                raise InvalidPlatformAssignmentError(f"Platform '{new_platform_id}' not found.")
            ok, msg = self.can_add_object_to_platform(new_platform_id, exclude_id=object_id)
            if not ok:
                raise ObjectLimitExceededError(msg)
            obj.platform_id = new_platform_id

        if new_definition_id is not None:
            if str(new_definition_id).strip() != "":
                try:
                    obj.definition_id = int(new_definition_id)
                except (ValueError, TypeError):
                    obj.definition_id = str(new_definition_id).strip()
            else:
                obj.definition_id = ""

        if new_type is not None:
            norm_new_type = OBJECT_TYPE_SECRET if new_type in ("secret", "treasure") else OBJECT_TYPE_ENEMY
            obj.type = norm_new_type
            if norm_new_type == OBJECT_TYPE_SECRET:
                obj.speed = None
                obj.movement_strategy = None
            elif norm_new_type == OBJECT_TYPE_ENEMY and not obj.speed:
                obj.speed = ENEMY_SPEED_MEDIUM
                obj.movement_strategy = STRATEGY_STATIONARY

        if new_source is not None:
            obj.source = new_source
        if new_source_rect is not None:
            obj.source_rect = new_source_rect.clone()
        if obj.type == OBJECT_TYPE_ENEMY:
            if new_speed is not None:
                obj.speed = new_speed
            if new_strategy is not None:
                obj.movement_strategy = new_strategy

        try:
            obj.validate(scene=self)
        except Exception:
            obj.type = old_type
            obj.definition_id = old_def_id
            obj.platform_id = old_platform_id
            obj.source = old_source
            obj.source_rect = old_rect
            obj.speed = old_speed
            obj.movement_strategy = old_strategy
            raise

    def clone(self) -> Scene:
        """Deep copy of the scene."""
        return copy.deepcopy(self)
