; ==============================================================================
; SECRETS.ASM — Secret Animation & Rendering Engine (5th Player / 4 Missiles)
; Target: Atari 800XL / 65XE (MOS 6502)
;
; In 5th player mode:
; - 4 Missiles (M0..M3) are grouped into a single 8-pixel wide Player
; - Positioned horizontally via HPOSM0..HPOSM3 (set by DLI per zone)
; - Colored via COLPF3 (set by DLI per zone)
; - Displayed using packed bytes in PMG_MISSILES ($6B00 + Y)
; ==============================================================================

MAX_SECRETS = 6
SECRETS_BLINK_STEP_FRAMES = 2   ; Frames each luminance step is held (2 = 2x slower blink pulse)

; --- Active Scene Secrets State (Structure-of-Arrays) ---
secrets_count       .byte 0
secrets_active      :MAX_SECRETS .byte 0
secrets_collected   :MAX_SECRETS .byte 0
secrets_def_id      :MAX_SECRETS .byte 0
secrets_dep_id      :MAX_SECRETS .byte 0
secrets_sprite_id   :MAX_SECRETS .byte 0
secrets_x           :MAX_SECRETS .byte 0
secrets_pmg_y       :MAX_SECRETS .byte 0
secrets_height      :MAX_SECRETS .byte 0
secrets_frame_dur   :MAX_SECRETS .byte 0
secrets_frame_count :MAX_SECRETS .byte 0
secrets_timer       :MAX_SECRETS .byte 0
secrets_frame_idx   :MAX_SECRETS .byte 0
secrets_color       :MAX_SECRETS .byte 0
secrets_zone        :MAX_SECRETS .byte 0
secrets_blink       :MAX_SECRETS .byte 0

; ==============================================================================
; RENDER SECRET FRAME
; Copies a single frame of a secret's sprite into PMG_MISSILES memory.
; Input: X = secret index (0..MAX_SECRETS-1)
; Preserves: X
; ==============================================================================
.proc render_secret_frame
    ; 1. Resolve frame data address from master sprite tables
    ldy secrets_sprite_id,x     ; Y = sprite_id (1..MAX_SPRITE_ID)
    lda sprite_frames_table_lo,y
    sta zp_ptr_src
    lda sprite_frames_table_hi,y
    sta zp_ptr_src+1

    ; Frame pointer table is an array of .word addresses (2 bytes per frame)
    lda secrets_frame_idx,x
    asl                         ; Frame index * 2
    tay

    lda (zp_ptr_src),y
    sta zp_temp_a               ; Frame addr low
    iny
    lda (zp_ptr_src),y
    sta zp_temp_x               ; Frame addr high

    ; Set zp_ptr_src = frame address
    lda zp_temp_a
    sta zp_ptr_src
    lda zp_temp_x
    sta zp_ptr_src+1

    ; 2. Set zp_ptr_dst = PMG_MISSILES + secrets_pmg_y,x
    lda #>PMG_MISSILES
    sta zp_ptr_dst+1
    lda secrets_pmg_y,x
    sta zp_ptr_dst

    ; 3. Copy scanlines from frame into PMG_MISSILES
    ldy secrets_height,x
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
; CLEAR SECRET ROWS
; Clears the scanlines of a secret in PMG_MISSILES memory with $00.
; Input: X = secret index (0..MAX_SECRETS-1)
; Preserves: X
; ==============================================================================
.proc clear_secret_rows
    lda #>PMG_MISSILES
    sta zp_ptr_dst+1
    lda secrets_pmg_y,x
    sta zp_ptr_dst

    lda #0
    ldy secrets_height,x
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
; UPDATE SECRET HPOS
; Updates DLI horizontal position (HPOSM0..M3), color (COLPF3), and PRIOR for
; a secret's zone in both DLI double buffers.
; Input: X = secret index (0..MAX_SECRETS-1)
; Preserves: X
; ==============================================================================
.proc update_secret_hpos
    clc
    lda secrets_x,x
    adc #48
    sta zp_temp_a       ; M0 = 48 + X

    lda secrets_zone,x
    beq @zone_0

    ; Zones 1..6: table offset = zone - 1 (0..5)
    sec
    sbc #1
    tay

    ; Buffer 0 (+0) and Buffer 1 (+8)
    lda zp_temp_a
    sta dli_zone_hpos_m0,y
    sta dli_zone_hpos_m0+8,y
    clc
    adc #2
    sta dli_zone_hpos_m1,y
    sta dli_zone_hpos_m1+8,y
    adc #2
    sta dli_zone_hpos_m2,y
    sta dli_zone_hpos_m2+8,y
    adc #2
    sta dli_zone_hpos_m3,y
    sta dli_zone_hpos_m3+8,y

    lda secrets_blink,x
    beq @solid_color
    lda secrets_color,x
    and #$F0
    ora secrets_blink_lum
    jmp @apply_color
