; ==============================================================================
; SCENES/GAME.ASM — Main Gameplay State Handler
; Target: Atari 800XL / 65XE (MOS 6502)
; ==============================================================================

; --- Game Sub-Phases ---
GAME_PHASE_TITLE_IN   = 0   ; Title card fade in (8 steps of 3 frames = 24 frames ~0.48s)
GAME_PHASE_TITLE_HOLD = 1   ; Title card hold (100 frames = 2.0s at 50 Hz PAL)
GAME_PHASE_TITLE_OUT  = 2   ; Title card fade out (8 steps of 3 frames = 24 frames ~0.48s)
GAME_PHASE_PLAYING    = 3   ; Active gameplay playfield (ANTIC Mode D)
GAME_PHASE_VICTORY    = 4   ; Level complete: victory fanfare plays in the finished
                            ; scene, game_next_scene runs only after it has finished

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

    ; 8. Initialize sound effects engine
    jsr sfx_init

    ; 9. Disable PMG latching and clear every player/missile horizontal position.
    ;    The title card phases run with PMG DMA off (SDMCTL = $22), so a still-enabled
    ;    GRACTL latch would make GTIA redraw the last latched hero scanline on every
    ;    scanline - a full-height vertical bar of garbage at the hero's x.
    ;    Gameplay restores GRACTL ($03) in @do_playing and HPOSP0/SIZEP0 through
    ;    dli_vblank_update, while the DLI re-stages the platform/enemy positions.
    lda #0
    sta GRACTL              ; $D01D: stop latching players and missiles
    ldx #7
@clr_pmg_pos
    sta HPOSP0,x            ; $D000-$D007: HPOSP0..3 followed by HPOSM0..3
    dex
    bpl @clr_pmg_pos

    ; 10. Initialize title card animation phase
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

    ; DLI VBLANK commit and secret animation run during gameplay and during the
    ; level-complete victory hold (the finished playfield stays on screen while the
    ; fanfare plays, and the DLI double buffer must keep being committed)
    lda game_phase
    cmp #GAME_PHASE_PLAYING
    beq @frame_updates
    cmp #GAME_PHASE_VICTORY
    bne @skip_dli_vblank
@frame_updates
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
    bne @chk_phase_victory
    jmp @do_title_out

@chk_phase_victory
    cmp #GAME_PHASE_VICTORY
    bne @chk_phase_playing
    jmp @do_victory

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
; PHASE 4: Level-Complete Victory Hold
; The finished playfield stays on screen while the victory fanfare plays; the next
; scene is loaded only after the whole fanfare has been played.
; ------------------------------------------------------------------------------
@do_victory
    jsr sfx_update
    jsr game_victory_update
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

    ; Advance dynamic moving platforms (motion, bounce, DLI HPOS, carrier)
    jsr platforms_update

    ; Update Hero Player 0 (joystick input, horizontal movement, animation & PMG render)
    jsr player_update
    jsr enemies_update
    jsr secrets_check_player_collision

    ; Collecting the last secret switches to the victory hold: stop this frame here so
    ; a same-frame enemy contact cannot kill the hero while the fanfare plays.
    lda game_phase
    cmp #GAME_PHASE_PLAYING
    bne @playing_done

    jsr enemies_check_player_collision
    jsr sfx_update
@playing_done
    rts
.endp

; ==============================================================================
; SECRETS HARDWARE COLLISION & PROGRESSION ENGINE
; Checks GTIA Player 0 - Missile collisions (M0PL..M3PL), bounding boxes,
; erases collected secrets, handles stage unlocking, and scene progression.
; ==============================================================================
secret_unl_count .byte 0
secret_coll_sfx  .byte 0         ; 1 = play the collect blip, 0 = suppressed (fanfare)
secret_coll_special .byte 0      ; 0 = normal secret, 1 = secret with "special": true
scene_victory_timer .byte 0     ; Frames left in the level-complete victory hold

