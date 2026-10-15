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

# Assets sources and artifacts
TITLE_IMG        := images/title.png
TITLE_BIN        := $(GEN_DIR)/title.bin

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

ASM_SRCS         := main.asm hardware.asm zeropage.asm lib/audio.asm lib/player.asm \
                    scenes/title.asm scenes/intro.asm scenes/game.asm scenes/gameover.asm

.PHONY: all assets tiles music data tests xex check_memory run clean

all: assets tiles music data xex tests check_memory

# ------------------------------------------------------------------------------
# 1. Assets conversion
# ------------------------------------------------------------------------------
assets: $(TITLE_BIN) $(INTRO_TXT_BIN) $(TILES_ARTIFACTS)

$(TITLE_BIN): $(TITLE_IMG) scripts/convert_image.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/convert_image.py $(TITLE_IMG) -o $(TITLE_BIN)

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
music: $(MUSIC_TITLE_ASM)

$(MUSIC_TITLE_ASM): $(MUSIC_TITLE_JSON) scripts/compile_music.py
	@$(MKDIR) $(GEN_DIR)
	$(PYTHON) scripts/compile_music.py -i $< -o $@ -l music_title_data

# ------------------------------------------------------------------------------
# 4. Data generation (future data tables / level definitions)
# ------------------------------------------------------------------------------
data:
	@echo "Data pipeline: up to date."

# ------------------------------------------------------------------------------
# 5. Binary assembly (MADS)
# ------------------------------------------------------------------------------
xex: $(TARGET)

$(TARGET): $(ASM_SRCS) $(TITLE_BIN) $(MUSIC_TITLE_ASM) $(INTRO_TXT_BIN) $(INTRO_FONT) $(TILES_ARTIFACTS)
	@$(MKDIR) $(GEN_DIR)
	$(MADS) -i:lib main.asm -o:$(TARGET) -l:$(GEN_DIR)/main.lst -t:$(GEN_DIR)/main.lab

# ------------------------------------------------------------------------------
# 5. Automated testing (Pytest suite + py65 emulation)
# ------------------------------------------------------------------------------
tests: $(TARGET)
	$(PYTHON) -m pytest -v

# ------------------------------------------------------------------------------
# 6. Automated memory map verification
# ------------------------------------------------------------------------------
check_memory: $(TARGET) scripts/check_memory.py
	$(PYTHON) scripts/check_memory.py $(TARGET)

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
