; ==============================================================================
; ENEMIES.ASM — Enemy Movement, Animation & PMG Rendering Engine
; Target: Atari 800XL / 65XE (MOS 6502)
;
; Hardware allocation:
; - Up to 3 enemies per zone on Players 1..3 (HPOSP1..3, COLPM1..3)
; - Vertical scanlines mapped in PMG memory (PMG_PLAYER1..3)
; - Movement strategies:
;     0: Stationary
;     1: Left - Right (no pause)
;     2: Right - Left (no pause)
;     3: Left - Pause - Right (1 sec = 50 frames pause at boundary)
;     4: Right - Pause - Left (1 sec = 50 frames pause at boundary)
; - Speeds:
;     0: Slow   (1 pixel every 4 frames)
;     1: Medium (1 pixel every 2 frames)
;     2: Fast   (1 pixel every 1 frame)
; ==============================================================================

MAX_ENEMIES = 6

; --- Active Scene Enemies State (Structure-of-Arrays) ---
enemies_count        .byte 0
enemies_active       :MAX_ENEMIES .byte 0
enemies_def_id       :MAX_ENEMIES .byte 0
enemies_sprite_id    :MAX_ENEMIES .byte 0
enemies_min_x        :MAX_ENEMIES .byte 0
enemies_max_x        :MAX_ENEMIES .byte 0
enemies_x            :MAX_ENEMIES .byte 0
enemies_pmg_y        :MAX_ENEMIES .byte 0
enemies_height       :MAX_ENEMIES .byte 0
enemies_frame_dur    :MAX_ENEMIES .byte 0
enemies_frame_count  :MAX_ENEMIES .byte 0
enemies_speed        :MAX_ENEMIES .byte 0
enemies_strategy     :MAX_ENEMIES .byte 0
enemies_dir          :MAX_ENEMIES .byte 0  ; 0 = right, 1 = left
enemies_color        :MAX_ENEMIES .byte 0
enemies_channel      :MAX_ENEMIES .byte 0  ; 0 = P1, 1 = P2, 2 = P3
enemies_zone         :MAX_ENEMIES .byte 0  ; 0..6
enemies_timer        :MAX_ENEMIES .byte 0  ; Frame animation timer
enemies_frame_idx    :MAX_ENEMIES .byte 0  ; Active animation frame index
enemies_speed_timer  :MAX_ENEMIES .byte 0  ; Movement speed countdown
enemies_pause_timer  :MAX_ENEMIES .byte 0  ; 50-frame pause countdown

; ==============================================================================
; RENDER ENEMY FRAME
; Copies a single frame of an enemy's sprite into its assigned PMG player buffer.
; Input: X = enemy index (0..MAX_ENEMIES-1)
; Preserves: X
; ==============================================================================
.proc render_enemy_frame
    ; 1. Resolve frame data address from master sprite tables
    ldy enemies_sprite_id,x     ; Y = sprite_id (1..MAX_SPRITE_ID)
    lda sprite_frames_table_lo,y
    sta zp_ptr_src
    lda sprite_frames_table_hi,y
    sta zp_ptr_src+1

    ; Frame pointer table is an array of .word addresses (2 bytes per frame)
    lda enemies_frame_idx,x
    asl                         ; Frame index * 2
    tay

    lda (zp_ptr_src),y
    sta zp_temp_a               ; Frame addr low
    iny
    lda (zp_ptr_src),y
    sta zp_temp_x               ; Frame addr high

    lda zp_temp_a
    sta zp_ptr_src
    lda zp_temp_x
    sta zp_ptr_src+1

    ; 2. Determine PMG player destination buffer based on channel (0=P1, 1=P2, 2=P3)
    lda enemies_channel,x
    bne @check_p2
    lda #>PMG_PLAYER1
    jmp @store_dst_hi
@check_p2
    cmp #1
    bne @use_p3
    lda #>PMG_PLAYER2
    jmp @store_dst_hi
@use_p3
    lda #>PMG_PLAYER3
@store_dst_hi
    sta zp_ptr_dst+1
    lda enemies_pmg_y,x
    sta zp_ptr_dst

    ; 3. Copy scanlines from frame into PMG buffer
    ldy enemies_height,x
    dey
    bmi @done
