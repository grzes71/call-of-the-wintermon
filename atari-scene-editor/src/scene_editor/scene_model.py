"""Data models and operations for the Atari 8-bit Scene Editor."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import math
from typing import Any, Optional
import warnings

from .catalogue_model import (
    SCROLL_MODES,
    SCROLL_NONE,
    SCROLL_PERIODS_FRAMES,
    SECRET_CHANNEL_MISSILES,
    SECRET_CHANNEL_PLAYER,
)


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


# ANTIC Mode E packs 4 pixels per byte and the game renderer reads tileset bitmaps in
# whole bytes (`w_bytes = (w + 3) // 4`), so an element crop must start on a multiple of
# this many pixels and be this many pixels wide, otherwise the game draws a horizontally
# shifted / wider tile than the editor previews.
SOURCE_X_ALIGN = 4


def align_source_x(x: float | int) -> int:
    """Round a crop source x down to the byte grid used by the game renderer."""
    return max(0, int(round(float(x)))) // SOURCE_X_ALIGN * SOURCE_X_ALIGN


def align_crop_width(width: float | int) -> int:
    """Round a crop width up to whole bytes (never below one byte).

    Rounding up keeps every pixel the author selected: the renderer reads whole bytes
    anyway, so the extra pixels are already part of the drawn tile.
    """
    value = max(1, int(round(float(width))))
    return max(SOURCE_X_ALIGN, -(-value // SOURCE_X_ALIGN) * SOURCE_X_ALIGN)


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

    def normalize_crop(self) -> bool:
        """Snap the crop onto the ANTIC Mode E byte grid (x down, width up).

        Returns True when anything changed, so callers can report the fix.
        """
        aligned_x = align_source_x(self.source_rect.x)
        aligned_w = align_crop_width(self.source_rect.width)
        if aligned_x == self.source_rect.x and aligned_w == self.source_rect.width:
            return False
        self.source_rect.x = aligned_x
        self.source_rect.width = aligned_w
        return True

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

SPRITE_WIDTHS = (8, 16, 24, 32, 48, 64, 96)
MISSILE_WIDTHS = (8, 32)
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


def get_required_platform_resources(platform_type: str, width: int) -> int:
    """Calculate the number of hardware resources (sprites or missiles) required for a platform.

    - Sprite: 24 px requires 2 sprites (16px double + 8px normal).
      Otherwise ceil(width / 32) (1 resource up to 32px, 2 up to 64px, 3 up to 96px).
    - Missile: 32 px requires 4 missiles (quad width across all 4).
      8 px requires 1 missile (quad width on 1 missile).

    Raises ModelValidationError if platform_type is invalid.
    Raises InvalidPlatformDimensionError if width is not in allowed widths for the given type.
    """
    if platform_type not in PLATFORM_TYPES:
        raise ModelValidationError(
            f"Invalid platform type '{platform_type}'. Must be one of {PLATFORM_TYPES}."
        )
    allowed = get_allowed_widths(platform_type)
    if not isinstance(width, int) or width not in allowed:
        raise InvalidPlatformDimensionError(
            f"Invalid width {width} for {platform_type}. Allowed widths: {list(allowed)} px."
        )
    if platform_type == PLATFORM_TYPE_SPRITE:
        if width == 24:
            return 2
        return math.ceil(width / 32)
    elif platform_type == PLATFORM_TYPE_MISSILE:
        return 4 if width == 32 else 1
    raise ModelValidationError(f"Unsupported platform type: '{platform_type}'.")


def get_row_resource_usage(
    platforms: list[PlatformElement],
    y: int,
    exclude_id: Optional[str] = None,
) -> tuple[int, int]:
    """Return (sprite_count, missile_count) resources used for row y in the given platform list."""
    sprites = 0
    missiles = 0
    for p in platforms:
        if exclude_id and p.id == exclude_id:
            continue
        if p.position.y == y:
            if p.type == PLATFORM_TYPE_SPRITE:
                sprites += get_required_platform_resources(p.type, p.width)
            elif p.type == PLATFORM_TYPE_MISSILE:
                missiles += get_required_platform_resources(p.type, p.width)
    return sprites, missiles


def can_add_platform_to_row(
    platforms: list[PlatformElement],
    platform_type: str,
    y: int,
    exclude_id: Optional[str] = None,
    scene_height: Optional[int] = None,
    width: Optional[int] = None,
) -> tuple[bool, str]:
    """Check if adding/moving/resizing a platform of platform_type to row y is within hardware limits and bounds."""
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

    if platform_type not in PLATFORM_TYPES:
        return (
            False,
            f"Unknown platform type: '{platform_type}'. Must be 'sprite' or 'missile'.",
        )

    needed = 1
    if width is not None:
        try:
            needed = get_required_platform_resources(platform_type, width)
        except (InvalidPlatformDimensionError, ModelValidationError) as exc:
            return False, str(exc)

    sprites, missiles = get_row_resource_usage(platforms, y, exclude_id=exclude_id)
    if platform_type == PLATFORM_TYPE_SPRITE:
        if sprites + needed > MAX_SPRITES_PER_ROW:
            return (
                False,
                f"Row y={y} would exceed sprite limit: {sprites + needed}/{MAX_SPRITES_PER_ROW} "
                f"(requires {needed}, row currently has {sprites}/{MAX_SPRITES_PER_ROW}).",
            )
    elif platform_type == PLATFORM_TYPE_MISSILE:
        if missiles + needed > MAX_MISSILES_PER_ROW:
            return (
                False,
                f"Row y={y} would exceed missile limit: {missiles + needed}/{MAX_MISSILES_PER_ROW} "
                f"(requires {needed}, row currently has {missiles}/{MAX_MISSILES_PER_ROW}).",
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
    color_profile_id: Optional[int] = None
    # Colour scroll of this platform's row colours: SCROLL_NONE (default, static), "slow"
    # (1 step / 20 frames), "medium" (10) or "fast" (5). Like `color_profile_id` it is a
    # row-wide property: every platform in the same row must use the same value (the DLI paints
    # the row's colours once, so the game can only scroll them together).
    scroll: str = SCROLL_NONE

    @property
    def row_index(self) -> int:
        return get_row_index(self.position.y)

    @property
    def required_resources(self) -> int:
        """Return the number of hardware resources (sprites or missiles) consumed by this platform."""
        return get_required_platform_resources(self.type, self.width)

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
        if self.color_profile_id is not None:
            if isinstance(self.color_profile_id, str) and self.color_profile_id.strip().isdigit():
                self.color_profile_id = int(self.color_profile_id.strip())
            if (
                isinstance(self.color_profile_id, bool)
                or not isinstance(self.color_profile_id, int)
                or not (1 <= self.color_profile_id <= 255)
            ):
                raise ModelValidationError(
                    f"Platform color_profile_id must be an integer between 1 and 255 or None, got {self.color_profile_id!r}."
                )
        if not isinstance(self.scroll, str):
            raise ModelValidationError(
                f"Platform 'scroll' must be a string, got {self.scroll!r}."
            )
        self.scroll = self.scroll.strip().lower()
        if self.scroll not in SCROLL_MODES:
            raise ModelValidationError(
                f"Platform 'scroll' must be one of {SCROLL_MODES}, got {self.scroll!r}."
            )

    def clone(self) -> PlatformElement:
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "type": self.type,
            "position": self.position.to_dict(),
            "width": int(self.width),
            "height": int(self.height),
        }
        if self.color_profile_id is not None:
            d["color_profile_id"] = int(self.color_profile_id)
        if self.scroll != SCROLL_NONE:
            d["scroll"] = self.scroll
        return d

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

        raw_cprof = data.get("color_profile_id")
        color_profile_id: Optional[int] = None
        if raw_cprof is not None:
            if isinstance(raw_cprof, str) and raw_cprof.strip().isdigit():
                color_profile_id = int(raw_cprof.strip())
            elif isinstance(raw_cprof, int) and not isinstance(raw_cprof, bool):
                color_profile_id = raw_cprof
            else:
                raise ModelValidationError(
                    f"Platform color_profile_id must be an integer between 1 and 255 or None, got {raw_cprof!r}."
                )

        p = cls(
            id=str(data["id"]),
            type=str(data["type"]),
            position=Position.from_dict(data["position"]),
            width=int(data["width"]),
            height=raw_h,
            color_profile_id=color_profile_id,
            scroll=str(data.get("scroll", SCROLL_NONE)),
        )
        p.validate()
        return p


# -----------------------------------------------------------------------------
# Scene Object (Enemies and Treasures) Constants & Model
# -----------------------------------------------------------------------------
MAX_ENEMIES_PER_ROW = 3
# Sprite channel budget per platform row and dependency stage: Players 1..3 plus the 5th
# player (the four missiles combined) = 4 channels. Enemies always claim their channels
# first, so one row/stage may hold `enemies + secrets <= MAX_CHANNELS_PER_ROW` - the same
# rule the compiler enforces (scripts/sprite_roles.py, scripts/compile_scenes.py).
MAX_CHANNELS_PER_ROW = 4
MAX_SECRETS_PER_STAGE = MAX_CHANNELS_PER_ROW  # backward-compatible alias
MAX_OBJECTS_PER_ROW = 3  # Kept for backward compatibility

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
        sprite_id: Optional[int] = None,
        sprite: Optional[str] = None,
        dependency: Optional[int] = None,
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

        raw_sprite_name = sprite if sprite is not None else kwargs.get("sprite")
        if raw_sprite_name is not None and str(raw_sprite_name).strip() and str(raw_sprite_name).lower() != "none":
            self.sprite: Optional[str] = str(raw_sprite_name).strip()
        else:
            self.sprite = None

        raw_sprite = sprite_id if sprite_id is not None else kwargs.get("sprite_id")
        if raw_sprite is not None and str(raw_sprite).strip() != "" and str(raw_sprite).lower() != "none":
            try:
                self.sprite_id: Optional[int] = int(raw_sprite)
            except (ValueError, TypeError):
                self.sprite_id = None
        else:
            self.sprite_id = None

        raw_dep = dependency if dependency is not None else kwargs.get("dependency")
        if raw_dep is not None and str(raw_dep).strip() != "" and str(raw_dep).lower() != "none":
            try:
                self.dependency: Optional[int] = int(raw_dep)
            except (ValueError, TypeError):
                self.dependency = None
        else:
            self.dependency = None

    def get_effective_sprite(self, catalogues: Any = None) -> Optional[str]:
        """Return explicit sprite name or fallback to definition's sprite name from catalogues."""
        if self.sprite:
            return self.sprite
        if catalogues and self.definition_id:
            try:
                norm_id = int(self.definition_id)
                cat_item = catalogues.enemies.get(norm_id) if self.type == OBJECT_TYPE_ENEMY else catalogues.secrets.get(norm_id)
                if cat_item:
                    if getattr(cat_item, "sprite", None):
                        return cat_item.sprite
                    if getattr(cat_item, "sprite_id", None) and hasattr(catalogues, "sprites") and cat_item.sprite_id in catalogues.sprites:
                        return getattr(catalogues.sprites[cat_item.sprite_id], "description", None)
            except (ValueError, TypeError):
                pass
        if self.sprite_id is not None and catalogues and hasattr(catalogues, "sprites") and self.sprite_id in catalogues.sprites:
            return getattr(catalogues.sprites[self.sprite_id], "description", None)
        return None

    def get_effective_sprite_id(self, catalogues: Any = None) -> Optional[int]:
        """Return explicit sprite_id or resolved from sprite name or fallback to definition's sprite_id from catalogues."""
        if self.sprite_id is not None:
            return self.sprite_id
        if self.sprite and catalogues and hasattr(catalogues, "sprites_by_name"):
            norm_name = self.sprite.strip().lower()
            if norm_name in catalogues.sprites_by_name:
                return catalogues.sprites_by_name[norm_name].id
        if catalogues and self.definition_id:
            try:
                norm_id = int(self.definition_id)
                cat_item = catalogues.enemies.get(norm_id) if self.type == OBJECT_TYPE_ENEMY else catalogues.secrets.get(norm_id)
                if cat_item:
                    if getattr(cat_item, "sprite_id", None) is not None:
                        return cat_item.sprite_id
                    if getattr(cat_item, "sprite", None) and hasattr(catalogues, "sprites_by_name"):
                        norm_cat_name = cat_item.sprite.strip().lower()
                        if norm_cat_name in catalogues.sprites_by_name:
                            return catalogues.sprites_by_name[norm_cat_name].id
            except (ValueError, TypeError):
                pass
        return None

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
            if self.dependency is not None:
                if not isinstance(self.dependency, int) or isinstance(self.dependency, bool) or not (1 <= self.dependency <= 255):
                    raise ModelValidationError(
                        f"Secret 'dependency' must be an integer between 1 and 255, got {self.dependency!r}."
                    )
                if self.definition_id and str(self.dependency) == str(self.definition_id):
                    raise ModelValidationError(
                        f"Secret '{self.id}' cannot depend on itself."
                    )

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

    def to_dict(self, catalogues: Optional[Any] = None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "definition_id": self.definition_id,
            "platform_id": self.platform_id,
            "x": int(self.x),
        }
        # Check catalogue default
        default_id: Optional[int] = None
        if catalogues and self.definition_id:
            try:
                norm_id = int(self.definition_id)
                cat_item = catalogues.enemies.get(norm_id) if self.type == OBJECT_TYPE_ENEMY else catalogues.secrets.get(norm_id)
                if cat_item:
                    default_id = getattr(cat_item, "sprite_id", None)
                    if default_id is None and getattr(cat_item, "sprite", None) and hasattr(catalogues, "sprites_by_name"):
                        norm_dn = cat_item.sprite.strip().lower()
                        if norm_dn in catalogues.sprites_by_name:
                            default_id = catalogues.sprites_by_name[norm_dn].id
            except (ValueError, TypeError):
                pass

        effective_sid = self.sprite_id
        if effective_sid is None and self.sprite and catalogues and hasattr(catalogues, "sprites_by_name"):
            norm_sn = self.sprite.strip().lower()
            if norm_sn in catalogues.sprites_by_name:
                effective_sid = catalogues.sprites_by_name[norm_sn].id

        if effective_sid is not None:
            is_default = (default_id is not None and effective_sid == default_id)
            if not is_default:
                d["sprite_id"] = int(effective_sid)

        if self.type == OBJECT_TYPE_ENEMY:
            d["speed"] = self.speed
            d["movement_strategy"] = self.movement_strategy
        elif self.type in (OBJECT_TYPE_SECRET, OBJECT_TYPE_TREASURE):
            if self.dependency is not None:
                d["dependency"] = int(self.dependency)

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

        raw_sprite = data.get("sprite")
        sprite = str(raw_sprite).strip() if (raw_sprite is not None and str(raw_sprite).strip()) else None
        if sprite is not None:
            warnings.warn(
                f"Obiekt '{obj_id}' używa przestarzałego pola 'sprite' ('{sprite}'). "
                f"Używaj numerycznego pola 'sprite_id'.",
                UserWarning,
                stacklevel=2,
            )

        raw_sprite_id = data.get("sprite_id")
        sprite_id = None
        if raw_sprite_id is not None and str(raw_sprite_id).strip() != "":
            try:
                sprite_id = int(raw_sprite_id)
            except (ValueError, TypeError):
                sprite_id = None

        raw_dep = data.get("dependency")
        if raw_dep is None and "dependency_id" in data:
            raw_dep = data.get("dependency_id")
        dep: Optional[int] = None
        if raw_dep is not None and str(raw_dep).strip() != "" and str(raw_dep).lower() != "none":
            try:
                dep = int(raw_dep)
            except (ValueError, TypeError):
                dep = None

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
            sprite_id=sprite_id,
            sprite=sprite,
            dependency=dep,
        )

    def clone(self) -> SceneObjectElement:
        return copy.deepcopy(self)


