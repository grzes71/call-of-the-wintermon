"""Undo/Redo commands using QUndoCommand for scene modifications."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtGui import QUndoCommand

from .scene_model import (
    PlatformElement,
    PlayerSpawn,
    Position,
    Rect,
    Scene,
    SceneElement,
    SceneObjectElement,
)


class SceneBaseCommand(QUndoCommand):
    """Base class for undoable scene commands."""

    def __init__(self, text: str, callback: Optional[Callable[[], None]] = None) -> None:
        super().__init__(text)
        self.callback = callback

    def notify(self) -> None:
        if self.callback:
            self.callback()


class AddElementCommand(SceneBaseCommand):
    """Command to add an element to the scene."""

    def __init__(
        self,
        scene: Scene,
        element: SceneElement,
        index: Optional[int] = None,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Add element {element.id}", callback)
        self.scene = scene
        self.element = element.clone()
        self.index = index if index is not None else len(scene.elements)

    def redo(self) -> None:
        self.scene.add_element(self.element.clone(), index=self.index)
        self.notify()

    def undo(self) -> None:
        self.scene.remove_element(self.element.id)
        self.notify()


class RemoveElementCommand(SceneBaseCommand):
    """Command to remove an element from the scene."""

    def __init__(
        self,
        scene: Scene,
        element_id: str,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Remove element {element_id}", callback)
        self.scene = scene
        self.element_id = element_id
        elem = scene.get_element(element_id)
        if elem is None:
            raise KeyError(f"Element '{element_id}' not found.")
        self.element = elem.clone()
        self.index = scene.get_element_index(element_id)

    def redo(self) -> None:
        self.scene.remove_element(self.element_id)
        self.notify()

    def undo(self) -> None:
        self.scene.add_element(self.element.clone(), index=self.index)
        self.notify()


class MoveElementCommand(SceneBaseCommand):
    """Command to move an element to new (x, y) coordinates."""

    def __init__(
        self,
        scene: Scene,
        element_id: str,
        old_pos: Position | tuple[int, int],
        new_pos: Position | tuple[int, int],
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Move element {element_id}", callback)
        self.scene = scene
        self.element_id = element_id
        self.old_x = old_pos.x if isinstance(old_pos, Position) else old_pos[0]
        self.old_y = old_pos.y if isinstance(old_pos, Position) else old_pos[1]
        self.new_x = new_pos.x if isinstance(new_pos, Position) else new_pos[0]
        self.new_y = new_pos.y if isinstance(new_pos, Position) else new_pos[1]

    def redo(self) -> None:
        self.scene.move_element(self.element_id, self.new_x, self.new_y)
        self.notify()

    def undo(self) -> None:
        self.scene.move_element(self.element_id, self.old_x, self.old_y)
        self.notify()


class FlipElementCommand(SceneBaseCommand):
    """Command to toggle horizontal flip on an element."""

    def __init__(
        self,
        scene: Scene,
        element_id: str,
        new_flip: bool,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Flip element {element_id}", callback)
        self.scene = scene
        self.element_id = element_id
        elem = scene.get_element(element_id)
        if elem is None:
            raise KeyError(f"Element '{element_id}' not found.")
        self.old_flip = elem.flip_x
        self.new_flip = new_flip

    def redo(self) -> None:
        self.scene.set_element_flip(self.element_id, self.new_flip)
        self.notify()

    def undo(self) -> None:
        self.scene.set_element_flip(self.element_id, self.old_flip)
        self.notify()


class ReorderElementCommand(SceneBaseCommand):
    """Command to reorder an element in draw order."""

    def __init__(
        self,
        scene: Scene,
        element_id: str,
        new_index: int,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Reorder element {element_id}", callback)
        self.scene = scene
        self.element_id = element_id
        self.old_index = scene.get_element_index(element_id)
        self.new_index = new_index

    def redo(self) -> None:
        self.scene.reorder_element(self.element_id, self.new_index)
        self.notify()

    def undo(self) -> None:
        self.scene.reorder_element(self.element_id, self.old_index)
        self.notify()


class ModifyElementPropertiesCommand(SceneBaseCommand):
    """Command for updating element position, crop rect, and flip from properties panel."""

    def __init__(
        self,
        scene: Scene,
        element_id: str,
        new_pos: Position,
        new_rect: Rect,
        new_flip: bool,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Edit properties {element_id}", callback)
        self.scene = scene
        self.element_id = element_id
        elem = scene.get_element(element_id)
        if elem is None:
            raise KeyError(f"Element '{element_id}' not found.")
        self.old_pos = Position(elem.position.x, elem.position.y)
        self.old_rect = Rect(
            elem.source_rect.x,
            elem.source_rect.y,
            elem.source_rect.width,
            elem.source_rect.height,
        )
        self.old_flip = elem.flip_x

        self.new_pos = Position(new_pos.x, new_pos.y)
        self.new_rect = Rect(new_rect.x, new_rect.y, new_rect.width, new_rect.height)
        self.new_flip = new_flip

    def redo(self) -> None:
        elem = self.scene.get_element(self.element_id)
        if elem:
            elem.position = Position(self.new_pos.x, self.new_pos.y)
            elem.source_rect = Rect(
                self.new_rect.x,
                self.new_rect.y,
                self.new_rect.width,
                self.new_rect.height,
            )
            elem.flip_x = self.new_flip
        self.notify()

    def undo(self) -> None:
        elem = self.scene.get_element(self.element_id)
        if elem:
            elem.position = Position(self.old_pos.x, self.old_pos.y)
            elem.source_rect = Rect(
                self.old_rect.x,
                self.old_rect.y,
                self.old_rect.width,
                self.old_rect.height,
            )
            elem.flip_x = self.old_flip
        self.notify()


class ResizeSceneCommand(SceneBaseCommand):
    """Command to resize the scene canvas dimensions."""

    def __init__(
        self,
        scene: Scene,
        new_width: int,
        new_height: int,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Resize scene to {new_width}x{new_height}", callback)
        self.scene = scene
        self.old_width = scene.width
        self.old_height = scene.height
        self.new_width = new_width
        self.new_height = new_height

    def redo(self) -> None:
        self.scene.resize(self.new_width, self.new_height)
        self.notify()

    def undo(self) -> None:
        self.scene.resize(self.old_width, self.old_height)
        self.notify()


# -----------------------------------------------------------------------------
# Hardware Platform Commands
# -----------------------------------------------------------------------------
class AddPlatformCommand(SceneBaseCommand):
    """Command to add a hardware platform to the scene."""

    def __init__(
        self,
        scene: Scene,
        platform: PlatformElement,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Add platform {platform.id}", callback)
        self.scene = scene
        self.platform = platform.clone()

    def redo(self) -> None:
        self.scene.add_platform(self.platform.clone())
        self.notify()

    def undo(self) -> None:
        self.scene.remove_platform(self.platform.id)
        self.notify()


class RemovePlatformCommand(SceneBaseCommand):
    """Command to remove a hardware platform from the scene, cascading to attached objects."""

    def __init__(
        self,
        scene: Scene,
        platform_id: str,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Remove platform {platform_id}", callback)
        self.scene = scene
        self.platform_id = platform_id
        p = scene.get_platform(platform_id)
        if p is None:
            raise KeyError(f"Platform '{platform_id}' not found.")
        self.platform = p.clone()
        self.attached_objects = [o.clone() for o in scene.objects if o.platform_id == platform_id]

    def redo(self) -> None:
        self.scene.remove_platform(self.platform_id)
        self.notify()

    def undo(self) -> None:
        self.scene.add_platform(self.platform.clone())
        for obj in self.attached_objects:
            self.scene.add_object(obj.clone())
        self.notify()


class MovePlatformCommand(SceneBaseCommand):
    """Command to move a platform to new coordinates."""

    def __init__(
        self,
        scene: Scene,
        platform_id: str,
        old_pos: Position | tuple[int, int],
        new_pos: Position | tuple[int, int],
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Move platform {platform_id}", callback)
        self.scene = scene
        self.platform_id = platform_id
        self.old_x = old_pos.x if isinstance(old_pos, Position) else old_pos[0]
        self.old_y = old_pos.y if isinstance(old_pos, Position) else old_pos[1]
        self.new_x = new_pos.x if isinstance(new_pos, Position) else new_pos[0]
        self.new_y = new_pos.y if isinstance(new_pos, Position) else new_pos[1]

    def redo(self) -> None:
        self.scene.move_platform(self.platform_id, self.new_x, self.new_y)
        self.notify()

    def undo(self) -> None:
        self.scene.move_platform(self.platform_id, self.old_x, self.old_y)
        self.notify()


class ResizePlatformCommand(SceneBaseCommand):
    """Command to resize a platform to a new allowed width."""

    def __init__(
        self,
        scene: Scene,
        platform_id: str,
        old_width: int,
        new_width: int,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Resize platform {platform_id} to {new_width}px", callback)
        self.scene = scene
        self.platform_id = platform_id
        self.old_width = old_width
        self.new_width = new_width

    def redo(self) -> None:
        self.scene.resize_platform(self.platform_id, self.new_width)
        self.notify()

    def undo(self) -> None:
        self.scene.resize_platform(self.platform_id, self.old_width)
        self.notify()


class ChangePlatformTypeCommand(SceneBaseCommand):
    """Command to toggle platform type between sprite and missile."""

    def __init__(
        self,
        scene: Scene,
        platform_id: str,
        old_type: str,
        old_width: int,
        new_type: str,
        new_width: int,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Change platform {platform_id} type to {new_type}", callback)
        self.scene = scene
        self.platform_id = platform_id
        self.old_type = old_type
        self.old_width = old_width
        self.new_type = new_type
        self.new_width = new_width

    def redo(self) -> None:
        self.scene.set_platform_type(self.platform_id, self.new_type, self.new_width)
        self.notify()

    def undo(self) -> None:
        self.scene.set_platform_type(self.platform_id, self.old_type, self.old_width)
        self.notify()


class ChangeRowColorProfileCommand(SceneBaseCommand):
    """Command to change the assigned color profile of an entire platform row."""

    def __init__(
        self,
        scene: Scene,
        row_index: int,
        old_profile_id: Optional[int],
        new_profile_id: Optional[int],
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Change row {row_index} color profile", callback)
        self.scene = scene
        self.row_index = int(row_index)
        self.old_profile_id = old_profile_id
        self.new_profile_id = new_profile_id

    def redo(self) -> None:
        self.scene.set_row_color_profile_id(self.row_index, self.new_profile_id)
        self.notify()

    def undo(self) -> None:
        self.scene.set_row_color_profile_id(self.row_index, self.old_profile_id)
        self.notify()


class ChangePlatformColorProfileCommand(SceneBaseCommand):
    """Command to change the assigned color profile of a platform (and its row)."""

    def __init__(
        self,
        scene: Scene,
        platform_id: str,
        old_profile_id: Optional[int],
        new_profile_id: Optional[int],
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Change platform {platform_id} color profile", callback)
        self.scene = scene
        self.platform_id = platform_id
        plat = scene.get_platform(platform_id)
        self.row_index = plat.row_index if plat else 0
        self.old_profile_id = old_profile_id
        self.new_profile_id = new_profile_id

    def redo(self) -> None:
        plat = self.scene.get_platform(self.platform_id)
        row_idx = plat.row_index if plat else self.row_index
        self.scene.set_row_color_profile_id(row_idx, self.new_profile_id)
        self.notify()

    def undo(self) -> None:
        plat = self.scene.get_platform(self.platform_id)
        row_idx = plat.row_index if plat else self.row_index
        self.scene.set_row_color_profile_id(row_idx, self.old_profile_id)
        self.notify()


# -----------------------------------------------------------------------------
# Scene Object (Enemies and Treasures) Commands
# -----------------------------------------------------------------------------
class AddSceneObjectCommand(SceneBaseCommand):
    """Command to add a scene object (enemy or treasure) to a platform."""

    def __init__(
        self,
        scene: Scene,
        scene_object: SceneObjectElement,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Add {scene_object.type} {scene_object.id}", callback)
        self.scene = scene
        self.scene_object = scene_object.clone()

    def redo(self) -> None:
        self.scene.add_object(self.scene_object.clone())
        self.notify()

    def undo(self) -> None:
        self.scene.remove_object(self.scene_object.id)
        self.notify()


class RemoveSceneObjectCommand(SceneBaseCommand):
    """Command to remove a scene object."""

    def __init__(
        self,
        scene: Scene,
        object_id: str,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Remove object {object_id}", callback)
        self.scene = scene
        self.object_id = object_id
        obj = scene.get_object(object_id)
        if obj is None:
            raise KeyError(f"Object '{object_id}' not found.")
        self.scene_object = obj.clone()

    def redo(self) -> None:
        self.scene.remove_object(self.object_id)
        self.notify()

    def undo(self) -> None:
        self.scene.add_object(self.scene_object.clone())
        self.notify()


class MoveSceneObjectCommand(SceneBaseCommand):
    """Command to move a scene object horizontally or across platforms."""

    def __init__(
        self,
        scene: Scene,
        object_id: str,
        old_x: int,
        new_x: int,
        old_platform_id: Optional[str] = None,
        new_platform_id: Optional[str] = None,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Move object {object_id}", callback)
        self.scene = scene
        self.object_id = object_id
        self.old_x = int(old_x)
        self.new_x = int(new_x)
        obj = scene.get_object(object_id)
        current_plat = obj.platform_id if obj else ""
        self.old_platform_id = old_platform_id or current_plat
        self.new_platform_id = new_platform_id or self.old_platform_id

    def redo(self) -> None:
        self.scene.move_object(self.object_id, self.new_x, self.new_platform_id)
        self.notify()

    def undo(self) -> None:
        self.scene.move_object(self.object_id, self.old_x, self.old_platform_id)
        self.notify()


class UpdateSceneObjectPropsCommand(SceneBaseCommand):
    """Command to update type, definition, platform, speed, movement strategy, or graphic of an object."""

    def __init__(
        self,
        scene: Scene,
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
        old_type: Optional[str] = None,
        old_definition_id: Optional[str] = None,
        old_platform_id: Optional[str] = None,
        old_source: Optional[str] = None,
        old_source_rect: Optional[Rect] = None,
        old_speed: Optional[str] = None,
        old_strategy: Optional[str] = None,
        old_sprite_id: Optional[int | str] = None,
        old_sprite: Optional[str] = None,
        old_dependency: Any = ...,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Update properties of {object_id}", callback)
        self.scene = scene
        self.object_id = object_id
        obj = scene.get_object(object_id)
        if obj is None:
            raise KeyError(f"Object '{object_id}' not found.")

        self.old_type = old_type if old_type is not None else obj.type
        self.new_type = new_type if new_type is not None else self.old_type

        self.old_definition_id = old_definition_id if old_definition_id is not None else obj.definition_id
        self.new_definition_id = new_definition_id if new_definition_id is not None else self.old_definition_id

        self.old_platform_id = old_platform_id if old_platform_id is not None else obj.platform_id
        self.new_platform_id = new_platform_id if new_platform_id is not None else self.old_platform_id

        self.old_source = old_source if old_source is not None else obj.source
        self.new_source = new_source if new_source is not None else self.old_source

        raw_old_rect = old_source_rect if old_source_rect is not None else obj.source_rect
        self.old_rect = raw_old_rect.clone() if raw_old_rect is not None else None
        self.new_rect = new_source_rect.clone() if new_source_rect is not None else (self.old_rect.clone() if self.old_rect else None)

        self.old_speed = old_speed if old_speed is not None else obj.speed
        self.new_speed = new_speed if new_speed is not None else self.old_speed

        self.old_strategy = old_strategy if old_strategy is not None else obj.movement_strategy
        self.new_strategy = new_strategy if new_strategy is not None else self.old_strategy

        self.old_sprite_id = old_sprite_id if old_sprite_id is not None else obj.sprite_id
        self.new_sprite_id = new_sprite_id if new_sprite_id is not None else self.old_sprite_id

        self.old_sprite = old_sprite if old_sprite is not None else obj.sprite
        self.new_sprite = new_sprite if new_sprite is not None else self.old_sprite

        self.old_dependency = old_dependency if old_dependency is not ... else getattr(obj, "dependency", None)
        self.new_dependency = new_dependency if new_dependency is not ... else self.old_dependency

    def redo(self) -> None:
        self.scene.update_object_props(
            self.object_id,
            new_type=self.new_type,
            new_definition_id=self.new_definition_id,
            new_platform_id=self.new_platform_id,
            new_source=self.new_source,
            new_source_rect=self.new_rect,
            new_speed=self.new_speed,
            new_strategy=self.new_strategy,
            new_sprite_id=self.new_sprite_id,
            new_sprite=self.new_sprite,
            new_dependency=self.new_dependency,
        )
        self.notify()

    def undo(self) -> None:
        self.scene.update_object_props(
            self.object_id,
            new_type=self.old_type,
            new_definition_id=self.old_definition_id,
            new_platform_id=self.old_platform_id,
            new_source=self.old_source,
            new_source_rect=self.old_rect,
            new_speed=self.old_speed,
            new_strategy=self.old_strategy,
            new_sprite_id=self.old_sprite_id if self.old_sprite_id is not None else "",
            new_sprite=self.old_sprite if self.old_sprite is not None else "",
            new_dependency=self.old_dependency,
        )
        self.notify()


class ChangeSceneObjectIdCommand(SceneBaseCommand):
    """Command to change the ID of a scene object."""

    def __init__(
        self,
        scene: Scene,
        old_id: Any,
        new_id: Any,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Change object ID from {old_id} to {new_id}", callback)
        self.scene = scene
        self.old_id = old_id
        self.new_id = new_id

    def redo(self) -> None:
        obj = self.scene.get_object(self.old_id)
        if obj:
            obj.id = self.new_id
        self.notify()

    def undo(self) -> None:
        obj = self.scene.get_object(self.new_id)
        if obj:
            obj.id = self.old_id
        self.notify()


class SetPlayerSpawnCommand(SceneBaseCommand):
    """Command to set or remove the player spawn position on the scene."""

    def __init__(
        self,
        scene: Scene,
        new_spawn: Optional[PlayerSpawn],
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        text = f"Set player start at ({new_spawn.x}, {new_spawn.y})" if new_spawn else "Remove player start"
        super().__init__(text, callback)
        self.scene = scene
        self.old_spawn = scene.player_spawn.clone() if scene.player_spawn else None
        self.new_spawn = new_spawn.clone() if new_spawn else None

    def redo(self) -> None:
        self.scene.player_spawn = self.new_spawn.clone() if self.new_spawn else None
        self.notify()

    def undo(self) -> None:
        self.scene.player_spawn = self.old_spawn.clone() if self.old_spawn else None
        self.notify()


class MovePlayerSpawnCommand(SceneBaseCommand):
    """Command to move the player spawn coordinates."""

    def __init__(
        self,
        scene: Scene,
        old_pos: tuple[int, int],
        new_pos: tuple[int, int],
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Move player start to ({new_pos[0]}, {new_pos[1]})", callback)
        self.scene = scene
        self.old_x, self.old_y = int(old_pos[0]), int(old_pos[1])
        self.new_x, self.new_y = int(new_pos[0]), int(new_pos[1])

    def redo(self) -> None:
        if self.scene.player_spawn:
            self.scene.player_spawn.x = self.new_x
            self.scene.player_spawn.y = self.new_y
        else:
            self.scene.player_spawn = PlayerSpawn(self.new_x, self.new_y)
        self.notify()

    def undo(self) -> None:
        if self.scene.player_spawn:
            self.scene.player_spawn.x = self.old_x
            self.scene.player_spawn.y = self.old_y
        self.notify()


class ChangePlayerSpawnColorCommand(SceneBaseCommand):
    """Command to change the player spawn color."""

    def __init__(
        self,
        scene: Scene,
        old_color: int,
        new_color: int,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(f"Change player color to ${new_color:02X}", callback)
        self.scene = scene
        self.old_color = int(old_color) & 0xFE
        self.new_color = int(new_color) & 0xFE

    def redo(self) -> None:
        if self.scene.player_spawn:
            self.scene.player_spawn.color = self.new_color
        self.notify()

    def undo(self) -> None:
        if self.scene.player_spawn:
            self.scene.player_spawn.color = self.old_color
        self.notify()


