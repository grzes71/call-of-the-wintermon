"""Unit and integration tests for scene editing commands and QUndoStack integration."""

import os
from pathlib import Path
import sys

# Ensure offscreen Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atari-scene-editor" / "src"))

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication
import pytest
from scene_editor.commands import (
    AddElementCommand,
    FlipElementCommand,
    ModifyElementPropertiesCommand,
    MoveElementCommand,
    RemoveElementCommand,
    ReorderElementCommand,
)
from scene_editor.scene_model import Position, Rect, Scene, SceneElement

# Initialize headless QApplication once for tests
_qapp = QApplication.instance() or QApplication([])


class TestSceneOperations:
    @pytest.fixture
    def empty_scene(self) -> Scene:
        return Scene(name="test_ops", width=160, height=96)

    def test_add_element_undo_redo(self, empty_scene: Scene):
        stack = QUndoStack()
        elem = SceneElement(
            id="elem-1",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(10, 20),
            flip_x=False,
        )

        cmd = AddElementCommand(empty_scene, elem)
        stack.push(cmd)

        assert len(empty_scene.elements) == 1
        assert empty_scene.elements[0].id == "elem-1"

        stack.undo()
        assert len(empty_scene.elements) == 0

        stack.redo()
        assert len(empty_scene.elements) == 1
        assert empty_scene.elements[0].id == "elem-1"

    def test_remove_element_undo_redo(self, empty_scene: Scene):
        elem = SceneElement(
            id="elem-1",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(10, 20),
        )
        empty_scene.add_element(elem)

        stack = QUndoStack()
        cmd = RemoveElementCommand(empty_scene, "elem-1")
        stack.push(cmd)

        assert len(empty_scene.elements) == 0

        stack.undo()
        assert len(empty_scene.elements) == 1
        assert empty_scene.elements[0].id == "elem-1"
        assert empty_scene.elements[0].position.x == 10

        stack.redo()
        assert len(empty_scene.elements) == 0

    def test_move_element_undo_redo(self, empty_scene: Scene):
        elem = SceneElement(
            id="elem-1",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(10, 20),
        )
        empty_scene.add_element(elem)

        stack = QUndoStack()
        cmd = MoveElementCommand(empty_scene, "elem-1", old_pos=(10, 20), new_pos=(45, 60))
        stack.push(cmd)

        assert empty_scene.elements[0].position.x == 45
        assert empty_scene.elements[0].position.y == 60

        stack.undo()
        assert empty_scene.elements[0].position.x == 10
        assert empty_scene.elements[0].position.y == 20

        stack.redo()
        assert empty_scene.elements[0].position.x == 45
        assert empty_scene.elements[0].position.y == 60

    def test_flip_element_undo_redo(self, empty_scene: Scene):
        elem = SceneElement(
            id="elem-1",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(0, 0),
            flip_x=False,
        )
        empty_scene.add_element(elem)

        stack = QUndoStack()
        cmd = FlipElementCommand(empty_scene, "elem-1", new_flip=True)
        stack.push(cmd)

        assert empty_scene.elements[0].flip_x is True

        stack.undo()
        assert empty_scene.elements[0].flip_x is False

        stack.redo()
        assert empty_scene.elements[0].flip_x is True

    def test_reorder_element_undo_redo(self, empty_scene: Scene):
        for i in range(3):
            empty_scene.add_element(
                SceneElement(
                    id=f"elem-{i}",
                    source="tiles/castles.png",
                    source_rect=Rect(0, 0, 8, 8),
                    position=Position(i * 10, 0),
                )
            )

        stack = QUndoStack()
        # Move elem-0 from index 0 to index 2
        cmd = ReorderElementCommand(empty_scene, "elem-0", new_index=2)
        stack.push(cmd)

        assert [e.id for e in empty_scene.elements] == ["elem-1", "elem-2", "elem-0"]

        stack.undo()
        assert [e.id for e in empty_scene.elements] == ["elem-0", "elem-1", "elem-2"]

        stack.redo()
        assert [e.id for e in empty_scene.elements] == ["elem-1", "elem-2", "elem-0"]

    def test_modify_properties_command_undo_redo(self, empty_scene: Scene):
        elem = SceneElement(
            id="elem-1",
            source="tiles/castles.png",
            source_rect=Rect(0, 0, 16, 16),
            position=Position(0, 0),
            flip_x=False,
        )
        empty_scene.add_element(elem)

        stack = QUndoStack()
        new_pos = Position(30, 40)
        new_rect = Rect(16, 8, 32, 24)
        cmd = ModifyElementPropertiesCommand(
            empty_scene,
            "elem-1",
            new_pos=new_pos,
            new_rect=new_rect,
            new_flip=True,
        )
        stack.push(cmd)

        assert elem.position.x == 30
        assert elem.position.y == 40
        assert elem.source_rect.width == 32
        assert elem.flip_x is True

        stack.undo()
        assert elem.position.x == 0
        assert elem.position.y == 0
        assert elem.source_rect.width == 16
        assert elem.flip_x is False

        stack.redo()
        assert elem.position.x == 30
        assert elem.flip_x is True
