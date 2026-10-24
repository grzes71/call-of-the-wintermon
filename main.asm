; ==============================================================================
; MAIN.ASM — Atari 8-bit State Machine & Game Engine Entry Point
; Target: Atari 800XL / 65XE (64 KB RAM)
; Mode: ANTIC Mode E & D (Title 2bpp) + Mode 2 (Scroller & Intro) / ANTIC Mode D (Game)
; Audio: Atari POKEY Music (4-channel relocatable player)
; ==============================================================================

    icl 'hardware.asm'
    icl 'zeropage.asm'

; --- Memory Map Equates ---
CODE_ADDR   = $2000
FONT_ADDR   = $2400     ; 1 KB aligned font (1024 bytes: $2400-$27FF)
INTRO_VRAM  = $2800     ; Intro text VRAM (480 bytes: $2800-$29DF, 12 lines x 40 cols)
INTRO_DLIST = $2A00     ; Intro display list (~30 bytes: $2A00-$2A1D)
TILES_META  = $2A30     ; Tileset SoA metadata & row offset tables (~494 bytes: $2A30-$2C1D)
GAME_VRAM   = $3000     ; Playfield VRAM: ANTIC Mode D ($0D) 160x96 2bpp (3,840 bytes: $3000-$3EFF, 4 KB aligned)
GAME_DLIST  = $3F00     ; Gameplay Display List (~107 bytes: $3F00-$3F6A, 1 KB aligned)
TITLE_VRAM  = $4000     ; Title Scroll VRAM & Text ($4000-$40C6, 4 KB aligned)
SCENES_DATA = $5000     ; Scene runtime engine (secrets + channel dispatch/enemies/sfx): $5000-$5BFF
SCENE_TABLES = $B300    ; Scene SoA tables + pointer tables + per-scene DLI blocks, in the RAM freed
                        ; by the smaller tilesets (tilesets end at $B21F, so 224 B of tile headroom
                        ; is kept before the tables)
DLIST_ADDR  = $6000     ; Title Display List (99 bytes: $6000-$6062, 1 KB aligned)
DLI_BUFFERS = $6100     ; Unified DLI Engine & Double Buffers ($6100-$6706)
GAMEOVER_CODE = $5C00    ; Game Over / Victory module: 2 display lists + DLI chain + builder
                        ; (free tail of the $5000 block: runtime ends $5B94, title DL at $6000)
GAMEOVER_TEXT = $BC00   ; Game Over texts (generated compact data, ~850 B)
RENDER_TABLES = $6800   ; Render Lookup Tables: Flip byte (256 B, page aligned) + Playfield row offsets (192 B) — reclaims $6800-$6AFF (MEM-006)
INTRO_CODE_ADDR = $69C0 ; Intro screen handler: relocated out of the $2000 CODE block (which was down to 21 B of headroom)
PMG_ADDR    = $6800     ; Player-Missile Graphics base: 2 KB aligned (PMBASE=$68, active memory $6B00-$6FFF)
AUDIO_ADDR  = $7000     ; Audio Player & Music Buffers
RENDER_CODE = $7A00     ; Playfield Blitter Engine & Sprites Data (headroom before $8000 expanded)
TILES_ADDR  = $8000     ; ANTIC Mode E Tileset Bitmaps (16,237 bytes: $8000-$BF6C)

; --- Gameplay & Title Buffer Equates ---
GAME_VRAM_SIZE        = 3840  ; 40 bytes/line * 96 lines
GAME_VRAM_LINES       = 96
GAME_VRAM_PITCH       = 40
TITLE_VS_BUF_LEN      = 120   ; 3 lines * 40 bytes for vertical scroll window (L0, L1, L2)

; --- PMG Equates (Single-Line Resolution at PMBASE=$68, active memory $6B00-$6FFF) ---
PMG_ACTIVE_SIZE = 1280  ; 5 pages: Missiles ($6B00) + P0..P3 ($6C00..$6FFF)
PMG_SIZE        = 1280  ; Alias for active PMG size
PMBASE_PAGE     = >PMG_ADDR
PMG_MISSILES    = PMG_ADDR + $0300
PMG_PLAYER0     = PMG_ADDR + $0400
PMG_PLAYER1     = PMG_ADDR + $0500
PMG_PLAYER2     = PMG_ADDR + $0600
PMG_PLAYER3     = PMG_ADDR + $0700

