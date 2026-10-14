# Project History

<!-- AGENT INSTRUCTIONS: Add new entries below this comment. Use format: ## [YYYY-MM-DD] - [Brief Title] -->

## [2026-10-14] - Fix Scene Loading for Integer Object IDs in Sequence Number Calculation

- **Fixed `AttributeError: 'int' object has no attribute 'split'` when loading scenes with numeric object IDs** in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - In `MainWindow.open_scene()`, updated `_next_object_num` calculation to inspect `isinstance(obj.id, int)` directly and parse numeric IDs cleanly, avoiding calling `.split("-")` on integer object IDs from saved scenes like [scenes/01-forest.json](scenes/01-forest.json).
  - Also safeguarded element and platform ID sequence number calculations with `str()` conversions.
  - Allowed `MainWindow.open_scene()` to take an optional `file_path: Optional[str] = None` argument so scene files can be loaded programmatically.
- **Automated Tests**:
  - Added `test_load_01_forest_scene_with_numeric_objects` in [tests/test_scene_objects.py](tests/test_scene_objects.py) verifying that [scenes/01-forest.json](scenes/01-forest.json) loads without errors, all 4 objects are preserved with numeric IDs, and objects can be moved with Undo/Redo.
  - Verified all 203 tests pass.


## [2026-10-14] - Enable All Selected Object Controls (ID, Type, Definition, X, Speed, Strategy, Delete) with Platform Exclusively Read-Only

- **Kept all property editing components enabled under "Selected Object"** in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - In `_update_object_property_panel()`, ensured `self.obj_elem_group`, `obj_prop_id_spin`, `obj_prop_type_combo`, `obj_prop_definition_combo`, `obj_prop_x_spin`, `obj_prop_speed_combo`, `obj_prop_strategy_combo`, and `btn_delete_obj` remain enabled (`setEnabled(True)`).
  - Enforced that **exclusively** `self.obj_prop_platform_combo` is read-only (`setEnabled(False)`).
  - Connected `self.prop_tabs.currentChanged` to `_on_prop_tab_changed()` so that switching to the "Objects" tab immediately selects and populates the active/first scene object.
  - Implemented `_get_effective_selected_object_id()` to seamlessly fall back to the highlighted list object or active object, ensuring direct edits to `x_spin`, `speed_combo`, `strategy_combo`, `type_combo`, and `definition_combo` update the object without being dropped.
  - In `_on_object_command_executed()`, called `self._on_object_selected(select_id)` to keep the property panel refreshed after adding or modifying an object.
- **Removed `QFont::setPointSize: Point size <= 0 (-1)` runtime warning**:
  - In [atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py), changed glyph and badge font sizing from `setPixelSize()` to `setPointSize()`.
- **Automated Tests**:
  - Added `test_selected_object_components_enabled_and_only_platform_readonly` in [tests/test_scene_objects.py](tests/test_scene_objects.py) verifying that all controls in "Selected Object" are enabled while only `Platform` is read-only, and that modifying properties via these controls functions properly.
  - Verified all 202 tests pass.


## [2026-10-14] - Fix Canvas Object Selection and Paint Rendering for Numeric Object IDs

- **Fixed object selection on canvas click** in [atari-scene-editor/src/scene_editor/scene_view.py](atari-scene-editor/src/scene_editor/scene_view.py):
  - Changed `object_selected` and `object_moved` signals from `Signal(str)` to `Signal(object)`. With numeric IDs (1–255), PySide6 failed C++ copy-conversion for `Signal(str)`, emitting an empty string `""` and causing `_on_object_selected` to clear rather than populate the Selected Object panel.
  - Updated `select_object()`, `get_selected_object_id()`, `update_object_item()`, and `populate_scene()` to match object IDs flexibly whether represented as `int` or `str`.
  - In [atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py), added explicit `self.setSelected(True)` on left mouse click in `SceneObjectGraphicsItem.mousePressEvent()`.
- **Fixed `NameError: name 'is_enemy' is not defined` during `paint()`**:
  - In [atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py), defined `is_enemy` and resolved `defn` at the beginning of `SceneObjectGraphicsItem.paint()`, resolving the paint crash that prevented graphics item selection and visual borders from rendering.
