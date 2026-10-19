; ==============================================================================
; SCENES/GAMEOVER.ASM — Game Over State Handler (Stub)
; Transitions back to STATE_TITLE upon Fire / Keypress
; ==============================================================================

.proc gameover_init
    ; Blank playfield and PMG DMA during stub screen
    lda #0
    sta SDMCTL
    sta DMACTL

    ; Disable GTIA PMG graphics and clear all player/missile positions
    sta GRACTL
    sta HPOSP0
    sta HPOSP1
    sta HPOSP2
    sta HPOSP3
    sta HPOSM0
    sta HPOSM1
    sta HPOSM2
    sta HPOSM3
    sta SIZEP0
    sta SIZEP1
    sta SIZEP2
    sta SIZEP3
    sta SIZEM
    sta GRAFP0
    sta GRAFP1
    sta GRAFP2
    sta GRAFP3
    sta GRAFM

    ; Clear entire PMG memory buffer ($6800-$6FFF, 2,048 bytes)
    tax
@clr_pmg
    sta PMG_ADDR + $0000,x
    sta PMG_ADDR + $0100,x
    sta PMG_ADDR + $0200,x
    sta PMG_ADDR + $0300,x
    sta PMG_ADDR + $0400,x
    sta PMG_ADDR + $0500,x
    sta PMG_ADDR + $0600,x
    sta PMG_ADDR + $0700,x
    inx
    bne @clr_pmg

    ; Set background to Black ($00)
    sta COLOR4
    sta COLBK

    ; Require releasing fire button before accepting next press
    lda #0
    sta fire_released
    rts
.endp

.proc gameover_run
    ; Reset attract mode
    lda #0
    sta ATRACT

    ; Wait for VBLANK
    lda RTCLOK+2
@sync_vblank
    cmp RTCLOK+2
    beq @sync_vblank

    ; Check if button was released first
    lda fire_released
    bne @can_press

    lda STRIG0
    bne @btn_released
    lda CH
    cmp #$FF
    beq @no_input
@btn_released
    lda #1
    sta fire_released
@no_input
    rts

@can_press
    ; Check Fire button (STRIG0 = 0) or Keypress (CH != $FF)
    lda STRIG0
    beq @fire_pressed
    lda CH
    cmp #$FF
    bne @key_pressed
    rts

@key_pressed
    lda #$FF
    sta CH              ; Clear key buffer

@fire_pressed
    ; Transition back to TITLE screen (without fade-in)
    lda #STATE_TITLE
    sta game_state
    rts
.endp