.proc secrets_check_player_collision
    ; If hero is in death state, do not collect secrets
    lda player_state
    cmp #PLAYER_STATE_DEATH
    bcs @clear_hit

    ; 1. Check GTIA hardware collision between Player 0 and any sprite that can carry a secret:
    ;    Missiles M0..M3 (5th player channel) and Players P1..P3 (player channels). Enemies also
    ;    live on P1..P3, so a hit here only gates the precise overlap test below (which filters
    ;    out every sprite that is not a secret at the hero's position).
    lda M0PL
    ora M1PL
    ora M2PL
    ora M3PL
    ora P1PL
    ora P2PL
    ora P3PL
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
    ; 1. Erase secret scanlines from PMG_MISSILES memory and move offscreen
    txa
    pha
    jsr clear_secret_rows
    jsr clear_secret_hpos
    pla
    tax

    ; 2. Mark this secret as collected and inactive
    lda #1
    sta secrets_collected,x
    lda #0
    sta secrets_active,x

    ; 3. Arm the collect blip: secrets with "special": true use a different sound,
    ;    and the blip is suppressed later if this secret finishes the whole scene
    ;    (that path plays the victory fanfare instead - see @all_cleared).
    lda secrets_special,x
    sta secret_coll_special
    cmp #0
    beq @no_special_icon

    ; 3b. Special secrets also get a permanent HUD icon (one disc glyph per secret,
    ;     filled from the right). The counter survives scene changes - only a new
    ;     game (status_line_reset) clears it.
    jsr status_line_add_special

@no_special_icon
    ; 3c. Secrets with "killer": true activate Killer mode for 5 seconds (250 frames)
    lda secrets_killer,x
    beq @no_killer
    lda #KILLER_MODE_DURATION
    sta player_killer_timer

@no_killer
    ; 3d. Secrets with "extra_life": true increment player lives by 1 (max STATUS_MAX_LIVES)
    lda secrets_extra_life,x
    beq @no_extra_life
    lda player_lives
    cmp #STATUS_MAX_LIVES
    bcs @max_lives_reached
    inc player_lives
@max_lives_reached
    jsr status_line_refresh_lives

@no_extra_life
    lda #1
    sta secret_coll_sfx

    ; 4. Check if any active required secrets remain on the scene
    ldy #0
@chk_act
    cpy secrets_count
    bcs @stage_cleared
    lda secrets_active,y
    beq @chk_act_next
    lda secrets_killer,y
    ora secrets_extra_life,y
    bne @chk_act_next
    jmp @done               ; Active required secret remains in current stage
@chk_act_next
    iny
    jmp @chk_act

@stage_cleared
    ; All active secrets of this stage have been collected!
    ; Unlock every secret whose dependency definition has been collected at all. A stage
    ; may mix definitions (e.g. keys + skulls), so the unlock must not depend on which of
    ; them happened to be collected last.
    ldy #0
    lda #0
    sta secret_unl_count    ; Unlocked count
@unl_loop
    cpy secrets_count
    bcs @chk_unlocked
    lda secrets_collected,y
    bne @next_unl

    lda secrets_active,y
    bne @next_unl           ; Already active on screen - do not re-unlock

    lda secrets_dep_id,y
    beq @next_unl           ; Root secret (no dependency) - never unlocked here

    ldx #0                  ; Scan the collected secrets for the required definition
@unl_scan
    cpx secrets_count
    bcs @next_unl           ; Dependency not collected yet -> stays inactive
    lda secrets_collected,x
    beq @unl_scan_next
    lda secrets_def_id,x
    cmp secrets_dep_id,y
    beq @unlock
@unl_scan_next
    inx
    jmp @unl_scan

@unlock
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
    jsr update_secret_hpos
    pla
    tay

    inc secret_unl_count

@next_unl
    iny
    jmp @unl_loop

@chk_unlocked
    lda secret_unl_count
    beq @chk_all_start
    jmp @done               ; Newly unlocked stage is now active on screen!

    ; No dependent secrets unlocked. Check if ALL required scene secrets are collected!
@chk_all_start
    ldy #0
@chk_all
    cpy secrets_count
    bcs @all_cleared
    lda secrets_killer,y
    ora secrets_extra_life,y
    bne @chk_all_next       ; Optional secrets (killer / extra life) are not required
    lda secrets_collected,y
    beq @chk_all_done       ; Required uncollected secret remains
@chk_all_next
    iny
    jmp @chk_all
@chk_all_done
    jmp @done

@all_cleared
    ; All secrets on level collected: play the victory fanfare IN this scene and only
    ; then advance. game_phase = GAME_PHASE_VICTORY makes game_run count the fanfare
    ; down through game_victory_update before game_next_scene is called.
    ; The collect blip is dropped for this one secret - the fanfare replaces it.
    lda #0
    sta secret_coll_sfx
    lda #SFX_VICTORY_DURATION
    sta scene_victory_timer
    jsr sfx_play_victory
    lda #GAME_PHASE_VICTORY
    sta game_phase

@done
    ; Collect blip: normal or special variant, skipped for the scene-finishing secret.
    lda secret_coll_sfx
    beq @no_collect_blip
    lda secret_coll_special
    jsr sfx_play_secret_collect
@no_collect_blip
    rts
.endp

; ==============================================================================
; GAME_VICTORY_UPDATE
; Counts down the level-complete victory hold and advances to the next scene (or to
; GAME_SUCCESS on the final scene) only after the whole fanfare has been played.
; Called once per frame while game_phase == GAME_PHASE_VICTORY.
; ==============================================================================
.proc game_victory_update
    dec scene_victory_timer
    bne @hold
    jsr game_next_scene
@hold
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
