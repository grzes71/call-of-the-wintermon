; ==============================================================================
; ENGINE/SFX_SECRET.ASM — Secret-Collect Blip (POKEY Channel 3)
; Target: Atari 800XL / 65XE (MOS 6502)
;
; Two short rising blips, both on Channel 3 - the only channel the other effects
; never touch (footstep/jump/death/fanfare use Channel 1, free fall uses 2):
;   - normal secret  ("special": false) - 2 notes, C5 -> F5, 6 frames  (~0.12 s)
;   - special secret ("special": true)  - 3 notes, G5 -> C6 -> E6, 9 frames (~0.18 s)
;     (an octave above the normal blip, one note longer, so the two are clearly
;      distinguishable by ear without any change of timbre)
;
; Triggered from secret_collect (scenes/game.asm). The blip is deliberately NOT
; started when the collected secret is the last one of the scene - that path plays
; the victory fanfare instead (engine/sfx_victory.asm).
;
; MEMORY: lives in the TILES_META segment ($2A30) next to engine/sfx_victory.asm,
; because the SCENES_DATA block ($5000) has no headroom left. sfx_update
; (engine/sfx.asm) reaches it through sfx_secret_tick.
; ==============================================================================

; --- Secret-Collect Blip State & Data ---
sfx_secret_timer    .byte 0     ; Blip frame countdown (0 = inactive)
sfx_secret_special  .byte 0     ; 0 = normal blip, 1 = special blip (table selector)

SFX_SECRET_DURATION         = 6 ; Normal blip: 2 notes x 3 frames (~0.12 s)
SFX_SECRET_SPECIAL_DURATION = 9 ; Special blip: 3 notes x 3 frames (~0.18 s)

; Normal secret: C5 ($3C) -> F5 ($2D), 3 frames per note, pure tone distortion $A0
sfx_secret_audf
    .byte $3C, $3C, $3C, $2D, $2D, $2D
sfx_secret_audc
    .byte $A8, $A8, $A8, $A4, $A4, $A4

; Special secret: G5 ($28) -> C6 ($1D) -> E6 ($17), 3 frames per note
sfx_secret_sp_audf
    .byte $28, $28, $28, $1D, $1D, $1D, $17, $17, $17
sfx_secret_sp_audc
    .byte $AC, $AC, $AC, $A8, $A8, $A8, $A4, $A4, $A4


; ==============================================================================
; SFX_PLAY_SECRET_COLLECT
; Starts the collect blip for the secret that has just been collected.
; Input: A = 0 -> normal secret, A != 0 -> special secret ("special": true).
; Clobbers A and X.
; ==============================================================================
.proc sfx_play_secret_collect
    sta sfx_secret_special
    cmp #0                      ; self-contained: does not rely on the caller's flags
    beq @normal

    lda #SFX_SECRET_SPECIAL_DURATION
    sta sfx_secret_timer
    lda sfx_secret_sp_audf + 0
    sta AUDF3
    lda sfx_secret_sp_audc + 0
    sta AUDC3
    rts

@normal
    lda #SFX_SECRET_DURATION
    sta sfx_secret_timer
    lda sfx_secret_audf + 0
    sta AUDF3
    lda sfx_secret_audc + 0
    sta AUDC3
    rts
.endp


; ==============================================================================
; SFX_SECRET_TICK
; Per-frame blip driver, called from sfx_update (engine/sfx.asm).
; Unlike the victory fanfare it never takes the frame exclusively: the blip owns
; Channel 3, so the caller falls through to the remaining sounds either way.
; Clobbers A and X - sfx_update restores all registers on exit.
; ==============================================================================
.proc sfx_secret_tick
    lda sfx_secret_timer
    beq @inactive

    dec sfx_secret_timer
    beq @finished

    ; Frame index (0-based) = DURATION - timer, selected by the blip variant
    lda sfx_secret_special
    beq @normal

    lda #SFX_SECRET_SPECIAL_DURATION
    sec
    sbc sfx_secret_timer
    tax
    lda sfx_secret_sp_audf,x
    sta AUDF3
    lda sfx_secret_sp_audc,x
    sta AUDC3
    rts

@normal
    lda #SFX_SECRET_DURATION
    sec
    sbc sfx_secret_timer
    tax
    lda sfx_secret_audf,x
    sta AUDF3
    lda sfx_secret_audc,x
    sta AUDC3
    rts

@finished
    lda #0
    sta AUDC3
    sta AUDF3
@inactive
    rts
.endp
