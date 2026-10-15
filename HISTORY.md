# Project History

<!-- AGENT INSTRUCTIONS: Add new entries below this comment. Use format: ## [YYYY-MM-DD] - [Brief Title] -->

## [2026-10-15] - Scene Title Card Screen with Centered ANTIC 2 Display List & Fade Sequence

- **Generated 40-Character Centered Screen Codes in Scene Compiler** in [scripts/compile_scenes.py](scripts/compile_scenes.py):
  - Added `POLISH_CHARS` diacritic mapping and `char_to_atari_screencode(c)` converting ASCII/Unicode to Atari ANTIC Mode 2 internal screen codes.
  - Added `text_to_screencodes_line(text, width=40)` to pre-center scene names into 40-character screen lines at build time.
  - Emitted `scene_{symbol}_name_line` per scene and master index pointer tables `scene_name_line_lo` / `scene_name_line_hi` in [gen/scenes_data.asm](gen/scenes_data.asm).
- **Added Centered ANTIC 2 Display List** in [main.asm](main.asm):
  - Defined `dlist_scene_title` in segment `GAME_DLIST` ($3F00) safely below 1 KB boundary ($3F88): 92 blank scanlines (11x `DL_BLANK8` + 1x `DL_BLANK4`), 1 line of ANTIC Mode 2 with LMS (`dlist_scene_title_addr`, 8 scanlines), 92 blank scanlines, and `DL_JVB` back to `dlist_scene_title` (total 192 scanlines, perfectly centered vertically).
  - Relocated [engine/render.asm](engine/render.asm) code into segment `RENDER_ADDR = $7A00` alongside lookup tables, freeing 300+ bytes in code segment at `$2000`.
- **Implemented Frame-Driven Title Card Phase State Machine** in [scenes/game.asm](scenes/game.asm):
  - Added game sub-phases: `GAME_PHASE_TITLE_IN` (0), `GAME_PHASE_TITLE_HOLD` (1), `GAME_PHASE_TITLE_OUT` (2), `GAME_PHASE_PLAYING` (3).
  - Added green luminance fade table `scene_title_fade_colors` ($00, $C2, $C4, $C6, $C8, $CA, $CC, $CE).
  - `game_init`: pre-renders playfield into `GAME_VRAM` ($3000), points `dlist_scene_title_addr` to active scene name line, sets font to `intro_font` ($24), sets colors to black, and switches `SDLSTL` to `dlist_scene_title`.
  - `game_run`:
    - Phase 0: Smooth 24-frame fade-in (8 luminance steps x 3 frames = ~0.48s).
    - Phase 1: 100-frame hold (~2.0s at 50 Hz PAL) with optional debounced button/key skip.
    - Phase 2: Smooth 24-frame fade-out (8 luminance steps x 3 frames = ~0.48s).
    - Transition: switches `SDLSTL` to `dlist_game` ($3F00) and restores scene gameplay palette via `set_scene_palette`.
- **Added Automated Emulation & Unit Tests**:
  - Added screen code unit tests in [tests/test_compile_scenes.py](tests/test_compile_scenes.py) verifying ASCII, Polish diacritics, and 40-character centering.
  - Added py65 6502 emulation test `test_scene_title_card_frame_progression` in [tests/test_state_machine_and_fade.py](tests/test_state_machine_and_fade.py) validating the complete 148-frame progression (fade in -> 100-frame hold -> fade out -> playfield display list swap).
  - All 288 automated tests pass and memory validation passes with 3,984 bytes headroom.


## [2026-10-15] - Switch Gameplay Graphics Mode to ANTIC $0D (Graphics 7)

- **Switched Gameplay Display List to ANTIC Mode D ($0D)** in [main.asm](main.asm):
  - Updated `dlist_game` from `DL_MODE_E` ($0E) to `DL_MODE_D` ($0D) with `DL_MODE_D | DL_LMS` at `$3000` followed by 95 mode lines of `DL_MODE_D`.
  - In ANTIC Mode D, each mode line spans 2 scanlines (totaling 192 scanlines for full-screen display height), preserving 160x96 2bpp resolution with 3,840 bytes of VRAM while avoiding 7,680-byte 192-line Mode E VRAM expansion.
- **Updated State Handlers and Renderers** in [scenes/game.asm](scenes/game.asm) and [engine/render.asm](engine/render.asm):
  - Updated gameplay DMA comments and mode documentation.