; ==============================================================================
; CODE SEGMENT ($2000)
; ==============================================================================
    org CODE_ADDR

start
    ; Disable BASIC ROM ($A000-$BFFF) to expose full 64 KB RAM
    sei
    lda PORTB
    ora #$02            ; Bit 1 = 1: disable BASIC ROM
    sta PORTB
    cli

    ; Initialize state machine variables
    lda #STATE_TITLE
    sta game_state
    lda #$FF
    sta current_state   ; Force initialization on first entry

    lda #1
    sta title_first_run ; First run: enable 28-frame fade-in

    lda #0
    sta active_scene_id ; Default to scene 0 (Forest)

main_loop
    ; Check if active state needs initialization
    lda game_state
    cmp current_state
    beq @run_active

    ; State transition: update current_state and dispatch scene init
    sta current_state
    cmp #STATE_TITLE
    bne @chk_intro_init
    jsr title_init
    jmp @run_active

@chk_intro_init
    cmp #STATE_INTRO
    bne @chk_game_init
    jsr intro_init
    jmp @run_active

@chk_game_init
    cmp #STATE_GAME
    bne @chk_over_init
    jsr game_init
    jmp @run_active

@chk_over_init
    jsr gameover_init

@run_active
    ; Dispatch active state frame runner
    lda current_state
    cmp #STATE_TITLE
    bne @chk_intro_run
    jsr title_run
    jmp main_loop

@chk_intro_run
    cmp #STATE_INTRO
    bne @chk_game_run
    jsr intro_run
    jmp main_loop

@chk_game_run
    cmp #STATE_GAME
    bne @chk_over_run
    jsr game_run
    jmp main_loop

@chk_over_run
    jsr gameover_run
    jmp main_loop

; ==============================================================================
; SCENE MODULES (Game)
; scenes/intro.asm lives at INTRO_CODE_ADDR ($69C0) so this block stays clear of
; the intro font at $2400 and has room for future gameplay logic.
; ==============================================================================
    icl 'scenes/game.asm'

; ==============================================================================
; INTRO FONT SEGMENT ($2400) - 1024 bytes (1 KB boundary aligned)
; ==============================================================================
    org FONT_ADDR
intro_font
    ins 'fonts/font.fnt'

; ==============================================================================
; INTRO TEXT VRAM SEGMENT ($2800) - 480 bytes (12 lines x 40 bytes)
; ==============================================================================
    org INTRO_VRAM
intro_text
    ins 'gen/intro_text.bin'

; ==============================================================================
; INTRO DISPLAY LIST SEGMENT ($2A00)
; 12 lines in ANTIC mode 2 with 8 empty scanlines between each line:
; 3 x DL_BLANK8 + 12 x (8 + 8) + 3 x DL_BLANK8 = 232 scanlines (PAL screen is 240,
; so the text block stays vertically centred with 8 scanlines of slack at the bottom)
; ==============================================================================
    org INTRO_DLIST
dlist_intro
    .byte DL_BLANK8
    .byte DL_BLANK8
    .byte DL_BLANK8

    ; Line 1 with LMS
    .byte DL_MODE_2 | DL_LMS
    .word INTRO_VRAM
    .byte DL_BLANK8

    ; Line 2
    .byte DL_MODE_2
    .byte DL_BLANK8

    ; Line 3
    .byte DL_MODE_2
    .byte DL_BLANK8

    ; Line 4
    .byte DL_MODE_2
    .byte DL_BLANK8

    ; Line 5
    .byte DL_MODE_2
    .byte DL_BLANK8

    ; Line 6
    .byte DL_MODE_2
    .byte DL_BLANK8

    ; Line 7
    .byte DL_MODE_2
    .byte DL_BLANK8

    ; Line 8
    .byte DL_MODE_2
    .byte DL_BLANK8

    ; Line 9
    .byte DL_MODE_2
    .byte DL_BLANK8

    ; Line 10
    .byte DL_MODE_2
    .byte DL_BLANK8

    ; Line 11
    .byte DL_MODE_2
    .byte DL_BLANK8

    ; Line 12
    .byte DL_MODE_2

    .byte DL_BLANK8
    .byte DL_BLANK8
    .byte DL_BLANK8

    ; Jump and wait for vertical blank
    .byte DL_JVB
    .word dlist_intro