PLAYER_WIDTH = 8
PLAYER_HEIGHT = 20
DEFAULT_PLAYER_COLOR = 0x98  # Royal cyan/blue for Player 0 (COLPM0 / PCOLR0)


@dataclass
class PlayerSpawn:
    """Initial spawn position and color for the player character on a scene."""
    x: int
    y: int
    color: int = DEFAULT_PLAYER_COLOR

    @property
    def width(self) -> int:
        return PLAYER_WIDTH

    @property
    def height(self) -> int:
        return PLAYER_HEIGHT

    @property
    def right(self) -> int:
        return self.x + PLAYER_WIDTH

    @property
    def bottom(self) -> int:
        return self.y + PLAYER_HEIGHT

    def clone(self) -> PlayerSpawn:
        return PlayerSpawn(int(self.x), int(self.y), int(self.color))

    def validate(self, scene_width: Optional[int] = None, scene_height: Optional[int] = None) -> None:
        if not isinstance(self.x, int) or not isinstance(self.y, int):
            raise ModelValidationError("Player spawn coordinates must be integers.")
        if not isinstance(self.color, int) or not (0 <= self.color <= 255):
            raise ModelValidationError(
                f"Player color must be an integer between 0 and 255 ($00-$FF), got {self.color}."
            )
        if (self.color & 1) != 0:
            raise ModelValidationError(
                f"Invalid Atari player color 0x{self.color:02X}: lowest bit must be 0 (even luminance step)."
            )
        if scene_width is not None and (self.x < 0 or (self.x + PLAYER_WIDTH) > scene_width):
            raise ModelValidationError(
                f"Player spawn x={self.x} (width={PLAYER_WIDTH}) out of scene bounds (scene width={scene_width})."
            )
        if scene_height is not None and (self.y < 0 or (self.y + PLAYER_HEIGHT) > scene_height):
            raise ModelValidationError(
                f"Player spawn y={self.y} (height={PLAYER_HEIGHT}) out of scene bounds (scene height={scene_height})."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": int(self.x),
            "y": int(self.y),
            "color": int(self.color),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlayerSpawn:
        if not isinstance(data, dict):
            raise ModelValidationError("Player spawn data must be a dictionary.")
        if "x" not in data or "y" not in data:
            raise ModelValidationError("Missing required PlayerSpawn fields 'x' and 'y'.")

        color_val = DEFAULT_PLAYER_COLOR
        raw_color = data.get("color") if "color" in data else data.get("atari_color")
        if raw_color is not None:
            if isinstance(raw_color, str):
                cleaned = raw_color.strip()
                if cleaned.startswith("$"):
                    color_val = int(cleaned[1:], 16)
                elif cleaned.startswith("0x") or cleaned.startswith("0X"):
                    color_val = int(cleaned[2:], 16)
                else:
                    color_val = int(cleaned, 16)
            else:
                color_val = int(raw_color)
            color_val = color_val & 0xFE

        return cls(x=int(data["x"]), y=int(data["y"]), color=color_val)


# ---------------------------------------------------------------------------
# Scene background palette (upper / lower zone colours driven by the DLI)
# ---------------------------------------------------------------------------
# ANTIC Mode E shows four playfield colours: pixel value 0 is always COLBK (black),
# values 1..3 are COLPF0..COLPF2. engine/dli.asm re-loads COLPF0..2 once per zone, so a
# scene owns one colour triple for the upper zone and one for the lower zone.
BG_PALETTE_ZONES = ("upper", "lower")
BG_PALETTE_COLORS_PER_ZONE = 3

# Fallback palette used by scripts/compile_scenes.py when a scene stores no explicit
# palette (the trees tileset palette). tests/test_scene_background_palette.py asserts the
# editor and the compiler agree on this value.
DEFAULT_BACKGROUND_PALETTE_COLORS = (0xC4, 0xC8, 0xDC)


def parse_atari_color_value(raw: Any, field_name: str = "color") -> int:
    """Parse an Atari colour register value from an int or hex string ('$C4', '0xC4', 'C4').

    GTIA ignores bit 0, so the returned value is always even.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise ModelValidationError(
            f"{field_name} must be an integer or hex string, got {type(raw).__name__}."
        )
    if isinstance(raw, int):
        value = raw
    else:
        cleaned = raw.strip()
        if not cleaned:
            raise ModelValidationError(f"{field_name} cannot be empty.")
        try:
            if cleaned.startswith("$"):
                value = int(cleaned[1:], 16)
            elif cleaned.lower().startswith("0x"):
                value = int(cleaned[2:], 16)
            else:
                value = int(cleaned, 16)
        except ValueError as exc:
            raise ModelValidationError(
                f"{field_name} is not a valid Atari colour value: '{raw}'."
            ) from exc
    if not (0 <= value <= 255):
        raise ModelValidationError(f"{field_name} must be within 0x00-0xFF, got {value}.")
    return value & 0xFE


@dataclass
class BackgroundPalette:
    """Per-scene background colours for the upper and lower screen zones (3 colours each)."""

    upper: list[int] = field(default_factory=lambda: list(DEFAULT_BACKGROUND_PALETTE_COLORS))
    lower: list[int] = field(default_factory=lambda: list(DEFAULT_BACKGROUND_PALETTE_COLORS))

    def clone(self) -> BackgroundPalette:
        return BackgroundPalette(upper=list(self.upper), lower=list(self.lower))

    def get_colors(self, zone: str) -> list[int]:
        """Return the colour triple of 'upper' or 'lower'."""
        if zone not in BG_PALETTE_ZONES:
            raise ModelValidationError(
                f"Unknown background palette zone '{zone}' (expected one of {BG_PALETTE_ZONES})."
            )
        return self.upper if zone == "upper" else self.lower

    def set_color(self, zone: str, index: int, value: int) -> None:
        """Set one colour of a zone (index 0..2 maps to COLPF0..COLPF2)."""
        if not (0 <= index < BG_PALETTE_COLORS_PER_ZONE):
            raise ModelValidationError(
                f"Background palette colour index must be 0..{BG_PALETTE_COLORS_PER_ZONE - 1}, got {index}."
            )
        self.get_colors(zone)[index] = int(value) & 0xFE

    def validate(self) -> None:
        """Ensure both zones carry exactly three even, in-range Atari colour values."""
        for zone in BG_PALETTE_ZONES:
            colors = self.get_colors(zone)
            if not isinstance(colors, list) or len(colors) != BG_PALETTE_COLORS_PER_ZONE:
                raise ModelValidationError(
                    f"Background palette '{zone}' must have exactly {BG_PALETTE_COLORS_PER_ZONE} colours, "
                    f"got {colors!r}."
                )
            for idx, color in enumerate(colors):
                if isinstance(color, bool) or not isinstance(color, int):
                    raise ModelValidationError(
                        f"Background palette '{zone}' colour {idx} must be an integer, "
                        f"got {type(color).__name__}."
                    )
                if not (0 <= color <= 255):
                    raise ModelValidationError(
                        f"Background palette '{zone}' colour {idx} must be within 0x00-0xFF, got {color}."
                    )
                if color & 1:
                    raise ModelValidationError(
                        f"Background palette '{zone}' colour {idx} (0x{color:02X}) must have bit 0 clear "
                        f"(GTIA ignores the lowest bit)."
                    )

    def to_dict(self) -> dict[str, list[int]]:
        return {
            "upper": [int(c) for c in self.upper],
            "lower": [int(c) for c in self.lower],
        }

    @classmethod
    def from_dict(cls, data: Any) -> BackgroundPalette:
        """Build a palette from JSON data (ints or hex strings per colour)."""
        if not isinstance(data, dict):
            raise ModelValidationError(
                "Background palette must be a dictionary with 'upper' and 'lower' zones."
            )
        palette = cls()
        for zone in BG_PALETTE_ZONES:
            if zone not in data:
                raise ModelValidationError(f"Background palette is missing the '{zone}' zone.")
            raw_colors = data[zone]
            if not isinstance(raw_colors, (list, tuple)):
                raise ModelValidationError(f"Background palette '{zone}' must be a list of colours.")
            if len(raw_colors) != BG_PALETTE_COLORS_PER_ZONE:
                raise ModelValidationError(
                    f"Background palette '{zone}' must have exactly {BG_PALETTE_COLORS_PER_ZONE} colours, "
                    f"got {len(raw_colors)}."
                )
            colors = [
                parse_atari_color_value(raw, f"background_palette.{zone}[{idx}]")
                for idx, raw in enumerate(raw_colors)
            ]
            if zone == "upper":
                palette.upper = colors
            else:
                palette.lower = colors
        palette.validate()
        return palette


# ANTIC Mode D playfield: the engine renders 160 x 96 pixels (40 bytes x 96 lines - see
# main.asm GAME_VRAM_SIZE / GAME_VRAM_LINES). Scenes must use this size to be fully
# displayed; the compiler defaults to the same height (scripts/compile_scenes.py).
ANTIC_D_PLAYFIELD_WIDTH = 160
ANTIC_D_PLAYFIELD_HEIGHT = 96

DEFAULT_SCENE_WIDTH = ANTIC_D_PLAYFIELD_WIDTH
DEFAULT_SCENE_HEIGHT = ANTIC_D_PLAYFIELD_HEIGHT
MIN_SCENE_WIDTH = 1
MIN_SCENE_HEIGHT = 1
MAX_SCENE_WIDTH = 4096
MAX_SCENE_HEIGHT = 4096


def playfield_rows_overflow(height: int) -> int:
    """How many scene rows sit below the visible ANTIC D playfield (0 = fully visible)."""
    try:
        return max(0, int(height) - ANTIC_D_PLAYFIELD_HEIGHT)
    except (TypeError, ValueError):
        return 0


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
    row_color_profiles: list[Optional[int]] = field(default_factory=lambda: [None] * 6)
    background_palette: Optional[BackgroundPalette] = None
    catalogues: Optional[Any] = None
    player_spawn: Optional[PlayerSpawn] = None

    def __post_init__(self) -> None:
        self._sync_z_indices()
        self._ensure_row_color_profiles()
        self._sync_platform_color_profiles()

    def _ensure_row_scroll(self) -> None:
        """Force every platform in a row to that row's scroll mode (row-wide, like the profile).

        The effective value of a row is the first scroll mode explicitly set by one of its
        platforms ("none" means "not set"), so a platform that sets "medium" makes the whole row
        scroll - and a scene that mixes values still loads instead of failing validation.
        """
        row_modes: dict[int, str] = {}
        for platform in self.platforms:
            row_y = platform.position.y
            if platform.scroll != SCROLL_NONE and row_y not in row_modes:
                row_modes[row_y] = platform.scroll
        for platform in self.platforms:
            platform.scroll = row_modes.get(platform.position.y, SCROLL_NONE)

    def _ensure_row_color_profiles(self) -> None:
        """Ensure row_color_profiles has entries for all rows and infer from platforms if needed."""
        if not isinstance(self.height, int) or isinstance(self.height, bool):
            return
        rows = get_allowed_platform_rows(self.height)
        max_rows = max(6, len(rows))
        while len(self.row_color_profiles) < max_rows:
            self.row_color_profiles.append(None)
        # Infer row profiles from platforms and check for row profile conflicts
        seen_row_cprofs: dict[int, tuple[str, Optional[int]]] = {}
        for p in self.platforms:
            r = p.row_index
            if r in seen_row_cprofs:
                first_id, first_cp = seen_row_cprofs[r]
                if p.color_profile_id is not None and first_cp is not None and p.color_profile_id != first_cp:
                    raise ModelValidationError(
                        f"Niezgodność profilu kolorów w wierszu y={p.position.y}: "
                        f"platforma '{first_id}' ma profil {first_cp}, a platforma '{p.id}' ma profil {p.color_profile_id}. "
                        f"Wszystkie platformy w danym wierszu muszą korzystać z jednego profilu kolorów."
                    )
            else:
                seen_row_cprofs[r] = (p.id, p.color_profile_id)

            if 0 <= r < len(self.row_color_profiles):
                if self.row_color_profiles[r] is None:
                    if p.color_profile_id is not None:
                        self.row_color_profiles[r] = p.color_profile_id
                elif p.color_profile_id is not None and p.color_profile_id != self.row_color_profiles[r]:
                    raise ModelValidationError(
                        f"Platforma '{p.id}' w wierszu y={p.position.y} ma profil kolorów {p.color_profile_id}, "
                        f"podczas gdy wiersz ma przypisany profil {self.row_color_profiles[r]}. "
                        f"Wszystkie platformy w danym wierszu muszą korzystać z jednego profilu kolorów."
                    )

    def _sync_platform_color_profiles(self) -> None:
        """Ensure all platforms reflect their row's color profile."""
        for p in self.platforms:
            r = p.row_index
            if 0 <= r < len(self.row_color_profiles):
                p.color_profile_id = self.row_color_profiles[r]

    def get_row_color_profile_id(self, row_index: int) -> Optional[int]:
        """Return the color profile ID assigned to the given platform row index."""
        if 0 <= row_index < len(self.row_color_profiles):
            return self.row_color_profiles[row_index]
        return None

    def effective_background_palette(self) -> BackgroundPalette:
        """Explicit scene background palette, or the compiler default when none is stored."""
        if self.background_palette is not None:
            return self.background_palette
        return BackgroundPalette()

    def get_background_colors(self, zone: str) -> list[int]:
        """Colour triple of a background zone ('upper'/'lower'), explicit or default."""
        return self.effective_background_palette().get_colors(zone)

    def set_row_color_profile_id(self, row_index: int, profile_id: Optional[int]) -> None:
        """Set the color profile ID for a platform row, updating all platforms in that row."""
        while len(self.row_color_profiles) <= row_index:
            self.row_color_profiles.append(None)
        self.row_color_profiles[row_index] = profile_id
        for p in self.platforms:
            if p.row_index == row_index:
                p.color_profile_id = profile_id

    def set_platform_color_profile(self, platform_id: str, profile_id: Optional[int]) -> None:
        """Set color profile for the row containing the specified platform."""
        p = self.get_platform(platform_id)
        if p is not None:
            self.set_row_color_profile_id(p.row_index, profile_id)

    def get_secret_stage(self, definition_id: Any) -> int:
        """Resolve stage (1-based) for a secret definition. Defaults to 1 if catalogues missing or not found."""
        if self.catalogues is not None and hasattr(self.catalogues, "get_secret_stage"):
            return self.catalogues.get_secret_stage(definition_id)
        return 1

    def get_secret_dependency(self, definition_id: Any, obj: Optional[SceneObjectElement] = None) -> Optional[int]:
        """Resolve dependency (None or int ID) for a secret.
        Priority:
        1. Object-level explicit dependency (obj.dependency)
        2. Scene object instance for definition_id with dependency set
        3. Fallback to catalogue secret definition's dependency (legacy compatibility)
        """
        if obj is not None and obj.dependency is not None:
            return obj.dependency
        if obj is None:
            for o in self.objects:
                if o.type in (OBJECT_TYPE_SECRET, OBJECT_TYPE_TREASURE) and str(o.definition_id) == str(definition_id):
                    if o.dependency is not None:
                        return o.dependency
        if self.catalogues is not None:
            if hasattr(self.catalogues, "get_secret_dependency"):
                return self.catalogues.get_secret_dependency(definition_id)
            if hasattr(self.catalogues, "get_secret"):
                sec = self.catalogues.get_secret(definition_id)
                if sec is not None and getattr(sec, "dependency", None) is not None:
                    return sec.dependency
        return None

    def get_dependency_display_name(self, dependency: Optional[int]) -> str:
        """Return human-readable representation of a dependency, e.g. "'Gold Key' (ID 1)" or "None"."""
        if dependency is None:
            return "None"
        if self.catalogues is not None:
            if hasattr(self.catalogues, "get_dependency_display_name"):
                return self.catalogues.get_dependency_display_name(dependency)
            if hasattr(self.catalogues, "get_secret"):
                sec = self.catalogues.get_secret(dependency)
                if sec is not None:
                    return f"'{sec.name}' (ID {dependency})"
        return f"ID {dependency}"

    def get_secret_channel_kind(self, definition_id: Any, obj: Optional[SceneObjectElement] = None) -> str:
        """Rendering channel kind of a secret definition: "player" or "missiles".

        Read from the catalogue (scenes/definitions.json); a missing definition or field means
        "missiles", which is exactly what the compiler assumes (backward compatible).
        """
        cat_item: Any = None
        if self.catalogues is not None:
            if hasattr(self.catalogues, "get_secret"):
                cat_item = self.catalogues.get_secret(definition_id)
            if cat_item is None and hasattr(self.catalogues, "secrets"):
                try:
                    cat_item = self.catalogues.secrets.get(int(definition_id))
                except (TypeError, ValueError):
                    cat_item = None

        raw = getattr(cat_item, "channel", None)
        if raw is None and isinstance(cat_item, dict):
            raw = cat_item.get("channel")
        return str(raw or SECRET_CHANNEL_MISSILES).strip().lower()

    def get_row_channel_usage(self, y: int, exclude_id: Optional[Any] = None) -> dict[str, Any]:
        """Sprite channel usage of the platform row at y (hardware budget model).

        Enemies always occupy Players 1..3 first, so one platform row and dependency stage can
        hold at most MAX_CHANNELS_PER_ROW sprites (three players + the 5th player). Within a
        stage a "player" secret needs one of P1..P3 that neither an enemy nor another
        player-channel secret of the same stage has taken, while a "missiles" secret needs the
        single 5th player channel. Mirrors the assignment in scripts/compile_scenes.py.

        Returns a dict with "enemies" (count), "stages" ({dependency: {"player": [...],
        "missiles": [...]}}) and "errors" (human readable conflicts, empty when the row fits).
        """
        row_objs = self.get_row_objects(y, exclude_id=exclude_id)
        enemies = [o for o in row_objs if o.type == OBJECT_TYPE_ENEMY]
        used_players = min(len(enemies), MAX_CHANNELS_PER_ROW - 1)
        stages: dict[Optional[int], dict[str, list[SceneObjectElement]]] = {}
        errors: list[str] = []

        for o in row_objs:
            if o.type not in (OBJECT_TYPE_SECRET, OBJECT_TYPE_TREASURE):
                continue
            dep = self.get_secret_dependency(o.definition_id, obj=o)
            kind = self.get_secret_channel_kind(o.definition_id, obj=o)
            stage = stages.setdefault(dep, {"player": [], "missiles": []})
            stage["player" if kind == SECRET_CHANNEL_PLAYER else "missiles"].append(o)

        for dep, stage in stages.items():
            dep_name = self.get_dependency_display_name(dep)
            player_secrets = stage["player"]
            missile_secrets = stage["missiles"]
            free_players = (MAX_CHANNELS_PER_ROW - 1) - used_players
            if len(missile_secrets) > 1:
                ids = ", ".join(f"'{s.id}'" for s in missile_secrets)
                errors.append(
                    f"Platform row y={y}: {len(missile_secrets)} secrets of dependency {dep_name} "
                    f"({ids}) ask for the 5th player channel - only one fits (missiles)."
                )
            if len(player_secrets) > free_players:
                ids = ", ".join(f"'{s.id}'" for s in player_secrets)
                errors.append(
                    f"Platform row y={y}: {len(player_secrets)} player-channel secret(s) of "
                    f"dependency {dep_name} ({ids}) but only {free_players} of Players 1..3 are free "
                    f"({used_players} taken by enemies)."
                )
            total = used_players + len(player_secrets) + len(missile_secrets)
            if total > MAX_CHANNELS_PER_ROW:
                errors.append(
                    f"Platform row y={y}: {used_players} enemy(ies) + "
                    f"{len(player_secrets) + len(missile_secrets)} secret(s) of dependency {dep_name} "
                    f"exceed the {MAX_CHANNELS_PER_ROW}-channel budget (3 players + 5th player)."
                )
        return {"enemies": len(enemies), "stages": stages, "errors": errors}

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

        if self.background_palette is not None:
            self.background_palette.validate()

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
            counts[p.type] += p.required_resources
            if counts[PLATFORM_TYPE_SPRITE] > MAX_SPRITES_PER_ROW:
                raise HardwareResourceLimitError(
                    f"Row y={p.position.y} exceeds sprite limit ({counts[PLATFORM_TYPE_SPRITE]}/{MAX_SPRITES_PER_ROW})."
                )
            if counts[PLATFORM_TYPE_MISSILE] > MAX_MISSILES_PER_ROW:
                raise HardwareResourceLimitError(
                    f"Row y={p.position.y} exceeds missile limit ({counts[PLATFORM_TYPE_MISSILE]}/{MAX_MISSILES_PER_ROW})."
                )

        # Validate that all platforms in the same row share the exact same color profile
        row_plat_cprofs: dict[int, tuple[str, Optional[int]]] = {}
        for p in self.platforms:
            py = p.position.y
            if py in row_plat_cprofs:
                first_id, first_cp = row_plat_cprofs[py]
                if p.color_profile_id != first_cp:
                    raise ModelValidationError(
                        f"Wiersz platform y={py} zawiera platformy o różnych profilach kolorów: "
                        f"platforma '{first_id}' ma profil {first_cp}, a platforma '{p.id}' ma profil {p.color_profile_id}. "
                        f"Wszystkie platformy w danym wierszu muszą korzystać z jednego profilu kolorów."
                    )
            else:
                row_plat_cprofs[py] = (p.id, p.color_profile_id)

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

        # Validate scene objects and hardware row limits:
        # - Max MAX_ENEMIES_PER_ROW enemies per platform row
        # - Sprite channel budget per platform row and dependency stage: enemies + secrets of
        #   one stage <= MAX_CHANNELS_PER_ROW (3 players + the 5th player), because enemies
        #   always claim their channels first and each kind of secret needs a channel it can
        #   use ("player" -> P1..P3, "missiles" -> the single 5th player channel).
        seen_object_ids: set[str] = set()
        row_enemy_counts: dict[int, int] = {}

        for obj in self.objects:
            obj.validate(scene=self)
            str_id = str(obj.id)
            if str_id in seen_object_ids:
                raise DuplicateElementIdError(f"Duplicate object ID detected: '{obj.id}'.")
            seen_object_ids.add(str_id)

            plat = self.get_platform(obj.platform_id)
            if plat is not None and obj.type == OBJECT_TYPE_ENEMY:
                row_y = plat.position.y
                row_enemy_counts[row_y] = row_enemy_counts.get(row_y, 0) + 1
                if row_enemy_counts[row_y] > MAX_ENEMIES_PER_ROW:
                    raise ObjectLimitExceededError(
                        f"Platform row y={row_y} exceeds maximum enemy limit "
                        f"({row_enemy_counts[row_y]}/{MAX_ENEMIES_PER_ROW})."
                    )

        for row_y in sorted({p.position.y for p in self.platforms}):
            usage = self.get_row_channel_usage(row_y)
            if usage["errors"]:
                raise ObjectLimitExceededError(" ".join(usage["errors"]))

        # Scroll is a row-wide setting (like the row colour profile): normalise it - the first
        # explicitly set value in a row wins and every platform in that row follows. A half-edited
        # scene (one platform scrolled, the rest not yet) must still load instead of failing.
        self._ensure_row_scroll()

        # Check for circular secret dependencies on this scene
        scene_secret_defs: dict[int, Optional[int]] = {}
        for o in self.objects:
            if o.type in (OBJECT_TYPE_SECRET, OBJECT_TYPE_TREASURE) and o.definition_id:
                try:
                    s_def = int(o.definition_id)
                    s_dep = self.get_secret_dependency(s_def, obj=o)
                    scene_secret_defs[s_def] = s_dep
                except (ValueError, TypeError):
                    pass
        for start_def in scene_secret_defs:
            visited = set()
            curr = start_def
            while curr in scene_secret_defs:
                if curr in visited:
                    raise ModelValidationError(
                        f"Cyclic dependency detected on scene involving secret definition ID {curr}."
                    )
                visited.add(curr)
                curr = scene_secret_defs[curr]
                if curr is None:
                    break

        # Validate player spawn if present
        if self.player_spawn is not None:
            self.player_spawn.validate(scene_width=self.width, scene_height=self.height)

    def set_player_spawn(self, x: int, y: int, color: Optional[int] = None) -> PlayerSpawn:
        """Set or update player initial spawn position and color on the scene."""
        if color is None:
            color = self.player_spawn.color if self.player_spawn else DEFAULT_PLAYER_COLOR
        spawn = PlayerSpawn(x=int(x), y=int(y), color=int(color))
        spawn.validate(scene_width=self.width, scene_height=self.height)
        self.player_spawn = spawn
        return spawn

    def set_player_spawn_color(self, color: int) -> None:
        """Set or update player initial color on the scene."""
        if self.player_spawn is not None:
            self.player_spawn.color = int(color) & 0xFE
            self.player_spawn.validate(scene_width=self.width, scene_height=self.height)


    def remove_player_spawn(self) -> Optional[PlayerSpawn]:
        """Remove player spawn from the scene."""
        old = self.player_spawn
        self.player_spawn = None
        return old

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
            self.platforms,
            platform.type,
            platform.position.y,
            scene_height=self.height,
            width=platform.width,
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

        r = platform.row_index
        if platform.color_profile_id is not None and self.get_row_color_profile_id(r) is None:
            self.set_row_color_profile_id(r, platform.color_profile_id)
        else:
            platform.color_profile_id = self.get_row_color_profile_id(r)

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
                self.platforms,
                p.type,
                target_y,
                exclude_id=platform_id,
                scene_height=self.height,
                width=p.width,
            )
            if not ok:
                raise HardwareResourceLimitError(msg)

            # Check if moving attached objects to target_y exceeds row limits
            target_row_objs = [o for o in self.get_row_objects(target_y) if o.platform_id != platform_id]
            moving_enemies = sum(1 for o in attached_objs if o.type == OBJECT_TYPE_ENEMY)
            target_enemies = sum(1 for o in target_row_objs if o.type == OBJECT_TYPE_ENEMY)
            if target_enemies + moving_enemies > MAX_ENEMIES_PER_ROW:
                raise ObjectLimitExceededError(
                    f"Moving platform '{platform_id}' to row y={target_y} exceeds enemy limit: "
                    f"target row would have {target_enemies + moving_enemies} enemies "
                    f"(hardware limit is {MAX_ENEMIES_PER_ROW} per row)."
                )

            # Check the sprite channel budget of the target row (enemies + secrets of one stage)
            moving_secrets = [o for o in attached_objs if o.type in (OBJECT_TYPE_SECRET, OBJECT_TYPE_TREASURE)]
            target_usage = self.get_row_channel_usage(target_y)
            target_enemies = target_usage["enemies"] + moving_enemies

            moving_stages: dict[Optional[int], dict[str, list[SceneObjectElement]]] = {}
            for m in moving_secrets:
                mdep = self.get_secret_dependency(m.definition_id, obj=m)
                mkind = self.get_secret_channel_kind(m.definition_id, obj=m)
                moving_stages.setdefault(mdep, {"player": [], "missiles": []})[
                    "player" if mkind == SECRET_CHANNEL_PLAYER else "missiles"
                ].append(m)

            for mdep, stage in moving_stages.items():
                dep_name = self.get_dependency_display_name(mdep)
                target_stage = target_usage["stages"].get(mdep, {"player": [], "missiles": []})
                players = len(target_stage["player"]) + len(stage["player"])
                missiles = len(target_stage["missiles"]) + len(stage["missiles"])

                if missiles > 1:
                    raise ObjectLimitExceededError(
                        f"Moving platform '{platform_id}' to row y={target_y} would place {missiles} "
                        f"'missiles' secrets of dependency {dep_name} in one row - the 5th player is "
                        f"a single channel."
                    )

                free_players = (MAX_CHANNELS_PER_ROW - 1) - min(target_enemies, MAX_CHANNELS_PER_ROW - 1)
                if players > free_players:
                    raise ObjectLimitExceededError(
                        f"Moving platform '{platform_id}' to row y={target_y} leaves no Player channel "
                        f"for dependency {dep_name}: {players} player secret(s) but only {free_players} "
                        f"of Players 1..3 free ({target_enemies} enemy(ies) in that row)."
                    )

                if target_enemies + players + missiles > MAX_CHANNELS_PER_ROW:
                    raise ObjectLimitExceededError(
                        f"Moving platform '{platform_id}' to row y={target_y} exceeds the sprite channel "
                        f"budget for dependency {dep_name}: {target_enemies} enemy(ies) + "
                        f"{players + missiles} secret(s) > {MAX_CHANNELS_PER_ROW} channels "
                        f"(3 players + 5th player)."
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
        p.color_profile_id = self.get_row_color_profile_id(p.row_index)
        for obj in attached_objs:
            obj.x += dx

    def resize_platform(self, platform_id: str, new_width: int) -> None:
        """Change platform width to another allowed hardware width without collisions or exceeding limits."""
        p = self.get_platform(platform_id)
        if p is None:
            raise KeyError(f"Platform '{platform_id}' not found.")
        allowed = get_allowed_widths(p.type)
        if new_width not in allowed:
            raise InvalidPlatformDimensionError(
                f"Invalid width {new_width} for {p.type}. Allowed widths: {list(allowed)} px."
            )

        # Validate hardware limits with new width
        ok, msg = can_add_platform_to_row(
            self.platforms,
            p.type,
            p.position.y,
            exclude_id=platform_id,
            scene_height=self.height,
            width=new_width,
        )
        if not ok:
            raise HardwareResourceLimitError(msg)

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

        # Always check resource limits for target configuration
        ok, msg = can_add_platform_to_row(
            self.platforms,
            new_type,
            p.position.y,
            exclude_id=platform_id,
            scene_height=self.height,
            width=target_w,
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
        obj_type: Optional[str] = None,
        definition_id: Optional[Any] = None,
        dependency: Any = ...,
        stage: Optional[int] = None,
        obj: Optional[SceneObjectElement] = None,
    ) -> tuple[bool, str]:
        """Check if adding an object to the specified platform satisfies hardware row limits:
        - Max MAX_ENEMIES_PER_ROW enemies per row.
        - Sprite channel budget: enemies + secrets of one dependency stage <= MAX_CHANNELS_PER_ROW,
          where a "player" secret needs a free Player 1..3 channel and a "missiles" secret the
          single 5th player channel."""
        eff_exclude = exclude_id if exclude_id is not None else exclude_obj_id
        plat = self.get_platform(platform_id)
        if plat is None:
            return False, f"Platform '{platform_id}' not found."

        if obj is not None:
            obj_type = obj.type
            definition_id = obj.definition_id
            if eff_exclude is None:
                eff_exclude = obj.id

        row_objs = self.get_row_objects(plat.position.y, exclude_id=eff_exclude)
        eff_type = (obj_type or "").lower()

        if eff_type == OBJECT_TYPE_ENEMY:
            enemy_count = sum(1 for o in row_objs if o.type == OBJECT_TYPE_ENEMY)
            if enemy_count >= MAX_ENEMIES_PER_ROW:
                return (
                    False,
                    f"Row y={plat.position.y} already has {enemy_count}/{MAX_ENEMIES_PER_ROW} enemies. "
                    f"Hardware limit reached for enemies on this platform row.",
                )
            return True, ""

        if eff_type in (OBJECT_TYPE_SECRET, OBJECT_TYPE_TREASURE):
            if dependency is not ...:
                eff_dep = dependency
            else:
                eff_dep = self.get_secret_dependency(definition_id, obj=obj)

            kind = self.get_secret_channel_kind(definition_id, obj=obj)
            usage = self.get_row_channel_usage(plat.position.y, exclude_id=eff_exclude)
            stage = usage["stages"].get(eff_dep, {"player": [], "missiles": []})
            enemies = usage["enemies"]
            dep_name = self.get_dependency_display_name(eff_dep)
            player_count = len(stage["player"])
            missile_count = len(stage["missiles"])

            if kind == SECRET_CHANNEL_PLAYER:
                free_players = (MAX_CHANNELS_PER_ROW - 1) - enemies
                if player_count + 1 > free_players:
                    return (
                        False,
                        f"Platform row y={plat.position.y}: no free Player channel for another "
                        f"'player' secret of dependency {dep_name} - {enemies} enemy(ies) and "
                        f"{player_count} player secret(s) already use Players 1..3. "
                        f"Switch the definition's channel to 'missiles' or use another row.",
                    )
            elif missile_count + 1 > 1:
                return (
                    False,
                    f"Platform row y={plat.position.y} already contains secret "
                    f"'{stage['missiles'][0].id}' on the 5th player channel for dependency {dep_name} - "
                    f"the 5th player is a single channel. Use another row or switch the definition's "
                    f"channel to 'player'.",
                )

            total = enemies + player_count + missile_count + 1
            if total > MAX_CHANNELS_PER_ROW:
                return (
                    False,
                    f"Platform row y={plat.position.y} would exceed the sprite channel budget: "
                    f"{enemies} enemy(ies) + {player_count + missile_count + 1} secret(s) of dependency "
                    f"{dep_name} > {MAX_CHANNELS_PER_ROW} channels (3 players + 5th player).",
                )
            return True, ""

        # Generic / untyped check (fallback for callers not specifying object type):
        enemies_count = sum(1 for o in row_objs if o.type == OBJECT_TYPE_ENEMY)
        if enemies_count >= MAX_ENEMIES_PER_ROW and len(row_objs) >= MAX_OBJECTS_PER_ROW:
            return (
                False,
                f"Row y={plat.position.y} already has {len(row_objs)}/{MAX_OBJECTS_PER_ROW} objects. "
                f"Hardware limit reached for this platform row.",
            )
        return True, ""

    def duplicate_object(
        self,
        object_id: Any,
        new_id: Optional[Any] = None,
        new_x: Optional[int] = None,
        new_platform_id: Optional[str] = None,
    ) -> SceneObjectElement:
        """Duplicate an existing scene object with new ID and optional position/platform."""
        obj = self.get_object(object_id)
        if obj is None:
            raise KeyError(f"Object '{object_id}' not found.")

        if new_id is None:
            used_ids = set()
            for o in self.objects:
                try:
                    used_ids.add(int(str(o.id).strip()))
                except (ValueError, TypeError):
                    pass
            cand = 1
            while cand in used_ids:
                cand += 1
            new_id = cand

        plat_id = new_platform_id if new_platform_id is not None else obj.platform_id
        x_pos = new_x if new_x is not None else obj.x

        copied = SceneObjectElement(
            id=new_id,
            type=obj.type,
            definition_id=obj.definition_id,
            platform_id=plat_id,
            x=x_pos,
            source=obj.source,
            source_rect=obj.source_rect.clone() if obj.source_rect else None,
            speed=obj.speed,
            movement_strategy=obj.movement_strategy,
        )
        self.add_object(copied)
        return copied

    def add_object(self, obj: SceneObjectElement) -> None:
        """Add a scene object after validating platform assignment and hardware row limit."""
        if any(o.id == obj.id or str(o.id) == str(obj.id) for o in self.objects):
            raise DuplicateElementIdError(f"Object with ID '{obj.id}' already exists.")

        plat = self.get_platform(obj.platform_id)
        if plat is None:
            raise InvalidPlatformAssignmentError(
                f"Cannot add object '{obj.id}': assigned platform '{obj.platform_id}' does not exist."
            )

        ok, msg = self.can_add_object_to_platform(obj.platform_id, obj=obj)
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
            ok, msg = self.can_add_object_to_platform(target_plat_id, obj=obj, exclude_id=object_id)
            if not ok:
                raise ObjectLimitExceededError(msg)

        old_plat = obj.platform_id
        old_x = obj.x
        obj.platform_id = target_plat_id
        obj.x = int(new_x)

        try:
            obj.validate(scene=self)
            self.validate()
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
        new_sprite_id: Optional[int | str] = None,
        new_sprite: Optional[str] = None,
        new_dependency: Any = ...,
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
        old_sprite_id = obj.sprite_id
        old_sprite = obj.sprite
        old_dependency = obj.dependency

        if new_platform_id is not None and new_platform_id != obj.platform_id:
            target_plat = self.get_platform(new_platform_id)
            if target_plat is None:
                raise InvalidPlatformAssignmentError(f"Platform '{new_platform_id}' not found.")
            ok, msg = self.can_add_object_to_platform(new_platform_id, obj=obj, exclude_id=object_id)
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

        if new_sprite is not None:
            if str(new_sprite).strip() and str(new_sprite).lower() != "none":
                obj.sprite = str(new_sprite).strip()
            else:
                obj.sprite = None

        if new_sprite_id is not None:
            if str(new_sprite_id).strip() != "" and str(new_sprite_id).lower() != "none":
                try:
                    obj.sprite_id = int(new_sprite_id)
                except (ValueError, TypeError):
                    obj.sprite_id = None
            else:
                obj.sprite_id = None

        if new_dependency is not ...:
            if new_dependency is not None and str(new_dependency).strip() != "" and str(new_dependency).lower() != "none":
                try:
                    obj.dependency = int(new_dependency)
                except (ValueError, TypeError):
                    obj.dependency = None
            else:
                obj.dependency = None

        try:
            obj.validate(scene=self)
            # Re-check row limits for the scene
            self.validate()
        except Exception:
            obj.type = old_type
            obj.definition_id = old_def_id
            obj.platform_id = old_platform_id
            obj.source = old_source
            obj.source_rect = old_rect
            obj.speed = old_speed
            obj.movement_strategy = old_strategy
            obj.sprite_id = old_sprite_id
            obj.sprite = old_sprite
            obj.dependency = old_dependency
            raise

    def clone(self) -> Scene:
        """Deep copy of the scene."""
        return copy.deepcopy(self)


# -----------------------------------------------------------------------------
# Runtime State Simulation for Secret Chains
# -----------------------------------------------------------------------------
class SceneSecretRuntime:
    """Runtime state simulator for secret dependency chains on a scene.
    Enforces the single-scene gameplay requirements:
    1. Dependencies are defined globally between secret types (SecretDefinition.dependency).
    2. Progress in collecting secrets is strictly local to each scene.
    3. A secret type with dependency=None is available from the start of the scene.
    4. A secret type with dependency=P unlocks on this scene once all secrets of type P
       present on this scene have been collected.
    5. At any time, only currently unlocked, uncollected secrets are active.
    6. Collected secrets never reappear.
    7. Collecting all secrets on the scene completes the scene and triggers transition."""

    def __init__(self, scene: Scene) -> None:
        self.scene = scene
        self.collected_secret_ids: set[str] = set()

    def get_scene_secret_objects(self) -> list[SceneObjectElement]:
        """Return all secret objects placed on this scene."""
        return [
            o for o in self.scene.objects
            if o.type in (OBJECT_TYPE_SECRET, OBJECT_TYPE_TREASURE)
        ]

    def get_scene_secret_type_ids(self) -> set[int]:
        """Return set of secret definition IDs present on this scene."""
        result = set()
        for o in self.get_scene_secret_objects():
            if o.definition_id is not None:
                try:
                    result.add(int(o.definition_id))
                except (ValueError, TypeError):
                    pass
        return result

    def is_type_fully_collected(self, defn_id: int) -> bool:
        """Check if all secrets of type defn_id on THIS scene have been collected."""
        type_objs = [
            o for o in self.get_scene_secret_objects()
            if o.definition_id is not None and int(o.definition_id) == int(defn_id)
        ]
        if not type_objs:
            return True
        return all(str(o.id) in self.collected_secret_ids for o in type_objs)

    def is_type_unlocked(self, defn_id: int) -> bool:
        """Check if a secret type is currently unlocked on THIS scene.
        A type is unlocked if:
        - It has no dependency (dependency is None).
        - OR its dependency P is unlocked AND all secrets of type P on THIS scene are collected."""
        parent_id = self.scene.get_secret_dependency(defn_id)
        if parent_id is None:
            return True

        if not self.is_type_unlocked(parent_id):
            return False

        return self.is_type_fully_collected(parent_id)

    def is_secret_active(self, secret_id: Any) -> bool:
        """Check if a secret is currently active (visible and collectible) on the scene."""
        str_id = str(secret_id)
        if str_id in self.collected_secret_ids:
            return False
        obj = self.scene.get_object(str_id)
        if obj is None or obj.type not in (OBJECT_TYPE_SECRET, OBJECT_TYPE_TREASURE):
            return False
        if obj.definition_id is None:
            return True

        try:
            defn_id = int(obj.definition_id)
        except (ValueError, TypeError):
            return True

        if not self.is_type_unlocked(defn_id):
            return False

        if self.is_type_fully_collected(defn_id):
            return False

        return True

    def get_active_secrets(self) -> list[SceneObjectElement]:
        """Return all secrets currently active on the scene."""
        return [
            obj for obj in self.scene.objects
            if self.is_secret_active(obj.id)
        ]

    def is_secret_collected(self, secret_id: Any) -> bool:
        """Return True if secret has already been collected."""
        return str(secret_id) in self.collected_secret_ids

    def is_scene_complete(self) -> bool:
        """Return True if all secrets across all types on this scene have been collected."""
        secret_objs = self.get_scene_secret_objects()
        if not secret_objs:
            return True
        return all(str(o.id) in self.collected_secret_ids for o in secret_objs)

    @property
    def current_stage(self) -> int:
        """Return the current active stage index (1-based) on this scene."""
        active = self.get_active_secrets()
        if active and self.scene.catalogues:
            first_def = active[0].definition_id
            return self.scene.get_secret_stage(first_def)
        if self.scene.catalogues:
            scene_objs = self.get_scene_secret_objects()
            if scene_objs:
                return max(self.scene.get_secret_stage(o.definition_id) for o in scene_objs)
        return 1

    def is_stage_complete(self, stage: int) -> bool:
        """Return True if all secrets assigned to given stage on this scene have been collected."""
        stage_objs = [
            o for o in self.get_scene_secret_objects()
            if self.scene.get_secret_stage(o.definition_id) == stage
        ]
        if not stage_objs:
            return True
        return all(str(o.id) in self.collected_secret_ids for o in stage_objs)

    def collect_secret(self, secret_id: Any) -> bool:
        """Collect a secret by ID.
        Returns True if this collection unlocked the next secret type on the scene, False otherwise."""
        str_id = str(secret_id)
        if not self.is_secret_active(str_id):
            return False

        obj = self.scene.get_object(str_id)
        defn_id = obj.definition_id if obj else None

        self.collected_secret_ids.add(str_id)

        # Check if collecting this secret completed its type and unlocked a successor type on this scene
        if defn_id is not None:
            try:
                norm_def_id = int(defn_id)
            except (ValueError, TypeError):
                norm_def_id = None

            if norm_def_id is not None and self.is_type_fully_collected(norm_def_id):
                for scene_obj in self.get_scene_secret_objects():
                    if scene_obj.definition_id is not None:
                        try:
                            s_def_id = int(scene_obj.definition_id)
                        except (ValueError, TypeError):
                            continue
                        if s_def_id != norm_def_id:
                            succ_dep = self.scene.get_secret_dependency(s_def_id, obj=scene_obj)
                            if succ_dep == norm_def_id:
                                if self.is_secret_active(scene_obj.id):
                                    return True
        return False