- **Updated Automated Validation and Tests** in [scripts/check_memory.py](scripts/check_memory.py) and [tests/test_convert_tiles.py](tests/test_convert_tiles.py):
  - Updated `check_memory.py` segment label for `$3000` to `Gameplay VRAM (ANTIC Mode D 160x96) + DLIST`.
  - Updated DLIST assertions in `test_convert_tiles.py` to assert `0x4D` (`DL_MODE_D | DL_LMS`) and `0x0D` (`DL_MODE_D`).
  - Confirmed all 285 tests pass and memory validation passes with 4,386 bytes headroom via `make all`.

## [2026-10-15] - Playfield Background Renderer (ANTIC Mode E) & Hardware Horizontal Flip

- **Implemented Core Renderer Engine** in [engine/render.asm](engine/render.asm):
  - Created `clear_game_vram` clearing all 3,840 bytes of gameplay playfield VRAM ($3000-$3EFF) using an unrolled 15-page loop (~21,000 cycles).
  - Created `render_scene_background`: parameterized background graphics renderer accepting scene index in `A` (`0..SCENE_COUNT-1`).
  - Automatically configures Atari GTIA color palette registers (`COLBK`, `COLPF0..COLPF2`, and OS shadows `COLOR4`, `COLOR0..COLOR2`) from the scene's primary tileset.
  - Computes source tileset bitmap row offsets from 16-bit row tables and playfield row offsets from precomputed lookup tables.
  - Implemented boundary clipping against screen bounds (40 bytes / 96 scanlines) preventing memory overruns.
  - Implemented 2bpp horizontal flipping (`flip_x`): inverts pixel bit ordering using precomputed lookup table `flip_byte_2bpp` and reverses byte order across the scanline.
- **Created Precomputed Render Lookup Tables** in [engine/render_tables.asm](engine/render_tables.asm):
  - `flip_byte_2bpp` (256 bytes): swaps pixel 0 <-> pixel 3 and pixel 1 <-> pixel 2.
  - `playfield_row_lo` and `playfield_row_hi` (192 bytes): 96 precomputed addresses for Mode E scanlines at `$3000`.
  - Allocated in memory segment `RENDER_TABLES = $7A00` ($7A00-$7BCA, 459 bytes) within free RAM before `$8000`.
- **Integrated Scene Rendering in Gameplay State** in [scenes/game.asm](scenes/game.asm):
  - Updated `game_init` to invoke `render_scene_background` with `SCENE_SC_01_FOREST_ID` (Scene 0 - Forest).
  - Screen displays rendered forest background when transitioning to `STATE_GAME`.
- **Added Automated Pytest Test Harness** in [tests/test_render_scene.py](tests/test_render_scene.py):
  - Tested `clear_game_vram` verifying 100% of bytes in `$3000-$3EFF` are cleared to 0.
  - Tested `flip_byte_2bpp` verifying exact 2-bit pixel reversal across all 4 pixel positions.
  - Tested `render_scene_background` on Scene 0 (Forest) and Scene 1 (Castle) verifying correct GTIA palette configuration, active scene ID update, and non-zero blitted graphics at expected element coordinates.
  - Verified full test suite (285 passed) and memory check (4,386 bytes headroom) via `make all`.

## [2026-10-15] - Automated Scene Compiler & Structure-of-Arrays 6502 Engine Data Integration

- **Created Scene Compilation Tool** in [scripts/compile_scenes.py](scripts/compile_scenes.py):
  - Parses scene definitions listed in [scenes/scenes.json](scenes/scenes.json) and resolves tilesets, element dimensions/coordinates, platforms, and entities.
  - Cross-references entity definition IDs with [enemies.json](enemies.json) and [secrets.json](secrets.json) to resolve Atari GTIA colors and blink flags.
  - Automatically associates objects with platform indices and calculates resting vertical positions (`platform.y - 8`).
  - Generates Structure-of-Arrays (SoA) tables in [gen/scenes_data.asm](gen/scenes_data.asm) containing per-scene element, platform, and object tables plus master indexing pointer tables for `O(1)` runtime scene loading (`LDX active_scene_id`).
- **Integrated Scene Compilation into Build Pipeline** in [Makefile](Makefile):
  - Added `data: $(SCENES_ASM)` rule compiling scene data whenever [scenes/scenes.json](scenes/scenes.json), scene JSON files, or catalogue definitions change.
  - Added `$(SCENES_ASM)` as prerequisite to `$(TARGET)` (`call_of_the_wintermon.xex`).
