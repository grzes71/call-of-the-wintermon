"""Main application window uniting tile browser, crop editor, scene canvas, and properties."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QIcon,
    QKeySequence,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .asset_manager import AssetManager
from .catalogue_dialog import CataloguePathsDialog, CataloguesDialog
from .catalogue_model import (
    CorruptedCatalogueFileError,
    DuplicateDefinitionIdError,
    EnemyDefinition,
    PlatformColorProfile,
    ProjectCatalogues,
    SecretDefinition,
)
from .commands import (
    AddElementCommand,
    AddPlatformCommand,
    AddSceneObjectCommand,
    ChangePlatformColorProfileCommand,
    ChangePlatformTypeCommand,
    ChangeSceneObjectIdCommand,
    FlipElementCommand,
    ModifyElementPropertiesCommand,
    MoveElementCommand,
    MovePlatformCommand,
    MoveSceneObjectCommand,
    RemoveElementCommand,
    RemovePlatformCommand,
    RemoveSceneObjectCommand,
    ReorderElementCommand,
    ResizePlatformCommand,
    ResizeSceneCommand,
    UpdateSceneObjectPropsCommand,
)
from .crop_editor import CropEditorWidget
from .json_serializer import (
    CorruptedFileError,
    MissingSourceFileError,
    SceneSerializer,
    UnsupportedSchemaVersionError,
    find_project_root,
)
from .scene_model import (
    DEFAULT_SCENE_HEIGHT,
    DEFAULT_SCENE_WIDTH,
    ENEMY_SPEED_FAST,
    ENEMY_SPEED_LABELS,
    ENEMY_SPEED_MEDIUM,
    ENEMY_SPEED_SLOW,
    ENEMY_SPEEDS,
    InvalidObjectPropertyError,
    InvalidPlatformAssignmentError,
    MAX_MISSILES_PER_ROW,
    MAX_OBJECTS_PER_ROW,
    MAX_SCENE_HEIGHT,
    MAX_SCENE_WIDTH,
    MAX_SPRITES_PER_ROW,
    MIN_SCENE_HEIGHT,
    MIN_SCENE_WIDTH,
    MISSILE_WIDTHS,
    ModelValidationError,
    MOVEMENT_STRATEGIES,
    MOVEMENT_STRATEGY_LABELS,
    OBJECT_TYPE_ENEMY,
    OBJECT_TYPE_SECRET,
    OBJECT_TYPE_TREASURE,
    OBJECT_TYPES,
    ObjectLimitExceededError,
    PLATFORM_HEIGHT,
    PLATFORM_TYPE_MISSILE,
    PLATFORM_TYPE_SPRITE,
    PLATFORM_TYPES,
    PlatformCollisionError,
    PlatformElement,
    Position,
    Rect,
    Scene,
    SceneElement,
    SceneObjectElement,
    SingleSourceViolationError,
    SPRITE_WIDTHS,
    STRATEGY_STATIONARY,
    can_add_platform_to_row,
    check_platform_collision,
    get_allowed_platform_rows,
    get_allowed_widths,
    get_required_platform_resources,
    get_row_index,
    get_row_resource_usage,
    platforms_overlap,
)
from .scene_view import SceneView
from .tile_browser import TileBrowserWidget


class NewSceneDialog(QDialog):
    """Dialog for configuring name, width, and height of a new scene."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Atari Scene")
        self.setModal(True)
        self.resize(340, 220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        form = QFormLayout()
        self.name_edit = QLineEdit("untitled")
        form.addRow("Scene Name:", self.name_edit)

        # Preset selector
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Atari Standard (160 × 192)", (160, 192))
        self.preset_combo.addItem("Atari Legacy Screen (160 × 96)", (160, 96))
        self.preset_combo.addItem("Atari Wide / Scroll (320 × 192)", (320, 192))
        self.preset_combo.addItem("Atari Tall / Tower (160 × 384)", (160, 384))
        self.preset_combo.addItem("Atari Full Area (320 × 384)", (320, 384))
        self.preset_combo.addItem("Custom Dimensions...", None)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow("Preset:", self.preset_combo)

        # Width and Height spinboxes
        self.width_spin = QSpinBox()
        self.width_spin.setRange(MIN_SCENE_WIDTH, MAX_SCENE_WIDTH)
        self.width_spin.setValue(DEFAULT_SCENE_WIDTH)
        self.width_spin.setSuffix(" px")

        self.height_spin = QSpinBox()
        self.height_spin.setRange(MIN_SCENE_HEIGHT, MAX_SCENE_HEIGHT)
        self.height_spin.setValue(DEFAULT_SCENE_HEIGHT)
        self.height_spin.setSuffix(" px")

        dim_layout = QHBoxLayout()
        dim_layout.addWidget(self.width_spin)
        dim_layout.addWidget(QLabel("×"))
        dim_layout.addWidget(self.height_spin)
        form.addRow("Resolution:", dim_layout)

        layout.addLayout(form)

        info_lbl = QLabel(
            f"<small style='color: #888;'>Limits: {MIN_SCENE_WIDTH} to {MAX_SCENE_WIDTH} px. Any positive integers.</small>"
        )
        layout.addWidget(info_lbl)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_preset_changed(self, index: int) -> None:
        data = self.preset_combo.currentData()
        if data:
            w, h = data
            self.width_spin.setValue(w)
            self.height_spin.setValue(h)

    def _validate_and_accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Input", "Scene name cannot be empty.")
            return
        w = self.width_spin.value()
        h = self.height_spin.value()
        if w < MIN_SCENE_WIDTH or h < MIN_SCENE_HEIGHT or w > MAX_SCENE_WIDTH or h > MAX_SCENE_HEIGHT:
            QMessageBox.warning(
                self,
                "Invalid Dimensions",
                f"Resolution must be between {MIN_SCENE_WIDTH} and {MAX_SCENE_WIDTH} px.",
            )
            return
        self.accept()

    def get_values(self) -> tuple[str, int, int]:
        return (
            self.name_edit.text().strip() or "untitled",
            self.width_spin.value(),
            self.height_spin.value(),
        )


class MainWindow(QMainWindow):
    """Main application window for Atari 8-bit Scene Editor."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        super().__init__()
        self.base_dir = Path(base_dir).resolve() if base_dir else find_project_root()
        self.asset_manager = AssetManager(self.base_dir)

        # Load project-level catalogues (enemies.json and secrets.json)
        try:
            self.catalogues = ProjectCatalogues.load_from_dir(self.base_dir)
        except CorruptedCatalogueFileError as err:
            QMessageBox.critical(
                self,
                "Corrupted Catalogue",
                f"Corrupted catalogue file detected:\n{err}\n\n"
                "The application will start with an empty catalogue in memory to avoid overwriting files.",
            )
            self.catalogues = ProjectCatalogues()
        except Exception:
            self.catalogues = ProjectCatalogues()

        self.scene_model = Scene(
            name="level_01",
            width=DEFAULT_SCENE_WIDTH,
            height=DEFAULT_SCENE_HEIGHT,
            catalogues=self.catalogues,
        )
        self.current_file_path: Optional[Path] = None
        self._is_dirty: bool = False
        self._next_element_num: int = 1
        self._next_platform_num: int = 1
        self._next_object_num: int = 1
        self._is_selecting_element: bool = False
        self._is_selecting_platform: bool = False
        self._is_selecting_object: bool = False
        self._new_obj_source: Optional[str] = None
        self._new_obj_rect: Optional[Rect] = None

        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)

        self.setWindowTitle("Atari 8-bit Scene Editor")
        self.resize(1280, 800)

        self._build_ui()
        self._build_menus_and_toolbars()
        self._sync_all()

    # -------------------------------------------------------------------------
    # UI Setup
    # -------------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Central widget: Splitter containing Left (Tiles & Crop) and Center (Scene Canvas)
        main_splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left panel: Vertical splitter with TileBrowser and CropEditor
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.tile_browser = TileBrowserWidget(self.asset_manager, self)
        self.crop_editor = CropEditorWidget(self.asset_manager, self)

        left_splitter.addWidget(self.tile_browser)
        left_splitter.addWidget(self.crop_editor)
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 2)
        left_splitter.setMinimumWidth(320)

        main_splitter.addWidget(left_splitter)

        # Center: SceneView
        self.scene_view = SceneView(self)
        main_splitter.addWidget(self.scene_view)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)

        self.setCentralWidget(main_splitter)

        # Right Dock: Properties Panel and Element Layers
        self.right_dock = QDockWidget("Scene & Element Properties", self)
        self.right_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._build_properties_dock()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock)

        # Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.status_cursor_lbl = QLabel("Cursor: (0, 0)")
        self.status_zoom_lbl = QLabel("Zoom: 8x")
        self.status_res_lbl = QLabel(f"Size: {self.scene_model.width}×{self.scene_model.height}")
        self.status_elem_count_lbl = QLabel("Tiles: 0 | Platforms: 0 | Objects: 0")
        self.status_bar.addPermanentWidget(self.status_cursor_lbl)
        self.status_bar.addPermanentWidget(self.status_zoom_lbl)
        self.status_bar.addPermanentWidget(self.status_res_lbl)
        self.status_bar.addPermanentWidget(self.status_elem_count_lbl)

        # Signal connections
        self.tile_browser.image_selected.connect(self._on_tile_image_selected)
        self.crop_editor.add_to_scene_requested.connect(self._on_add_element_requested)
        self.scene_view.element_selected.connect(self._on_element_selected)
        self.scene_view.element_moved.connect(self._on_element_moved_by_view)
        self.scene_view.platform_selected.connect(self._on_platform_selected)
        self.scene_view.platform_moved.connect(self._on_platform_moved_by_view)
        self.scene_view.object_selected.connect(self._on_object_selected)
        self.scene_view.object_moved.connect(self._on_object_moved_by_view)
        self.scene_view.delete_requested.connect(self.delete_selected_element)
        self.scene_view.flip_requested.connect(self.toggle_flip_selected)
        self.scene_view.cursor_position_changed.connect(self._on_cursor_coords_changed)

    def _build_properties_dock(self) -> None:
        self.prop_tabs = QTabWidget()

        # -------------------------------------------------------------
        # Tab 1: Tiles & Elements
        # -------------------------------------------------------------
        tiles_widget = QWidget()
        t_layout = QVBoxLayout(tiles_widget)
        t_layout.setContentsMargins(6, 6, 6, 6)
        t_layout.setSpacing(6)

        # Scene Details Group
        self.scene_group = QGroupBox(f"Scene Settings ({self.scene_model.width} × {self.scene_model.height})")
        s_layout = QFormLayout(self.scene_group)
        self.scene_name_edit = QLineEdit(self.scene_model.name)
        self.scene_name_edit.editingFinished.connect(self._on_scene_name_edited)
        s_layout.addRow("Scene Name:", self.scene_name_edit)

        # Resolution controls
        res_layout = QHBoxLayout()
        self.scene_w_spin = QSpinBox()
        self.scene_w_spin.setRange(MIN_SCENE_WIDTH, MAX_SCENE_WIDTH)
        self.scene_w_spin.setValue(self.scene_model.width)
        self.scene_w_spin.setSuffix(" px")

        self.scene_h_spin = QSpinBox()
        self.scene_h_spin.setRange(MIN_SCENE_HEIGHT, MAX_SCENE_HEIGHT)
        self.scene_h_spin.setValue(self.scene_model.height)
        self.scene_h_spin.setSuffix(" px")

        self.btn_apply_res = QPushButton("Apply")
        self.btn_apply_res.setToolTip("Change scene resolution (elements outside canvas will be preserved)")
        self.btn_apply_res.clicked.connect(self._on_apply_resolution_clicked)

        res_layout.addWidget(self.scene_w_spin)
        res_layout.addWidget(QLabel("×"))
        res_layout.addWidget(self.scene_h_spin)
        res_layout.addWidget(self.btn_apply_res)
        s_layout.addRow("Resolution:", res_layout)

        self.scene_graphic_lbl = QLabel("<i>None (no elements yet)</i>")
        self.scene_graphic_lbl.setWordWrap(True)
        s_layout.addRow("Tileset Graphics:", self.scene_graphic_lbl)
        t_layout.addWidget(self.scene_group)

        # Selected Element Group
        self.elem_group = QGroupBox("Selected Element")
        e_layout = QFormLayout(self.elem_group)

        self.prop_id_lbl = QLabel("-")
        e_layout.addRow("ID:", self.prop_id_lbl)

        self.prop_src_lbl = QLabel("-")
        self.prop_src_lbl.setWordWrap(True)
        e_layout.addRow("Source:", self.prop_src_lbl)

        pos_layout = QHBoxLayout()
        self.prop_pos_x = QSpinBox()
        self.prop_pos_x.setRange(-500, 500)
        self.prop_pos_y = QSpinBox()
        self.prop_pos_y.setRange(-500, 500)
        self.prop_pos_x.valueChanged.connect(self._on_prop_pos_changed)
        self.prop_pos_y.valueChanged.connect(self._on_prop_pos_changed)
        pos_layout.addWidget(QLabel("X:"))
        pos_layout.addWidget(self.prop_pos_x)
        pos_layout.addWidget(QLabel("Y:"))
        pos_layout.addWidget(self.prop_pos_y)
        e_layout.addRow("Position:", pos_layout)

        self.prop_size_lbl = QLabel("-")
        e_layout.addRow("Size (W×H):", self.prop_size_lbl)

        self.prop_crop_lbl = QLabel("-")
        e_layout.addRow("Source Rect:", self.prop_crop_lbl)

        self.prop_flip_check = QCheckBox("Horizontal Flip (flip_x)")
        self.prop_flip_check.toggled.connect(self._on_prop_flip_toggled)
        e_layout.addRow("Orientation:", self.prop_flip_check)

        # Reorder buttons
        order_layout = QHBoxLayout()
        btn_front = QPushButton("To Front")
        btn_front.clicked.connect(self.bring_to_front_selected)
        btn_raise = QPushButton("Raise")
        btn_raise.clicked.connect(self.raise_selected)
        btn_lower = QPushButton("Lower")
        btn_lower.clicked.connect(self.lower_selected)
        btn_back = QPushButton("To Back")
        btn_back.clicked.connect(self.send_to_back_selected)

        order_layout.addWidget(btn_front)
        order_layout.addWidget(btn_raise)
        order_layout.addWidget(btn_lower)
        order_layout.addWidget(btn_back)
        e_layout.addRow("Draw Order:", order_layout)

        btn_delete = QPushButton("Delete Element")
        btn_delete.setStyleSheet("color: #ff5555;")
        btn_delete.clicked.connect(self.delete_selected_element)
        e_layout.addRow("", btn_delete)

        t_layout.addWidget(self.elem_group)

        # Elements / Layers List
        layers_group = QGroupBox("Elements in Draw Order (Bottom to Top)")
        l_layout = QVBoxLayout(layers_group)
        self.layers_list = QListWidget()
        self.layers_list.currentRowChanged.connect(self._on_layer_row_changed)
        l_layout.addWidget(self.layers_list)
        t_layout.addWidget(layers_group, stretch=1)

        self.prop_tabs.addTab(tiles_widget, "Tiles & Elements")

        # -------------------------------------------------------------
        # Tab 2: Hardware Platforms (PMG)
        # -------------------------------------------------------------
        plat_widget = QWidget()
        p_layout = QVBoxLayout(plat_widget)
        p_layout.setContentsMargins(6, 6, 6, 6)
        p_layout.setSpacing(6)

        # Platform Creator Group
        self.plat_creator_group = QGroupBox("New Platform Creator")
        pc_layout = QFormLayout(self.plat_creator_group)

        self.new_plat_type_combo = QComboBox()
        self.new_plat_type_combo.addItem(f"Sprite (max {MAX_SPRITES_PER_ROW}/row)", PLATFORM_TYPE_SPRITE)
        self.new_plat_type_combo.addItem(f"Missile (max {MAX_MISSILES_PER_ROW}/row)", PLATFORM_TYPE_MISSILE)
        self.new_plat_type_combo.currentIndexChanged.connect(self._on_new_plat_type_changed)
        pc_layout.addRow("Resource Type:", self.new_plat_type_combo)

        self.new_plat_width_combo = QComboBox()
        pc_layout.addRow("Width (×4 expanded):", self.new_plat_width_combo)

        self.new_plat_row_combo = QComboBox()
        pc_layout.addRow("Target Row:", self.new_plat_row_combo)

        self.new_plat_color_profile_combo = QComboBox()
        pc_layout.addRow("Color Profile:", self.new_plat_color_profile_combo)

        self.new_plat_x_spin = QSpinBox()
        self.new_plat_x_spin.setRange(-500, 500)
        self.new_plat_x_spin.setValue(20)
        pc_layout.addRow("Horizontal X (px):", self.new_plat_x_spin)

        self.btn_add_plat = QPushButton("+ Add Platform to Scene")
        self.btn_add_plat.clicked.connect(self._on_add_platform_clicked)
        pc_layout.addRow("", self.btn_add_plat)

        p_layout.addWidget(self.plat_creator_group)

        # Selected Platform Properties Group
        self.plat_elem_group = QGroupBox("Selected Platform")
        pe_layout = QFormLayout(self.plat_elem_group)

        self.plat_prop_id_lbl = QLabel("-")
        pe_layout.addRow("ID:", self.plat_prop_id_lbl)

        self.plat_prop_type_combo = QComboBox()
        self.plat_prop_type_combo.addItem("sprite", PLATFORM_TYPE_SPRITE)
        self.plat_prop_type_combo.addItem("missile", PLATFORM_TYPE_MISSILE)
        self.plat_prop_type_combo.currentIndexChanged.connect(self._on_plat_prop_type_changed)
        pe_layout.addRow("Resource Type:", self.plat_prop_type_combo)

        self.plat_prop_width_combo = QComboBox()
        self.plat_prop_width_combo.currentIndexChanged.connect(self._on_plat_prop_width_changed)
        pe_layout.addRow("Width:", self.plat_prop_width_combo)

        self.plat_prop_row_combo = QComboBox()
        self.plat_prop_row_combo.currentIndexChanged.connect(self._on_plat_prop_row_changed)
        pe_layout.addRow("Row (y % 16 == 8):", self.plat_prop_row_combo)

        self.plat_prop_color_profile_combo = QComboBox()
        self.plat_prop_color_profile_combo.currentIndexChanged.connect(self._on_plat_prop_color_profile_changed)
        pe_layout.addRow("Color Profile:", self.plat_prop_color_profile_combo)

        self.plat_prop_x_spin = QSpinBox()
        self.plat_prop_x_spin.setRange(-500, 500)
        self.plat_prop_x_spin.valueChanged.connect(self._on_plat_prop_x_changed)
        pe_layout.addRow("Position X:", self.plat_prop_x_spin)

        self.plat_prop_height_lbl = QLabel("4 lines (Fixed)")
        pe_layout.addRow("Height:", self.plat_prop_height_lbl)

        self.plat_prop_row_status_lbl = QLabel("-")
        self.plat_prop_row_status_lbl.setWordWrap(True)
        pe_layout.addRow("Row Usage:", self.plat_prop_row_status_lbl)

        self.btn_delete_plat = QPushButton("Delete Platform")
        self.btn_delete_plat.setStyleSheet("color: #ff5555;")
        self.btn_delete_plat.clicked.connect(self.delete_selected_element)
        pe_layout.addRow("", self.btn_delete_plat)

        p_layout.addWidget(self.plat_elem_group)

        # Platforms List Group
        self.plat_list_group = QGroupBox("Platforms on Scene")
        pl_layout = QVBoxLayout(self.plat_list_group)
        self.platforms_list = QListWidget()
        self.platforms_list.currentRowChanged.connect(self._on_platform_list_row_changed)
        pl_layout.addWidget(self.platforms_list)
        p_layout.addWidget(self.plat_list_group, stretch=1)

        self.prop_tabs.addTab(plat_widget, "Hardware Platforms")

        # -------------------------------------------------------------
        # Tab 3: Objects (Enemies & Secrets)
        # -------------------------------------------------------------
        obj_widget = QWidget()
        o_layout = QVBoxLayout(obj_widget)
        o_layout.setContentsMargins(6, 6, 6, 6)
        o_layout.setSpacing(6)

        # Object Creator Group
        self.obj_creator_group = QGroupBox("New Object Creator")
        oc_layout = QFormLayout(self.obj_creator_group)

        self.new_obj_type_combo = QComboBox()
        self.new_obj_type_combo.addItem("Enemy", OBJECT_TYPE_ENEMY)
        self.new_obj_type_combo.addItem("Secret", OBJECT_TYPE_SECRET)
        self.new_obj_type_combo.currentIndexChanged.connect(self._on_new_obj_type_changed)
        oc_layout.addRow("Object Type:", self.new_obj_type_combo)

        # Definition selection from catalogue
        self.new_obj_definition_combo = QComboBox()
        self.new_obj_definition_combo.currentIndexChanged.connect(self._on_new_obj_definition_changed)
        oc_layout.addRow("Definition:", self.new_obj_definition_combo)

        self.new_obj_definition_info_lbl = QLabel("")
        self.new_obj_definition_info_lbl.setWordWrap(True)
        oc_layout.addRow("", self.new_obj_definition_info_lbl)

        self.new_obj_platform_combo = QComboBox()
        self.new_obj_platform_combo.currentIndexChanged.connect(self._on_new_obj_platform_combo_changed)
        oc_layout.addRow("Target Platform:", self.new_obj_platform_combo)

        self.new_obj_x_spin = QSpinBox()
        self.new_obj_x_spin.setRange(-500, 500)
        self.new_obj_x_spin.setValue(20)
        oc_layout.addRow("Position X (px):", self.new_obj_x_spin)

        self.new_obj_speed_combo = QComboBox()
        for spd in ENEMY_SPEEDS:
            self.new_obj_speed_combo.addItem(ENEMY_SPEED_LABELS.get(spd, spd), spd)
        self.new_obj_speed_combo.setCurrentIndex(1)  # medium
        self.new_obj_speed_lbl = QLabel("Speed:")
        oc_layout.addRow(self.new_obj_speed_lbl, self.new_obj_speed_combo)

        self.new_obj_strategy_combo = QComboBox()
        for st in MOVEMENT_STRATEGIES:
            self.new_obj_strategy_combo.addItem(MOVEMENT_STRATEGY_LABELS.get(st, st), st)
        self.new_obj_strategy_lbl = QLabel("Strategy:")
        oc_layout.addRow(self.new_obj_strategy_lbl, self.new_obj_strategy_combo)

        self.btn_add_object = QPushButton("+ Add Object to Platform")
        self.btn_add_object.clicked.connect(self._on_add_object_clicked)
        oc_layout.addRow("", self.btn_add_object)

        o_layout.addWidget(self.obj_creator_group)

        # Selected Object Properties Group
        self.obj_elem_group = QGroupBox("Selected Object")
        oe_layout = QFormLayout(self.obj_elem_group)

        self.obj_prop_id_spin = QSpinBox()
        self.obj_prop_id_spin.setRange(1, 255)
        self.obj_prop_id_spin.setToolTip("Unique numeric object ID (1-255)")
        self.obj_prop_id_spin.valueChanged.connect(self._on_obj_prop_id_changed)
        self.obj_prop_id_lbl = self.obj_prop_id_spin
        oe_layout.addRow("ID (1-255):", self.obj_prop_id_spin)

        self.obj_prop_type_combo = QComboBox()
        self.obj_prop_type_combo.addItem("Enemy", OBJECT_TYPE_ENEMY)
        self.obj_prop_type_combo.addItem("Secret", OBJECT_TYPE_SECRET)
        self.obj_prop_type_combo.currentIndexChanged.connect(self._on_obj_prop_type_changed)
        oe_layout.addRow("Type:", self.obj_prop_type_combo)

        self.obj_prop_definition_combo = QComboBox()
        self.obj_prop_definition_combo.currentIndexChanged.connect(self._on_obj_prop_definition_changed)
        oe_layout.addRow("Definition:", self.obj_prop_definition_combo)

        self.obj_prop_definition_info_lbl = QLabel("-")
        self.obj_prop_definition_info_lbl.setWordWrap(True)
        oe_layout.addRow("", self.obj_prop_definition_info_lbl)

        self.obj_prop_platform_combo = QComboBox()
        self.obj_prop_platform_combo.setEnabled(False)
        self.obj_prop_platform_combo.setToolTip("Assigned platform for this object (read-only)")
        oe_layout.addRow("Platform (read-only):", self.obj_prop_platform_combo)

        self.obj_prop_x_spin = QSpinBox()
        self.obj_prop_x_spin.setRange(-500, 500)
        self.obj_prop_x_spin.valueChanged.connect(self._on_obj_prop_x_changed)
        oe_layout.addRow("Position X:", self.obj_prop_x_spin)

        self.obj_prop_speed_combo = QComboBox()
        for spd in ENEMY_SPEEDS:
            self.obj_prop_speed_combo.addItem(ENEMY_SPEED_LABELS.get(spd, spd), spd)
        self.obj_prop_speed_combo.currentIndexChanged.connect(self._on_obj_prop_speed_changed)
        self.obj_prop_speed_lbl = QLabel("Speed:")
        oe_layout.addRow(self.obj_prop_speed_lbl, self.obj_prop_speed_combo)

        self.obj_prop_strategy_combo = QComboBox()
        for st in MOVEMENT_STRATEGIES:
            self.obj_prop_strategy_combo.addItem(MOVEMENT_STRATEGY_LABELS.get(st, st), st)
        self.obj_prop_strategy_combo.currentIndexChanged.connect(self._on_obj_prop_strategy_changed)
        self.obj_prop_strategy_lbl = QLabel("Strategy:")
        oe_layout.addRow(self.obj_prop_strategy_lbl, self.obj_prop_strategy_combo)

        self.btn_delete_obj = QPushButton("Delete Object")
        self.btn_delete_obj.setStyleSheet("color: #ff5555;")
        self.btn_delete_obj.clicked.connect(self.delete_selected_element)
        oe_layout.addRow("", self.btn_delete_obj)

        o_layout.addWidget(self.obj_elem_group)

        # Objects List Group
        self.obj_list_group = QGroupBox("Objects on Scene")
        ol_layout = QVBoxLayout(self.obj_list_group)
        self.objects_list = QListWidget()
        self.objects_list.currentRowChanged.connect(self._on_object_list_row_changed)
        ol_layout.addWidget(self.objects_list)
        o_layout.addWidget(self.obj_list_group, stretch=1)

        self.prop_tabs.addTab(obj_widget, "Objects")
        self.prop_tabs.currentChanged.connect(self._on_prop_tab_changed)

        self.right_dock.setWidget(self.prop_tabs)
        self._refresh_platform_creator_profiles()
        self._on_new_plat_type_changed()
        self._on_new_obj_type_changed()
        self._update_property_panel(None)
        self._update_platform_property_panel(None)
        self._update_object_property_panel(None)

    # -------------------------------------------------------------------------
    # Menus and Toolbars
    # -------------------------------------------------------------------------
    def _build_menus_and_toolbars(self) -> None:
        menubar = self.menuBar()
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # --- File Menu ---
        file_menu = menubar.addMenu("&File")

        act_new = QAction("&New Scene", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self.new_scene)
        file_menu.addAction(act_new)
        toolbar.addAction(act_new)

        act_open = QAction("&Open Scene...", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self.open_scene)
        file_menu.addAction(act_open)
        toolbar.addAction(act_open)

        act_save = QAction("&Save", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self.save_scene)
        file_menu.addAction(act_save)
        toolbar.addAction(act_save)

        act_save_as = QAction("Save &As...", self)
        act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        act_save_as.triggered.connect(self.save_scene_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # --- Edit Menu ---
        edit_menu = menubar.addMenu("&Edit")

        self.act_undo = self.undo_stack.createUndoAction(self, "&Undo")
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(self.act_undo)
        toolbar.addAction(self.act_undo)

        self.act_redo = self.undo_stack.createRedoAction(self, "&Redo")
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(self.act_redo)
        toolbar.addAction(self.act_redo)

        edit_menu.addSeparator()
        toolbar.addSeparator()

        act_del = QAction("&Delete Element", self)
        act_del.setShortcut(QKeySequence.StandardKey.Delete)
        act_del.triggered.connect(self.delete_selected_element)
        edit_menu.addAction(act_del)
        toolbar.addAction(act_del)

        act_flip = QAction("&Flip Horizontally", self)
        act_flip.setShortcut(QKeySequence("F"))
        act_flip.triggered.connect(self.toggle_flip_selected)
        edit_menu.addAction(act_flip)
        toolbar.addAction(act_flip)

        edit_menu.addSeparator()

        act_front = QAction("Bring to &Front", self)
        act_front.setShortcut(QKeySequence("Ctrl+Shift+]"))
        act_front.triggered.connect(self.bring_to_front_selected)
        edit_menu.addAction(act_front)

        act_raise = QAction("&Raise Layer", self)
        act_raise.setShortcut(QKeySequence("Ctrl+]"))
        act_raise.triggered.connect(self.raise_selected)
        edit_menu.addAction(act_raise)

        act_lower = QAction("&Lower Layer", self)
        act_lower.setShortcut(QKeySequence("Ctrl+["))
        act_lower.triggered.connect(self.lower_selected)
        edit_menu.addAction(act_lower)

        act_back = QAction("Send to &Back", self)
        act_back.setShortcut(QKeySequence("Ctrl+Shift+["))
        act_back.triggered.connect(self.send_to_back_selected)
        edit_menu.addAction(act_back)

        edit_menu.addSeparator()

        act_catalogues = QAction("Manage &Catalogues...", self)
        act_catalogues.setShortcut(QKeySequence("Ctrl+K"))
        act_catalogues.triggered.connect(self._open_catalogues_dialog)
        edit_menu.addAction(act_catalogues)
        toolbar.addAction(act_catalogues)

        # --- Catalogues Menu ---
        cat_menu = menubar.addMenu("&Catalogues")

        act_cat_manage = QAction("&Manage Catalogues...", self)
        act_cat_manage.setShortcut(QKeySequence("Ctrl+K"))
        act_cat_manage.setStatusTip("Open window to browse, create, edit, and delete catalogue entries")
        act_cat_manage.triggered.connect(self._open_catalogues_dialog)
        cat_menu.addAction(act_cat_manage)

        self.act_configure_paths = QAction("&Configure Catalogue Paths...", self)
        self.act_configure_paths.setStatusTip("Configure default file paths for enemies.json and secrets.json")
        self.act_configure_paths.triggered.connect(self.configure_catalogue_paths)
        cat_menu.addAction(self.act_configure_paths)

        cat_menu.addSeparator()

        self.act_load_catalogues = QAction("&Load Catalogues (JSON)...", self)
        self.act_load_catalogues.setStatusTip("Load enemy or secret definitions from a JSON file")
        self.act_load_catalogues.triggered.connect(self.load_catalogues_from_json)
        cat_menu.addAction(self.act_load_catalogues)

        self.act_save_catalogues = QAction("&Save Catalogues (JSON)", self)
        self.act_save_catalogues.setStatusTip("Save enemy and secret definitions to default or configured JSON files")
        self.act_save_catalogues.triggered.connect(self.save_catalogues_to_json)
        cat_menu.addAction(self.act_save_catalogues)

        self.act_save_catalogues_as = QAction("Save Catalogues &As...", self)
        self.act_save_catalogues_as.setStatusTip("Save enemy and secret definitions to a chosen directory")
        self.act_save_catalogues_as.triggered.connect(self.save_catalogues_as)
        cat_menu.addAction(self.act_save_catalogues_as)

        # --- View Menu ---
        view_menu = menubar.addMenu("&View")

        act_zoom_in = QAction("Zoom &In", self)
        act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        act_zoom_in.triggered.connect(self._on_zoom_in)
        view_menu.addAction(act_zoom_in)
        toolbar.addAction(act_zoom_in)

        act_zoom_out = QAction("Zoom &Out", self)
        act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        act_zoom_out.triggered.connect(self._on_zoom_out)
        view_menu.addAction(act_zoom_out)
        toolbar.addAction(act_zoom_out)

        act_fit = QAction("&Fit Scene to View", self)
        act_fit.triggered.connect(self.scene_view.fit_scene_in_view)
        view_menu.addAction(act_fit)
        toolbar.addAction(act_fit)

        # Grid submenu
        grid_menu = view_menu.addMenu("&Grid Overlay")
        grid_group = QActionGroup(self)
        for mode in ("none", "4x8", "8x8", "16x16"):
            act_g = QAction(f"Grid: {mode.upper() if mode != 'none' else 'Off'}", self)
            act_g.setCheckable(True)
            if mode == "none":
                act_g.setChecked(True)
            act_g.setData(mode)
            act_g.triggered.connect(lambda checked=False, m=mode: self.scene_view.canvas.set_grid_mode(m))
            grid_group.addAction(act_g)
            grid_menu.addAction(act_g)

    # -------------------------------------------------------------------------
    # Scene Operations
    # -------------------------------------------------------------------------
    def new_scene(
        self,
        prompt_dialog: bool = True,
        name: str = "untitled",
        width: int = DEFAULT_SCENE_WIDTH,
        height: int = DEFAULT_SCENE_HEIGHT,
    ) -> None:
        """Create a new empty scene with configurable resolution after prompting for unsaved changes."""
        if not self._maybe_save_changes():
            return

        if prompt_dialog:
            dialog = NewSceneDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            name, width, height = dialog.get_values()

        self.scene_model = Scene(name=name, width=width, height=height, catalogues=self.catalogues)
        self.current_file_path = None
        self._next_element_num = 1
        self._next_platform_num = 1
        self.undo_stack.clear()
        self._is_dirty = False
        self._sync_all()

    def _on_apply_resolution_clicked(self) -> None:
        """Apply new resolution to current scene via undoable command with out-of-bounds warning."""
        new_w = self.scene_w_spin.value()
        new_h = self.scene_h_spin.value()
        if new_w == self.scene_model.width and new_h == self.scene_model.height:
            return

        # Check if decreasing resolution leaves any elements outside boundaries
        oob_count = 0
        for elem in self.scene_model.elements:
            if (
                elem.position.x < 0
                or elem.position.y < 0
                or elem.position.x + elem.width > new_w
                or elem.position.y + elem.height > new_h
            ):
                oob_count += 1

        if oob_count > 0 and (new_w < self.scene_model.width or new_h < self.scene_model.height):
            reply = QMessageBox.warning(
                self,
                "Elements Outside Canvas",
                f"Decreasing resolution will leave {oob_count} element(s) partially or completely outside the canvas boundaries.\n\n"
                "Elements will NOT be deleted or moved.\nDo you want to proceed with resizing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.scene_w_spin.setValue(self.scene_model.width)
                self.scene_h_spin.setValue(self.scene_model.height)
                return

        cmd = ResizeSceneCommand(
            self.scene_model,
            new_w,
            new_h,
            callback=lambda: self._on_command_executed(self.scene_view.get_selected_element_id()),
        )
        self.undo_stack.push(cmd)

    def open_scene(self, file_path: Optional[str] = None) -> None:
        """Open a scene JSON file."""
        if not self._maybe_save_changes():
            return

        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Open Atari Scene JSON",
                str(self.base_dir),
                "Scene JSON (*.json);;All Files (*)",
            )
            if not file_path:
                return

        try:
            scene = SceneSerializer.load_from_file(
                file_path,
                base_dir=self.base_dir,
                validate_source_exists=False,
            )
        except UnsupportedSchemaVersionError as err:
            QMessageBox.critical(self, "Unsupported Schema", f"Cannot load file: {err}")
            return
        except CorruptedFileError as err:
            QMessageBox.critical(self, "Corrupted File", f"Cannot load file: {err}")
            return
        except Exception as err:
            QMessageBox.critical(self, "Load Error", f"Unexpected error reading file: {err}")
            return

        # Check if source graphics exist; warn if missing without crashing
        missing_sources = []
        for src in scene.get_sources():
            res_path = self.asset_manager.resolve_path(src)
            if not res_path.is_file() and src not in missing_sources:
                missing_sources.append(src)

        if missing_sources:
            QMessageBox.warning(
                self,
                "Source Graphics Missing",
                f"The following tileset graphic(s) were not found in 'tiles/':\n"
                + "\n".join(f"• {s}" for s in missing_sources)
                + "\n\nElements referencing these graphics will be rendered as placeholders until the files are restored.",
            )

        # Refresh project catalogues
        try:
            self.catalogues = ProjectCatalogues.load_from_dir(self.base_dir)
        except Exception:
            pass

        # Check if objects reference missing definitions
        missing_defs = []
        for obj in scene.objects:
            if not self.catalogues.get_definition(obj.type, obj.definition_id):
                missing_defs.append(f"{obj.id} ({obj.type} -> '{obj.definition_id}')")
        if missing_defs:
            QMessageBox.warning(
                self,
                "Missing Catalogue Definitions",
                "The following objects in the loaded scene reference missing definitions:\n"
                + "\n".join(f"• {m}" for m in missing_defs)
                + "\n\nThese objects will be displayed with default warning colors.",
            )

        scene.catalogues = self.catalogues
        self.scene_model = scene
        self.current_file_path = Path(file_path).resolve()
        self.undo_stack.clear()
        self._is_dirty = False

        # Determine next element number
        max_num = 0
        for elem in self.scene_model.elements:
            elem_id_str = str(elem.id)
            if elem_id_str.startswith("element-"):
                try:
                    num = int(elem_id_str.split("-")[-1])
                    if num > max_num:
                        max_num = num
                except (ValueError, TypeError):
                    pass
        self._next_element_num = max_num + 1

        max_plat = 0
        for plat in self.scene_model.platforms:
            plat_id_str = str(plat.id)
            if plat_id_str.startswith("platform-"):
                try:
                    num = int(plat_id_str.split("-")[-1])
                    if num > max_plat:
                        max_plat = num
                except (ValueError, TypeError):
                    pass
        self._next_platform_num = max_plat + 1

        max_obj = 0
        for obj in self.scene_model.objects:
            try:
                if isinstance(obj.id, int):
                    num = obj.id
                else:
                    str_id = str(obj.id).strip()
                    if "-" in str_id:
                        num = int(str_id.split("-")[-1])
                    else:
                        num = int(str_id)
                if num > max_obj:
                    max_obj = num
            except (ValueError, TypeError):
                pass
        self._next_object_num = max_obj + 1

        self._sync_all()

        # Preselect file in tile browser if elements exist
        sources = scene.get_sources()
        if sources:
            self.tile_browser.select_file(sources[0])

    def save_scene(self) -> bool:
        """Save scene to current file path, or prompt Save As."""
        if self.current_file_path is None:
            return self.save_scene_as()

        try:
            self.catalogues.save_to_dir(self.base_dir)
            SceneSerializer.save_to_file(
                self.scene_model,
                self.current_file_path,
                base_dir=self.base_dir,
            )
            self._is_dirty = False
            self.undo_stack.setClean()
            self._update_window_title()
            self.status_bar.showMessage(f"Saved to {self.current_file_path.name}", 3000)
            return True
        except Exception as err:
            QMessageBox.critical(self, "Save Error", f"Could not save scene: {err}")
            return False

    def save_scene_as(self) -> bool:
        """Prompt user for file path and save atomically."""
        suggested_name = f"{self.scene_model.name}.json"
        target_dir = self.current_file_path.parent if self.current_file_path else self.base_dir

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Atari Scene JSON As",
            str(target_dir / suggested_name),
            "Scene JSON (*.json);;All Files (*)",
        )
        if not file_path:
            return False

        self.current_file_path = Path(file_path).resolve()
        return self.save_scene()

    def _maybe_save_changes(self) -> bool:
        """Check for unsaved changes and prompt user. Returns True to proceed, False to cancel."""
        if not self._is_dirty:
            return True

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "The current scene has unsaved changes.\nDo you want to save them before proceeding?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Save:
            return self.save_scene()
        elif reply == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._maybe_save_changes():
            event.accept()
        else:
            event.ignore()

    # -------------------------------------------------------------------------
    # Synchronization & State
    # -------------------------------------------------------------------------
    def _sync_all(self) -> None:
        """Synchronize the whole UI with current model state."""
        selected_elem_id = self.scene_view.get_selected_element_id()
        selected_plat_id = self.scene_view.get_selected_platform_id()
        selected_obj_id = self.scene_view.get_selected_object_id()

        self.scene_name_edit.setText(self.scene_model.name)
        self.scene_group.setTitle(f"Scene Settings ({self.scene_model.width} × {self.scene_model.height})")

        self.scene_w_spin.blockSignals(True)
        self.scene_h_spin.blockSignals(True)
        self.scene_w_spin.setValue(self.scene_model.width)
        self.scene_h_spin.setValue(self.scene_model.height)
        self.scene_w_spin.blockSignals(False)
        self.scene_h_spin.blockSignals(False)

        sources = self.scene_model.get_sources()
        if not sources:
            self.scene_graphic_lbl.setText("<i>None (no elements yet)</i>")
        elif len(sources) == 1:
            self.scene_graphic_lbl.setText(f"<b>{sources[0]}</b>")
        else:
            names = ", ".join(Path(s).name for s in sources)
            self.scene_graphic_lbl.setText(f"<b>{len(sources)} graphics:</b> {names}")

        self.scene_view.populate_scene(
            self.scene_model,
            self.asset_manager,
            selected_element_id=selected_elem_id,
            selected_platform_id=selected_plat_id,
            selected_object_id=selected_obj_id,
            catalogues=self.catalogues,
        )

        self._refresh_layers_list(selected_elem_id)
        self._refresh_platform_list(selected_plat_id)
        self._refresh_object_list(selected_obj_id)
        self._refresh_object_creator_platforms()
        self._refresh_object_creator_definitions()
        self._refresh_platform_creator_profiles()

        selected_elem = self.scene_model.get_element(selected_elem_id) if selected_elem_id else None
        self._update_property_panel(selected_elem)

        selected_plat = self.scene_model.get_platform(selected_plat_id) if selected_plat_id else None
        self._update_platform_property_panel(selected_plat)

        selected_obj = self.scene_model.get_object(selected_obj_id) if selected_obj_id is not None else None
        self._update_object_property_panel(selected_obj)

        self.status_res_lbl.setText(f"Size: {self.scene_model.width}×{self.scene_model.height}")
        self.status_elem_count_lbl.setText(
            f"Tiles: {len(self.scene_model.elements)} | Platforms: {len(self.scene_model.platforms)} | Objects: {len(self.scene_model.objects)}"
        )
        self._update_window_title()

    def _refresh_layers_list(self, selected_id: Optional[str] = None) -> None:
        self.layers_list.blockSignals(True)
        self.layers_list.clear()

        selected_row = -1
        for idx, elem in enumerate(self.scene_model.elements):
            src_name = Path(elem.source).name
            text = f"[{idx}] {elem.id} ({src_name} {elem.width}×{elem.height}) @ ({elem.position.x}, {elem.position.y})"
            if elem.flip_x:
                text += " [FLIPPED]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, elem.id)
            self.layers_list.addItem(item)
            if elem.id == selected_id:
                selected_row = idx

        if selected_row >= 0:
            self.layers_list.setCurrentRow(selected_row)
        self.layers_list.blockSignals(False)

    def _update_property_panel(self, elem: Optional[SceneElement]) -> None:
        if elem is None:
            self.elem_group.setEnabled(False)
            self.prop_id_lbl.setText("-")
            self.prop_src_lbl.setText("-")
            self.prop_pos_x.blockSignals(True)
            self.prop_pos_y.blockSignals(True)
            self.prop_pos_x.setValue(0)
            self.prop_pos_y.setValue(0)
            self.prop_pos_x.blockSignals(False)
            self.prop_pos_y.blockSignals(False)
            self.prop_size_lbl.setText("-")
            self.prop_crop_lbl.setText("-")
            self.prop_flip_check.blockSignals(True)
            self.prop_flip_check.setChecked(False)
            self.prop_flip_check.blockSignals(False)
            return

        self.elem_group.setEnabled(True)
        self.prop_id_lbl.setText(f"<b>{elem.id}</b>")
        self.prop_src_lbl.setText(elem.source)

        self.prop_pos_x.blockSignals(True)
        self.prop_pos_y.blockSignals(True)
        self.prop_pos_x.setValue(elem.position.x)
        self.prop_pos_y.setValue(elem.position.y)
        self.prop_pos_x.blockSignals(False)
        self.prop_pos_y.blockSignals(False)

        self.prop_size_lbl.setText(f"{elem.width} × {elem.height} px")
        self.prop_crop_lbl.setText(
            f"({elem.source_rect.x}, {elem.source_rect.y}) [{elem.source_rect.width}×{elem.source_rect.height}]"
        )

        self.prop_flip_check.blockSignals(True)
        self.prop_flip_check.setChecked(elem.flip_x)
        self.prop_flip_check.blockSignals(False)

    def _update_window_title(self) -> None:
        title = "Atari 8-bit Scene Editor"
        if self.current_file_path:
            title += f" - {self.current_file_path.name}"
        else:
            title += f" - [{self.scene_model.name}]"
        if self._is_dirty:
            title += " *"
        self.setWindowTitle(title)

    def _on_clean_changed(self, is_clean: bool) -> None:
        self._is_dirty = not is_clean
        self._update_window_title()

    # -------------------------------------------------------------------------
    # User Actions & Events
    # -------------------------------------------------------------------------
    def _on_tile_image_selected(self, source_path: str) -> None:
        self.crop_editor.load_image(source_path)

    def _on_add_element_requested(self, source_path: str, crop_rect: Rect) -> None:
        """Handle request to add a cropped fragment onto the scene canvas."""
        norm_source = self.asset_manager.to_relative_path(source_path)

        # Generate unique element ID
        elem_id = f"element-{self._next_element_num:03d}"
        self._next_element_num += 1

        # Center on canvas initially
        init_x = max(0, (self.scene_model.width - crop_rect.width) // 2)
        init_y = max(0, (self.scene_model.height - crop_rect.height) // 2)

        elem = SceneElement(
            id=elem_id,
            source=norm_source,
            source_rect=Rect(crop_rect.x, crop_rect.y, crop_rect.width, crop_rect.height),
            position=Position(init_x, init_y),
            flip_x=False,
            z_index=len(self.scene_model.elements),
        )

        cmd = AddElementCommand(
            self.scene_model,
            elem,
            callback=lambda: self._on_command_executed(elem_id),
        )
        self.undo_stack.push(cmd)

    def _on_command_executed(self, select_id: Optional[str] = None) -> None:
        self._is_dirty = True
        self._sync_all()
        if select_id:
            self.scene_view.select_element(select_id)

    def _on_element_selected(self, element_id: str) -> None:
        if self._is_selecting_element:
            return
        self._is_selecting_element = True
        try:
            elem = self.scene_model.get_element(element_id)
            self.scene_view.select_element(element_id)
            self._update_property_panel(elem)
            self._update_platform_property_panel(None)
            self._update_object_property_panel(None)
            self._refresh_layers_list(element_id)
            self.prop_tabs.setCurrentIndex(0)
        finally:
            self._is_selecting_element = False

    def _on_platform_selected(self, platform_id: str) -> None:
        if self._is_selecting_platform:
            return
        self._is_selecting_platform = True
        try:
            plat = self.scene_model.get_platform(platform_id)
            self.scene_view.select_platform(platform_id)
            self._update_platform_property_panel(plat)
            self._update_property_panel(None)
            self._update_object_property_panel(None)
            self._refresh_platform_list(platform_id)
            if platform_id and hasattr(self, "new_obj_platform_combo"):
                idx = self.new_obj_platform_combo.findData(platform_id)
                if idx >= 0 and self.new_obj_platform_combo.currentIndex() != idx:
                    self.new_obj_platform_combo.setCurrentIndex(idx)
            self.prop_tabs.setCurrentIndex(1)
        finally:
            self._is_selecting_platform = False

    def _on_object_selected(self, object_id: str) -> None:
        if self._is_selecting_object:
            return
        self._is_selecting_object = True
        try:
            obj = self.scene_model.get_object(object_id)
            self.scene_view.select_object(object_id)
            self._update_object_property_panel(obj)
            self._update_property_panel(None)
            self._update_platform_property_panel(None)
            self._refresh_object_list(object_id)
            self.prop_tabs.setCurrentIndex(2)
        finally:
            self._is_selecting_object = False

    def _get_effective_selected_object_id(self) -> Optional[Any]:
        selected_id = self.scene_view.get_selected_object_id()
        if selected_id is not None:
            return selected_id
        if self.objects_list.currentRow() >= 0:
            item = self.objects_list.currentItem()
            if item:
                val = item.data(Qt.ItemDataRole.UserRole)
                if val is not None:
                    return val
        if self.scene_model.objects:
            return self.scene_model.objects[0].id
        return None

    def _on_prop_tab_changed(self, index: int) -> None:
        if index == 2:  # Objects tab
            eff_id = self._get_effective_selected_object_id()
            if eff_id is not None:
                self._on_object_selected(eff_id)
            else:
                self._update_object_property_panel(None)

    def _on_object_command_executed(self, select_id: Optional[Any] = None) -> None:
        self._is_dirty = True
        self._sync_all()
        if select_id is not None:
            self._on_object_selected(select_id)

    def _on_element_moved_by_view(
        self, element_id: str, old_pos: tuple, new_pos: tuple
    ) -> None:
        if old_pos == new_pos:
            return
        cmd = MoveElementCommand(
            self.scene_model,
            element_id,
            old_pos,
            new_pos,
            callback=lambda: self._on_command_executed(element_id),
        )
        self.undo_stack.push(cmd)

    def _on_platform_moved_by_view(
        self, platform_id: str, old_pos: tuple, new_pos: tuple
    ) -> None:
        if old_pos == new_pos:
            return
        plat = self.scene_model.get_platform(platform_id)
        if not plat:
            return

        old_x, old_y = old_pos
        new_x, new_y = new_pos

        if new_y != old_y:
            ok, msg = can_add_platform_to_row(
                self.scene_model.platforms,
                plat.type,
                new_y,
                exclude_id=platform_id,
                scene_height=self.scene_model.height,
                width=plat.width,
            )
            if not ok:
                QMessageBox.warning(self, "Invalid Platform Position", msg)
                self.scene_view.update_platform_item(plat)
                return

        # Check collision with other platforms
        colliding = check_platform_collision(
            self.scene_model.platforms,
            (new_x, new_y, plat.width, plat.height),
            exclude_id=platform_id,
        )
        if colliding:
            QMessageBox.warning(
                self,
                "Platform Collision",
                f"Cannot move platform '{platform_id}': position ({new_x}, {new_y}) collides with "
                f"platform '{colliding.id}' ({colliding.type}, x={colliding.position.x}..{colliding.position.x+colliding.width}, y={colliding.position.y}).",
            )
            self.scene_view.update_platform_item(plat)
            return

        cmd = MovePlatformCommand(
            self.scene_model,
            platform_id,
            old_pos,
            new_pos,
            callback=lambda: self._on_platform_command_executed(platform_id),
        )
        self.undo_stack.push(cmd)

    def _on_new_plat_type_changed(self) -> None:
        """Update allowed widths in creator combo when type changes."""
        p_type = self.new_plat_type_combo.currentData()
        self.new_plat_width_combo.blockSignals(True)
        self.new_plat_width_combo.clear()
        for w in get_allowed_widths(p_type):
            res = get_required_platform_resources(p_type, w)
            unit = "sprite" if p_type == PLATFORM_TYPE_SPRITE else "missile"
            plural = "s" if res > 1 else ""
            self.new_plat_width_combo.addItem(f"{w} px ({res} {unit}{plural})", w)
        default_w = 16 if p_type == PLATFORM_TYPE_SPRITE else 8
        idx = self.new_plat_width_combo.findData(default_w)
        if idx >= 0:
            self.new_plat_width_combo.setCurrentIndex(idx)
        self.new_plat_width_combo.blockSignals(False)

    def _on_add_platform_clicked(self) -> None:
        """Add a new hardware platform from creator controls."""
        p_type = self.new_plat_type_combo.currentData()
        width = self.new_plat_width_combo.currentData()
        y = self.new_plat_row_combo.currentData()
        x = self.new_plat_x_spin.value()

        if y is None or width is None:
            QMessageBox.warning(self, "Invalid Configuration", "No valid row or width selected.")
            return

        ok, msg = can_add_platform_to_row(
            self.scene_model.platforms, p_type, y, width=width, scene_height=self.scene_model.height
        )
        if not ok:
            QMessageBox.warning(self, "Invalid Platform Position", msg)
            return

        colliding = check_platform_collision(
            self.scene_model.platforms,
            (x, y, width, PLATFORM_HEIGHT),
        )
        if colliding:
            QMessageBox.warning(
                self,
                "Platform Collision",
                f"Cannot add platform: position ({x}, {y}) with width {width} collides with "
                f"existing platform '{colliding.id}' ({colliding.type}, x={colliding.position.x}..{colliding.position.x+colliding.width}, y={colliding.position.y}).",
            )
            return

        plat_id = f"platform-{self._next_platform_num:03d}"
        self._next_platform_num += 1

        prof_id = self.new_plat_color_profile_combo.currentData()
        plat = PlatformElement(
            id=plat_id,
            type=p_type,
            position=Position(x, y),
            width=width,
            height=PLATFORM_HEIGHT,
            color_profile_id=prof_id,
        )

        cmd = AddPlatformCommand(
            self.scene_model,
            plat,
            callback=lambda: self._on_platform_command_executed(plat_id),
        )
        self.undo_stack.push(cmd)

    def _on_platform_command_executed(self, select_id: Optional[str] = None) -> None:
        self._is_dirty = True
        self._sync_all()
        if select_id:
            self._on_platform_selected(select_id)

    def _on_plat_prop_x_changed(self) -> None:
        selected_id = self.scene_view.get_selected_platform_id()
        if not selected_id:
            return
        plat = self.scene_model.get_platform(selected_id)
        if not plat:
            return

        new_x = self.plat_prop_x_spin.value()
        if plat.position.x == new_x:
            return

        colliding = check_platform_collision(
            self.scene_model.platforms,
            (new_x, plat.position.y, plat.width, plat.height),
            exclude_id=selected_id,
        )
        if colliding:
            QMessageBox.warning(
                self,
                "Platform Collision",
                f"Cannot move platform '{selected_id}': position ({new_x}, {plat.position.y}) collides with "
                f"existing platform '{colliding.id}' ({colliding.type}, x={colliding.position.x}..{colliding.position.x+colliding.width}, y={colliding.position.y}).",
            )
            self._update_platform_property_panel(plat)
            return

        cmd = MovePlatformCommand(
            self.scene_model,
            selected_id,
            (plat.position.x, plat.position.y),
            (new_x, plat.position.y),
            callback=lambda: self._on_platform_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_plat_prop_row_changed(self) -> None:
        selected_id = self.scene_view.get_selected_platform_id()
        if not selected_id:
            return
        plat = self.scene_model.get_platform(selected_id)
        if not plat:
            return

        new_y = self.plat_prop_row_combo.currentData()
        if new_y is None or plat.position.y == new_y:
            return

        ok, msg = can_add_platform_to_row(
            self.scene_model.platforms,
            plat.type,
            new_y,
            exclude_id=selected_id,
            scene_height=self.scene_model.height,
            width=plat.width,
        )
        if not ok:
            QMessageBox.warning(self, "Invalid Platform Position", msg)
            self._update_platform_property_panel(plat)
            return

        colliding = check_platform_collision(
            self.scene_model.platforms,
            (plat.position.x, new_y, plat.width, plat.height),
            exclude_id=selected_id,
        )
        if colliding:
            QMessageBox.warning(
                self,
                "Platform Collision",
                f"Cannot move platform '{selected_id}' to row y={new_y}: collides with "
                f"existing platform '{colliding.id}' ({colliding.type}, x={colliding.position.x}..{colliding.position.x+colliding.width}, y={colliding.position.y}).",
            )
            self._update_platform_property_panel(plat)
            return

        cmd = MovePlatformCommand(
            self.scene_model,
            selected_id,
            (plat.position.x, plat.position.y),
            (plat.position.x, new_y),
            callback=lambda: self._on_platform_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_plat_prop_width_changed(self) -> None:
        selected_id = self.scene_view.get_selected_platform_id()
        if not selected_id:
            return
        plat = self.scene_model.get_platform(selected_id)
        if not plat:
            return

        new_w = self.plat_prop_width_combo.currentData()
        if new_w is None or plat.width == new_w:
            return

        ok, msg = can_add_platform_to_row(
            self.scene_model.platforms,
            plat.type,
            plat.position.y,
            exclude_id=selected_id,
            scene_height=self.scene_model.height,
            width=new_w,
        )
        if not ok:
            QMessageBox.warning(self, "Hardware Resource Limit", msg)
            self._update_platform_property_panel(plat)
            return

        colliding = check_platform_collision(
            self.scene_model.platforms,
            (plat.position.x, plat.position.y, new_w, plat.height),
            exclude_id=selected_id,
        )
        if colliding:
            QMessageBox.warning(
                self,
                "Platform Collision",
                f"Cannot resize platform '{selected_id}' to width {new_w}: collides with "
                f"existing platform '{colliding.id}' ({colliding.type}, x={colliding.position.x}..{colliding.position.x+colliding.width}, y={colliding.position.y}).",
            )
            self._update_platform_property_panel(plat)
            return

        cmd = ResizePlatformCommand(
            self.scene_model,
            selected_id,
            plat.width,
            new_w,
            callback=lambda: self._on_platform_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_plat_prop_type_changed(self) -> None:
        selected_id = self.scene_view.get_selected_platform_id()
        if not selected_id:
            return
        plat = self.scene_model.get_platform(selected_id)
        if not plat:
            return

        new_type = self.plat_prop_type_combo.currentData()
        if new_type is None or plat.type == new_type:
            return

        allowed = get_allowed_widths(new_type)
        new_w = plat.width if plat.width in allowed else (16 if new_type == PLATFORM_TYPE_SPRITE else 8)

        ok, msg = can_add_platform_to_row(
            self.scene_model.platforms,
            new_type,
            plat.position.y,
            exclude_id=selected_id,
            scene_height=self.scene_model.height,
            width=new_w,
        )
        if not ok:
            QMessageBox.warning(self, "Hardware Resource Limit", msg)
            self._update_platform_property_panel(plat)
            return

        colliding = check_platform_collision(
            self.scene_model.platforms,
            (plat.position.x, plat.position.y, new_w, plat.height),
            exclude_id=selected_id,
        )
        if colliding:
            QMessageBox.warning(
                self,
                "Platform Collision",
                f"Cannot change platform '{selected_id}' to {new_type}: new configuration with width {new_w} "
                f"collides with existing platform '{colliding.id}' ({colliding.type}, x={colliding.position.x}..{colliding.position.x+colliding.width}, y={colliding.position.y}).",
            )
            self._update_platform_property_panel(plat)
            return

        cmd = ChangePlatformTypeCommand(
            self.scene_model,
            selected_id,
            plat.type,
            plat.width,
            new_type,
            new_w,
            callback=lambda: self._on_platform_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_platform_list_row_changed(self, row: int) -> None:
        if 0 <= row < len(self.scene_model.platforms):
            plat = self.scene_model.platforms[row]
            self.scene_view.select_platform(plat.id)
            self._update_platform_property_panel(plat)

    def _refresh_platform_list(self, selected_id: Optional[str] = None) -> None:
        self.platforms_list.blockSignals(True)
        self.platforms_list.clear()

        selected_row = -1
        for idx, plat in enumerate(self.scene_model.platforms):
            type_tag = "SPRITE" if plat.type == PLATFORM_TYPE_SPRITE else "MISSILE"
            text = f"[{type_tag}] {plat.id} ({plat.width}×{plat.height}) @ ({plat.position.x}, {plat.position.y}) [Row {plat.row_index}]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, plat.id)
            self.platforms_list.addItem(item)
            if plat.id == selected_id:
                selected_row = idx

        if selected_row >= 0:
            self.platforms_list.setCurrentRow(selected_row)
        self.platforms_list.blockSignals(False)

        # Also refresh rows in creator combo with current usage
        cur_creator_y = self.new_plat_row_combo.currentData()
        self.new_plat_row_combo.blockSignals(True)
        self.new_plat_row_combo.clear()
        allowed_rows = get_allowed_platform_rows(self.scene_model.height)
        for y in allowed_rows:
            s_count, m_count = self.scene_model.get_platform_row_usage(y)
            row_idx = get_row_index(y)
            label = f"Row {row_idx} (y={y}) — Sprite: {s_count}/{MAX_SPRITES_PER_ROW}, Missile: {m_count}/{MAX_MISSILES_PER_ROW}"
            self.new_plat_row_combo.addItem(label, y)
        if cur_creator_y in allowed_rows:
            idx = self.new_plat_row_combo.findData(cur_creator_y)
            if idx >= 0:
                self.new_plat_row_combo.setCurrentIndex(idx)
        self.new_plat_row_combo.blockSignals(False)

    def _update_platform_property_panel(self, plat: Optional[PlatformElement]) -> None:
        if plat is None:
            self.plat_elem_group.setEnabled(False)
            self.plat_prop_id_lbl.setText("-")
            self.plat_prop_type_combo.blockSignals(True)
            self.plat_prop_type_combo.setCurrentIndex(0)
            self.plat_prop_type_combo.blockSignals(False)
            self.plat_prop_width_combo.blockSignals(True)
            self.plat_prop_width_combo.clear()
            self.plat_prop_width_combo.blockSignals(False)
            self.plat_prop_row_combo.blockSignals(True)
            self.plat_prop_row_combo.clear()
            self.plat_prop_row_combo.blockSignals(False)
            self.plat_prop_color_profile_combo.blockSignals(True)
            self.plat_prop_color_profile_combo.clear()
            self.plat_prop_color_profile_combo.blockSignals(False)
            self.plat_prop_x_spin.blockSignals(True)
            self.plat_prop_x_spin.setValue(0)
            self.plat_prop_x_spin.blockSignals(False)
            self.plat_prop_row_status_lbl.setText("-")
            return

        self.plat_elem_group.setEnabled(True)
        self.plat_prop_id_lbl.setText(f"<b>{plat.id}</b>")

        # Type combo
        self.plat_prop_type_combo.blockSignals(True)
        idx = self.plat_prop_type_combo.findData(plat.type)
        if idx >= 0:
            self.plat_prop_type_combo.setCurrentIndex(idx)
        self.plat_prop_type_combo.blockSignals(False)

        # Width combo
        self.plat_prop_width_combo.blockSignals(True)
        self.plat_prop_width_combo.clear()
        for w in get_allowed_widths(plat.type):
            res = get_required_platform_resources(plat.type, w)
            unit = "sprite" if plat.type == PLATFORM_TYPE_SPRITE else "missile"
            plural = "s" if res > 1 else ""
            self.plat_prop_width_combo.addItem(f"{w} px ({res} {unit}{plural})", w)
        w_idx = self.plat_prop_width_combo.findData(plat.width)
        if w_idx >= 0:
            self.plat_prop_width_combo.setCurrentIndex(w_idx)
        self.plat_prop_width_combo.blockSignals(False)

        # Row combo
        self.plat_prop_row_combo.blockSignals(True)
        self.plat_prop_row_combo.clear()
        allowed_rows = get_allowed_platform_rows(self.scene_model.height)
        for y in allowed_rows:
            s_count, m_count = self.scene_model.get_platform_row_usage(y, exclude_id=plat.id)
            if y == plat.position.y:
                if plat.type == PLATFORM_TYPE_SPRITE:
                    s_count += get_required_platform_resources(plat.type, plat.width)
                else:
                    m_count += get_required_platform_resources(plat.type, plat.width)
            row_idx = get_row_index(y)
            label = f"Row {row_idx} (y={y}) [Sprite: {s_count}/{MAX_SPRITES_PER_ROW}, Missile: {m_count}/{MAX_MISSILES_PER_ROW}]"
            self.plat_prop_row_combo.addItem(label, y)
        r_idx = self.plat_prop_row_combo.findData(plat.position.y)
        if r_idx >= 0:
            self.plat_prop_row_combo.setCurrentIndex(r_idx)
        self.plat_prop_row_combo.blockSignals(False)

        # Color profile combo
        self.plat_prop_color_profile_combo.blockSignals(True)
        self.plat_prop_color_profile_combo.clear()
        self.plat_prop_color_profile_combo.addItem("(None / Default)", None)
        for prof in sorted(self.catalogues.platform_profiles.values(), key=lambda p: p.name):
            self.plat_prop_color_profile_combo.addItem(f"{prof.name} [{prof.id}]", prof.id)
        p_idx = self.plat_prop_color_profile_combo.findData(plat.color_profile_id)
        if p_idx >= 0:
            self.plat_prop_color_profile_combo.setCurrentIndex(p_idx)
        else:
            self.plat_prop_color_profile_combo.setCurrentIndex(0)
        self.plat_prop_color_profile_combo.blockSignals(False)

        # X spinbox
        self.plat_prop_x_spin.blockSignals(True)
        self.plat_prop_x_spin.setValue(plat.position.x)
        self.plat_prop_x_spin.blockSignals(False)

        # Row status label
        s_used, m_used = self.scene_model.get_platform_row_usage(plat.position.y)
        self.plat_prop_row_status_lbl.setText(
            f"Row {plat.row_index} (y={plat.position.y}): <b>Sprite: {s_used}/{MAX_SPRITES_PER_ROW}</b>, "
            f"<b>Missile: {m_used}/{MAX_MISSILES_PER_ROW}</b>"
        )

    def _on_plat_prop_color_profile_changed(self) -> None:
        selected_id = self.scene_view.get_selected_platform_id()
        if not selected_id:
            return
        plat = self.scene_model.get_platform(selected_id)
        if not plat:
            return

        new_prof_id = self.plat_prop_color_profile_combo.currentData()
        if plat.color_profile_id == new_prof_id:
            return

        cmd = ChangePlatformColorProfileCommand(
            self.scene_model,
            selected_id,
            plat.color_profile_id,
            new_prof_id,
            callback=self._sync_all,
        )
        self.undo_stack.push(cmd)

    def _refresh_platform_creator_profiles(self) -> None:
        if not hasattr(self, "new_plat_color_profile_combo"):
            return
        cur_data = self.new_plat_color_profile_combo.currentData()
        self.new_plat_color_profile_combo.blockSignals(True)
        self.new_plat_color_profile_combo.clear()
        self.new_plat_color_profile_combo.addItem("(None / Default)", None)
        for prof in sorted(self.catalogues.platform_profiles.values(), key=lambda p: p.name):
            self.new_plat_color_profile_combo.addItem(f"{prof.name} [{prof.id}]", prof.id)
        idx = self.new_plat_color_profile_combo.findData(cur_data)
        if idx >= 0:
            self.new_plat_color_profile_combo.setCurrentIndex(idx)
        else:
            self.new_plat_color_profile_combo.setCurrentIndex(0)
        self.new_plat_color_profile_combo.blockSignals(False)

    def _on_prop_pos_changed(self) -> None:
        selected_id = self.scene_view.get_selected_element_id()
        if not selected_id:
            return
        elem = self.scene_model.get_element(selected_id)
        if not elem:
            return

        new_x = self.prop_pos_x.value()
        new_y = self.prop_pos_y.value()
        if elem.position.x == new_x and elem.position.y == new_y:
            return

        cmd = MoveElementCommand(
            self.scene_model,
            selected_id,
            (elem.position.x, elem.position.y),
            (new_x, new_y),
            callback=lambda: self._on_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_prop_flip_toggled(self, checked: bool) -> None:
        selected_id = self.scene_view.get_selected_element_id()
        if not selected_id:
            return
        elem = self.scene_model.get_element(selected_id)
        if not elem or elem.flip_x == checked:
            return

        cmd = FlipElementCommand(
            self.scene_model,
            selected_id,
            checked,
            callback=lambda: self._on_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def toggle_flip_selected(self) -> None:
        selected_id = self.scene_view.get_selected_element_id()
        if not selected_id:
            return
        elem = self.scene_model.get_element(selected_id)
        if not elem:
            return
        cmd = FlipElementCommand(
            self.scene_model,
            selected_id,
            not elem.flip_x,
            callback=lambda: self._on_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def delete_selected_element(self) -> None:
        if self.prop_tabs.currentIndex() == 2:
            selected_obj_id = self._get_effective_selected_object_id()
        else:
            selected_obj_id = self.scene_view.get_selected_object_id()
        if selected_obj_id is not None:
            cmd = RemoveSceneObjectCommand(
                self.scene_model,
                selected_obj_id,
                callback=lambda: self._on_object_command_executed(None),
            )
            self.undo_stack.push(cmd)
            return

        selected_plat_id = self.scene_view.get_selected_platform_id()
        if selected_plat_id:
            cmd = RemovePlatformCommand(
                self.scene_model,
                selected_plat_id,
                callback=lambda: self._on_platform_command_executed(None),
            )
            self.undo_stack.push(cmd)
            return

        selected_id = self.scene_view.get_selected_element_id()
        if not selected_id:
            return
        cmd = RemoveElementCommand(
            self.scene_model,
            selected_id,
            callback=lambda: self._on_command_executed(None),
        )
        self.undo_stack.push(cmd)

    # -------------------------------------------------------------
    # Catalogues & Objects (Enemies & Secrets) Handlers
    # -------------------------------------------------------------
    def _open_catalogues_dialog(self) -> None:
        """Open the modal dialog for managing enemy and secret definitions."""
        dlg = CataloguesDialog(self.catalogues, scene=self.scene_model, base_dir=self.base_dir, parent=self)
        dlg.exec()
        try:
            self.catalogues.save_to_dir(self.base_dir)
        except Exception as err:
            QMessageBox.critical(self, "Save Error", f"Failed to save catalogues:\n{err}")
        self._refresh_object_creator_definitions()
        self._sync_all()

    def load_catalogues_from_json(self, file_path: Optional[Path | str] = None) -> bool:
        """Load enemy and/or secret catalogue definitions from a JSON file."""
        if file_path is None:
            path_str, _ = QFileDialog.getOpenFileName(
                self,
                "Open Catalogue JSON File",
                str(self.base_dir),
                "Catalogue JSON (*.json);;All Files (*)",
            )
            if not path_str:
                return False
            target_path = Path(path_str)
        else:
            target_path = Path(file_path)

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as err:
            QMessageBox.critical(self, "Load Error", f"Failed to parse catalogue JSON file:\n{err}")
            return False

        enemies_count = 0
        secrets_count = 0
        profiles_count = 0
        try:
            if isinstance(data, dict):
                if "enemies" in data and isinstance(data["enemies"], list):
                    for item in data["enemies"]:
                        defn = EnemyDefinition.from_dict(item)
                        self.catalogues.enemies[defn.id] = defn
                        enemies_count += 1
                if "secrets" in data and isinstance(data["secrets"], list):
                    for item in data["secrets"]:
                        defn = SecretDefinition.from_dict(item)
                        self.catalogues.secrets[defn.id] = defn
                        secrets_count += 1
                raw_profiles = data.get("profiles") or data.get("platform_profiles")
                if raw_profiles and isinstance(raw_profiles, list):
                    for item in raw_profiles:
                        defn = PlatformColorProfile.from_dict(item)
                        self.catalogues.platform_profiles[defn.id] = defn
                        profiles_count += 1
                if "enemies" not in data and "secrets" not in data and "platform_profiles" not in data and "profiles" not in data:
                    if "id" in data and "name" in data:
                        if "enemy" in target_path.name.lower():
                            defn = EnemyDefinition.from_dict(data)
                            self.catalogues.enemies[defn.id] = defn
                            enemies_count += 1
                        elif "profile" in target_path.name.lower():
                            defn = PlatformColorProfile.from_dict(data)
                            self.catalogues.platform_profiles[defn.id] = defn
                            profiles_count += 1
                        else:
                            defn = SecretDefinition.from_dict(data)
                            self.catalogues.secrets[defn.id] = defn
                            secrets_count += 1
            elif isinstance(data, list):
                if "secret" in target_path.name.lower():
                    for item in data:
                        defn = SecretDefinition.from_dict(item)
                        self.catalogues.secrets[defn.id] = defn
                        secrets_count += 1
                elif "profile" in target_path.name.lower():
                    for item in data:
                        defn = PlatformColorProfile.from_dict(item)
                        self.catalogues.platform_profiles[defn.id] = defn
                        profiles_count += 1
                else:
                    for item in data:
                        defn = EnemyDefinition.from_dict(item)
                        self.catalogues.enemies[defn.id] = defn
                        enemies_count += 1

            self.catalogues.save_to_dir(self.base_dir)
            self._refresh_object_creator_definitions()
            self._sync_all()

            QMessageBox.information(
                self,
                "Catalogues Loaded",
                f"Successfully loaded definitions from:\n{target_path.name}\n\n"
                f"Enemies loaded: {enemies_count}\n"
                f"Secrets loaded: {secrets_count}\n"
                f"Platform profiles loaded: {profiles_count}",
            )
            return True
        except Exception as err:
            QMessageBox.critical(self, "Import Error", f"Failed to import catalogue definitions:\n{err}")
            return False

    def save_catalogues_to_json(self) -> bool:
        """Save project catalogues to default or configured JSON files."""
        try:
            self.catalogues.save_to_dir(self.base_dir)
            enemies_path, secrets_path = self.catalogues.get_effective_paths(self.base_dir)
            self.statusBar().showMessage(f"Catalogues saved to {enemies_path.parent}", 3000)
            QMessageBox.information(
                self,
                "Catalogues Saved",
                f"Catalogues successfully saved to:\n• {enemies_path}\n• {secrets_path}",
            )
            return True
        except Exception as err:
            QMessageBox.critical(self, "Save Error", f"Failed to save catalogues:\n{err}")
            return False

    def save_catalogues_as(self) -> bool:
        """Save project catalogues to a chosen directory."""
        dir_str = QFileDialog.getExistingDirectory(
            self,
            "Select Directory to Save Catalogues (enemies.json & secrets.json)",
            str(self.base_dir),
        )
        if not dir_str:
            return False
        target_dir = Path(dir_str)
        try:
            self.catalogues.set_paths(target_dir / "enemies.json", target_dir / "secrets.json")
            self.catalogues.save_to_dir(target_dir)
            self.statusBar().showMessage(f"Catalogues saved to {target_dir}", 3000)
            QMessageBox.information(
                self,
                "Catalogues Saved",
                f"Catalogues successfully saved to:\n• {target_dir / 'enemies.json'}\n• {target_dir / 'secrets.json'}",
            )
            return True
        except Exception as err:
            QMessageBox.critical(self, "Save Error", f"Failed to save catalogues:\n{err}")
            return False

    def configure_catalogue_paths(self) -> None:
        """Open dialog to configure custom file paths for enemies.json and secrets.json."""
        cur_enemies, cur_secrets = self.catalogues.get_effective_paths(self.base_dir)
        dlg = CataloguePathsDialog(
            base_dir=self.base_dir,
            current_enemies_path=cur_enemies,
            current_secrets_path=cur_secrets,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            enemies_path, secrets_path, reload_now = dlg.get_paths()
            self.catalogues.set_paths(enemies_path, secrets_path)

            if reload_now:
                try:
                    reloaded = ProjectCatalogues.load_from_paths(enemies_path, secrets_path)
                    self.catalogues.enemies = reloaded.enemies
                    self.catalogues.secrets = reloaded.secrets
                    self._refresh_object_creator_definitions()
                    self._sync_all()
                    self.statusBar().showMessage(
                        f"Catalogue paths configured to {enemies_path.parent}", 4000
                    )
                    QMessageBox.information(
                        self,
                        "Catalogue Paths Updated",
                        f"Catalogue paths updated successfully:\n• Enemies: {enemies_path}\n• Secrets: {secrets_path}\n\nDefinitions reloaded.",
                    )
                except Exception as err:
                    QMessageBox.warning(
                        self,
                        "Catalogue Paths Updated",
                        f"Catalogue paths updated to:\n• {enemies_path}\n• {secrets_path}\n\n"
                        f"Notice during reload: {err}",
                    )
            else:
                self.statusBar().showMessage("Catalogue paths updated.", 3000)
                QMessageBox.information(
                    self,
                    "Catalogue Paths Updated",
                    f"Catalogue paths updated successfully:\n• Enemies: {enemies_path}\n• Secrets: {secrets_path}",
                )

    def _on_new_obj_type_changed(self) -> None:
        obj_type = self.new_obj_type_combo.currentData() or OBJECT_TYPE_ENEMY
        is_enemy = (obj_type == OBJECT_TYPE_ENEMY)
        self.new_obj_speed_lbl.setVisible(is_enemy)
        self.new_obj_speed_combo.setVisible(is_enemy)
        self.new_obj_strategy_lbl.setVisible(is_enemy)
        self.new_obj_strategy_combo.setVisible(is_enemy)
        self._refresh_object_creator_definitions()

    def _on_new_obj_definition_changed(self) -> None:
        self._update_new_obj_definition_info()

    def _update_new_obj_definition_info(self) -> None:
        obj_type = self.new_obj_type_combo.currentData() or OBJECT_TYPE_ENEMY
        defn_id = self.new_obj_definition_combo.currentData()
        if not defn_id:
            self.new_obj_definition_info_lbl.setText("<small style='color: #888;'>No definition selected.</small>")
            return
        defn = self.catalogues.get_definition(obj_type, defn_id)
        if defn:
            atari_str = f"${defn.atari_color:02X}" if defn.atari_color is not None else "None"
            blink_str = "Yes" if defn.blink else "No"
            color_badge = ""
            if defn.rgb_color:
                r, g, b = defn.rgb_color
                color_badge = f"<span style='background-color: rgb({r},{g},{b}); border: 1px solid #aaa;'>&nbsp;&nbsp;&nbsp;&nbsp;</span> "
            self.new_obj_definition_info_lbl.setText(
                f"<small>{color_badge}Atari: <code>{atari_str}</code> | Blink: <b>{blink_str}</b></small>"
            )
        else:
            self.new_obj_definition_info_lbl.setText("")

    def _refresh_object_creator_definitions(self) -> None:
        obj_type = self.new_obj_type_combo.currentData() or OBJECT_TYPE_ENEMY
        self.new_obj_definition_combo.blockSignals(True)
        self.new_obj_definition_combo.clear()

        defs = self.catalogues.enemies if obj_type == OBJECT_TYPE_ENEMY else self.catalogues.secrets
        if not defs:
            self.new_obj_definition_combo.addItem("(No definitions)", None)
            self.new_obj_definition_info_lbl.setText(
                "<small style='color: #e57373;'>Catalogue is empty. Click 'Manage Catalogues...' to add definitions.</small>"
            )
        else:
            for defn_id, defn in defs.items():
                label = f"{defn.name} [{defn.id}]"
                self.new_obj_definition_combo.addItem(label, defn.id)
            self._update_new_obj_definition_info()

        self.new_obj_definition_combo.blockSignals(False)

    def _on_new_obj_platform_combo_changed(self) -> None:
        plat_id = self.new_obj_platform_combo.currentData()
        if plat_id:
            plat = self.scene_model.get_platform(plat_id)
            if plat:
                obj_w = self._new_obj_rect.width if self._new_obj_rect else 8
                min_x = max(0, plat.position.x - obj_w + 1)
                max_x = min(self.scene_model.width - obj_w, plat.position.x + plat.width - 1)
                self.new_obj_x_spin.blockSignals(True)
                self.new_obj_x_spin.setRange(min_x, max_x)
                self.new_obj_x_spin.setValue(plat.position.x)
                self.new_obj_x_spin.blockSignals(False)

    def _on_capture_crop_for_new_obj_clicked(self) -> None:
        """Compatibility helper for capturing crop."""
        if not self.crop_editor.current_source or self.crop_editor._current_crop is None:
            return
        self._new_obj_source = self.asset_manager.to_relative_path(self.crop_editor.current_source)
        c = self.crop_editor._current_crop
        self._new_obj_rect = Rect(c.x, c.y, c.width, c.height)
        if not self.catalogues.enemies:
            self.catalogues.add_enemy(EnemyDefinition(id=1, name="Default Enemy"))
            self._refresh_object_creator_definitions()
        self._on_new_obj_platform_combo_changed()

    def _on_add_object_clicked(self) -> None:
        obj_type = self.new_obj_type_combo.currentData() or OBJECT_TYPE_ENEMY
        defn_id = self.new_obj_definition_combo.currentData()
        if not defn_id:
            defs = self.catalogues.enemies if obj_type == OBJECT_TYPE_ENEMY else self.catalogues.secrets
            if defs:
                defn_id = next(iter(defs.keys()))
            else:
                cat_name = "Enemies" if obj_type == OBJECT_TYPE_ENEMY else "Secrets"
                QMessageBox.warning(
                    self,
                    "Empty Catalogue",
                    f"The {cat_name} catalogue is empty or no definition is selected.\n"
                    f"Create at least one definition in the catalogue before adding an object to the scene.",
                )
                return

        plat_id = self.new_obj_platform_combo.currentData()
        if not plat_id:
            QMessageBox.warning(
                self,
                "No Platform Selected",
                "Objects must be placed on a platform. Create a platform first if none exist.",
            )
            return

        plat = self.scene_model.get_platform(plat_id)
        if not plat:
            QMessageBox.warning(self, "Invalid Platform", f"Platform '{plat_id}' not found.")
            return

        # Check limits: max 3 enemies, max 4 secrets per stage per row
        can_add, reason = self.scene_model.can_add_object_to_platform(
            plat_id, obj_type=obj_type, definition_id=defn_id
        )
        if not can_add:
            QMessageBox.warning(
                self,
                "Object Limit Exceeded",
                f"Cannot add object to platform '{plat_id}':\n{reason}",
            )
            return

        # Determine lowest unused integer ID in 1-255
        used_ids = set()
        for o in self.scene_model.objects:
            try:
                used_ids.add(int(str(o.id).strip()))
            except (ValueError, TypeError):
                pass
        obj_id = 1
        for i in range(1, 256):
            if i not in used_ids:
                obj_id = i
                break

        x = self.new_obj_x_spin.value()
        obj_w = self._new_obj_rect.width if self._new_obj_rect else 8
        # Ensure object rests on the platform
        if not (max(x, plat.position.x) < min(x + obj_w, plat.position.x + plat.width)):
            x = plat.position.x
            self.new_obj_x_spin.setValue(x)

        speed = self.new_obj_speed_combo.currentData() if obj_type == OBJECT_TYPE_ENEMY else None
        strategy = self.new_obj_strategy_combo.currentData() if obj_type == OBJECT_TYPE_ENEMY else None

        obj = SceneObjectElement(
            id=obj_id,
            type=obj_type,
            definition_id=defn_id,
            platform_id=plat_id,
            x=x,
            source=self._new_obj_source,
            source_rect=self._new_obj_rect.clone() if self._new_obj_rect else None,
            speed=speed,
            movement_strategy=strategy,
        )

        try:
            obj.validate(scene=self.scene_model)
            cmd = AddSceneObjectCommand(
                self.scene_model,
                obj,
                callback=lambda: self._on_object_command_executed(obj_id),
            )
            self.undo_stack.push(cmd)
        except InvalidPlatformAssignmentError as err:
            QMessageBox.warning(self, "Invalid Platform Assignment", str(err))
        except Exception as err:
            QMessageBox.warning(self, "Error Adding Object", str(err))

    def _on_object_moved_by_view(
        self, object_id: str, old_pos: tuple, new_pos: tuple
    ) -> None:
        if old_pos == new_pos:
            return
        cmd = MoveSceneObjectCommand(
            self.scene_model,
            object_id,
            old_pos[0],
            new_pos[0],
            callback=lambda: self._on_object_command_executed(object_id),
        )
        self.undo_stack.push(cmd)

    def _on_obj_prop_id_changed(self) -> None:
        selected_id = self._get_effective_selected_object_id()
        if selected_id is None:
            return
        obj = self.scene_model.get_object(selected_id)
        if not obj:
            return
        new_id = self.obj_prop_id_spin.value()
        if new_id == obj.id or str(new_id) == str(obj.id):
            return

        # Check duplicate
        if any((o.id == new_id or str(o.id) == str(new_id)) and o != obj for o in self.scene_model.objects):
            QMessageBox.warning(
                self,
                "Duplicate Object ID",
                f"An object with ID {new_id} already exists on the scene. IDs must be unique (1-255).",
            )
            self.obj_prop_id_spin.blockSignals(True)
            try:
                self.obj_prop_id_spin.setValue(int(str(obj.id).strip()))
            except Exception:
                pass
            self.obj_prop_id_spin.blockSignals(False)
            return

        cmd = ChangeSceneObjectIdCommand(
            self.scene_model,
            obj.id,
            new_id,
            callback=lambda: self._on_object_command_executed(new_id),
        )
        self.undo_stack.push(cmd)

    def _on_obj_prop_type_changed(self) -> None:
        selected_id = self._get_effective_selected_object_id()
        if selected_id is None:
            return
        obj = self.scene_model.get_object(selected_id)
        if not obj:
            return
        new_type = self.obj_prop_type_combo.currentData()
        if new_type == obj.type:
            return
        new_speed = ENEMY_SPEED_MEDIUM if new_type == OBJECT_TYPE_ENEMY else None
        new_strat = STRATEGY_STATIONARY if new_type == OBJECT_TYPE_ENEMY else None

        # Pick first available definition in target catalogue if any
        defs = self.catalogues.enemies if new_type == OBJECT_TYPE_ENEMY else self.catalogues.secrets
        new_def_id = next(iter(defs.keys())) if defs else ""

        if new_type in (OBJECT_TYPE_SECRET, "treasure"):
            can_add, reason = self.scene_model.can_add_object_to_platform(
                obj.platform_id,
                obj_type=new_type,
                definition_id=new_def_id,
                exclude_id=selected_id,
            )
            if not can_add:
                QMessageBox.warning(
                    self,
                    "Secret Dependency Conflict",
                    f"Cannot change object type to Secret:\n{reason}",
                )
                self._update_object_property_panel(obj)
                return

        cmd = UpdateSceneObjectPropsCommand(
            self.scene_model,
            selected_id,
            new_type=new_type,
            new_definition_id=new_def_id,
            new_speed=new_speed,
            new_strategy=new_strat,
            callback=lambda: self._on_object_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_obj_prop_definition_changed(self) -> None:
        selected_id = self._get_effective_selected_object_id()
        if selected_id is None:
            return
        obj = self.scene_model.get_object(selected_id)
        if not obj:
            return
        new_def_id = self.obj_prop_definition_combo.currentData()
        if not new_def_id or new_def_id == obj.definition_id:
            return

        if obj.type in (OBJECT_TYPE_SECRET, "treasure"):
            can_add, reason = self.scene_model.can_add_object_to_platform(
                obj.platform_id,
                obj_type=obj.type,
                definition_id=new_def_id,
                exclude_id=selected_id,
            )
            if not can_add:
                QMessageBox.warning(
                    self,
                    "Secret Dependency Conflict",
                    f"Cannot change secret definition:\n{reason}",
                )
                self._update_object_property_panel(obj)
                return

        cmd = UpdateSceneObjectPropsCommand(
            self.scene_model,
            selected_id,
            new_definition_id=new_def_id,
            callback=lambda: self._on_object_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_obj_prop_platform_changed(self) -> None:
        selected_id = self.scene_view.get_selected_object_id()
        if selected_id is None:
            return
        obj = self.scene_model.get_object(selected_id)
        if not obj:
            return
        new_plat_id = self.obj_prop_platform_combo.currentData()
        if not new_plat_id or new_plat_id == obj.platform_id:
            return

        can_add, reason = self.scene_model.can_add_object_to_platform(new_plat_id, obj=obj, exclude_id=selected_id)
        if not can_add:
            QMessageBox.warning(
                self,
                "Object Limit Exceeded",
                f"Cannot move object to platform '{new_plat_id}':\n{reason}",
            )
            self._update_object_property_panel(obj)
            return

        cmd = UpdateSceneObjectPropsCommand(
            self.scene_model,
            selected_id,
            new_platform_id=new_plat_id,
            callback=lambda: self._on_object_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_obj_prop_x_changed(self) -> None:
        selected_id = self._get_effective_selected_object_id()
        if selected_id is None:
            return
        obj = self.scene_model.get_object(selected_id)
        if not obj:
            return
        new_x = self.obj_prop_x_spin.value()
        if new_x == obj.x:
            return
        cmd = MoveSceneObjectCommand(
            self.scene_model,
            selected_id,
            obj.x,
            new_x,
            callback=lambda: self._on_object_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_obj_prop_speed_changed(self) -> None:
        selected_id = self._get_effective_selected_object_id()
        if selected_id is None:
            return
        obj = self.scene_model.get_object(selected_id)
        if not obj or obj.type != OBJECT_TYPE_ENEMY:
            return
        new_spd = self.obj_prop_speed_combo.currentData()
        if not new_spd or new_spd == obj.speed:
            return
        cmd = UpdateSceneObjectPropsCommand(
            self.scene_model,
            selected_id,
            new_speed=new_spd,
            callback=lambda: self._on_object_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_obj_prop_strategy_changed(self) -> None:
        selected_id = self._get_effective_selected_object_id()
        if selected_id is None:
            return
        obj = self.scene_model.get_object(selected_id)
        if not obj or obj.type != OBJECT_TYPE_ENEMY:
            return
        new_strat = self.obj_prop_strategy_combo.currentData()
        if not new_strat or new_strat == obj.movement_strategy:
            return
        cmd = UpdateSceneObjectPropsCommand(
            self.scene_model,
            selected_id,
            new_strategy=new_strat,
            callback=lambda: self._on_object_command_executed(selected_id),
        )
        self.undo_stack.push(cmd)

    def _on_object_list_row_changed(self, row: int) -> None:
        if 0 <= row < len(self.scene_model.objects):
            obj = self.scene_model.objects[row]
            self.scene_view.select_object(obj.id)
            self._update_object_property_panel(obj)

    def _refresh_object_list(self, selected_id: Optional[str] = None) -> None:
        self.objects_list.blockSignals(True)
        self.objects_list.clear()

        selected_row = -1
        for idx, obj in enumerate(self.scene_model.objects):
            type_tag = "ENEMY" if obj.type == OBJECT_TYPE_ENEMY else "SECRET"
            defn = self.catalogues.get_definition(obj.type, obj.definition_id)
            defn_name = f" '{defn.name}'" if defn else f" [def: {obj.definition_id or 'None'}]"
            strat_info = f", {obj.movement_strategy}" if obj.movement_strategy else ""
            spd_info = f", {obj.speed}" if obj.speed else ""
            text = f"[{type_tag}]{defn_name} {obj.id} @ {obj.platform_id} (x={obj.x}{spd_info}{strat_info})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, obj.id)
            self.objects_list.addItem(item)
            if selected_id is not None and (obj.id == selected_id or str(obj.id) == str(selected_id)):
                selected_row = idx

        if selected_row >= 0:
            self.objects_list.setCurrentRow(selected_row)
        self.objects_list.blockSignals(False)

    def _refresh_object_creator_platforms(self) -> None:
        cur_id = self.new_obj_platform_combo.currentData()
        self.new_obj_platform_combo.blockSignals(True)
        self.new_obj_platform_combo.clear()

        for plat in self.scene_model.platforms:
            row_objs = len(self.scene_model.get_row_objects(plat.position.y))
            label = f"{plat.id} ({plat.type}, x={plat.position.x}, y={plat.position.y}) [Row {plat.row_index}: {row_objs}/{MAX_OBJECTS_PER_ROW} objs]"
            self.new_obj_platform_combo.addItem(label, plat.id)

        if cur_id:
            idx = self.new_obj_platform_combo.findData(cur_id)
            if idx >= 0:
                self.new_obj_platform_combo.setCurrentIndex(idx)
            elif self.new_obj_platform_combo.count() > 0:
                self.new_obj_platform_combo.setCurrentIndex(0)
        elif self.new_obj_platform_combo.count() > 0:
            self.new_obj_platform_combo.setCurrentIndex(0)
        self.new_obj_platform_combo.blockSignals(False)
        self._on_new_obj_platform_combo_changed()

    def _update_object_property_panel(self, obj: Optional[SceneObjectElement]) -> None:
        self.obj_elem_group.setEnabled(True)
        self.obj_prop_id_spin.setEnabled(True)
        self.obj_prop_type_combo.setEnabled(True)
        self.obj_prop_definition_combo.setEnabled(True)
        self.obj_prop_platform_combo.setEnabled(False)  # Read-only platform as requested
        self.obj_prop_x_spin.setEnabled(True)
        self.obj_prop_speed_combo.setEnabled(True)
        self.obj_prop_strategy_combo.setEnabled(True)
        self.btn_delete_obj.setEnabled(True)

        if obj is None:
            self.obj_prop_id_spin.blockSignals(True)
            self.obj_prop_id_spin.setValue(1)
            self.obj_prop_id_spin.blockSignals(False)

            self.obj_prop_type_combo.blockSignals(True)
            self.obj_prop_type_combo.setCurrentIndex(0)
            self.obj_prop_type_combo.blockSignals(False)

            self.obj_prop_definition_combo.blockSignals(True)
            self.obj_prop_definition_combo.clear()
            defs = self.catalogues.enemies
            for d_id, d_val in defs.items():
                self.obj_prop_definition_combo.addItem(f"{d_val.name} [{d_id}]", d_id)
            self.obj_prop_definition_combo.blockSignals(False)
            self.obj_prop_definition_info_lbl.setText("<small style='color: #888;'>No object selected on scene.</small>")

            self.obj_prop_platform_combo.blockSignals(True)
            self.obj_prop_platform_combo.clear()
            for plat in self.scene_model.platforms:
                self.obj_prop_platform_combo.addItem(plat.id, plat.id)
            self.obj_prop_platform_combo.blockSignals(False)

            self.obj_prop_x_spin.blockSignals(True)
            self.obj_prop_x_spin.setValue(0)
            self.obj_prop_x_spin.blockSignals(False)

            self.obj_prop_speed_lbl.setVisible(True)
            self.obj_prop_speed_combo.setVisible(True)
            self.obj_prop_strategy_lbl.setVisible(True)
            self.obj_prop_strategy_combo.setVisible(True)
            return

        self.obj_prop_id_spin.blockSignals(True)
        try:
            self.obj_prop_id_spin.setValue(int(str(obj.id).strip()))
        except (ValueError, TypeError):
            self.obj_prop_id_spin.setValue(1)
        self.obj_prop_id_spin.blockSignals(False)

        # Type combo
        self.obj_prop_type_combo.blockSignals(True)
        idx = self.obj_prop_type_combo.findData(obj.type)
        if idx >= 0:
            self.obj_prop_type_combo.setCurrentIndex(idx)
        self.obj_prop_type_combo.blockSignals(False)

        # Definition combo
        self.obj_prop_definition_combo.blockSignals(True)
        self.obj_prop_definition_combo.clear()
        defs = self.catalogues.enemies if obj.type == OBJECT_TYPE_ENEMY else self.catalogues.secrets
        found_def_idx = -1
        for idx_def, (d_id, d_val) in enumerate(defs.items()):
            self.obj_prop_definition_combo.addItem(f"{d_val.name} [{d_id}]", d_id)
            if d_id == obj.definition_id or str(d_id) == str(obj.definition_id):
                found_def_idx = idx_def

        if found_def_idx >= 0:
            self.obj_prop_definition_combo.setCurrentIndex(found_def_idx)
        else:
            self.obj_prop_definition_combo.addItem(f"MISSING: {obj.definition_id or 'None'}", obj.definition_id)
            self.obj_prop_definition_combo.setCurrentIndex(self.obj_prop_definition_combo.count() - 1)
        self.obj_prop_definition_combo.blockSignals(False)

        # Definition details / info
        defn = self.catalogues.get_definition(obj.type, obj.definition_id)
        if defn:
            atari_str = f"${defn.atari_color:02X}" if defn.atari_color is not None else "None"
            blink_str = "Yes" if defn.blink else "No"
            color_badge = ""
            if defn.rgb_color:
                r, g, b = defn.rgb_color
                color_badge = f"<span style='background-color: rgb({r},{g},{b}); border: 1px solid #aaa;'>&nbsp;&nbsp;&nbsp;&nbsp;</span> "
            self.obj_prop_definition_info_lbl.setText(
                f"<small>{color_badge}Atari: <code>{atari_str}</code> | Blink: {blink_str}</small>"
            )
        else:
            self.obj_prop_definition_info_lbl.setText("<small style='color: #ff5555;'>⚠ Definition not found in catalogue</small>")

        # Platform combo - read-only
        self.obj_prop_platform_combo.blockSignals(True)
        self.obj_prop_platform_combo.clear()
        for plat in self.scene_model.platforms:
            row_objs = len(self.scene_model.get_row_objects(plat.position.y))
            label = f"{plat.id} (x={plat.position.x}, y={plat.position.y}) [{row_objs}/{MAX_OBJECTS_PER_ROW} objs]"
            self.obj_prop_platform_combo.addItem(label, plat.id)
        idx = self.obj_prop_platform_combo.findData(obj.platform_id)
        if idx >= 0:
            self.obj_prop_platform_combo.setCurrentIndex(idx)
        else:
            self.obj_prop_platform_combo.addItem(f"INVALID: {obj.platform_id}", obj.platform_id)
            self.obj_prop_platform_combo.setCurrentIndex(self.obj_prop_platform_combo.count() - 1)
        self.obj_prop_platform_combo.blockSignals(False)

        # X position
        plat = self.scene_model.get_platform(obj.platform_id)
        self.obj_prop_x_spin.blockSignals(True)
        if plat:
            min_x = max(0, plat.position.x - obj.width + 1)
            max_x = min(self.scene_model.width - obj.width, plat.position.x + plat.width - 1)
            self.obj_prop_x_spin.setRange(min_x, max_x)
        self.obj_prop_x_spin.setValue(obj.x)
        self.obj_prop_x_spin.blockSignals(False)

        # Speed and Strategy
        is_enemy = (obj.type == OBJECT_TYPE_ENEMY)
        self.obj_prop_speed_lbl.setVisible(is_enemy)
        self.obj_prop_speed_combo.setVisible(is_enemy)
        self.obj_prop_strategy_lbl.setVisible(is_enemy)
        self.obj_prop_strategy_combo.setVisible(is_enemy)

        if is_enemy:
            self.obj_prop_speed_combo.blockSignals(True)
            s_idx = self.obj_prop_speed_combo.findData(obj.speed)
            if s_idx >= 0:
                self.obj_prop_speed_combo.setCurrentIndex(s_idx)
            self.obj_prop_speed_combo.blockSignals(False)

            self.obj_prop_strategy_combo.blockSignals(True)
            st_idx = self.obj_prop_strategy_combo.findData(obj.movement_strategy)
            if st_idx >= 0:
                self.obj_prop_strategy_combo.setCurrentIndex(st_idx)
            self.obj_prop_strategy_combo.blockSignals(False)

    def bring_to_front_selected(self) -> None:
        selected_id = self.scene_view.get_selected_element_id()
        if not selected_id:
            return
        old_idx = self.scene_model.get_element_index(selected_id)
        new_idx = len(self.scene_model.elements) - 1
        if old_idx != new_idx:
            cmd = ReorderElementCommand(
                self.scene_model,
                selected_id,
                new_idx,
                callback=lambda: self._on_command_executed(selected_id),
            )
            self.undo_stack.push(cmd)

    def send_to_back_selected(self) -> None:
        selected_id = self.scene_view.get_selected_element_id()
        if not selected_id:
            return
        old_idx = self.scene_model.get_element_index(selected_id)
        if old_idx != 0:
            cmd = ReorderElementCommand(
                self.scene_model,
                selected_id,
                0,
                callback=lambda: self._on_command_executed(selected_id),
            )
            self.undo_stack.push(cmd)

    def raise_selected(self) -> None:
        selected_id = self.scene_view.get_selected_element_id()
        if not selected_id:
            return
        old_idx = self.scene_model.get_element_index(selected_id)
        if old_idx < len(self.scene_model.elements) - 1:
            cmd = ReorderElementCommand(
                self.scene_model,
                selected_id,
                old_idx + 1,
                callback=lambda: self._on_command_executed(selected_id),
            )
            self.undo_stack.push(cmd)

    def lower_selected(self) -> None:
        selected_id = self.scene_view.get_selected_element_id()
        if not selected_id:
            return
        old_idx = self.scene_model.get_element_index(selected_id)
        if old_idx > 0:
            cmd = ReorderElementCommand(
                self.scene_model,
                selected_id,
                old_idx - 1,
                callback=lambda: self._on_command_executed(selected_id),
            )
            self.undo_stack.push(cmd)

    def _on_layer_row_changed(self, row: int) -> None:
        if 0 <= row < len(self.scene_model.elements):
            elem = self.scene_model.elements[row]
            self.scene_view.select_element(elem.id)
            self._update_property_panel(elem)

    def _on_scene_name_edited(self) -> None:
        name = self.scene_name_edit.text().strip()
        if name:
            self.scene_model.name = name
            self._is_dirty = True
            self._update_window_title()

    def _on_cursor_coords_changed(self, x: int, y: int) -> None:
        self.status_cursor_lbl.setText(f"Cursor: ({x}, {y})")

    def _on_zoom_in(self) -> None:
        self.scene_view.zoom_in()
        factor = self.scene_view.ZOOM_LEVELS[self.scene_view.zoom_index]
        self.status_zoom_lbl.setText(f"Zoom: {int(factor)}x")

    def _on_zoom_out(self) -> None:
        self.scene_view.zoom_out()
        factor = self.scene_view.ZOOM_LEVELS[self.scene_view.zoom_index]
        self.status_zoom_lbl.setText(f"Zoom: {int(factor)}x")
