; ==============================================================================
; ENGINE/PLAYER.ASM — Hero (Player 0) State Machine, Physics & PMG Renderer
; Target: Atari 800XL / 65XE (MOS 6502)
; Hardware: Atari GTIA Player 0 (HPOSP0, SIZEP0, COLPM0) + PMG_PLAYER0 ($6C00)
; ==============================================================================

; --- Player Direction Equates ---
PLAYER_DIR_RIGHT    = 0
PLAYER_DIR_LEFT     = 1


; --- Player Geometry & Movement Constants (Canvas 160x96) ---
PLAYER_MIN_X        = 0
PLAYER_MAX_X        = 152       ; 160 - 8 (player width)
PLAYER_HPOS_OFFSET  = 48        ; Normal playfield starts at HPOS 48 ($30)
PLAYER_DEFAULT_COLOR = $98      ; Royal cyan/blue default for Player 0 (COLPM0 / PCOLR0)
PLAYER_FALL_SPEED   = 1         ; 1 canvas line per frame
PLAYER_DEATH_Y      = 94        ; Death threshold: entire frame past bottom of status line (y=94 -> pmg_y=240)

; --- Player Inertia & Speed Constants ---
PLAYER_MAX_SPEED    = $80       ; Maximum speed: 128/256 = 0.5 pixels/frame
PLAYER_ACCEL        = $10       ; Acceleration: 16/256 = 0.0625 px/frame^2 (reaches max speed in 8 frames)
PLAYER_DECEL        = $10       ; Deceleration: 16/256 = 0.0625 px/frame^2 (stops in 8 frames)

; ==============================================================================
; PLAYER_INIT
; Initializes Hero Player 0 spawn position, direction, hardware registers and PMG.
; Input: A = active_scene_id (0..SCENE_COUNT-1)
; ==============================================================================
.proc player_init
    tax

    ; 1. Set initial canvas coordinates from scene data
    lda scene_player_start_x,x
    sta player_x

    lda scene_player_start_y,x
    sta player_y

    ; PMG scanline: player_pmg_y = (player_start_y << 1) + 52
    ; Maps editor player start Y (e.g. 68) to PMG single-line scanline (e.g. 188)
    asl
    clc
    adc #52
    sta player_pmg_y
    lda #0
    sta player_prev_pmg_y

    ; 2. Initialize movement state: Facing right, standing idle
    lda #PLAYER_DIR_RIGHT
    sta player_dir
    lda #PLAYER_STATE_IDLE
    sta player_state
    lda #0
    sta player_frame_idx
    sta player_x_sub
    sta player_speed
    lda #PLAYER_FRAME_DUR
    sta player_frame_timer

    ; 3. Setup GTIA hardware registers for Player 0 from active scene data
    lda scene_player_color,x
    sta player_color
    sta COLPM0
    sta PCOLR0

    lda #0                  ; Normal width 1x (8 color clocks)
    sta SIZEP0

    ; 4. Set horizontal position HPOSP0 = 48 + player_x
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    ; 5. Clear entire PMG Player 0 buffer ($6C00-$6CFF, 256 bytes)
    lda #0
    tax
@clr_p0
    sta PMG_PLAYER0,x
    inx
    bne @clr_p0

    ; 6. Setup platform pointer tables in Zero Page for active scene
    lda scene_plat_count,x
    sta zp_plat_count

    lda scene_plat_x_lo,x
    sta zp_plat_ptr_x
    lda scene_plat_x_hi,x
    sta zp_plat_ptr_x+1

    lda scene_plat_y_lo,x
    sta zp_plat_ptr_y
    lda scene_plat_y_hi,x
    sta zp_plat_ptr_y+1

    lda scene_plat_w_lo,x
    sta zp_plat_ptr_w
    lda scene_plat_w_hi,x
    sta zp_plat_ptr_w+1

    ; 7. Locate initial standing platform index
    ; Feet Y = player_y + 20
    lda player_y
    clc
    adc #20
    sta zp_temp_a           ; feet Y

    ; Mid X = player_x + 4
    lda player_x
    clc
    adc #4
    sta zp_temp_y           ; mid X

    lda #$FF
    sta player_plat_idx

    ldy zp_plat_count
    beq @no_start_plat
    dey