- **Mapped Scene Structures into 6502 Memory Map** in [main.asm](main.asm):
  - Allocated segment `SCENES_DATA = $2D00` ($2D00-$2EF8, 505 bytes) in available RAM before gameplay VRAM ($3000), preserving strictly ascending `org` order.
  - Included `gen/scenes_data.asm` into assembly.
- **Updated Memory Map Validation** in [scripts/check_memory.py](scripts/check_memory.py):
  - Registered segment `$2D00` as `Scene Definitions & Object Tables`.
- **Added Automated Pytest Test Suite** in [tests/test_compile_scenes.py](tests/test_compile_scenes.py):
  - Verified symbol sanitization, tileset ID resolution, catalogue lookups, scene parsing, and end-to-end ASM generation.
  - Verified presence of all generated scene and table symbols in compiled `gen/main.lab`.
  - Confirmed all 281 tests pass and memory validation passes with 5,257 bytes headroom.

## [2026-10-15] - Add Game Scenes Order Manifest (scenes/scenes.json)

- **Created scenes order manifest** in [scenes/scenes.json](scenes/scenes.json):
  - Defined the list and sequence of game scenes (`01-forest.json`, `02-forest-castle.json`).
  - Formatted as a JSON object with `"scenes"` array for game level progression.

## [2026-10-15] - Simplification of Secret Dependency UI and Scene-Isolated Progress Runtime

- **Refactored Secrets Catalogue UI to Pure Type-Based Dependencies** in [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py):
  - Removed all `Stage 1`, `Stage 2`, and `(Stage X -> Unlocks Stage Y)` text from the Dependency dropdown, label, and secrets list items.
  - Dependency dropdown now clearly displays `None (dostępny od początku sceny)` for root secrets and clean prerequisite names: `Name [ID]` (e.g. `Gold Key [ID: 11]`).
  - Replaced the `Stage in Chain` label with an intuitive `Unlock Condition (Warunek):` label displaying either `"Available from the start of the scene (no dependency)"` or `"Unlocks after collecting all '<Prerequisite>' secrets on the scene"`.
  - Secrets list widget displays clean annotations: `Name [ID] (from start)` or `Name [ID] (requires: <Prerequisite>)`.
- **Refactored Scene Runtime for Strict Multi-Scene Isolation** in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py):
  - Refactored [SceneSecretRuntime](atari-scene-editor/src/scene_editor/scene_model.py) so unlock checks evaluate prerequisite secret types on the specific scene instance.
  - Secret collection progress is strictly isolated per scene: collecting keys on Scene 1 leaves doors on Scene 2 locked.
  - A dependent secret type unlocks only when all instances of its prerequisite type on the current scene are collected.
  - Preserved backward-compatible helper properties (`current_stage`, `is_stage_complete`) while keeping internal state purely type- and scene-driven.
- **Added Integration Tests for Multi-Scene Isolation and Type Prerequisites** in [tests/test_catalogues.py](tests/test_catalogues.py) and [tests/test_scene_objects.py](tests/test_scene_objects.py):
  - Added `test_dependencies_work_across_multiple_scenes_with_isolated_progress` verifying Scene 1 actions do not unlock Scene 2.
  - Added `test_unlock_requires_all_secrets_of_dependent_type_on_scene` verifying partial collection does not unlock dependent types.
  - Updated UI tests to assert absence of `Stage` text and presence of prerequisite descriptions.
  - Verified full test suite (271 passed) and memory check via `make all`.


## [2026-10-15] - Linear Dependency Chain for Secrets & Stage-Based Row Limit Validation

- **Extended Secrets Catalogue Data Model** in [atari-scene-editor/src/scene_editor/catalogue_model.py](atari-scene-editor/src/scene_editor/catalogue_model.py):
  - Added `dependency: Optional[int] = None` to `SecretDefinition` with backward-compatible JSON serialization (`to_dict` / `from_dict`).
  - Implemented single linear dependency chain validation in `ProjectCatalogues`: rejects cycles, branching (multiple dependents on the same predecessor), and multiple independent chains.
  - Added `get_secret_stage()`, `get_all_secret_stages()`, and `get_valid_dependencies_for()` to dynamically compute topological stage numbering and filter valid predecessor candidates.
  - Implemented deletion guards in `remove_secret()` to prevent deleting secrets referenced as dependencies, and automatic ID cascading in `update_secret()`.
