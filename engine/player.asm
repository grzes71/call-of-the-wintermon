; ==============================================================================
; ENGINE/PLAYER.ASM — Hero (Player 0) State Machine, Physics & PMG Renderer
; Target: Atari 800XL / 65XE (MOS 6502)
; Hardware: Atari GTIA Player 0 (HPOSP0, SIZEP0, COLPM0) + PMG_PLAYER0 ($6C00)
; ==============================================================================

; --- Player Direction Equates ---
PLAYER_DIR_RIGHT    = 0
PLAYER_DIR_LEFT     = 1

; --- Player Movement State Equates ---
PLAYER_STATE_IDLE   = 0
PLAYER_STATE_WALK   = 1

; --- Player Geometry & Movement Constants (Canvas 160x96) ---
PLAYER_MIN_X        = 0
PLAYER_MAX_X        = 152       ; 160 - 8 (player width)
PLAYER_HPOS_OFFSET  = 48        ; Normal playfield starts at HPOS 48 ($30)
PLAYER_COLOR        = $98       ; Royal cyan/blue for Player 0 (COLPM0 / PCOLR0)

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

    ; PMG scanline: player_pmg_y = (player_start_y << 1) + 52
    ; Maps editor player start Y (e.g. 68) to PMG single-line scanline (e.g. 188)
    lda scene_player_start_y,x
    asl
    clc
    adc #52
    sta player_pmg_y

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

    ; 3. Setup GTIA hardware registers for Player 0
    lda #PLAYER_COLOR
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

    ; 6. Render initial standing frame into PMG_PLAYER0
    jsr player_render_frame
    rts
.endp

; ==============================================================================
; PLAYER_RENDER_FRAME
; Copies the active animation frame (20 bytes) into PMG_PLAYER0 memory.
; Uses: player_dir (0=right, 1=left), player_frame_idx (0..PLAYER_FRAME_COUNT-1),
;       player_pmg_y (scanline offset in PMG_PLAYER0).
; ==============================================================================
.proc player_render_frame
    ; 1. Select animation frame table based on player_dir
    ldy player_dir
    lda player_anim_table_lo,y
    sta zp_ptr_src
    lda player_anim_table_hi,y
    sta zp_ptr_src+1

    ; 2. Resolve frame address from .word pointer array
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

    ; 3. Set destination pointer = PMG_PLAYER0 + player_pmg_y
    lda #>PMG_PLAYER0
    sta zp_ptr_dst+1
    lda player_pmg_y
    sta zp_ptr_dst

    ; 4. Copy PLAYER_SPRITE_HEIGHT scanlines
    ldy #PLAYER_SPRITE_HEIGHT - 1
@copy_loop
    lda (zp_ptr_src),y
    sta (zp_ptr_dst),y
    dey
    bpl @copy_loop

    rts
.endp

; ==============================================================================
; PLAYER_UPDATE
; Called once per frame during active gameplay (GAME_PHASE_PLAYING).
; Reads joystick STICK0, simulates inertia (acceleration, deceleration, braking),
; integrates sub-pixel motion, updates animation frames, and updates PMG buffer.
; Max speed: 0.5 pixels/frame ($80 subpixels/frame).
; ==============================================================================
.proc player_update
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
    ; 5. Update hardware horizontal position: HPOSP0 = 48 + player_x
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    ; 6. Re-render current frame into PMG buffer
    jsr player_render_frame
    rts
.endp