- **Fixed `TypeError: can_add_object_to_platform() got unexpected keyword argument 'exclude_obj_id'**:
  - In [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py), added `exclude_obj_id` alias parameter to `can_add_object_to_platform()` and normalized argument usage in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py).
- **Automated Tests**:
  - Added `test_click_object_on_canvas_selects_and_populates_properties` in [tests/test_scene_objects.py](tests/test_scene_objects.py) verifying clean `paint()`, canvas selection signal emission, property panel synchronization, and automatic tab switching.
  - Verified all 201 tests pass.


## [2026-10-14] - Objects Tab UI Refinements: Remove Manage Catalogues Button, Numeric Object ID (1-255), and Read-Only Platform Dropdown

- **Removed "Manage Catalogues" button from the "Objects" tab** in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Removed `btn_manage_catalogues` and simplified the Objects tab layout. Catalogue management remains cleanly accessible via the top-level `Catalogues` menu (`Ctrl+K`).
- **Standardized Scene Object IDs to numeric range 1-255**:
  - In [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py), replaced the static ID label in "Selected Object" panel with `obj_prop_id_spin` (`QSpinBox`, range 1..255).
  - Implemented `ChangeSceneObjectIdCommand` in [atari-scene-editor/src/scene_editor/commands.py](atari-scene-editor/src/scene_editor/commands.py) to support full Undo/Redo tracking when changing an object's ID.
  - Added duplicate ID validation in `_on_obj_prop_id_changed()` with user-friendly warnings.
  - Updated auto-generation of new object IDs in `_on_add_object_clicked()` to automatically assign the lowest unused integer in 1..255.
  - In [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py), updated `SceneObjectElement.__init__()` and `validate()` to accept and enforce integer IDs within 1..255 while preserving backwards-compatibility for existing tests.
- **Made "Platform" dropdown read-only in "Selected Object" panel**:
  - In [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py), disabled `obj_prop_platform_combo` (`setEnabled(False)`) with updated label `"Platform (read-only):"` and tooltip.
  - Guaranteed `obj_prop_platform_combo` remains disabled across all object selection and property update flows.
- **Automated Tests**:
  - Added `test_objects_tab_ui_specifications` in [tests/test_scene_objects.py](tests/test_scene_objects.py) validating the absence of the button, numeric ID assignment (1-255), ID mutation with undo/redo, and read-only state of the platform dropdown.
  - Verified all 200 tests pass.


## [2026-10-14] - Fix Object Creation AttributeError on None Source and Resolve QFont Warning

- Fixed `AttributeError: 'NoneType' object has no attribute 'replace'` in `Scene.get_sources()` in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py):
  - Added guard check `if obj.source:` before normalizing source file path with `.replace("\\", "/")`. Objects created from definition catalogues without an explicit tile crop have `source=None`, which previously triggered an unhandled exception inside `QUndoCommand::redo()` and interrupted scene rendering.
  - Added guard check `if elem.source:` for scene elements.
- Resolved Qt font point size warnings in [atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py):
  - Passed explicit positive point sizes in `QFont` constructors (`QFont("Arial", 6)`, `QFont("Arial", 5)`, `QFont("Courier", 8)`, `QFont("Monospace", 6)`) to eliminate `QFont::setPointSize: Point size <= 0 (-1)` runtime warnings.
- Added automated integration tests in [tests/test_scene_objects.py](tests/test_scene_objects.py):
  - Added `test_get_sources_handles_none_source` ensuring `Scene.get_sources()` properly handles `obj.source=None`.
  - Added `test_add_catalogue_object_without_source_in_main_window` validating full GUI addition workflow, scene rendering, and Undo/Redo commands when creating catalogue objects without source images.
  - Verified all 199 tests pass.

## [2026-10-14] - Dedicated Catalogues Menu and Custom Catalogue File Paths Configuration

- Removed duplicated catalogue management options (`Load Catalogues (JSON)...`, `Save Catalogues (JSON)`, `Save Catalogues As...`) from the `File` menu in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py), centralizing all catalogue operations in the dedicated `Catalogues` top-level menu.
- Implemented configurable catalogue file paths in [atari-scene-editor/src/scene_editor/catalogue_model.py](atari-scene-editor/src/scene_editor/catalogue_model.py):
  - Added `enemies_path` and `secrets_path` fields to `ProjectCatalogues`.
  - Added `set_paths()` and `get_effective_paths()` methods allowing custom file paths for enemies and secrets definitions while falling back to project defaults.
  - Added `load_from_paths()` and updated `save_to_dir()` to load and save definitions using configured paths.
- Added `CataloguePathsDialog` in [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py):
  - Allows user to browse and customize file paths for enemies and secrets JSON files with relative and absolute path support.
  - Added "Reset to Defaults" button and option to reload definitions from newly selected paths immediately.
  - Added `"⚙ Configure Paths..."` button to the bottom toolbar in `CataloguesDialog`.
- Added `"Configure Catalogue Paths..."` action to the `Catalogues` menu in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py) with handler `configure_catalogue_paths()`.
- Extended automated tests in [tests/test_catalogues.py](tests/test_catalogues.py):
  - Verified `File` menu no longer contains catalogue actions.
  - Verified `Catalogues` menu contains all management and path configuration actions.
  - Added tests for `ProjectCatalogues` custom path saving and loading (`test_custom_catalogue_paths`).
  - Added tests for `CataloguePathsDialog` path resolution and reset logic (`test_catalogue_paths_dialog`).
  - Verified all 197 tests pass.

## [2026-10-14] - Update Entry Button and Main Menu Catalogue JSON Import/Export

- Updated button label to `"Update Entry"` for editing existing entries in [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py):
  - Changed default entry button text to `"Update Entry"` and switched dynamically between `"Add Entry"` (when creating a new definition) and `"Update Entry"` (when viewing, selecting, or updating an existing definition).
  - Ensured `currentRow` is reset to `-1` when creating a new definition so subsequent selection changes reliably trigger updates.
  - Added `"📂 Load JSON..."` and `"💾 Save JSON"` buttons to the bottom action bar in `CataloguesDialog`.
- Added catalogue JSON persistence and management actions to the main application menu in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Added `Load Catalogues (JSON)...`, `Save Catalogues (JSON)`, and `Save Catalogues As...` to the `File` menu.
  - Added dedicated top-level `Catalogues` menu with items `Manage Catalogues... (Ctrl+K)`, `Load Catalogues (JSON)...`, `Save Catalogues (JSON)`, and `Save Catalogues As...`.
  - Implemented `load_catalogues_from_json()`, `save_catalogues_to_json()`, and `save_catalogues_as()` handlers supporting both combined dictionary format and discrete `enemies.json` / `secrets.json` files with automatic UI synchronization and scene definition refresh.
- Extended integration test suite in [tests/test_catalogues.py](tests/test_catalogues.py):
  - Added `test_dialog_button_says_update_entry_when_editing` verifying dynamic label switching.
  - Added `test_menu_contains_catalogue_actions` verifying menu presence in both `File` and `Catalogues` menus.
  - Added `test_main_window_save_and_load_catalogues_json` verifying JSON save and reload functionality.
  - Verified all 195 tests pass.

## [2026-10-14] - Enforce Integer Object Definition ID in Range 1-255

- Enforced integer range `1-255` for catalogue definition IDs in [atari-scene-editor/src/scene_editor/catalogue_model.py](atari-scene-editor/src/scene_editor/catalogue_model.py):
  - Updated `CatalogDefinition.id` to `int` with strict validation (`1 <= id <= 255`), rejecting numbers outside bounds, non-numeric strings, and booleans.
  - Added support for numeric string conversions in `validate()` and `from_dict()`.
  - Updated `ProjectCatalogues` with `_normalize_id` helper ensuring dictionary lookups (`get_definition`, `get_enemy`, `get_secret`) work seamlessly with both `int` and numeric `str` keys.
  - Updated `save_to_dir()` to sort catalogue entries deterministically by integer `id`.
- Replaced definition ID text input with `QSpinBox` (range `1-255`) in [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py):
  - Updated label to `"ID (unique identifier 1-255):"`.
  - Implemented automatic suggestion of the lowest unused integer ID in `1..255` when clicking "+ New Enemy" or "+ New Secret".
  - Added automatic cascading update of scene object references when an existing definition ID is modified.
  - Made `scene` parameter optional in `CataloguesDialog.__init__`.
- Updated scene object model and editor integration in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py) and [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Ensured `SceneObjectElement.definition_id` parses and serializes integer IDs cleanly, while maintaining fallback support for legacy strings.
  - Updated definition combo selection matching in property inspector.
- Updated automated test suite in [tests/test_catalogues.py](tests/test_catalogues.py):
  - Added tests for valid integer IDs (1, 255), out-of-bounds rejection (0, -1, 256, 1000), string numbers, and `CataloguesDialog` spinbox bounds.
  - Verified all 192 tests pass.

## [2026-10-14] - English UI Translation and Font Initialization Fix

- Translated all user interface elements, labels, tooltips, comboboxes, and dialog messages in `atari-scene-editor` to pure English:
  - In [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py): Updated `ENEMY_SPEED_LABELS` (`Slow`, `Medium`, `Fast`) and `MOVEMENT_STRATEGY_LABELS` (`Stationary`, `Left - Right`, `Right - Left`, `Left - Pause - Right`, `Right - Pause - Left`).
  - In [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py): Translated window title ("Enemies & Secrets Catalogues"), tab titles ("Enemies", "Secrets"), form labels ("ID (unique identifier):", "Name:", "Enable RGB Color", "Enable Atari Color (GTIA)", "Blink (cycle luminance)"), buttons ("Save Entry", "Delete Entry"), and confirmation/deletion protection dialogs.
  - In [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py): Translated catalogue management button ("Manage Catalogues..."), action menu item, object creator type selector ("Enemy", "Secret"), speed/strategy form labels, definition status badges, and critical/warning message boxes (corrupted catalogue file, missing catalogue definitions, empty catalogue, object limit exceeded).
- Fixed Qt font warning in [atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py):
  - Replaced `QFont("Arial", -1, QFont.Weight.Bold)` with `QFont("Arial")` + `f.setBold(True)` + `f.setPixelSize(...)`, resolving `QFont::setPointSize: Point size <= 0 (-1), must be greater than 0`.
- Verified all 183 automated tests in [tests/](tests/) pass cleanly with zero warnings.

## [2026-10-14] - Implement Enemy & Secret Project Catalogues and Scene Object Instances

- Created project-level catalogue model in [atari-scene-editor/src/scene_editor/catalogue_model.py](atari-scene-editor/src/scene_editor/catalogue_model.py):
  - Added dataclasses `CatalogDefinition`, `EnemyDefinition`, `SecretDefinition` with fields: `id` (mandatory, non-empty, unique within catalogue), `name` (mandatory, non-empty), `rgb_color` (optional tuple of 3 ints 0-255), `atari_color` (optional int 0-255 / GTIA color byte, not computed from RGB), and `blink` (boolean flag, default False).
  - Added `ProjectCatalogues` container managing separate collections of enemies and secrets with CRUD operations, duplicate ID prevention, and lookup (`get_definition`).
  - Implemented atomic file persistence (`save_to_dir`, `load_from_dir`, `_atomic_save_json`) saving to `enemies.json` and `secrets.json` via temporary files and `os.replace`.
  - Added corrupted file protection (`CorruptedCatalogueFileError`): raises descriptive error without silently overwriting malformed files.
- Implemented catalogue management dialog in [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py):
  - Created PySide6 modal `CataloguesDialog` with dedicated tabs for Enemies and Secrets.
  - Added reactive form with real-time RGB color swatch preview, color picker dialog, Atari hex/dec spinbox, and blink toggle.
  - Implemented deletion safety check preventing deletion of definitions currently referenced by scene objects on the active scene.
- Updated scene object model in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py):
  - Unified object types around `OBJECT_TYPE_SECRET = "secret"` with `OBJECT_TYPE_TREASURE = "secret"` backward-compatible alias.
  - Updated `SceneObjectElement` to store `definition_id` referencing catalogue definitions without duplicating definition properties in scene instances.
  - Preserved backward-compatible constructors and crop attributes for legacy scenes.
  - Enforced combined limit of 3 objects (enemies and secrets) per platform row.
- Updated undo/redo commands in [atari-scene-editor/src/scene_editor/commands.py](atari-scene-editor/src/scene_editor/commands.py):
  - Added support for `new_definition_id` in `UpdateSceneObjectPropsCommand`.
- Updated canvas graphics rendering in [atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py) and [atari-scene-editor/src/scene_editor/scene_view.py](atari-scene-editor/src/scene_editor/scene_view.py):
  - Rendered scene object instances as crisp 8x8 colored squares resting on platforms (`y = platform.y - height`).
  - Implemented `resolve_color`: renders square using definition `rgb_color` if present, or neutral readable fallback (`#D32F2F` crimson for Enemy, `#FFA000` amber for Secret).
  - Rendered contrasting glyph ("E" or "S") inside each square.
  - Added comprehensive tooltip displaying definition name, Atari color in hex, blink status, and warning badge if definition or platform is missing.