- **Refined Row Limits and Scene Validation** in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py):
  - Separated hardware object limits: `MAX_ENEMIES_PER_ROW = 3` (Players P1-P3) and `MAX_SECRETS_PER_STAGE = 4` (Missiles M0-M3).
  - Updated `can_add_object_to_platform()`, `add_object()`, `move_object()`, and `Scene.validate()`: secrets in the same row are validated per-stage. Up to 4 secrets per stage are allowed per row, enabling multiple stages (e.g. 4 Stage 1 + 4 Stage 2 = 8 secrets) to occupy the same row and positions without exceeding hardware capacity.
  - Implemented `SceneSecretRuntime` to simulate single-scene gameplay progression: activates Stage 1 at start, automatically unlocks the next stage upon collecting all secrets of the current stage, prevents collected secrets from reappearing, and triggers scene transition upon finishing the final stage.
- **Enhanced Catalogue & Scene Editor UI** in [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py) and [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Added dependency selector (`QComboBox`) and dynamic stage indicator label (`QLabel`) in Secret Details panel.
  - Displayed stage badges and dependency links in catalogue list items (`[Stage X] Name [ID] (after: ...)`).
  - Integrated `self.catalogues` into `MainWindow.scene_model` for real-time stage-aware placement validation.
- **Unit and Integration Test Suites** in [tests/test_catalogues.py](tests/test_catalogues.py) and [tests/test_scene_objects.py](tests/test_scene_objects.py):
  - Added tests covering legacy backward compatibility, linear chain rules, cycle/branching prevention, 4-secrets-per-stage validation, row position sharing, and runtime progression.
  - Verified full test suite (269 passed) and memory map validation via `make all`.

## [2026-10-15] - Memory Reservation for Gameplay VRAM (ANTIC E 160x96) & PMG Buffer

- **Reserved dedicated Gameplay Playfield VRAM (`GAME_VRAM`)** in [main.asm](main.asm):
  - Address: `$3000` (aligned to a 4 KB boundary: `$3000-$3EFF`).
  - Size: 3,840 bytes ($40 \text{ bytes/line} \times 96 \text{ lines}$).
  - Hardware advantage: Because the entire 3,840-byte buffer lies strictly inside the 4 KB page `$3000-$3FFF`, ANTIC's 12-bit address counter never wraps, eliminating the need for any mid-screen LMS instructions.
- **Created Gameplay Display List (`dlist_game`)** in [main.asm](main.asm):
  - Address: `GAME_DLIST = $3F00` (107 bytes: `$3F00-$3F6A`, aligned within `$3C00-$3FFF`, no 1 KB boundary crossing).
  - Structure: 3x top blank scanlines (`DL_BLANK8`), 1x mode line with LMS (`DL_MODE_E | DL_LMS` pointing to `$3000`), 95x `DL_MODE_E` lines, 3x bottom blank scanlines (`DL_BLANK8`), and `DL_JVB` back to `dlist_game`.
- **Reserved Player-Missile Graphics buffer (`PMG_ADDR`)** in [main.asm](main.asm):
  - Address: `$6800` (2 KB boundary aligned: `$6800-$6FFF`, `PMBASE = $68`).
  - Size: 2,048 bytes (supports both 1-line single-line resolution and 2-line double-line resolution).
  - Equates defined: `PMBASE_PAGE = $68`, `PMG_MISSILES = $6B00`, `PMG_PLAYER0 = $6C00`, `PMG_PLAYER1 = $6D00`, `PMG_PLAYER2 = $6E00`, `PMG_PLAYER3 = $6F00`.
- **Updated Gameplay State Initializer** in [scenes/game.asm](scenes/game.asm):
  - Configures `SDLSTL`/`SDLSTH` (and direct `DLISTL`/`DLISTH`) to point to `dlist_game`.
  - Sets `PMBASE` hardware register to `$68`.
  - Applies default Forest palette from `tileset_trees` (`COLOR4/COLBK = $00`, `COLOR0/COLPF0 = $C4`, `COLOR1/COLPF1 = $C8`, `COLOR2/COLPF2 = $DC`).
  - Enables ANTIC Mode E playfield DMA (`$22` into `SDMCTL` and `DMACTL`).
- **Enhanced Memory Checker** in [scripts/check_memory.py](scripts/check_memory.py):
  - Automatically identifies and labels known subsystem segments: Engine Code, Fonts, Intro, Tileset Metadata, Gameplay VRAM & DLIST, Title Screen VRAM & DLIST, PMG + Audio, and Tileset Bitmaps.
  - Accurately tracks total user allocation (**35,198 bytes**) and remaining contiguous/total headroom (**5,762 bytes** below `$C000`).
- **Added Automated Emulation Tests** in [tests/test_convert_tiles.py](tests/test_convert_tiles.py):
  - `test_gameplay_vram_and_pmg_reservation`: Verifies addresses, 4 KB alignment of VRAM, 2 KB alignment of PMG, 107-byte display list structure, and py65 emulation of `game_init` setting `PMBASE=$68` and `SDLSTL=$3F00`.
  - Full test suite passing: 242 tests.

## [2026-10-15] - ANTIC Mode E Tileset Conversion & Memory Integration

- **Developed ANTIC Mode E tile conversion pipeline** in [scripts/convert_tiles.py](scripts/convert_tiles.py):
  - Scans `tiles/` folder directly (excluding subdirectories like `tiles/org`).
  - Supports both indexed mode `P` images (`castles.png`, `depths.png`, `trees.png`) and true-color RGB (`hell.png`).
  - Implemented 1D k-means luminance clustering for RGB graphics: classifies background ($\le 10$ lum) as index 0 and non-black pixels into 3 distinct tone levels (1=dark, 2=mid, 3=highlight).
  - Packs 4 pixels per byte in ANTIC Mode E format (2bpp, MSB leftmost: `(p0<<6)|(p1<<4)|(p2<<2)|p3`), padding incomplete bytes with background color.
  - Generates binary bitmapped assets:
    - [gen/tiles_castles.bin](gen/tiles_castles.bin) (270x44 px, 68 B/line, 2,992 bytes)
    - [gen/tiles_depths.bin](gen/tiles_depths.bin) (360x72 px, 90 B/line, 6,480 bytes)
    - [gen/tiles_hell.bin](gen/tiles_hell.bin) (291x57 px, 73 B/line, 4,161 bytes)
    - [gen/tiles_trees.bin](gen/tiles_trees.bin) (246x42 px, 62 B/line, 2,604 bytes)
    - Total tiles payload: 16,237 bytes across 4 tilesets.
- **Generated MADS 6502 assembly descriptors and SoA tables** in [gen/tiles_data.asm](gen/tiles_data.asm):
  - Equates: `TILESET_CASTLES=0`, `TILESET_DEPTHS=1`, `TILESET_HELL=2`, `TILESET_TREES=3`, `TILESET_COUNT=4`.
  - Dimensions & pitch constants (`TILESET_*_W_PX`, `TILESET_*_W_BYTES`, `TILESET_*_H_LINES`, `TILESET_*_SIZE`).
  - Structure-of-Arrays (SoA) tables: `tileset_w_px_lo/hi`, `tileset_w_bytes`, `tileset_h_lines`, `tileset_size_lo/hi`, `tileset_data_lo/hi`.
  - Recommended Atari GTIA color palette registers for each tileset (`tileset_colbk`, `tileset_colpf0`, `tileset_colpf1`, `tileset_colpf2`).
  - Precomputed row offset tables (`tiles_*_row_lo/hi` for $y \times \text{stride}$) and pointers (`tileset_row_table_lo/hi`) for $O(1)$ fast indexed blitting.
- **Integrated tiles into game memory architecture** in [main.asm](main.asm):
  - Allocated `TILES_META` at `$2B00` (486 bytes: `$2B00-$2CE5`) in the gap between intro display list and title VRAM.
  - Added early boot vector `init_disable_basic` (`ini`) before tiles payload to disable BASIC ROM (`PORTB |= $02`), ensuring `$A000-$BFFF` RAM is writable during XEX loading.
  - Allocated `TILES_ADDR` at `$8000`: all 4 tileset binaries reside contiguously in `$8000-$BF6C` (16,237 bytes), strictly below `$C000`.
- **Integrated build automation** in [Makefile](Makefile):
  - Added `tiles` target and dependencies on `scripts/convert_tiles.py` and `$(TILES_SRCS)`.
  - Added tile binaries and ASM descriptors as prerequisites for binary assembly `$(TARGET)`.
- **Automated verification & testing**:
  - Added unit, packing, and integration tests in [tests/test_convert_tiles.py](tests/test_convert_tiles.py).
  - py65 CPU emulation test verifying memory layout, symbol addresses, SoA tables, and row offset lookups directly from the compiled binary.
  - Full suite passes: 241 tests, memory checker confirms 29,145 bytes user RAM allocated with 11,815 bytes available headroom below `$C000`.

## [2026-10-15] - Intro Screen in ANTIC Mode 2 with Polish Diacritics & Text Source

- **Implemented Intro Screen text generation pipeline** in [scripts/gen_intro_text.py](scripts/gen_intro_text.py):
  - Reads 10 story lines from [texts/intro.txt](texts/intro.txt) instead of hardcoded strings.
  - Automatically calculates horizontal centering for each line across 40 columns (`left_pad = (40 - len) // 2`).
  - Implemented new custom font Polish character mappings:
    - Uppercase (`Ą, Ć, Ę, Ł, Ń, Ó, Ś, Ź, Ż` -> `65, 66, 67, 68, 69, 70, 71, 72, 73`).
    - Lowercase (`ą, ć, ę, ł, ń, ó, ś, ź, ż` -> `81, 82, 83, 84, 85, 86, 87, 88, 89`).
  - Outputs 400-byte raw screen VRAM binary [gen/intro_text.bin](gen/intro_text.bin).
- **Added Polish 8-bit character font**:
  - Integrated 1,024-byte font [fonts/font.fnt](fonts/font.fnt) containing the updated Polish diacritics layout.
  - Placed at 1 KB boundary `$2400` (`FONT_ADDR`), referenced by `CHBASE = $24`.
- **Created ANTIC 2 Display List with 8-line spacing** in [main.asm](main.asm) and [scenes/intro.asm](scenes/intro.asm):
  - Total vertical layout: 3x `DL_BLANK8` (top margin) + 10x `DL_MODE_2` text lines with 9x `DL_BLANK8` (8 blank scanlines between each line) + 3x `DL_BLANK8` (bottom margin) + `DL_JVB`.
  - Configured colors: Light green text foreground (`COLOR1` / `COLPF1` = `$CA`, Hue $C, Lum $A), pure black background/border (`COLOR2` / `COLOR4` = `$00`).
  - Display list located at `$2A00` (`INTRO_DLIST`), text VRAM at `$2800` (`INTRO_VRAM`).
- **Updated build automation** in [Makefile](Makefile):
  - Added `$(INTRO_TXT_SRC)` dependency (`texts/intro.txt`), `$(INTRO_TXT_BIN)`, and `$(INTRO_FONT)` to targets.
  - Ensured `tests` depend on `$(TARGET)` so clean builds run binary assembly before py65 emulation tests.
- **Added automated tests** in [tests/test_intro_screen.py](tests/test_intro_screen.py):
  - Verified exact Polish character mappings (65..73 and 81..89) and file-based conversion from [texts/intro.txt](texts/intro.txt).
  - py65 emulation test verifying `intro_init` registers: `COLOR1` ($CA), `COLOR2` ($00), `CHBASE` ($24), and Display List pointer.
  - All 233 tests pass, memory validation confirms 12,411 bytes allocated with 28,549 bytes headroom below `$C000`.


## [2026-10-15] - State Machine & 28-Frame Title Fade-In with Music Trigger

- **Implemented game state machine architecture**:
  - In [zeropage.asm](zeropage.asm): Defined state equates (`STATE_TITLE=0`, `STATE_INTRO=1`, `STATE_GAME=2`, `STATE_OVER=3`) and state control variables (`game_state`, `current_state`, `title_first_run`, `fade_frame`, `fire_released`).
  - In [main.asm](main.asm): Built top-level dispatcher that detects state changes, calls `*_init` upon entry, and dispatches `*_run` each frame.
- **Implemented 28-frame smooth fade-in for title screen** in [scenes/title.asm](scenes/title.asm):
  - Formula: `(fade_frame >> 1) & $0E` smoothly increments foreground color (`COLOR1` / `COLPF1`) through even GTIA luminances (`$00, $02, ..., $0E`) over exactly 28 frames.
  - Music playback is delayed during fade-in and starts only upon reaching full brightness at frame 28 (`audio_play_title`).
  - Sets `title_first_run = 0` when fade-in finishes.
  - On re-entry from Game Over (`title_first_run == 0`), skips fade-in completely, displaying title image at full brightness (`$0E`) and playing music immediately.
  - Input polling (Joystick Fire `STRIG0` / Keyboard `CH`) with debounce stops music (`audio_stop`) and transitions to `STATE_INTRO`.
- **Created scene stubs with input debouncing**:
  - [scenes/intro.asm](scenes/intro.asm): blanks display, waits for Fire press to transition to `STATE_GAME`.
  - [scenes/game.asm](scenes/game.asm): blanks display, waits for Fire press to transition to `STATE_OVER`.
  - [scenes/gameover.asm](scenes/gameover.asm): blanks display, waits for Fire press to transition back to `STATE_TITLE`.
- **Automated verification & py65 testing**:
  - Added [tests/test_state_machine_and_fade.py](tests/test_state_machine_and_fade.py) with py65 MPU emulation:
    - Tested `title_init` on first run (`title_first_run == 1`): asserts color is `$00` and `fade_frame == 0`.
    - Tested `title_init` on subsequent runs (`title_first_run == 0`): asserts color is `$0E` and `fade_frame == 28` immediately.
    - Tested 28-frame luminance progression formula.
  - Added `py65>=1.1.0` to [requirements.txt](requirements.txt).
  - Updated [Makefile](Makefile) with scene sources in `ASM_SRCS`.
  - All 230 unit/integration/emulation tests pass (`make all`).


## [2026-10-15] - Title Screen Music Integration (Atari Music Composer & POKEY Player)

- **Created music compilation pipeline** in [scripts/compile_music.py](scripts/compile_music.py):
  - Uses `atari_music` library (`load_composition_json`, `generate_music_from_composition`, `export_mads_asm`) to compile [music/title.json](music/title.json) into relocatable MADS assembly [gen/title_music.asm](gen/title_music.asm) with label `music_title_data`.
  - Song "Horde of the North" by Chiptune Necromancer (140 BPM, D minor, 4 channels with 16-bit coupled bass on Ch1+Ch2).
- **Added audio subsystem wrapper** in [lib/audio.asm](lib/audio.asm):
  - Integrates 4-channel relocatable driver [lib/player.asm](lib/player.asm).
  - Implements `audio_play_title` (initializes song via `music_init` and triggers playback with `music_play`), `audio_update` (advances playback by 1 frame), and `audio_stop` (stops and silences POKEY).
- **Configured Zero Page allocations** in [zeropage.asm](zeropage.asm):
  - Allocated `PLAYER_ZP_BASE = $90` ($90-$99, 10 bytes) for audio player track and temporary pointers, avoiding collision with engine variables ($80-$8F).
- **Integrated playback into title screen** in [main.asm](main.asm):
  - Calls `audio_play_title` at startup.
  - Updates music player once per 50 Hz frame (`audio_update`) synchronized with vertical blank via `RTCLOK`.
  - Allocated isolated audio segment at `$7000` (`$7000-$79CE`, 2,511 bytes: 886 bytes player + 1,618 bytes song data and structures), keeping music memory isolated from VRAM (`$4000-$5E0F`) and Display List (`$6000-$60C9`).
- **Updated build automation** in [Makefile](Makefile):
  - Added `music` target compiling `music/title.json` into `gen/title_music.asm`.
  - Updated dependencies and added `-i:lib` flag to MADS assembly command.
- **Added automated tests** in [tests/test_compile_music.py](tests/test_compile_music.py):
  - Verified music compilation, label generation, and error handling.
  - All 227 tests passing; memory validation verifies 10,495 bytes allocated with 30,465 bytes headroom below `$C000`.


## [2026-10-15] - Title Screen Implementation in ANTIC Mode F & Build Pipeline

- **Created image conversion tool for ANTIC Mode F** in [scripts/convert_image.py](scripts/convert_image.py):
  - Converts 320x192 1bpp PNG images into ANTIC Mode F (Graphics 8, 40 bytes/line) binary data.
  - Automatically splits image into two VRAM segments to respect ANTIC's 12-bit address 4 KB boundary wrap:
    - Segment 1: scanlines 0..101 (102 lines * 40 bytes = 4,080 bytes) at `$4000`.
    - Padding: 16 zero-bytes to align Segment 2 at `$5000`.
    - Segment 2: scanlines 102..191 (90 lines * 40 bytes = 3,600 bytes) at `$5000`.
    - Total output binary size: 7,696 bytes (`gen/title.bin`).
- **Created automated memory validation tool** in [scripts/check_memory.py](scripts/check_memory.py):
  - Parses Atari DOS `.xex` segments and verifies adherence to project architecture rules.
  - Asserts that no segment overlaps OS ROM (`$C000-$CFFF`, `$E000-$FFFF`) or Hardware registers (`$D000-$DFFF`), and all code/data ends at or below `$BFFF`.
  - Calculates total allocated RAM and reports remaining headroom below `$C000`.
- **Created assembly architecture for title screen**:
  - In [zeropage.asm](zeropage.asm): Defined user zero-page equates strictly in `$80-$FF`.
  - In [main.asm](main.asm):
    - Added startup routine disabling BASIC ROM (`PORTB |= $02`) to ensure full 64 KB RAM is accessible.
    - Configured ANTIC Mode F colors: Background black (`COLPF2` / `COLOR2` = `$00`, `COLBK` / `COLOR4` = `$00`), Foreground white (`COLPF1` / `COLOR1` = `$0E`).
    - Built Display List (`dlist_title`) at `$6000` with 24 top blank scanlines, two LMS mode F segments (`$4000` and `$5000`), and a `DL_JVB` loop.
    - Synchronized main loop with vertical blank via `RTCLOK` and reset `ATRACT` screensaver timer.
    - Set standard DOS run vector at `RUNAD` (`$02E0`).
- **Created cross-platform build automation** in [Makefile](Makefile):
  - Target binary set to `call_of_the_wintermon.xex`.
  - Integrated portable Python-based directory and cleanup helpers (`MKDIR`, `RM`).
  - Configured target chain: `assets -> data -> tests -> xex -> check_memory`.
  - Targets: `all`, `assets`, `data`, `tests`, `xex`, `check_memory`, `run`, `clean`.
- **Added automated tests** in [tests/test_convert_image.py](tests/test_convert_image.py):
  - Tested output binary length (7,696 bytes), pixel packing (MSB first), 16-byte padding at offset 4080, and dimension validation.
  - Verified full test suite passes (225 tests) and memory check validates `call_of_the_wintermon.xex` (7,978 bytes allocated with 32,982 bytes headroom).


## [2026-10-15] - Support Multi-Resource Hardware Platform Widths (Sprite & Missile)

- **Expanded hardware platform width lists and resource consumption logic** in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py):
  - Added new `SPRITE_WIDTHS`: `[4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96]`.
  - Added new `MISSILE_WIDTHS`: `[4, 8, 12, 16, 20, 24, 28, 32]`.
  - Implemented single shared calculation function `get_required_platform_resources(platform_type, width)`:
    - Sprite: `ceil(width / 32)` (4–32 px: 1 sprite, 36–64 px: 2 sprites, 68–96 px: 3 sprites).
    - Missile: `ceil(width / 8)` (4–8 px: 1 missile, 12–16 px: 2 missiles, 20–24 px: 3 missiles, 28–32 px: 4 missiles).
    - Rejects invalid platform types with `ModelValidationError` and invalid widths with `InvalidPlatformDimensionError`.
  - Added `required_resources` property on `PlatformElement`.
  - Updated `get_row_resource_usage()` to accumulate hardware resource units rather than raw platform count.
  - Updated `can_add_platform_to_row()`, `Scene.add_platform()`, `Scene.move_platform()`, `Scene.resize_platform()`, `Scene.set_platform_type()`, and `Scene.validate()` to validate hardware resource limits using platform width.
- **Updated UI controls and resource indicators** in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Populated creator width combo `new_plat_width_combo` and property panel `plat_prop_width_combo` with new allowed widths and resource counts.
  - Enforced resource validation and collision detection when resizing platform width (`_on_plat_prop_width_changed`) and changing type (`_on_plat_prop_type_changed`).
  - Updated row status labels and combo row labels to format resource usage as `Sprite: X/3, Missile: Y/4`.
  - Updated platform documentation in [atari-scene-editor/README.md](atari-scene-editor/README.md).
- **Automated Tests**:
  - In [tests/test_platform_editor.py](tests/test_platform_editor.py), added `TestPlatformResourceCalculation` and comprehensive tests covering all width intervals, limit checks, combinations (Sprite 96, 32+64, 32+32+32, 64+64 rejected; Missile 12+8, 12+12, 32+4 rejected), resize and move limits, and JSON load rejections.
  - In [tests/test_gui_integration.py](tests/test_gui_integration.py), added `test_platform_gui_resource_limit_rejection`.
  - In [tests/test_scene_objects.py](tests/test_scene_objects.py), made `test_load_01_forest_scene_with_numeric_objects` verify object count dynamically from the scene file.
  - Verified all 222 unit and integration tests pass.

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