; ==============================================================================
; TILESET METADATA, STATUS LINE & SFX ENGINE ($2A30)
; ==============================================================================
    org TILES_META
    icl 'gen/tiles_data.asm'
    icl 'gen/player_sprites.asm'
    icl 'engine/status_line.asm'
    icl 'engine/sfx_victory.asm'
    icl 'engine/sfx_secret.asm'

; ==============================================================================
; GAME PLAYFIELD VRAM SEGMENT ($3000)
; ANTIC Mode D ($0D, 160x96 2bpp, 2 scanlines/line, 40 bytes/line * 96 lines = 3,840 bytes)
; 4 KB aligned: strictly within $3000-$3FFF (never crosses 4 KB boundary)
; ==============================================================================
    org GAME_VRAM
game_vram_buf
    :GAME_VRAM_SIZE .byte 0

; ==============================================================================
; GAME DISPLAY LIST SEGMENT ($3F00)
; 96 lines of ANTIC Mode D ($0D) with top/bottom blank margins (~107 bytes: $3F00-$3F6A)
; 1 KB aligned: strictly within $3C00-$3FFF (never crosses 1 KB boundary)
; ==============================================================================
    org GAME_DLIST
dlist_game
    .byte DL_BLANK8
    .byte DL_BLANK8
    .byte DL_BLANK8

    ; Line 0 with LMS (starts at $3000, 3840 bytes -> ends at $3EFF, never wraps)
    .byte DL_MODE_D | DL_LMS
    .word GAME_VRAM
    :5 .byte DL_MODE_D          ; Lines 1-5
    .byte DL_MODE_D | DL_DLI    ; Line 6 (DLI 1: setup Pas 0 at line 8)
    :15 .byte DL_MODE_D         ; Lines 7-21
    .byte DL_MODE_D | DL_DLI    ; Line 22 (DLI 2: setup Pas 1 at line 24)
    :15 .byte DL_MODE_D         ; Lines 23-37
    .byte DL_MODE_D | DL_DLI    ; Line 38 (DLI 3: setup Pas 2 at line 40)
    :15 .byte DL_MODE_D         ; Lines 39-53
    .byte DL_MODE_D | DL_DLI    ; Line 54 (DLI 4: setup Pas 3 at line 56)
    :15 .byte DL_MODE_D         ; Lines 55-69
    .byte DL_MODE_D | DL_DLI    ; Line 70 (DLI 5: setup Pas 4 at line 72)
    :15 .byte DL_MODE_D         ; Lines 71-85
    .byte DL_MODE_D | DL_DLI    ; Line 86 (DLI 6: setup Pas 5 at line 88)
    :9 .byte DL_MODE_D          ; Lines 87-95

    ; Bottom spacing & Status Line (ANTIC Mode 2, 40 columns)
    .byte DL_BLANK8 | DL_DLI    ; 8 blank scanlines; DLI 7 triggers on line 7
    .byte DL_MODE_2 | DL_LMS    ; 1 line ANTIC Mode 2 (8 scanlines)
    .word status_line_vram
    .byte DL_BLANK8             ; 8 blank scanlines bottom margin

    ; Jump and wait for vertical blank
    .byte DL_JVB
    .word dlist_game

; ==============================================================================
; SCENE TITLE CARD DISPLAY LIST
; 1 line of ANTIC Mode 2 (8 scanlines) centered in 192 scanlines:
; 92 blank scanlines (11x8 + 1x4), 1 line ANTIC 2 with LMS (8 scanlines),
; 92 blank scanlines (11x8 + 1x4), and JVB.
; Strictly within $3F00-$3FFF (never crosses 1 KB boundary)
; ==============================================================================
dlist_scene_title
    :11 .byte DL_BLANK8
    .byte DL_BLANK4

    .byte DL_MODE_2 | DL_LMS
dlist_scene_title_addr
    .word 0

    :11 .byte DL_BLANK8
    .byte DL_BLANK4

    .byte DL_JVB
    .word dlist_scene_title