- Updated main application window in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Integrated `self.catalogues` loaded from `enemies.json` and `secrets.json` on startup.
  - Added "Manage Catalogues (Kartoteki)..." button (`Ctrl+K` shortcut and Edit menu action).
  - Replaced crop capture controls on `Objects` tab with definition selector combo boxes reflecting active catalogue entries.
  - Blocked object creation when catalogue is empty with informative user prompt to define entries first.
  - Added definition property inspector and reselection combo in Selected Object panel.
  - Updated `save_scene` to save both scene JSON and project catalogues atomically.
- Updated JSON serialization in [atari-scene-editor/src/scene_editor/json_serializer.py](atari-scene-editor/src/scene_editor/json_serializer.py):
  - Handled `obj.source is None` for definition-based scene objects.
  - Ensured scene JSON stores only instance data and definition references (`definition_id`), avoiding definition duplication.
- Created test suite in [tests/test_catalogues.py](tests/test_catalogues.py):
  - 37 unit and integration tests covering model validation, uniqueness, persistence, corrupted file safety, definition renaming, square rendering, fallback colors, empty catalogue blocking, and deletion protection.
- Updated documentation in [atari-scene-editor/README.md](atari-scene-editor/README.md).


## [2026-10-14] - Update Platform Height to 4 Lines & Backward Compatibility

