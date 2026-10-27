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
PLAYER_VISIBLE_DEATH_Y = 68     ; Height of player on lowest platform (plat_y=88, y=88-20=68)
PLAYER_VISIBLE_DEATH_PMG_Y = 188 ; PMG scanline at lowest platform height: (68*2)+52 = 188
PLAYER_EMERGE_START_PMG_Y = 224 ; Emergence start: top of sprite at scanline 224 (fully below visible playfield)

; --- Player Inertia & Speed Constants ---
PLAYER_MAX_SPEED    = $80       ; Maximum speed: 128/256 = 0.5 pixels/frame
PLAYER_ACCEL        = $10       ; Acceleration: 16/256 = 0.0625 px/frame^2 (reaches max speed in 8 frames)
PLAYER_DECEL        = $10       ; Deceleration: 16/256 = 0.0625 px/frame^2 (stops in 8 frames)

; --- Player Jump Constants & Profile Lengths ---
JUMP_UP_LEN         = 30        ; Vertical jump: 30 steps (11 ascent, 1 apex, 18 descent at 1 px/frame, net dy=0, dx=0)
JUMP_SHORT_LEN      = 18        ; Short jump: 18 steps, apex 10 lines, net dy=0, dx=18 px
JUMP_LONG_LEN       = 22        ; Long jump: 22 steps, apex 18 lines (higher platform at -16), dx=8 px

; ==============================================================================
; JUMP TRAJECTORY TABLES
; ==============================================================================
; 1. Vertical Jump Trajectory (apex 18 lines, 30 steps: 11 ascent, 1 apex, 18 descent at 1 px/frame)
jump_up_dy
    .byte -2, -2, -2, -2        ; Steps 0..3: fast ascent (up 8)
    .byte -2, -2, -2            ; Steps 4..6: mid ascent (up 6 -> up 14)
    .byte -1, -1, -1, -1        ; Steps 7..10: apex approach (up 4 -> peak 18 lines)
    .byte  0                    ; Step 11: apex (peak 18 lines)
    :18 .byte 1                 ; Steps 12..29: descent at 1 px/frame (down 18 lines -> net 0)

jump_up_anim
    .byte 0, 0, 0, 0, 0, 0, 0, 0; Steps 0..7: Frame 0 (fast ascent)
    .byte 1, 1, 1, 1            ; Steps 8..11: Frame 1 (apex)
    :18 .byte 0                 ; Steps 12..29: Fall animation frame 0

jump_up_dx
    :30 .byte 0

; 2. Long Jump Trajectory (apex 18 lines, 22 steps, dx=8 px)
jump_long_dy
    .byte -2, -2, -2, -2        ; Steps 0..3: fast ascent (up 8)
    .byte -2, -2, -2            ; Steps 4..6: mid ascent (up 6 -> up 14)
    .byte -1, -1, -1, -1        ; Steps 7..10: apex approach (up 4 -> peak 18 lines)
    .byte  0                    ; Step 11: apex (peak 18 lines)
    .byte  1,  1,  1            ; Steps 12..14: initial descent (down 3)
    .byte  2,  2,  2,  2,  2,  2,  3 ; Steps 15..21: fast descent (down 15 -> net 0)

jump_long_anim
    .byte 0, 0, 0, 0, 0, 0, 0, 0; Steps 0..7: Frame 0 (fast ascent)
    .byte 1, 1, 1, 1, 1, 1      ; Steps 8..13: Frame 1 (apex & landing)
    .byte 2, 2, 2, 2, 2, 2, 2, 2; Steps 14..21: Frame 2 (fast descent)

; 2. Short Jump (JUMP_TYPE_SHORT = 1): across ~16px gap
jump_short_dy
    .byte -2, -2, -2, -1, -1    ; Steps 0..4: fast ascent (up 8)
    .byte -1, -1,  0,  0,  0,  1,  1 ; Steps 5..11: apex (up 2 -> peak 10; down 2)
    .byte  1,  1,  1,  1,  2,  2 ; Steps 12..17: fast descent (down 8 -> net 0)

jump_short_dx
    :18 .byte 1                 ; 1 px/step * 18 steps = 18 px horizontal

jump_short_anim
    .byte 0, 0, 0, 0, 0         ; Frame 0 (fast ascent)
    .byte 1, 1, 1, 1, 1, 1, 1   ; Frame 1 (apex & transition)
    .byte 2, 2, 2, 2, 2, 2      ; Frame 2 (fast descent)

