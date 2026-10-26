; ==============================================================================
; PLATFORMS.ASM — Dynamic Moving Platforms Engine & DLI Hardware Sync
; Target: Atari 800XL / 65XE (MOS 6502)
;
; Movement strategies (from scene JSONs / compile_scenes.py):
;   0: None (stationary platform)
;   1: Left - Right (moves left, bounces right at edge/collision, no pause)
;   2: Right - Left (moves right, bounces left at edge/collision, no pause)
;   3: Left - Pause - Right (moves left, bounces right, 50-frame pause at bounce)
;   4: Right - Pause - Left (moves right, bounces left, 50-frame pause at bounce)
;
; Collision rules:
;   - Screen edges: X <= 0 (bounce right) or X + Width >= 160 (bounce left).
;   - Inter-platform: Two platforms in the same pas (row) bounce upon touching.
;   - Player carrier: Hero standing on a moving platform is carried by dx.
; ==============================================================================

MAX_PLATFORMS = 24
PLAT_SPEED_SLOW   = 3   ; 1 pixel every 4 frames (12.5 px/s PAL)
PLAT_SPEED_MEDIUM = 1   ; 1 pixel every 2 frames (25 px/s PAL)
PLAT_SPEED_FAST   = 0   ; 1 pixel every 1 frame  (50 px/s PAL)
PLATFORM_PAUSE_FRAMES = 50  ; 50 frames = 1.0 second PAL

; --- Active Scene Platforms State (Structure-of-Arrays) ---
plat_count        .byte 0
plat_movement     :MAX_PLATFORMS .byte 0  ; 0..4
plat_dir          :MAX_PLATFORMS .byte 0  ; 0 = right, 1 = left
plat_speed        :MAX_PLATFORMS .byte 0  ; Frame reload count (3 = slow, 1 = medium, 0 = fast)
plat_speed_timer  :MAX_PLATFORMS .byte 0  ; Frame divider countdown
plat_pause_timer  :MAX_PLATFORMS .byte 0  ; 50-frame pause countdown
plat_pas          :MAX_PLATFORMS .byte 0  ; 0..5 (derived from y)
plat_hw_info      :MAX_PLATFORMS .byte 0  ; bit 7: type (0=sprite, 1=missile), bits 4..5: ch_start (0..3), bits 0..2: ch_count (1..4)

; Temporary variables for inter-platform collision checks
plat_check_j      .byte 0
plat_other_x      .byte 0
plat_other_w      .byte 0
plat_cur_w        .byte 0

; ==============================================================================
; PLATFORMS INIT
; Staging/initialization for the active scene.
; Restores initial X positions from scene_plat_init_x to scene_plat_x and
; copies movement attributes into runtime tables.
; Input: A = active_scene_id (0..SCENE_COUNT-1)
; ==============================================================================
.proc platforms_init
    cmp #SCENE_COUNT
    bcc @scene_ok
    lda #0
@scene_ok
    tax

    lda scene_plat_count,x
    sta plat_count
    bne @has_plats
    rts
@has_plats

    ; Setup Zero Page platform pointers
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

    ; 1. Restore platform X coordinates: scene_plat_init_x -> scene_plat_x
    lda scene_plat_init_x_lo,x
    sta zp_ptr_src
    lda scene_plat_init_x_hi,x
    sta zp_ptr_src+1

    lda scene_plat_x_lo,x
    sta zp_ptr_dst
    lda scene_plat_x_hi,x
    sta zp_ptr_dst+1

    ldy plat_count
    dey
@cp_x
    lda (zp_ptr_src),y
    sta (zp_ptr_dst),y
    dey
    bpl @cp_x

    ; 2. Copy movement codes, derive initial dir and pas index
    lda scene_plat_movement_lo,x
    sta zp_ptr_src
    lda scene_plat_movement_hi,x
    sta zp_ptr_src+1
    ldy plat_count
    dey
@cp_mv
    lda (zp_ptr_src),y
    sta plat_movement,y
    and #1                      ; 1 & 3 start left (1), 2 & 4 start right (0)
    sta plat_dir,y

    ; Derive pas index = (y - 8) >> 4
    lda (zp_plat_ptr_y),y
    sec
    sbc #8
    lsr
    lsr
    lsr
    lsr
    sta plat_pas,y

    dey
    bpl @cp_mv

    ; 3. Copy hardware channel info
    lda scene_plat_hw_info_lo,x
    sta zp_ptr_src
    lda scene_plat_hw_info_hi,x
    sta zp_ptr_src+1
    ldy plat_count
    dey
