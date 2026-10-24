"""Custom QGraphicsItem representing an element placed on the Atari 8-bit scene."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from .asset_manager import AssetManager
from .atari_palette import atari_color_to_rgb
from .catalogue_model import PlatformColorProfile, ProjectCatalogues
from .scene_model import (
    ANTIC_D_PLAYFIELD_HEIGHT,
    ANTIC_D_PLAYFIELD_WIDTH,
    OBJECT_TYPE_ENEMY,
    OBJECT_TYPE_SECRET,
    OBJECT_TYPE_TREASURE,
    PLATFORM_TYPE_SPRITE,
    PlatformElement,
    PlayerSpawn,
    PLAYER_HEIGHT,
    PLAYER_WIDTH,
    Scene,
    SceneElement,
    SceneObjectElement,
)


class SceneGraphicsItem(QGraphicsItem):
    """QGraphicsItem for displaying and interacting with a scene element."""

    def __init__(
        self,
        element: SceneElement,
        asset_manager: AssetManager,
        on_move_committed: Optional[Callable[[str, tuple[int, int], tuple[int, int]], None]] = None,
        on_selection_changed: Optional[Callable[[str, bool], None]] = None,
    ) -> None:
        super().__init__()
        self.element = element
        self.asset_manager = asset_manager
        self.on_move_committed = on_move_committed
        self.on_selection_changed = on_selection_changed

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        self._drag_start_pos: Optional[tuple[int, int]] = None
        self._cached_pixmap: Optional[QPixmap] = None
        self._missing_source: bool = False

        self.update_from_element(element)

    @property
    def element_id(self) -> str:
        return self.element.id

    def update_from_element(self, element: SceneElement) -> None:
        """Update graphics item representation from model element."""
        self.element = element
        self.setPos(QPointF(element.position.x, element.position.y))
        self.setZValue(element.z_index)

        self._cached_pixmap = self.asset_manager.get_cropped_pixmap(
            element.source,
            element.source_rect,
            flip_x=element.flip_x,
        )
        self._missing_source = self._cached_pixmap is None

        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        w = max(1, self.element.width)
        h = max(1, self.element.height)
        # Margin of 2px for selection border and handle drawing
        return QRectF(-2, -2, w + 4, h + 4)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        w = self.element.width
        h = self.element.height

        # Render pixmap or missing fallback
        if self._cached_pixmap is not None:
            painter.drawPixmap(0, 0, self._cached_pixmap)
        else:
            # Fallback for missing graphics
            painter.setPen(QPen(QColor(220, 50, 50), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(80, 20, 20, 160)))
            painter.drawRect(0, 0, w, h)

            # Warning text
            painter.setPen(QColor(255, 200, 200))
            font = QFont("Courier", 8)
            font.setPixelSize(8)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "MISSING")

        # Check if partially or completely out of scene bounds
        item_scene_x = int(round(self.pos().x()))
        item_scene_y = int(round(self.pos().y()))
        scene_obj = self.scene()
        if scene_obj:
            scene_w = int(round(scene_obj.sceneRect().width()))
            scene_h = int(round(scene_obj.sceneRect().height()))
        else:
            scene_w = ANTIC_D_PLAYFIELD_WIDTH
            scene_h = ANTIC_D_PLAYFIELD_HEIGHT

        out_of_bounds = (
            item_scene_x < 0
            or item_scene_y < 0
            or (item_scene_x + w) > scene_w
            or (item_scene_y + h) > scene_h
        )

        if out_of_bounds and not self.isSelected():
            # Subtle amber outline indicating element exceeds canvas bounds
            warn_pen = QPen(QColor(255, 165, 0, 180), 1, Qt.PenStyle.DotLine)
            painter.setPen(warn_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(0, 0, w, h)

        # Highlight if selected (clean non-destructive overlay)
        if self.isSelected():
            # Primary selection border
            sel_pen = QPen(QColor(0, 220, 255), 1.0, Qt.PenStyle.SolidLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(-0.5, -0.5, w + 1, h + 1)

            # Small corner handles (2x2)
            corner_pen = QPen(QColor(255, 255, 255), 1)
            corner_brush = QBrush(QColor(0, 160, 255))
            painter.setPen(corner_pen)
            painter.setBrush(corner_brush)

            handle_size = 2.0
            for pt in (
                (-1, -1),
                (w - handle_size + 1, -1),
                (-1, h - handle_size + 1),
                (w - handle_size + 1, h - handle_size + 1),
            ):
                painter.drawRect(QRectF(pt[0], pt[1], handle_size, handle_size))

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = (
                int(round(self.pos().x())),
                int(round(self.pos().y())),
            )
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            curr_pos = (
                int(round(self.pos().x())),
                int(round(self.pos().y())),
            )
            # Snap to integer pixel grid
            self.setPos(QPointF(curr_pos[0], curr_pos[1]))
            if curr_pos != self._drag_start_pos and self.on_move_committed:
                self.on_move_committed(self.element.id, self._drag_start_pos, curr_pos)
            self._drag_start_pos = None

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: any) -> any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos: QPointF = value
            # Enforce 1-pixel integer grid snapping while dragging
            rounded_x = round(new_pos.x())
            rounded_y = round(new_pos.y())
            return QPointF(rounded_x, rounded_y)

        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            is_selected = bool(value)
            if self.on_selection_changed:
                self.on_selection_changed(self.element.id, is_selected)

        return super().itemChange(change, value)


class PlatformGraphicsItem(QGraphicsItem):
    """QGraphicsItem for displaying and interacting with an Atari hardware platform (Sprite / Missile)."""

    def __init__(
        self,
        platform: PlatformElement,
        on_move_committed: Optional[Callable[[str, tuple[int, int], tuple[int, int]], None]] = None,
        on_selection_changed: Optional[Callable[[str, bool], None]] = None,
        color_profile: Optional[PlatformColorProfile] = None,
    ) -> None:
        super().__init__()
        self.platform = platform
        self.color_profile = color_profile
        self.on_move_committed = on_move_committed
        self.on_selection_changed = on_selection_changed

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        self._drag_start_pos: Optional[tuple[int, int]] = None
        self.setZValue(1000)  # Render platforms on top of standard background tiles
        self.update_from_platform(platform, color_profile=color_profile)

    @property
    def platform_id(self) -> str:
        return self.platform.id

    def update_from_platform(
        self,
        platform: PlatformElement,
        color_profile: Optional[PlatformColorProfile] = None,
    ) -> None:
        self.platform = platform
        if color_profile is not None:
            self.color_profile = color_profile
        self.setPos(QPointF(platform.position.x, platform.position.y))
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        w = max(1, self.platform.width)
        h = max(1, self.platform.height)
        return QRectF(-2, -2, w + 4, h + 4)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        w = self.platform.width
        h = self.platform.height  # always 4

        is_sprite = self.platform.type == PLATFORM_TYPE_SPRITE

        # Color theme fallback: Cyan/Blue for Sprite, Amber/Orange for Missile
        if is_sprite:
            base_col = QColor(41, 128, 185, 230)       # Atari player cyan-blue
            highlight_col = QColor(85, 239, 196, 255)  # Top edge highlight
            shadow_col = QColor(24, 44, 97, 255)       # Bottom edge shadow
            tick_col = QColor(100, 200, 255, 120)      # 4px bit ticks
            text_col = QColor(255, 255, 255, 230)
            tag = f"S:{w}"
        else:
            base_col = QColor(230, 126, 34, 230)       # Atari missile gold-orange
            highlight_col = QColor(254, 202, 87, 255)  # Top edge highlight
            shadow_col = QColor(186, 74, 0, 255)       # Bottom edge shadow
            tick_col = QColor(255, 220, 120, 140)      # 4px bit ticks
            text_col = QColor(255, 255, 255, 230)
            tag = f"M:{w}"

        # Draw main platform body
        # In ANTIC Mode D, 4 pixel lines correspond to 8 scanlines (2 scanlines per mode line).
        # We render 4 pixel lines using the 8-scanline color profile (row 0..3 -> scanlines 0, 2, 4, 6).
        if self.color_profile and self.color_profile.colors and len(self.color_profile.colors) == 8:
            for row in range(min(h, 4)):
                rgb = atari_color_to_rgb(self.color_profile.colors[row * 2])
                painter.fillRect(QRectF(0, row, w, 1), QColor(*rgb))
        else:
            painter.fillRect(QRectF(0, 0, w, h), base_col)

        # Draw 4px tick marks (hardware ×4 pixel bits)
        painter.setPen(QPen(tick_col, 1))
        for x in range(4, w, 4):
            painter.drawLine(x, 1, x, h - 2)

        # Top 3D highlight & bottom 3D shadow
        painter.setPen(QPen(highlight_col, 1))
        painter.drawLine(0, 0, w - 1, 0)
        painter.setPen(QPen(shadow_col, 1))
        painter.drawLine(0, h - 1, w - 1, h - 1)

        # Side borders
        painter.setPen(QPen(shadow_col, 1))
        painter.drawLine(0, 0, 0, h - 1)
        painter.drawLine(w - 1, 0, w - 1, h - 1)

        # Text label (e.g. S:16 or M:8) if height >= 6 and width >= 12
        if h >= 6 and w >= 12:
            font = QFont("Monospace", 6)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(text_col)
            painter.drawText(QRectF(1, 0, w - 2, h), Qt.AlignmentFlag.AlignCenter, tag)

        # Selection styling
        if self.isSelected():
            sel_pen = QPen(QColor(255, 255, 0), 1.0, Qt.PenStyle.SolidLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(-0.5, -0.5, w + 1, h + 1)

            corner_pen = QPen(QColor(0, 0, 0), 1)
            corner_brush = QBrush(QColor(255, 255, 0))
            painter.setPen(corner_pen)
            painter.setBrush(corner_brush)
            for pt in ((-1, -1), (w - 1, -1), (-1, h - 1), (w - 1, h - 1)):
                painter.drawRect(QRectF(pt[0], pt[1], 2, 2))

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = (
                int(round(self.pos().x())),
                int(round(self.pos().y())),
            )
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            curr_pos = (
                int(round(self.pos().x())),
                int(round(self.pos().y())),
            )
            # Find nearest valid platform y (satisfying y % 16 == 8 and y >= 8)
            raw_y = curr_pos[1]
            snapped_row = round((raw_y - 8) / 16.0)
            snapped_row = max(0, snapped_row)
            snapped_y = 8 + snapped_row * 16

            scene_obj = self.scene()
            if scene_obj:
                scene_h = int(round(scene_obj.sceneRect().height()))
                allowed = [y for y in range(8, scene_h - self.platform.height + 1, 16)]
                if allowed and snapped_y > allowed[-1]:
                    snapped_y = allowed[-1]

            snapped_pos = (curr_pos[0], snapped_y)
            self.setPos(QPointF(snapped_pos[0], snapped_pos[1]))
            if snapped_pos != self._drag_start_pos and self.on_move_committed:
                self.on_move_committed(self.platform.id, self._drag_start_pos, snapped_pos)
            self._drag_start_pos = None

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: any) -> any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos: QPointF = value
            rounded_x = round(new_pos.x())
            rounded_y = round(new_pos.y())
            return QPointF(rounded_x, rounded_y)

        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            is_selected = bool(value)
            if self.on_selection_changed:
                self.on_selection_changed(self.platform.id, is_selected)

        return super().itemChange(change, value)


class SceneObjectGraphicsItem(QGraphicsItem):
    """QGraphicsItem for displaying and interacting with an Enemy or Secret placed on a platform."""

    def __init__(
        self,
        scene_object: SceneObjectElement,
        scene_model: Scene,
        asset_manager: AssetManager,
        catalogues: Optional[ProjectCatalogues] = None,
        on_move_committed: Optional[Callable[[str, tuple[int, str], tuple[int, str]], None]] = None,
        on_selection_changed: Optional[Callable[[str, bool], None]] = None,
    ) -> None:
        super().__init__()
        self.scene_object = scene_object
        self.scene_model = scene_model
        self.asset_manager = asset_manager
        self.catalogues = catalogues
        self.on_move_committed = on_move_committed
        self.on_selection_changed = on_selection_changed

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        self._drag_start_pos: Optional[tuple[int, str]] = None  # (x, platform_id)
        self._missing_platform: bool = False

        self.setZValue(2000)  # Render objects on top of platforms
        self.update_from_object(scene_object, catalogues)

    @property
    def object_id(self) -> str:
        return self.scene_object.id

    def update_from_object(
        self,
        scene_object: SceneObjectElement,
        catalogues: Optional[ProjectCatalogues] = None,
    ) -> None:
        """Update graphics item representation from model object."""
        self.scene_object = scene_object
        if catalogues is not None:
            self.catalogues = catalogues

        if hasattr(self.scene_model, "get_platform"):
            plat = self.scene_model.get_platform(scene_object.platform_id)
        else:
            plat = self.scene_model

        if plat is not None and hasattr(plat, "position"):
            obj_y = plat.position.y - scene_object.height
            self._missing_platform = False
        else:
            obj_y = 0
            self._missing_platform = True

        self.setPos(QPointF(scene_object.x, obj_y))

        # Update tooltip with definition information
        defn = None
        if self.catalogues is not None and self.scene_object.definition_id:
            defn = self.catalogues.get_definition(self.scene_object.type, self.scene_object.definition_id)

        kind_label = "Enemy" if self.scene_object.type == OBJECT_TYPE_ENEMY else "Secret"
        def_name = defn.name if defn else (self.scene_object.definition_id or "No definition")
        tip = f"[{kind_label}] {def_name} ({self.scene_object.id})\nPlatform: {self.scene_object.platform_id} @ x={self.scene_object.x}"
        if self.scene_object.type == OBJECT_TYPE_ENEMY and self.scene_object.speed:
            tip += f"\nSpeed: {self.scene_object.speed}, Strategy: {self.scene_object.movement_strategy}"
        if defn and defn.atari_color is not None:
            tip += f"\nAtari Color: ${defn.atari_color:02X} ({defn.atari_color})"
        if defn and defn.blink:
            tip += "\nBlink: ON"
        eff_sprite_id = self.scene_object.get_effective_sprite_id(self.catalogues)
        if eff_sprite_id is not None:
            spr_desc = ""
            if self.catalogues and hasattr(self.catalogues, "sprites") and eff_sprite_id in self.catalogues.sprites:
                spr = self.catalogues.sprites[eff_sprite_id]
                spr_desc = f" ({getattr(spr, 'description', '')})" if getattr(spr, "description", "") else ""
            tip += f"\nSprite: ID {eff_sprite_id}{spr_desc}"
        if not defn and self.scene_object.definition_id:
            tip += f"\n[WARNING: Definition '{self.scene_object.definition_id}' not found in catalogue!]"
        self.setToolTip(tip)

        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        w = max(1, self.scene_object.width)
        h = max(1, self.scene_object.height)
        return QRectF(-2, -2, w + 4, h + 8)

    def resolve_color(self) -> QColor:
        """Resolve the display color for the square, using definition rgb_color or fallback."""
        defn = None
        if self.catalogues is not None and self.scene_object.definition_id:
            defn = self.catalogues.get_definition(self.scene_object.type, self.scene_object.definition_id)
        if defn and defn.rgb_color is not None:
            return QColor(defn.rgb_color[0], defn.rgb_color[1], defn.rgb_color[2])
        is_enemy = self.scene_object.type == OBJECT_TYPE_ENEMY
        return QColor(211, 47, 47) if is_enemy else QColor(255, 160, 0)

    _resolve_color = resolve_color

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        w = max(1, self.scene_object.width)
        h = max(1, self.scene_object.height)

        fill_col = self.resolve_color()
        is_enemy = (self.scene_object.type == OBJECT_TYPE_ENEMY)
        defn = None
        if self.catalogues is not None and self.scene_object.definition_id:
            defn = self.catalogues.get_definition(self.scene_object.type, self.scene_object.definition_id)

        # Draw square body
        painter.setBrush(QBrush(fill_col))
        border_col = QColor(20, 20, 20, 220)
        painter.setPen(QPen(border_col, 1, Qt.PenStyle.SolidLine))
        painter.drawRect(0, 0, w, h)

        # Draw type glyph inside square ("E" or "S")
        lum = 0.299 * fill_col.red() + 0.587 * fill_col.green() + 0.114 * fill_col.blue()
        text_col = QColor(255, 255, 255) if lum < 140 else QColor(0, 0, 0)
        painter.setPen(QPen(text_col, 1))
        f = QFont("Arial", 6)
        f.setBold(True)
        f.setPointSize(max(4, min(7, h - 2)))
        painter.setFont(f)
        glyph = "E" if is_enemy else "S"
        painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, glyph)

        # Missing definition indicator
        if defn is None and self.scene_object.definition_id:
            painter.setPen(QPen(QColor(255, 40, 40), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(-1, -1, w + 2, h + 2))

        # Visual indication of missing platform
        if self._missing_platform:
            painter.setPen(QPen(QColor(255, 60, 60), 1, Qt.PenStyle.DashDotLine))
            painter.setBrush(QBrush(QColor(255, 0, 0, 50)))
            painter.drawRect(0, 0, w, h)
            # Warning badge
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(231, 76, 60, 220)))
            painter.drawRect(QRectF(w - 7, 0, 7, 7))
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            wf = QFont("Arial", 5)
            wf.setPointSize(5)
            painter.setFont(wf)
            painter.drawText(QRectF(w - 7, 0, 7, 7), Qt.AlignmentFlag.AlignCenter, "!")

        # Selection styling
        if self.isSelected():
            theme_col = QColor(231, 76, 60) if is_enemy else QColor(241, 196, 15)
            # Outer crisp border
            pen = QPen(theme_col, 1.0, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(-1, -1, w + 2, h + 2))

            # Corner handles
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(theme_col))
            for pt in [(-2, -2), (w, -2), (-2, h), (w, h)]:
                painter.drawRect(QRectF(pt[0], pt[1], 2, 2))

            # Visual guide line indicating assigned platform connection
            if not self._missing_platform:
                painter.setPen(QPen(theme_col, 1, Qt.PenStyle.DotLine))
                painter.drawLine(0, h, 0, h + 4)
                painter.drawLine(w, h, w, h + 4)
                painter.drawLine(0, h + 4, w, h + 4)

            # Strategy / Speed label badge on select for enemy
            if is_enemy and self.scene_object.movement_strategy:
                strat_symbols = {
                    "stationary": "■",
                    "left_right": "⇄",
                    "right_left": "⇆",
                    "left_pause_right": "⇥",
                    "right_pause_left": "⇤",
                }
                sym = strat_symbols.get(self.scene_object.movement_strategy, "E")
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(30, 30, 30, 220)))
                painter.drawRoundedRect(QRectF(0, -7, 10, 6), 1, 1)
                painter.setPen(QPen(theme_col, 1))
                bf = QFont("Arial", 5)
                bf.setPointSize(5)
                painter.setFont(bf)
                painter.drawText(QRectF(0, -7, 10, 6), Qt.AlignmentFlag.AlignCenter, sym)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = (
                self.scene_object.x,
                self.scene_object.platform_id,
            )
            if not self.isSelected():
                self.setSelected(True)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            curr_x = int(round(self.pos().x()))
            plat = self.scene_model.get_platform(self.scene_object.platform_id)
            if plat:
                min_x = plat.position.x
                max_x = plat.position.x + plat.width - self.scene_object.width
                if max_x < min_x:
                    min_x = max(0, plat.position.x - self.scene_object.width + 1)
                    max_x = min(self.scene_model.width - self.scene_object.width, plat.position.x + plat.width - 1)
                curr_x = max(min_x, min(curr_x, max_x))
                obj_y = plat.position.y - self.scene_object.height
            else:
                obj_y = int(round(self.pos().y()))

            self.setPos(QPointF(curr_x, obj_y))
            if curr_x != self._drag_start_pos[0] and self.on_move_committed:
                self.on_move_committed(
                    self.scene_object.id,
                    self._drag_start_pos,
                    (curr_x, self.scene_object.platform_id),
                )
            self._drag_start_pos = None

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: any) -> any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos: QPointF = value
            rounded_x = round(new_pos.x())
            plat = self.scene_model.get_platform(self.scene_object.platform_id)
            if plat:
                fixed_y = plat.position.y - self.scene_object.height
            else:
                fixed_y = round(new_pos.y())
            return QPointF(rounded_x, fixed_y)

        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            is_selected = bool(value)
            if self.on_selection_changed:
                self.on_selection_changed(self.scene_object.id, is_selected)

        return super().itemChange(change, value)


class PlayerSpawnGraphicsItem(QGraphicsItem):
    """QGraphicsItem for displaying and positioning the player character's initial spawn on the scene."""

    def __init__(
        self,
        player_spawn: PlayerSpawn,
        scene_model: Scene,
        on_move_committed: Optional[Callable[[tuple[int, int], tuple[int, int]], None]] = None,
        on_selection_changed: Optional[Callable[[bool], None]] = None,
    ) -> None:
        super().__init__()
        self.player_spawn = player_spawn
        self.scene_model = scene_model
        self.on_move_committed = on_move_committed
        self.on_selection_changed = on_selection_changed

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        self._drag_start_pos: Optional[tuple[int, int]] = None

        self.setZValue(3000)  # Render Hero spawn on top of platforms and objects
        self.update_from_spawn(player_spawn)

    def update_from_spawn(self, player_spawn: PlayerSpawn) -> None:
        """Update graphics item position and tooltips from model spawn."""
        self.player_spawn = player_spawn
        self.setPos(QPointF(player_spawn.x, player_spawn.y))

        color_val = getattr(player_spawn, "color", 0x98)
        tip = (
            f"[Player Start]\n"
            f"Coordinates: X={player_spawn.x}, Y={player_spawn.y}\n"
            f"Hero Color: ${color_val:02X} ({color_val})\n"
            f"Hardware: Atari Player 0 (Hero, 8×20 px)"
        )
        self.setToolTip(tip)
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, PLAYER_WIDTH + 4, PLAYER_HEIGHT + 4)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        w = PLAYER_WIDTH
        h = PLAYER_HEIGHT

        # Resolve dynamic hero color from scene model
        color_val = getattr(self.player_spawn, "color", 0x98) if self.player_spawn else 0x98
        r, g, b = atari_color_to_rgb(color_val)
        hero_color = QColor(r, g, b)
        helmet_color = hero_color.lighter(120) if hero_color.lightness() < 200 else hero_color.darker(120)

        # 1. Base shadow / silhouette
        painter.fillRect(QRectF(1, 1, w - 2, h - 2), QColor(20, 24, 30, 220))

        # 2. Hero Head (helmet/hair: tinted with hero color, face skin: #f5cd79)
        painter.fillRect(QRectF(2, 1, 4, 3), helmet_color)             # Helmet
        painter.fillRect(QRectF(2, 4, 4, 3), QColor(245, 205, 121))   # Face
        painter.fillRect(QRectF(4, 5, 1, 1), QColor(30, 30, 30))      # Eye

        # 3. Hero Torso (armor/tunic: Player 0 active Atari color)
        painter.fillRect(QRectF(1, 7, 6, 7), hero_color)

        # 4. Belt / Accent (gold #fed330)
        painter.fillRect(QRectF(1, 14, 6, 1), QColor(254, 211, 48))

        # 5. Boots / Legs (dark navy #2c3e50)
        painter.fillRect(QRectF(1, 15, 2, 5), QColor(44, 62, 80))
        painter.fillRect(QRectF(5, 15, 2, 5), QColor(44, 62, 80))


        # 6. Outline border
        painter.setPen(QPen(QColor(0, 0, 0, 200), 1))
        painter.drawRect(0, 0, w, h)

        # 7. "P" badge indicator centered on chest
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        f = QFont("Arial", 5)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(1, 7, 6, 7), Qt.AlignmentFlag.AlignCenter, "P")

        # 8. Selection styling
        if self.isSelected():
            # Vibrant cyan-gold selection border
            sel_pen = QPen(QColor(0, 230, 255), 1.0, Qt.PenStyle.SolidLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(-1, -1, w + 2, h + 2))

            # Corner handles
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 220, 0)))
            for pt in [(-2, -2), (w, -2), (-2, h), (w, h)]:
                painter.drawRect(QRectF(pt[0], pt[1], 2, 2))

            # Ground baseline indicator
            painter.setPen(QPen(QColor(0, 230, 255, 180), 1, Qt.PenStyle.DashLine))
            painter.drawLine(-4, h, w + 4, h)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = (
                int(round(self.pos().x())),
                int(round(self.pos().y())),
            )
            if not self.isSelected():
                self.setSelected(True)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            curr_x = int(round(self.pos().x()))
            curr_y = int(round(self.pos().y()))

            # Clamp coordinates within scene boundary
            max_x = max(0, self.scene_model.width - PLAYER_WIDTH)
            max_y = max(0, self.scene_model.height - PLAYER_HEIGHT)
            clamped_x = max(0, min(curr_x, max_x))
            clamped_y = max(0, min(curr_y, max_y))

            self.setPos(QPointF(clamped_x, clamped_y))
            if (clamped_x, clamped_y) != self._drag_start_pos and self.on_move_committed:
                self.on_move_committed(self._drag_start_pos, (clamped_x, clamped_y))
            self._drag_start_pos = None

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: any) -> any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos: QPointF = value
            max_x = max(0, self.scene_model.width - PLAYER_WIDTH)
            max_y = max(0, self.scene_model.height - PLAYER_HEIGHT)
            clamped_x = max(0, min(round(new_pos.x()), max_x))
            clamped_y = max(0, min(round(new_pos.y()), max_y))
            return QPointF(clamped_x, clamped_y)

        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            is_selected = bool(value)
            if self.on_selection_changed:
                self.on_selection_changed(is_selected)

        return super().itemChange(change, value)

