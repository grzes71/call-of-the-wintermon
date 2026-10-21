# Project History

<!-- AGENT INSTRUCTIONS: Add new entries below this comment. Use format: ## [YYYY-MM-DD] - [Brief Title] -->

## [2026-10-20] - 2+4+2 Glyph Conversion and 9-Value DLI Color Table

- **2+4+2 Glyph-to-2bpp Conversion ([scenes/title.asm](scenes/title.asm))**:
  - Replaced the 4+4 LUT mapping with a 2+4+2 bit-per-glyph mapping:
    - Bits 7–6 (pixels 0–1): `1 → 10` (`COLPF1`).
    - Bits 5–2 (pixels 2–5): `1 → 11` (`COLPF2`).
    - Bits 1–0 (pixels 6–7): `1 → 01` (`COLPF0`).
    - Bit `0` maps strictly to `00` (`COLBK`).
  - Updated explicit 16-byte lookup tables `title_text_lut_hi` and `title_text_lut_lo`.
- **Expanded DLI Playfield Colors (9 Values) ([scenes/title.asm](scenes/title.asm))**:
  - Added new default color constant `TITLE_COLOR_PF2_TEXT = $EE` (contrasting bright blue-white).
  - Defined 9 color constants (`TITLE_CALL_PF0/PF1/PF2`, `TITLE_OFTHE_PF0/PF1/PF2`, `TITLE_WINTER_PF0/PF1/PF2`).
  - Expanded `title_row_colors` to 9 bytes in RAM (`PF0`, `PF1`, `PF2` per title line).
  - Expanded DLI handlers `dli_title_color_call`, `dli_title_color_of_the`, and `dli_title_color_winter` to write `COLPF0`, `COLPF1`, and `COLPF2` (49 cycles each, well within the 114-cycle blank line budget).
  - Verified `COLPF2` isolation: `dli_title_scroll` sets `COLPF2 = $C0` at cycle 6 of scanline 0 of Mode 2 before pixel graphics rendering begins; preceding blank scanlines render background black (`COLBK = $00`), ensuring no color bleed onto the scroll line.
- **Font Column Usage & py65 Test Suite ([tests/test_title_text.py](tests/test_title_text.py))**:
  - Analyzed `intro_font` column usage for all title characters (`CALL`, `OF THE`, `WINTERMON`): verified that all 3 color bands (left: cols 0–1, center: cols 2–5, right: cols 6–7) contain active pixels across all characters.
  - Implemented independent `conv(b)` reference function in Python and verified equivalence against memory LUTs for all 256 byte values and test vectors.
  - Added structural pixel band verification replacing the legacy pair test.
  - Updated DLI handler tests to check 9-byte color vectors, 49 cycles, and allowed writes to `COLPF0`, `COLPF1`, `COLPF2`, and `VDSLST`.
  - All 448 automated unit and py65 tests and memory validation checks passed cleanly in `make all`.

## [2026-10-20] - Separate Colors (COLPF0/COLPF1) per Title Line via DLI

- **Title Screen Display List ([main.asm](main.asm))**:
  - Added `DL_DLI` (`$80`) bit to the 3 blank lines (`DL_BLANK8 | DL_DLI` = `$F0`) directly preceding each of the three title lines (`CALL`, `OF THE`, `WINTERMON`).
  - Total DLI count in `dlist_title` is now exactly 4 (3 blank line color DLIs + 1 marquee scroll line prolog DLI).
  - Maintained overall height (229 scanlines), binary size (99 bytes), and LMS addresses without modification.
- **Color Tables & Self-Resetting DLI Chain ([scenes/title.asm](scenes/title.asm))**:
  - Defined 6 color constants (`TITLE_CALL_PF0/PF1`, `TITLE_OFTHE_PF0/PF1`, `TITLE_WINTER_PF0/PF1`) defaulting to `$C4` / `$CA`.
  - Added 6-byte runtime-writable RAM table `title_row_colors` at `$41DC` (outside VRAM, scroll buffers, and DLI double buffers).
  - Implemented 3 lightweight DLI handlers (`dli_title_color_call`, `dli_title_color_of_the`, `dli_title_color_winter`), each executing in exactly 41 cycles without `WSYNC` (during blank lines with no playfield DMA) and chaining `VDSLST` to the next handler.
  - Updated `dli_title_scroll` to self-reset `VDSLST` back to `dli_title_color_call` at the end of every frame.
  - Updated `title_init` and `title_run` to point `VDSLST` to `dli_title_color_call`.
- **Automated Verification ([tests/test_title_text.py](tests/test_title_text.py), [tests/test_title_scroll.py](tests/test_title_scroll.py))**:
  - Added tests verifying exactly 4 DLI instructions in `dlist_title` at offsets 2, 13, 24, and 88.
  - Added parameterized test verifying color pair loading from `title_row_colors` into `COLPF0` / `COLPF1` and `VDSLST` progression across the entire chain.
  - Verified cycle counts (41 cycles each) and strict register / memory isolation (A, X, Y preserved; only `COLPF0`, `COLPF1`, `VDSLST` modified).
  - Verified full-frame 4-interrupt simulation and `title_run` fallback reset.
  - All 448 automated tests and memory architecture checks passed cleanly in `make all`.

## [2026-10-20] - External Title Text Compilation & Dynamic Centering

- **Data Compiler & Pipeline ([scripts/compile_title_text.py](scripts/compile_title_text.py), [Makefile](Makefile), [manifest.yaml](manifest.yaml))**:
  - Implemented `scripts/compile_title_text.py` converting lines from `texts/title.txt` into Atari ANTIC internal screen codes and automatically calculating symmetric horizontal centering offsets (`offset = (40 - length * 2) // 2`).
  - Generates `gen/title_text_data.asm` defining line lengths, centering offsets, bounds validation checks, and screen code tables with backward-compatible symbol aliases (`TITLE_CALL_*`, `TITLE_OF_THE_*`, `TITLE_WINTERMOON_*`).
  - Added `TITLE_TXT_SRC` / `TITLE_TXT_ASM` targets and prerequisites to `Makefile` and registered the new compiler script and text asset in `manifest.yaml`.
- **Title Screen Engine Integration ([scenes/title.asm](scenes/title.asm))**:
  - Removed hardcoded title line lengths and offsets from `scenes/title.asm` in favor of including `gen/title_text_data.asm`.
  - Display generator seamlessly renders any three title lines loaded from `texts/title.txt` (currently: `CALL` at offset 16, `OF THE` at offset 14, `WINTERMON` at offset 11).
- **Automated Verification ([tests/test_title_text.py](tests/test_title_text.py))**:
  - Updated test suite to dynamically parse `texts/title.txt`, verifying screen code memory tables, character counts, centering zero-margins, and buffer matching against reference model.
  - All 442 automated tests and memory architecture checks pass cleanly in `make all`.

## [2026-10-20] - Dual-Tone 2bpp Glyph Conversion for Title Text

- **Dual-Tone 2bpp Conversion Tables & Generator ([scenes/title.asm](scenes/title.asm))**:
  - Implemented dual-tone 2bpp glyph conversion where high nibble (bits 7-4, left 4 pixels) maps `0 -> 00`, `1 -> 10` (color `COLPF1`), and low nibble (bits 3-0, right 4 pixels) maps `0 -> 00`, `1 -> 01` (color `COLPF0`).
  - Added explicit 16-byte tables `title_text_lut_hi` (`$00, $02, ..., $AA`) and `title_text_lut_lo` (`$00, $01, ..., $55`), satisfying `lut_lo[n] == lut_hi[n] >> 1`.
  - Updated `title_text_generate` loop so the first byte of each destination pair reads `title_text_lut_hi,x` and the second byte reads `title_text_lut_lo,x`.
  - Added named constant `TITLE_COLOR_PF0 = $C4` (dark forest green) and initialized `COLOR0` and `COLPF0` in `title_init`, ensuring high contrast against black background (`COLBK = $00`) and clear distinction from `COLPF1 = $CA`.
- **Automated Verification ([tests/test_title_text.py](tests/test_title_text.py))**:
  - Updated Python test suite with independent mathematical reference formulas `hi(n)` and `lo(n)`.
  - Verified LUT memory contents, `lut_lo[n] == lut_hi[n] >> 1` relationship, and all test vectors (`$00`, `$FF`, `$F0`, `$0F`, `$9A`, `$81`).
  - Added `test_pixel_patterns_and_no_11_pairs` asserting left bytes contain only `%00`/`%10`, right bytes contain only `%00`/`%01`, and no `%11` pixel pairs exist across all title buffers.
  - Verified `COLPF0` / `COLOR0` initialization to `$C4` (non-zero, distinct from `COLBK` and `COLPF1`).
  - All 442 automated tests and memory architecture checks passed cleanly.

## [2026-10-20] - Procedural 2bpp Text Generator & Title Display List

- **Procedural 2bpp Text Generator ([scenes/title.asm](scenes/title.asm), [zeropage.asm](zeropage.asm))**:
  - Implemented `title_text_generate` converting 1bpp font glyphs (`intro_font` at `$2400`) to 2bpp pixel data (`0 -> 00`, `1 -> 10`) using a 16-byte nibble LUT (`title_text_lut`).
  - Added strict parameter validation enforcing `length in 1..20`, `x_offset < 40`, and `x_offset + 2*length <= 40` (with 8-bit overflow safety) returning Carry=1 on error with zero buffer modification, and Carry=0 on success.
  - Implemented `title_generate_all_texts` rendering `CALL` (ANTIC E, offset 16), `OF THE` (ANTIC D, offset 14), and `WINTERMOON` (ANTIC D, offset 10) into 320-byte buffers inside `GAME_VRAM` (`$3000-$33BF`).
  - Added assembly-time compile assertions verifying valid bounding parameters for all three static title lines.
  - Implemented 960-byte overlay memory clearing loop in `title_init` strictly erasing `$3000-$33BF` while leaving `$33C0` onwards untouched.
- **New Title Display List & Architecture ([main.asm](main.asm), [scenes/title.asm](scenes/title.asm))**:
  - Replaced the static 3,072-byte bitmap (`gen/title.bin`) with a procedural 99-byte Display List (`dlist_title` at `$6000`):
    - 24 blank scanlines top margin (3x `DL_BLANK8`)
    - `CALL`: ANTIC Mode E with LMS + 7 lines Mode E (8 scanlines)
    - 8 blank scanlines spacing (`DL_BLANK8`)
    - `OF THE`: ANTIC Mode D with LMS + 7 lines Mode D (16 scanlines)
    - 8 blank scanlines spacing (`DL_BLANK8`)
    - `WINTERMOON`: 16 lines ANTIC Mode D with explicit LMS per row repeating each of the 8 source rows twice (32 scanlines)
    - 110 blank scanlines padding (13x `DL_BLANK8` + 1x `DL_BLANK6`)
    - 3 blank scanlines DLI prolog (`DL_BLANK1`, `DL_BLANK1 | DL_DLI`, `DL_BLANK1`)
    - 1 line ANTIC Mode 2 hardware scroller with LMS & HSCROL (8 scanlines)
    - 12 blank scanlines tail (`DL_BLANK1`, `DL_BLANK8`, `DL_BLANK3`) + `DL_JVB` to `dlist_title`
    - Total Display List height: exactly 229 scanlines (preserving exact vertical position of the marquee scroller).
  - Switched entire title screen display to Normal playfield DMA (`SDMCTL = $22`, `DMACTL = $22`), eliminating DLI DMA width toggling.
  - Relocated title screen code and scroll buffers to `$4000-$438E`, recovering 3,072 bytes of ROM/RAM footprint and providing 4,663 bytes of headroom below `$C000`.
- **Build Pipeline & Tooling ([Makefile](Makefile), [scripts/check_memory.py](scripts/check_memory.py), [scripts/generate_memory_map.py](scripts/generate_memory_map.py), [manifest.yaml](manifest.yaml))**:
  - Removed `TITLE_IMG` and `TITLE_BIN` rules and targets from `Makefile` and deleted `gen/title.bin`.
  - Updated segment memory validation and report generators for the new `$4000` Title Scroll VRAM & Text segment.
  - Updated `manifest.yaml` marking legacy bitmap artwork as archived.
- **Automated Verification ([tests/test_title_text.py](tests/test_title_text.py), [tests/test_title_scroll.py](tests/test_title_scroll.py), [tests/test_state_machine_and_fade.py](tests/test_state_machine_and_fade.py))**:
  - Added new 10-test test suite in `tests/test_title_text.py` verifying font identity against `fonts/font.fnt`, test vectors, LUT table, Python reference render matching, exact offsets and row zero-margins, sentinel bounds, negative and positive validation, Display List LMS instructions, 229-scanline height, and hardware registers.
  - Updated existing scroll and fade tests to assert `SDMCTL = $22` and `DMACTL = $22`.
  - All 441 automated tests and `check_memory` passed cleanly in `make all`.


- **Documentation ([README.md](README.md))**:
  - Completely updated and modernized project documentation to reflect current engine architecture, tools, and build pipeline.
  - Added comprehensive overview of Atari 8-bit architecture (ANTIC Mode D Narrow 128x96 scroller with rainbow raster DLI, Mode D 160x96 gameplay, Mode E tilesets, PMG Player 0 & Missiles, GTIA hardware collisions, HUD in ANTIC Mode 2, and Game Over states).
  - Documented full player controls table (directional movement, inertia, vertical jump, short jump, and long jump combinations).
  - Documented complete project tooling suite including [atari-scene-editor/](atari-scene-editor/README.md), [sprite_studio/](sprite_studio/), and the full Python asset pipeline (`convert_image.py`, `convert_tiles.py`, `compile_scenes.py`, `compile_sprites.py`, `compile_music.py`, `compile_scroll_text.py`, `check_memory.py`, and `generate_memory_map.py`).
  - Added build target reference guide for `Makefile` (`make all`, `xex`, `tests`, `check_memory`, `map`, `run`, `clean`) and GUI editor launch instructions.
  - Added summary of the 431+ automated tests covering py65 6502 CPU emulation and Python tool verification.


- **Physics & Collision Engine ([engine/player.asm](engine/player.asm))**:
  - Extended the ceiling collision bypass in `player_jump_update` (`beq @render_jump`) to `JUMP_TYPE_UP` (vertical jump), mirroring the existing behavior for `JUMP_TYPE_LONG`.
  - Platforms directly overhead (1 tier above, <= 20 lines) remain fully blocked from initiating any jump at start via `player_initiate_jump`.
  - Platforms two or more tiers above (>= 32 lines higher) no longer artificially truncate vertical jumps, allowing Hero to reach his full 18-line vertical jump apex and cleanly land back on his starting platform.
- **Automated Verification ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Added `test_player_jump_up_does_not_hit_ceiling_two_tiers_above` verifying that a vertical jump beneath a platform at `plat_y = 56` (32px above floor `y = 88`) reaches full apex without bouncing into `PLAYER_STATE_FALL`.
  - Updated `test_player_jump_ceiling_collision_bounces_to_fall` to use `JUMP_TYPE_SHORT`, confirming that horizontal leaping directly into low overhead obstacles continues to bounce into fall state.
  - All 431 py65 emulation and Python unit tests passed in `make all`.


- **State Management & Title Architecture ([scenes/title.asm](scenes/title.asm), [scenes/game.asm](scenes/game.asm))**:
  - Fixed STAB-004 where completing all scenes or exiting from Game Over left `active_scene_id = SCENE_COUNT` without resetting game state upon return to title.
  - Updated `title_init` in [scenes/title.asm](scenes/title.asm) to reset `active_scene_id = 0` and call `status_line_reset`, restoring `player_lives = 3`, `player_cds = 0`, and `game_result = GAME_RESULT_NONE` for fresh playthroughs.
  - Added front-gate defensive validation in `game_init` ([scenes/game.asm](scenes/game.asm)) clamping `active_scene_id` to `0` if `>= SCENE_COUNT`.
- **Defensive Bounds Checking & Size Optimization ([engine/secrets.asm](engine/secrets.asm), [engine/player.asm](engine/player.asm), [engine/status_line.asm](engine/status_line.asm))**:
  - Added `cmp #SCENE_COUNT; bcc @valid_id; rts` bounds guards in `player_init`, `secrets_init`, and `status_line_init` to prevent out-of-bounds table indexing.
  - Removed 8 redundant `ldx active_scene_id` instructions across copy phases in `secrets_init` and redundant `lda secrets_count`, recovering 18 bytes and shrinking `SCENES_DATA` ($5000-$5FED, 19 bytes of headroom before `$6000`).