@cp_hw
    lda (zp_ptr_src),y
    sta plat_hw_info,y
    dey
    bpl @cp_hw

    ; 4. Copy platform speeds
    lda scene_plat_speed_lo,x
    sta zp_ptr_src
    lda scene_plat_speed_hi,x
    sta zp_ptr_src+1
    ldy plat_count
    dey
@cp_spd
    lda (zp_ptr_src),y
    sta plat_speed,y
    dey
    bpl @cp_spd

    ; 5. Reset runtime frame divider and pause timers
    ldy plat_count
    dey
@reset_timers
    lda #0
    sta plat_speed_timer,y
    sta plat_pause_timer,y
    dey
    bpl @reset_timers

@done
    rts
.endp

; ==============================================================================
; PLATFORMS UPDATE DLI HPOS
; Updates hardware horizontal position registers in DLI double buffers
; (both buffer 0 and buffer 1) for the platform at index X.
; Input: X = platform index (0..plat_count-1)
; Preserves: X
; ==============================================================================
.proc platforms_update_dli_hpos
    txa
    pha                         ; Push platform index X to stack

    ; Fetch platform X and calculate base HPOS = 48 + X
    tay
    lda (zp_plat_ptr_x),y
    clc
    adc #48
    sta zp_temp_a               ; zp_temp_a = base HPOS

    lda plat_hw_info,x
    bpl @do_sprite
    jmp @do_missile

@do_sprite
    ; --- SPRITE PLATFORM ---
    ; Segment 0
    lda plat_hw_info,x
    lsr
    lsr
    lsr
    lsr
    and #3
    tay                         ; channel (0=P1, 1=P2, 2=P3)
    lda plat_pas,x
    tax                         ; pas
    lda zp_temp_a
    jsr @write_sprite_ch

    pla
    pha
    tax

    lda plat_hw_info,x
    and #7
    cmp #2
    bcs @do_seg1
    jmp @dli_done

@do_seg1
    ; Segment 1 (width 48..64: offset +16 or +32)
    lda (zp_plat_ptr_w),y
    cmp #48
    bne @seg1_w24
    lda zp_temp_a
    clc
    adc #16
    jmp @write_seg1
@seg1_w24
    lda zp_temp_a
    clc
    adc #32
@write_seg1
    sta zp_temp_y
    lda plat_hw_info,x
    lsr
    lsr
    lsr
    lsr
    and #3
    clc
    adc #1
    tay                         ; channel
    lda plat_pas,x
    tax                         ; pas
    lda zp_temp_y
    jsr @write_sprite_ch

    pla
    pha
    tax

    lda plat_hw_info,x
    and #7
    cmp #3
    bcs @do_seg2
    jmp @dli_done

@do_seg2
    ; Segment 2 (width 96: offset +64)
    lda zp_temp_a
    clc
    adc #64
    sta zp_temp_y
    lda plat_hw_info,x
    lsr
    lsr
    lsr
    lsr
    and #3
    clc
    adc #2
    tay                         ; channel
    lda plat_pas,x
    tax                         ; pas
    lda zp_temp_y
    jsr @write_sprite_ch
    jmp @dli_done

@write_sprite_ch
    ; A = HPOS, X = pas (0..5), Y = channel (0=P1, 1=P2, 2=P3)
    cpy #0
    bne @chk_p2
    sta dli_hpos_p1,x
    sta dli_hpos_p1+8,x
    rts
@chk_p2
    cpy #1
    bne @chk_p3
    sta dli_hpos_p2,x
    sta dli_hpos_p2+8,x
    rts
@chk_p3
    sta dli_hpos_p3,x
    sta dli_hpos_p3+8,x
    rts

@do_missile
    lda plat_hw_info,x
    and #7
    cmp #4
    beq @m_quad

    ; Single missile (width 8)
    lda plat_hw_info,x
    lsr
    lsr
    lsr
    lsr
    and #3                      ; channel (0..3)
    tay
    lda plat_pas,x
    tax                         ; pas
    lda zp_temp_a
    cpy #0
    bne @m1
    sta dli_hpos_m0,x
    sta dli_hpos_m0+8,x
    jmp @dli_done
@m1
    cpy #1
    bne @m2
    sta dli_hpos_m1,x
    sta dli_hpos_m1+8,x
    jmp @dli_done
@m2
    cpy #2
    bne @m3
    sta dli_hpos_m2,x
    sta dli_hpos_m2+8,x
    jmp @dli_done