@solid_color
    lda secrets_color,x
@apply_color
    sta dli_zone_secret_col,y
    sta dli_zone_secret_col+8,y
    lda #$11
    sta dli_zone_prior,y
    sta dli_zone_prior+8,y
    rts

@zone_0
    ; Zone 0: Buffer 0 (+0) and Buffer 1 (+1)
    lda zp_temp_a
    sta dli_z0_hpos_m0
    sta dli_z0_hpos_m0+1
    clc
    adc #2
    sta dli_z0_hpos_m1
    sta dli_z0_hpos_m1+1
    adc #2
    sta dli_z0_hpos_m2
    sta dli_z0_hpos_m2+1
    adc #2
    sta dli_z0_hpos_m3
    sta dli_z0_hpos_m3+1

    lda secrets_blink,x
    beq @solid_color_z0
    lda secrets_color,x
    and #$F0
    ora secrets_blink_lum
    jmp @apply_color_z0
@solid_color_z0
    lda secrets_color,x
@apply_color_z0
    sta dli_z0_secret_col
    sta dli_z0_secret_col+1
    sta COLPF3
    lda #$11
    sta dli_z0_prior
    sta dli_z0_prior+1
    rts
.endp

; ==============================================================================
; CLEAR SECRET HPOS
; Clears DLI horizontal position (HPOSM0..M3 = $FF) for a secret's zone in both
; DLI double buffers.
; Input: X = secret index (0..MAX_SECRETS-1)
; Preserves: X
; ==============================================================================
.proc clear_secret_hpos
    lda secrets_zone,x
    beq @zone_0

    sec
    sbc #1
    tay

    lda #$FF
    sta dli_zone_hpos_m0,y
    sta dli_zone_hpos_m0+8,y
    sta dli_zone_hpos_m1,y
    sta dli_zone_hpos_m1+8,y
    sta dli_zone_hpos_m2,y
    sta dli_zone_hpos_m2+8,y
    sta dli_zone_hpos_m3,y
    sta dli_zone_hpos_m3+8,y
    rts

@zone_0
    lda #$FF
    sta dli_z0_hpos_m0
    sta dli_z0_hpos_m0+1
    sta dli_z0_hpos_m1
    sta dli_z0_hpos_m1+1
    sta dli_z0_hpos_m2
    sta dli_z0_hpos_m2+1
    sta dli_z0_hpos_m3
    sta dli_z0_hpos_m3+1
    rts
.endp

; ==============================================================================
; SECRETS INIT
; Initializes secret state and renders Frame 0 for active secrets on scene load.
; Input: A = scene_id (0..SCENE_COUNT-1)
; ==============================================================================
.proc secrets_init
    cmp #SCENE_COUNT
    bcc @valid_id
    rts

@valid_id
    sta active_scene_id

    ; Initialize blinking luminance counter and its frame divider
    lda #0
    sta secrets_blink_lum
    lda #SECRETS_BLINK_STEP_FRAMES
    sta secrets_blink_timer

    ; 0. Clear PMG rows for any previous active secrets and reset active flags
    ldx #0