; 3. Long Jump Horizontal Trajectory (max 8px horizontal)
jump_long_dx
    .byte 1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1 ; Steps 0..10: 8 px horizontal
    :11 .byte 0                           ; Steps 11..21: 0 px (landed or falling)

; Directional frame tables for jump animations
player_jump_anim_table_lo
    .byte <player_anim_jump_right_frames, <player_anim_jump_left_frames

player_jump_anim_table_hi
    .byte >player_anim_jump_right_frames, >player_anim_jump_left_frames

player_jump_start_y .byte 0


; ==============================================================================
; PLAYER_INIT
; Initializes Hero Player 0 spawn position, direction, hardware registers and PMG.
; Input: A = active_scene_id (0..SCENE_COUNT-1)
; ==============================================================================
.proc player_init
    cmp #SCENE_COUNT
    bcc @valid_id
    rts

@valid_id
    sta active_scene_id
    pha
    jsr platforms_init
    pla
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

    ; 2. Initialize movement state: Facing right, standing idle, zeroed registers
    lda #0
    sta player_prev_pmg_y
    sta player_dir              ; PLAYER_DIR_RIGHT = 0
    sta player_state            ; PLAYER_STATE_IDLE = 0
    sta player_frame_idx
    sta player_x_sub
    sta player_speed
    sta player_jump_type
    sta player_jump_step
    sta player_jump_len
    sta player_fire_released
    sta player_prev_y
    sta player_jump_start_y
    sta player_killer_timer
    sta SIZEP0                  ; Normal width 1x (8 color clocks)
    lda #PLAYER_FRAME_DUR
    sta player_frame_timer

    ; 3. Setup GTIA hardware registers for Player 0 from active scene data
    lda scene_player_color,x
    sta player_color
    sta COLPM0
    sta PCOLR0

    ; 4. Set horizontal position HPOSP0 = 48 + player_x
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    ; 5. Setup platform pointer tables in Zero Page for active scene (X = active_scene_id)
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

    ; 6. Clear entire PMG Player 0 buffer ($6C00-$6CFF, 256 bytes)
    lda #0
    tax
@clr_p0
    sta PMG_PLAYER0,x
    inx
    bne @clr_p0

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
    ; 8. Silence any playing sound effects and render initial frame
    jsr sfx_stop_all
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
    cmp #PLAYER_STATE_DEATH
    bne @not_death_sprite

    ; Death animation: player_anim_death_frames
    lda #<player_anim_death_frames
    sta zp_ptr_src
    lda #>player_anim_death_frames
    sta zp_ptr_src+1
    jmp @resolve_frame

@not_death_sprite
    cmp #PLAYER_STATE_EMERGE
    beq @use_fall_sprite
    cmp #PLAYER_STATE_FALL
    bne @not_fall_sprite

@use_fall_sprite
    ; Fall animation: player_anim_fall_frames
    lda #<player_anim_fall_frames
    sta zp_ptr_src
    lda #>player_anim_fall_frames
    sta zp_ptr_src+1
    jmp @resolve_frame

@not_fall_sprite
    cmp #PLAYER_STATE_JUMP
    bne @not_jump_sprite

    ; Check if vertical jump is in descent phase (use fall animation)
    lda player_jump_type
    bne @normal_jump_sprite     ; Not JUMP_TYPE_UP -> normal directional jump sprite
    ldx player_jump_step
    cpx #13                     ; Post-incremented step: step >= 13 is descent phase (steps 12..29)
    bcc @normal_jump_sprite

    ; Vertical jump descent: use fall animation!
    lda #<player_anim_fall_frames
    sta zp_ptr_src
    lda #>player_anim_fall_frames
    sta zp_ptr_src+1
    jmp @resolve_frame

@normal_jump_sprite
    ; Jump animation: select jump-left or jump-right based on player_dir
    ldy player_dir
    lda player_jump_anim_table_lo,y
    sta zp_ptr_src
    lda player_jump_anim_table_hi,y
    sta zp_ptr_src+1
    jmp @resolve_frame

@not_jump_sprite
    ; Select animation frame table based on player_dir
    ldy player_dir
    lda player_anim_table_lo,y
    sta zp_ptr_src
    lda player_anim_table_hi,y
    sta zp_ptr_src+1