- Updated platform height specification from 8 scanlines to exactly 4 scanlines in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py):
  - Changed `PLATFORM_HEIGHT = 4`.
  - Enforced strict validation: height must equal 4; non-4 values raise `InvalidPlatformDimensionError`.
  - Added backward compatibility in `PlatformElement.from_dict`: automatically migrates legacy platform definitions with `height == 8` to `PLATFORM_HEIGHT = 4`.
  - Updated `can_add_platform_to_row` to support optional `scene_height` parameter for row boundary validation (`(y + PLATFORM_HEIGHT) <= scene_height`).
  - Maintained vertical positioning rule (`y % 16 == 8`) and resource limits (max 3 sprites, 4 missiles per row).
- Updated GUI rendering and item manipulation in [atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py):
  - Set `boundingRect` and paint dimensions to exactly 4 logical pixels high.
  - Adjusted label rendering condition (`if h >= 6 and w >= 12:`) to prevent font overflow within a 4px tall platform.
  - Constrained mouse dragging/snapping to `scene_h - self.platform.height`.
- Updated keyboard navigation in [atari-scene-editor/src/scene_editor/scene_view.py](atari-scene-editor/src/scene_editor/scene_view.py):
  - Clamped vertical arrow navigation `new_y` strictly to valid rows within `scene_h - PLATFORM_HEIGHT`.
