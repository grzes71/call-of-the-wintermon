# ==============================================================================
# Makefile — Call of the Wintermon (Atari 800XL / 65XE)
# Target: 64 KB RAM MOS 6502 (MADS Assembler + Python Tooling)
# ==============================================================================

# Toolchain configuration
PYTHON           ?= .venv/Scripts/python.exe
MADS             ?= c:/Apps/Mad-Assembler-2.1.6/bin/windows_x86_64/mads.exe
ALTIRRA          ?= C:/Apps/Altirra-4.40/Altirra64.exe

# Portable filesystem helpers (cross-platform cmd / powershell / sh)
MKDIR            := $(PYTHON) -c "import os, sys; os.makedirs(sys.argv[1], exist_ok=True)"
RM               := $(PYTHON) -c "import os, sys, shutil; [shutil.rmtree(a, ignore_errors=True) if os.path.isdir(a) else os.remove(a) for a in sys.argv[1:] if os.path.exists(a)]"

# Build targets and artifacts
TARGET           := call_of_the_wintermon.xex
GEN_DIR          := gen

TITLE_VSCROLL_SRC := scroll/title.txt
TITLE_VSCROLL_ASM := $(GEN_DIR)/title_vscroll_data.asm

TITLE_TXT_SRC    := texts/title.txt
TITLE_TXT_ASM    := $(GEN_DIR)/title_text_data.asm

TITLE_LOGO_JSON  := title/title.json
TITLE_LOGO_INC   := $(GEN_DIR)/title_logo.inc

INTRO_TXT_SRC    := texts/intro.txt
INTRO_TXT_BIN    := $(GEN_DIR)/intro_text.bin
INTRO_FONT       := fonts/font.fnt