@resolve_frame

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
    ; Update Killer mode countdown and color pulsation
    lda player_killer_timer
    beq @no_killer_timer
    dec player_killer_timer
    bne @killer_modulate
    ; Killer mode just expired: restore base scene player color
    lda player_color
    sta COLPM0
    sta PCOLR0
    jmp @no_killer_timer

@killer_modulate
    ; Modulate luminance: shift timer right by 1 to step every 2 frames
    lda player_killer_timer
    lsr
    and #$0E
    sta zp_temp_a
    lda player_color
    and #$F0
    ora zp_temp_a
    sta COLPM0
    sta PCOLR0

@no_killer_timer
    ; 0a. If currently emerging from bottom edge, run emergence update routine
    lda player_state
    cmp #PLAYER_STATE_EMERGE
    bne @not_emerging
    jmp player_emerge_update

@not_emerging
    ; 0b. If currently in death animation/hold, run death update routine
    cmp #PLAYER_STATE_DEATH
    bne @not_dying
    jmp player_death_update

@not_dying
    ; 1. If currently jumping, run jump update routine
    lda player_state
    cmp #PLAYER_STATE_JUMP
    bne @not_jumping
    jmp player_jump_update

@not_jumping
    ; 2. If currently falling, run falling update routine
    cmp #PLAYER_STATE_FALL
    bne @check_jump_fire
    jmp player_fall_update

@check_jump_fire
    ; 3. Check Fire button (STRIG0 = 0) for jump trigger
    lda STRIG0
    bne @fire_up

    ; Fire button is currently pressed (0)
    lda player_fire_released
    beq @no_jump_trigger    ; Not released since last press, do not re-trigger

    ; Fire was just pressed! Consume release flag:
    lda #0
    sta player_fire_released

    ; Only trigger jump if standing on a platform
    ldy player_plat_idx
    bmi @no_jump_trigger

    jsr player_initiate_jump
    lda player_state
    cmp #PLAYER_STATE_JUMP
    bne @no_jump_trigger
    jmp player_jump_update

@fire_up
    lda #1
    sta player_fire_released

@no_jump_trigger
@handle_movement
    ; 4. Poll Joystick 0
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
    bcc @check_footstep
    lda #0
    sta player_frame_idx

@check_footstep
    ; Trigger footstep sound when walking and stepping (frame 1 and frame 3)
    lda player_state
    cmp #PLAYER_STATE_WALK
    bne @finish_update
    lda player_frame_idx
    cmp #1
    beq @do_step_sfx
    cmp #3
    bne @finish_update
@do_step_sfx
    jsr sfx_play_step

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
    bcc @check_adjacent_platform

    ; Right edge check: mid_x >= plat_x + plat_w
    lda (zp_plat_ptr_x),y
    clc
    adc (zp_plat_ptr_w),y
    cmp zp_temp_a
    bcc @check_adjacent_platform
    beq @check_adjacent_platform
    jmp @no_edge_check

@check_adjacent_platform
    ; Save standing platform Y coordinate
    lda (zp_plat_ptr_y),y
    sta zp_temp_x

    ; Search all active scene platforms for one supporting mid_x at the same Y
    ldy zp_plat_count
    beq @walked_off_edge
    dey

@find_adj_loop
    lda (zp_plat_ptr_y),y
    cmp zp_temp_x
    bne @next_adj

    ; Check bounds: plat_x <= mid_x < plat_x + plat_w
    lda zp_temp_a           ; mid_x
    cmp (zp_plat_ptr_x),y
    bcc @next_adj

    lda (zp_plat_ptr_x),y
    clc
    adc (zp_plat_ptr_w),y
    cmp zp_temp_a
    bcc @next_adj
    beq @next_adj

    ; Seamless transition onto adjacent/overlapping platform!
    sty player_plat_idx
    jmp @no_edge_check

