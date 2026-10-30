; ==============================================================================
; SECRETS CHANNEL DISPATCH — per-definition sprite channel for secrets
; Target: Atari 800XL / 65XE (MOS 6502)
;
; A secret definition in scenes/definitions.json selects its rendering channel:
; - "missiles" (default): the 5th player built from M0..M3 (HPOSM0..M3 + COLPF3,
;   bitmap in PMG_MISSILES)
; - "player": one of Players 1..3 (HPOSP1..P3 + COLPM1..P3, bitmap in PMG_PLAYER1..3)
;
; The compiler keeps every platform row and dependency stage within
; MAX_CHANNELS_PER_ROW = 4 sprite channels (enemies claim theirs first), so a player
; channel carries no enemy in the row/stage where the secret is displayed.
;
; This module lives in the free tail of the $5C00 page (between the Game Over module
; and the Title display list) because the $5000 runtime block is full: the whole
; $5000-$5BFF window is taken by the scene DLI data and the secrets/enemies/sfx code.
; ==============================================================================

; --- Per-secret sprite channel: 0..2 = Players 1..3, 3 = 5th player (missiles) ---
; secrets_channel declared in main.asm under GAMEOVER_CODE

; PMG page holding the bitmap of each channel (index = channel)
secret_pmg_pages
    .byte >PMG_PLAYER1, >PMG_PLAYER2, >PMG_PLAYER3, >PMG_MISSILES

; Channel -> DLI table offset. The player tables are declared in engine/dli.asm as
;   dli_zone_hpos_p1, dli_zone_col_p1, dli_zone_hpos_p2, dli_zone_col_p2, ...
; (16 bytes each), so one channel step is 32 bytes for the zone tables and 4 bytes
; for the 2-byte zone 0 tables. The assertions below fail the build if that layout
; ever changes, instead of silently drawing the secret in the wrong table.
    .if dli_zone_hpos_p2 - dli_zone_hpos_p1 <> 32
        .error "dli_zone_hpos_p* stride changed - update engine/secrets_channel.asm"
    .endif
    .if dli_zone_hpos_p3 - dli_zone_hpos_p1 <> 64
        .error "dli_zone_hpos_p* stride changed - update engine/secrets_channel.asm"
    .endif
    .if dli_zone_col_p2 - dli_zone_col_p1 <> 32
        .error "dli_zone_col_p* stride changed - update engine/secrets_channel.asm"
    .endif
    .if dli_zone_col_p3 - dli_zone_col_p1 <> 64
        .error "dli_zone_col_p* stride changed - update engine/secrets_channel.asm"
    .endif
    .if dli_z0_hpos_p2 - dli_z0_hpos_p1 <> 4
        .error "dli_z0_hpos_p* stride changed - update engine/secrets_channel.asm"
    .endif
    .if dli_z0_hpos_p3 - dli_z0_hpos_p1 <> 8
        .error "dli_z0_hpos_p* stride changed - update engine/secrets_channel.asm"
    .endif
    .if dli_z0_col_p2 - dli_z0_col_p1 <> 4
        .error "dli_z0_col_p* stride changed - update engine/secrets_channel.asm"
    .endif
    .if dli_z0_col_p3 - dli_z0_col_p1 <> 8
        .error "dli_z0_col_p* stride changed - update engine/secrets_channel.asm"
    .endif

secret_zone_off .byte 0, 32, 64     ; dli_zone_* offset per player channel
secret_z0_off   .byte 0, 4, 8       ; dli_z0_* offset per player channel

; ==============================================================================
; SECRET PMG DESTINATION
; Sets zp_ptr_dst = PMG page of a secret's channel + secrets_pmg_y.
; Input: X = secret index (0..MAX_SECRETS-1)
; Preserves: X
; ==============================================================================
.proc secret_pmg_dst
    ldy secrets_channel,x
    cpy #4
    bcc @channel_ok
    ldy #3                  ; corrupt data -> 5th player
@channel_ok
    lda secret_pmg_pages,y
    sta zp_ptr_dst+1
    lda secrets_pmg_y,x
    sta zp_ptr_dst
    rts
.endp

; ==============================================================================
; WRITE SECRET PLAYER CHANNEL
; Commits a player-channel secret's horizontal position and colour to the DLI
; tables (HPOSP<ch> + COLPM<ch>) of its zone, in both double buffers.
; Input: X = secret index, zp_temp_a = HPOS (48 + X), zp_temp_x = colour
; Preserves: X
; ==============================================================================
.proc secret_write_player
    lda secrets_zone,x
    beq @zone_0

    ; Zones 1..6: table offset = channel * 32 + (zone - 1)
    sec
    sbc #1
    ldy secrets_channel,x
    clc
    adc secret_zone_off,y
    tay

    lda zp_temp_a
    sta dli_zone_hpos_p1,y
    sta dli_zone_hpos_p1+8,y
    lda zp_temp_x
    sta dli_zone_col_p1,y
    sta dli_zone_col_p1+8,y
    rts

@zone_0
    ; Zone 0: 2-byte tables, offset = channel * 4
    ldy secrets_channel,x
    lda secret_z0_off,y
    tay

    lda zp_temp_a
    sta dli_z0_hpos_p1,y
    sta dli_z0_hpos_p1+1,y
    lda zp_temp_x
    sta dli_z0_col_p1,y
    sta dli_z0_col_p1+1,y
    rts
.endp

; ==============================================================================
; CLEAR SECRET PLAYER CHANNEL
; Moves a player-channel secret off screen (HPOS = $FF) in both DLI buffers.
; Input: X = secret index (0..MAX_SECRETS-1)
; Preserves: X
; ==============================================================================
.proc secret_clear_player
    lda #$FF
    sta zp_temp_a

    lda secrets_zone,x
    beq @zone_0

    sec
    sbc #1
    ldy secrets_channel,x
    clc
    adc secret_zone_off,y
    tay

    lda zp_temp_a
    sta dli_zone_hpos_p1,y
    sta dli_zone_hpos_p1+8,y
    rts

@zone_0
    ldy secrets_channel,x
    lda secret_z0_off,y
    tay

    lda zp_temp_a
    sta dli_z0_hpos_p1,y
    sta dli_z0_hpos_p1+1,y
    rts
.endp

; ==============================================================================
; COPY SECRET CHANNELS
; Copies the active scene's scene_secret_channel table into secrets_channel.
; Input: X = scene id (0..SCENE_COUNT-1)
; Preserves: X
; ==============================================================================
.proc secrets_copy_channels
    lda scene_secret_channel_lo,x
    sta zp_ptr_src
    lda scene_secret_channel_hi,x
    sta zp_ptr_src+1
    ldy secrets_count
    dey
@copy
    lda (zp_ptr_src),y
    sta secrets_channel,y
    dey
    bpl @copy
    jsr secrets_copy_plat_idx
    rts
.endp
