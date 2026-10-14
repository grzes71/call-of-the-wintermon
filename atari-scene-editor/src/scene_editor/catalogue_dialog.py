"""Dialog for managing project-wide Enemies and Secrets catalogues."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
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

from .catalogue_model import (
    DuplicateDefinitionIdError,
    EnemyDefinition,
    InvalidDefinitionError,
    ProjectCatalogues,
    SecretDefinition,
)
from .scene_model import OBJECT_TYPE_ENEMY, OBJECT_TYPE_SECRET, Scene


class CataloguesDialog(QDialog):
    """Dialog allowing users to browse, create, edit, and delete catalogue entries for Enemies and Secrets."""

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
        self.setWindowTitle("Enemies & Secrets Catalogues")
        self.resize(780, 540)
        self.setModal(True)

        self.catalogues = catalogues
        self.scene = scene
        self.base_dir = Path(base_dir).resolve() if base_dir else None

        self._build_ui()
        if initial_tab == "secrets":
            self.tabs.setCurrentIndex(1)
        else:
            self.tabs.setCurrentIndex(0)

        self._refresh_enemies_list()
        self._refresh_secrets_list()

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

        return widget

    # -------------------------------------------------------------------------
    # Enemies Handlers
    # -------------------------------------------------------------------------
    def _refresh_enemies_list(self, select_id: Optional[str] = None) -> None:
        self.enemy_list.blockSignals(True)
        self.enemy_list.clear()

        row_to_select = -1
        for idx, (defn_id, defn) in enumerate(self.catalogues.enemies.items()):
            text = f"{defn.name} [{defn.id}]"
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

        try:
            defn = EnemyDefinition(
                id=defn_id,
                name=name,
                rgb_color=rgb,
                atari_color=atari,
                blink=blink,
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
        self.secret_btn_delete.setEnabled(True)

    def _on_new_secret_clicked(self) -> None:
        self._cur_editing_secret_id = None
        self.secret_list.blockSignals(True)
        self.secret_list.clearSelection()
        self.secret_list.setCurrentRow(-1)
        self.secret_list.blockSignals(False)

        # Suggest next unused integer ID in 1-255
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

        try:
            defn = SecretDefinition(
                id=defn_id,
                name=name,
                rgb_color=rgb,
                atari_color=atari,
                blink=blink,
            )
            defn.validate()

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

        # Safety check: is this definition used by any scene object?
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
                if "enemies" not in data and "secrets" not in data:
                    if "id" in data and "name" in data:
                        if self.tabs.currentIndex() == 0:
                            defn = EnemyDefinition.from_dict(data)
                            self.catalogues.enemies[defn.id] = defn
                            enemies_count += 1
                        else:
                            defn = SecretDefinition.from_dict(data)
                            self.catalogues.secrets[defn.id] = defn
                            secrets_count += 1
            elif isinstance(data, list):
                if self.tabs.currentIndex() == 0:
                    for item in data:
                        defn = EnemyDefinition.from_dict(item)
                        self.catalogues.enemies[defn.id] = defn
                        enemies_count += 1
                else:
                    for item in data:
                        defn = SecretDefinition.from_dict(item)
                        self.catalogues.secrets[defn.id] = defn
                        secrets_count += 1

            if self.base_dir:
                self.catalogues.save_to_dir(self.base_dir)

            self._refresh_enemies_list()
            self._refresh_secrets_list()
            self.catalogues_changed.emit()

            QMessageBox.information(
                self,
                "Catalogues Loaded",
                f"Successfully loaded definitions from:\n{file_path.name}\n\n"
                f"Enemies loaded: {enemies_count}\n"
                f"Secrets loaded: {secrets_count}",
            )
        except Exception as err:
            QMessageBox.critical(self, "Import Error", f"Error importing catalogue definitions:\n{err}")

    def _on_save_json_clicked(self) -> None:
        try:
            self.catalogues.save_to_dir(self.base_dir)
            enemies_path, secrets_path = self.catalogues.get_effective_paths(self.base_dir)
            QMessageBox.information(
                self,
                "Catalogues Saved",
                f"Catalogues saved successfully to:\n• {enemies_path}\n• {secrets_path}",
            )
        except Exception as err:
            QMessageBox.critical(self, "Save Error", f"Failed to save catalogues:\n{err}")

    def _on_configure_paths_clicked(self) -> None:
        cur_e, cur_s = self.catalogues.get_effective_paths(self.base_dir)
        dlg = CataloguePathsDialog(
            base_dir=self.base_dir or Path.cwd(),
            current_enemies_path=cur_e,
            current_secrets_path=cur_s,
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
                    self._refresh_enemies_list()
                    self._refresh_secrets_list()
                    self.catalogues_changed.emit()
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
                QMessageBox.information(
                    self,
                    "Catalogue Paths Updated",
                    f"Catalogue paths updated successfully:\n• Enemies: {enemies_path}\n• Secrets: {secrets_path}",
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


class CataloguePathsDialog(QDialog):
    """Dialog allowing users to configure custom file paths for enemies.json and secrets.json."""

    def __init__(
        self,
        base_dir: Path | str,
        current_enemies_path: Optional[Path | str] = None,
        current_secrets_path: Optional[Path | str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Catalogue Paths")
        self.resize(600, 220)
        self.setModal(True)

        self.base_dir = Path(base_dir).resolve()
        default_enemies, default_secrets = ProjectCatalogues.find_catalogue_paths(self.base_dir)
        self.default_enemies = default_enemies
        self.default_secrets = default_secrets

        cur_e = Path(current_enemies_path).resolve() if current_enemies_path else default_enemies
        cur_s = Path(current_secrets_path).resolve() if current_secrets_path else default_secrets

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        desc_lbl = QLabel(
            "Configure default JSON file paths for Enemies and Secrets definitions.\n"
            "Relative paths will be resolved relative to the project root directory."
        )
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Enemies Path
        enemies_row = QWidget()
        er_layout = QHBoxLayout(enemies_row)
        er_layout.setContentsMargins(0, 0, 0, 0)
        self.edit_enemies = QLineEdit(str(cur_e))
        btn_browse_enemies = QPushButton("Browse...")
        btn_browse_enemies.clicked.connect(self._browse_enemies)
        er_layout.addWidget(self.edit_enemies, stretch=1)
        er_layout.addWidget(btn_browse_enemies)
        form_layout.addRow("Enemies JSON Path:", enemies_row)

        # Secrets Path
        secrets_row = QWidget()
        sr_layout = QHBoxLayout(secrets_row)
        sr_layout.setContentsMargins(0, 0, 0, 0)
        self.edit_secrets = QLineEdit(str(cur_s))
        btn_browse_secrets = QPushButton("Browse...")
        btn_browse_secrets.clicked.connect(self._browse_secrets)
        sr_layout.addWidget(self.edit_secrets, stretch=1)
        sr_layout.addWidget(btn_browse_secrets)
        form_layout.addRow("Secrets JSON Path:", secrets_row)

        layout.addLayout(form_layout)

        # Reload option
        self.chk_reload = QCheckBox("Reload definitions from these paths immediately")
        self.chk_reload.setChecked(True)
        layout.addWidget(self.chk_reload)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_reset = QPushButton("Reset to Defaults")
        btn_reset.setToolTip("Reset paths to standard project location")
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

    def _browse_enemies(self) -> None:
        start = self.edit_enemies.text().strip() or str(self.default_enemies)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Enemies JSON File",
            start,
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            self.edit_enemies.setText(path)

    def _browse_secrets(self) -> None:
        start = self.edit_secrets.text().strip() or str(self.default_secrets)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Secrets JSON File",
            start,
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            self.edit_secrets.setText(path)

    def _reset_defaults(self) -> None:
        self.edit_enemies.setText(str(self.default_enemies))
        self.edit_secrets.setText(str(self.default_secrets))

    def _on_accept(self) -> None:
        e_text = self.edit_enemies.text().strip()
        s_text = self.edit_secrets.text().strip()
        if not e_text or not s_text:
            QMessageBox.warning(self, "Invalid Path", "Both file paths must be specified.")
            return
        self.accept()

    def get_paths(self) -> tuple[Path, Path, bool]:
        e_path = Path(self.edit_enemies.text().strip())
        s_path = Path(self.edit_secrets.text().strip())
        if not e_path.is_absolute():
            e_path = (self.base_dir / e_path).resolve()
        if not s_path.is_absolute():
            s_path = (self.base_dir / s_path).resolve()
        return e_path, s_path, self.chk_reload.isChecked()