@next_adj
    dey
    bpl @find_adj_loop

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
; PLAYER_INITIATE_JUMP
; Evaluates STICK0 direction when Fire is pressed, sets jump type and initializes trajectory.
; Controls:
; - Fire + neutral joystick (or Up only) -> JUMP_TYPE_UP (pionowy)
; - Fire + Left or Right (without Up)    -> JUMP_TYPE_SHORT (w przód, ok. 16px)
; - Fire + Up+Left or Up+Right           -> JUMP_TYPE_LONG (w górę, max 8px w poziomie)
; ==============================================================================
.proc player_initiate_jump
    ; 1. Check if there is a platform directly overhead
    ; If an overhead platform is within 20 lines above the standing platform,
    ; Hero has insufficient headroom to jump -> block jump completely!
    ldy player_plat_idx
    bmi @can_jump           ; Not on platform -> skip

    lda (zp_plat_ptr_y),y
    sta zp_temp_a           ; zp_temp_a = floor_y

    ; Mid X = player_x + 4
    lda player_x
    clc
    adc #4
    sta zp_temp_y

    ldy zp_plat_count
    beq @can_jump
    dey

@overhead_loop
    ; Check X bounds: plat_x <= mid_x < plat_x + plat_w
    lda zp_temp_y
    cmp (zp_plat_ptr_x),y
    bcc @next_overhead

    lda (zp_plat_ptr_x),y
    clc
    adc (zp_plat_ptr_w),y
    cmp zp_temp_y
    bcc @next_overhead
    beq @next_overhead

    ; Mid X is within horizontal span of platform Y
    ; Check if platform Y is directly overhead:
    ; overhead_y < floor_y AND overhead_y + 20 >= floor_y
    lda (zp_plat_ptr_y),y
    cmp zp_temp_a           ; overhead_y < floor_y ?
    bcs @next_overhead      ; If >= floor_y, not above standing platform

    clc
    adc #20                 ; overhead_y + 20 >= floor_y ?
    cmp zp_temp_a
    bcc @next_overhead      ; If < floor_y, 2+ tiers above (plenty of clearance)

    ; Directly overhead platform detected! Block jump completely:
    rts

@next_overhead
    dey
    bpl @overhead_loop

@can_jump
    ; 2. Check horizontal joystick deflection (bits 2 and 3)
    ; STICK0 bits: bit 0 = Up, bit 1 = Down, bit 2 = Left, bit 3 = Right (0 = active)
    lda STICK0
    and #%00001100          ; Mask bits 2 and 3
    cmp #%00001100          ; Neither left nor right?
    beq @do_jump_up
    cmp #0                  ; Both left and right?
    beq @do_jump_up

    ; Left or Right is active! Determine horizontal direction
    cmp #%00001000          ; Bit 2 is 0 (Left active)?
    bne @dir_is_right

    lda #PLAYER_DIR_LEFT
    sta player_dir
    jmp @check_up_modifier

@dir_is_right
    lda #PLAYER_DIR_RIGHT
    sta player_dir

@check_up_modifier
    ; Check if Up is also active (bit 0 == 0)
    lda STICK0
    and #%00000001          ; Mask bit 0 (Up)
    beq @do_jump_long       ; Up is active -> Long Jump!

    ; Up is not active -> Short Jump!
    lda #JUMP_TYPE_SHORT
    sta player_jump_type
    lda #JUMP_SHORT_LEN
    sta player_jump_len
    jmp @setup_jump_state

@do_jump_long
    lda #JUMP_TYPE_LONG
    sta player_jump_type
    lda #JUMP_LONG_LEN
    sta player_jump_len
    jmp @setup_jump_state

@do_jump_up
    ; Vertical jump: keep current player_dir
    lda #JUMP_TYPE_UP
    sta player_jump_type
    lda #JUMP_UP_LEN
    sta player_jump_len

@setup_jump_state
    lda #PLAYER_STATE_JUMP
    sta player_state
    lda player_y
    sta player_jump_start_y
    lda #0
    sta player_jump_step
    sta player_speed
    sta player_x_sub
    sta player_frame_idx
    lda #$FF
    sta player_plat_idx     ; Airborne
    jsr sfx_play_jump
    rts
.endp

; ==============================================================================
; PLAYER_JUMP_UPDATE
; Advances jump trajectory by 1 step.
; Updates player_x and player_y according to active jump profile tables.
; Detects ceiling collisions during ascent (bounces and transitions to fall).
; Detects platform landings during descent (lands and transitions to idle).
; ==============================================================================
.proc player_jump_update
    ; 1. Check if jump steps completed
    ldx player_jump_step
    cpx player_jump_len
    bcc @step_in_bounds

    ; Jump trajectory completed without landing -> transition to fall
    lda #PLAYER_STATE_FALL
    sta player_state
    lda #$FF
    sta player_plat_idx
    lda #0
    sta player_speed
    sta player_x_sub
    sta player_frame_idx
    jmp player_fall_update