@find_plat_loop
    lda (zp_plat_ptr_y),y
    cmp zp_temp_a
    bne @next_find_plat

    ; Check X bounds: plat_x <= mid_x < plat_x + plat_w
    lda zp_temp_y
    cmp (zp_plat_ptr_x),y
    bcc @next_find_plat

    lda (zp_plat_ptr_x),y
    clc
    adc (zp_plat_ptr_w),y
    cmp zp_temp_y
    bcc @next_find_plat
    beq @next_find_plat

    ; Found matching platform!
    sty player_plat_idx
    jmp @found_plat

@next_find_plat
    dey
    bpl @find_plat_loop

@no_start_plat
    lda #PLAYER_STATE_FALL
    sta player_state

@found_plat
    ; 8. Render initial standing frame into PMG_PLAYER0
    jsr player_render_frame
    rts
.endp

; ==============================================================================
; PLAYER_RENDER_FRAME
; Copies the active animation frame (20 bytes) into PMG_PLAYER0 memory.
; Erases previous sprite scanlines, clips at scanline 244 (never visible on status line).
; Uses: player_dir, player_frame_idx, player_state, player_pmg_y, player_prev_pmg_y.
; ==============================================================================
.proc player_render_frame
    ; 1. Clear previous sprite scanlines (< 224) from PMG_PLAYER0
    lda player_prev_pmg_y
    beq @skip_clear
    ldy #PLAYER_SPRITE_HEIGHT - 1
@clr_loop
    tya
    clc
    adc player_prev_pmg_y
    bcs @skip_clr_line      ; If carry set (>= 256), wrapped around -> skip!
    cmp #224
    bcs @skip_clr_line      ; If >= 224 (status line area) -> skip!
    tax
    lda #0
    sta PMG_PLAYER0,x
@skip_clr_line
    dey
    bpl @clr_loop
@skip_clear

    ; 2. Select animation frame source pointer
    lda player_state
    cmp #PLAYER_STATE_FALL
    bne @not_fall_sprite

    ; Fall animation: single frame player_anim_fall_frame_0
    lda #<player_anim_fall_frame_0
    sta zp_ptr_src
    lda #>player_anim_fall_frame_0
    sta zp_ptr_src+1
    jmp @do_draw

@not_fall_sprite
    ; Select animation frame table based on player_dir
    ldy player_dir
    lda player_anim_table_lo,y
    sta zp_ptr_src
    lda player_anim_table_hi,y
    sta zp_ptr_src+1

    ; Resolve frame address from .word pointer array
    lda player_frame_idx
    asl
    tay
    lda (zp_ptr_src),y
    sta zp_temp_a           ; Frame addr low
    iny
    lda (zp_ptr_src),y
    sta zp_temp_x           ; Frame addr high

    lda zp_temp_a
    sta zp_ptr_src
    lda zp_temp_x
    sta zp_ptr_src+1

@do_draw
    ; 3. Save current player_pmg_y for next frame's clear
    lda player_pmg_y
    sta player_prev_pmg_y

    ; 4. Copy PLAYER_SPRITE_HEIGHT scanlines (clipping: only lines < 224)
    ldy #PLAYER_SPRITE_HEIGHT - 1
@draw_loop
    tya
    clc
    adc player_pmg_y
    bcs @skip_draw_line     ; If carry set (>= 256), wrapped around -> skip!
    cmp #224
    bcs @skip_draw_line     ; If >= 224 (status line area) -> skip!
    tax
    lda (zp_ptr_src),y
    sta PMG_PLAYER0,x
@skip_draw_line
    dey
    bpl @draw_loop

    rts
.endp

; ==============================================================================
; PLAYER_UPDATE
; Called once per frame during active gameplay (GAME_PHASE_PLAYING).
; Reads joystick STICK0, simulates inertia (acceleration, deceleration, braking),
; integrates sub-pixel motion, updates animation frames, checks for platform edges,
; and updates PMG buffer.
; ==============================================================================
.proc player_update
    ; If currently falling, run falling update routine
    lda player_state
    cmp #PLAYER_STATE_FALL
    bne @handle_movement
    jmp player_fall_update

@handle_movement
    ; 1. Poll Joystick 0
    ; STICK0 bits: bit 2 = Left (0 = active), bit 3 = Right (0 = active)
    lda STICK0
    and #%00001100          ; Mask bits 2 and 3
    cmp #%00001100          ; Neither left nor right pressed?
    beq @stick_idle
    cmp #%00000000          ; Both left and right pressed?
    beq @stick_idle

    cmp #%00001000          ; Bit 2 is 0 (Left active)?
    beq @stick_left

    ; Otherwise Bit 3 is 0 (Right active)
    jmp @stick_right