@clear_prev_loop
    cpx #MAX_SECRETS
    bcs @clear_done
    lda secrets_active,x
    beq @next_prev
    jsr clear_secret_rows
    lda #0
    sta secrets_active,x
@next_prev
    inx
    bne @clear_prev_loop
@clear_done

    ldx active_scene_id     ; X = scene_id
    lda scene_secret_count,x
    sta secrets_count
    bne @has_secrets
    rts

@has_secrets
    ; Limit count to MAX_SECRETS
    cmp #MAX_SECRETS
    bcc @count_ok
    lda #MAX_SECRETS
    sta secrets_count
@count_ok

    ; 1. Copy active flags
    lda scene_secret_active_lo,x
    sta zp_ptr_src
    lda scene_secret_active_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_active
    lda (zp_ptr_src),y
    sta secrets_active,y
    dey
    bpl @copy_active

    ; 2. Copy sprite IDs
    lda scene_secret_sprite_id_lo,x
    sta zp_ptr_src
    lda scene_secret_sprite_id_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_spr
    lda (zp_ptr_src),y
    sta secrets_sprite_id,y
    dey
    bpl @copy_spr

    ; 3. Copy PMG Y scanline offsets
    lda scene_secret_pmg_y_lo,x
    sta zp_ptr_src
    lda scene_secret_pmg_y_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_y
    lda (zp_ptr_src),y
    sta secrets_pmg_y,y
    dey
    bpl @copy_y

    ; 4. Copy heights
    lda scene_secret_height_lo,x
    sta zp_ptr_src
    lda scene_secret_height_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_h
    lda (zp_ptr_src),y
    sta secrets_height,y
    dey
    bpl @copy_h

    ; 5. Copy frame durations & initialize timer
    lda scene_secret_frame_dur_lo,x
    sta zp_ptr_src
    lda scene_secret_frame_dur_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_dur
    lda (zp_ptr_src),y
    sta secrets_frame_dur,y
    sta secrets_timer,y     ; Timer starts at frame_dur
    dey
    bpl @copy_dur

    ; 6. Copy frame counts & reset frame_idx = 0
    lda scene_secret_frame_count_lo,x
    sta zp_ptr_src
    lda scene_secret_frame_count_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_cnt
    lda (zp_ptr_src),y
    sta secrets_frame_count,y
    lda #0
    sta secrets_frame_idx,y
    dey
    bpl @copy_cnt

    ; 7. Copy def_ids
    lda scene_secret_def_id_lo,x
    sta zp_ptr_src
    lda scene_secret_def_id_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_def
    lda (zp_ptr_src),y
    sta secrets_def_id,y
    dey
    bpl @copy_def

    ; 8. Copy dep_ids
    lda scene_secret_dep_id_lo,x
    sta zp_ptr_src
    lda scene_secret_dep_id_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_dep
    lda (zp_ptr_src),y
    sta secrets_dep_id,y
    dey
    bpl @copy_dep

    ; 9. Copy X coordinates
    lda scene_secret_x_lo,x
    sta zp_ptr_src
    lda scene_secret_x_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_x
    lda (zp_ptr_src),y
    sta secrets_x,y
    dey
    bpl @copy_x

    ; 10. Copy colors
    lda scene_secret_color_lo,x
    sta zp_ptr_src
    lda scene_secret_color_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_col
    lda (zp_ptr_src),y
    sta secrets_color,y
    dey
    bpl @copy_col

    ; 11. Copy zones
    lda scene_secret_zone_lo,x
    sta zp_ptr_src
    lda scene_secret_zone_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_zone
    lda (zp_ptr_src),y
    sta secrets_zone,y
    dey
    bpl @copy_zone

    ; 12. Copy blink flags
    lda scene_secret_blink_lo,x
    sta zp_ptr_src
    lda scene_secret_blink_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy_blk
    lda (zp_ptr_src),y
    sta secrets_blink,y
    dey
    bpl @copy_blk

    ; 13. Clear secrets_collected array
    ldy secrets_count
    dey
    lda #0