@step_in_bounds
    ; 2. Fetch dy, dx, and anim_frame from active profile table
    lda player_jump_type
    beq @fetch_up
    cmp #JUMP_TYPE_SHORT
    beq @fetch_short

    ; JUMP_TYPE_LONG
    lda jump_long_dy,x
    sta zp_temp_a           ; signed dy
    lda jump_long_dx,x
    sta zp_temp_x           ; unsigned dx
    lda jump_long_anim,x
    sta player_frame_idx
    jmp @have_step_data

@fetch_up
    lda jump_up_dy,x
    sta zp_temp_a
    lda jump_up_dx,x
    sta zp_temp_x
    lda jump_up_anim,x
    sta player_frame_idx
    jmp @have_step_data

@fetch_short
    lda jump_short_dy,x
    sta zp_temp_a
    lda jump_short_dx,x
    sta zp_temp_x
    lda jump_short_anim,x
    sta player_frame_idx

@have_step_data
    ; Advance step counter for next frame
    inc player_jump_step

    ; 3. Apply horizontal movement (dx)
    lda zp_temp_x
    beq @no_h_motion

    lda player_dir
    bne @move_left

    ; Move right
    lda player_x
    clc
    adc zp_temp_x
    cmp #PLAYER_MAX_X
    bcc @x_right_ok
    lda #PLAYER_MAX_X
@x_right_ok
    sta player_x
    jmp @no_h_motion

@move_left
    lda player_x
    sec
    sbc zp_temp_x
    bcs @x_left_ok
    lda #0
@x_left_ok
    sta player_x

@no_h_motion
    ; 4. Apply vertical movement (dy)
    ; Save previous Y for collision checks
    lda player_y
    sta player_prev_y

    ; Add signed dy
    clc
    adc zp_temp_a
    ; Clamp to top boundary (min player_y = -24 = $E8, PMG scanline 4):
    ; In signed 8-bit, valid range is -24 ($E8..$FF) or 0..127 ($00..$7F).
    ; Values between $80 (-128) and $E7 (-25) are below -24 and clamped to $E8.
    cmp #$E8
    bcs @y_ok
    cmp #128
    bcc @y_ok
    lda #$E8
@y_ok
    sta player_y

    ; Recalculate PMG scanline: player_pmg_y = (player_y << 1) + 52
    asl
    clc
    adc #52
    sta player_pmg_y

    ; 5. Collision checks
    lda zp_temp_a
    bpl @check_descent

    ; --- ASCENT (dy < 0): CEILING COLLISION CHECK ---
    ; During JUMP_TYPE_LONG and JUMP_TYPE_UP, platforms 2+ tiers above (32px higher)
    ; must not artificially clip the jump trajectory:
    lda player_jump_type
    beq @render_jump        ; JUMP_TYPE_UP = 0
    cmp #JUMP_TYPE_LONG     ; JUMP_TYPE_LONG = 2
    beq @render_jump

    ; Hero's head is at player_y.
    ; Mid X = player_x + 4
    lda player_x
    clc
    adc #4
    sta zp_temp_y

    ldy zp_plat_count
    beq @render_jump
    dey

@ceil_loop
    ; Check X bounds: plat_x <= mid_x < plat_x + plat_w
    lda zp_temp_y
    cmp (zp_plat_ptr_x),y
    bcc @next_ceil

    lda (zp_plat_ptr_x),y
    clc
    adc (zp_plat_ptr_w),y
    cmp zp_temp_y
    bcc @next_ceil
    beq @next_ceil

    ; X is within bounds!
    ; Platforms 2+ tiers above (plat_y + 8 <= player_jump_start_y) have 32+ px clearance and are never ceilings
    lda (zp_plat_ptr_y),y
    clc
    adc #8
    cmp player_jump_start_y
    bcc @next_ceil
    beq @next_ceil

    ; Check if Hero's head bumped platform from below:
    ; 1. Hero's head reached or penetrated bottom of platform: player_y <= plat_y + 4
    lda (zp_plat_ptr_y),y
    clc
    adc #4
    cmp player_y            ; plat_y + 4 >= player_y ?
    bcc @next_ceil

    ; 2. Hero's feet are still below the platform (distinguishes hitting ceiling from landing on platform from above):
    ; player_feet_y > plat_y + 4  <=>  player_y + 16 > plat_y
    lda player_y
    clc
    adc #16
    cmp (zp_plat_ptr_y),y   ; player_y + 16 > plat_y ?
    bcc @next_ceil
    beq @next_ceil

    ; Hit ceiling! Bounce off and fall vertically down!
    lda #PLAYER_STATE_FALL
    sta player_state
    lda #$FF
    sta player_plat_idx
    lda #0
    sta player_speed
    sta player_x_sub
    sta player_frame_idx

    ; Snap head just below platform: plat_y + 4 (never push below player_prev_y)
    lda (zp_plat_ptr_y),y
    clc
    adc #4
    cmp player_prev_y
    bcc @snap_ok
    lda player_prev_y