@stick_idle
    ; Coast to stop: apply friction deceleration
    lda player_speed
    bne @do_decel
    jmp @apply_motion       ; Already stopped
@do_decel
    sec
    sbc #PLAYER_DECEL
    bcs @decel_ok
    lda #0
@decel_ok
    sta player_speed
    jmp @apply_motion

@stick_left
    ; If currently moving right with speed > 0, brake first
    lda player_dir
    bne @stick_left_accel   ; Already facing left
    lda player_speed
    beq @stick_left_accel   ; Speed is 0, start left motion immediately

    ; Active turnaround braking while moving right
    sec
    lda player_speed
    sbc #PLAYER_ACCEL
    bcs @still_braking_right
    lda #0
@still_braking_right
    sta player_speed
    beq @braked_to_stop_right
    jmp @apply_motion       ; Still coasting right
@braked_to_stop_right
    lda #PLAYER_DIR_LEFT    ; Speed reached 0: reverse direction to left
    sta player_dir
    jmp @apply_motion

@stick_left_accel
    lda #PLAYER_DIR_LEFT
    sta player_dir
    lda player_x
    beq @at_left_wall       ; Cannot accelerate left if already at left boundary

    clc
    lda player_speed
    adc #PLAYER_ACCEL
    cmp #PLAYER_MAX_SPEED
    bcc @speed_left_ok
    lda #PLAYER_MAX_SPEED
@speed_left_ok
    sta player_speed
    jmp @apply_motion

@at_left_wall
    lda #0
    sta player_speed
    sta player_x_sub
    jmp @apply_motion

@stick_right
    ; If currently moving left with speed > 0, brake first
    lda player_dir
    beq @stick_right_accel  ; Already facing right
    lda player_speed
    beq @stick_right_accel  ; Speed is 0, start right motion immediately

    ; Active turnaround braking while moving left
    sec
    lda player_speed
    sbc #PLAYER_ACCEL
    bcs @still_braking_left
    lda #0
@still_braking_left
    sta player_speed
    beq @braked_to_stop_left
    jmp @apply_motion       ; Still coasting left
@braked_to_stop_left
    lda #PLAYER_DIR_RIGHT   ; Speed reached 0: reverse direction to right
    sta player_dir
    jmp @apply_motion

@stick_right_accel
    lda #PLAYER_DIR_RIGHT
    sta player_dir
    lda player_x
    cmp #PLAYER_MAX_X
    bcs @at_right_wall      ; Cannot accelerate right if already at right boundary

    clc
    lda player_speed
    adc #PLAYER_ACCEL
    cmp #PLAYER_MAX_SPEED
    bcc @speed_right_ok
    lda #PLAYER_MAX_SPEED
@speed_right_ok
    sta player_speed
    jmp @apply_motion

@at_right_wall
    lda #0
    sta player_speed
    sta player_x_sub
    jmp @apply_motion

@apply_motion
    ; 2. Determine state (IDLE or WALK) based on current speed
    lda player_speed
    bne @is_moving

    ; Speed == 0: transition to IDLE state
    lda #PLAYER_STATE_IDLE
    sta player_state
    lda #0
    sta player_frame_idx
    sta player_x_sub
    lda #PLAYER_FRAME_DUR
    sta player_frame_timer
    jmp @finish_update

@is_moving
    lda #PLAYER_STATE_WALK
    sta player_state

    ; 3. Integrate sub-pixel position: player_x_sub += player_speed
    clc
    lda player_x_sub
    adc player_speed
    sta player_x_sub
    bcc @tick_anim          ; No integer pixel step on this frame

    ; Step 1 pixel in player_dir
    lda player_dir
    bne @step_left

@step_right
    lda player_x
    cmp #PLAYER_MAX_X
    bcs @clamp_right
    inc player_x
    jmp @tick_anim
@clamp_right
    lda #0
    sta player_speed
    sta player_x_sub
    jmp @tick_anim

@step_left
    lda player_x
    beq @clamp_left
    dec player_x
    jmp @tick_anim
@clamp_left
    lda #0
    sta player_speed
    sta player_x_sub

@tick_anim
    ; 4. Advance animation timer
    dec player_frame_timer
    bne @finish_update

    ; Timer expired: reset timer and advance frame index
    lda #PLAYER_FRAME_DUR
    sta player_frame_timer

    inc player_frame_idx
    lda player_frame_idx
    cmp #PLAYER_FRAME_COUNT
    bcc @finish_update
    lda #0
    sta player_frame_idx