@clr_coll
    sta secrets_collected,y
    dey
    bpl @clr_coll

    ; 14. Clear PMG rows for all scene secrets
    ldx #0
@clear_all_loop
    cpx secrets_count
    bcs @start_render
    txa
    pha
    jsr clear_secret_rows
    pla
    tax
    inx
    jmp @clear_all_loop

@start_render
    ; 15. Render Frame 0 and update DLI positions for active secrets
    ldx #0
@init_render_loop
    cpx secrets_count
    bcs @done

    lda secrets_active,x
    beq @skip_initial

    ; Active: render Frame 0 and configure DLI
    txa
    pha
    jsr render_secret_frame
    jsr update_secret_hpos
    pla
    tax

@skip_initial
    inx
    jmp @init_render_loop

@done
    rts
.endp

; ==============================================================================
; SECRETS UPDATE
; Advances animation timer and updates PMG_MISSILES rows for active secrets.
; Called once per frame during active gameplay.
; ==============================================================================
.proc secrets_update
    lda secrets_count
    bne @has_secrets
    rts

@has_secrets
    ; --------------------------------------------------------------------------
    ; 1. Blink Luminance Pulse for Active Blinking Secrets
    ; Pulsed color = (secrets_color,x & $F0) | secrets_blink_lum
    ; Applied to dli_zone_secret_col (both double buffers) or dli_z0_secret_col/COLPF3
    ; --------------------------------------------------------------------------
    ldx #0
@blink_loop
    cpx secrets_count
    bcs @advance_blink_lum

    lda secrets_active,x
    beq @next_blink
    lda secrets_blink,x
    beq @next_blink

    lda secrets_color,x
    and #$F0
    ora secrets_blink_lum
    sta zp_temp_a

    lda secrets_zone,x
    beq @blink_z0

    sec
    sbc #1
    tay
    lda zp_temp_a
    sta dli_zone_secret_col,y
    sta dli_zone_secret_col+8,y
    jmp @next_blink

@blink_z0
    lda zp_temp_a
    sta dli_z0_secret_col
    sta dli_z0_secret_col+1
    sta COLPF3

@next_blink
    inx
    jmp @blink_loop

@advance_blink_lum
    ; Hold each luminance step for SECRETS_BLINK_STEP_FRAMES frames
    ; (frame divider -> half-speed blinking pulse)
    dec secrets_blink_timer
    bne @blink_anim

    lda #SECRETS_BLINK_STEP_FRAMES
    sta secrets_blink_timer

    ; Advance luminance offset: $00 -> $02 -> ... -> $0E -> $00
    clc
    lda secrets_blink_lum
    adc #2
    and #$0E
    sta secrets_blink_lum

@blink_anim

    ; --------------------------------------------------------------------------
    ; 2. Secret Animation Frames Update
    ; --------------------------------------------------------------------------
    ldx #0
@anim_loop
    cpx secrets_count
    bcs @done

    ; Only animate active secrets
    lda secrets_active,x
    beq @next_anim

    ; Decrement animation timer
    dec secrets_timer,x
    bne @next_anim

    ; Timer reached 0: reload from frame duration
    lda secrets_frame_dur,x
    sta secrets_timer,x

    ; Advance to next animation frame
    inc secrets_frame_idx,x
    lda secrets_frame_idx,x
    cmp secrets_frame_count,x
    bcc @frame_ok
    lda #0
    sta secrets_frame_idx,x

@frame_ok
    ; Render updated frame to PMG_MISSILES
    txa
    pha
    jsr render_secret_frame
    pla
    tax

@next_anim
    inx
    jmp @anim_loop

@done
    rts
.endp