@sl_loop
    lda (zp_ptr_src),y
    sta (zp_ptr_dst),y
    dey
    bpl @sl_loop

@done
    rts
.endp

; ==============================================================================
; CLEAR ENEMY ROWS
; Clears the scanlines of an enemy in PMG memory with $00.
; Input: X = enemy index (0..MAX_ENEMIES-1)
; Preserves: X
; ==============================================================================
.proc clear_enemy_rows
    lda enemies_channel,x
    bne @check_p2
    lda #>PMG_PLAYER1
    jmp @store_dst_hi
@check_p2
    cmp #1
    bne @use_p3
    lda #>PMG_PLAYER2
    jmp @store_dst_hi
@use_p3
    lda #>PMG_PLAYER3
@store_dst_hi
    sta zp_ptr_dst+1
    lda enemies_pmg_y,x
    sta zp_ptr_dst

    lda #0
    ldy enemies_height,x
    dey
    bmi @done
@clear_loop
    sta (zp_ptr_dst),y
    dey
    bpl @clear_loop

@done
    rts
.endp

; ==============================================================================
; UPDATE ENEMY HPOS
; Computes hardware horizontal position (48 + X) and stores it in DLI tables.
; Input: X = enemy index (0..MAX_ENEMIES-1)
; Preserves: X
; ==============================================================================
.proc update_enemy_hpos
    ; Calculate hardware HPOS = 48 + x
    clc
    lda enemies_x,x
    adc #48
    sta zp_temp_a

    lda enemies_zone,x
    beq @zone_0

    ; Zones 1..6: table offset = zone - 1 (0..5)
    sec
    sbc #1
    tay

    lda enemies_channel,x
    bne @z_check_p2
    ; Channel 0: Player 1
    lda zp_temp_a
    sta dli_zone_hpos_p1,y
    sta dli_zone_hpos_p1+8,y
    rts

@z_check_p2
    cmp #1
    bne @z_use_p3
    ; Channel 1: Player 2
    lda zp_temp_a
    sta dli_zone_hpos_p2,y
    sta dli_zone_hpos_p2+8,y
    rts

@z_use_p3
    ; Channel 2: Player 3
    lda zp_temp_a
    sta dli_zone_hpos_p3,y
    sta dli_zone_hpos_p3+8,y
    rts

@zone_0
    lda enemies_channel,x
    bne @z0_check_p2
    lda zp_temp_a
    sta dli_z0_hpos_p1
    sta dli_z0_hpos_p1+1
    rts

@z0_check_p2
    cmp #1
    bne @z0_use_p3
    lda zp_temp_a
    sta dli_z0_hpos_p2
    sta dli_z0_hpos_p2+1
    rts

@z0_use_p3
    lda zp_temp_a
    sta dli_z0_hpos_p3
    sta dli_z0_hpos_p3+1
    rts
.endp

; ==============================================================================
; ENEMIES INIT
; Initializes enemies for active scene.
; Input: A = active_scene_id (0..SCENE_COUNT-1)
; ==============================================================================
.proc enemies_init
    ; 1. Clear PMG rows for any previous active enemies and reset active flags
    ldx #0
@clear_prev_loop
    cpx #MAX_ENEMIES
    bcs @clear_done
    lda enemies_active,x
    beq @next_prev
    jsr clear_enemy_rows
    lda #0
    sta enemies_active,x
@next_prev
    inx
    bne @clear_prev_loop
@clear_done

    ; 2. Read enemy count for new scene
    tax
    lda scene_enemy_count,x
    sta enemies_count
    bne @has_enemies
    rts