@m3
    cpy #3
    sta dli_hpos_m3,x
    sta dli_hpos_m3+8,x
    jmp @dli_done

@m_quad
    ; 4 missiles: M0..M3 at +0, +8, +16, +24
    ldy plat_pas,x
    lda zp_temp_a
    sta dli_hpos_m0,y
    sta dli_hpos_m0+8,y
    clc
    adc #8
    sta dli_hpos_m1,y
    sta dli_hpos_m1+8,y
    clc
    adc #8
    sta dli_hpos_m2,y
    sta dli_hpos_m2+8,y
    clc
    adc #8
    sta dli_hpos_m3,y
    sta dli_hpos_m3+8,y

@dli_done
    pla
    tax                         ; Restore platform index X
    rts
.endp

; ==============================================================================
; PLATFORMS UPDATE
; Advances platform motion, evaluates screen boundary & inter-platform bounces,
; updates GTIA/DLI double buffers, and moves Hero if standing on a moving platform.
; ==============================================================================
.proc platforms_update
    ldx #0
@plat_loop
    cpx plat_count
    bcc @continue_plat
    rts

@continue_plat
    ; 1. Check if platform has movement
    lda plat_movement,x
    bne @chk_pause
    jmp @next_plat

@chk_pause
    ; 2. Check pause timer
    lda plat_pause_timer,x
    beq @chk_speed
    dec plat_pause_timer,x
    jmp @next_plat          ; While paused, do not move

@chk_speed
    ; 3. Check speed timer
    lda plat_speed_timer,x
    beq @do_step
    dec plat_speed_timer,x
    jmp @next_plat

@do_step
    lda plat_speed,x
    sta plat_speed_timer,x

    ; 4. Perform movement step
    ; Old X is in (zp_plat_ptr_x),x
    txa
    tay
    lda (zp_plat_ptr_x),y
    sta zp_temp_x           ; zp_temp_x = old X

    ; Direction: 0 = right, 1 = left
    lda plat_dir,x
    bne @move_left

    ; --- MOVING RIGHT ---
    lda zp_temp_x
    clc
    adc #1
    sta zp_temp_a           ; candidate X

    ; Boundary check: candidate_x + width >= 160
    txa
    tay
    lda (zp_plat_ptr_w),y   ; width
    sta zp_temp_y
    clc
    adc zp_temp_a
    cmp #160
    bcc @check_inter_plat

    ; Hit right screen boundary!
    lda #160
    sec
    sbc zp_temp_y
    sta zp_temp_a
    lda #1
    sta plat_dir,x          ; Reverse direction to left
    lda plat_movement,x
    cmp #3                  ; Pause strategy? (3 = left_pause_right, 4 = right_pause_left)
    bcc @check_inter_plat
    lda #PLATFORM_PAUSE_FRAMES
    sta plat_pause_timer,x
    lda #0
    sta plat_speed_timer,x
    jmp @check_inter_plat

@move_left
    ; --- MOVING LEFT ---
    lda zp_temp_x
    beq @hit_left_boundary  ; Already at 0
    sec
    sbc #1
    sta zp_temp_a           ; candidate X
    bne @check_inter_plat   ; candidate_x > 0

@hit_left_boundary
    ; Hit left screen boundary (candidate reached 0)
    lda #0
    sta zp_temp_a
    sta plat_dir,x          ; Reverse direction to right
    lda plat_movement,x
    cmp #3                  ; Pause strategy?
    bcc @check_inter_plat
    lda #PLATFORM_PAUSE_FRAMES
    sta plat_pause_timer,x
    lda #0
    sta plat_speed_timer,x

@check_inter_plat
    ; 5. Inter-platform collision check in the same pas
    lda #0
    sta plat_check_j
@inter_loop
    ldy plat_check_j
    cpy plat_count
    bcc @check_this_j
    jmp @carry_hero_check

@check_this_j
    cpx plat_check_j        ; Skip comparison against self
    bne @check_pas_match
    jmp @next_inter_j

@check_pas_match
    ; Only check platforms in the same pas (row)
    lda plat_pas,y
    cmp plat_pas,x
    beq @do_inter_chk
    jmp @next_inter_j

@do_inter_chk
    ; Fetch platform j's current X and W
    lda (zp_plat_ptr_x),y
    sta plat_other_x
    lda (zp_plat_ptr_w),y
    sta plat_other_w

    ; Fetch platform X's width
    txa
    tay
    lda (zp_plat_ptr_w),y
    sta plat_cur_w
    ldy plat_check_j

    ; Case 1: Platform X is initially to the left of platform j
    lda zp_temp_x
    cmp plat_other_x
    bcs @chk_case_2

    ; Candidate right edge: candidate_x + cur_w >= other_x
    lda zp_temp_a
    clc
    adc plat_cur_w
    cmp plat_other_x
    bcs @do_collide_right
    jmp @next_inter_j       ; No overlap

