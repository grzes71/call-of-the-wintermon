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

    ; Ensure active_scene_id is within bounds (0..SCENE_COUNT-1)
    lda active_scene_id
    cmp #SCENE_COUNT
    bcc @scene_ok
    lda #0
    sta active_scene_id
@scene_ok

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

    ; Initialize enemies engine and render active scene enemies
    lda active_scene_id
    jsr enemies_init

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
    jsr enemies_update
    jsr secrets_check_player_collision
    jsr enemies_check_player_collision
    rts
.endp

; ==============================================================================
; SECRETS HARDWARE COLLISION & PROGRESSION ENGINE
; Checks GTIA Player 0 - Missile collisions (M0PL..M3PL), bounding boxes,
; erases collected secrets, handles stage unlocking, and scene progression.
; ==============================================================================
secret_coll_def .byte 0

.proc secrets_check_player_collision
    ; 1. Check GTIA hardware collision between Player 0 and any Missile (M0..M3)
    lda M0PL
    ora M1PL
    ora M2PL
    ora M3PL
    and #1
    beq @clear_hit

    ; 2. Iterate through all secrets of active scene
    ldx #0
@loop
    cpx secrets_count
    bcs @clear_hit

    ; Secret must be active and not yet collected
    lda secrets_active,x
    beq @next
    lda secrets_collected,x
    bne @next

    ; Check horizontal overlap: abs(player_x - secrets_x) < 8
    lda player_x
    sec
    sbc secrets_x,x
    bcs @x_pos
    eor #$FF
    clc
    adc #1
@x_pos
    cmp #8
    bcs @next

    ; Check vertical overlap:
    ; secrets_pmg_y + secrets_height > player_pmg_y
    lda secrets_pmg_y,x
    clc
    adc secrets_height,x
    sec
    sbc player_pmg_y
    beq @next
    bcc @next

    ; player_pmg_y + 20 > secrets_pmg_y
    lda player_pmg_y
    clc
    adc #20
    sec
    sbc secrets_pmg_y,x
    beq @next
    bcc @next

    ; Hero collided with Secret X! Collect it!
    jsr secret_collect
    jmp @clear_hit

@next
    inx
    jmp @loop

@clear_hit
    sta HITCLR
    rts
.endp

.proc secret_collect
    ; 1. Erase secret scanlines from PMG_MISSILES memory
    txa
    pha
    jsr clear_secret_rows
    pla
    tax

    ; 2. Mark this secret as collected and inactive
    lda #1
    sta secrets_collected,x
    lda #0
    sta secrets_active,x

    ; 3. Record def_id of collected secret
    lda secrets_def_id,x
    sta secret_coll_def

    ; 4. Check if any active secrets remain on the scene
    ldy #0
@chk_act
    cpy secrets_count
    bcs @stage_cleared
    lda secrets_active,y
    bne @done               ; At least one active secret remains in current stage
    iny
    jmp @chk_act

@stage_cleared
    ; All active secrets of this stage have been collected!
    ; Unlock dependent secrets where dep_id == secret_coll_def
    ldy #0
    lda #0
    sta zp_temp_x           ; Unlocked count
@unl_loop
    cpy secrets_count
    bcs @chk_unlocked
    lda secrets_collected,y
    bne @next_unl

    lda secrets_dep_id,y
    cmp secret_coll_def
    bne @next_unl

    ; Match! Activate dependent secret and render initial Frame 0
    lda #1
    sta secrets_active,y
    lda secrets_frame_dur,y
    sta secrets_timer,y
    lda #0
    sta secrets_frame_idx,y

    tya
    pha
    tax
    jsr render_secret_frame
    pla
    tay

    inc zp_temp_x

@next_unl
    iny
    jmp @unl_loop

@chk_unlocked
    lda zp_temp_x
    bne @done               ; Newly unlocked stage is now active on screen!

    ; No dependent secrets unlocked. Check if ALL scene secrets are collected!
    ldy #0
@chk_all
    cpy secrets_count
    bcs @all_cleared
    lda secrets_collected,y
    beq @done               ; Uncollected secret remains
    iny
    jmp @chk_all

@all_cleared
    ; All secrets on level collected: proceed to next scene!
    jsr game_next_scene

@done
    rts
.endp

.proc game_next_scene
    inc active_scene_id
    lda active_scene_id
    cmp #SCENE_COUNT
    bcc @load_next

    ; Completed all scenes: GAME_SUCCESS!
    lda #GAME_SUCCESS
    sta game_result
    lda #STATE_OVER
    sta game_state
    rts

@load_next
    ; Initialize next scene (preserves lives & CD count)
    jsr game_init
    rts
.endp