@has_enemies
    ; 3. Copy SoA tables from ROM master pointers into RAM
    ; def_id
    lda scene_enemy_def_id_lo,x
    sta zp_ptr_src
    lda scene_enemy_def_id_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_def
    lda (zp_ptr_src),y
    sta enemies_def_id,y
    dey
    bpl @cp_def

    ; sprite_id
    lda scene_enemy_sprite_id_lo,x
    sta zp_ptr_src
    lda scene_enemy_sprite_id_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_spr
    lda (zp_ptr_src),y
    sta enemies_sprite_id,y
    dey
    bpl @cp_spr

    ; min_x
    lda scene_enemy_min_x_lo,x
    sta zp_ptr_src
    lda scene_enemy_min_x_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_min_x
    lda (zp_ptr_src),y
    sta enemies_min_x,y
    dey
    bpl @cp_min_x

    ; max_x
    lda scene_enemy_max_x_lo,x
    sta zp_ptr_src
    lda scene_enemy_max_x_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_max_x
    lda (zp_ptr_src),y
    sta enemies_max_x,y
    dey
    bpl @cp_max_x

    ; x
    lda scene_enemy_x_lo,x
    sta zp_ptr_src
    lda scene_enemy_x_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_x
    lda (zp_ptr_src),y
    sta enemies_x,y
    dey
    bpl @cp_x

    ; pmg_y
    lda scene_enemy_pmg_y_lo,x
    sta zp_ptr_src
    lda scene_enemy_pmg_y_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_pmg_y
    lda (zp_ptr_src),y
    sta enemies_pmg_y,y
    dey
    bpl @cp_pmg_y

    ; height
    lda scene_enemy_height_lo,x
    sta zp_ptr_src
    lda scene_enemy_height_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_h
    lda (zp_ptr_src),y
    sta enemies_height,y
    dey
    bpl @cp_h

    ; frame_dur
    lda scene_enemy_frame_dur_lo,x
    sta zp_ptr_src
    lda scene_enemy_frame_dur_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_dur
    lda (zp_ptr_src),y
    sta enemies_frame_dur,y
    dey
    bpl @cp_dur

    ; frame_count
    lda scene_enemy_frame_count_lo,x
    sta zp_ptr_src
    lda scene_enemy_frame_count_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_cnt
    lda (zp_ptr_src),y
    sta enemies_frame_count,y
    dey
    bpl @cp_cnt

    ; speed
    lda scene_enemy_speed_lo,x
    sta zp_ptr_src
    lda scene_enemy_speed_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_spd
    lda (zp_ptr_src),y
    sta enemies_speed,y
    dey
    bpl @cp_spd

    ; strategy
    lda scene_enemy_strategy_lo,x
    sta zp_ptr_src
    lda scene_enemy_strategy_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_strat
    lda (zp_ptr_src),y
    sta enemies_strategy,y
    dey
    bpl @cp_strat

    ; dir
    lda scene_enemy_dir_lo,x
    sta zp_ptr_src
    lda scene_enemy_dir_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_dir
    lda (zp_ptr_src),y
    sta enemies_dir,y
    dey
    bpl @cp_dir

    ; color
    lda scene_enemy_color_lo,x
    sta zp_ptr_src
    lda scene_enemy_color_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_col
    lda (zp_ptr_src),y
    sta enemies_color,y
    dey
    bpl @cp_col

    ; channel
    lda scene_enemy_channel_lo,x
    sta zp_ptr_src
    lda scene_enemy_channel_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_ch
    lda (zp_ptr_src),y
    sta enemies_channel,y
    dey
    bpl @cp_ch

    ; zone
    lda scene_enemy_zone_lo,x
    sta zp_ptr_src
    lda scene_enemy_zone_hi,x
    sta zp_ptr_src+1
    ldy enemies_count
    dey
@cp_zone
    lda (zp_ptr_src),y
    sta enemies_zone,y
    dey
    bpl @cp_zone

    ; 4. Initialize runtime state for each enemy
    ldx #0
@init_loop
    lda #1
    sta enemies_active,x
    lda #0
    sta enemies_frame_idx,x
    sta enemies_speed_timer,x
    sta enemies_pause_timer,x
    lda enemies_frame_dur,x
    sta enemies_timer,x

    jsr render_enemy_frame
    jsr update_enemy_hpos

    inx
    cpx enemies_count
    bcc @init_loop

    rts
.endp

; ==============================================================================
; ENEMIES UPDATE
; Advances animation and platform patrol movement once per frame.
; ==============================================================================
.proc enemies_update
    ldx #0
@loop
    cpx enemies_count
    bcc @continue_loop
    rts
@continue_loop

    lda enemies_active,x
    bne @is_active
    jmp @next
@is_active

    ; 1. Animation frame countdown
    dec enemies_timer,x
    bne @skip_anim
    lda enemies_frame_dur,x
    sta enemies_timer,x
    inc enemies_frame_idx,x
    lda enemies_frame_idx,x
    cmp enemies_frame_count,x
    bcc @anim_ok
    lda #0
    sta enemies_frame_idx,x