@do_collide_right
    ; Collision detected on right!
    ; Rozklejenie: candidate_x = other_x - cur_w
    lda plat_other_x
    sec
    sbc plat_cur_w
    sta zp_temp_a

    ; Reverse current platform to left
    lda #1
    sta plat_dir,x
    lda plat_movement,x
    cmp #3
    bcc @bounce_j_right
    lda #PLATFORM_PAUSE_FRAMES
    sta plat_pause_timer,x
    lda #0
    sta plat_speed_timer,x

@bounce_j_right
    ; Reverse other platform to right if active
    lda plat_movement,y
    beq @jmp_next_j
    lda #0
    sta plat_dir,y
    lda plat_movement,y
    cmp #3
    bcc @jmp_next_j

    ; Set pause timer for other platform y
    ; If x < y, platform y hasn't executed yet this frame and will decrement, so set 51
    txa
    cmp plat_check_j
    bcc @y_is_later_r
    lda #PLATFORM_PAUSE_FRAMES
    jmp @store_pause_r
@y_is_later_r
    lda #PLATFORM_PAUSE_FRAMES+1
@store_pause_r
    sta plat_pause_timer,y
    lda #0
    sta plat_speed_timer,y
@jmp_next_j
    jmp @next_inter_j

@chk_case_2
    ; Case 2: Platform X is initially to the right of platform j
    ; Candidate left edge: candidate_x <= other_x + other_w
    lda plat_other_x
    clc
    adc plat_other_w
    cmp zp_temp_a
    bcs @do_collide_left
    jmp @next_inter_j       ; No overlap

@do_collide_left
    ; Collision detected on left!
    ; Rozklejenie: candidate_x = other_x + other_w
    lda plat_other_x
    clc
    adc plat_other_w
    sta zp_temp_a

    ; Reverse current platform to right
    lda #0
    sta plat_dir,x
    lda plat_movement,x
    cmp #3
    bcc @bounce_j_left
    lda #PLATFORM_PAUSE_FRAMES
    sta plat_pause_timer,x
    lda #0
    sta plat_speed_timer,x

@bounce_j_left
    ; Reverse other platform to left if active
    lda plat_movement,y
    beq @next_inter_j
    lda #1
    sta plat_dir,y
    lda plat_movement,y
    cmp #3
    bcc @next_inter_j

    ; Set pause timer for other platform y
    txa
    cmp plat_check_j
    bcc @y_is_later_l
    lda #PLATFORM_PAUSE_FRAMES
    jmp @store_pause_l
@y_is_later_l
    lda #PLATFORM_PAUSE_FRAMES+1
@store_pause_l
    sta plat_pause_timer,y
    lda #0
    sta plat_speed_timer,y

@next_inter_j
    inc plat_check_j
    jmp @inter_loop

@carry_hero_check
    ; 6. Hero carrier mechanics (evaluated BEFORE DLI HPOS update clobbers temp ZP)
    cpx player_plat_idx
    bne @commit_x

    ; Check if Hero is standing on this platform (IDLE or WALK)
    lda player_state
    cmp #PLAYER_STATE_IDLE
    beq @carry_hero
    cmp #PLAYER_STATE_WALK
    bne @commit_x

@carry_hero
    lda zp_temp_a           ; candidate_x
    cmp zp_temp_x           ; old_x
    beq @commit_x           ; No movement occurred

    bcs @carry_hero_right

    ; Moving left (candidate_x < old_x)
    lda player_x
    beq @commit_x           ; Hero blocked by left screen boundary
    sec
    sbc #1
    sta player_x
    clc
    adc #48
    sta HPOSP0
    jmp @commit_x

@carry_hero_right
    ; Moving right (candidate_x > old_x)
    lda player_x
    cmp #152
    bcs @commit_x           ; Hero blocked by right screen boundary
    clc
    adc #1
    sta player_x
    clc
    adc #48
    sta HPOSP0

@commit_x
    ; 7. Store updated X coordinate
    txa
    tay
    lda zp_temp_a
    sta (zp_plat_ptr_x),y

    ; 8. Update hardware DLI registers
    jsr platforms_update_dli_hpos

@next_plat
    inx
    jmp @plat_loop

@done
    rts
.endp
