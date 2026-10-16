"""Dialog for managing project-wide Enemies and Secrets catalogues."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .atari_palette import (
    atari_color_to_hex_rgb,
    atari_color_to_rgb,
    format_atari_color_hex,
    is_valid_atari_color_string,
    parse_atari_color_hex,
)
from .catalogue_model import (
    DuplicateDefinitionIdError,
    EnemyDefinition,
    InvalidDefinitionError,
    PlatformColorProfile,
    ProfileInUseError,
    ProjectCatalogues,
    SecretDefinition,
)
from .scene_model import OBJECT_TYPE_ENEMY, OBJECT_TYPE_SECRET, Scene


class PlatformPreviewBar(QWidget):
    """Widget rendering an 8-scanline gradient bar representing the platform color profile."""

    def __init__(self, colors: Optional[list[int]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.colors = list(colors) if colors else [0x80] * 8
        self.setFixedHeight(30)
        self.setMinimumWidth(160)

    def set_colors(self, colors: list[int]) -> None:
        self.colors = list(colors)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = self.rect()
        w = rect.width()
        h = rect.height()
        if not self.colors:
            return
        num_lines = len(self.colors)
        line_h = h / num_lines
        for idx, col_val in enumerate(self.colors):
            rgb = atari_color_to_rgb(col_val)
            y_start = int(idx * line_h)
            y_end = int((idx + 1) * line_h) if idx < num_lines - 1 else h
            painter.fillRect(0, y_start, w, y_end - y_start, QColor(*rgb))

        # Border
        painter.setPen(QColor(80, 80, 80))
        painter.drawRect(0, 0, w - 1, h - 1)


class CataloguesDialog(QDialog):
    """Dialog allowing users to browse, create, edit, and delete catalogue entries for Enemies, Secrets, and Platform Profiles."""

    catalogues_changed = Signal()

    def __init__(
        self,
        catalogues: ProjectCatalogues,
        scene: Optional[Scene] = None,
        base_dir: Optional[Path | str] = None,
        parent: Optional[QWidget] = None,
        initial_tab: str = "enemies",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project Catalogues (Enemies, Secrets & Platform Profiles)")
        self.resize(800, 560)
        self.setModal(True)

        self.catalogues = catalogues
        self.scene = scene
        self.base_dir = Path(base_dir).resolve() if base_dir else None

        self._build_ui()
        if initial_tab in ("secrets", "secret"):
            self.tabs.setCurrentIndex(1)
        elif initial_tab in ("platforms", "platform", "profiles", "profile", "platform_profiles"):
            self.tabs.setCurrentIndex(2)
        else:
            self.tabs.setCurrentIndex(0)

        self._refresh_enemies_list()
        self._refresh_secrets_list()
        self._refresh_profiles_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.tabs = QTabWidget(self)

        # Tab 1: Enemies
        enemies_widget = self._create_catalogue_tab(is_enemy=True)
        self.tabs.addTab(enemies_widget, "Enemies")

        # Tab 2: Secrets
        secrets_widget = self._create_catalogue_tab(is_enemy=False)
        self.tabs.addTab(secrets_widget, "Secrets")

        # Tab 3: Platform Profiles
        profiles_widget = self._create_platform_profiles_tab()
        self.tabs.addTab(profiles_widget, "Platform Profiles")

        layout.addWidget(self.tabs, stretch=1)

        # Bottom buttons (Load JSON, Save JSON, Close)
        btn_bar = QHBoxLayout()
        btn_load_json = QPushButton("📂 Load JSON...")
        btn_load_json.setToolTip("Import enemy or secret definitions from a JSON file")
        btn_load_json.clicked.connect(self._on_load_json_clicked)
        btn_bar.addWidget(btn_load_json)

        btn_save_json = QPushButton("💾 Save JSON")
        btn_save_json.setToolTip("Save catalogues to default or configured JSON files")
        btn_save_json.clicked.connect(self._on_save_json_clicked)
        btn_bar.addWidget(btn_save_json)

        btn_paths = QPushButton("⚙ Configure Paths...")
        btn_paths.setToolTip("Configure default file paths for enemies.json and secrets.json")
        btn_paths.clicked.connect(self._on_configure_paths_clicked)
        btn_bar.addWidget(btn_paths)

        btn_load_sprites = QPushButton("👾 Load Sprites...")
        btn_load_sprites.setToolTip("Import sprite definitions from Sprite Studio JSON file (*.sprite.json)")
        btn_load_sprites.clicked.connect(self._on_load_sprites_clicked)
        btn_bar.addWidget(btn_load_sprites)

        btn_bar.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.setDefault(False)
        btn_close.clicked.connect(self.accept)
        btn_bar.addWidget(btn_close)

        layout.addLayout(btn_bar)

    def _create_catalogue_tab(self, is_enemy: bool) -> QWidget:
        widget = QWidget()
        h_layout = QHBoxLayout(widget)
        h_layout.setContentsMargins(6, 6, 6, 6)
        h_layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: List & New button
        left_pane = QWidget()
        lp_layout = QVBoxLayout(left_pane)
        lp_layout.setContentsMargins(0, 0, 0, 0)
        lp_layout.setSpacing(6)

        list_widget = QListWidget()
        btn_new = QPushButton("+ New Entry (Nowy wpis)")

        lp_layout.addWidget(list_widget, stretch=1)
        lp_layout.addWidget(btn_new)
        splitter.addWidget(left_pane)

        # Right: Detail / Edit Form
        right_pane = QWidget()
        rp_layout = QVBoxLayout(right_pane)
        rp_layout.setContentsMargins(0, 0, 0, 0)
        rp_layout.setSpacing(6)

        group_title = "Enemy Details" if is_enemy else "Secret Details"
        form_group = QGroupBox(group_title)
        form_layout = QFormLayout(form_group)

        id_spin = QSpinBox()
        id_spin.setRange(1, 255)
        form_layout.addRow("ID (unique identifier 1-255):", id_spin)

        name_edit = QLineEdit()
        form_layout.addRow("Name:", name_edit)

        # RGB Color controls
        rgb_check = QCheckBox("Enable RGB Color")
        form_layout.addRow("", rgb_check)

        rgb_controls = QWidget()
        rgb_layout = QHBoxLayout(rgb_controls)
        rgb_layout.setContentsMargins(0, 0, 0, 0)
        rgb_layout.setSpacing(4)

        r_spin = QSpinBox()
        r_spin.setRange(0, 255)
        r_spin.setPrefix("R: ")
        g_spin = QSpinBox()
        g_spin.setRange(0, 255)
        g_spin.setPrefix("G: ")
        b_spin = QSpinBox()
        b_spin.setRange(0, 255)
        b_spin.setPrefix("B: ")

        swatch_btn = QPushButton()
        swatch_btn.setFixedSize(36, 24)
        swatch_btn.setToolTip("Click to pick color with ColorDialog")

        rgb_layout.addWidget(r_spin)
        rgb_layout.addWidget(g_spin)
        rgb_layout.addWidget(b_spin)
        rgb_layout.addWidget(swatch_btn)
        form_layout.addRow("RGB (0-255):", rgb_controls)

        # Atari Color controls
        atari_check = QCheckBox("Enable Atari Color (GTIA)")
        form_layout.addRow("", atari_check)

        atari_controls = QWidget()
        ac_layout = QHBoxLayout(atari_controls)
        ac_layout.setContentsMargins(0, 0, 0, 0)
        ac_layout.setSpacing(6)

        atari_spin = QSpinBox()
        atari_spin.setRange(0, 255)
        atari_hex_lbl = QLabel("Hex: $00")
        ac_layout.addWidget(atari_spin)
        ac_layout.addWidget(atari_hex_lbl)
        ac_layout.addStretch()
        form_layout.addRow("Atari GTIA Color (0-255 / $00-$FF):", atari_controls)

        # Blink option
        blink_check = QCheckBox("Blink (cycle luminance)")
        form_layout.addRow("", blink_check)

        # Sprite mapping option (from Sprite Studio)
        sprite_combo = QComboBox()
        sprite_combo.setToolTip("Select a sprite from Sprite Studio to map with this entry. Enabled when sprites are loaded.")
        sprite_combo.setEnabled(False)
        form_layout.addRow("Sprite (Sprite Studio):", sprite_combo)

        dep_combo = None
        stage_lbl = None
        if not is_enemy:
            dep_combo = QComboBox()
            dep_combo.setToolTip("Select prerequisite secret type. 'None' means this secret is available from the start of the scene.")
            form_layout.addRow("Dependency (Zależność):", dep_combo)

            stage_lbl = QLabel("Available from the start of the scene")
            stage_lbl.setStyleSheet("font-weight: bold; color: #4CAF50;")
            form_layout.addRow("Unlock Condition (Warunek):", stage_lbl)

        rp_layout.addWidget(form_group)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Update Entry")
        btn_save.setDefault(True)
        btn_delete = QPushButton("Delete Entry")
        btn_delete.setStyleSheet("color: #ff5555;")
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_delete)
        rp_layout.addLayout(btn_layout)
        rp_layout.addStretch(1)

        splitter.addWidget(right_pane)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        h_layout.addWidget(splitter)

        # Store widgets in self
        if is_enemy:
            self.enemy_list = list_widget
            self.enemy_btn_new = btn_new
            self.enemy_id_spin = id_spin
            self.enemy_id_edit = id_spin
            self.enemy_name_edit = name_edit
            self.enemy_rgb_check = rgb_check
            self.enemy_r_spin = r_spin
            self.enemy_g_spin = g_spin
            self.enemy_b_spin = b_spin
            self.enemy_swatch_btn = swatch_btn
            self.enemy_atari_check = atari_check
            self.enemy_atari_spin = atari_spin
            self.enemy_atari_hex_lbl = atari_hex_lbl
            self.enemy_blink_check = blink_check
            self.enemy_sprite_combo = sprite_combo
            self.enemy_btn_save = btn_save
            self.enemy_btn_delete = btn_delete
            self._cur_editing_enemy_id: Optional[int] = None

            # Connect signals
            list_widget.currentRowChanged.connect(self._on_enemy_selected)
            btn_new.clicked.connect(self._on_new_enemy_clicked)
            btn_save.clicked.connect(self._on_save_enemy_clicked)
            btn_delete.clicked.connect(self._on_delete_enemy_clicked)
            rgb_check.toggled.connect(lambda chk: self._update_rgb_enabled(True, chk))
            atari_check.toggled.connect(lambda chk: self._update_atari_enabled(True, chk))
            atari_spin.valueChanged.connect(lambda val: atari_hex_lbl.setText(f"Hex: ${val:02X}"))
            swatch_btn.clicked.connect(lambda: self._on_pick_color(True))
            r_spin.valueChanged.connect(lambda: self._update_swatch_color(True))
            g_spin.valueChanged.connect(lambda: self._update_swatch_color(True))
            b_spin.valueChanged.connect(lambda: self._update_swatch_color(True))
        else:
            self.secret_list = list_widget
            self.secret_btn_new = btn_new
            self.secret_id_spin = id_spin
            self.secret_id_edit = id_spin
            self.secret_name_edit = name_edit
            self.secret_rgb_check = rgb_check
            self.secret_r_spin = r_spin
            self.secret_g_spin = g_spin
            self.secret_b_spin = b_spin
            self.secret_swatch_btn = swatch_btn
            self.secret_atari_check = atari_check
            self.secret_atari_spin = atari_spin
            self.secret_atari_hex_lbl = atari_hex_lbl
            self.secret_blink_check = blink_check
            self.secret_sprite_combo = sprite_combo
            self.secret_dep_combo = dep_combo
            self.secret_stage_lbl = stage_lbl
            self.secret_btn_save = btn_save
            self.secret_btn_delete = btn_delete
            self._cur_editing_secret_id: Optional[int] = None

            # Connect signals
            list_widget.currentRowChanged.connect(self._on_secret_selected)
            btn_new.clicked.connect(self._on_new_secret_clicked)
            btn_save.clicked.connect(self._on_save_secret_clicked)
            btn_delete.clicked.connect(self._on_delete_secret_clicked)
            rgb_check.toggled.connect(lambda chk: self._update_rgb_enabled(False, chk))
            atari_check.toggled.connect(lambda chk: self._update_atari_enabled(False, chk))
            atari_spin.valueChanged.connect(lambda val: atari_hex_lbl.setText(f"Hex: ${val:02X}"))
            swatch_btn.clicked.connect(lambda: self._on_pick_color(False))
            r_spin.valueChanged.connect(lambda: self._update_swatch_color(False))
            g_spin.valueChanged.connect(lambda: self._update_swatch_color(False))
            b_spin.valueChanged.connect(lambda: self._update_swatch_color(False))
            if dep_combo:
                dep_combo.currentIndexChanged.connect(self._on_secret_dependency_changed)

        return widget

    # -------------------------------------------------------------------------
    # Sprites Mapping Helpers
    # -------------------------------------------------------------------------
    def _populate_sprite_combo(self, combo: Optional[QComboBox], current_sprite_id: Optional[int]) -> None:
        if combo is None:
            return
        combo.blockSignals(True)
        combo.clear()

        has_sprites = bool(self.catalogues and self.catalogues.sprites)
        combo.setEnabled(has_sprites)

        if not has_sprites:
            if current_sprite_id is not None:
                combo.addItem(f"Sprite ID {current_sprite_id} (definicje nie załadowane)", current_sprite_id)
            else:
                combo.addItem("Brak (definicje sprite'ów nie załadowane)", None)
            combo.setCurrentIndex(0)
            combo.setToolTip("Combobox jest wyłączony (disabled), ponieważ nie załadowano definicji sprite'ów z pliku JSON.")
            combo.blockSignals(False)
            return

        combo.setToolTip("Wybierz sprite ze Sprite Studio do zmapowania z tym wpisem.")
        combo.addItem("None (Brak)", None)

        for s_id in sorted(self.catalogues.sprites.keys()):
            spr = self.catalogues.sprites[s_id]
            desc = getattr(spr, "description", "")
            label = f"{spr.id}: {desc}" if desc else f"Sprite {spr.id}"
            combo.addItem(label, spr.id)

        if current_sprite_id is None:
            combo.setCurrentIndex(0)
        else:
            idx = combo.findData(current_sprite_id)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.addItem(f"Sprite ID {current_sprite_id}", current_sprite_id)
                combo.setCurrentIndex(combo.count() - 1)

        combo.blockSignals(False)

    def _on_load_sprites_clicked(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open Sprite Studio JSON File",
            str(self.base_dir / "sprites") if (self.base_dir / "sprites").is_dir() else str(self.base_dir),
            "Sprite JSON (*.sprite.json *.json);;All Files (*)",
        )
        if not path_str:
            return

        try:
            count = self.catalogues.load_sprites_from_json(Path(path_str))
            cur_enemy_sprite = None
            if self._cur_editing_enemy_id and self._cur_editing_enemy_id in self.catalogues.enemies:
                cur_enemy_sprite = getattr(self.catalogues.enemies[self._cur_editing_enemy_id], "sprite_id", None)
            self._populate_sprite_combo(self.enemy_sprite_combo, cur_enemy_sprite)

            cur_secret_sprite = None
            if self._cur_editing_secret_id and self._cur_editing_secret_id in self.catalogues.secrets:
                cur_secret_sprite = getattr(self.catalogues.secrets[self._cur_editing_secret_id], "sprite_id", None)
            self._populate_sprite_combo(self.secret_sprite_combo, cur_secret_sprite)

            self._refresh_enemies_list(select_id=self._cur_editing_enemy_id)
            self._refresh_secrets_list(select_id=self._cur_editing_secret_id)

            QMessageBox.information(
                self,
                "Sprites Loaded",
                f"Successfully loaded {count} sprite(s) from:\n{Path(path_str).name}",
            )
        except Exception as err:
            QMessageBox.critical(self, "Load Error", f"Failed to load sprite definitions:\n{err}")

    # -------------------------------------------------------------------------
    # Enemies Handlers
    # -------------------------------------------------------------------------
    def _refresh_enemies_list(self, select_id: Optional[str] = None) -> None:
        self.enemy_list.blockSignals(True)
        self.enemy_list.clear()

        row_to_select = -1
        for idx, (defn_id, defn) in enumerate(self.catalogues.enemies.items()):
            text = f"{defn.name} [{defn.id}]"
            if getattr(defn, "sprite_id", None) is not None:
                text += f" [Sprite: {defn.sprite_id}]"
            if defn.atari_color is not None:
                text += f" (Atari: ${defn.atari_color:02X})"
            if defn.blink:
                text += " [BLINK]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, defn.id)

            if defn.rgb_color is not None:
                pm = QPixmap(12, 12)
                pm.fill(QColor(*defn.rgb_color))
                item.setIcon(QIcon(pm))

            self.enemy_list.addItem(item)
            if defn_id == select_id:
                row_to_select = idx

        self.enemy_list.blockSignals(False)

        if row_to_select >= 0:
            self.enemy_list.setCurrentRow(row_to_select)
        elif self.enemy_list.count() > 0:
            self.enemy_list.setCurrentRow(0)
        else:
            self._on_new_enemy_clicked()

    def _on_enemy_selected(self, row: int) -> None:
        if row < 0 or row >= self.enemy_list.count():
            return
        item = self.enemy_list.item(row)
        defn_id = item.data(Qt.ItemDataRole.UserRole)
        defn = self.catalogues.get_enemy(defn_id)
        if not defn:
            return

        self._cur_editing_enemy_id = defn.id
        self.enemy_id_spin.setValue(int(defn.id))
        self.enemy_name_edit.setText(defn.name)
        self.enemy_btn_save.setText("Update Entry")

        if defn.rgb_color is not None:
            self.enemy_rgb_check.setChecked(True)
            self.enemy_r_spin.setValue(defn.rgb_color[0])
            self.enemy_g_spin.setValue(defn.rgb_color[1])
            self.enemy_b_spin.setValue(defn.rgb_color[2])
            self._update_swatch_color(True)
        else:
            self.enemy_rgb_check.setChecked(False)
            self._update_rgb_enabled(True, False)

        if defn.atari_color is not None:
            self.enemy_atari_check.setChecked(True)
            self.enemy_atari_spin.setValue(defn.atari_color)
            self.enemy_atari_hex_lbl.setText(f"Hex: ${defn.atari_color:02X}")
        else:
            self.enemy_atari_check.setChecked(False)
            self._update_atari_enabled(True, False)

        self.enemy_blink_check.setChecked(defn.blink)
        self._populate_sprite_combo(getattr(self, "enemy_sprite_combo", None), getattr(defn, "sprite_id", None))
        self.enemy_btn_delete.setEnabled(True)

    def _on_new_enemy_clicked(self) -> None:
        self._cur_editing_enemy_id = None
        self.enemy_list.blockSignals(True)
        self.enemy_list.clearSelection()
        self.enemy_list.setCurrentRow(-1)
        self.enemy_list.blockSignals(False)

        # Suggest next unused integer ID in 1-255
        used = set(self.catalogues.enemies.keys())
        suggested_id = 1
        for i in range(1, 256):
            if i not in used:
                suggested_id = i
                break

        self.enemy_id_spin.setValue(suggested_id)
        self.enemy_name_edit.setText(f"New Enemy {suggested_id}")
        self.enemy_btn_save.setText("Add Entry")
        self.enemy_rgb_check.setChecked(True)
        self.enemy_r_spin.setValue(220)
        self.enemy_g_spin.setValue(50)
        self.enemy_b_spin.setValue(50)
        self._update_swatch_color(True)
        self.enemy_atari_check.setChecked(False)
        self._update_atari_enabled(True, False)
        self.enemy_blink_check.setChecked(False)
        self._populate_sprite_combo(getattr(self, "enemy_sprite_combo", None), None)
        self.enemy_btn_delete.setEnabled(False)

    def _on_save_enemy_clicked(self) -> None:
        defn_id = self.enemy_id_spin.value()
        name = self.enemy_name_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Invalid Input", "Name cannot be empty.")
            return

        rgb = None
        if self.enemy_rgb_check.isChecked():
            rgb = (
                self.enemy_r_spin.value(),
                self.enemy_g_spin.value(),
                self.enemy_b_spin.value(),
            )

        atari = None
        if self.enemy_atari_check.isChecked():
            atari = self.enemy_atari_spin.value()

        blink = self.enemy_blink_check.isChecked()
        sprite_id = self.enemy_sprite_combo.currentData() if hasattr(self, "enemy_sprite_combo") and self.enemy_sprite_combo else None

        try:
            defn = EnemyDefinition(
                id=defn_id,
                name=name,
                rgb_color=rgb,
                atari_color=atari,
                blink=blink,
                sprite_id=sprite_id,
            )
            defn.validate()

            if self._cur_editing_enemy_id is None:
                self.catalogues.add_enemy(defn)
            else:
                self.catalogues.update_enemy(self._cur_editing_enemy_id, defn)
                if self.scene and self._cur_editing_enemy_id != defn.id:
                    for obj in self.scene.objects:
                        if obj.type == OBJECT_TYPE_ENEMY and (obj.definition_id == self._cur_editing_enemy_id or str(obj.definition_id) == str(self._cur_editing_enemy_id)):
                            obj.definition_id = defn.id

            # Persist atomically
            self.catalogues.save_to_dir(self.base_dir)
            self._refresh_enemies_list(select_id=defn.id)
            self.enemy_btn_save.setText("Update Entry")
            self.catalogues_changed.emit()

        except DuplicateDefinitionIdError as err:
            QMessageBox.warning(self, "Duplicate ID", str(err))
        except InvalidDefinitionError as err:
            QMessageBox.warning(self, "Validation Error", str(err))
        except Exception as err:
            QMessageBox.critical(self, "Error Saving", f"Could not save definition: {err}")

    def _on_delete_enemy_clicked(self) -> None:
        if not self._cur_editing_enemy_id:
            return

        target_id = self._cur_editing_enemy_id

        # Safety check: is this definition used by any scene object?
        used_count = sum(
            1 for obj in self.scene.objects
            if obj.type == OBJECT_TYPE_ENEMY and (obj.definition_id == target_id or str(obj.definition_id) == str(target_id))
        )
        if used_count > 0:
            QMessageBox.warning(
                self,
                "Cannot Delete Definition",
                f"Cannot delete enemy definition '{target_id}':\n"
                f"It is currently assigned to {used_count} object(s) on the current scene.\n\n"
                f"Please reassign or delete those objects before removing this definition.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete enemy definition '{target_id}' from the catalogue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self.catalogues.remove_enemy(target_id)
            self.catalogues.save_to_dir(self.base_dir)
            self._refresh_enemies_list()
            self.catalogues_changed.emit()
        except Exception as err:
            QMessageBox.critical(self, "Delete Error", str(err))

    # -------------------------------------------------------------------------
    # Secrets Handlers
    # -------------------------------------------------------------------------
    def _refresh_secrets_list(self, select_id: Optional[str] = None) -> None:
        self.secret_list.blockSignals(True)
        self.secret_list.clear()

        row_to_select = -1
        for idx, (defn_id, defn) in enumerate(self.catalogues.secrets.items()):
            text = f"{defn.name} [{defn.id}]"
            if getattr(defn, "sprite_id", None) is not None:
                text += f" [Sprite: {defn.sprite_id}]"
            if defn.dependency is not None:
                parent = self.catalogues.get_secret(defn.dependency)
                p_name = parent.name if parent else f"ID {defn.dependency}"
                text += f" (requires: {p_name})"
            else:
                text += " (from start)"
            if defn.atari_color is not None:
                text += f" (Atari: ${defn.atari_color:02X})"
            if defn.blink:
                text += " [BLINK]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, defn.id)

            if defn.rgb_color is not None:
                pm = QPixmap(12, 12)
                pm.fill(QColor(*defn.rgb_color))
                item.setIcon(QIcon(pm))

            self.secret_list.addItem(item)
            if defn_id == select_id:
                row_to_select = idx

        self.secret_list.blockSignals(False)

        if row_to_select >= 0:
            self.secret_list.setCurrentRow(row_to_select)
        elif self.secret_list.count() > 0:
            self.secret_list.setCurrentRow(0)
        else:
            self._on_new_secret_clicked()

    def _on_secret_dependency_changed(self) -> None:
        if not hasattr(self, "secret_dep_combo") or not self.secret_dep_combo:
            return
        dep_id = self.secret_dep_combo.currentData()
        if dep_id is None:
            self.secret_stage_lbl.setText("Available from the start of the scene (no dependency)")
            self.secret_stage_lbl.setStyleSheet("font-weight: bold; color: #4CAF50;")
        else:
            parent = self.catalogues.get_secret(dep_id)
            p_name = parent.name if parent else f"ID {dep_id}"
            self.secret_stage_lbl.setText(f"Unlocks after collecting all '{p_name}' secrets on the scene")
            self.secret_stage_lbl.setStyleSheet("font-weight: bold; color: #2196F3;")

    def _populate_secret_dependency_options(self, target_id: Optional[int], current_dep: Optional[int]) -> None:
        if not hasattr(self, "secret_dep_combo") or not self.secret_dep_combo:
            return
        self.secret_dep_combo.blockSignals(True)
        self.secret_dep_combo.clear()

        # Item 0: No dependency
        self.secret_dep_combo.addItem("None (dostępny od początku sceny)", None)

        valid_deps = self.catalogues.get_valid_dependencies_for(target_id)
        valid_ids = {d.id for d in valid_deps}

        # Keep current selection visible if already assigned
        if current_dep is not None and current_dep not in valid_ids:
            cur_defn = self.catalogues.get_secret(current_dep)
            if cur_defn:
                valid_deps.insert(0, cur_defn)
                valid_ids.add(current_dep)

        for d in valid_deps:
            self.secret_dep_combo.addItem(f"{d.name} [ID: {d.id}]", d.id)

        if current_dep is None:
            self.secret_dep_combo.setCurrentIndex(0)
        else:
            idx = self.secret_dep_combo.findData(current_dep)
            if idx >= 0:
                self.secret_dep_combo.setCurrentIndex(idx)
            else:
                self.secret_dep_combo.addItem(f"Secret ID {current_dep}", current_dep)
                self.secret_dep_combo.setCurrentIndex(self.secret_dep_combo.count() - 1)

        self.secret_dep_combo.blockSignals(False)
        self._on_secret_dependency_changed()

    def _on_secret_selected(self, row: int) -> None:
        if row < 0 or row >= self.secret_list.count():
            return
        item = self.secret_list.item(row)
        defn_id = item.data(Qt.ItemDataRole.UserRole)
        defn = self.catalogues.get_secret(defn_id)
        if not defn:
            return

        self._cur_editing_secret_id = defn.id
        self.secret_id_spin.setValue(int(defn.id))
        self.secret_name_edit.setText(defn.name)
        self.secret_btn_save.setText("Update Entry")

        if defn.rgb_color is not None:
            self.secret_rgb_check.setChecked(True)
            self.secret_r_spin.setValue(defn.rgb_color[0])
            self.secret_g_spin.setValue(defn.rgb_color[1])
            self.secret_b_spin.setValue(defn.rgb_color[2])
            self._update_swatch_color(False)
        else:
            self.secret_rgb_check.setChecked(False)
            self._update_rgb_enabled(False, False)

        if defn.atari_color is not None:
            self.secret_atari_check.setChecked(True)
            self.secret_atari_spin.setValue(defn.atari_color)
            self.secret_atari_hex_lbl.setText(f"Hex: ${defn.atari_color:02X}")
        else:
            self.secret_atari_check.setChecked(False)
            self._update_atari_enabled(False, False)

        self.secret_blink_check.setChecked(defn.blink)
        self._populate_secret_dependency_options(defn.id, defn.dependency)
        self._populate_sprite_combo(getattr(self, "secret_sprite_combo", None), getattr(defn, "sprite_id", None))
        self.secret_btn_delete.setEnabled(True)

    def _on_new_secret_clicked(self) -> None:
        self._cur_editing_secret_id = None
        self.secret_list.blockSignals(True)
        self.secret_list.clearSelection()
        self.secret_list.setCurrentRow(-1)
        self.secret_list.blockSignals(False)

        used = set(self.catalogues.secrets.keys())
        suggested_id = 1
        for i in range(1, 256):
            if i not in used:
                suggested_id = i
                break

        self.secret_id_spin.setValue(suggested_id)
        self.secret_name_edit.setText(f"New Secret {suggested_id}")
        self.secret_btn_save.setText("Add Entry")
        self.secret_rgb_check.setChecked(True)
        self.secret_r_spin.setValue(255)
        self.secret_g_spin.setValue(215)
        self.secret_b_spin.setValue(0)
        self._update_swatch_color(False)
        self.secret_atari_check.setChecked(False)
        self._update_atari_enabled(False, False)
        self.secret_blink_check.setChecked(False)
        self._populate_secret_dependency_options(None, None)
        self._populate_sprite_combo(getattr(self, "secret_sprite_combo", None), None)
        self.secret_btn_delete.setEnabled(False)

    def _on_save_secret_clicked(self) -> None:
        defn_id = self.secret_id_spin.value()
        name = self.secret_name_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Invalid Input", "Name cannot be empty.")
            return

        rgb = None
        if self.secret_rgb_check.isChecked():
            rgb = (
                self.secret_r_spin.value(),
                self.secret_g_spin.value(),
                self.secret_b_spin.value(),
            )

        atari = None
        if self.secret_atari_check.isChecked():
            atari = self.secret_atari_spin.value()

        blink = self.secret_blink_check.isChecked()
        dependency = self.secret_dep_combo.currentData() if hasattr(self, "secret_dep_combo") and self.secret_dep_combo else None
        sprite_id = self.secret_sprite_combo.currentData() if hasattr(self, "secret_sprite_combo") and self.secret_sprite_combo else None

        try:
            defn = SecretDefinition(
                id=defn_id,
                name=name,
                rgb_color=rgb,
                atari_color=atari,
                blink=blink,
                dependency=dependency,
                sprite_id=sprite_id,
            )
            defn.validate()

            if self._cur_editing_secret_id is not None and self.scene:
                ok, msg = self.catalogues.check_scene_secret_dependency_conflict(
                    self.scene,
                    self._cur_editing_secret_id,
                    dependency,
                )
                if not ok:
                    QMessageBox.warning(self, "Secret Dependency Conflict", msg)
                    return

            if self._cur_editing_secret_id is None:
                self.catalogues.add_secret(defn)
            else:
                self.catalogues.update_secret(self._cur_editing_secret_id, defn)
                if self.scene and self._cur_editing_secret_id != defn.id:
                    for obj in self.scene.objects:
                        if obj.type in (OBJECT_TYPE_SECRET, "treasure") and (obj.definition_id == self._cur_editing_secret_id or str(obj.definition_id) == str(self._cur_editing_secret_id)):
                            obj.definition_id = defn.id

            self.catalogues.save_to_dir(self.base_dir)
            self._refresh_secrets_list(select_id=defn.id)
            self.secret_btn_save.setText("Update Entry")
            self.catalogues_changed.emit()

        except DuplicateDefinitionIdError as err:
            QMessageBox.warning(self, "Duplicate ID", str(err))
        except InvalidDefinitionError as err:
            QMessageBox.warning(self, "Validation Error", str(err))
        except Exception as err:
            QMessageBox.critical(self, "Error Saving", f"Could not save definition: {err}")

    def _on_delete_secret_clicked(self) -> None:
        if not self._cur_editing_secret_id:
            return

        target_id = self._cur_editing_secret_id

        # Safety check 1: is this definition used by any scene object?
        used_count = sum(
            1 for obj in self.scene.objects
            if obj.type in (OBJECT_TYPE_SECRET, "treasure") and (obj.definition_id == target_id or str(obj.definition_id) == str(target_id))
        )
        if used_count > 0:
            QMessageBox.warning(
                self,
                "Cannot Delete Definition",
                f"Cannot delete secret definition '{target_id}':\n"
                f"It is currently assigned to {used_count} object(s) on the current scene.\n\n"
                f"Please reassign or delete those objects before removing this definition.",
            )
            return

        # Safety check 2: does any other secret depend on this secret in the chain?
        dependents = [s for s in self.catalogues.secrets.values() if s.dependency == target_id]
        if dependents:
            dep_names = ", ".join(f"'{s.name}' [{s.id}]" for s in dependents)
            QMessageBox.warning(
                self,
                "Cannot Delete Definition",
                f"Cannot delete secret definition '{target_id}':\n"
                f"The following secret(s) in the dependency chain depend on it:\n{dep_names}\n\n"
                f"Please reassign or remove dependencies before deleting this definition.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete secret definition '{target_id}' from the catalogue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self.catalogues.remove_secret(target_id)
            self.catalogues.save_to_dir(self.base_dir)
            self._refresh_secrets_list()
            self.catalogues_changed.emit()
        except Exception as err:
            QMessageBox.critical(self, "Delete Error", str(err))

    def _on_load_json_clicked(self) -> None:
        start_dir = str(self.base_dir) if self.base_dir else "."
        file_path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Load Catalogue JSON File",
            start_dir,
            "Catalogue JSON (*.json);;All Files (*)",
        )
        if not file_path_str:
            return

        file_path = Path(file_path_str)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as err:
            QMessageBox.critical(self, "Load Error", f"Failed to parse JSON file:\n{err}")
            return

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
                if "profiles" in data and isinstance(data["profiles"], list):
                    for item in data["profiles"]:
                        prof = PlatformColorProfile.from_dict(item)
                        self.catalogues.platform_profiles[prof.id] = prof
                        profiles_count += 1
                if "enemies" not in data and "secrets" not in data and "profiles" not in data:
                    if "id" in data and "name" in data:
                        if self.tabs.currentIndex() == 0:
                            defn = EnemyDefinition.from_dict(data)
                            self.catalogues.enemies[defn.id] = defn
                            enemies_count += 1
                        elif self.tabs.currentIndex() == 1:
                            defn = SecretDefinition.from_dict(data)
                            self.catalogues.secrets[defn.id] = defn
                            secrets_count += 1
                        else:
                            prof = PlatformColorProfile.from_dict(data)
                            self.catalogues.platform_profiles[prof.id] = prof
                            profiles_count += 1
            elif isinstance(data, list):
                if self.tabs.currentIndex() == 0:
                    for item in data:
                        defn = EnemyDefinition.from_dict(item)
                        self.catalogues.enemies[defn.id] = defn
                        enemies_count += 1
                elif self.tabs.currentIndex() == 1:
                    for item in data:
                        defn = SecretDefinition.from_dict(item)
                        self.catalogues.secrets[defn.id] = defn
                        secrets_count += 1
                else:
                    for item in data:
                        prof = PlatformColorProfile.from_dict(item)
                        self.catalogues.platform_profiles[prof.id] = prof
                        profiles_count += 1

            if self.base_dir:
                self.catalogues.save_to_dir(self.base_dir)

            self._refresh_enemies_list()
            self._refresh_secrets_list()
            self._refresh_profiles_list()
            self.catalogues_changed.emit()

            msg_parts = []
            if enemies_count:
                msg_parts.append(f"Enemies loaded: {enemies_count}")
            if secrets_count:
                msg_parts.append(f"Secrets loaded: {secrets_count}")
            if profiles_count:
                msg_parts.append(f"Platform profiles loaded: {profiles_count}")
            msg = "\n".join(msg_parts) if msg_parts else "Definitions loaded."

            QMessageBox.information(
                self,
                "Catalogues Loaded",
                f"Successfully loaded definitions from:\n{file_path.name}\n\n{msg}",
            )
        except Exception as err:
            QMessageBox.critical(self, "Import Error", f"Error importing catalogue definitions:\n{err}")

    def _on_save_json_clicked(self) -> None:
        try:
            self.catalogues.save_to_dir(self.base_dir)
            def_path = self.catalogues.get_effective_definitions_path(self.base_dir)
            QMessageBox.information(
                self,
                "Catalogues Saved",
                f"Catalogues saved successfully to:\n• {def_path}",
            )
        except Exception as err:
            QMessageBox.critical(self, "Save Error", f"Failed to save catalogues:\n{err}")

    def _on_configure_paths_clicked(self) -> None:
        cur_def = self.catalogues.get_effective_definitions_path(self.base_dir)
        dlg = CataloguePathsDialog(
            base_dir=self.base_dir or Path.cwd(),
            current_definitions_path=cur_def,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            def_path, reload_now = dlg.get_definitions_path()
            self.catalogues.set_paths(definitions_path=def_path)
            if reload_now:
                try:
                    reloaded = ProjectCatalogues.load_from_paths(definitions_path=def_path)
                    self.catalogues.enemies = reloaded.enemies
                    self.catalogues.secrets = reloaded.secrets
                    self.catalogues.platform_profiles = reloaded.platform_profiles
                    self._refresh_enemies_list()
                    self._refresh_secrets_list()
                    self._refresh_profiles_list()
                    self.catalogues_changed.emit()
                    QMessageBox.information(
                        self,
                        "Catalogue Path Updated",
                        f"Catalogue definitions path updated successfully:\n• {def_path}\n\nDefinitions reloaded.",
                    )
                except Exception as err:
                    QMessageBox.warning(
                        self,
                        "Catalogue Path Updated",
                        f"Catalogue path updated to:\n• {def_path}\n\n"
                        f"Notice during reload: {err}",
                    )
            else:
                QMessageBox.information(
                    self,
                    "Catalogue Path Updated",
                    f"Catalogue path updated successfully:\n• {def_path}",
                )

    # -------------------------------------------------------------------------
    # Color Pickers & Swatches
    # -------------------------------------------------------------------------
    def _update_rgb_enabled(self, is_enemy: bool, enabled: bool) -> None:
        r_spin = self.enemy_r_spin if is_enemy else self.secret_r_spin
        g_spin = self.enemy_g_spin if is_enemy else self.secret_g_spin
        b_spin = self.enemy_b_spin if is_enemy else self.secret_b_spin
        swatch_btn = self.enemy_swatch_btn if is_enemy else self.secret_swatch_btn

        r_spin.setEnabled(enabled)
        g_spin.setEnabled(enabled)
        b_spin.setEnabled(enabled)
        swatch_btn.setEnabled(enabled)
        if enabled:
            self._update_swatch_color(is_enemy)
        else:
            swatch_btn.setStyleSheet("background-color: #555555; border: 1px solid #777;")

    def _update_atari_enabled(self, is_enemy: bool, enabled: bool) -> None:
        spin = self.enemy_atari_spin if is_enemy else self.secret_atari_spin
        lbl = self.enemy_atari_hex_lbl if is_enemy else self.secret_atari_hex_lbl
        spin.setEnabled(enabled)
        lbl.setEnabled(enabled)

    def _update_swatch_color(self, is_enemy: bool) -> None:
        r_spin = self.enemy_r_spin if is_enemy else self.secret_r_spin
        g_spin = self.enemy_g_spin if is_enemy else self.secret_g_spin
        b_spin = self.enemy_b_spin if is_enemy else self.secret_b_spin
        swatch_btn = self.enemy_swatch_btn if is_enemy else self.secret_swatch_btn

        r, g, b = r_spin.value(), g_spin.value(), b_spin.value()
        swatch_btn.setStyleSheet(
            f"background-color: rgb({r}, {g}, {b}); border: 1px solid #ffffff; border-radius: 2px;"
        )

    def _on_pick_color(self, is_enemy: bool) -> None:
        r_spin = self.enemy_r_spin if is_enemy else self.secret_r_spin
        g_spin = self.enemy_g_spin if is_enemy else self.secret_g_spin
        b_spin = self.enemy_b_spin if is_enemy else self.secret_b_spin

        cur_color = QColor(r_spin.value(), g_spin.value(), b_spin.value())
        picked = QColorDialog.getColor(cur_color, self, "Pick RGB Color")
        if picked.isValid():
            r_spin.setValue(picked.red())
            g_spin.setValue(picked.green())
            b_spin.setValue(picked.blue())
            self._update_swatch_color(is_enemy)

    # -------------------------------------------------------------------------
    # Tab 3: Platform Profiles UI & Handlers
    # -------------------------------------------------------------------------
    def _create_platform_profiles_tab(self) -> QWidget:
        widget = QWidget()
        h_layout = QHBoxLayout(widget)
        h_layout.setContentsMargins(6, 6, 6, 6)
        h_layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Profiles List & Action Buttons
        left_pane = QWidget()
        lp_layout = QVBoxLayout(left_pane)
        lp_layout.setContentsMargins(0, 0, 0, 0)
        lp_layout.setSpacing(6)

        self.profiles_list = QListWidget()
        self.profiles_list.currentItemChanged.connect(self._on_profile_selected)

        btn_row = QHBoxLayout()
        self.btn_new_profile = QPushButton("+ New Profile")
        self.btn_new_profile.clicked.connect(self._on_new_profile_clicked)
        self.btn_dup_profile = QPushButton("📋 Duplicate")
        self.btn_dup_profile.clicked.connect(self._on_duplicate_profile_clicked)
        btn_row.addWidget(self.btn_new_profile)
        btn_row.addWidget(self.btn_dup_profile)

        lp_layout.addWidget(self.profiles_list, stretch=1)
        lp_layout.addLayout(btn_row)
        splitter.addWidget(left_pane)

        # Right: Detail / Edit Form
        right_pane = QWidget()
        rp_layout = QVBoxLayout(right_pane)
        rp_layout.setContentsMargins(0, 0, 0, 0)
        rp_layout.setSpacing(6)

        form_group = QGroupBox("Platform Color Profile (8 Scanlines)")
        form_layout = QFormLayout(form_group)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.prof_id_spin = QSpinBox()
        self.prof_id_spin.setRange(1, 255)
        self.prof_id_edit = self.prof_id_spin
        form_layout.addRow("Profile ID (unique identifier 1-255):", self.prof_id_spin)

        self.prof_name_edit = QLineEdit()
        self.prof_name_edit.setPlaceholderText("e.g. Glacial Ice")
        form_layout.addRow("Profile Name:", self.prof_name_edit)

        self.prof_desc_edit = QLineEdit()
        self.prof_desc_edit.setPlaceholderText("Optional description")
        form_layout.addRow("Description:", self.prof_desc_edit)

        self.prof_usage_lbl = QLabel("-")
        self.prof_usage_lbl.setWordWrap(True)
        form_layout.addRow("Scene Usage:", self.prof_usage_lbl)

        # Composite preview bar
        self.prof_preview_bar = PlatformPreviewBar([0x8E, 0x8C, 0x8A, 0x88, 0x86, 0x84, 0x82, 0x80])
        form_layout.addRow("8-Scanline Preview:", self.prof_preview_bar)

        # 8 scanline input editors
        self.prof_scanline_edits: list[QLineEdit] = []
        self.prof_swatches: list[QLabel] = []
        self.prof_rgb_lbls: list[QLabel] = []

        scanlines_group = QGroupBox("Scanline Colors (GTIA 0x00-0xFE, lowest bit 0)")
        sl_layout = QFormLayout(scanlines_group)
        sl_layout.setContentsMargins(6, 6, 6, 6)
        sl_layout.setSpacing(4)

        for i in range(8):
            row_widget = QWidget()
            r_layout = QHBoxLayout(row_widget)
            r_layout.setContentsMargins(0, 0, 0, 0)
            r_layout.setSpacing(8)

            hex_edit = QLineEdit("0x80")
            hex_edit.setFixedWidth(70)
            hex_edit.textChanged.connect(lambda _, idx=i: self._on_scanline_color_changed(idx))

            swatch = QLabel()
            swatch.setFixedSize(36, 20)
            swatch.setStyleSheet("background-color: #000000; border: 1px solid #555; border-radius: 2px;")

            rgb_lbl = QLabel("#000000")
            rgb_lbl.setFixedWidth(70)
            rgb_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #aaa;")

            r_layout.addWidget(hex_edit)
            r_layout.addWidget(swatch)
            r_layout.addWidget(rgb_lbl)
            r_layout.addStretch()

            sl_label = f"Scanline {i + 1} (Row {i // 2}):"
            sl_layout.addRow(sl_label, row_widget)

            self.prof_scanline_edits.append(hex_edit)
            self.prof_swatches.append(swatch)
            self.prof_rgb_lbls.append(rgb_lbl)

        form_layout.addRow(scanlines_group)

        self.prof_error_lbl = QLabel("")
        self.prof_error_lbl.setStyleSheet("color: #ff5555; font-weight: bold;")
        self.prof_error_lbl.setVisible(False)
        form_layout.addRow("", self.prof_error_lbl)

        rp_layout.addWidget(form_group, stretch=1)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_save_profile = QPushButton("Save Profile")
        self.btn_save_profile.clicked.connect(self._on_save_profile_clicked)

        self.btn_revert_profile = QPushButton("Revert")
        self.btn_revert_profile.clicked.connect(self._on_revert_profile_clicked)

        self.btn_delete_profile = QPushButton("Delete Profile")
        self.btn_delete_profile.setStyleSheet("color: #ff5555;")
        self.btn_delete_profile.clicked.connect(self._on_delete_profile_clicked)

        btn_layout.addWidget(self.btn_save_profile)
        btn_layout.addWidget(self.btn_revert_profile)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_delete_profile)
        rp_layout.addLayout(btn_layout)

        splitter.addWidget(right_pane)
        splitter.setSizes([240, 520])

        h_layout.addWidget(splitter)
        return widget

    def _refresh_profiles_list(self, select_id: Optional[int] = None) -> None:
        self.profiles_list.blockSignals(True)
        self.profiles_list.clear()

        sorted_profiles = sorted(self.catalogues.platform_profiles.values(), key=lambda p: p.id)
        selected_row = 0
        for idx, prof in enumerate(sorted_profiles):
            usage = self.catalogues.get_profile_platform_usage(prof.id, self.scene)
            usage_str = f" ({len(usage)} used)" if usage else ""
            item_text = f"[{prof.id}] {prof.name}{usage_str}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, int(prof.id))
            self.profiles_list.addItem(item)
            if select_id is not None and prof.id == select_id:
                selected_row = idx

        self.profiles_list.blockSignals(False)

        if self.profiles_list.count() > 0:
            self.profiles_list.setCurrentRow(selected_row)
        else:
            self._populate_profile_form(None)

    def _on_profile_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if current is None:
            self._populate_profile_form(None)
            return
        prof_id = current.data(Qt.ItemDataRole.UserRole)
        prof = self.catalogues.get_platform_profile(prof_id)
        self._populate_profile_form(prof)

    def _populate_profile_form(self, prof: Optional[PlatformColorProfile]) -> None:
        if prof is None:
            self.prof_id_spin.setEnabled(False)
            self.prof_name_edit.setEnabled(False)
            self.prof_desc_edit.setEnabled(False)
            self.btn_save_profile.setEnabled(False)
            self.btn_revert_profile.setEnabled(False)
            self.btn_delete_profile.setEnabled(False)
            self.prof_id_spin.setValue(1)
            self.prof_name_edit.setText("")
            self.prof_desc_edit.setText("")
            self.prof_usage_lbl.setText("-")
            self.prof_error_lbl.setVisible(False)
            for idx in range(8):
                self.prof_scanline_edits[idx].blockSignals(True)
                self.prof_scanline_edits[idx].setText("0x00")
                self.prof_scanline_edits[idx].setEnabled(False)
                self.prof_scanline_edits[idx].blockSignals(False)
                self._update_scanline_row_ui(idx, 0x00)
            self.prof_preview_bar.set_colors([0x00] * 8)
            return

        self.prof_id_spin.setEnabled(True)
        self.prof_name_edit.setEnabled(True)
        self.prof_desc_edit.setEnabled(True)
        self.btn_save_profile.setEnabled(True)
        self.btn_revert_profile.setEnabled(True)
        self.btn_delete_profile.setEnabled(True)

        self.prof_id_spin.setValue(int(prof.id))
        self.prof_name_edit.setText(prof.name)
        self.prof_desc_edit.setText(prof.description)

        used = self.catalogues.get_profile_platform_usage(prof.id, self.scene)
        if used:
            plat_ids = ", ".join(p.id for p in used)
            self.prof_usage_lbl.setText(f"<b>Assigned to {len(used)} platform(s):</b> {plat_ids}")
            self.prof_usage_lbl.setStyleSheet("color: #4CAF50;")
        else:
            self.prof_usage_lbl.setText("Not currently assigned to any platform on this scene.")
            self.prof_usage_lbl.setStyleSheet("color: #888;")

        colors = prof.colors if (prof.colors and len(prof.colors) == 8) else [0x80] * 8
        for idx, col in enumerate(colors):
            self.prof_scanline_edits[idx].blockSignals(True)
            self.prof_scanline_edits[idx].setEnabled(True)
            self.prof_scanline_edits[idx].setText(format_atari_color_hex(col))
            self.prof_scanline_edits[idx].setStyleSheet("")
            self.prof_scanline_edits[idx].blockSignals(False)
            self._update_scanline_row_ui(idx, col)

        self.prof_preview_bar.set_colors(colors)
        self.prof_error_lbl.setVisible(False)

    def _update_scanline_row_ui(self, idx: int, color_val: int) -> None:
        hex_rgb = atari_color_to_hex_rgb(color_val)
        self.prof_swatches[idx].setStyleSheet(
            f"background-color: {hex_rgb}; border: 1px solid #666; border-radius: 2px;"
        )
        self.prof_rgb_lbls[idx].setText(hex_rgb)

    def _on_scanline_color_changed(self, idx: int) -> None:
        all_valid = True
        error_msg = ""
        current_colors: list[int] = []

        for i, edit in enumerate(self.prof_scanline_edits):
            val_str = edit.text().strip()
            try:
                c = parse_atari_color_hex(val_str)
                current_colors.append(c)
                edit.setStyleSheet("")
                edit.setToolTip("")
                self._update_scanline_row_ui(i, c)
            except Exception as exc:
                all_valid = False
                edit.setStyleSheet("border: 1px solid #ff4444; background-color: #331515;")
                edit.setToolTip(str(exc))
                if not error_msg:
                    error_msg = f"Scanline {i + 1}: {exc}"

        if all_valid:
            self.prof_preview_bar.set_colors(current_colors)
            self.prof_error_lbl.setVisible(False)
            self.btn_save_profile.setEnabled(True)
        else:
            self.prof_error_lbl.setText(error_msg)
            self.prof_error_lbl.setVisible(True)
            self.btn_save_profile.setEnabled(False)

    def _on_new_profile_clicked(self) -> None:
        avail_ids = [i for i in range(1, 256) if i not in self.catalogues.platform_profiles]
        if not avail_ids:
            QMessageBox.warning(self, "Limit Reached", "All profile IDs (1-255) are in use.")
            return
        new_id = avail_ids[0]

        new_prof = PlatformColorProfile(
            id=new_id,
            name=f"New Profile {new_id}",
            colors=[0x8E, 0x8C, 0x8A, 0x88, 0x86, 0x84, 0x82, 0x80],
            description="",
        )
        self.catalogues.add_platform_profile(new_prof)
        self._refresh_profiles_list(select_id=new_id)
        if self.base_dir:
            self.catalogues.save_to_dir(self.base_dir)
        self.catalogues_changed.emit()

    def _on_duplicate_profile_clicked(self) -> None:
        cur_item = self.profiles_list.currentItem()
        if not cur_item:
            return
        prof_id = cur_item.data(Qt.ItemDataRole.UserRole)
        copied = self.catalogues.duplicate_platform_profile(prof_id)
        self._refresh_profiles_list(select_id=copied.id)
        if self.base_dir:
            self.catalogues.save_to_dir(self.base_dir)
        self.catalogues_changed.emit()

    def _on_delete_profile_clicked(self) -> None:
        cur_item = self.profiles_list.currentItem()
        if not cur_item:
            return
        prof_id = cur_item.data(Qt.ItemDataRole.UserRole)
        prof = self.catalogues.get_platform_profile(prof_id)
        if not prof:
            return

        used = self.catalogues.get_profile_platform_usage(prof_id, self.scene)
        if used:
            plat_ids = ", ".join(p.id for p in used)
            reply = QMessageBox.warning(
                self,
                "Profile In Use",
                f"Platform profile '{prof.name}' [{prof.id}] is currently assigned to {len(used)} platform(s):\n"
                f"{plat_ids}\n\n"
                "Deleting this profile will unassign it from all referencing platforms.\n"
                "Do you want to proceed and unassign the profile?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return
            self.catalogues.remove_platform_profile(prof_id, self.scene, force=True)
        else:
            reply = QMessageBox.question(
                self,
                "Delete Profile",
                f"Are you sure you want to delete profile '{prof.name}' [{prof.id}]?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.catalogues.remove_platform_profile(prof_id)

        self._refresh_profiles_list()
        if self.base_dir:
            self.catalogues.save_to_dir(self.base_dir)
        self.catalogues_changed.emit()

    def _on_revert_profile_clicked(self) -> None:
        cur_item = self.profiles_list.currentItem()
        if not cur_item:
            return
        prof_id = cur_item.data(Qt.ItemDataRole.UserRole)
        prof = self.catalogues.get_platform_profile(prof_id)
        self._populate_profile_form(prof)

    def _on_save_profile_clicked(self) -> None:
        cur_item = self.profiles_list.currentItem()
        if not cur_item:
            return
        old_id = int(cur_item.data(Qt.ItemDataRole.UserRole))
        new_id = self.prof_id_spin.value()
        new_name = self.prof_name_edit.text().strip()
        new_desc = self.prof_desc_edit.text().strip()

        if not (1 <= new_id <= 255):
            QMessageBox.warning(self, "Invalid ID", "Profile ID must be between 1 and 255.")
            return
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Profile Name cannot be empty.")
            return

        colors: list[int] = []
        for i, edit in enumerate(self.prof_scanline_edits):
            try:
                colors.append(parse_atari_color_hex(edit.text()))
            except Exception as exc:
                QMessageBox.warning(self, "Invalid Color", f"Error in scanline {i + 1}: {exc}")
                return

        # Check if ID was renamed
        if new_id != old_id:
            if new_id in self.catalogues.platform_profiles:
                QMessageBox.warning(self, "Duplicate ID", f"A profile with ID {new_id} already exists.")
                return
            # Update any platforms referencing old_id to new_id
            if self.scene and hasattr(self.scene, "platforms"):
                for p in self.scene.platforms:
                    if getattr(p, "color_profile_id", None) == old_id:
                        p.color_profile_id = new_id
            self.catalogues.platform_profiles.pop(old_id, None)

        updated_prof = PlatformColorProfile(
            id=new_id,
            name=new_name,
            colors=colors,
            description=new_desc,
        )
        self.catalogues.platform_profiles[new_id] = updated_prof
        self._refresh_profiles_list(select_id=new_id)
        if self.base_dir:
            self.catalogues.save_to_dir(self.base_dir)
        self.catalogues_changed.emit()


class CataloguePathsDialog(QDialog):
    """Dialog allowing users to configure file path for definitions.json."""

    def __init__(
        self,
        base_dir: Path | str,
        current_definitions_path: Optional[Path | str] = None,
        parent: Optional[QWidget] = None,
        current_enemies_path: Optional[Path | str] = None,
        current_secrets_path: Optional[Path | str] = None,
        current_profiles_path: Optional[Path | str] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Catalogue Definitions Path")
        self.resize(600, 180)
        self.setModal(True)

        self.base_dir = Path(base_dir).resolve()
        default_def = ProjectCatalogues.find_definitions_path(self.base_dir)
        self.default_definitions = default_def

        cur_def = current_definitions_path or current_enemies_path or default_def
        self.cur_def = Path(cur_def).resolve() if cur_def else default_def

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        desc_lbl = QLabel(
            "Configure default JSON file path for game definitions (enemies, secrets, and platform profiles).\n"
            "Relative paths will be resolved relative to the project root directory."
        )
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Definitions Path
        def_row = QWidget()
        dr_layout = QHBoxLayout(def_row)
        dr_layout.setContentsMargins(0, 0, 0, 0)
        self.edit_definitions = QLineEdit(str(self.cur_def))
        self.edit_enemies = self.edit_definitions
        self.edit_secrets = self.edit_definitions
        self.edit_profiles = self.edit_definitions

        btn_browse_definitions = QPushButton("Browse...")
        btn_browse_definitions.clicked.connect(self._browse_definitions)
        dr_layout.addWidget(self.edit_definitions, stretch=1)
        dr_layout.addWidget(btn_browse_definitions)
        form_layout.addRow("Definitions JSON Path:", def_row)

        layout.addLayout(form_layout)

        # Reload option
        self.chk_reload = QCheckBox("Reload definitions immediately")
        self.chk_reload.setChecked(True)
        layout.addWidget(self.chk_reload)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_reset = QPushButton("Reset to Default")
        btn_reset.setToolTip("Reset path to standard project location (scenes/definitions.json)")
        btn_reset.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(btn_reset)

        btn_layout.addStretch(1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        btn_layout.addWidget(button_box)

        layout.addLayout(btn_layout)

    def _browse_definitions(self) -> None:
        start = self.edit_definitions.text().strip() or str(self.default_definitions)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Definitions JSON File",
            start,
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            self.edit_definitions.setText(path)

    def _reset_defaults(self) -> None:
        self.edit_definitions.setText(str(self.default_definitions))

    def _on_accept(self) -> None:
        d_text = self.edit_definitions.text().strip()
        if not d_text:
            QMessageBox.warning(self, "Invalid Path", "File path must be specified.")
            return
        self.accept()

    def get_definitions_path(self) -> tuple[Path, bool]:
        d_path = Path(self.edit_definitions.text().strip())
        if not d_path.is_absolute():
            d_path = (self.base_dir / d_path).resolve()
        return d_path, self.chk_reload.isChecked()

    def get_paths(self) -> tuple[Path, Path, Path, bool]:
        d_path, reload_now = self.get_definitions_path()
        return d_path, d_path, d_path, reload_now