; ==============================================================================
; STATUS LINE VRAM (40 bytes, ANTIC Mode 2)
; Strictly within $3F00-$3FFF (never crosses 4 KB boundary)
; ==============================================================================
status_line_vram
    :40 .byte 0

; ==============================================================================
; TITLE VERTICAL SCROLLER DATA SEGMENT ($4000)
; 120-byte ANTIC Mode 2 vertical scroll buffer ($4000-$4077: 3x 40B L0, L1, L2)
; and centered text lines ($4078-...).
; Strictly within $4000-$4FFF (never crosses 4 KB boundary)
; ==============================================================================
    org TITLE_VRAM
title_vs_buf
    :TITLE_VS_BUF_LEN .byte 0

; Compiled vertical scroll text lines (internal screen codes, 40 bytes each)
    icl 'gen/title_vscroll_data.asm'

; Title screen state handler & 2bpp text generator
    icl 'scenes/title.asm'

; Player 0 Hero Engine & Intro Music Data (residing in $4000 block)
    icl 'engine/player.asm'
    icl 'gen/intro_music.asm'

; ==============================================================================
; SCENE RUNTIME ENGINE SEGMENT ($5000)
; Scene runtime code (secrets + sprite channel dispatch, enemies, SFX). The
; per-scene DLI blocks (241 B/scene) moved to the SCENE SoA TABLES segment
; ($B300), because they grow with the scene count exactly like the SoA tables
; and this block has to stay inside $5000-$5BFF (the Game Over module uses
; $5C00-$5F09 and the Title display list starts at $6000).
; ==============================================================================
    org SCENES_DATA
    icl 'engine/secrets.asm'
    icl 'engine/secrets_channel.asm'
    icl 'engine/enemies.asm'
    icl 'engine/sfx.asm'

; ==============================================================================
; TITLE DISPLAY LIST SEGMENT ($6000)
; Procedural 2bpp Title Screen + 1 line ANTIC Mode 2 Scroller (Normal width, 40 bytes/line)
; Height:
;   - 24 blank scanlines top (3x DL_BLANK8)
;   - CALL: ANTIC Mode E, 8 lines (8 scanlines)
;   - 8 blank scanlines (1x DL_BLANK8)
;   - OF THE: ANTIC Mode D, 8 lines (16 scanlines)
;   - 8 blank scanlines (1x DL_BLANK8)
;   - WINTERMOON: ANTIC Mode D, 16 lines (32 scanlines, 8 rows duplicated via 16x LMS)
;   - 110 blank scanlines padding (13x DL_BLANK8 + 1x DL_BLANK6)
;   - 3 blank scanlines DLI prolog (2x DL_BLANK1 + 1x DL_BLANK1 with DLI)
; ==============================================================================
; PROCEDURAL TITLE SCREEN DISPLAY LIST ($6000)
; Structure:
;   - 24 blank scanlines top margin (3x DL_BLANK8, third has DL_DLI)
;   - 8 scanlines CALL in ANTIC Mode E with LMS
;   - 8 blank scanlines spacing with DL_DLI
;   - 16 scanlines OF THE in ANTIC Mode D with LMS
;   - 8 blank scanlines spacing with DL_DLI
;   - 32 scanlines WINTERMOON in ANTIC Mode D (8 rows x 2 lines each with LMS)
;   - 8 blank scanlines spacing with DL_DLI (sets logo colors)
;   - 64 scanlines ATARI LOGO in ANTIC Mode D (1 LMS + 31 successive Mode D lines)
;   - 8 blank scanlines margin (DL_BLANK8)
;   - 3 blank scanlines scroll prolog (3x DL_BLANK1, second has DL_DLI)
;   - 2 lines ANTIC Mode 2 vertical scroll window (1x DL_VSCROL + 1x buffer line without VSCROL = 9 scanlines)
;   - Tail: 12 blank scanlines (DL_BLANK1 + DL_BLANK8 + DL_BLANK3)
;   - JVB to dlist_title
; Total height = 24 + 8 + 8 + 16 + 8 + 32 + 8 + 64 + 8 + 3 + 9 + 12 = 200 scanlines
; Total bytes = 122 bytes (strictly within $6000-$6079, max $60FF)
; ==============================================================================
    org DLIST_ADDR
