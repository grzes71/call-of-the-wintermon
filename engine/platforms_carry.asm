; ==============================================================================
; PLATFORMS_CARRY.ASM — Platform Object Carrying Engine
; Target: Atari 800XL / 65XE (MOS 6502)
; Relocated to free headroom before PMG missiles ($6A6A-$6AE0 < $6B00)
; ==============================================================================

; ==============================================================================
; PLATFORMS CARRY OBJECTS
; Ties the X coordinate of any Secrets or Enemies placed on platform X directly
; to the platform's current X position:
;   - secrets_x[i]     = plat_x[X] + secrets_rel_x[i]
;   - enemies_x[i]     = plat_x[X] + (enemies_x[i] - enemies_min_x[i])
;   - enemies_max_x[i] = plat_x[X] + (enemies_max_x[i] - enemies_min_x[i])
;   - enemies_min_x[i] = plat_x[X]
; and updates their DLI horizontal positions in both double buffers.
; Input: X = platform index (0..plat_count-1)
; Preserves: X
; ==============================================================================
.proc platforms_carry_objects
    stx plat_cur_idx
    txa
    tay
    lda (zp_plat_ptr_x),y
    sta plat_cur_x

    ; --- 1. Tie Secrets on platform plat_cur_idx to plat_cur_x ---
    ldx secrets_count
    beq @sec_done
    dex
@sec_loop
    lda secrets_plat_idx,x
    cmp plat_cur_idx
    bne @sec_next

    lda secrets_collected,x
    bne @sec_next

    lda plat_cur_x
    clc
    adc secrets_rel_x,x
    cmp #152
    bcc @sec_store_x
    lda #152
@sec_store_x
    sta secrets_x,x

    lda secrets_active,x
    beq @sec_next
    jsr update_secret_hpos

@sec_next
    dex
    bpl @sec_loop

@sec_done
    ; --- 2. Tie Enemies on platform plat_cur_idx to plat_cur_x ---
    ldx enemies_count
    beq @enm_done
    dex
@enm_loop
    lda enemies_plat_idx,x
    cmp plat_cur_idx
    bne @enm_next

    lda enemies_active,x
    beq @enm_next

    ; Compute platform displacement relative to enemy's current min_x (= old plat_x)
    lda plat_cur_x
    sec
    sbc enemies_min_x,x
    sta zp_temp_a               ; delta = plat_cur_x - enemies_min_x,x

    lda enemies_x,x
    clc
    adc zp_temp_a
    sta enemies_x,x

    lda enemies_max_x,x
    clc
    adc zp_temp_a
    sta enemies_max_x,x

    lda plat_cur_x
    sta enemies_min_x,x

    jsr update_enemy_hpos

@enm_next
    dex
    bpl @enm_loop

@enm_done
    ldx plat_cur_idx
    rts
.endp