@snap_ok
    sta player_y
    asl
    clc
    adc #52
    sta player_pmg_y
    jmp @do_render

@next_ceil
    dey
    bpl @ceil_loop
@render_jump
    jmp @do_render

@check_descent
    ; If dy == 0, skip landing check
    lda zp_temp_a
    beq @render_jump

    ; --- DESCENT (dy > 0): LANDING COLLISION CHECK ---
    ; Feet Y = player_y + 20
    ; Prev Feet Y = player_prev_y + 20
    lda player_prev_y
    clc
    adc #20
    sta zp_temp_x           ; prev_feet_y

    lda player_y
    clc
    adc #20
    sta zp_temp_a           ; current feet_y

    lda player_x
    clc
    adc #4
    sta zp_temp_y           ; mid X

    ldy zp_plat_count
    beq @render_jump
    dey

@land_loop
    ; Check X bounds: plat_x <= mid_x < plat_x + plat_w
    lda zp_temp_y
    cmp (zp_plat_ptr_x),y
    bcc @next_land

    lda (zp_plat_ptr_x),y
    clc
    adc (zp_plat_ptr_w),y
    cmp zp_temp_y
    bcc @next_land
    beq @next_land

    ; X is within bounds!
    ; Did feet cross or hit platform top (plat_y)?
    ; prev_feet_y <= plat_y AND feet_y >= plat_y
    lda (zp_plat_ptr_y),y   ; plat_y
    cmp zp_temp_x           ; plat_y >= prev_feet_y ?
    bcc @next_land

    lda zp_temp_a           ; feet_y
    cmp (zp_plat_ptr_y),y   ; feet_y >= plat_y ?
    bcc @next_land

    ; Landed on platform!
    sty player_plat_idx
    lda (zp_plat_ptr_y),y
    sec
    sbc #20
    sta player_y
    asl
    clc
    adc #52
    sta player_pmg_y

    lda #PLAYER_STATE_IDLE
    sta player_state
    lda #0
    sta player_speed
    sta player_x_sub
    sta player_frame_idx
    lda #PLAYER_FRAME_DUR
    sta player_frame_timer
    jmp @do_render

@next_land
    dey
    bpl @land_loop

@do_render
    ; 6. Update HPOSP0
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    ; 7. Render sprite frame into PMG
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
    bmi @do_render          ; Negative player_y ($80..$FF) is in upper sky, not dead!
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
; Initiates Hero death sequence:
; Sets player_state = PLAYER_STATE_DEATH, resets speed, decrements remaining lives,
; updates status line HUD, and renders initial death animation frame.
; ==============================================================================
.proc player_handle_death
    ; If already dying or emerging, ignore redundant triggers
    lda player_state
    cmp #PLAYER_STATE_DEATH
    bcs @ignore
    jmp @start_death
@ignore
    rts

@start_death
    ; 1. Decrement remaining lives (protect against underflow if already 0)
    lda player_lives
    beq @no_dec
    dec player_lives
@no_dec

    ; 2. Update hearts display on status line
    jsr status_line_refresh_lives

    ; 3. Stop all horizontal movement and reset Killer mode
    lda #0
    sta player_speed
    sta player_x_sub
    sta player_killer_timer
    lda player_color
    sta COLPM0
    sta PCOLR0

    ; 4. Check if hero died from falling below lowest platform
    lda player_y
    bmi @regular_death      ; Negative player_y ($80..$FF) is in upper sky
    cmp #PLAYER_VISIBLE_DEATH_Y + 1
    bcc @regular_death

    ; Hero fell below visible screen: initiate emergence sequence!
    ; Start at scanline 224 (fully hidden below status line edge, 0 scanlines visible)
    lda #PLAYER_EMERGE_START_PMG_Y
    sta player_pmg_y
    lda #PLAYER_STATE_EMERGE
    sta player_state
    lda #0
    sta player_frame_idx
    jsr player_render_frame
    rts