dlist_title
    ; Top margin: 24 scanlines
    .byte DL_BLANK8
    .byte DL_BLANK8
    ; DLI in blank line triggers on its last scanline immediately before CALL.
    ; No graphics are drawn during blank scanlines, making color changes invisible
    ; without requiring WSYNC synchronization.
    .byte DL_BLANK8 | DL_DLI

    ; CALL: ANTIC Mode E (1 scanline/line * 8 lines = 8 scanlines)
    .byte DL_MODE_E | DL_LMS
    .word title_text_call
    :7 .byte DL_MODE_E

    ; Spacing: 8 scanlines (DLI triggers on last scanline before OF THE, no WSYNC needed)
    .byte DL_BLANK8 | DL_DLI

    ; OF THE: ANTIC Mode D (2 scanlines/line * 8 lines = 16 scanlines)
    .byte DL_MODE_D | DL_LMS
    .word title_text_of_the
    :7 .byte DL_MODE_D

    ; Spacing: 8 scanlines (DLI triggers on last scanline before WINTERMOON, no WSYNC needed)
    .byte DL_BLANK8 | DL_DLI

    ; WINTERMOON: ANTIC Mode D (2 scanlines/line * 16 lines = 32 scanlines)
    ; Each of the 8 source rows is displayed twice using explicit LMS
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 0
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 0
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 40
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 40
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 80
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 80
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 120
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 120
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 160
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 160
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 200
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 200
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 240
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 240
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 280
    .byte DL_MODE_D | DL_LMS
    .word title_text_wintermoon + 280

    ; Spacing: 8 scanlines (DLI triggers on last scanline before LOGO, no WSYNC needed)
    .byte DL_BLANK8 | DL_DLI

    ; ATARI LOGO: ANTIC Mode D (2 scanlines/line * 32 lines = 64 scanlines)
    ; 1 LMS instruction + 31 successive Mode D lines (ANTIC automatically advances address)
    .byte DL_MODE_D | DL_LMS
    .word title_text_logo
    :31 .byte DL_MODE_D

    ; Spacing margin between logo and scroll: 8 scanlines
    .byte DL_BLANK8

    ; DLI Prolog: 3 scanlines
    .byte DL_BLANK1
    .byte DL_BLANK1 | DL_DLI
    .byte DL_BLANK1

    ; ANTIC Mode 2 vertical scroll window (1 line with VSCROL + 1 buffer line without VSCROL = 9 scanlines)
title_dl_vs_lms
    .byte DL_MODE_2 | DL_LMS | DL_VSCROL
title_dl_vs_addr
    .word title_vs_buf
    .byte DL_MODE_2

    ; Tail (12 scanlines) copied directly from original display list
    .byte DL_BLANK1
    .byte DL_BLANK8
    .byte DL_BLANK3

    ; End of display list: Jump and wait for vertical blank
    .byte DL_JVB
    .word dlist_title

; ==============================================================================
; UNIFIED DLI ENGINE & DOUBLE BUFFERS SEGMENT ($6200)
; Strictly between Title DList ($60CA) and PMG ($6800)
; ==============================================================================
    org DLI_BUFFERS
    icl 'engine/dli.asm'

; ==============================================================================
; GAMEOVER SCENE MODULE ($5C00) — two display lists + DLI chain + screen builder
; Uses the free tail of the $5000 block (scene runtime ends at $5B94, title DL
; starts at $6000): the whole module fits in the 1 KB page $5C00-$5FFF, so the
; display lists can never cross a 1 KB boundary.
; ==============================================================================
    org GAMEOVER_CODE
    icl 'scenes/gameover.asm'

; ==============================================================================
; GAMEOVER TEXT SEGMENT ($BC00) — generated compact text data
; Kept out of the $5C00 page so the code + display lists stay under 1 KB (the
; display lists must not cross a 1 KB boundary). The scene SoA tables start at
; $B300 and grow with the scene count; they may use everything up to $BBFF.
; ==============================================================================
    org GAMEOVER_TEXT
    icl 'gen/gameover_texts.inc'

; The generated line count must match the display list size.
.if GAMEOVER_MAX_LINES != GAMEOVER_TEXT_LINES
    .error "gen/gameover_texts.inc allows a different line count than the display list"
