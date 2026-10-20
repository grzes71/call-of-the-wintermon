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
    tax                     ; X = scene_id
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

    ; 10. Clear secrets_collected array
    ldy secrets_count
    dey
    lda #0
@clr_coll
    sta secrets_collected,y
    dey
    bpl @clr_coll

    ; 11. Clear PMG rows for all scene secrets
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
    ; 12. Render Frame 0 for active secrets
    ldx #0
@init_render_loop
    cpx secrets_count
    bcs @done

    lda secrets_active,x
    beq @skip_initial

    ; Active: render Frame 0
    txa
    pha
    jsr render_secret_frame
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
    ldx #0
@loop
    cpx secrets_count
    bcs @done

    ; Only animate active secrets
    lda secrets_active,x
    beq @next

    ; Decrement animation timer
    dec secrets_timer,x
    bne @next

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

@next
    inx
    jmp @loop

@done
    rts
.endp