@regular_death
    ; In-place death (e.g. enemy collision on platform)
    lda #PLAYER_STATE_DEATH
    sta player_state
    lda #0
    sta player_frame_idx
    lda #PLAYER_ANIM_DEATH_DUR
    sta player_frame_timer

    ; Trigger death sound effect
    jsr sfx_play_death

    ; Render initial death frame
    jsr player_render_frame
    rts
.endp

; ==============================================================================
; PLAYER_EMERGE_UPDATE
; Called once per frame when player_state == PLAYER_STATE_EMERGE.
; Smoothly slides hero sprite upwards from below the bottom edge (scanline 224)
; to PLAYER_VISIBLE_DEATH_PMG_Y (scanline 188, lowest platform height) at 1 scanline / frame.
; Uses fall animation frame ("fall") during emergence.
; Once fully emerged, transitions to PLAYER_STATE_DEATH.
; ==============================================================================
.proc player_emerge_update
    ; 1. Move up by 1 scanline towards lowest platform height
    dec player_pmg_y

    ; 2. Check if reached target visible PMG Y (188)
    lda player_pmg_y
    cmp #PLAYER_VISIBLE_DEATH_PMG_Y
    beq @reached_target
    bcc @reached_target

    ; 3. Still emerging: update HPOSP0 and render fall frame
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    jsr player_render_frame
    rts

@reached_target
    ; Fully emerged: lock to target coordinates at lowest platform height
    lda #PLAYER_VISIBLE_DEATH_PMG_Y     ; 188
    sta player_pmg_y
    lda #PLAYER_VISIBLE_DEATH_Y         ; 68
    sta player_y

    ; Transition to death animation
    lda #PLAYER_STATE_DEATH
    sta player_state
    lda #0
    sta player_frame_idx
    lda #PLAYER_ANIM_DEATH_DUR          ; 10
    sta player_frame_timer

    ; Trigger death sound effect
    jsr sfx_play_death

    ; Update HPOSP0 and render first death frame
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    jsr player_render_frame
    rts
.endp

; ==============================================================================
; PLAYER_DEATH_UPDATE
; Called once per frame when player_state == PLAYER_STATE_DEATH.
; Advances death animation frames (0 -> 1 -> 2).
; Holds last frame (frame 2) for an additional 1 second (50 PAL frames, total 60 frames).
; Once hold expires, clears PMG Player 0 and either respawns or triggers Game Over.
; ==============================================================================
.proc player_death_update
    ; 1. Count down frame timer
    dec player_frame_timer
    bne @do_render

    ; Frame timer expired: advance frame sequence
    lda player_frame_idx
    cmp #0
    bne @check_frame_1

    ; Transition Frame 0 -> Frame 1
    lda #1
    sta player_frame_idx
    lda #PLAYER_ANIM_DEATH_DUR
    sta player_frame_timer
    jmp @do_render

@check_frame_1
    cmp #1
    bne @finish_death

    ; Transition Frame 1 -> Frame 2 (last frame, hold for 10 dur + 50 hold = 60 frames)
    lda #2
    sta player_frame_idx
    lda #PLAYER_ANIM_DEATH_HOLD
    sta player_frame_timer
    jmp @do_render

@finish_death
    ; 2. Death sequence complete: Clear entire PMG Player 0 buffer ($6C00-$6CFF)
    lda #0
    tax
@clr_pmg
    sta PMG_PLAYER0,x
    inx
    bne @clr_pmg
    sta player_prev_pmg_y
    sta HPOSP0
    sta GRAFP0

    ; 3. Check if any lives remain
    lda player_lives
    bne @respawn

    ; No lives left: Game Over with failure status!
    lda #GAME_FAILED
    sta game_result
    lda #STATE_OVER
    sta game_state
    rts

@respawn
    ; Respawn hero on current scene at initial position
    lda active_scene_id
    jsr player_init
    rts

@do_render
    ; Update HPOSP0 and render active death frame
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    jsr player_render_frame
    rts
.endp