@anim_ok
    jsr render_enemy_frame

@skip_anim
    ; 2. Check pause timer (1 sec = 50 frames pause at boundary)
    lda enemies_pause_timer,x
    beq @check_speed
    dec enemies_pause_timer,x
    jmp @next               ; While paused, do not move

@check_speed
    ; 3. Check movement speed
    ; speed = 0: slow   (every 4 frames)
    ; speed = 1: medium (every 2 frames)
    ; speed = 2: fast   (every frame)
    lda enemies_speed,x
    bne @check_med
    ; Slow: check speed_timer == 0
    lda enemies_speed_timer,x
    bne @dec_timer
    lda #3
    sta enemies_speed_timer,x
    jmp @move_step

@check_med
    cmp #1
    bne @fast_move
    ; Medium: check speed_timer == 0
    lda enemies_speed_timer,x
    bne @dec_timer
    lda #1
    sta enemies_speed_timer,x
    jmp @move_step

@fast_move
    ; Fast: moves every frame
    lda #0
    sta enemies_speed_timer,x
    jmp @move_step

@dec_timer
    dec enemies_speed_timer,x
    jmp @next

@move_step
    ; 4. Check strategy: 0 = stationary -> no movement
    lda enemies_strategy,x
    beq @next

    ; Check direction: 0 = right, 1 = left
    lda enemies_dir,x
    bne @move_left

    ; Moving Right (dir = 0)
    lda enemies_x,x
    clc
    adc #1
    cmp enemies_max_x,x
    bcc @store_x_right
    ; Hit or reached right boundary!
    lda enemies_max_x,x
    sta enemies_x,x
    lda #1
    sta enemies_dir,x      ; Reverse to left (1)
    ; Check if strategy has pause (3: left_pause_right, 4: right_pause_left)
    lda enemies_strategy,x
    cmp #3
    bcc @update_pos        ; 1 or 2 -> no pause
    lda #50                ; 1 second = 50 frames pause
    sta enemies_pause_timer,x
    jmp @update_pos

@store_x_right
    sta enemies_x,x
    jmp @update_pos

@move_left
    ; Moving Left (dir = 1)
    lda enemies_x,x
    sec
    sbc #1
    cmp enemies_min_x,x
    beq @hit_left
    bcc @hit_left
    sta enemies_x,x
    jmp @update_pos

@hit_left
    ; Hit or reached left boundary!
    lda enemies_min_x,x
    sta enemies_x,x
    lda #0
    sta enemies_dir,x      ; Reverse to right (0)
    ; Check if strategy has pause (3: left_pause_right, 4: right_pause_left)
    lda enemies_strategy,x
    cmp #3
    bcc @update_pos        ; 1 or 2 -> no pause
    lda #50                ; 1 second = 50 frames pause
    sta enemies_pause_timer,x

@update_pos
    jsr update_enemy_hpos

@next
    inx
    jmp @loop

@done
    rts
.endp

; ==============================================================================
; ENEMIES CHECK PLAYER COLLISION
; Checks bounding box overlap between Hero and all active enemies.
; If Hero touches an enemy, triggers player_handle_death.
; ==============================================================================
.proc enemies_check_player_collision
    ; Collision is active only while playing and alive
    lda player_lives
    beq @done

    ldx #0
@loop
    cpx enemies_count
    bcs @done

    lda enemies_active,x
    beq @next

    ; 1. Check horizontal overlap: abs(player_x - enemies_x,x) < 8
    lda player_x
    sec
    sbc enemies_x,x
    bcs @x_pos
    eor #$FF
    clc
    adc #1
@x_pos
    cmp #8
    bcs @next

    ; 2. Check vertical overlap:
    ; enemies_pmg_y + enemies_height > player_pmg_y
    lda enemies_pmg_y,x
    clc
    adc enemies_height,x
    sec
    sbc player_pmg_y
    beq @next
    bcc @next

    ; player_pmg_y + 20 > enemies_pmg_y
    lda player_pmg_y
    clc
    adc #20
    sec
    sbc enemies_pmg_y,x
    beq @next
    bcc @next

    ; Collision detected! Hero dies!
    jsr player_handle_death
    sta HITCLR
    rts

@next
    inx
    jmp @loop

@done
    rts
.endp