- Updated GUI properties panel in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Displayed fixed "4 lines (Fixed)" label for platform height.
  - Handled row and type changes passing `scene_height=self.scene_model.height` to row limit checks.
  - Prevented invalid moves from triggering uncaught exceptions.
- Updated JSON serialization and sample scenes:
  - Ensured platforms serialize with `"height": 4`.
  - Migrated [scenes/01-forest.json](scenes/01-forest.json) platforms to height 4.
- Updated test suite in [tests/test_platform_editor.py](tests/test_platform_editor.py):
  - Updated all platform test cases to assert and validate `height == 4`.
  - Added tests ensuring invalid platform heights (`[1, 2, 3, 5, 8, 16]`) are rejected.
  - Added test `test_backward_compatibility_platform_height_8_migrated_to_4` verifying legacy JSON data with height 8 seamlessly converts to 4.
  - Added collision tests verifying 4px vertical collision boundaries, edge touching without overlap, and pairwise collision detection.
- Updated documentation in [atari-scene-editor/README.md](atari-scene-editor/README.md) to document 4-line platform height.


## [2026-10-14] - Implement Strict Platform Collision Prohibition & Fix Selection Recursion

- Added strict platform collision validation in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py):
  - Added `PlatformCollisionError` exception.
  - Implemented `platforms_overlap(x1, y1, w1, h1, x2, y2, w2, h2)`: checks strict 2D rectangular intersection (platforms touching edges without sharing pixels do not collide).
  - Implemented `check_platform_collision(platforms, candidate_rect, exclude_id)` helper function.
  - Updated `Scene.validate()` to perform pairwise platform collision checks across all platforms on the scene.
  - Updated `Scene.add_platform()`, `Scene.move_platform()`, `Scene.resize_platform()`, and `Scene.set_platform_type()` to atomically validate collisions before mutating platform state, preserving original coordinates and dimensions upon rejection.
- Updated JSON deserialization in [atari-scene-editor/src/scene_editor/json_serializer.py](atari-scene-editor/src/scene_editor/json_serializer.py) to wrap `ModelValidationError` from `scene.validate()` in `CorruptedFileError`, reporting exact colliding platform IDs and coordinates.
- Fixed selection signal recursion and font point size warnings:
  - Added re-entrancy protection flags in [atari-scene-editor/src/scene_editor/scene_view.py](atari-scene-editor/src/scene_editor/scene_view.py) (`_is_updating_selection`) and [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py) (`_is_selecting_platform`, `_is_selecting_element`) preventing infinite signal loop between canvas items and list widgets.
  - Updated [atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py) to use `font.setPixelSize(...)` instead of `setPointSize(...)`, resolving font point size warning.
