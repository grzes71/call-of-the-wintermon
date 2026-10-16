; ==============================================================================
; SCENES/TITLE.ASM — Title Screen State Handler
; Target: Atari 800XL / 65XE
; Mode: ANTIC Mode D (160x95, 2 bpp, 4 colors) + ANTIC Mode 2 Scroller (40x8, 1 bpp)
; Palette:
;   %00 = COLBK  = $00 (Black background)
;   %01 = COLPF0 = $C4 (Forest dark green)
;   %02 = COLPF1 = $CA (Forest medium green)
;   %03 = COLPF2 = $EE (Bright yellow-green moon glow)
; ==============================================================================

TITLE_COLOR_PF0       = $C4
TITLE_COLOR_PF1       = $CA
TITLE_COLOR_PF2       = $EE
TITLE_SCROLL_SPEED    = 1     ; Step fine scroll every 1 frame (smooth 50/60 fps)

.proc title_init
    ; Turn off ANTIC DMA during setup
    lda #0
    sta SDMCTL
    sta DMACTL

    ; Set background / frame colors to Black ($00)
    sta COLOR4
    sta COLBK

    ; Set Display List pointer
    lda <dlist_title
    sta SDLSTL
    sta DLISTL
    lda >dlist_title
    sta SDLSTH
    sta DLISTH

    ; Set character set font pointer to intro_font ($24)
    lda >intro_font
    sta CHBAS
    sta CHBASE

    ; Set DLI vector for Title scroll line
    lda <dli_title_scroll
    sta VDSLST
    lda >dli_title_scroll
    sta VDSLST+1

    ; Enable VBLANK ($40) + DLI ($80) = $C0
    lda #$C0
    sta NMIEN

    ; Clear 48-byte scroll VRAM buffer with spaces ($00)
    lda #0
    ldx #TITLE_SCROLL_VRAM_LEN - 1
@   sta title_scroll_vram,x
    dex
    bpl @-

    ; Reset scroll ticker state (start at fine scroll 3)
    sta title_scroll_idx
    lda #TITLE_SCROLL_SPEED
    sta title_scroll_delay
    lda #3
    sta title_scroll_fine

    ; Require releasing fire button before accepting next press
    lda #0
    sta fire_released

    ; Check if this is the first time the title screen is shown
    lda title_first_run
    beq @show_immediate

    ; --- First run: 28-frame fade-in from black ($00) ---
    lda #0
    sta COLOR0
    sta COLPF0
    sta COLOR1
    sta COLPF1
    sta COLOR2
    sta COLPF2
    sta fade_frame
    rts

@show_immediate
    ; --- Return from Game Over: show immediately at full brightness ---
    lda #28
    sta fade_frame
    lda #TITLE_COLOR_PF0
    sta COLOR0
    sta COLPF0
    lda #TITLE_COLOR_PF1
    sta COLOR1
    sta COLPF1
    lda #TITLE_COLOR_PF2
    sta COLOR2
    sta COLPF2

    ; Start music immediately on re-entry
    jsr audio_play_title
    rts
.endp

; 8-step fade tables for 28-frame fade-in (fade_frame >> 2 = 0..7)
title_fade_c0  .byte $00, $C0, $C0, $C2, $C2, $C4, $C4, $C4
title_fade_c1  .byte $00, $C2, $C4, $C6, $C8, $CA, $CA, $CA
title_fade_c2  .byte $00, $E2, $E4, $E6, $E8, $EA, $EC, $EE

.proc title_run
    ; Enable playfield DMA (normal width 160px/40-byte playfield)
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
    lsr @
    tax
    lda title_fade_c0,x
    sta COLOR0
    sta COLPF0
    lda title_fade_c1,x
    sta COLOR1
    sta COLPF1
    lda title_fade_c2,x
    sta COLOR2
    sta COLPF2

    ; Check if fade finished on this frame
    lda fade_frame
    cmp #28
    bcc @check_input

    ; Fade-in complete: lock to full brightness, clear first_run flag, and start music
    lda #TITLE_COLOR_PF0
    sta COLOR0
    sta COLPF0
    lda #TITLE_COLOR_PF1
    sta COLOR1
    sta COLPF1
    lda #TITLE_COLOR_PF2
    sta COLOR2
    sta COLPF2
    lda #0
    sta title_first_run

    jsr audio_play_title
    jmp @check_input

@fade_completed
    ; Advance music player by 1 frame
    jsr audio_update

@check_input
    ; Update smooth scrolling ticker (once per frame)
    jsr update_title_scroll

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

    ; Reset horizontal scroll and disable DLI
    lda #0
    sta HSCROL
    lda #$40            ; VBLANK only ($40), DLI disabled
    sta NMIEN

    ; Transition to INTRO screen
    lda #STATE_INTRO
    sta game_state
    rts
.endp

; ==============================================================================
; DLI ROUTINE — Triggered on DL_BLANK1 right before ANTIC Mode 2 scroll line
; Sets fine horizontal scroll (HSCROL) and playfield colors for text line:
; In ANTIC Mode 2:
;   Foreground pixels = COLPF1 (set to current COLOR1 green / fade)
;   Background pixels = COLPF2 (set to $00 black to match black background)
; ==============================================================================
.proc dli_title_scroll
    pha                         ; Save accumulator
    sta WSYNC                   ; Wait for horizontal sync at end of blank line

    lda title_scroll_fine       ; Load fine scroll offset (3..0 color clocks)
    sta HSCROL                  ; Set ANTIC fine horizontal scroll

    lda #0
    sta COLPF2                  ; Text background: Black ($00)

    lda COLOR1                  ; Text foreground: current green (tracks fade-in!)
    sta COLPF1

    pla                         ; Restore accumulator
    rti
.endp

; ==============================================================================
; SCROLL TICKER UPDATE ROUTINE
; ANTIC Mode 2: 1 char = 4 color clocks (fine scroll 3 -> 2 -> 1 -> 0)
; When wrapping to 3, coarse shifts 48-byte VRAM left by 1 and loads next char.
; ==============================================================================
.proc update_title_scroll
    dec title_scroll_delay
    bne @done
    lda #TITLE_SCROLL_SPEED
    sta title_scroll_delay

    ; Decrement fine scroll
    lda title_scroll_fine
    sec
    sbc #1
    bpl @save_fine

    ; Wrap fine scroll: reset to 3 color clocks
    lda #3
    sta title_scroll_fine

    ; Coarse shift: shift 48-byte VRAM left by 1 position
    ldx #0
@shift_loop
    lda title_scroll_vram + 1,x
    sta title_scroll_vram,x
    inx
    cpx #TITLE_SCROLL_VRAM_LEN - 1
    bne @shift_loop

    ; Fetch next character from scroll text
    ldx title_scroll_idx
    lda title_scroll_text,x
    sta title_scroll_vram + TITLE_SCROLL_VRAM_LEN - 1

    ; Advance text index and loop if end reached
    inx
    cpx #TITLE_SCROLL_TEXT_LEN
    bcc @save_idx
    ldx #0                      ; Loop back to start
@save_idx
    stx title_scroll_idx
    rts

@save_fine
    sta title_scroll_fine
@done
    rts
.endp

; --- Scroll Ticker Variables ---
title_scroll_fine   .byte 3
title_scroll_delay  .byte TITLE_SCROLL_SPEED
title_scroll_idx    .byte 0
