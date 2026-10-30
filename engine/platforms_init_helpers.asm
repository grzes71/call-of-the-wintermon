; ==============================================================================
; PLATFORMS_INIT_HELPERS.ASM — Platform & Scene Object Init Helpers
; Target: Atari 800XL / 65XE (MOS 6502)
; Relocated to free headroom in $6000 page ($607A-$60E8 < $6100)
; ==============================================================================

; ==============================================================================
; SECRETS COPY PLAT IDX
; Copies the active scene's scene_secret_plat_idx table into secrets_plat_idx
; and derives secrets_rel_x[i] = scene_secret_x[i] - scene_plat_init_x[plat_idx].
; Input: X = scene id (0..SCENE_COUNT-1)
; Preserves: X
; ==============================================================================
.proc secrets_copy_plat_idx
    ldy scene_secret_count,x
    beq @done
    cpy #MAX_SECRETS
    bcc @cnt_ok
    ldy #MAX_SECRETS
@cnt_ok
    lda scene_secret_plat_idx_lo,x
    sta zp_ptr_src
    lda scene_secret_plat_idx_hi,x
    sta zp_ptr_src+1
    dey
@loop
    lda (zp_ptr_src),y
    sta secrets_plat_idx,y
    dey
    bpl @loop

    ; Compute secrets_rel_x[y] = scene_secret_x[y] - scene_plat_init_x[secrets_plat_idx[y]]
    lda scene_secret_x_lo,x
    sta zp_ptr_src
    lda scene_secret_x_hi,x
    sta zp_ptr_src+1

    lda scene_plat_init_x_lo,x
    sta zp_ptr_dst
    lda scene_plat_init_x_hi,x
    sta zp_ptr_dst+1

    ldy scene_secret_count,x
    dey
@rel_loop
    sty plat_cur_idx
    lda secrets_plat_idx,y
    tay
    lda (zp_ptr_dst),y          ; A = scene_plat_init_x[p]
    sta zp_temp_a
    ldy plat_cur_idx
    lda (zp_ptr_src),y          ; A = scene_secret_x[y]
    sec
    sbc zp_temp_a               ; A = scene_secret_x[y] - scene_plat_init_x[p]
    sta secrets_rel_x,y
    dey
    bpl @rel_loop
@done
    rts
.endp

; ==============================================================================
; ENEMIES COPY PLAT IDX
; Copies the active scene's scene_enemy_plat_idx table into enemies_plat_idx.
; Input: X = scene id (0..SCENE_COUNT-1)
; Preserves: X
; ==============================================================================
.proc enemies_copy_plat_idx
    ldy scene_enemy_count,x
    beq @done
    cpy #MAX_ENEMIES
    bcc @cnt_ok
    ldy #MAX_ENEMIES
@cnt_ok
    lda scene_enemy_plat_idx_lo,x
    sta zp_ptr_src
    lda scene_enemy_plat_idx_hi,x
    sta zp_ptr_src+1
    dey
@loop
    lda (zp_ptr_src),y
    sta enemies_plat_idx,y
    dey
    bpl @loop
@done
    rts
.endp

