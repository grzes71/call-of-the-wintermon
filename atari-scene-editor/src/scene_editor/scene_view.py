"""QGraphicsView and canvas management for the 160x96 Atari 8-bit scene."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QWidget

from .asset_manager import AssetManager
from .catalogue_model import ProjectCatalogues
from .scene_items import (
    PlatformGraphicsItem,
    PlayerSpawnGraphicsItem,
    SceneGraphicsItem,
    SceneObjectGraphicsItem,
)
from .scene_model import (
    ANTIC_D_PLAYFIELD_HEIGHT,
    ANTIC_D_PLAYFIELD_WIDTH,
    PLATFORM_HEIGHT,
    PlatformElement,
    PlayerSpawn,
    Scene,
    SceneElement,
    SceneObjectElement,
    is_valid_platform_y,
)


class SceneCanvas(QGraphicsScene):
    """QGraphicsScene representing the logical pixel canvas of the scene."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # Default canvas = the ANTIC Mode D playfield the engine renders (160 x 96)
        self.setSceneRect(0, 0, ANTIC_D_PLAYFIELD_WIDTH, ANTIC_D_PLAYFIELD_HEIGHT)
        self.setBackgroundBrush(QBrush(QColor(15, 15, 18)))
        self.grid_mode: str = "none"  # "none", "4x8", "8x8", "16x16"
        self.show_platform_guides: bool = True

    @property
    def canvas_width(self) -> int:
        return int(round(self.sceneRect().width()))

    @property
    def canvas_height(self) -> int:
        return int(round(self.sceneRect().height()))

    def set_canvas_size(self, width: int, height: int) -> None:
        """Update the logical boundaries of the scene canvas."""
        self.setSceneRect(0, 0, width, height)
        self.update()

    def set_grid_mode(self, mode: str) -> None:
        """Set grid overlay mode: 'none', '4x8', '8x8', '16x16'."""
        self.grid_mode = mode
        self.update()

    def set_platform_guides_visible(self, visible: bool) -> None:
        """Toggle platform row guides."""
        self.show_platform_guides = visible
        self.update()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        cw = self.canvas_width
        ch = self.canvas_height

        # Fill base canvas background
        painter.fillRect(QRectF(0, 0, cw, ch), QColor(15, 15, 18))

        # Draw subtle platform row guide bands at y % 16 == 8
        if self.show_platform_guides:
            band_brush = QBrush(QColor(0, 180, 255, 12))
            border_pen = QPen(QColor(0, 180, 255, 40), 0.5, Qt.PenStyle.DotLine)
            for y in range(8, ch - PLATFORM_HEIGHT + 1, 16):
                painter.fillRect(QRectF(0, y, cw, PLATFORM_HEIGHT), band_brush)
                painter.setPen(border_pen)
                painter.drawLine(0, y, cw, y)
                painter.drawLine(0, y + PLATFORM_HEIGHT, cw, y + PLATFORM_HEIGHT)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)

        cw = self.canvas_width
        ch = self.canvas_height

        # Draw grid overlay if enabled
        if self.grid_mode != "none":
            grid_pen = QPen(QColor(255, 255, 255, 35), 0.5, Qt.PenStyle.DotLine)
            painter.setPen(grid_pen)

            step_x, step_y = 8, 8
            if self.grid_mode == "4x8":
                step_x, step_y = 4, 8
            elif self.grid_mode == "8x8":
                step_x, step_y = 8, 8
            elif self.grid_mode == "16x16":
                step_x, step_y = 16, 16

            # Vertical grid lines
            for x in range(step_x, cw, step_x):
                painter.drawLine(x, 0, x, ch)

            # Horizontal grid lines
            for y in range(step_y, ch, step_y):
                painter.drawLine(0, y, cw, y)

        # Draw crisp screen boundary outline
        border_pen = QPen(QColor(90, 160, 240, 220), 1, Qt.PenStyle.SolidLine)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, cw, ch)