.endif

; ==============================================================================
; RENDER LOOKUP TABLES SEGMENT ($6800)
; Reclaims $6800-$6AFF (768 B) unused by GTIA single-line PMG DMA (MEM-006)
; Page-aligned at $6800 for 0-cycle crossing overhead on flip_byte_2bpp
; ==============================================================================
    org RENDER_TABLES
    icl 'engine/render_tables.asm'

; ==============================================================================
; INTRO SCREEN HANDLER SEGMENT ($69C0)
; Relocated from the $2000 CODE block (which was down to 21 bytes of headroom)
; into the free PMG headroom between the render lookup tables ($69BF) and the active
; PMG buffer ($6B00). Single-line PMG DMA (PBASE=$68) only fetches $6B00-$6FFF,
; so this area is never overwritten by the player/missile graphics hardware.
; ==============================================================================
    org INTRO_CODE_ADDR
    icl 'scenes/intro.asm'

; ==============================================================================
; PLAYER-MISSILE GRAPHICS (PMG) ACTIVE MEMORY SEGMENT ($6B00)
; GTIA single-line resolution DMA (PMBASE=$68) only accesses $6B00-$6FFF (1,280 B):
; - Missiles: $6B00
; - Player 0: $6C00
; - Player 1: $6D00
; - Player 2: $6E00
; - Player 3: $6F00
; ==============================================================================
    org PMG_MISSILES
pmg_memory
    :PMG_ACTIVE_SIZE .byte 0

; ==============================================================================
; AUDIO SYSTEM SEGMENT ($7000)
; Isolated from VRAM ($4000) and Display List ($6000)
; ==============================================================================
    org AUDIO_ADDR
    icl 'lib/audio.asm'
    icl 'gen/title_music.asm'

; ==============================================================================
; RENDER CODE & SPRITES DATA SEGMENT ($7A00)
; Playfield blitter engine and sprite bitmaps (room expanded before $8000)
; ==============================================================================
    org RENDER_CODE
    icl 'engine/render.asm'
    icl 'gen/sprites_data.asm'

; ==============================================================================
; EARLY INIT VECTOR: Disable BASIC ROM so $A000-$BFFF RAM is writable by loader
; ==============================================================================
init_disable_basic
    sei
    lda PORTB
    ora #$02            ; Bit 1 = 1: disable BASIC ROM
    sta PORTB
    cli
    rts

    ini init_disable_basic

; ==============================================================================
; TILES GRAPHICS DATA SEGMENT ($8000)
; Mode E 2bpp bitmapped sheets (sizes are generated by scripts/convert_tiles.py):
; - castles: 1,936 bytes ($8000-$8790)
; - depths:  6,480 bytes ($8790-$9CDF)
; - hell:    2,736 bytes ($9CE0-$A78F)
; - trees:   1,680 bytes ($A790-$B21F)
; Total: 12,832 bytes ($8000-$B21F) -> strictly below the Scene SoA Tables at $B300
; ==============================================================================
    org TILES_ADDR
tiles_castles_data
    ins 'gen/tiles_castles.bin'
tiles_depths_data
    ins 'gen/tiles_depths.bin'
tiles_hell_data
    ins 'gen/tiles_hell.bin'
tiles_trees_data
    ins 'gen/tiles_trees.bin'
tiles_data_end

; ==============================================================================
; SCENE DATA TABLES SEGMENT ($B300, above the tilesets)
; Scene definitions, platforms, objects, every pointer table the engine indexes
; (`scene_elem_*_lo/hi`, `scene_secret_*`, ...) and the per-scene DLI blocks
; (241 B/scene). Placed in the RAM freed by the smaller tilesets so the scene
; count can grow (7 scenes planned) without competing for the $5000 block
; (runtime code) or the $6000 title DL.
; Budget: $B300-$BFFF = 3,328 bytes; keep the tilesets below $B300.
; ==============================================================================
    org SCENE_TABLES
    icl 'gen/scenes_data.asm'
    icl 'gen/scenes_dli_data.asm'
scene_tables_end

; ==============================================================================
; XEX DOS RUN VECTOR
; ==============================================================================
    org RUNAD
    .word start