- Integrated GUI collision rejection in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Platform Creator: checks collision before creating platform; shows warning dialog on overlap.
  - Drag & Drop: checks collision upon mouse release; reverts item position on canvas if collision occurs.
  - Property Controls: validates Position X, Row, Width, and Type changes; reverts controls and keeps previous valid platform state.
- Added 12 new automated tests in [tests/test_platform_editor.py](tests/test_platform_editor.py) and [tests/test_gui_integration.py](tests/test_gui_integration.py):
  - Tested identical positions, partial overlaps, varying widths, sprite vs. missile collisions, touching edges without overlap, different row independence, rejected moves/resizes/type changes, JSON collision detection, Undo/Redo collision invariants, and GUI rejection flows.


## [2026-10-14] - Implement Atari 8-Bit Hardware Platform Editor (PMG Sprites & Missiles)

- Added PMG platform domain logic and hardware constraints to [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py):
  - Defined `PlatformElement` dataclass with `id`, `type` (`sprite` or `missile`), `position` (`Position(x, y)`), `width`, and fixed `height = 8`.
  - Enforced horizontal ×4 expansion rules: sprite widths strictly in `[4, 8, 12, 16, 20, 24, 28, 32]` px; missile widths strictly in `[4, 8]` px.
  - Enforced vertical row rule: platforms can only start at `y % 16 == 8` (e.g. `y = 8, 24, 40, ...`) and within scene bounds (`y + 8 <= height`).
  - Implemented row resource tracking and validation: maximum **3 sprites** and **4 missiles** per allowed row; raised `HardwareResourceLimitError` when exceeding limits.
  - Added scene methods: `add_platform()`, `remove_platform()`, `get_platform()`, `move_platform()`, `resize_platform()`, `set_platform_type()`, `get_platform_row_usage()`, and `can_add_platform_to_row()`.
- Extended JSON serialization in [atari-scene-editor/src/scene_editor/json_serializer.py](atari-scene-editor/src/scene_editor/json_serializer.py):
  - Serialized `platforms` list in scene JSON.
  - Provided backwards compatibility: older scene files without `platforms` load seamlessly as empty list.
- Implemented Undo/Redo commands in [atari-scene-editor/src/scene_editor/commands.py](atari-scene-editor/src/scene_editor/commands.py):
  - Added `AddPlatformCommand`, `RemovePlatformCommand`, `MovePlatformCommand`, `ResizePlatformCommand`, `ChangePlatformTypeCommand` integrated with `QUndoStack`.
- Added graphics rendering in [atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py):
  - Implemented `PlatformGraphicsItem` with Atari retro styling (cyan for sprites, orange for missiles), 4px bit grid ticks, 3D border, type and width labels, and selection handles.
  - Implemented vertical dragging constrained strictly to allowed platform rows (`y % 16 == 8`) with boundary clamping.
- Updated canvas view in [atari-scene-editor/src/scene_editor/scene_view.py](atari-scene-editor/src/scene_editor/scene_view.py):
  - Added subtle guide bands for allowed platform rows (`y % 16 == 8`).
  - Added platform selection and movement signals (`platform_selected`, `platform_moved`).
  - Configured keyboard navigation: arrows for 1px X nudging and 16-line vertical row jumping; Delete/Backspace for removing selected platform.
- Implemented dedicated GUI controls in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Converted properties dock to a `QTabWidget` with tabs: "Tiles & Elements" and "Hardware Platforms".
  - Created platform creator panel: resource type selector, width dropdown with valid sizes, row picker, and X position spinbox.
  - Created selected platform properties panel: type, position, width, height (fixed 8), row index, and dynamic row resource usage counter (`Sprites: M/3, Missiles: N/4`).
  - Added platform list widget and warning dialogs (`QMessageBox.warning`) preventing actions that violate per-row hardware resource limits.
- Added comprehensive automated test suite in [tests/test_platform_editor.py](tests/test_platform_editor.py) (23 tests):
  - Tested all allowed widths, rejection of invalid widths, and fixed 8px height.
  - Tested vertical row acceptance (`y = 8, 24, 40`) and rejection (`y = 0, 16, 32`, out-of-bounds).
  - Tested hardware row limits: 3 sprites accepted, 4th rejected; 4 missiles accepted, 5th rejected; independent resource counting; resource freeing upon deletion; resource recalculation upon row transfers.
  - Tested JSON serialization round-trip, invalid data validation, and legacy file loading.
  - Tested Undo/Redo for adding, removing, moving, resizing, and changing types of platforms.
- Updated documentation in [atari-scene-editor/README.md](atari-scene-editor/README.md) and [README.md](README.md).

## [2026-10-14] - Configurable Scene Resolution (Default 160x192)

