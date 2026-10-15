; ==============================================================================
; MAIN.ASM — Atari 8-bit State Machine & Game Engine Entry Point
; Target: Atari 800XL / 65XE (64 KB RAM)
; Mode: ANTIC Mode F (Title) / ANTIC Mode 2 (Intro)
; Audio: Atari POKEY Music (4-channel relocatable player)
; ==============================================================================

    icl 'hardware.asm'
    icl 'zeropage.asm'

; --- Memory Map Equates ---
CODE_ADDR   = $2000
FONT_ADDR   = $2400     ; 1 KB aligned font (1024 bytes: $2400-$27FF)
INTRO_VRAM  = $2800     ; Intro text VRAM (400 bytes: $2800-$298F)
INTRO_DLIST = $2A00     ; Intro display list (~30 bytes: $2A00-$2A1D)
TILES_META  = $2A30     ; Tileset SoA metadata & row offset tables (~494 bytes: $2A30-$2C1D)
SCENES_DATA = $2C30     ; Scene definitions, platforms & objects SoA tables (~832 bytes: $2C30-$2F6F)
GAME_VRAM   = $3000     ; Playfield VRAM: ANTIC Mode D ($0D) 160x96 2bpp (3,840 bytes: $3000-$3EFF, 4 KB aligned)
GAME_DLIST  = $3F00     ; Gameplay Display List (~107 bytes: $3F00-$3F6A, 1 KB aligned)
VRAM_SEG1   = $4000     ; Title VRAM Segment 1
VRAM_SEG2   = $5000     ; Title VRAM Segment 2
DLIST_ADDR  = $6000     ; Title Display List
PMG_ADDR    = $6800     ; Player-Missile Graphics: 2 KB aligned (2,048 bytes: $6800-$6FFF)
AUDIO_ADDR    = $7000     ; Audio Player & Music Buffers
RENDER_TABLES = $7A00     ; Render Lookup Tables: Flip byte (256 B) + Playfield row offsets (192 B)
TILES_ADDR    = $8000     ; ANTIC Mode E Tileset Bitmaps (16,237 bytes: $8000-$BF6C)

; --- Gameplay Buffer Equates ---
GAME_VRAM_SIZE  = 3840  ; 40 bytes/line * 96 lines
GAME_VRAM_LINES = 96
GAME_VRAM_PITCH = 40

; --- PMG Equates (2 KB Single-Line Resolution at $6800, PMBASE=$68) ---
PMG_SIZE        = 2048
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
; SCENE MODULES
; ==============================================================================
    icl 'scenes/title.asm'
    icl 'scenes/intro.asm'
    icl 'scenes/game.asm'
    icl 'scenes/gameover.asm'

; ==============================================================================
; INTRO FONT SEGMENT ($2400) - 1024 bytes (1 KB boundary aligned)
; ==============================================================================
    org FONT_ADDR
intro_font
    ins 'fonts/font.fnt'

; ==============================================================================
; INTRO TEXT VRAM SEGMENT ($2800) - 400 bytes (10 lines x 40 bytes)
; ==============================================================================
    org INTRO_VRAM
intro_text
    ins 'gen/intro_text.bin'

; ==============================================================================
; INTRO DISPLAY LIST SEGMENT ($2A00)
; 10 lines in ANTIC mode 2 with 8 empty scanlines between each line
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
    .byte DL_BLANK8
    .byte DL_BLANK8

    ; Jump and wait for vertical blank
    .byte DL_JVB
    .word dlist_intro

; ==============================================================================
; TILESET METADATA & ROW OFFSET TABLES ($2A30)
; ==============================================================================
    org TILES_META
    icl 'gen/tiles_data.asm'

; ==============================================================================
; SCENE DEFINITIONS & OBJECT TABLES ($2C30)
; ==============================================================================
    org SCENES_DATA
    icl 'gen/scenes_data.asm'

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
    :95 .byte DL_MODE_D

    .byte DL_BLANK8
    .byte DL_BLANK8
    .byte DL_BLANK8

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
; TITLE GRAPHICS DATA SEGMENT ($4000)
; Segment 1: $4000..$4FEF (4080 bytes) + 16 bytes pad -> $5000
; Segment 2: $5000..$5E0F (3600 bytes)
; Total: 7696 bytes
; ==============================================================================
    org VRAM_SEG1
    ins 'gen/title.bin'

; ==============================================================================
; TITLE DISPLAY LIST SEGMENT ($6000)
; ==============================================================================
    org DLIST_ADDR
dlist_title
    .byte DL_BLANK8
    .byte DL_BLANK8
    .byte DL_BLANK8

    ; Segment 1: scanlines 0..101 (102 scanlines)
    .byte DL_MODE_F | DL_LMS
    .word VRAM_SEG1
    :101 .byte DL_MODE_F

    ; Segment 2: scanlines 102..191 (90 scanlines)
    .byte DL_MODE_F | DL_LMS
    .word VRAM_SEG2
    :89 .byte DL_MODE_F

    ; End of display list: Jump and wait for vertical blank
    .byte DL_JVB
    .word dlist_title

; ==============================================================================
; PLAYER-MISSILE GRAPHICS (PMG) MEMORY SEGMENT ($6800)
; 2 KB boundary aligned ($6800-$6FFF, 2,048 bytes, PMBASE=$68)
; Supports single-line resolution (full 2 KB) and double-line resolution (1 KB)
; - Missiles: $6B00
; - Player 0: $6C00
; - Player 1: $6D00
; - Player 2: $6E00
; - Player 3: $6F00
; ==============================================================================
    org PMG_ADDR
pmg_memory
    :PMG_SIZE .byte 0

; ==============================================================================
; AUDIO SYSTEM SEGMENT ($7000)
; Isolated from VRAM ($4000) and Display List ($6000)
; ==============================================================================
    org AUDIO_ADDR
    icl 'lib/audio.asm'
    icl 'gen/title_music.asm'

; ==============================================================================
; RENDER LOOKUP TABLES SEGMENT ($7A00)
; ==============================================================================
    org RENDER_TABLES
    icl 'engine/render_tables.asm'
    icl 'engine/render.asm'

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
; Mode E 2bpp bitmapped sheets:
; - castles: 2,992 bytes ($8000-$8BAF)
; - depths:  6,480 bytes ($8BB0-$A4FF)
; - hell:    4,161 bytes ($A500-$B540)
; - trees:   2,604 bytes ($B541-$BF6C)
; Total: 16,237 bytes ($8000-$BF6C) -> strictly <= $BFFF
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
; XEX DOS RUN VECTOR
; ==============================================================================
    org RUNAD
    .word start