- **Automated Verification ([tests/test_state_machine_and_fade.py](tests/test_state_machine_and_fade.py))**:
  - Added `test_title_init_resets_game_state_and_active_scene_id` verifying that returning to title after game completion resets `active_scene_id = 0`, `player_lives = 3`, `player_cds = 0`, and `game_result = GAME_RESULT_NONE`.
  - Added `test_subroutines_reject_out_of_bounds_scene_id` verifying that `secrets_init`, `player_init`, and `status_line_init` safely reject `scene_id >= SCENE_COUNT` without memory corruption.
  - All 430 py65 emulation and Python unit tests passed in `make all`.


- **Physics & Engine Runtime ([engine/player.asm](engine/player.asm))**:
  - Fixed STAB-006 where `player_init` erased the active scene index in register `X` during the PMG buffer clearing loop (`@clr_p0`), causing platform pointer tables (`zp_plat_count`, `zp_plat_ptr_x`, `zp_plat_ptr_y`, `zp_plat_ptr_w`) to always index Scene 0 geometry even when called for Scene 1 ("Be Quick or Be Dead").
  - Moved platform table setup before PMG buffer clearing so `X = active_scene_id` is retained directly from procedure entry without requiring register reloading.
  - Added `sta active_scene_id` at the start of `player_init` ensuring Zero Page `active_scene_id` is always updated when entering from external callers with `A = scene_id`.
  - Consolidated register zero-initialization (`player_prev_pmg_y`, `player_dir`, `player_state`, `player_frame_idx...`, `SIZEP0`), saving 10 bytes in `SCENES_DATA` ($5000-$5FF6) and keeping the segment within bounds.