class SceneView(QGraphicsView):
    """Custom view for pixel-art scene editing with integer zoom levels."""

    element_selected = Signal(str)
    element_moved = Signal(str, tuple, tuple)
    platform_selected = Signal(str)
    platform_moved = Signal(str, tuple, tuple)
    object_selected = Signal(object)
    object_moved = Signal(object, tuple, tuple)
    player_spawn_selected = Signal(bool)
    player_spawn_moved = Signal(tuple, tuple)
    delete_requested = Signal()
    flip_requested = Signal()
    cursor_position_changed = Signal(int, int)

    ZOOM_LEVELS = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.canvas = SceneCanvas(self)
        self.setScene(self.canvas)

        # Disable smoothing for nearest-neighbor pixel art
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(QColor(32, 34, 40)))

        self.zoom_index = 6  # Default: 8.0x
        self._apply_zoom()

        self._items_by_id: dict[str, SceneGraphicsItem] = {}
        self._platform_items_by_id: dict[str, PlatformGraphicsItem] = {}
        self._object_items_by_id: dict[str, SceneObjectGraphicsItem] = {}
        self._player_spawn_item: Optional[PlayerSpawnGraphicsItem] = None
        self._is_updating_selection: bool = False

    def _apply_zoom(self) -> None:
        factor = self.ZOOM_LEVELS[self.zoom_index]
        self.resetTransform()
        self.scale(factor, factor)

    def zoom_in(self) -> None:
        if self.zoom_index < len(self.ZOOM_LEVELS) - 1:
            self.zoom_index += 1
            self._apply_zoom()

    def zoom_out(self) -> None:
        if self.zoom_index > 0:
            self.zoom_index -= 1
            self._apply_zoom()

    def set_zoom_factor(self, factor: float) -> None:
        best_idx = 0
        min_diff = float("inf")
        for idx, z in enumerate(self.ZOOM_LEVELS):
            if abs(z - factor) < min_diff:
                min_diff = abs(z - factor)
                best_idx = idx
        self.zoom_index = best_idx
        self._apply_zoom()

    def fit_scene_in_view(self) -> None:
        """Fit the whole scene canvas inside the viewport at the closest integer zoom level.

        The canvas is fitted (not the viewport), so a 160 x 96 ANTIC D scene fills a landscape
        viewport while a taller scene still shows every row. Snapping the scale to ZOOM_LEVELS
        keeps the pixel art crisp - `fitInView` alone would leave a fractional scale (e.g. 4.37x).
        """
        rect = self.canvas.sceneRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        viewport = self.viewport().size()
        margin = 8  # leave the screen boundary outline visible
        scale = min(
            (viewport.width() - margin) / rect.width(),
            (viewport.height() - margin) / rect.height(),
        )
        if scale <= 0:
            return

        factor = next((z for z in reversed(self.ZOOM_LEVELS) if z <= scale), self.ZOOM_LEVELS[0])
        self.set_zoom_factor(factor)
        self.centerOn(rect.center())

    def update_canvas_size(self, width: int, height: int) -> None:
        """Update the logical boundaries of the scene canvas."""
        self.canvas.set_canvas_size(width, height)

    def populate_scene(
        self,
        scene_model: Scene,
        asset_manager: AssetManager,
        selected_element_id: Optional[str] = None,
        selected_platform_id: Optional[str] = None,
        selected_object_id: Optional[str] = None,
        catalogues: Optional[ProjectCatalogues] = None,
    ) -> None:
        """Clear and repopulate canvas from scene model."""
        self.canvas.set_canvas_size(scene_model.width, scene_model.height)
        self.canvas.clear()
        self._items_by_id.clear()
        self._platform_items_by_id.clear()
        self._object_items_by_id.clear()
        self._player_spawn_item = None

        # Add regular tile elements
        for elem in scene_model.elements:
            item = SceneGraphicsItem(
                element=elem,
                asset_manager=asset_manager,
                on_move_committed=self._on_item_moved,
                on_selection_changed=self._on_item_selected,
            )
            self.canvas.addItem(item)
            self._items_by_id[elem.id] = item

            if selected_element_id == elem.id:
                item.setSelected(True)

        # Add hardware platforms
        for plat in scene_model.platforms:
            prof = (
                catalogues.get_platform_profile(plat.color_profile_id)
                if (catalogues and plat.color_profile_id)
                else None
            )
            p_item = PlatformGraphicsItem(
                platform=plat,
                on_move_committed=self._on_platform_moved,
                on_selection_changed=self._on_platform_selected,
                color_profile=prof,
            )
            self.canvas.addItem(p_item)
            self._platform_items_by_id[plat.id] = p_item

            if selected_platform_id == plat.id:
                p_item.setSelected(True)

        # Add scene objects (Enemies & Secrets)
        for obj in scene_model.objects:
            o_item = SceneObjectGraphicsItem(
                scene_object=obj,
                scene_model=scene_model,
                asset_manager=asset_manager,
                catalogues=catalogues,
                on_move_committed=self._on_object_moved,
                on_selection_changed=self._on_object_selected,
            )
            self.canvas.addItem(o_item)
            self._object_items_by_id[obj.id] = o_item

            if selected_object_id is not None and (selected_object_id == obj.id or str(selected_object_id) == str(obj.id)):
                o_item.setSelected(True)

        # Add Player Spawn if present
        if scene_model.player_spawn is not None:
            self._player_spawn_item = PlayerSpawnGraphicsItem(
                player_spawn=scene_model.player_spawn,
                scene_model=scene_model,
                on_move_committed=self._on_player_spawn_moved,
                on_selection_changed=self._on_player_spawn_selected,
            )
            self.canvas.addItem(self._player_spawn_item)

    def update_element_item(self, element: SceneElement) -> None:
        """Update graphics item for an existing element."""
        if element.id in self._items_by_id:
            self._items_by_id[element.id].update_from_element(element)

    def update_platform_item(
        self,
        platform: PlatformElement,
        catalogues: Optional[ProjectCatalogues] = None,
    ) -> None:
        """Update graphics item for an existing platform."""
        if platform.id in self._platform_items_by_id:
            prof = (
                catalogues.get_platform_profile(platform.color_profile_id)
                if (catalogues and platform.color_profile_id)
                else None
            )
            self._platform_items_by_id[platform.id].update_from_platform(platform, color_profile=prof)

    def update_object_item(
        self,
        scene_object: SceneObjectElement,
        catalogues: Optional[ProjectCatalogues] = None,
    ) -> None:
        """Update graphics item for an existing scene object."""
        for o_id, item in self._object_items_by_id.items():
            if o_id == scene_object.id or str(o_id) == str(scene_object.id):
                item.update_from_object(scene_object, catalogues)
                break

    def select_element(self, element_id: Optional[str]) -> None:
        """Programmatically select a tile element."""
        if self._is_updating_selection:
            return
        self._is_updating_selection = True
        try:
            self.canvas.blockSignals(True)
            for e_id, item in self._items_by_id.items():
                item.setSelected(e_id == element_id)
            if element_id:
                for p_item in self._platform_items_by_id.values():
                    p_item.setSelected(False)
                for o_item in self._object_items_by_id.values():
                    o_item.setSelected(False)
                if self._player_spawn_item is not None:
                    self._player_spawn_item.setSelected(False)
            self.canvas.blockSignals(False)
        finally:
            self._is_updating_selection = False

    def select_platform(self, platform_id: Optional[str]) -> None:
        """Programmatically select a hardware platform."""
        if self._is_updating_selection:
            return
        self._is_updating_selection = True
        try:
            self.canvas.blockSignals(True)
            for p_id, p_item in self._platform_items_by_id.items():
                p_item.setSelected(p_id == platform_id)
            if platform_id:
                for item in self._items_by_id.values():
                    item.setSelected(False)
                for o_item in self._object_items_by_id.values():
                    o_item.setSelected(False)
                if self._player_spawn_item is not None:
                    self._player_spawn_item.setSelected(False)
            self.canvas.blockSignals(False)
        finally:
            self._is_updating_selection = False

    def select_object(self, object_id: Optional[Any]) -> None:
        """Programmatically select a scene object."""
        if self._is_updating_selection:
            return
        self._is_updating_selection = True
        try:
            self.canvas.blockSignals(True)
            for o_id, o_item in self._object_items_by_id.items():
                is_match = (object_id is not None) and (o_id == object_id or str(o_id) == str(object_id))
                o_item.setSelected(is_match)
            if object_id is not None:
                for item in self._items_by_id.values():
                    item.setSelected(False)
                for p_item in self._platform_items_by_id.values():
                    p_item.setSelected(False)
                if self._player_spawn_item is not None:
                    self._player_spawn_item.setSelected(False)
            self.canvas.blockSignals(False)
        finally:
            self._is_updating_selection = False

    def get_selected_element_id(self) -> Optional[str]:
        for e_id, item in self._items_by_id.items():
            if item.isSelected():
                return e_id
        return None

    def get_selected_platform_id(self) -> Optional[str]:
        for p_id, item in self._platform_items_by_id.items():
            if item.isSelected():
                return p_id
        return None

    def get_selected_object_id(self) -> Optional[Any]:
        for o_id, item in self._object_items_by_id.items():
            if item.isSelected():
                return item.scene_object.id
        return None

    def _on_item_moved(self, element_id: str, old_pos: tuple, new_pos: tuple) -> None:
        self.element_moved.emit(element_id, old_pos, new_pos)

    def _on_item_selected(self, element_id: str, is_selected: bool) -> None:
        if self._is_updating_selection:
            return
        if is_selected:
            self._is_updating_selection = True
            try:
                for p_item in self._platform_items_by_id.values():
                    p_item.setSelected(False)
                for o_item in self._object_items_by_id.values():
                    o_item.setSelected(False)
            finally:
                self._is_updating_selection = False
            self.element_selected.emit(element_id)

    def _on_platform_moved(self, platform_id: str, old_pos: tuple, new_pos: tuple) -> None:
        self.platform_moved.emit(platform_id, old_pos, new_pos)

    def select_player_spawn(self, selected: bool = True) -> None:
        """Programmatically select or deselect the player spawn."""
        if self._is_updating_selection:
            return
        self._is_updating_selection = True
        try:
            self.canvas.blockSignals(True)
            if self._player_spawn_item is not None:
                self._player_spawn_item.setSelected(selected)
            if selected:
                for item in self._items_by_id.values():
                    item.setSelected(False)
                for p_item in self._platform_items_by_id.values():
                    p_item.setSelected(False)
                for o_item in self._object_items_by_id.values():
                    o_item.setSelected(False)
            self.canvas.blockSignals(False)
        finally:
            self._is_updating_selection = False

    def is_player_spawn_selected(self) -> bool:
        """Return True if the player spawn item is currently selected."""
        return self._player_spawn_item is not None and self._player_spawn_item.isSelected()

    @property
    def player_spawn_item(self) -> Optional[PlayerSpawnGraphicsItem]:
        """Return the current PlayerSpawnGraphicsItem on canvas, if any."""
        return self._player_spawn_item

    def update_player_spawn_item(
        self,
        player_spawn: Optional[PlayerSpawn] = ...,
        scene_model: Optional[Scene] = None,
    ) -> None:
        """Update or create/remove the player spawn graphics item on the canvas."""
        if scene_model is None and hasattr(self.parent(), "scene_model"):
            scene_model = getattr(self.parent(), "scene_model", None)

        if player_spawn is ...:
            player_spawn = scene_model.player_spawn if scene_model else None

        if player_spawn is None:
            if self._player_spawn_item is not None:
                self.canvas.removeItem(self._player_spawn_item)
                self._player_spawn_item = None
        else:
            if self._player_spawn_item is None:
                model = scene_model or getattr(self.parent(), "scene_model", None)
                self._player_spawn_item = PlayerSpawnGraphicsItem(
                    player_spawn=player_spawn,
                    scene_model=model,
                    on_move_committed=self._on_player_spawn_moved,
                    on_selection_changed=self._on_player_spawn_selected,
                )
                self.canvas.addItem(self._player_spawn_item)
            else:
                self._player_spawn_item.update_from_spawn(player_spawn)

    def _on_player_spawn_moved(self, old_pos: tuple, new_pos: tuple) -> None:
        self.player_spawn_moved.emit(old_pos, new_pos)

    def _on_player_spawn_selected(self, is_selected: bool) -> None:
        if self._is_updating_selection:
            return
        if is_selected:
            self._is_updating_selection = True
            try:
                for item in self._items_by_id.values():
                    item.setSelected(False)
                for p_item in self._platform_items_by_id.values():
                    p_item.setSelected(False)
                for o_item in self._object_items_by_id.values():
                    o_item.setSelected(False)
            finally:
                self._is_updating_selection = False
        self.player_spawn_selected.emit(is_selected)

    def _on_platform_selected(self, platform_id: str, is_selected: bool) -> None:
        if self._is_updating_selection:
            return
        if is_selected:
            self._is_updating_selection = True
            try:
                for item in self._items_by_id.values():
                    item.setSelected(False)
                for o_item in self._object_items_by_id.values():
                    o_item.setSelected(False)
            finally:
                self._is_updating_selection = False
            self.platform_selected.emit(platform_id)

    def _on_object_moved(self, object_id: Any, old_pos: tuple, new_pos: tuple) -> None:
        self.object_moved.emit(object_id, old_pos, new_pos)

    def _on_object_selected(self, object_id: Any, is_selected: bool) -> None:
        if self._is_updating_selection:
            return
        if is_selected:
            self._is_updating_selection = True
            try:
                for item in self._items_by_id.values():
                    item.setSelected(False)
                for p_item in self._platform_items_by_id.values():
                    p_item.setSelected(False)
                for o_id, o_item in self._object_items_by_id.items():
                    if not (o_id == object_id or str(o_id) == str(object_id)):
                        o_item.setSelected(False)
            finally:
                self._is_updating_selection = False
            self.object_selected.emit(object_id)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        scene_pt = self.mapToScene(event.pos())
        self.cursor_position_changed.emit(int(scene_pt.x()), int(scene_pt.y()))

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Ctrl + Wheel zooms in/out."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        selected_obj_id = self.get_selected_object_id()
        if selected_obj_id:
            obj_item = self._object_items_by_id.get(selected_obj_id)
            if obj_item:
                step_x = 4 if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1
                dx = 0
                if event.key() == Qt.Key.Key_Left:
                    dx = -step_x
                elif event.key() == Qt.Key.Key_Right:
                    dx = step_x
                elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                    self.delete_requested.emit()
                    event.accept()
                    return
                else:
                    super().keyPressEvent(event)
                    return

                if dx != 0:
                    old_x = obj_item.scene_object.x
                    plat_id = obj_item.scene_object.platform_id
                    new_x = old_x + dx
                    self.object_moved.emit(selected_obj_id, (old_x, plat_id), (new_x, plat_id))
                    event.accept()
                    return
        selected_plat_id = self.get_selected_platform_id()
        if selected_plat_id:
            plat_item = self._platform_items_by_id.get(selected_plat_id)
            if plat_item:
                step_x = 4 if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1
                dx, dy = 0, 0
                if event.key() == Qt.Key.Key_Left:
                    dx = -step_x
                elif event.key() == Qt.Key.Key_Right:
                    dx = step_x
                elif event.key() == Qt.Key.Key_Up:
                    dy = -16  # snap up one platform row
                elif event.key() == Qt.Key.Key_Down:
                    dy = 16   # snap down one platform row
                elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                    self.delete_requested.emit()
                    event.accept()
                    return
                else:
                    super().keyPressEvent(event)
                    return

                if dx != 0 or dy != 0:
                    old_x = int(round(plat_item.pos().x()))
                    old_y = int(round(plat_item.pos().y()))
                    new_x = old_x + dx
                    new_y = old_y + dy
                    if dy != 0:
                        scene_h = self.canvas_height
                        allowed = [y for y in range(8, scene_h - PLATFORM_HEIGHT + 1, 16)]
                        if new_y not in allowed:
                            event.accept()
                            return
                    self.platform_moved.emit(selected_plat_id, (old_x, old_y), (new_x, new_y))
                    event.accept()
                    return

        selected_id = self.get_selected_element_id()
        if not selected_id:
            super().keyPressEvent(event)
            return

        item = self._items_by_id.get(selected_id)
        if not item:
            super().keyPressEvent(event)
            return

        step = 4 if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1
        dx, dy = 0, 0

        if event.key() == Qt.Key.Key_Left:
            dx = -step
        elif event.key() == Qt.Key.Key_Right:
            dx = step
        elif event.key() == Qt.Key.Key_Up:
            dy = -step
        elif event.key() == Qt.Key.Key_Down:
            dy = step
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_requested.emit()
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_F, Qt.Key.Key_H):
            self.flip_requested.emit()
            event.accept()
            return
        else:
            super().keyPressEvent(event)
            return

        if dx != 0 or dy != 0:
            old_x = int(round(item.pos().x()))
            old_y = int(round(item.pos().y()))
            new_x = old_x + dx
            new_y = old_y + dy
            item.setPos(QPointF(new_x, new_y))
            self.element_moved.emit(selected_id, (old_x, old_y), (new_x, new_y))
            event.accept()
