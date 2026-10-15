; ==============================================================================
; SCENES/TITLE.ASM — Title Screen State Handler
; Target: Atari 800XL / 65XE
; Mode: ANTIC Mode F (Graphics 8, 320x192, 1 bpp)
; ==============================================================================

.proc title_init
    ; Turn off ANTIC DMA during setup
    lda #0
    sta SDMCTL
    sta DMACTL

    ; Set background / frame colors to Black ($00)
    sta COLOR2
    sta COLPF2
    sta COLOR4
    sta COLBK

    ; Set Display List pointer
    lda <dlist_title
    sta SDLSTL
    sta DLISTL
    lda >dlist_title
    sta SDLSTH
    sta DLISTH

    ; Require releasing fire button before accepting next press
    lda #0
    sta fire_released

    ; Check if this is the first time the title screen is shown
    lda title_first_run
    beq @show_immediate

    ; --- First run: 28-frame fade-in from black ($00) ---
    lda #0
    sta COLOR1
    sta COLPF1
    sta fade_frame
    rts

@show_immediate
    ; --- Return from Game Over: show immediately at full brightness ($0E) ---
    lda #$0E
    sta COLOR1
    sta COLPF1
    lda #28
    sta fade_frame

    ; Start music immediately on re-entry
    jsr audio_play_title
    rts
.endp

.proc title_run
    ; Enable playfield DMA (normal width 320px playfield)
    lda #$22
    sta SDMCTL
    sta DMACTL

    ; Reset attract mode
    lda #0
    sta ATRACT

    ; Synchronize with VBLANK via RTCLOK low byte ($14)
    lda RTCLOK+2
@sync_vblank
    cmp RTCLOK+2
    beq @sync_vblank

    ; --- Handle 28-frame fade-in ---
    lda fade_frame
    cmp #28
    bcs @fade_completed

    ; Still fading: advance fade frame
    inc fade_frame
    lda fade_frame
    lsr @
    and #$0E            ; Generates even GTIA luminance: $00, $02, ..., $0E
    sta COLOR1
    sta COLPF1

    ; Check if fade finished on this frame
    lda fade_frame
    cmp #28
    bcc @check_input

    ; Fade-in complete: lock to full white, clear first_run flag, and start music
    lda #$0E
    sta COLOR1
    sta COLPF1
    lda #0
    sta title_first_run

    jsr audio_play_title
    jmp @check_input

@fade_completed
    ; Advance music player by 1 frame
    jsr audio_update

@check_input
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
    ; Stop title music before state transition
    jsr audio_stop

    ; Transition to INTRO screen
    lda #STATE_INTRO
    sta game_state
    rts
.endp