- **Automated Verification ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Expanded `test_player_init_scene1_custom_color` to assert that Scene 1 (`A = 1`) sets `zp_plat_count == 14` (matching Scene 1 platform count instead of Scene 0's 11) and that `zp_plat_ptr_x`, `zp_plat_ptr_y`, `zp_plat_ptr_w` point to Scene 1 platform tables.
  - All 428 py65 emulation and Python unit tests passed in `make all`.
  - Segment memory validation passes with 1,835 bytes of total headroom below `$C000`.


- **Image Converter & Asset Pipeline ([scripts/convert_image.py](scripts/convert_image.py), [Makefile](Makefile), [manifest.yaml](manifest.yaml))**:
  - Updated `convert_image_to_antic_d` to convert 128-pixel narrow images (32 bytes/line) for 96 or 102 lines into ANTIC Mode D format.
  - Replaced title screen image source in `Makefile` and `manifest.yaml` with `images/title3.png` (128x96 2bpp indexed Mode P), compiling to `gen/title.bin` (3,072 bytes vs former 3,840 bytes, saving 768 bytes of VRAM).
- **Display List & DLI Architecture ([main.asm](main.asm), [scenes/title.asm](scenes/title.asm))**:
  - Rebuilt `dlist_title` in `main.asm` to display 96 lines of ANTIC Mode D in Narrow playfield (128 pixels wide, 32 bytes/line), vertically centered (14 blank lines top, 11 blank lines bottom) with 229 total scanlines.
  - Resolved visible horizontal color glitch above scroll line by placing a 1-scanline blank buffer (`DL_BLANK1`) between DLI 1 and `DL_MODE_2`:
    - **DLI (`dli_title_scroll`)**: Triggers on `DL_BLANK1 | DL_DLI`, synchronizes with `WSYNC` to configure `DMACTL = $22`, `HSCROL`, and `COLPF1 = TITLE_COLOR_SCROLL` during the blank buffer line. Then across the 8 scanlines of the ANTIC Mode 2 text line, writes the rainbow raster gradient (`$C0, $C2, $C4, $C6, $C6, $C4, $C2, $C0`) into `COLPF2` with explicit per-scanline `WSYNC` synchronization. On the post-scroll blank line, restores Narrow playfield (`DMACTL = $21`), resets `HSCROL = 0`, and restores Mode D colors (`COLPF1 = $CA`, `COLPF2 = $EE`).
- **Scroll Speed & Timing ([scenes/title.asm](scenes/title.asm), [tests/test_title_scroll.py](tests/test_title_scroll.py))**:
  - Adjusted `TITLE_SCROLL_SPEED` to `2` (steps fine scroll every 2 frames / 25 fps, ~6.25 chars/sec) for comfortable reading pace.
  - Updated `test_title_scroll.py` to step fine scroll according to `TITLE_SCROLL_SPEED` delay dynamically.
- **Memory Footprint & Validation ([scripts/check_memory.py](scripts/check_memory.py))**:
  - `TITLE_VRAM` segment shrunk from 4,039 bytes to 3,271 bytes ($4000-$4CC6), freeing 768 bytes of headroom below `$5000`.
  - Total allocated user RAM reduced to 39,094 bytes (1,866 bytes available below `$C000`).
- **Automated Verification ([tests/test_state_machine_and_fade.py](tests/test_state_machine_and_fade.py), [tests/test_title_scroll.py](tests/test_title_scroll.py))**:
  - Added test `test_title_init_immediate_full_brightness_and_narrow_playfield` asserting immediate colors and `SDMCTL = $21`.
  - Updated `test_title_dual_dli_chain` and `test_dli_title_scroll_sets_registers` to dynamically assert `labels["TITLE_COLOR_SCROLL"]` instead of hardcoded literal.
  - All 428 automated py65 emulation and python unit tests passed in `make all`.

- **Data Pipeline & Pointer Tables ([scripts/compile_scenes.py](scripts/compile_scenes.py))**:
  - Added `dep_id` field to `SceneSecretData` and populated it from scene object definitions.
  - Exported `scene_{sym}_secret_dep_id` arrays in per-scene ASM blocks and added `scene_secret_dep_id_lo` and `scene_secret_dep_id_hi` pointer tables in master scenes metadata.
- **Secrets Runtime Engine ([engine/secrets.asm](engine/secrets.asm))**:
  - Added SoA arrays: `secrets_collected`, `secrets_def_id`, `secrets_dep_id`, and `secrets_x`.
  - Updated `secrets_init` to copy `def_id`, `dep_id`, and `x` tables, reset `secrets_collected` array to zero, clear PMG missile scanlines for all secrets, and render Frame 0 for initially active secrets.
- **Hardware Collision & Stage Unlocking Engine ([scenes/game.asm](scenes/game.asm))**:
  - Implemented `secrets_check_player_collision`: reads GTIA hardware registers `M0PL..M3PL` bit 0 for Player 0 - Missile contact; filters against false positives (such as standing on missile platforms) using 2D bounding-box checks (`abs(player_x - secrets_x) < 8` and vertical PMG overlap `player_pmg_y < secrets_pmg_y + height` & `secrets_pmg_y < player_pmg_y + 20`); clears `HITCLR` at the end of each evaluation.
  - Implemented `secret_collect`: clears touched secret's scanlines from `PMG_MISSILES` via `clear_secret_rows`, marks `secrets_collected = 1` and `secrets_active = 0`.
  - When all active secrets in the current stage are collected, scans uncollected secrets for matching `dep_id == collected_def_id`, unlocks them (`secrets_active = 1`), and renders initial Frame 0 into PMG memory.
  - When all possible secrets on the scene are collected, triggers `game_next_scene`.
- **Level & Victory Progression ([scenes/game.asm](scenes/game.asm))**:
  - Implemented `game_next_scene`: advances `active_scene_id`; if more scenes exist, calls `game_init` (initiating scene title card fade-in/out and spawning player at new level position while preserving lives and CD count); if all scenes are complete, sets `game_result = GAME_SUCCESS` and `game_state = STATE_OVER`.
  - Integrated `secrets_check_player_collision` into `@do_playing` loop in `game_run`.
- **Memory Architecture & Segment Layout ([main.asm](main.asm), [engine/player.asm](engine/player.asm), [scripts/check_memory.py](scripts/check_memory.py))**:
  - Aliased duplicate jump trajectory tables (`jump_up_dy = jump_long_dy`, `jump_up_anim = jump_long_anim`) in `engine/player.asm`, saving 44 bytes in `SCENES_DATA` segment ($5000-$5FFC).
  - Relocated `scenes/gameover.asm` to dedicated `GAMEOVER_ADDR` ($6710), keeping `CODE_ADDR` ($2000-$238A) strictly below `$2400` font boundary and maintaining strictly ascending `org` order without segment backtracking or overlaps.
  - Updated `scripts/check_memory.py` to validate strictly ascending segments and prevent XEX segment overwrites.
- **Automated Verification ([tests/test_secrets_runtime.py](tests/test_secrets_runtime.py), [tests/test_memory_map.py](tests/test_memory_map.py))**:
  - Added py65 test `test_secret_collection_and_stage_progression_scene0` verifying hardware collision collection, PMG scanline clearing, missile platform collision rejection, sequential stage unlocking (Keys $\to$ Ladder), Frame 0 rendering on unlock, and automatic level transition to Scene 1 with preserved lives.
  - Added py65 test `test_game_success_on_final_scene_completion` verifying completion of the final scene sets `game_result = GAME_SUCCESS` and `game_state = STATE_OVER`.
  - All 429 tests passed in `make all`.

- **Vertical Jump Profile Update ([engine/player.asm](engine/player.asm))**:
  - Increased vertical jump length `JUMP_UP_LEN` from 16 to 22 steps.
  - Updated `jump_up_dy` to match the 18-line apex trajectory of `jump_long_dy` (`-2, -2, -2, -2, -2, -2, -2, -1, -1, -1, -1, 0, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3`), reaching peak ascent at step 11 (-18 lines) with net $\Delta Y = 0$.
  - Expanded `jump_up_dx` to 22 bytes (`:22 .byte 0`) and aligned `jump_up_anim` to matching 3-phase timing (steps 0..7 Frame 0, steps 8..13 Frame 1, steps 14..21 Frame 2).
- **Automated Verification ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Updated `test_player_jump_up_trajectory` verifying full 22-step vertical trajectory, 18-line peak ascent ($Y = 68 \to 50$), and landing back on Platform 0 at $Y=68$.
  - Updated `test_player_jump_animation_frames_in_pmg` and `test_player_jump_on_row_1_full_height` to verify updated step boundaries and 18-line apex ($Y = 4 \to -14$) with PMG scanline 24.
  - All 427 tests passed in `make all`.

## [2026-10-19] - Fix Jump Height Restriction on Top Platform Row (Row 1, Y=24)

- **Signed Player Coordinate Clamping ([engine/player.asm](engine/player.asm))**:
  - Identified cause of artificial jump height truncation on Row 1 platforms ($Y=24$, standing head at $Y=4$): `player_jump_update` previously clamped `player_y` at $0$ upon underflow, freezing upward ascent after only 4 lines of rise.
  - Replaced zero-clamp with signed limit down to $Y=-24$ (`$E8`, PMG scanline 4): allows full vertical/short jump ascent (apex $Y=-6$) and long jump ascent (apex $Y=-14$) into open sky above the playfield without wrapping.
  - Added negative $Y$ guard (`bmi @do_render`) to `player_fall_update` before death check against `PLAYER_DEATH_Y`, preventing negative two's-complement values from falsely triggering bottom-of-screen death.
- **Automated Verification ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Added `test_player_jump_on_row_1_full_height` verifying full 10-line vertical rise to apex $Y=-6$ ($250 / \$FA$) with valid PMG scanline 40, followed by exact return to starting platform ($Y=4$) in `PLAYER_STATE_IDLE`.
  - All 427 tests passed in `make all`.

## [2026-10-19] - Block Jump Initiation Under Directly Overhead Platforms

- **Jump Initiation Validation ([engine/player.asm](engine/player.asm))**:
  - Implemented overhead platform detection in `player_initiate_jump`: before starting any jump trajectory, iterates through scene platforms to check if any platform is directly overhead (`plat_x <= mid_x < plat_x + plat_w`, `overhead_y < floor_y`, and `overhead_y + 20 >= floor_y`).
  - When standing directly beneath a platform 16 lines above, Hero has insufficient clearance to jump; jumping is completely blocked without modifying `player_state` or transitioning to fall, preventing the ceiling bounce routine from snapping the player through the floor.
  - In `player_update`, verified `player_state == PLAYER_STATE_JUMP` after `player_initiate_jump` before routing to `player_jump_update`, allowing normal movement handling to proceed seamlessly when jump is blocked.
- **Ceiling Bounce Snapping Safeguard ([engine/player.asm](engine/player.asm))**:
  - In `player_jump_update`, clamped ceiling bounce snap `plat_y + 4` against `player_prev_y` (`cmp player_prev_y; bcc @snap_ok; lda player_prev_y`), guaranteeing `player_y` never increases (moves downwards) during ceiling collisions.
- **Automated Verification ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Updated `test_player_jump_blocked_when_platform_directly_overhead` verifying that pressing Fire (or Fire + directional input) while standing directly under an overhead platform keeps Hero securely in `PLAYER_STATE_IDLE` on his standing platform without movement or state corruption.
  - All 426 tests passed in `make all`.

## [2026-10-19] - Set Long Jump Apex to 18 Lines and Fix Ceiling Collision Detection

- **Ceiling Collision Overhaul ([engine/player.asm](engine/player.asm))**:
  - Fixed false-negative ceiling collision when a platform is directly overhead (16px above floor, e.g. `plat_y = 72` for floor `88`): previously checked `player_prev_y >= plat_y`, which falsely evaluated to false because Hero's standing head at $Y=68$ is numerically $< 72$.
  - Replaced with robust condition: verified platform is above Hero's feet (`player_y + 20 > plat_y`) and Hero's head penetrated the platform underside (`player_y <= plat_y + 4`).
  - Bypassed ceiling collision during `JUMP_TYPE_LONG` so jumping to an adjacent higher tier is not obstructed by ceilings 2 tiers higher ($Y - 32$).
- **Long Jump Trajectory Adjusted to 18-Line Apex ([engine/player.asm](engine/player.asm))**:
  - Re-profiled `jump_long_dy` to 22 steps with peak ascent of -18 lines at step 11 (`-2, -2, -2, -2, -2, -2, -2, -1, -1, -1, -1, 0, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3`), returning net $\Delta Y = 0$.
  - Adjusted horizontal step distribution in `jump_long_dx` across steps 0..10 for 8px total displacement.
- **Automated Verification ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Added `test_player_jump_ceiling_directly_above_hero_bounces` verifying immediate bounce into `PLAYER_STATE_FALL` when jumping directly beneath a platform 16px higher.
  - Updated `test_player_jump_long_does_not_hit_ceiling_two_tiers_above` and `test_player_jump_short_crosses_gap`.
  - Full test suite passed (426 tests).

## [2026-10-19] - Tune Long Jump Trajectory to Prevent Ceiling Collision with Higher Platforms

- **Long Jump Trajectory Optimization ([engine/player.asm](engine/player.asm))**:
  - Reduced `jump_long_dy` apex height from 20 lines to exactly 16 lines (`steps 0..3: dy=-2`, `steps 4..5: dy=-2`, `steps 6..9: dy=-1`, `steps 10..11: dy=0`, `steps 12..15: dy=+1`, `steps 16..21: dy=+2`).
  - Matches the exact 16-line distance between platform tiers, eliminating vertical overshoot (4 lines lower) and preventing Hero's head from bumping into ceilings located 2 tiers above (e.g. at $Y - 32$).
  - Front-loaded horizontal displacement in `jump_long_dx` across steps 0..11 (traversing the full 8px before or at apex), ensuring Hero immediately moves away from any platform overhang above his spawn point before cresting onto the destination platform.
  - Adjusted `jump_long_anim` phase markers: Frame 0 (fast ascent, steps 0..7), Frame 1 (apex & landing, steps 8..13), Frame 2 (accelerating descent if falling, steps 14..21).
- **Automated Verification ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Added `test_player_jump_long_does_not_hit_ceiling_two_tiers_above`, confirming that with a ceiling platform at scanline 46 (bottom 50), the long jump to a tier at scanline 72 cleanly lands without triggering ceiling collision.
  - All 425 unit and py65 tests passing.

## [2026-10-19] - Hero Jumping Physics, Trajectory Profiles, Ceiling Bounce, and Three-Phase Animation

- **Zero Page Architecture & Equates ([zeropage.asm](zeropage.asm))**:
  - Added player movement state equate `PLAYER_STATE_JUMP = 3`.
  - Added jump type equates: `JUMP_TYPE_UP = 0` (vertical), `JUMP_TYPE_SHORT = 1` (forward ~16px), `JUMP_TYPE_LONG = 2` (upward to higher platform, max 8px horizontal).
  - Allocated zero page jump registers: `player_jump_type = $D7`, `player_jump_step = $D8`, `player_jump_len = $D9`, `player_fire_released = $DA` (single-press fire debounce), `player_prev_y = $DB` (for ceiling and landing collision detection).
- **Trajectory Profiles & Three-Phase Animation Selection ([engine/player.asm](engine/player.asm))**:
  - Defined trajectory profiles for vertical jump (16 steps, apex 10 lines, net dy=0, dx=0), short forward jump (18 steps, apex 10 lines, net dy=0, dx=18px across gaps), and long upward jump (22 steps, apex 20 lines, reaching platforms 16 lines above, dx=8px).
  - Configured three-phase animation lookup tables (`jump_up_anim`, `jump_short_anim`, `jump_long_anim`): Frame 0 during initial fast ascent, Frame 1 at apex transition and initial descent, and Frame 2 during accelerating descent.
  - Added directional frame address tables `player_jump_anim_table_lo/hi` selecting `player_anim_jump_right_frames` and `player_anim_jump_left_frames`.
- **Joystick Jump Dispatch & Debounce ([engine/player.asm](engine/player.asm))**:
  - In `player_update`: tracks joystick Fire button release (`STRIG0 == 1`) in `player_fire_released` to ensure a deliberate, single-press trigger per jump.
  - Implemented `player_initiate_jump`: evaluates joystick direction:
    - Neutral joystick (or Up only) + Fire -> `JUMP_TYPE_UP`.
    - Left or Right + Fire -> `JUMP_TYPE_SHORT` in the corresponding direction.
    - Up+Left or Up+Right + Fire -> `JUMP_TYPE_LONG` in the corresponding direction.
- **Jump Physics & Collision Engine ([engine/player.asm](engine/player.asm))**:
  - Implemented `player_jump_update`: steps through active trajectory table, updates canvas coordinates `player_x` (clamped to `PLAYER_MAX_X`) and `player_y` (clamped to 0), and updates PMG scanline `player_pmg_y`.
  - Ascent ceiling detection (`dy < 0`): checks if Hero's head overlaps any platform from below (`plat_x <= mid_x < plat_x + plat_w` and `player_y <= plat_y + 4` and `player_prev_y >= plat_y`). Bounces off immediately, transitioning to `PLAYER_STATE_FALL` and falling vertically downward using `player_anim_fall_frame_0`.
  - Descent landing detection (`dy > 0`): checks if Hero's feet cross platform top surface (`prev_feet_y <= plat_y` and `feet_y >= plat_y` and `plat_x <= mid_x < plat_x + plat_w`). Snaps feet to platform top and returns to `PLAYER_STATE_IDLE`.
- **Memory Architecture Optimization ([main.asm](main.asm), [tests/test_memory_map.py](tests/test_memory_map.py))**:
  - Relocated `gen/sprites_data.asm` and `engine/status_line.asm` from `$5000` to the `RENDER_TABLES` segment at `$7A00`, keeping `$5000` segment at `$5F3B` (well below `$6000`) and `$7A00` segment at `$7F95` (below `$8000`).
  - Total headroom below `$C000`: 1,460 bytes.
- **Automated Integration Tests ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Added 5 py65 integration tests: `test_player_jump_up_vertical`, `test_player_jump_short_crosses_gap`, `test_player_jump_long_reaches_higher_platform`, `test_player_jump_ceiling_collision_bounces_to_fall`, and `test_player_jump_animation_frames_in_pmg`.
  - All 424 tests pass in automated verification.

## [2026-10-19] - Fix Status Line Clipping, Top-of-Screen Wrap, and Title/Game Over PMG Clearing

- **Status Line Sprite Hiding & Anti-Wrap Fix ([engine/player.asm](engine/player.asm), [engine/dli.asm](engine/dli.asm))**:
  - Adjusted PMG sprite clipping threshold in `player_render_frame` from 244 to 224 (`cmp #224` and carry check `bcs @skip`), matching the end of the Mode D playfield (scanlines 32..223) and beginning of the status line area (224..239). Sprite smoothly hides behind the status line as it falls.
  - Corrected `PLAYER_DEATH_Y` from 104 to 94 (`pmg_y = 94 * 2 + 52 = 240`), ensuring the top of the sprite completely clears the bottom of the status line without 8-bit arithmetic wrap-around (which previously wrapped 260 to 4, redrawing the sprite at the top of the screen).
  - In `dli_status_line` ([engine/dli.asm](engine/dli.asm)): added hardware zeroing for Player 0 (`sta HPOSP0`, `sta SIZEP0`) to guarantee that no sprite pixels appear on the Mode 2 text row.
  - In `dli_vblank_update` ([engine/dli.asm](engine/dli.asm)): restored `HPOSP0 = 48 + player_x` and `SIZEP0 = 0` for the active playfield area.
- **PMG Buffer & Hardware Register Clearing ([scenes/title.asm](scenes/title.asm), [scenes/gameover.asm](scenes/gameover.asm), [scenes/intro.asm](scenes/intro.asm), [engine/player.asm](engine/player.asm))**:
  - In `title_init`, `gameover_init`, and `intro_init`: disabled GTIA PMG latching (`sta GRACTL`), cleared all horizontal positions (`HPOSP0..3`, `HPOSM0..3`), size registers (`SIZEP0..3`, `SIZEM`), and graphics latch registers (`GRAFP0..3`, `GRAFM`), and wiped all 2,048 bytes of PMG memory (`$6800-$6FFF`) to eliminate residual vertical strips or flickering on the title screen after game over.
  - In `player_handle_death` ([engine/player.asm](engine/player.asm)): added immediate clearing of `HPOSP0` and `GRAFP0` upon death.
- **Test Suite Updates ([tests/test_player_movement.py](tests/test_player_movement.py), [tests/test_dli_system.py](tests/test_dli_system.py))**:
  - Updated falling death tests for `PLAYER_DEATH_Y = 94` and verified scanlines `>= 224` are strictly 0.
  - Updated DLI 7 status line assertions to verify `HPOSP0 == 0` and `SIZEP0 == 0` on the status line, with position restoration on VBLANK.
  - All 419 unit and integration tests passing; memory map passes with 2,115 bytes headroom below `$C000`.

## [2026-10-19] - Platform Edge Falling Physics, Fall Animation, PMG Status Line Clipping, and Defeat Handling

- **Zero Page Architecture ([zeropage.asm](zeropage.asm))**:
  - Added game result equates (`GAME_RESULT_NONE = 0`, `GAME_FAILED = 1`, `GAME_SUCCESS = 2`).
  - Added player movement state equate `PLAYER_STATE_FALL = 2`.
  - Allocated zero page variables: `player_y = $CC`, `player_plat_idx = $CD` (standing platform index, `$FF` if falling), `player_prev_pmg_y = $CE` (previous frame PMG scanline for glitch-free clearing), `game_result = $CF` (defeat/victory outcome).
  - Allocated platform collision pointers in Zero Page: `zp_plat_ptr_x = $D0`, `zp_plat_ptr_y = $D2`, `zp_plat_ptr_w = $D4`, `zp_plat_count = $D6`.
- **Platform Edge & Falling Engine ([engine/player.asm](engine/player.asm))**:
  - In `player_init`: initializes `player_y`, `player_prev_pmg_y`, sets up active scene platform pointers, and scans platform bounds (`plat_y == player_y + 20` and `plat_x <= player_x + 4 < plat_x + plat_w`) to detect the initial standing platform.
  - In `player_update`: checks if Hero walks > 50% of sprite width (midpoint `player_x + 4`) beyond either left or right platform bounds (`mid_x < plat_x` or `mid_x >= plat_x + plat_w`); transitions immediately to `PLAYER_STATE_FALL`, zeroes horizontal speed and resets platform index to `$FF`.
  - Implemented `player_fall_update`: drops Hero downwards by 1 canvas line/frame, updates `player_pmg_y`, and checks for landing on lower platforms in the active scene.
  - Landing detection: if `feet_y == plat_y` and `plat_x <= mid_x < plat_x + plat_w`, lands safely, resetting state to `PLAYER_STATE_IDLE` and setting `player_plat_idx`.
- **PMG Rendering & Status Line Clipping Invariant ([engine/player.asm](engine/player.asm))**:
  - In `player_render_frame`: selects 1-frame fall animation `player_anim_fall_frame_0` when in `PLAYER_STATE_FALL`.
  - Implemented scanline-precise erasing of previous sprite lines (`player_prev_pmg_y + y < 244`) from `PMG_PLAYER0` buffer to prevent vertical smearing.
  - Enforced strict hardware clipping at scanline 244 (`PMG_MAX_DRAW_SCANLINE`): any sprite scanline falling onto or below scanline 244 is never written to PMG memory, guaranteeing zero sprite visibility over the status line text or bottom blank margins.
- **Death & Defeat / Game Over State Handling ([engine/player.asm](engine/player.asm), [engine/status_line.asm](engine/status_line.asm))**:
  - Implemented `player_handle_death`: triggered once the entire sprite frame completely traverses through the bottom of the status line (`player_y >= PLAYER_DEATH_Y = 104`).
  - Clears `PMG_PLAYER0` buffer, decrements `player_lives` by 1, and immediately updates hearts on the Mode 2 status line HUD via `status_line_refresh_lives`.
  - If lives remain (`player_lives > 0`), re-initializes Hero at the scene spawn position via `player_init`.
  - If no lives remain (`player_lives == 0`), sets `game_result = GAME_FAILED` and triggers defeat game over transition to `game_state = STATE_OVER`.
  - Updated `status_line_reset` in [engine/status_line.asm](engine/status_line.asm) to reset `game_result` to `GAME_RESULT_NONE`.
- **Memory Layout & Segment Headroom ([main.asm](main.asm))**:
  - Relocated `scenes/title.asm` into `TILES_META` segment ($2A30), preventing segment $5000 from overflowing into Title Display List ($6000).
  - Maintained memory continuity with 2,354 bytes headroom below `$C000`.
- **Automated Verification ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Added py65 CPU integration tests covering right-edge fall trigger (> 50% width), left-edge fall trigger (> 50% width), fall animation in PMG memory, landing on lower platforms, bottom-of-screen status line clipping and lives decrement respawn, and Game Over failure transition upon reaching 0 lives (419/419 tests passing).

## [2026-10-19] - Per-Scene Player 0 Color Configuration in Scene Editor and Engine

- **Scene Model & Serialization ([atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py), [atari-scene-editor/src/scene_editor/json_serializer.py](atari-scene-editor/src/scene_editor/json_serializer.py))**:
  - Added `DEFAULT_PLAYER_COLOR = 0x98` and `color` attribute to [PlayerSpawn](atari-scene-editor/src/scene_editor/scene_model.py) dataclass.
  - Implemented GTIA register validation for `color` (integer in range 0..255, lowest bit must be 0 for even luminance step).
  - Updated `to_dict` and `from_dict` to serialize/deserialize player color (supporting both integer and `$XX`/`0xXX` hex string formats, defaulting to `$98`).
  - Added `set_player_spawn_color(color)` helper to [Scene](atari-scene-editor/src/scene_editor/scene_model.py) and updated `set_player_spawn` to retain/accept color.
- **Palette Dialog & Commands ([atari-scene-editor/src/scene_editor/atari_palette.py](atari-scene-editor/src/scene_editor/atari_palette.py), [atari-scene-editor/src/scene_editor/commands.py](atari-scene-editor/src/scene_editor/commands.py))**:
  - Added [AtariColorPickerDialog](atari-scene-editor/src/scene_editor/atari_palette.py) providing an interactive 16x8 GTIA matrix (16 hues x 8 luminances) with live preview swatch, hex/RGB labels, and `get_color()` modal helper.
  - Implemented [ChangePlayerSpawnColorCommand](atari-scene-editor/src/scene_editor/commands.py) with full Undo/Redo stack integration.
  - Ensured [MovePlayerSpawnCommand](atari-scene-editor/src/scene_editor/commands.py) and [SetPlayerSpawnCommand](atari-scene-editor/src/scene_editor/commands.py) preserve the configured color.
- **Graphics Item & Editor UI ([atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py), [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py))**:
  - Updated [PlayerSpawnGraphicsItem](atari-scene-editor/src/scene_editor/scene_items.py) to dynamically paint the hero torso and helmet using the active scene color converted via `atari_color_to_rgb`, and appended color details to the tooltip.
  - Added Hero Color controls to [MainWindow](atari-scene-editor/src/scene_editor/main_window.py) Player Start property panel (even-step `QSpinBox`, hex label, live color swatch button, and "Palette..." dialog button).
- **Scene Compiler & Data Generation ([scripts/compile_scenes.py](scripts/compile_scenes.py))**:
  - Extended `SceneCompiledData` with `player_color` (defaulting to `$98`).
  - Parsed `color`/`atari_color` from `player_spawn` in `parse_scene_json`.
  - Emitted per-scene equates (`SCENE_{sym}_PLAYER_COLOR = $XX`) and master Structure-of-Arrays table `scene_player_color` in `gen/scenes_data.asm`.
- **6502 Memory & Engine Architecture ([zeropage.asm](zeropage.asm), [engine/player.asm](engine/player.asm))**:
  - Allocated `player_color = $CB` in Zero Page.
  - Updated `player_init` in [engine/player.asm](engine/player.asm) to load `scene_player_color,x`, initializing `player_color`, `COLPM0`, and shadow `PCOLR0` dynamically per scene.
  - Renamed constant `PLAYER_COLOR` to `PLAYER_DEFAULT_COLOR` in `engine/player.asm` to avoid MADS symbol collision.
- **Scene Assets & Automated Verification ([scenes/01-forest.json](scenes/01-forest.json), [scenes/02-forest-castle.json](scenes/02-forest-castle.json), [tests/test_player_spawn.py](tests/test_player_spawn.py), [tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Dynamically assert player initialization colors against the active ROM table (`scene_player_color`), verifying distinct colors across scenes without breaking when scenes are reconfigured via editor.
  - Added unit, integration, and py65 emulation tests verifying model validation, command undo/redo, UI interaction, compilation to assembly, and 6502 `player_init` execution loading distinct colors per scene (413/413 passed).



- **Sprite Studio Frame Clipboard ([sprite_studio/main.py](sprite_studio/main.py), [sprite_studio/widgets/timeline.py](sprite_studio/widgets/timeline.py))**:
  - Implemented `_on_copy_frame(idx)`: copies current frame's pixel rows into `clipboard_frame_pixels` (retaining full pixel data).
  - Implemented `_on_paste_frame(idx)`: pastes clipboard content into the selected/current active frame with undo/redo command support (`_execute_cmd("Paste Frame", ...)`).
  - Handled height adjustments automatically: pads with zeroes or slices if clipboard content dimensions differ from target sprite height.
  - Added "Copy Frame" (`Ctrl+C`) and "Paste Frame" (`Ctrl+V`) actions to the `Edit` menu, yielding politely to text inputs when a `QLineEdit` is focused.
  - Added dedicated "Copy" and "Paste" buttons in `TimelineWidget` under `transform_layout`, connected via `copy_requested` and `paste_requested` signals.
- **Sprite Compiler & Memory Architecture ([scripts/compile_sprites.py](scripts/compile_sprites.py), [main.asm](main.asm), [scripts/generate_memory_map.py](scripts/generate_memory_map.py))**:
  - Sanitized animation symbol names in `compile_sprites.py` replacing non-alphanumeric characters (such as hyphens in `jump-right`) with underscores to ensure valid MADS 6502 assembly labels.
  - Relocated `player_sprites.asm` into the `$2A30` metadata segment (utilizing free headroom before `$3000`), preventing the expanded `$5000` block from overflowing past the `$6000` Title DLIST boundary.
- **Automated Verification ([tests/test_sprite_studio.py](tests/test_sprite_studio.py), [tests/test_memory_map.py](tests/test_memory_map.py))**:
  - Added unit and GUI tests for frame copy/paste, undo/redo, empty clipboard safety, and timeline signal routing (13/13 passed in `test_sprite_studio.py`).
  - Passed full test suite and memory validation (`make all`: 409 passed, 2,715 bytes headroom below $C000).

## [2026-10-19] - Restore Integer Sprite ID and Description in Sprite Studio

- **Sprite Studio Models & Validation ([sprite_studio/models.py](sprite_studio/models.py), [sprite_studio/validation.py](sprite_studio/validation.py))**:
  - Restored `Sprite.id` to `int` (range 1..255) and `Sprite.description` to `str` (max 40 characters) in `Sprite` dataclass.
  - Reinstated validation rules verifying non-boolean integer IDs, ID range bounds (1..255), uniqueness among sprites, and description string lengths.
- **Serialization & Backward Compatibility ([sprite_studio/io.py](sprite_studio/io.py))**:
  - Maintained safe integer conversion for legacy string IDs during `load_project`.
  - Saved `id` as integer and `description` as string.
- **User Interface & Undo/Redo ([sprite_studio/widgets/properties.py](sprite_studio/widgets/properties.py), [sprite_studio/widgets/sprite_list.py](sprite_studio/widgets/sprite_list.py), [sprite_studio/main.py](sprite_studio/main.py))**:
  - Restored `spin_id` (`QSpinBox`, 1..255) and `edit_description` (`QLineEdit`) in `PropertiesWidget`.
  - Reinstated sprite list item labeling format (`"{id}: {description}"`) and `update_sprite_display`.
  - Updated auto-generation of unique integer IDs upon adding or duplicating sprites in `MainWindow`.
- **Automated Verification ([tests/test_sprite_studio.py](tests/test_sprite_studio.py))**:
  - Verified all 10 unit and GUI integration tests pass in `tests/test_sprite_studio.py`.
  - Passed full test suite and memory validation (`make all`: 406 passed, 2,847 bytes headroom below $C000).

## [2026-10-18] - Hero Movement Inertia (Acceleration, Deceleration & Braking)

- **Inertia Physics Engine ([engine/player.asm](engine/player.asm), [zeropage.asm](zeropage.asm))**:
  - Replaced single-bit divider with a sub-pixel accumulator `player_x_sub` ($C9, 0..255) and speed magnitude `player_speed` ($CA, 0..`PLAYER_MAX_SPEED`).
  - Set top speed `PLAYER_MAX_SPEED = $80` (0.5 pixels/frame), acceleration rate `PLAYER_ACCEL = $10` (16 subpixels/frame^2, reaching top speed smoothly in 8 frames / ~0.16s), and friction deceleration rate `PLAYER_DECEL = $10` (coasting to a stop over 8 frames / ~0.16s).
  - Implemented turnaround braking: pushing stick opposite to current travel direction decelerates speed down to 0 before reversing facing direction and accelerating.
  - Symmetric 16-bit sub-pixel position integration (`player_x_sub += player_speed`, stepping integer `player_x` on carry overflow/borrow) with double-layer boundary clamping (`0 <= player_x <= 152`) that zeroes speed and sub-pixels at edges.
  - Idle state transitions: walk animation cycles while coasting (`player_speed > 0`); once speed reaches 0, transitions to `PLAYER_STATE_IDLE` with standing frame 0 in the current facing direction.
- **Automated Verification ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Updated py65 test suite validating gradual acceleration curves (0x10..0x80), deceleration friction coasting down to 0x00 upon stick release, active reversal braking, and wall clamping.
  - Ran full build pipeline (`make all`: 406 passed, 2,847 bytes headroom below $C000).

## [2026-10-18] - Reduce Player Walk Movement Speed by Half

- **Player Engine Physics ([engine/player.asm](engine/player.asm), [zeropage.asm](zeropage.asm))**:
  - Allocated `player_sub_x` ($C9) in Zero Page as a sub-pixel step divider.
  - Reduced horizontal movement speed from 1.0 px/frame to 0.5 px/frame (moves 1 pixel every 2 frames): `inc player_sub_x` followed by `lsr` carry check so the first movement step responds immediately on frame 1.
  - Reset `player_sub_x = 0` on entering idle state to ensure instantaneous response on subsequent stick presses.
- **Automated Verification ([tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Updated py65 test expectations verifying 0.5 px/frame right/left progression, idle sub-pixel reset, and 3-frame boundary clamping.
  - Verified full test suite (`make all`: 406 passed, 3,004 bytes headroom below $C000).

## [2026-10-18] - Hero (Player 0) Spawn and Horizontal Walk Movement

- **Player Sprite Compilation Pipeline ([scripts/compile_sprites.py](scripts/compile_sprites.py), [Makefile](Makefile))**:
  - Added `pack_row_to_player_bitmap()` converting 8-pixel scanlines to MSB-first 1bpp Player 0 bitmap bytes (`bit 7` = leftmost pixel, `bit 0` = rightmost pixel).
  - Implemented `generate_player_sprites_asm()` emitting `player_anim_right_frames`, `player_anim_left_frames`, and direction lookup tables (`player_anim_table_lo/hi`) into `gen/player_sprites.asm`.
  - Added `--mode {missiles,player}` CLI switch and integrated `PLAYER_SPRITE_SRC` / `PLAYER_SPRITE_ASM` targets into `Makefile`.
- **Hero Player 0 Engine ([engine/player.asm](engine/player.asm), [zeropage.asm](zeropage.asm), [main.asm](main.asm))**:
  - Allocated Player 0 Zero Page state registers: `player_x` ($C3), `player_pmg_y` ($C4), `player_dir` ($C5), `player_state` ($C6), `player_frame_idx` ($C7), `player_frame_timer` ($C8).
  - Implemented `player_init(A = active_scene_id)`: reads scene spawn coordinates (`scene_player_start_x/y`), maps vertical position to PMG scanline (`player_pmg_y = (player_start_y << 1) + 52`), sets `COLPM0 = $98` (royal cyan), `SIZEP0 = 0`, sets `HPOSP0 = 48 + player_x`, clears `PMG_PLAYER0` buffer ($6C00-$6CFF), and renders initial standing frame.
  - Implemented `player_render_frame()`: resolves frame address via `player_anim_table_lo/hi` based on `player_dir` and copies 20 scanlines to `PMG_PLAYER0 + player_pmg_y`.
  - Implemented `player_update()`: polls `STICK0` (bits 2 and 3), moves left/right with boundary clamping (`0 <= player_x <= 152`), updates `HPOSP0`, cycles 5-frame walk animation with wrap-around, and resets to standing frame 0 on idle while preserving last direction.
- **Gameplay State Machine Integration ([scenes/game.asm](scenes/game.asm))**:
  - Hooked `player_init` into `game_init` sequence after DLI and secrets setup.
  - Hooked `player_update` into active gameplay loop (`@do_playing`).
- **Resource Manifest Update ([manifest.yaml](manifest.yaml))**:
  - Registered `engine/player.asm` in the engine components section.
- **Automated Verification ([tests/test_compile_sprites.py](tests/test_compile_sprites.py), [tests/test_player_movement.py](tests/test_player_movement.py))**:
  - Added unit tests for player bitmap packing and assembly generation.
  - Added 5 py65 integration tests verifying spawn state, PMG scanline rendering, right walk animation progression, left walk direction switching, idle state frame reset, and boundary clamping.
  - Verified full test suite (`make all`: 406 passed, 3,022 bytes headroom below $C000).

## [2026-10-18] - Game Resource Manifest (manifest.yaml)

- **Game Manifest Creation ([manifest.yaml](manifest.yaml))**:
  - Created master YAML manifest aggregating all input/source assets and tooling for building the game (excluding generated files).
  - Categorized resources into: `source_code` (entry point, system, engine, scenes, libraries), `graphics` (screens, tilesets, fonts, sprites), `audio` (title JSON score, intro DSL music), `texts` (intro narrative, title scroller), `scenes` (ordering manifest, definition catalogues, levels), and `tools` (build pipeline Python scripts).
- **Automated Manifest Validation ([tests/test_manifest.py](tests/test_manifest.py))**:
  - Implemented unit test suite verifying manifest existence, ensuring all referenced files exist in the repository, and guarding against inclusion of generated (`gen/`) build artifacts.
  - Verified full test suite (`make all`: 399 passed, 3,430 bytes headroom below $C000).

## [2026-10-17] - Player Initial Spawn Configuration in Atari Scene Editor

- **Scene Data Model & Validation ([atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py))**:
  - Added `PlayerSpawn` dataclass representing Player 0 (Hero) initial spawn coordinates (`x`, `y`) with 8x20 pixel dimensions (`PLAYER_WIDTH = 8`, `PLAYER_HEIGHT = 20`).
  - Added geometric properties (`width`, `height`, `right`, `bottom`) and bounding validation against scene canvas dimensions (`0 <= x <= scene_width - 8`, `0 <= y <= scene_height - 20`).
  - Integrated `player_spawn: Optional[PlayerSpawn] = None` into `Scene` model with `set_player_spawn(x, y)` and `remove_player_spawn()`.
- **JSON Serialization & Backward Compatibility ([atari-scene-editor/src/scene_editor/json_serializer.py](atari-scene-editor/src/scene_editor/json_serializer.py))**:
  - Updated `SceneSerializer.to_dict()` and `from_dict()` to serialize `player_spawn: {"x": ..., "y": ...}` when configured.
  - Maintained full backward compatibility: scenes without `player_spawn` deserialize gracefully with `player_spawn = None`.
- **Undo / Redo Architecture ([atari-scene-editor/src/scene_editor/commands.py](atari-scene-editor/src/scene_editor/commands.py))**:
  - Implemented `SetPlayerSpawnCommand(SceneBaseCommand)` for creating and removing the player spawn position.
  - Implemented `MovePlayerSpawnCommand(SceneBaseCommand)` for position translations (keyboard arrows, spinboxes, and canvas dragging).
- **Interactive Canvas Rendering ([atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py), [atari-scene-editor/src/scene_editor/scene_view.py](atari-scene-editor/src/scene_editor/scene_view.py))**:
  - Implemented `PlayerSpawnGraphicsItem(QGraphicsItem)` rendering the 8x20 pixel-art Hero sprite (cyan body, skin face, brown boots), dashed bounding box, coordinate label, and ground baseline indicator.
  - Added canvas drag-and-drop with boundary clamping, selection synchronization with other elements/platforms/objects, and dedicated signals `player_spawn_selected` and `player_spawn_moved`.
- **Editor UI Integration ([atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py))**:
  - Added Tab 4 ("Player Start") to the right property dock with status indicator, `+ Set Player Start Position` button, X/Y spinboxes, platform snap selector (`Snap to Platform Feet`), and `Remove Player Start` button.
  - Integrated canvas selection, keyboard arrow nudge, and Delete key removal for the player spawn item.
  - Updated status bar to display active player spawn coordinates `Player: (X, Y)` or `Player: None`.
- **Scene Compiler & MADS Assembly Generation ([scripts/compile_scenes.py](scripts/compile_scenes.py))**:
  - Added `player_start_x` and `player_start_y` to `SceneCompiledData` and `parse_scene_json` (defaults to X=20, Y=68 if omitted in scene JSON).
  - Emits per-scene equates (`SCENE_{sym}_PLAYER_START_X`, `SCENE_{sym}_PLAYER_START_Y`) and master index tables (`scene_player_start_x`, `scene_player_start_y`) in `gen/scenes_data.asm`.
- **Automated Verification ([tests/test_player_spawn.py](tests/test_player_spawn.py))**:
  - Added 20 comprehensive unit and integration tests covering model validation, JSON serialization/backward compatibility, undo/redo commands, compiler assembly generation, and headless GUI interactions.
  - Verified full build pipeline via `make all` (all 397 tests passed, 3,430 bytes headroom below $C000).


- **Automated Sprite Tests ([tests/test_compile_sprites.py](tests/test_compile_sprites.py))**:
  - Refactored `test_parse_sprites_json_objects` to dynamically compare parsed sprite attributes (width, height, frames, loop, frame duration) directly against `objects.sprite.json` instead of hardcoded frame counts, preventing test breakage when sprite animations are expanded in Sprite Studio.
- **Runtime Secret Animation Tests ([tests/test_secrets_runtime.py](tests/test_secrets_runtime.py))**:
  - Updated `test_secrets_animation_progression` to read frame duration (`SECRETS_FRAME_DUR`) and frame count (`SECRETS_FRAME_COUNT`) dynamically from initialized engine tables.
  - Validates timer countdown, frame progression up to `key_frame_count - 1`, and loop wrapping back to frame 0 for arbitrary frame counts (such as the new 12-frame Gold Key animation).
- **Verification**: `make all` passes cleanly (all 377 tests passed, 3,434 bytes headroom below $C000).

## [2026-10-17] - Update Gameplay Mechanics Specification (MECHANIKA.md)

- **Mechanics Documentation ([MECHANIKA.md](MECHANIKA.md))**:
  - Corrected player sprite source file reference from `objects.sprite.json` to `player.sprite.json`.
  - Added section `2.5. Linia statusowa (HUD) i licznik płyt CD` detailing the ANTIC 2 bottom status bar, heart icons (decimal code 64) for lives, centered scene title, and 2-digit CD counter (00..99).
  - Documented CD counter retention across scene transitions and persistence upon player death.
  - Added status line definition to Section 1 terminology table.
  - Added acceptance scenarios 19 and 20 covering status line rendering and CD counter behavior.

## [2026-10-17] - Fix DLI Faza A Scanline Alignment & Platform Color Artifact

- **Zero-Overhead Faza A Restoration ([engine/dli.asm](engine/dli.asm))**:
  - Removed branch/jump instructions from `dli_handler` entry, restoring Faza A to its exact 47-cycle pre-WSYNC budget and eliminating scanline slip.
  - Resolved artifact where platform top scanline rendered in Zone 0 enemy color (purple) instead of black ($00), ensuring all 8 profile scanlines align cycle-exact to scanlines $2L..2L+7$ (starting with black and ending with black).
  - Shifted status line DLI vector hooking to DLI 6 Faza C: dynamically updates `VDSLST` to point to dedicated `dli_status_line` only after Pas 5 completes.
  - Dedicated `dli_status_line` handles DLI 7 (status line blank separator), sets black background (`COLPF2 = $00`), white text (`COLPF1 = $0E`), zeroes PMG positions/sizes, and restores `VDSLST` back to `dli_handler` for the next frame.
  - Corrected register loading order in `dli_vblank_update` before shifting `dli_active_offset` into `X`.
- **Automated Verification ([tests/test_dli_system.py](tests/test_dli_system.py))**:
  - Verified `VDSLST` dynamic hooking on DLI 6 and restoration on DLI 7.
  - Confirmed `test_dli_faza_a_cycle_budget_and_faza_b_iter0` passes with cycle-exact pre-WSYNC alignment.
  - Validated full build pipeline via `make all` (all 377 tests pass, 3,542 bytes headroom).

## [2026-10-17] - In-Game Status Line in ANTIC Mode 2

- **Status Line Engine ([engine/status_line.asm](engine/status_line.asm))**:
  - Implemented 40-column ANTIC Mode 2 status bar placed at the bottom of the active gameplay screen.
  - Left side: Player lives (initially 3), rendered as heart glyphs (decimal code 64) at columns 0..2.
  - Center: Active scene name loaded from pre-centered `scene_{sym}_name_line`.
  - Right side: Collected CDs counter (0..99) formatted as 2-digit decimal number in screen codes ($10..$19) at columns 38..39.
  - Routines provided: `status_line_reset`, `status_line_init(A = scene_id)`, `status_line_refresh_lives`, `status_line_refresh_cds`, `status_line_add_cd`, `status_line_lose_life`, and `status_line_update`.
- **Display List & DLI Architecture ([main.asm](main.asm), [engine/dli.asm](engine/dli.asm), [zeropage.asm](zeropage.asm))**:
  - Allocated 40-byte `status_line_vram` buffer in segment $3F00-$3FFF (address $3F8B, strictly avoiding ANTIC 4 KB boundary wrap).
  - Updated `dlist_game` with `DL_BLANK8 | DL_DLI` ($F0, 8 scanlines separator and DLI trigger), `DL_MODE_2 | DL_LMS` ($42, status line, 8 scanlines), and `DL_BLANK8` ($70, 8 scanlines bottom margin), maintaining the deterministic 240-scanline frame timing.
  - Added DLI 7 in `dli_handler` triggered on the blank scanline before Mode 2: sets `COLPF2 = $00` (black background), `COLPF1 = $0E` (crisp white text), and clears PMG horizontal positions/sizes so sprites do not bleed into the status bar.
  - Allocated `player_lives` ($C1) and `player_cds` ($C2) in Zero Page.
- **Scene & State Integration ([scenes/game.asm](scenes/game.asm))**:
  - Integrated `status_line_init` into `game_init` (initializes 3 lives and 0 CDs on start, preserves counters across scene transitions).
- **Automated Verification & py65 Test Suites ([tests/test_status_line.py](tests/test_status_line.py), [tests/test_dli_system.py](tests/test_dli_system.py), [tests/test_convert_tiles.py](tests/test_convert_tiles.py))**:
  - Created [tests/test_status_line.py](tests/test_status_line.py) testing reset, Scene 0/1 layout, heart glyphs at columns 0..2, CD counter at 38..39, clamping at 99, and life decrementation.
  - Updated Display List assertions in [tests/test_dli_system.py](tests/test_dli_system.py) and [tests/test_convert_tiles.py](tests/test_convert_tiles.py).
  - Verified full test suite (`make all`: 377 passed in 7.71s, 3,573 bytes headroom below `$C000`).

## [2026-10-17] - Animated Secrets Display via 5th-Player Missiles

- **Sprite Compilation Pipeline ([scripts/compile_sprites.py](scripts/compile_sprites.py))**:
  - Implemented GTIA 5th-player missile bit-packing (`(p6<<7)|(p7<<6)|(p4<<5)|(p5<<4)|(p2<<3)|(p3<<2)|(p0<<1)|p1`) combining 4 missiles (M0..M3) into an 8-pixel player colored by `COLPF3`.
  - Exported per-sprite frame scanline byte arrays, `.word` frame pointer arrays, and master 1-based lookup tables (`sprite_height`, `sprite_frame_count`, `sprite_frame_dur`, `sprite_frames_table_lo/hi`) into [gen/sprites_data.asm](gen/sprites_data.asm).
- **Scene Compiler Integration ([scripts/compile_scenes.py](scripts/compile_scenes.py))**:
  - Added `--sprites` CLI argument to parse sprite definitions and compute PMG Y scanline offsets with 2 scanlines (1 Mode D line $\ge 1$) margin above platform surfaces: `pmg_y = max(0, p_base - spr_h - 2)`.
  - Filtered initial DLI display to only secrets without dependencies (`dependency is None`), keeping dependent secrets inactive.
  - Generated Structure-of-Arrays (SoA) per-scene secret tables (`scene_{sym}_secret_active`, `_sprite_id`, `_pmg_y`, `_height`, `_frame_dur`, `_frame_count`) and master address pointer tables in [gen/scenes_data.asm](gen/scenes_data.asm).
- **Secrets Runtime Engine ([engine/secrets.asm](engine/secrets.asm))**:
  - Implemented `secrets_init(A = scene_id)`: copies scene SoA tables into RAM buffers, sets `secrets_timer = frame_dur` and `secrets_frame_idx = 0`, and renders Frame 0 into `PMG_MISSILES` (`$6B00`) for active secrets.
  - Implemented `render_secret_frame(X = secret_idx)`: resolves frame address via `sprite_frames_table_lo/hi` and copies scanlines into `PMG_MISSILES + pmg_y`.
  - Implemented `secrets_update()`: decrements per-secret timers each frame, advances frame indices with wrap-around at `frame_count`, and re-renders updated frames to `PMG_MISSILES`.
- **System Integration & Build Pipeline ([main.asm](main.asm), [scenes/game.asm](scenes/game.asm), [Makefile](Makefile))**:
  - Included `gen/sprites_data.asm` and `engine/secrets.asm` into `SCENES_DATA` ($5000 segment).
  - Wired `secrets_init` into `game_init` and `secrets_update` into `game_run` per-frame loop.
  - Updated `Makefile` with `SPRITES_SRC`, `SPRITES_ASM`, compilation target, and automated build dependencies.
- **Automated Verification & py65 Test Suites ([tests/test_compile_sprites.py](tests/test_compile_sprites.py), [tests/test_secrets_runtime.py](tests/test_secrets_runtime.py))**:
  - Validated bit packing, sprite parsing, and ASM generation.
  - Tested `secrets_init` state initialization, margin $\ge 1$ line above platforms, Frame 0 missile graphics, inactive secret filtering, timer decrementing, and animation frame looping.

## [2026-10-16] - Sprite Studio Integration in Atari Scene Editor

- **Catalogue Model & Session Loading ([atari-scene-editor/src/scene_editor/catalogue_model.py](atari-scene-editor/src/scene_editor/catalogue_model.py))**:
  - Added optional `sprite_id: Optional[int] = None` to `CatalogDefinition` with validation (`1 <= sprite_id <= 255`).
  - Updated `to_dict()` and `from_dict()` for `EnemyDefinition` and `SecretDefinition` to serialize and deserialize `sprite_id`.
  - Added `sprites: dict[int, Any]` and `sprites_path: Optional[Path]` to `ProjectCatalogues`.
  - Implemented `ProjectCatalogues.load_sprites_from_json(path)` supporting Sprite Studio format (`version: 1`, `sprites: [...]`).
  - Ensured sprite definitions are strictly loaded on demand via user action (menu/button) and not automatically persisted in [scenes/definitions.json](scenes/definitions.json), guaranteeing comboboxes start disabled.
- **Scene Model & Commands ([atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py), [atari-scene-editor/src/scene_editor/commands.py](atari-scene-editor/src/scene_editor/commands.py))**:
  - Added `sprite_id: Optional[int] = None` to `SceneObjectElement`, serialized in `to_dict()` and `from_dict()`.
  - Added `SceneObjectElement.get_effective_sprite_id(catalogues)` to inherit definition's sprite mapping or use an instance override.
  - Added `new_sprite_id` parameter to `Scene.update_object_props()` and `UpdateSceneObjectPropsCommand`.
- **Catalogue Dialog UI ([atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py))**:
  - Added `btn_load_sprites` ("Load Sprites...") button in the catalogue manager footer.
  - Added `sprite_combo` (`QComboBox`) for Enemies and Secrets: strictly disabled (`setEnabled(False)`) when no sprites are loaded, with tooltip explaining how to unlock it.
  - Implemented `_populate_sprite_combo()` to dynamically unlock the combobox (`setEnabled(True)`) and populate available sprites (`id: description`) only after a sprite JSON is loaded.
  - Updated enemy and secret save/selection handlers to map and display `[Sprite: X]` in entry lists and form controls.
  - Allowed multiple enemies and secrets to map to the same sprite while restricting each entry to at most one sprite.
- **Main Window & Menus ([atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py))**:
  - Added menu items: `Load &Sprites (JSON)...` under `&Catalogues` and `Load &Sprites (JSON)...` under `&File`.
  - Implemented `MainWindow.load_sprites_from_json(file_path)` to load sprite files on demand.
  - Added `new_obj_sprite_combo` to New Object Creator and `obj_prop_sprite_combo` to Selected Object properties (both strictly disabled when sprites are not loaded, enabled upon loading).
  - Connected `_on_obj_prop_sprite_changed` to push `UpdateSceneObjectPropsCommand(new_sprite_id=...)`.
- **Scene Graphics Item & Exporter ([atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py), [scripts/compile_scenes.py](scripts/compile_scenes.py))**:
  - Updated `SceneObjectGraphicsItem` tooltip to display mapped `Sprite: ID {id} ({description})`.
  - Added `sprite_id: Optional[int] = None` to `CatalogueItem` in [scripts/compile_scenes.py](scripts/compile_scenes.py) and updated `load_catalogues()`.
- **Automated Verification ([tests/test_catalogues.py](tests/test_catalogues.py))**:
  - Added `TestSpriteStudioIntegration` test suite covering validation, JSON loading of [sprites/objects.sprite.json](sprites/objects.sprite.json), combobox disabled state verification prior to loading, unlock after loading, multi-mapping, effective sprite resolution, and main window menu integration.
  - Ran `make all`: all 364 tests passed, assembly and memory validation passed.


## [2026-10-16] - Sprite Studio Integer ID (1-255) & Description Field

- **Data Models ([sprite_studio/models.py](sprite_studio/models.py))**:
  - Changed `Sprite.id` from `str = "NEW_SPRITE"` to `int = 1` (valid range 1..255).
  - Added `Sprite.description: str = ""` (string with maximum 40 characters).
- **Validation Engine ([sprite_studio/validation.py](sprite_studio/validation.py))**:
  - Updated `validate_project` to enforce integer IDs in range `1 <= id <= 255`, rejecting non-integers (including booleans), out-of-range values, and duplicates.
  - Added validation for `description`, ensuring it is a string not exceeding 40 characters.
- **Serialization & Backward Compatibility ([sprite_studio/io.py](sprite_studio/io.py))**:
  - Updated `load_project` to parse integer IDs with fallback, migrate legacy string IDs, and load `description`.
  - Updated `save_project` to emit `id` as integer and `description` as string.
  - Migrated [sprites/secret-cd.sprite.json](sprites/secret-cd.sprite.json) to integer ID and added `"description": "Secret CD"`.
- **Properties & UI Controls ([sprite_studio/widgets/properties.py](sprite_studio/widgets/properties.py))**:
  - Replaced ID `QLineEdit` with `QSpinBox` bounded to 1..255 emitting `id_changed(int)`.
  - Added description `QLineEdit` with `maxLength=40` emitting `description_changed(str)`.
  - Implemented focus-preserving value updates in `update_from_sprite` to avoid cursor jumping while typing.
- **Sprite List & Main Window Integration ([sprite_studio/widgets/sprite_list.py](sprite_studio/widgets/sprite_list.py), [sprite_studio/main.py](sprite_studio/main.py))**:
  - Display list items as `f"{sprite.id}: {sprite.description}"` or `f"{sprite.id}"`.
  - Added `update_sprite_display` to update list items without reselecting or triggering re-render cascades.
  - Updated `_on_add_sprite` and `_on_copy_sprite` to automatically allocate the smallest unused integer ID in 1..255.
  - Added undo/redo commands for description and ID modifications.
- **Automated Verification ([tests/test_sprite_studio.py](tests/test_sprite_studio.py))**:
  - Created test suite covering models, validation, serialization, legacy JSON migration, UI widgets, and undo/redo workflows.
  - Ran `make all`: all 359 tests passed.

## [2026-10-16] - Intro Music Replacement & Dynamic Tempo Test Harness

- **Intro Music Composition ([music/intro.dsl](music/intro.dsl))**:
  - Replaced intro music with new composition ("Rlyeh Awakening") at 140 BPM using 16-bit bass mode (`audctl_mode = $10`, `frames_per_tick = 4`).
  - Compiled DSL to [gen/intro_music.asm](gen/intro_music.asm) via [scripts/compile_music.py](scripts/compile_music.py).
- **Dynamic Tempo Test Harness ([tests/test_intro_music.py](tests/test_intro_music.py))**:
  - Updated `test_audio_play_intro_initialization` and `test_audio_update_advances_frame` to read song tempo directly from the compiled header (`mpu.memory[labels["MUSIC_INTRO_DATA"]]`) rather than asserting hardcoded 90 BPM (`frames_per_tick = 5`).
- **Build & Memory Verification**:
  - Ran `make all`: all 349 tests pass; binary [call_of_the_wintermon.xex](call_of_the_wintermon.xex) compiled cleanly.
  - Memory validation passes with 36,373 bytes total allocated and 4,587 bytes headroom below `$C000`.

## [2026-10-16] - Fix 1-Scanline Enemy Artifacts via 3x WSYNC Alignment

- **Root Cause Analysis ([engine/dli.asm](engine/dli.asm))**:
  - Identified the source of the 1-scanline horizontal stripes indicated by the user (purple stripe at $X=107$ corresponding to Enemy 1, blue stripe at $X=116$ corresponding to Enemy 7):
  - In ANTIC Mode D (2 scanlines per mode line), triggering DLI on line $2L-2$ (e.g. line 6) occurs on scanline 1 of that line (scanline 45).
  - The gap before line $2L$ (scanline 48) spans 3 TV scanlines: remaining scanline 1 of line 6, followed by scanlines 0 and 1 of pre-pas line 7.
  - Using only 2x `WSYNC` caused Faza B to start 1 scanline too early (scanline 47 instead of 48). Consequently, Faza B finished 1 scanline early (scanline 54), causing Faza C (guard line enemy positioning) to run on scanline 55 (the 8th scanline of the platform PMG bitmap, which still contained `$FF`).
  - When Faza C updated `HPOSP` to the enemy position and `COLPM` to the enemy color, the hardware immediately rendered an 8-pixel horizontal stripe in that enemy's color for that single scanline.
- **Cycle-Exact Scanline Alignment ([engine/dli.asm](engine/dli.asm))**:
  - Added the 3rd `STA WSYNC` in Faza A, correctly halting through all 3 scanlines (scanline 1 of line $2L-2$, scanlines 0 and 1 of line $2L-1$), aligning Faza B iteration 0 to cycle 0 of scanline $2L$ (the first scanline of platform PMG memory).
  - Faza C now executes cleanly on scanline $2L+8$ (the true guard line), where PMG memory is `$00`, eliminating both artifact lines completely.
- **Automated Verification ([tests/test_dli_system.py](tests/test_dli_system.py))**:
  - Updated `test_dli_faza_a_cycle_budget_and_faza_b_iter0` py65 test harness to step across the 3 synchronizing `WSYNC`s. All 349 tests pass.

- **Unified Color Table Generation ([scripts/compile_scenes.py](scripts/compile_scenes.py))**:
  - Replaced redundant 24 color tables (`pas_c1_sl0..7`, `pas_c2_sl0..7`, `pas_c3_sl0..7`) in `SceneDliCompiledData` and `compile_scene_dli_data()` with a single unified `pas_color_sl: list[list[int]]` (8 scanlines $\times$ 6 pas).
  - Updated `generate_scenes_dli_asm()` to emit `pas_color_sl0..7` (34 tables total $\times$ 6 bytes + 15 bytes Zone 0 = 219 bytes per scene, down from 315 bytes).
  - Saved 192 bytes of ROM in `SCENES_DATA` segment ($5000) across 2 scenes.
- **Engine DLI Buffering & Faza B Execution ([engine/dli.asm](engine/dli.asm))**:
  - Replaced 24-table double buffer allocation with 8 tables (`dli_pas_color_sl0..7`), saving 256 bytes in `DLI_SEGMENT` ($6100).
  - Reduced `DLI_TABLE_COUNT` from 50 to 34 and trimmed `dli_table_ptrs_lo` / `dli_table_ptrs_hi` by 32 bytes.
  - Streamlined Faza B iteration 0 from 60 cycles to 48 cycles before WSYNC (single `LDA dli_pas_color_sl0,y` followed by `STA COLPM1/2/3`).
  - Streamlined Faza B iterations 1–7 from 32 cycles to 24 cycles before WSYNC (single `LDA dli_pas_color_slN,y` followed by `STA COLPM1/2/3`, `STA COLPF3`).
  - Saved 68 cycles per pas (408 cycles per frame across all 6 pas).
- **Test Suite Updates ([tests/test_compile_scenes.py](tests/test_compile_scenes.py))**:
  - Updated `make_dummy_dli()` to construct `SceneDliCompiledData` with `pas_color_sl`.
  - Updated missile platform test assertions to resolve coordinates dynamically.
  - Verified 349 tests pass cleanly (`make all` and `make check_memory`).

- **Open Scene Target Path Fix ([atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py))**:
  - Fixed `TypeError: argument should be a str or an os.PathLike object ..., not 'NoneType'` in `open_scene()`.
  - Replaced `Path(file_path)` with `Path(target_path).resolve()` on line 989, ensuring that when `open_scene()` is invoked without arguments from the menu, the file path selected via `QFileDialog` is correctly stored in `self.current_file_path`.
- **Eliminate QFont Warning ([atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py))**:
  - Removed redundant `font.setPixelSize(6)` following `QFont("Monospace", 6)` in `PlatformGraphicsItem`, resolving `QFont::setPointSize: Point size <= 0 (-1)` warnings.
- **Automated Verification ([tests/test_gui_integration.py](tests/test_gui_integration.py))**:
  - Added `test_open_scene_with_file_dialog` testing `open_scene(None)` with mock file selection dialog. All 349 tests pass.

## [2026-10-16] - Row-Based Platform Color Profiles Architecture

- **Row-Based Profile Assignment ([atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py))**:
  - Added `row_color_profiles: list[Optional[int]]` to `Scene` model, replacing per-platform profile assignment with uniform row-level profiles (all platforms in a row share that row's profile).
  - Implemented `get_row_color_profile_id()`, `set_row_color_profile_id()`, and `set_platform_color_profile()`.
  - Added automatic synchronization in `add_platform()`, `move_platform()`, and `__post_init__()`: platforms on row $r$ immediately reflect row $r$'s profile, and moving a platform between rows dynamically adapts it to the destination row's profile.
- **Scene Serialization & Migration ([atari-scene-editor/src/scene_editor/json_serializer.py](atari-scene-editor/src/scene_editor/json_serializer.py))**:
  - Updated `SceneSerializer.to_dict()` and `from_dict()` to serialize `row_color_profiles`.
  - Maintained backward compatibility: legacy scenes without `row_color_profiles` automatically infer row profiles from their platforms.
- **Scene Editor UI ([atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py), [atari-scene-editor/src/scene_editor/commands.py](atari-scene-editor/src/scene_editor/commands.py))**:
  - Added `ChangeRowColorProfileCommand` with full Undo/Redo support.
  - Added dedicated `Platform Row Color Profiles` group in Tab 2 with combo selectors for each of the 6 platform rows (Row 0..5, y=8..88).
  - Updated Selected Platform panel to show and edit the selected platform's row profile, immediately updating all platforms sharing that row.
- **Compiler Pipeline & DLI Color Uniformity ([scripts/compile_scenes.py](scripts/compile_scenes.py))**:
  - Updated `parse_scene_json` to support `row_color_profiles` and assign uniform scanline colors to all platforms in each row.
  - Initialized `pas_c1_sl`, `pas_c2_sl`, `pas_c3_sl` with the row's color profile in `compile_scene_dli_data`, ensuring sprite channels and missile platforms (`COLPF3`) share the exact same scanline colors across the row.
  - Configured `scenes/01-forest.json` and `scenes/02-forest-castle.json` with explicit `row_color_profiles`.
- **Automated Verification ([tests/test_platform_profiles.py](tests/test_platform_profiles.py))**:
  - Added unit and integration tests verifying row profile sharing, moving platforms across rows, command undo/redo, and JSON round-trip serialization.
  - Verified full test suite (`make all`: 348 tests passed, 3,505 bytes headroom).

## [2026-10-16] - DLI Timing Fix via 1-Line Pre-Trigger & SIZEM Hardware Fix

- **DLI Trigger Re-Alignment ([main.asm](main.asm))**:
  - Shifted all 6 DLI triggers in `dlist_game` by 1 Mode D line earlier: from lines 7, 23, 39, 55, 71, 87 to lines 6, 22, 38, 54, 70, 86.
  - Gives Faza A an entire pre-pas Mode D line (2 scanlines = 228 cycles) before the start of each platform pas (lines 8, 24, 40, 56, 72, 88).
- **2x WSYNC Scanline 2L Synchronization ([engine/dli.asm](engine/dli.asm))**:
  - Synchronized Faza A to the start of scanline `2L` via double `STA WSYNC` (halting through the 2 scanlines of the pre-pas line).
  - Eliminates the 1-scanline late start of Faza B with 100% cycle-exact determinism across PAL, NTSC, and py65 emulation.
- **GTIA SIZEM Missile Platform Width Fix ([engine/dli.asm](engine/dli.asm))**:
  - Identified root cause of missile platforms appearing as 4 dashes: GTIA size register requires `%11` (bit 0=1 and bit 1=1) for 4x quad width; `%10` (`$AA`) is parsed by GTIA as 1x width.
  - Restored `LDA dli_sizem,y / STA SIZEM` in Faza A, which applies `%11111111` (`$FF`) generated by `compile_scenes.py` for 32px missile platforms (forming a solid 32-pixel platform).
  - Configured `STA SIZEM = #0` in Faza C and `dli_vblank_update` so zone secrets use normal 1x missile widths.
- **Automated Verification ([tests/test_dli_system.py](tests/test_dli_system.py), [tests/test_convert_tiles.py](tests/test_convert_tiles.py))**:
  - Updated DLI line indices in test harnesses to reflect shifted lines `{6, 22, 38, 54, 70, 86}`.
  - Verified Faza A cycle budget, 2x WSYNC execution, and SIZEM transitions across all 6 DLIs. All 344 tests pass.

## [2026-10-16] - DLI Faza A Reduction to 51 Cycles & Faza B Iteration 0 Missile Setup

- **Faza A Optimization to 51 Cycles ([engine/dli.asm](engine/dli.asm))**:
  - Removed `HPOSM0-3` setup from Faza A (saved 32 cycles), reducing Faza A pre-WSYNC execution to exactly 51 cycles.
  - Guarantees `STA WSYNC` is reached well within the ~60 CPU cycle budget of scanline `2L-1`, preventing scanline spillover.
- **Faza B Iteration 0 Missile Positioning ([engine/dli.asm](engine/dli.asm))**:
  - Removed the temporary Faza B prologue (`SIZEM` / `PRIOR` conditional branching).
  - Moved `HPOSM0-3` to Faza B iteration 0 on scanline `2L` along with `COLPM1..3` (60 cycles total, cleanly fitting scanline `2L`).
  - Removed `STA COLPF3` from iteration 0 to reserve cycles for missile positions.
- **Global Hardware Constants ([engine/dli.asm](engine/dli.asm), [scripts/compile_scenes.py](scripts/compile_scenes.py))**:
  - Configured `SIZEM = $AA` (quad-width missiles) and `PRIOR = $11` (5th player mode enabled) as global frame constants in `dli_vblank_update`.
  - Removed `STA SIZEM` and `STA PRIOR` resets from Faza C guard line so the hardware constants persist across all 6 platform pas.
  - Updated `scripts/compile_scenes.py` to default `HPOSM0-3` to `$FF` (offscreen) for pas and zones without active missile platforms or secrets.
- **Automated Verification ([tests/test_dli_system.py](tests/test_dli_system.py))**:
  - Updated py65 emulation harness `test_dli_faza_a_cycle_budget_and_faza_b_iter0` confirming Faza A reaches WSYNC in $\le 60$ cycles (~51 cycles) and iteration 0 completes within $\le 65$ cycles (~60 cycles).

## [2026-10-16] - DLI Faza A Cycle Reduction and Faza B PRIOR/SIZEM Prologue

- **Cycle Budget Optimization ([engine/dli.asm](engine/dli.asm))**:
  - Removed X register saving (`stx dli_save_x`) from DLI entry and restoration (`ldx dli_save_x`) from DLI exit, saving 6 cycles (X is never modified by any subroutine inside `dli_handler`).
  - Removed `lda dli_sizem,y / sta SIZEM` (8 cycles) and `lda #$11 / sta PRIOR` (6 cycles) from Faza A, saving 14 cycles.
  - Reduced Faza A execution before `STA WSYNC` down to 79 cycles (fits safely inside the 85-cycle window on scanline `2L-1`), eliminating the 1-scanline late start of Faza B.
- **Faza B Prologue Implementation ([engine/dli.asm](engine/dli.asm))**:
  - Moved SIZEM application to the beginning of Faza B on scanline `2L`.
  - Implemented dynamic PRIOR derivation (Option B): evaluates `dli_sizem,y` to set `PRIOR = $11` if missile 5th player platform is active (`SIZEM != 0`), or `PRIOR = $01` if no missile platform is present (`SIZEM == 0`).
  - Avoided adding any new tables or memory buffers, preserving 100% data compatibility and zero extra RAM consumption.
- **Automated Verification ([tests/test_dli_system.py](tests/test_dli_system.py))**:
  - Updated `test_dli_handler_full_execution_and_palette_transition` to assert that register X is strictly preserved across all 6 DLI phases.
  - Added `test_dli_faza_a_cycle_budget_and_faza_b_prologue` to emulate instruction execution up to `WSYNC`, asserting Faza A reaches WSYNC in <= 85 cycles and verifying PRIOR and SIZEM values in Faza B prologue.

## [2026-10-16] - Atari Scene Editor QAction Triggered Bool TypeError Fix

- **Qt Signal Argument Guard ([atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py))**:
  - Fixed `TypeError: argument should be a str or an os.PathLike object where __fspath__ returns a str, not 'bool'` occurring when clicking `Catalogues -> Load Catalogues (JSON)...`.
  - Root cause: `QAction.triggered(bool checked = False)` emits a boolean argument. Slots with default parameters `file_path: Optional[Path | str] = None` received `file_path=False`, failing `file_path is None` and attempting `Path(False)`.
  - Replaced `if file_path is None:` with `if not file_path or isinstance(file_path, bool):` in `load_catalogues_from_json` and guarded `open_scene`.
  - Wrapped action connections (`self.act_load_catalogues.triggered.connect(lambda: self.load_catalogues_from_json())` and `act_open.triggered.connect(lambda: self.open_scene())`) to prevent signal parameters from bleeding into path arguments.
- **Automated Verification ([tests/test_catalogues.py](tests/test_catalogues.py))**:
  - Added unit test `test_load_catalogues_triggered_action` verifying `load_catalogues_from_json` safely handles boolean inputs and launches file dialog without error.

## [2026-10-16] - Memory Map Visualizer Dynamic Free Block & Zero Page Fixes

- **Dynamic Free Block Resolution ([scripts/generate_memory_map.py](scripts/generate_memory_map.py))**:
  - Replaced hardcoded text `($60CA–$67FF)` in the PDF largest-gap overview panel with dynamic evaluation of `max(free_gaps, key=lambda g: g.size)`.
  - Added contextual description annotations to free gaps (`describe_free_gap`), identifying origin of vacated headroom (e.g., `$2C1E–$2FFF` vacated by `scenes_data`, `$22D0–$23FF` vacated by title code, and `$5C6B–$5FFF` headroom before DLIST).
  - Fixed duplicate size printing in the memory map zoom bar (`FREE RAM (994 B) (994 B)` -> `★ FREE: 994 B [$2C1E–$2FFF]`).
- **Zero Page Allocation Audit ([scripts/generate_memory_map.py](scripts/generate_memory_map.py))**:
  - Corrected stale `$B8–$FF` free block display to reflect modern layout in [zeropage.asm](zeropage.asm): `$B8–$C0` used by DLI Engine, leaving `$C1–$FF` (63 bytes) available.
- **Segment Naming Consistency ([scripts/check_memory.py](scripts/check_memory.py), [scripts/generate_memory_map.py](scripts/generate_memory_map.py))**:
  - Updated segment `0x4000` label to "Title VRAM & Scroller" and `0x5000` to "Scene Data, Title & Intro Music" across memory validation and visualization tools.

## [2026-10-16] - Intro Screen Background Music (music/intro.dsl)

- **Music Tooling DSL Support ([scripts/compile_music.py](scripts/compile_music.py))**:
  - Enhanced `compile_music` to detect `.dsl` files and invoke `generate_music_from_dsl` from the `atari_music` engine alongside `.json` compositions.
  - Automatically exports relocatable MADS assembly with configurable label prefix (`music_intro_data`).
- **Build Pipeline Integration ([Makefile](Makefile))**:
  - Added `MUSIC_INTRO_DSL := music/intro.dsl` and `MUSIC_INTRO_ASM := $(GEN_DIR)/intro_music.asm`.
  - Added compilation rule generating `$(MUSIC_INTRO_ASM)` from `$(MUSIC_INTRO_DSL)` with label `music_intro_data`.
  - Added `$(MUSIC_INTRO_ASM)` as prerequisite to `music:` and `$(TARGET)`.
- **Audio Manager & Intro Scene Driver ([lib/audio.asm](lib/audio.asm), [scenes/intro.asm](scenes/intro.asm))**:
  - In `lib/audio.asm`, implemented `audio_play_intro` subroutine loading `music_intro_data` pointers into `music_init` and triggering `music_play`.
  - In `scenes/intro.asm` (`intro_init`), calls `audio_play_intro` to start music when the Intro screen is entered.
  - In `scenes/intro.asm` (`intro_run`), calls `audio_update` every VBLANK frame to advance the POKEY music player.
  - In `scenes/intro.asm` (`@fire_pressed`), calls `audio_stop` to silence all POKEY channels before transitioning to `STATE_GAME`.
- **Memory Map Placement ([main.asm](main.asm))**:
  - Included `gen/intro_music.asm` (1,299 bytes) in the expanded `$5000` block (`$5000-$5C6A`) right after `scenes/title.asm`.
  - Leaves 917 bytes of headroom before `$6000` (`DLIST_ADDR`) and 3,492 bytes of total headroom below `$C000`.
- **Automated Verification**:
  - Added [tests/test_intro_music.py](tests/test_intro_music.py) testing DSL compilation, symbol resolution, `audio_play_intro` player state, `audio_update` tick advancement, `audio_stop` POKEY silencing, and `intro_init` triggering playback.
  - All 342 unit and py65 emulation tests passed; memory validation passed.


## [2026-10-16] - Smooth ANTIC Mode 2 Marquee Scroller Under Title Screen

- **Marquee Text Compiler ([scripts/compile_scroll_text.py](scripts/compile_scroll_text.py))**:
  - Implemented standalone text compiler converting UTF-8 text ([scroll/title.txt](scroll/title.txt)) to ANTIC 2 internal screen display codes (`0..127`), supporting standard ASCII and Polish diacritics.
  - Automatically appends trailing spaces (minimum 24 spaces) to guarantee a clean visual gap before the marquee loops.
  - Generates [gen/title_scroll_text.asm](gen/title_scroll_text.asm) containing `TITLE_SCROLL_TEXT_LEN` and formatted `.byte` tables.
- **Title Display List & Scroller Integration ([main.asm](main.asm))**:
  - Defined `TITLE_SCROLL_VRAM_LEN = 48` buffer equate (normal playfield width fetches 48 bytes with `DL_HSCROL`).
  - Placed 48-byte scrolling VRAM line `title_scroll_vram` ($4F00-$4F2F) and compiled text `title_scroll_text` ($4F30-$4FC6) into the `$4000-$4FFF` segment immediately after `gen/title.bin`.
  - Updated `dlist_title` ($6000) to 229 scanlines: 16 top blank scanlines, 96 Mode D lines (192 scanlines), 4 blank separator scanlines, 1 blank scanline with DLI (`DL_BLANK1 | DL_DLI`), 1 line ANTIC Mode 2 (`DL_MODE_2 | DL_LMS | DL_HSCROL` pointing to `title_scroll_vram`), 8 bottom blank scanlines, and `DL_JVB`.
  - Relocated [scenes/title.asm](scenes/title.asm) into the expanded `$5000` block (`$5000-$5757`), freeing up 240+ bytes in the `$2000` engine segment (now 314 bytes free before `$2400`).
- **Driver & DLI Routines ([scenes/title.asm](scenes/title.asm))**:
  - In `title_init`: sets `CHBAS`/`CHBASE` to `intro_font` ($24), hooks `dli_title_scroll` to `VDSLST`, enables NMI `VBLANK + DLI = $C0`, clears `title_scroll_vram` with spaces ($00), and resets scroll state (`title_scroll_fine = 3`).
  - In `title_run`: executes `update_title_scroll` once per frame to advance the ticker. On fire/key exit to `STATE_INTRO`, resets `HSCROL = 0` and restores `NMIEN = $40`.
  - Implemented `dli_title_scroll`: triggers on the blank scanline right before Mode 2, executes `WSYNC`, applies `HSCROL = title_scroll_fine`, sets `COLPF2 = $00` (black background for text line), and `COLPF1 = COLOR1` (text foreground tracks 28-frame fade-in).
  - Implemented `update_title_scroll`: decrements `title_scroll_fine` (3 -> 2 -> 1 -> 0); on underflow wraps to 3, coarse-shifts the 48-byte buffer left by 1 character, fetches next screen code from `title_scroll_text,x`, and advances `title_scroll_idx` (wrapping at `TITLE_SCROLL_TEXT_LEN`).
- **Build Pipeline & Automated Testing**:
  - Updated [Makefile](Makefile) with `TITLE_SCROLL_SRC`, `TITLE_SCROLL_ASM`, and build prerequisites.
  - Added [tests/test_title_scroll.py](tests/test_title_scroll.py) covering text compilation, symbol resolution, `title_init` state initialization, py65 emulation of fine/coarse scroll progression, and `dli_title_scroll` register updates.
  - All 336 unit/integration tests passed; memory validation passed.


## [2026-10-16] - Switch Title Screen to ANTIC Mode D (160x95) and Relocate Scene Data to $5000

- **ANTIC Mode D Title Screen (3,840 bytes vs 7,696 bytes)**:
  - In [scripts/convert_image.py](scripts/convert_image.py), added `convert_image_to_antic_d()` converting 160x95..97 4-color indexed images to standard 160x96 2bpp ANTIC Mode D binary (`gen/title.bin`, 3,840 bytes). Updated CLI to make Mode D default.
  - In [Makefile](Makefile), updated `TITLE_IMG := images/title2.png`.
  - In [scenes/title.asm](scenes/title.asm), converted title screen driver to ANTIC Mode D with 4-color palette (`COLPF0 = $C4` dark green, `COLPF1 = $CA` medium green, `COLPF2 = $EE` light yellow-green, `COLBK = $00` black). Replaced 1-color luminance fade with 8-step fade tables (`title_fade_c0..c2`) smoothly fading all 3 playfield registers over 28 frames.
  - In [main.asm](main.asm), replaced 2-segment Mode F `dlist_title` with a clean 96-line Mode D display list (`dlist_title` at `$6000`, 104 bytes) with a single LMS pointing to `TITLE_VRAM = $4000`.
- **Memory Map Architecture Refactoring (Headroom increased from 1.28 KB to 5.16 KB)**:
  - Relocated `SCENES_DATA` from `$2C30` to `$5000`, now including both `gen/scenes_data.asm` (796 B) and `gen/scenes_dli_data.asm` (666 B).
  - Relocated `RENDER_TABLES` to page-aligned `$7A00`, containing strictly `engine/render_tables.asm` (flip table) and `engine/render.asm` (blitter).
  - Freed 994 bytes of low RAM gap between `$2C1E` and `$3000` (before `GAME_VRAM`).
  - Created 2,626 bytes of contiguous unallocated headroom in `$55BE-$5FFF` allowing scene definitions and DLI tables to scale to 10+ scenes.
  - Created 628 bytes of headroom in `$7D8C-$7FFF` before `$8000` (`TILES_ADDR`).
  - Total allocated User RAM reduced from 39,671 to 35,800 bytes; headroom below `$C000` expanded to 5,160 bytes.
  - Updated [scripts/check_memory.py](scripts/check_memory.py) and [scripts/generate_memory_map.py](scripts/generate_memory_map.py) with the new segment locations.
- **Test Suite Updates**:
  - In [tests/test_convert_image.py](tests/test_convert_image.py), added unit tests for `convert_image_to_antic_d`.
  - In [tests/test_state_machine_and_fade.py](tests/test_state_machine_and_fade.py), updated title initialization and fade tests for 4-color Mode D palette.
  - All 330 unit/integration tests passed; memory validation passed.

## [2026-10-16] - Platform PMG Patterns and Hardcoded SIZEP in DLI Faza A

- **Hardcoded SIZEP in Faza A**:
  - In [engine/dli.asm](engine/dli.asm) (`dli_handler`), replaced dynamic indexing of `dli_sizep1..3,y` with hardcoded `lda #3; sta SIZEP1; sta SIZEP2; sta SIZEP3`, saving 10 cycles in Faza A (~108 cycles total) and eliminating scanline timing overflow into Faza B.
  - SIZEM remains dynamic (`dli_sizem,y`), and Faza C continues resetting `SIZEP1..3 = 0` and `SIZEM = 0` for Zone enemies and secrets.
- **Scene Compiler PMG Pattern Generation**:
  - In [scripts/compile_scenes.py](scripts/compile_scenes.py), added `WIDTH_TO_PMG_PATTERN` mapping (32px $\rightarrow$ `$FF`, 16px $\rightarrow$ `$F0`, 8px $\rightarrow$ `$C0`, 24px $\rightarrow$ `$FC`), `ScenePmgPatterns` dataclass, and extraction of 18 pattern bytes per scene (6 passes $\times$ 3 channels).
  - Generated `scene_{sym}_pmg_patterns` tables and pointer arrays `scene_pmg_patterns_lo` and `scene_pmg_patterns_hi` in [gen/scenes_dli_data.asm](gen/scenes_dli_data.asm).
- **DLI PMG Pattern Staging and Buffer Update**:
  - In [zeropage.asm](zeropage.asm), allocated `dli_scene_pmg_ptr = $BF` (2 bytes, `$BF-$C0`).
  - In [engine/dli.asm](engine/dli.asm), implemented `dli_apply_pmg_patterns` subroutine copying 18 pattern bytes from ROM into PMG memory for P1..P3 across all 6 passes while keeping missiles solid `$FF`.
  - Updated `dli_init` to pre-fill PMG memory using Scene 0 patterns.
  - Updated `dli_stage_scene` to save `scene_pmg_patterns_lo/hi,x` into `dli_scene_pmg_ptr`.
  - Updated `dli_vblank_update` to call `dli_apply_pmg_patterns` upon committing a double-buffer swap (`dli_swap_requested != 0`).
- **Test Suite Updates**:
  - In [tests/test_dli_system.py](tests/test_dli_system.py), updated `test_dli_init_execution` to assert Scene 0 patterns (`$F0` for 16-px platforms) and added `test_pmg_patterns_are_applied_on_scene_change`.
  - Updated test runner helper `step_until_rts_or_rti` to support `target_sp` so nested subroutines do not prematurely terminate harness execution.
  - In [tests/test_compile_scenes.py](tests/test_compile_scenes.py), added `test_pmg_patterns_match_platform_widths`.
  - All 327 unit/integration tests passed; memory validation passed with segment ending at `$67F4` (below `$6800`) and headroom below `$C000` at 1,289 bytes.

## [2026-10-16] - Fix Bottom Platform (Row 5) Visibility and Missile Platform Coloring

- **PMG Pre-fill Scanline Alignment Fix**:
  - In [engine/dli.asm](engine/dli.asm) (`dli_init`), corrected pre-filled solid PMG offsets from `16, 48, 80, 112, 144, 176` to `48, 80, 112, 144, 176, 208`.
  - Mode D lines start after 24 blank scanlines (TV scanline 32), so Mode D line $Y$ corresponds to scanline $32 + (Y \times 2)$. The previous offsets omitted the bottom row 5 (Mode D line 88 $\rightarrow$ scanlines 208..215), leaving `PMG_PLAYER1..3` and `PMG_MISSILES` at 208..215 empty ($00).
  - Row 5 platforms (`platform-014` and `platform-002`) now render solid 8-scanline bars across scanlines 208..215.
- **5th Player Mode and Missile Platform Color Gradient**:
  - In [engine/dli.asm](engine/dli.asm) (`dli_handler`), configured `PRIOR = $11` in Faza A to enable 5th player mode (converting all 4 missiles into a single entity colored by `COLPF3`).
  - In Faza B, added `sta COLPF3` to each of the 8 scanline updates to mirror `COLPM1`, giving missile platforms the exact same color gradient as player platforms without consuming Mode D playfield palette registers.
- **Test Suite Alignment**:
  - In [tests/test_dli_system.py](tests/test_dli_system.py), updated `pas_scanline_starts` to `[48, 80, 112, 144, 176, 208]` and guard line assertions.
  - In [tests/test_compile_scenes.py](tests/test_compile_scenes.py), updated assertion for row 5 x coordinate ($48 + 48 = 96$).
  - All 325 unit/integration tests passed via `.venv/Scripts/python.exe -m pytest`.


- **Unified Catalogue Schema and File**:
  - Combined `platform_profiles.json`, `enemies.json`, and `secrets.json` into a single file [scenes/definitions.json](scenes/definitions.json) containing `version`, `enemies`, `secrets`, and `platform_profiles`.
  - Removed obsolete individual files (`enemies.json`, `secrets.json`, and `platform_profiles.json`).
- **Atari Scene Editor Architecture**:
  - In [atari-scene-editor/src/scene_editor/catalogue_model.py](atari-scene-editor/src/scene_editor/catalogue_model.py), added `definitions_path` to `ProjectCatalogues`, updated `find_definitions_path()`, `load_from_paths()`, `load_from_dir()`, `save_to_dir()`, and `save_to_paths()` to default to and atomically persist [scenes/definitions.json](scenes/definitions.json) (while preserving fallback for legacy separate paths if explicitly supplied).
  - In [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py), updated `CataloguePathsDialog` to configure the unified `definitions.json` path while providing backwards-compatible properties for existing consumers and tests.
  - In [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py), updated `save_catalogues_to_json()`, `save_catalogues_as()`, and `configure_catalogue_paths()` to read, write, and configure [scenes/definitions.json](scenes/definitions.json).
- **Scene Compiler & Build Pipeline Integration**:
  - In [scripts/compile_scenes.py](scripts/compile_scenes.py), updated `load_catalogues()` and `load_platform_profiles()` to parse unified [scenes/definitions.json](scenes/definitions.json) directly.
  - Added `--definitions` / `-d` argument (defaulting to `scenes/definitions.json`) to `compile_scenes()` CLI.
  - In [Makefile](Makefile), updated `SCENES_DEFINITIONS := scenes/definitions.json` as prerequisite and parameter for `compile_scenes.py`.
- **Test Suite Updates**:
  - Updated [tests/test_compile_scenes.py](tests/test_compile_scenes.py), [tests/test_secret_row_constraints.py](tests/test_secret_row_constraints.py), [tests/test_platform_profiles.py](tests/test_platform_profiles.py), and [tests/test_catalogues.py](tests/test_catalogues.py) to assert and load against `scenes/definitions.json`.
  - Full test suite passed (325/325 tests) and clean build via `make all`.

- **Platform Profiles Auto-Save Fix in Atari Scene Editor**:
  - In [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py), added missing persistence calls `self.catalogues.save_to_dir(self.base_dir)` to `_on_new_profile_clicked`, `_on_duplicate_profile_clicked`, `_on_delete_profile_clicked`, and `_on_save_profile_clicked`.
  - Platform color profile changes are now immediately and atomically written to `platform_profiles.json` on disk.
- **Relocated Catalogues to `scenes/` as Default Directory**:
  - Moved `enemies.json`, `secrets.json`, and `platform_profiles.json` into [scenes/](scenes/).
  - Updated `ProjectCatalogues.find_catalogue_paths()` and `find_platform_profiles_path()` in [atari-scene-editor/src/scene_editor/catalogue_model.py](atari-scene-editor/src/scene_editor/catalogue_model.py) to check `scenes/` first and default to `scenes/`.
  - Updated [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py) `CataloguePathsDialog` and [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py) `save_catalogues_to_json()`, `save_catalogues_as()`, and `configure_catalogue_paths()` to configure and persist `platform_profiles.json` alongside enemies and secrets.
- **Scene Compiler & Build Pipeline Updates**:
  - In [scripts/compile_scenes.py](scripts/compile_scenes.py), updated `load_catalogues()`, `load_platform_profiles()`, and `compile_scenes()` to resolve catalogue files from `scenes/` by default with fallback to parent/scenes directories.
  - Updated CLI argument defaults for `--enemies`, `--secrets`, and `--profiles` to `scenes/enemies.json`, `scenes/secrets.json`, and `scenes/platform_profiles.json`.
  - Updated [Makefile](Makefile) target dependency for `scenes_data.asm` and `scenes_dli_data.asm` to use `scenes/enemies.json`, `scenes/secrets.json`, and `scenes/platform_profiles.json`.
- **Test Suite Updates**:
  - Updated [tests/test_compile_scenes.py](tests/test_compile_scenes.py), [tests/test_secret_row_constraints.py](tests/test_secret_row_constraints.py), and [tests/test_catalogues.py](tests/test_catalogues.py) to expect catalogues in `scenes/` and support 3-path configuration dialog.
  - Added new integration tests in [tests/test_platform_profiles.py](tests/test_platform_profiles.py): `test_catalogues_dialog_profile_auto_save_to_scenes_dir` and `test_default_catalogue_paths_point_to_scenes_dir`.
  - All 325 tests passing, `make all` clean build with memory verification.


## [2026-10-16] - Platform Widths via Dynamic SIZEP and SIZEM per Pas

- **Per-Pas Dynamic SIZEP and SIZEM**:
  - Replaced hardcoded `#3` and `#$FF` in Faza A of `dli_handler` in [engine/dli.asm](engine/dli.asm) with dynamic loads from `dli_sizep1,y`, `dli_sizep2,y`, `dli_sizep3,y`, and `dli_sizem,y`.
  - Configured hardware sizes according to GTIA specification: 32 px $\rightarrow$ `SIZEP=3` (quadruple width, 32 color clocks), 16 px $\rightarrow$ `SIZEP=1` (double width, 16 color clocks), 8 px $\rightarrow$ `SIZEP=0` (normal width, 8 color clocks), inactive $\rightarrow$ 0.
  - Configured missile platform size: 32 px (4 $\times$ 8 px) $\rightarrow$ `SIZEM=$FF` (%11111111, 4 quadruple-width missiles spaced by 8 color clocks).
- **PMG Missile Pre-Fill Pattern Correction**:
  - Corrected PMG missiles pre-fill pattern in `dli_init` in [engine/dli.asm](engine/dli.asm) from `$FC` to `$FF` so all 4 missiles (M0..M3) are solid 8-scanline bars in 5th player (5P) mode.
  - Updated [tests/test_dli_system.py](tests/test_dli_system.py) line 191 to assert `$FF`.
- **50-Table DLI Data Expansion (315 Bytes/Scene)**:
  - Added 4 new tables (`sizep1`, `sizep2`, `sizep3`, `sizem`) of 6 bytes each:
    - [engine/dli.asm](engine/dli.asm): allocated double buffers `dli_sizep1..3`, `dli_sizem` (`:16 .byte 0`), updated `DLI_TABLE_COUNT = 50`, and registered table pointers in `dli_table_ptrs_lo` / `hi`.
    - [scripts/compile_scenes.py](scripts/compile_scenes.py): added `sizep1..3` and `sizem` to `SceneDliCompiledData`, updated `compile_scene_dli_data()` to decompose sprite platforms into segments based on `SUPPORTED_SPRITE_WIDTHS` (e.g. 48 px $\rightarrow$ 32 px with SIZEP=2 + 16 px with SIZEP=1) and calculate missile `SIZEM`, updated `generate_scenes_dli_asm()` to output the 4 tables in order matching table pointers.
- **Relocated RENDER_TABLES to $79D0**:
  - Relocated `RENDER_TABLES = $79D0` in [main.asm](main.asm) into the 49-byte gap between Audio (`$79CE`) and `$7A00`, preventing the expanded 634-byte `scenes_dli_data` segment from exceeding `$8000` (`TILES_ADDR`). Segment ends at `$7FD5` with 42 bytes headroom.
  - Updated [scripts/check_memory.py](scripts/check_memory.py) and [scripts/generate_memory_map.py](scripts/generate_memory_map.py) to recognize `0x79D0`.
- **Exporter Validation & Tests**:
  - Added build-time validation in `validate_scene_dli_platforms()` in [scripts/compile_scenes.py](scripts/compile_scenes.py): checks `SIZEP` matches platform width, `SIZEM` matches missile platform, and rejects unsupported widths.
  - Added `test_sizep_matches_platform_width` and `test_sizem_for_missile_platforms` in [tests/test_compile_scenes.py](tests/test_compile_scenes.py).
  - All 323 automated unit and integration tests passed; memory map validated cleanly via `make all`.


## [2026-10-15] - Fix Scene Exporter Platform Allocation & DLI Rendering (Bugs 1-3)

- **Bug 1: Platform Profile Collision in Exporter**:
  - Replaced `color_profile_id` grouping in `compile_scene_dli_data()` in [scripts/compile_scenes.py](scripts/compile_scenes.py) with sequential channel allocation.
  - Platforms in each pas are now sorted by X ascending and assigned to channels sequentially, ensuring platforms sharing the same profile (e.g. `platform-010` and `platform-011` in Pas 1) do not overwrite each other. Color profiles are assigned per occupied channel.
- **Bug 2: Multi-Segment Wide Platform Rendering**:
  - Implemented multi-segment chunking for platforms wider than 32 px in [scripts/compile_scenes.py](scripts/compile_scenes.py): sprite platforms $> 32$ px are split into 32 px segments across consecutive player channels (P1 $\rightarrow$ P2 $\rightarrow$ P3), with any remainder width mapped to missile channels (8 px per missile).
  - Missile platforms are segmented into 8 px chunks across M0..M3.
  - In Scene 1 (`01-forest`) Pas 5 ($y=88$), `platform-002` (96 px sprite) now allocates P1=$61, P2=$81, P3=$A1, while `platform-014` (32 px missile) allocates M0=$40, M1=$48, M2=$50, M3=$58 (total 128 px across 4 active channels).
- **Bug 3: Missing HPOSM0 in DLI Faza A & 46-Table Format Expansion**:
  - Added `lda dli_hpos_m0,y; sta HPOSM0` before `HPOSM1` in Faza A of `dli_handler` in [engine/dli.asm](engine/dli.asm).
  - Expanded DLI table format from 45 to 46 tables (291 bytes per scene: $46 \times 6 + 15$ bytes Zone 0):
    - Added `dli_hpos_m0 :16 .byte 0` to double-buffered tables in [engine/dli.asm](engine/dli.asm).
    - Updated `DLI_TABLE_COUNT = 46` and updated `dli_table_ptrs_lo` / `dli_table_ptrs_hi`.
    - Added `hpos_m0` to `SceneDliCompiledData` and updated `generate_scenes_dli_asm()` in [scripts/compile_scenes.py](scripts/compile_scenes.py).
- **Build-Time Hardware Validation**:
  - Added `validate_scene_dli_platforms()` in [scripts/compile_scenes.py](scripts/compile_scenes.py) enforcing:
    1. Every platform from JSON has a matching HPOS in generated data.
    2. Sum of platform widths in each pas does not exceed 128 px.
    3. Active channels per pas do not exceed 4 (P1, P2, P3, 5P).
    4. Platforms $> 32$ px occupy consecutive player channels P1 $\rightarrow$ P2 $\rightarrow$ P3 without skips.
- **Automated Verification**:
  - Added `test_scene_dli_data_matches_json` and `test_validate_scene_dli_platforms_rejects_invalid` in [tests/test_compile_scenes.py](tests/test_compile_scenes.py).
  - Full test suite passed (321 tests), `check_memory` passed with 1,487 bytes headroom below `$C000`, and `make all` clean.

## [2026-10-15] - Shared Display List & Unified DLI Architecture

- **Unified Display List (`dlist_game`) & DLI Triggers**:
  - Configured shared 96-line ANTIC Mode D ($0D) Display List in [main.asm](main.asm) with Display List Interrupt flag (`DL_DLI = $80`) on lines 7, 23, 39, 55, 71, and 87 (the last scanline before each of the 6 platform pas).
  - Maintained single shared Display List invariant without scene-specific colors, object IDs, or positions.
- **Unified 3-Phase DLI Engine & Double Buffering**:
  - Implemented [engine/dli.asm](engine/dli.asm) containing `dli_init`, `dli_stage_scene`, `dli_vblank_update`, and `dli_handler`.
  - Allocated double buffers at `$6100` (`DLI_BUFFERS`) with 45 tables (Buf 0 at +0, Buf 1 at +8) for zero-branch, `absolute,Y` indexed register staging.
  - Zero Page allocation in [zeropage.asm](zeropage.asm) for register preservation and state tracking (`dli_save_a`, `dli_save_x`, `dli_save_y`, `dli_pas_idx`, `dli_active_offset`, `dli_pending_offset`, `dli_swap_requested`).
  - **Faza A** (pre-WSYNC on scanline before pas): Sets up PMG sizes (`SIZEP1..3 = $03`, `SIZEM = $FC`), positions (`HPOSP1..3`, `HPOSM1..3`), and resets `PRIOR` bit 4 ($04).
  - **Faza B** (8 scanlines of pas): Unrolled per-scanline color updates for `COLPM1`, `COLPM2`, `COLPM3` in HBLANK, interspersed with `WSYNC`.
  - **Faza C** (post-pas guard line): Updates background palette `COLPF0..2` (swapping lower palette after pas 40, restoring upper palette after pas 88), restores normal width (`SIZEP1..3 = $00`, `SIZEM = $00`), restores `PRIOR` bit 4 ($14) if secret present, sets enemy P1..P3 / secret M0..M3 positions and colors for the upcoming zone, and increments pas counter.
  - Strict preservation of Hero Player 0: DLI never accesses `HPOSP0`, `SIZEP0`, or `COLPM0`. `COLBK` kept permanently black ($00).
- **Scene DLI Data Compiler & Exporter**:
  - Extended [scripts/compile_scenes.py](scripts/compile_scenes.py) with `compile_scene_dli_data()` and `generate_scenes_dli_asm()`.
  - Generates [gen/scenes_dli_data.asm](gen/scenes_dli_data.asm) (285 bytes per scene) mapping platforms, platform profiles (8 scanlines per profile), enemies, secrets, and palettes into SoA format.
- **Engine Lifecycle Integration**:
  - Initialized DLI system in [scenes/game.asm](scenes/game.asm) (`dli_init`, `dli_stage_scene`, `dli_vblank_update`).
  - Set hardware registers `SDMCTL = $3E` and `GRACTL = $03` for full PMG DMA and latching.
- **Build System & Validation**:
  - Updated [Makefile](Makefile), [scripts/check_memory.py](scripts/check_memory.py), and [scripts/generate_memory_map.py](scripts/generate_memory_map.py) for the `$6100` DLI segment.
  - Added [tests/test_dli_system.py](tests/test_dli_system.py) with 6 py65 CPU emulation tests verifying DLI structure, memory layout, PMG pre-fills, buffer staging isolation, VBLANK atomic commits, 6-pas execution, and Hero isolation.
  - Updated existing tests [tests/test_convert_tiles.py](tests/test_convert_tiles.py), [tests/test_compile_scenes.py](tests/test_compile_scenes.py), and [tests/test_memory_map.py](tests/test_memory_map.py).

## [2026-10-15] - Platform Profile ID Range Constraint (Integer 1-255) & QPainter Import Fix

- **Platform Profile ID Integer Constraint (1-255)**:
  - Updated `PlatformColorProfile.id` to `int` in [atari-scene-editor/src/scene_editor/catalogue_model.py](atari-scene-editor/src/scene_editor/catalogue_model.py), enforcing integer range 1-255 in `.validate()` and `.from_dict()` (rejecting 0, negative values, values > 255, booleans, and non-numeric strings, while parsing numeric strings).
  - Updated `DEFAULT_PLATFORM_PROFILES` with integer IDs: `1` (Glacial Ice), `2` (Ancient Gold), `3` (Castle Stone), and `4` (Forest Moss).
  - Updated `ProjectCatalogues.platform_profiles` mapping from `dict[str, PlatformColorProfile]` to `dict[int, PlatformColorProfile]`, normalizing profile IDs with `_normalize_id()` in `add_platform_profile`, `update_platform_profile`, `get_platform_profile`, `remove_platform_profile`, `get_profile_platform_usage`, and `duplicate_platform_profile`.
  - Updated `PlatformElement.color_profile_id` in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py) to `Optional[int] = None`, with integer 1-255 range validation in `.validate()` and `.from_dict()`.
  - Updated `ChangePlatformColorProfileCommand` in [atari-scene-editor/src/scene_editor/commands.py](atari-scene-editor/src/scene_editor/commands.py) to use `Optional[int]` for old and new profile IDs.
  - Updated `CataloguesDialog` profile management UI in [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py) to use `QSpinBox` with range 1-255 (`self.prof_id_spin`) instead of `QLineEdit`, allocating next available integer in `_on_new_profile_clicked()` and validating `1 <= new_id <= 255` in `_on_save_profile_clicked()`.
  - Updated `load_platform_profiles()` and platform parsing in [scripts/compile_scenes.py](scripts/compile_scenes.py) to load integer IDs and map `color_profile_id: int | None`.
- **Fixed QPainter paintEvent NameError**:
  - Imported `QPainter` from `PySide6.QtGui` in [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py), resolving `NameError: name 'QPainter' is not defined` inside `PlatformPreviewBar.paintEvent`.
- **Updated Test Suite**:
  - Updated and extended [tests/test_platform_profiles.py](tests/test_platform_profiles.py) to test integer profile IDs (1-255), including boundary tests (1, 255), numeric string conversion, rejection of 0, negative, >255, non-numeric strings, and booleans for both `PlatformColorProfile` and `PlatformElement`. All 313 tests passing clean.

- **Updated Hardware Secret Row Limit Constraint** in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py):
  - Enforced rule: on each platform row (`row_y`), at most one secret per unique `Dependency` value is allowed (including `Dependency = None`). Multiple secrets on the same row are permitted if and only if each has a distinct dependency.
  - Removed and replaced the previous 4-secrets-per-stage restriction (`MAX_SECRETS_PER_STAGE`).
  - Added helper methods `Scene.get_secret_dependency(definition_id)` and `Scene.get_dependency_display_name(dependency)`.
  - Added `Scene.duplicate_object()` with integrated validation against row constraints.
  - Updated `Scene.validate()` to group row secrets by `dep = self.get_secret_dependency(definition_id)` and raise `ObjectLimitExceededError` with descriptive conflict details if duplicate dependencies are found.
  - Updated `Scene.can_add_object_to_platform()` to block adding secrets whose resolved dependency matches an existing secret on the target platform row.
  - Updated `Scene.move_platform()` and `Scene.move_object()` to validate target row dependencies and prevent secret collision across platforms moving to the same row.
  - Updated `Scene.update_object_props()` to guarantee scene validity and roll back on dependency collision.
- **Enhanced Catalogue Model & Secret Dependency Conflict Detection** in [atari-scene-editor/src/scene_editor/catalogue_model.py](atari-scene-editor/src/scene_editor/catalogue_model.py) and [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py):
  - Added `ProjectCatalogues.get_secret_dependency()`, `ProjectCatalogues.get_dependency_display_name()`, and `ProjectCatalogues.check_scene_secret_dependency_conflict()`.
  - In `CataloguesDialog._on_save_secret_clicked()`, validated whether editing a secret's dependency introduces a row conflict on any existing scene secret instance, blocking the update and presenting a user warning if violated.
- **Integrated Validation in UI and Serialization** in [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py) and [atari-scene-editor/src/scene_editor/json_serializer.py](atari-scene-editor/src/scene_editor/json_serializer.py):
  - Added row dependency collision pre-checks in `_on_obj_prop_definition_changed` and `_on_obj_prop_type_changed`.
  - Updated `SceneSerializer.from_dict()`, `from_json()`, and `load_from_file()` to support catalogues resolution and detect row dependency violations during project import and scene loading, raising `CorruptedFileError`.
- **Enforced Build-Time Export Validation** in [scripts/compile_scenes.py](scripts/compile_scenes.py):
  - Added `dependency: Optional[int] = None` to `CatalogueItem` and loaded secret dependencies in `load_catalogues()`.
  - Added validation in `parse_scene_json()` ensuring no platform row contains duplicate secret dependencies prior to assembly generation.
- **Updated Project Data & Catalogues** in [secrets.json](secrets.json):
  - Set `dependency: 1` on Exit Door (id 2) to establish the linear chain (Gold Key -> Exit Door), ensuring compatibility for existing multi-secret rows in `scenes/01-forest.json` and `scenes/02-forest-castle.json`.
- **Created Comprehensive Acceptance Test Suite** in [tests/test_secret_row_constraints.py](tests/test_secret_row_constraints.py) and updated [tests/test_scene_objects.py](tests/test_scene_objects.py):
  - Verified all 9 acceptance criteria: multiple distinct dependencies per row allowed (Examples A & D), duplicate `None` rejected (Example B), duplicate parent dependencies rejected across different secret types (Example C), same dependency across different rows allowed, horizontal/vertical platform and object moves blocked on collision, catalogue dependency changes protected against scene conflicts, duplicate secret creation safeguarded, import/export corruption detection, and existing scene stability. All 312 tests passing clean.

- **Implemented Atari GTIA Color/Luminance Palette & Validation Engine** in [atari-scene-editor/src/scene_editor/atari_palette.py](atari-scene-editor/src/scene_editor/atari_palette.py):
  - Provided 256-color composite Atari GTIA RGB palette table `ATARI_GTIA_PALETTE`.
  - Added conversion helpers `atari_color_to_rgb`, `atari_color_to_hex_rgb`, and `format_atari_color_hex` (`0x{:02X}`).
  - Enforced hardware-accurate Atari GTIA color register validation in `parse_atari_color_hex` and `is_valid_atari_color_string`: checks range `0x00`-`0xFE` and requires bit 0 to be 0 (strictly even byte values).
- **Added Platform Color Profiles Model & Catalogue Management** in [atari-scene-editor/src/scene_editor/catalogue_model.py](atari-scene-editor/src/scene_editor/catalogue_model.py):
  - Created `PlatformColorProfile` dataclass containing `id`, `name`, `colors` (strictly 8 integers corresponding to the 8 scanlines of a 4-pixel ANTIC Mode D platform), and optional `description`.
  - Added starter presets (`profile_ice`, `profile_gold`, `profile_stone`, `profile_forest`) in `DEFAULT_PLATFORM_PROFILES` and standalone `platform_profiles.json`.
  - Added CRUD operations to `ProjectCatalogues`: `add_platform_profile`, `update_platform_profile`, `get_platform_profile`, `duplicate_platform_profile`, `get_profile_platform_usage`, and safe deletion in `remove_platform_profile` (raises `ProfileInUseError` unless `force=True`, safely unlinking references from platforms).
  - Integrated persistence paths and directory auto-save/load (`platform_profiles.json`).
- **Extended Scene Model, Item Rendering & Commands** in [atari-scene-editor/src/scene_editor/scene_model.py](atari-scene-editor/src/scene_editor/scene_model.py), [atari-scene-editor/src/scene_editor/scene_items.py](atari-scene-editor/src/scene_editor/scene_items.py), and [atari-scene-editor/src/scene_editor/commands.py](atari-scene-editor/src/scene_editor/commands.py):
  - Added `color_profile_id: Optional[str] = None` to `PlatformElement` with full backwards compatibility for legacy scene files.
  - Implemented `ChangePlatformColorProfileCommand` for undo/redo support.
  - Updated `PlatformGraphicsItem` and `SceneView`: renders 4 Mode D pixel rows where each row displays the color corresponding to scanlines `r*2` from the assigned profile.
- **Added Platform Profiles UI Tab & Platform Property Inspector Combo** in [atari-scene-editor/src/scene_editor/catalogue_dialog.py](atari-scene-editor/src/scene_editor/catalogue_dialog.py) and [atari-scene-editor/src/scene_editor/main_window.py](atari-scene-editor/src/scene_editor/main_window.py):
  - Added "Platform Profiles" tab to `CataloguesDialog` with vertical 8-scanline gradient preview bar (`PlatformPreviewBar`), 8 editable hex fields with real-time swatch previews and `#RRGGBB` labels, new, duplicate, delete, and revert buttons.
  - Added color profile dropdown to platform creator bar and platform property panel, enabling individual assignment per platform.
- **Updated Scene Exporter and Build Tooling** in [scripts/compile_scenes.py](scripts/compile_scenes.py), [main.asm](main.asm), [Makefile](Makefile), [scripts/check_memory.py](scripts/check_memory.py), and [scripts/generate_memory_map.py](scripts/generate_memory_map.py):
  - Added `--profiles` argument to `compile_scenes.py` to resolve 8-scanline colors per platform into `PlatformData`.
  - Generated Structure-of-Arrays (SoA) tables `scene_{symbol}_plat_color_sl1` through `scene_{symbol}_plat_color_sl8` and master index pointer tables `scene_plat_color_sl1_lo`/`hi` .. `scene_plat_color_sl8_lo`/`hi` in [gen/scenes_data.asm](gen/scenes_data.asm).
  - Repositioned `TILES_META` to `$2A30` and `SCENES_DATA` to `$2C30`, preventing overlap with `GAME_VRAM` ($3000) while keeping all `org` addresses strictly ascending.
- **Added Comprehensive Test Suite** in [tests/test_platform_profiles.py](tests/test_platform_profiles.py):
  - Added 11 automated pytest tests verifying all acceptance criteria: creation, hex/even validation, RGB conversion, editing/cloning, multi-platform sharing, independent assignments, reactive updates, safe deletion with usage guards, save/reload roundtrip, exact-order 8-scanline assembly export, and backwards compatibility.


## [2026-10-15] - Memory Map Reporting Tool and Graphical Vector PDF Generator

- **Created Memory Map Generator Tool** in [scripts/generate_memory_map.py](scripts/generate_memory_map.py):
  - Parses Atari DOS XEX binary segments and calculates continuous memory ranges from `$2000` to `$BFFF`.
  - Computes exact addresses, sizes in bytes, and categorization for all allocated segments (Code, Graphics VRAM, Tileset Bitmaps, Display Lists, Audio, PMG, Metadata).
  - Identifies and ranks all unallocated free memory gaps (headroom) across user RAM.
  - Formats detailed Zero Page allocation breakdown (`$00-$FF`) highlighting the 72 free bytes (`$B8-$FF`).
  - Outputs a color-coded terminal report with summary statistics and headroom metrics.
  - Generates high-resolution graphical vector PDF diagram (`memory_map.pdf`) using Matplotlib:
    - Left column: Full 64 KB memory space overview (`$0000-$FFFF`) with system RAM, DOS, User area, OS ROM, and hardware I/O.
    - Center column: Zoomed User RAM diagram (`$2000-$BFFF`) with color-coded segments and highlighted free gaps.
    - Right sidebar: Memory utilization statistics card, category legend, top free memory regions table, and Zero Page layout card.
- **Added Build Integration** in [Makefile](Makefile):
  - Added `make memory_map` and `make map` targets to regenerate `memory_map.pdf` directly from the compiled binary.
- **Added Automated Pytest Test Suite** in [tests/test_memory_map.py](tests/test_memory_map.py):
  - Tests XEX segment parsing, segment identification, address continuity, and PDF file generation.
  - Verified all 292 tests pass and memory validation passes with 3,984 bytes headroom.


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
