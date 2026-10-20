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
TITLE_COLOR_SCROLL    = $CE   ; Green text foreground luminance/color
TITLE_COLOR_SCROLL_BG = $C0   ; Mode 2 background: Black with Green hue ($C0) to colorize text
TITLE_SCROLL_SPEED    = 2     ; Step fine scroll every 2 frames (smooth 25 fps, comfortable reading speed)

.proc title_init
    ; Turn off ANTIC DMA during setup
    lda #0
    sta SDMCTL
    sta DMACTL

    ; Reset game progression, lives, and CDs for new playthrough
    sta active_scene_id
    jsr status_line_reset

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

    ; Show immediately at full brightness (no fade-in)
    lda #TITLE_COLOR_PF0
    sta COLOR0
    sta COLPF0
    lda #TITLE_COLOR_PF1
    sta COLOR1
    sta COLPF1
    lda #TITLE_COLOR_PF2
    sta COLOR2
    sta COLPF2

    ; Enable playfield DMA in Narrow mode ($21: 128px Mode D title image)
    lda #$21
    sta SDMCTL
    sta DMACTL

    ; Start music immediately
    jsr audio_play_title
    rts
.endp

.proc title_run
    ; Maintain Narrow playfield DMA ($21)
    lda #$21
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

    ; Reset DLI vector to first DLI at the start of each frame
    lda <dli_title_scroll
    sta VDSLST
    lda >dli_title_scroll
    sta VDSLST+1

    ; Advance music player by 1 frame
    jsr audio_update

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
; DLI ROUTINE — Triggered on DL_BLANK1 before ANTIC Mode 2 scroll line
; 1. Waits for buffer blank scanline, switches ANTIC to Normal playfield ($22),
;    sets fine horizontal scroll (HSCROL), and sets text foreground color (COLPF1).
; 2. Renders 8-scanline rainbow background gradient ($C0, $C2, $C4, $C6, $C6, $C4, $C2, $C0)
;    into COLPF2 synchronized with WSYNC.
; 3. On post-scroll blank line, restores Narrow playfield ($21), resets HSCROL,
;    and restores Mode D playfield colors.
; ==============================================================================
.proc dli_title_scroll
    pha                         ; Save accumulator                    ; [3]
    sta WSYNC                   ; Wait for end of DLI blank line      ; [4]

    ; --- Buffer Blank Scanline ---
    lda #$22                    ; Normal playfield (40 cols / 48 fetch) ; [2]
    sta DMACTL                  ;                                     ; [4]
    lda title_scroll_fine       ; Fine scroll offset (3..0 clocks)    ; [3]
    sta HSCROL                  ;                                     ; [4]
    lda #TITLE_COLOR_SCROLL     ; Text foreground color               ; [2]
    sta COLPF1                  ;                                     ; [4]

    ; Wait for end of buffer line -> start of Mode 2 Scanline 0
    sta WSYNC                   ;                                     ; [4]

    ; --- 8-Scanline Rainbow Gradient on COLPF2 ---
    ; Scanline 0: $C0
    lda #$C0                    ;                                     ; [2]
    sta COLPF2                  ; Background: $C0                     ; [4]
    sta WSYNC                   ; Wait for Scanline 1                 ; [4]

    ; Scanline 1: $C2
    lda #$C2                    ;                                     ; [2]
    sta COLPF2                  ; Background: $C2                     ; [4]
    sta WSYNC                   ; Wait for Scanline 2                 ; [4]

    ; Scanline 2: $C4
    lda #$C4                    ;                                     ; [2]
    sta COLPF2                  ; Background: $C4                     ; [4]
    sta WSYNC                   ; Wait for Scanline 3                 ; [4]

    ; Scanline 3: $C6
    lda #$C6                    ;                                     ; [2]
    sta COLPF2                  ; Background: $C6                     ; [4]
    sta WSYNC                   ; Wait for Scanline 4                 ; [4]

    ; Scanline 4: $C6
    lda #$C6                    ;                                     ; [2]
    sta COLPF2                  ; Background: $C6                     ; [4]
    sta WSYNC                   ; Wait for Scanline 5                 ; [4]

    ; Scanline 5: $C4
    lda #$C4                    ;                                     ; [2]
    sta COLPF2                  ; Background: $C4                     ; [4]
    sta WSYNC                   ; Wait for Scanline 6                 ; [4]

    ; Scanline 6: $C2
    lda #$C2                    ;                                     ; [2]
    sta COLPF2                  ; Background: $C2                     ; [4]
    sta WSYNC                   ; Wait for Scanline 7                 ; [4]

    ; Scanline 7: $C0
    lda #$C0                    ;                                     ; [2]
    sta COLPF2                  ; Background: $C0                     ; [4]
    sta WSYNC                   ; Wait for post-scroll blank line     ; [4]

    ; --- Post-Scroll Blank Scanline: Restore Mode D State ---
    lda #$21                    ; Restore Narrow playfield (128 px)   ; [2]
    sta DMACTL                  ;                                     ; [4]
    lda #0                      ; Reset fine horizontal scroll        ; [2]
    sta HSCROL                  ;                                     ; [4]
    lda #TITLE_COLOR_PF1        ; Restore Mode D PF1 color            ; [2]
    sta COLPF1                  ;                                     ; [4]
    lda #TITLE_COLOR_PF2        ; Restore Mode D PF2 color            ; [2]
    sta COLPF2                  ;                                     ; [4]

    pla                         ; Restore accumulator                 ; [4]
    rti                         ; Return from interrupt               ; [6]
.endp

.proc dli_title_restore
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
