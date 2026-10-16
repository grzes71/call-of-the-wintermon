; ==============================================================================
; SCENES/INTRO.ASM — Intro Screen State Handler
; 10 lines of ANTIC 2 (Gr.0 40x8), separated by 8 empty scanlines (DL_BLANK8).
; Centered horizontally. Foreground: light green ($CA), Background: black ($00).
; ==============================================================================

INTRO_TEXT_COLOR = $CA     ; Light green (Hue $C, Luminance $A)

.proc intro_init
    ; Turn off DMA during display list and color setup
    lda #0
    sta SDMCTL
    sta DMACTL

    ; Background / frame: Black ($00)
    sta COLOR2
    sta COLPF2
    sta COLOR4
    sta COLBK

    ; Text foreground: Light Green ($CA)
    lda #INTRO_TEXT_COLOR
    sta COLOR1
    sta COLPF1

    ; Set Display List pointer to dlist_intro
    lda <dlist_intro
    sta SDLSTL
    sta DLISTL
    lda >dlist_intro
    sta SDLSTH
    sta DLISTH

    ; Set character set font pointer to intro_font ($24)
    lda >intro_font
    sta CHBAS
    sta CHBASE

    ; Require releasing fire button before accepting next press
    lda #0
    sta fire_released

    ; Start Intro background music
    jsr audio_play_intro
    rts
.endp

.proc intro_run
    ; Enable playfield DMA (standard 40 cols playfield)
    lda #$22
    sta SDMCTL
    sta DMACTL

    ; Reset attract mode
    lda #0
    sta ATRACT

    ; Wait for VBLANK
    lda RTCLOK+2
@sync_vblank
    cmp RTCLOK+2
    beq @sync_vblank

    ; Advance music playback by 1 frame
    jsr audio_update

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
    ; Stop intro music before transition
    jsr audio_stop

    ; Transition to GAME screen
    lda #STATE_GAME
    sta game_state
    rts
.endp