@finish_update
    ; 5. Check if Hero walked > 50% past the edge of the standing platform
    ldy player_plat_idx
    bmi @no_edge_check       ; If negative ($FF), not on a platform

    ; Mid X = player_x + 4
    lda player_x
    clc
    adc #4
    sta zp_temp_a

    ; Left edge check: mid_x < plat_x
    cmp (zp_plat_ptr_x),y
    bcc @walked_off_edge

    ; Right edge check: mid_x >= plat_x + plat_w
    lda (zp_plat_ptr_x),y
    clc
    adc (zp_plat_ptr_w),y
    cmp zp_temp_a
    bcc @walked_off_edge
    beq @walked_off_edge
    jmp @no_edge_check

@walked_off_edge
    lda #PLAYER_STATE_FALL
    sta player_state
    lda #$FF
    sta player_plat_idx
    lda #0
    sta player_speed
    sta player_x_sub
    sta player_frame_idx

@no_edge_check
    ; 6. Update hardware horizontal position: HPOSP0 = 48 + player_x
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    ; 7. Re-render current frame into PMG buffer
    jsr player_render_frame
    rts
.endp

; ==============================================================================
; PLAYER_FALL_UPDATE
; Called once per frame when player_state == PLAYER_STATE_FALL.
; Drops player downwards at 1 canvas line / frame, updates PMG Y, checks for
; landing on platforms below, clips PMG so sprite never renders on status line,
; and triggers hero death if player completely passes through the status line.
; ==============================================================================
.proc player_fall_update
    ; 1. Drop down by 1 canvas line
    inc player_y

    ; Recalculate PMG scanline: player_pmg_y = (player_y << 1) + 52
    lda player_y
    asl
    clc
    adc #52
    sta player_pmg_y

    ; 2. Check for landing on any platform below
    ; Feet Y = player_y + 20
    lda player_y
    clc
    adc #20
    sta zp_temp_a           ; feet Y

    ; Mid X = player_x + 4
    lda player_x
    clc
    adc #4
    sta zp_temp_y           ; mid X

    ldy zp_plat_count
    beq @check_death
    dey

@plat_loop
    lda (zp_plat_ptr_y),y
    cmp zp_temp_a
    bne @next_plat

    ; Check X bounds: plat_x <= mid_x < plat_x + plat_w
    lda zp_temp_y
    cmp (zp_plat_ptr_x),y
    bcc @next_plat

    lda (zp_plat_ptr_x),y
    clc
    adc (zp_plat_ptr_w),y
    cmp zp_temp_y
    bcc @next_plat
    beq @next_plat

    ; Landed on platform!
    sty player_plat_idx
    lda #PLAYER_STATE_IDLE
    sta player_state
    lda #0
    sta player_speed
    sta player_x_sub
    sta player_frame_idx
    lda #PLAYER_FRAME_DUR
    sta player_frame_timer
    jmp @do_render

@next_plat
    dey
    bpl @plat_loop

@check_death
    ; 3. If no platform landed on, check if fallen completely through status line
    lda player_y
    cmp #PLAYER_DEATH_Y
    bcc @do_render

    ; Fallen past status line -> Death!
    jsr player_handle_death
    rts

@do_render
    ; 4. Update HPOSP0
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    ; 5. Render fall frame (or idle frame if landed)
    jsr player_render_frame
    rts
.endp

; ==============================================================================
; PLAYER_HANDLE_DEATH
; Erases PMG Player 0 buffer, decrements lives, updates status line HUD.
; If lives remain (> 0), respawns hero at active scene start position.
; If no lives remain (= 0), sets game_result = GAME_FAILED and transitions to STATE_OVER.
; ==============================================================================
.proc player_handle_death
    ; 1. Clear entire PMG Player 0 buffer ($6C00-$6CFF, 256 bytes)
    lda #0
    tax
@clr_pmg
    sta PMG_PLAYER0,x
    inx
    bne @clr_pmg
    sta player_prev_pmg_y
    sta HPOSP0
    sta GRAFP0

    ; 2. Decrement remaining lives
    dec player_lives

    ; 3. Update hearts display on status line
    jsr status_line_refresh_lives

    ; 4. Check if any lives remain
    lda player_lives
    bne @respawn

    ; No lives left: Game Over with failure status!
    lda #GAME_FAILED
    sta game_result
    lda #STATE_OVER
    sta game_state
    rts

@respawn
    ; Respawn hero on current scene
    lda active_scene_id
    jsr player_init
    rts
.endp