TILES_DIR        := tiles
TILES_SRCS       := $(wildcard $(TILES_DIR)/*.png)
TILES_BIN_CAST   := $(GEN_DIR)/tiles_castles.bin
TILES_BIN_DEP    := $(GEN_DIR)/tiles_depths.bin
TILES_BIN_HELL   := $(GEN_DIR)/tiles_hell.bin
TILES_BIN_TREE   := $(GEN_DIR)/tiles_trees.bin
TILES_ASM        := $(GEN_DIR)/tiles_data.asm
TILES_ARTIFACTS  := $(TILES_BIN_CAST) $(TILES_BIN_DEP) $(TILES_BIN_HELL) $(TILES_BIN_TREE) $(TILES_ASM)

MUSIC_TITLE_JSON := music/title.json
MUSIC_TITLE_ASM  := $(GEN_DIR)/title_music.asm
MUSIC_INTRO_DSL  := music/intro.dsl
MUSIC_INTRO_ASM  := $(GEN_DIR)/intro_music.asm

SPRITES_SRC       := sprites/objects.sprite.json
SPRITES_ASM       := $(GEN_DIR)/sprites_data.asm
PLAYER_SPRITE_SRC := sprites/player.sprite.json
PLAYER_SPRITE_ASM := $(GEN_DIR)/player_sprites.asm

SCENES_MANIFEST    := scenes/scenes.json
SCENES_DIR         := scenes
SCENES_DEFINITIONS := scenes/definitions.json
SCENES_DEFINITIONS_RESOLVED := $(GEN_DIR)/definitions_resolved.json
SCENES_SRCS        := $(wildcard $(SCENES_DIR)/*.json)
SCENES_ASM         := $(GEN_DIR)/scenes_data.asm
SCENES_DLI_ASM     := $(GEN_DIR)/scenes_dli_data.asm

ASM_SRCS         := main.asm hardware.asm zeropage.asm lib/audio.asm lib/player.asm \
                    engine/dli.asm engine/render.asm engine/render_tables.asm engine/secrets.asm \
                    engine/enemies.asm engine/player.asm engine/status_line.asm engine/sfx.asm \
                    engine/sfx_victory.asm \
                    scenes/title.asm scenes/intro.asm scenes/game.asm scenes/gameover.asm


.PHONY: all assets tiles music data tests xex check_memory run clean

all: assets tiles music data xex tests check_memory

# ------------------------------------------------------------------------------
# 1. Assets conversion
# ------------------------------------------------------------------------------
assets: $(TITLE_VSCROLL_ASM) $(TITLE_TXT_ASM) $(TITLE_LOGO_INC) $(INTRO_TXT_BIN) $(TILES_ARTIFACTS)

$(TITLE_VSCROLL_ASM): $(TITLE_VSCROLL_SRC) scripts/compile_title_vscroll.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/compile_title_vscroll.py -i $(TITLE_VSCROLL_SRC) -o $(TITLE_VSCROLL_ASM)

$(TITLE_TXT_ASM): $(TITLE_TXT_SRC) scripts/compile_title_text.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/compile_title_text.py -i $(TITLE_TXT_SRC) -o $(TITLE_TXT_ASM)

$(TITLE_LOGO_INC): $(TITLE_LOGO_JSON) scripts/convert_title_logo.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/convert_title_logo.py $(TITLE_LOGO_JSON) $(TITLE_LOGO_INC)

$(INTRO_TXT_BIN): $(INTRO_TXT_SRC) scripts/gen_intro_text.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/gen_intro_text.py -i $(INTRO_TXT_SRC) -o $(INTRO_TXT_BIN)

# ------------------------------------------------------------------------------
# 2. Tiles conversion (ANTIC Mode E 160x96 2bpp)
# ------------------------------------------------------------------------------
tiles: $(TILES_ARTIFACTS)

$(TILES_ARTIFACTS): $(TILES_SRCS) scripts/convert_tiles.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/convert_tiles.py --tiles-dir $(TILES_DIR) --gen-dir $(GEN_DIR)

# ------------------------------------------------------------------------------
# 3. Audio / Music compilation
# ------------------------------------------------------------------------------
music: $(MUSIC_TITLE_ASM) $(MUSIC_INTRO_ASM)

$(MUSIC_TITLE_ASM): $(MUSIC_TITLE_JSON) scripts/compile_music.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/compile_music.py -i $< -o $@ -l music_title_data

$(MUSIC_INTRO_ASM): $(MUSIC_INTRO_DSL) scripts/compile_music.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/compile_music.py -i $< -o $@ -l music_intro_data

# ------------------------------------------------------------------------------
# 4. Data generation (Scene structures, platforms, objects, sprites)
# ------------------------------------------------------------------------------
data: $(SCENES_DEFINITIONS_RESOLVED) $(SPRITES_ASM) $(PLAYER_SPRITE_ASM) $(SCENES_ASM) $(SCENES_DLI_ASM)

$(SCENES_DEFINITIONS_RESOLVED): $(SCENES_DEFINITIONS) $(SPRITES_SRC) scripts/sprite_links.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/sprite_links.py --definitions $(SCENES_DEFINITIONS) --sprites $(SPRITES_SRC) --output $@

$(SPRITES_ASM): $(SPRITES_SRC) $(SCENES_DEFINITIONS_RESOLVED) $(SCENES_MANIFEST) $(SCENES_SRCS) scripts/compile_sprites.py scripts/sprite_roles.py scripts/sprite_links.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/compile_sprites.py --mode missiles -i $(SPRITES_SRC) -o $@ --definitions $(SCENES_DEFINITIONS_RESOLVED) --scenes $(SCENES_MANIFEST)

$(PLAYER_SPRITE_ASM): $(PLAYER_SPRITE_SRC) scripts/compile_sprites.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/compile_sprites.py --mode player -i $< -o $@

$(SCENES_ASM) $(SCENES_DLI_ASM): $(SCENES_MANIFEST) $(SCENES_SRCS) $(SCENES_DEFINITIONS_RESOLVED) $(SPRITES_SRC) $(SPRITES_ASM) scripts/compile_scenes.py scripts/sprite_links.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/compile_scenes.py --manifest $(SCENES_MANIFEST) --output $(SCENES_ASM) --definitions $(SCENES_DEFINITIONS_RESOLVED) --sprites $(SPRITES_SRC)


# ------------------------------------------------------------------------------
# 5. Binary assembly (MADS)
# ------------------------------------------------------------------------------
xex: $(TARGET)

$(TARGET): $(ASM_SRCS) $(TITLE_VSCROLL_ASM) $(TITLE_TXT_ASM) $(TITLE_LOGO_INC) $(MUSIC_TITLE_ASM) $(MUSIC_INTRO_ASM) $(INTRO_TXT_BIN) $(INTRO_FONT) $(TILES_ARTIFACTS) $(SPRITES_ASM) $(PLAYER_SPRITE_ASM) $(SCENES_ASM)
	@$(MKDIR) $(GEN_DIR)
	$(MADS) -i:lib main.asm -o:$(TARGET) -l:$(GEN_DIR)/main.lst -t:$(GEN_DIR)/main.lab


# ------------------------------------------------------------------------------
# 5. Automated testing (Pytest suite + py65 emulation)
# ------------------------------------------------------------------------------
tests: $(TARGET)
	$(PYTHON) -m pytest -v

# ------------------------------------------------------------------------------
# 6. Automated memory map verification and visual report
# ------------------------------------------------------------------------------
check_memory: $(TARGET) scripts/check_memory.py
	$(PYTHON) scripts/check_memory.py $(TARGET)

memory_map: $(TARGET) scripts/generate_memory_map.py
	$(PYTHON) scripts/generate_memory_map.py $(TARGET) --pdf memory_map.pdf

map: memory_map

# ------------------------------------------------------------------------------
# 7. Emulator execution (Altirra)
# ------------------------------------------------------------------------------
run: $(TARGET)
	cmd /c start "" "$(ALTIRRA)" /run "$(TARGET)"

# ------------------------------------------------------------------------------
# Clean build artifacts
# ------------------------------------------------------------------------------
clean:
	@$(RM) $(GEN_DIR) $(TARGET)
	@echo "Clean completed."