- Updated [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py) to support configurable per-scene resolution with default `160 × 192`, constraints `16 <= width <= 320` and `16 <= height <= 256`, and out-of-bounds element detection.
- Updated [atari-scene-editor/src/scene_editor/json_serializer.py](atari-scene-editor/src/scene_editor/json_serializer.py) to serialize/deserialize scene `width` and `height`, migrating legacy unversioned files to `160 × 96` and new default files to `160 × 192`.
- Added `ResizeSceneCommand` in [atari-scene-editor/src/scene_editor/commands.py](atari-scene-editor/src/scene_editor/commands.py) for Undo/Redo support on scene dimension changes.
- Added `NewSceneDialog` in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py) prompting for scene name, width, and height with presets. Added resolution spinboxes in scene properties dock.
- Added automated test suite [tests/test_scene_resolution.py](tests/test_scene_resolution.py) (10 tests). All tests pass.


## [2026-10-14] - Support Multiple Graphic Sources on a Single Scene

- Removed single-graphic constraint from [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py): elements now independently store their own `source` graphics path; added `Scene.get_sources()` helper.
- Updated [atari-scene-editor/src/scene_editor/json_serializer.py](atari-scene-editor/src/scene_editor/json_serializer.py) to serialize scenes with multiple tile sources cleanly, preserving element-level `source` paths and backwards compatibility with legacy projects.
- Updated [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Removed tile source blocking in `_on_add_element_requested`, allowing elements from different tilesets to be added dynamically without resetting the scene.
  - Updated layer list items and scene properties panel to display element-specific graphic filenames and all active tilesets.
  - Updated `open_scene` to validate all unique graphic sources used across elements and warn on missing files without crashing or dropping elements.
- Added [examples/sample_multisource_scene.json](examples/sample_multisource_scene.json) combining `tiles/castles.png` and `tiles/trees.png`.
- Added [tests/test_multi_source.py](tests/test_multi_source.py) containing 10 comprehensive tests covering adding from multiple files, overlap, independent `flip_x`, draw order preservation, JSON round-trip, Undo/Redo, and missing source fallback.
- Updated [tests/test_scene_model.py](tests/test_scene_model.py) and [tests/test_gui_integration.py](tests/test_gui_integration.py) to assert multi-source support. All 71 tests pass.
- Updated documentation in [atari-scene-editor/README.md](atari-scene-editor/README.md) and root [README.md](README.md).

## [2026-10-14] - Add Console Script Entry Point for atari-scene-editor

- Added [atari-scene-editor/pyproject.toml](atari-scene-editor/pyproject.toml) declaring `[project.scripts]` entry point `atari-scene-editor = "scene_editor.app:main"`.
- Installed package in editable mode (`pip install -e ./atari-scene-editor`) and added `-e ./atari-scene-editor` to [requirements.txt](requirements.txt).
- Enabled direct terminal execution via `atari-scene-editor` without typing `python`.
- Updated [atari-scene-editor/src/scene_editor/app.py](atari-scene-editor/src/scene_editor/app.py), [atari-scene-editor/README.md](atari-scene-editor/README.md), and root [README.md](README.md) with the new execution command.

## [2026-10-14] - Relocate Scene Editor to atari-scene-editor Subdirectory

- Moved `src/` to [atari-scene-editor/src](atari-scene-editor/src) and tool documentation to [atari-scene-editor/README.md](atari-scene-editor/README.md).
- Added [atari-scene-editor/main.py](atari-scene-editor/main.py) as the dedicated tool entry point with `--help` CLI option.
- Created root [README.md](README.md) for the "Call of the Wintermoon" Atari 8-bit game project, organizing tools, scripts, and assets.
- Updated [atari-scene-editor/src/scene_editor/asset_manager.py](atari-scene-editor/src/scene_editor/asset_manager.py) and [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py) to resolve the game project root and `tiles/` directory automatically via `find_project_root()`.
- Updated test suite [tests/](tests/) to import from `atari-scene-editor/src`. Verified all 61 tests pass.

## [2026-10-14] - Implement Atari 8-Bit Scene Editor (atari-scene-editor)

- Implemented full desktop GUI application for designing 160x96 Atari 8-bit platformer screens using PySide6.
- Added [src/scene_editor/scene_model.py](src/scene_editor/scene_model.py): Core data models (`Scene`, `SceneElement`, `Rect`, `Position`) enforcing 160x96 fixed dimensions, unique element IDs, single tile graphic invariant per scene, horizontal flip (`flip_x`), integer pixel precision, and draw order management.
- Added [src/scene_editor/json_serializer.py](src/scene_editor/json_serializer.py): Versioned schema (`schema_version: 1`) JSON serialization/deserialization with atomic writing (`os.replace` via temporary files), relative path conversion, and validation of source graphic files.
- Added [src/scene_editor/asset_manager.py](src/scene_editor/asset_manager.py): Graphics management for `tiles/` directory supporting PNG, BMP, GIF, and JPEG with thumbnail caching, non-destructive cropping, crop bounds validation, and horizontal flip via `QTransform`.
- Added [src/scene_editor/commands.py](src/scene_editor/commands.py): `QUndoCommand` implementations for Add, Remove, Move, Flip, Reorder, and Property modifications.
- Added [src/scene_editor/scene_items.py](src/scene_editor/scene_items.py) and [src/scene_editor/scene_view.py](src/scene_editor/scene_view.py): Pixel-perfect nearest-neighbor rendering (`QGraphicsView` / `QGraphicsScene`), custom non-destructive selection highlight, out-of-bounds warning indicators, toggleable helper grids (Off, 4x8, 8x8, 16x16), and keyboard nudging (1px/4px).
- Added [src/scene_editor/tile_browser.py](src/scene_editor/tile_browser.py) and [src/scene_editor/crop_editor.py](src/scene_editor/crop_editor.py): Interactive tile library browser with thumbnails and crop editor supporting mouse drag selection, handle resizing, manual coordinate spinboxes, and crop validation.
- Added [src/scene_editor/main_window.py](src/scene_editor/main_window.py) and [src/scene_editor/app.py](src/scene_editor/app.py): Complete main window integrating menus, shortcuts (`Ctrl+N`, `Ctrl+O`, `Ctrl+S`, `Ctrl+Shift+S`, `Ctrl+Z`, `Ctrl+Y`, `Delete`, `F`/`H`), dockable property panels, layers list, and unsaved changes prompts.
- Added [main.py](main.py) and [src/scene_editor/__main__.py](src/scene_editor/__main__.py) for running via `python main.py` and `python -m scene_editor`.
- Added example scenes in [examples/sample_castle_scene.json](examples/sample_castle_scene.json) and [examples/sample_forest_scene.json](examples/sample_forest_scene.json).
- Added comprehensive unit and integration test suites:
  - [tests/test_scene_model.py](tests/test_scene_model.py) (14 tests)
  - [tests/test_json_serializer.py](tests/test_json_serializer.py) (8 tests)
  - [tests/test_asset_manager.py](tests/test_asset_manager.py) (7 tests)
  - [tests/test_scene_operations.py](tests/test_scene_operations.py) (6 tests)
  - [tests/test_gui_integration.py](tests/test_gui_integration.py) (4 tests)
- Added technical documentation in [README.md](README.md) and updated [requirements.txt](requirements.txt).

## [2026-10-14] - Add Project .gitignore

- Created [.gitignore](.gitignore) covering Python bytecode and cache directories, pytest/coverage/lint caches, virtual environments, Atari 8-bit build outputs (`*.xex`, `*.fnt`, `gen/`), and editor/OS metadata.

## [2026-10-14] - Relocate Charset Generator to scripts Directory

- Moved `png_to_charset.py` to [scripts/png_to_charset.py](scripts/png_to_charset.py).
- Updated [tests/test_png_to_charset.py](tests/test_png_to_charset.py) to configure `sys.path` dynamically for importing modules from `scripts/`.
- Verified all 22 pytest unit and integration tests pass cleanly.

## [2026-10-14] - Implement Atari 8-bit Charset Generator from PNG

- Added [png_to_charset.py](png_to_charset.py): CLI tool converting 4-color indexed PNG images into Atari 8-bit charset binary files (`.fnt`, 1024 bytes) and JSON tile mapping.
  - Implemented 4x8 pixel tile extraction and 2-bit color index pixel packing (`(p0 << 6) | (p1 << 4) | (p2 << 2) | p3`) into 8 bytes per character.
  - Added strict image validation: file existence, PNG format, palette mode `P`, dimensions divisible by 4 (width) and 8 (height), exactly 4 used colors `{0, 1, 2, 3}`.
  - Implemented character deduplication preserving order of first appearance and enforced 128 character capacity limit with full unique pattern reporting on overflow.
  - Implemented atomic file writing to prevent partial outputs on validation, capacity, or I/O errors, along with collision detection.
- Added [tests/test_png_to_charset.py](tests/test_png_to_charset.py): 22 automated pytest unit and integration tests covering all 18 specification requirements.
- Added [requirements.txt](requirements.txt) with dependencies `pillow>=10.0.0` and `pytest>=8.0.0`.
