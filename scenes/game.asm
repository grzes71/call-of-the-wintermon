; ==============================================================================
; SCENES/GAME.ASM — Main Gameplay State Handler
; Target: Atari 800XL / 65XE (MOS 6502)
; ==============================================================================

; --- Game Sub-Phases ---
GAME_PHASE_TITLE_IN   = 0   ; Title card fade in (8 steps of 3 frames = 24 frames ~0.48s)
GAME_PHASE_TITLE_HOLD = 1   ; Title card hold (100 frames = 2.0s at 50 Hz PAL)
GAME_PHASE_TITLE_OUT  = 2   ; Title card fade out (8 steps of 3 frames = 24 frames ~0.48s)
GAME_PHASE_PLAYING    = 3   ; Active gameplay playfield (ANTIC Mode D)

; Fade table for scene title card (green hue $C, increasing luminance)
; 8 luminance steps: black -> faint green -> bright light green
scene_title_fade_colors
    .byte $00, $C2, $C4, $C6, $C8, $CA, $CC, $CE
SCENE_TITLE_FADE_STEPS = 8

.proc game_init
    ; 1. Turn off DMA during setup
    lda #0
    sta SDMCTL
    sta DMACTL

    ; 2. Set PMBASE (Player-Missile Graphics buffer page)
    lda #PMBASE_PAGE
    sta PMBASE

    ; 3. Pre-render scene background into GAME_VRAM ($3000)
    lda active_scene_id
    jsr render_scene_background

    ; Initialize DLI engine and stage initial scene DLI data
    jsr dli_init
    lda active_scene_id
    jsr dli_stage_scene

    ; Initialize secrets engine and render active scene secrets
    lda active_scene_id
    jsr secrets_init

    ; Initialize player engine (Player 0 Hero spawn and PMG)
    lda active_scene_id
    jsr player_init

    ; Initialize status line (lives hearts, scene name, collected CDs)
    lda player_lives
    bne @has_lives
    jsr status_line_reset
@has_lives
    lda active_scene_id
    jsr status_line_init

    ; 4. Set up Scene Title Card LMS operand in dlist_scene_title
    ldx active_scene_id
    lda scene_name_line_lo,x
    sta dlist_scene_title_addr
    lda scene_name_line_hi,x
    sta dlist_scene_title_addr+1

    ; 5. Set font pointer to intro_font ($24)
    lda >intro_font
    sta CHBAS
    sta CHBASE

    ; 6. Set initial title card colors: black background, black text (ready for fade-in)
    lda #0
    sta COLOR1
    sta COLPF1
    sta COLOR2
    sta COLPF2
    sta COLOR4
    sta COLBK

    ; 7. Point display list to dlist_scene_title
    lda <dlist_scene_title
    sta SDLSTL
    sta DLISTL
    lda >dlist_scene_title
    sta SDLSTH
    sta DLISTH

    ; 8. Initialize title card animation phase
    lda #GAME_PHASE_TITLE_IN
    sta game_phase
    lda #0
    sta scene_card_step
    sta scene_card_timer
    sta fire_released
    rts
.endp

.proc game_run
    ; Reset attract mode
    lda #0
    sta ATRACT

    ; Wait for VBLANK
    lda RTCLOK+2
@sync_vblank
    cmp RTCLOK+2
    beq @sync_vblank

    ; If in active playing phase, perform DLI VBLANK update and secret animation
    lda game_phase
    cmp #GAME_PHASE_PLAYING
    bne @skip_dli_vblank
    jsr dli_vblank_update
    jsr secrets_update
@skip_dli_vblank

    ; Dispatch based on game_phase
    lda game_phase
    cmp #GAME_PHASE_TITLE_IN
    bne @chk_phase_hold
    jmp @do_title_in

@chk_phase_hold
    cmp #GAME_PHASE_TITLE_HOLD
    bne @chk_phase_out
    jmp @do_title_hold

@chk_phase_out
    cmp #GAME_PHASE_TITLE_OUT
    bne @chk_phase_playing
    jmp @do_title_out

@chk_phase_playing
    jmp @do_playing

; ------------------------------------------------------------------------------
; PHASE 0: Title Card Fade In (8 steps, 3 frames each = 24 frames ~0.48s)
; ------------------------------------------------------------------------------
@do_title_in
    lda #$22
    sta SDMCTL
    sta DMACTL

    ldx scene_card_step
    lda scene_title_fade_colors,x
    sta COLOR1
    sta COLPF1

    inc scene_card_timer
    lda scene_card_timer
    cmp #3
    bcc @done_in

    lda #0
    sta scene_card_timer
    inc scene_card_step
    lda scene_card_step
    cmp #SCENE_TITLE_FADE_STEPS
    bcc @done_in

    lda #GAME_PHASE_TITLE_HOLD
    sta game_phase
    lda #0
    sta scene_card_timer
@done_in
    rts

; ------------------------------------------------------------------------------
; PHASE 1: Title Card Hold (100 frames = 2.0s at 50 Hz PAL)
; ------------------------------------------------------------------------------
@do_title_hold
    lda #$22
    sta SDMCTL
    sta DMACTL

    lda scene_title_fade_colors + SCENE_TITLE_FADE_STEPS - 1
    sta COLOR1
    sta COLPF1

    ; Check skip conditions (debounced fire or keypress)
    lda STRIG0
    bne @fire_up
    lda fire_released
    bne @skip_to_fade_out
    jmp @advance_hold_timer
@fire_up
    lda #1
    sta fire_released
    lda CH
    cmp #$FF
    bne @skip_key
@advance_hold_timer
    inc scene_card_timer
    lda scene_card_timer
    cmp #100
    bcc @done_hold

    jmp @start_fade_out

@skip_key
    lda #$FF
    sta CH              ; Clear key buffer
@skip_to_fade_out
@start_fade_out
    lda #GAME_PHASE_TITLE_OUT
    sta game_phase
    lda #SCENE_TITLE_FADE_STEPS - 1
    sta scene_card_step
    lda #0
    sta scene_card_timer
@done_hold
    rts

; ------------------------------------------------------------------------------
; PHASE 2: Title Card Fade Out (8 steps, 3 frames each = 24 frames ~0.48s)
; ------------------------------------------------------------------------------
@do_title_out
    lda #$22
    sta SDMCTL
    sta DMACTL

    ldx scene_card_step
    lda scene_title_fade_colors,x
    sta COLOR1
    sta COLPF1

    inc scene_card_timer
    lda scene_card_timer
    cmp #3
    bcc @done_out

    lda #0
    sta scene_card_timer
    dec scene_card_step
    bpl @done_out

    ; Fade-out complete: switch to active gameplay with dlist_game!
    lda #0
    sta SDMCTL
    sta DMACTL
    sta COLOR1
    sta COLPF1

    ; Point display list to dlist_game
    lda <dlist_game
    sta SDLSTL
    sta DLISTL
    lda >dlist_game
    sta SDLSTH
    sta DLISTH

    ; Perform initial DLI VBLANK update for gameplay
    jsr dli_vblank_update

    ; Enable PMG single-line + players + missiles + normal playfield ($3E)
    lda #$3E
    sta SDMCTL
    sta DMACTL
    lda #$03
    sta GRACTL

    lda #GAME_PHASE_PLAYING
    sta game_phase
    lda #0
    sta fire_released
@done_out
    rts

; ------------------------------------------------------------------------------
; PHASE 3: Active Gameplay Loop
; ------------------------------------------------------------------------------
@do_playing
    lda #$3E
    sta SDMCTL
    sta DMACTL
    lda #$03
    sta GRACTL

    ; Update Hero Player 0 (joystick input, horizontal movement, animation & PMG render)
    jsr player_update
    rts
.endp
