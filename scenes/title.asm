; ==============================================================================
; SCENES/TITLE.ASM — Title Screen State Handler & 2bpp Text Generator
; Target: Atari 800XL / 65XE
; Mode: ANTIC Mode E (CALL) + Mode D (OF THE & WINTERMOON) + ANTIC Mode 2 Scroller (Normal width, 40 bytes/line)
; Palette:
;   %00 = COLBK  = $00 (Black background)
;   %01 = COLPF0 = $C4 (Forest dark green - right half of 2bpp glyphs)
;   %02 = COLPF1 = $CA (Forest medium green - left half of 2bpp glyphs)
;   %03 = COLPF2 = $EE (Bright yellow-green moon glow)
; ==============================================================================

TITLE_COLOR_PF0       = $C4   ; Forest dark green (COLPF0: right half of glyphs, distinct from black and COLPF1)
TITLE_COLOR_PF1       = $CA   ; Forest medium green (COLPF1: left half of glyphs)
TITLE_COLOR_PF2       = $EE   ; Bright yellow-green moon glow
TITLE_COLOR_SCROLL    = $CE   ; Green text foreground luminance/color
TITLE_COLOR_SCROLL_BG = $C0   ; Mode 2 background: Black with Green hue ($C0) to colorize text
TITLE_SCROLL_SPEED    = 2     ; Step fine scroll every 2 frames (smooth 25 fps, comfortable reading speed)

; Default color pairs for each of the three title lines (COLPF0 = right half, COLPF1 = left half)
TITLE_CALL_PF0        = TITLE_COLOR_PF0   ; $CA (Forest dark green on black)
TITLE_CALL_PF1        = TITLE_COLOR_PF1   ; $C4 (Forest medium green)
TITLE_OFTHE_PF0       = $34
TITLE_OFTHE_PF1       = $3A
TITLE_WINTER_PF0      = $74
TITLE_WINTER_PF1      = $7A

; --- Title Text Generator Constants & Buffer Equates ---
TITLE_TEXT_PITCH      = 40
TITLE_TEXT_ROWS       = 8
TITLE_TEXT_BYTES      = 320

title_text_call       = GAME_VRAM + $0000 ; $3000–$313F
title_text_of_the     = GAME_VRAM + $0140 ; $3140–$327F
title_text_wintermoon = GAME_VRAM + $0280 ; $3280–$33BF

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
    ldx #17
@clr_gtia
    sta HPOSP0,x
    dex
    bpl @clr_gtia

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

    ; Clear exactly 960 bytes of title text overlay ($3000-$33BF)
    ldx #0
@clr_text
    sta GAME_VRAM + $0000,x
    sta GAME_VRAM + $0100,x
    sta GAME_VRAM + $0200,x
    cpx #$C0
    bcs @skip_p3
    sta GAME_VRAM + $0300,x
@skip_p3
    inx
    bne @clr_text

    ; Generate title texts: CALL, OF THE, WINTERMOON
    jsr title_generate_all_texts

    ; Set background / frame colors to Black ($00)
    lda #0
    sta COLOR4
    sta COLBK

    ; Set playfield colors
    lda #TITLE_COLOR_PF0
    sta COLOR0
    sta COLPF0
    lda #TITLE_COLOR_PF1
    sta COLOR1
    sta COLPF1
    lda #TITLE_COLOR_PF2
    sta COLOR2
    sta COLPF2

    ; Set Display List pointer
    lda <dlist_title
    sta SDLSTL
    sta DLISTL
    lda >dlist_title
    sta SDLSTH
    sta DLISTH

    ; Enable playfield DMA in Normal mode ($22: 40 cols / 160px)
    lda #$22
    sta SDMCTL
    sta DMACTL

    ; Set character set font pointer to intro_font ($24)
    lda >intro_font
    sta CHBAS
    sta CHBASE

    ; Set DLI vector to first handler in chain (dli_title_color_call)
    lda <dli_title_color_call
    sta VDSLST
    lda >dli_title_color_call
    sta VDSLST+1

    ; Enable VBLANK ($40) + DLI ($80) = $C0
    lda #$C0
    sta NMIEN

    ; Start music immediately
    jsr audio_play_title
    rts
.endp

.proc title_run
    ; Maintain Normal playfield DMA ($22)
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

    ; Reset DLI vector to first DLI at the start of each frame (fallback safety)
    lda <dli_title_color_call
    sta VDSLST
    lda >dli_title_color_call
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
; TITLE ROW COLORS TABLE (Runtime-writable in RAM)
; Layout: 2 bytes per row (COLPF0 = right half, COLPF1 = left half)
; ==============================================================================
title_row_colors:
    .byte TITLE_CALL_PF0,   TITLE_CALL_PF1
    .byte TITLE_OFTHE_PF0,  TITLE_OFTHE_PF1
    .byte TITLE_WINTER_PF0, TITLE_WINTER_PF1

; ==============================================================================
; DLI ROUTINES — Title Line Colors (Self-Resetting Chain)
; Handlers trigger during DL_BLANK8 lines preceding each title line.
; No graphics are rendered during blank scanlines, making color updates invisible
; without requiring WSYNC synchronization (~41 CPU cycles per handler).
; ==============================================================================
.proc dli_title_color_call
    pha                         ; Save accumulator                    ; [3]
    lda title_row_colors + 0    ; COLPF0 for CALL (right half)        ; [4]
    sta COLPF0                  ;                                     ; [4]
    lda title_row_colors + 1    ; COLPF1 for CALL (left half)         ; [4]
    sta COLPF1                  ;                                     ; [4]
    lda #<dli_title_color_of_the; Chain next DLI handler              ; [2]
    sta VDSLST                  ;                                     ; [4]
    lda #>dli_title_color_of_the;                                     ; [2]
    sta VDSLST+1                ;                                     ; [4]
    pla                         ; Restore accumulator                 ; [4]
    rti                         ; Return from interrupt               ; [6]
.endp

.proc dli_title_color_of_the
    pha                         ; Save accumulator                    ; [3]
    lda title_row_colors + 2    ; COLPF0 for OF THE (right half)      ; [4]
    sta COLPF0                  ;                                     ; [4]
    lda title_row_colors + 3    ; COLPF1 for OF THE (left half)       ; [4]
    sta COLPF1                  ;                                     ; [4]
    lda #<dli_title_color_winter; Chain next DLI handler              ; [2]
    sta VDSLST                  ;                                     ; [4]
    lda #>dli_title_color_winter;                                     ; [2]
    sta VDSLST+1                ;                                     ; [4]
    pla                         ; Restore accumulator                 ; [4]
    rti                         ; Return from interrupt               ; [6]
.endp

.proc dli_title_color_winter
    pha                         ; Save accumulator                    ; [3]
    lda title_row_colors + 4    ; COLPF0 for WINTERMOON (right half)  ; [4]
    sta COLPF0                  ;                                     ; [4]
    lda title_row_colors + 5    ; COLPF1 for WINTERMOON (left half)   ; [4]
    sta COLPF1                  ;                                     ; [4]
    lda #<dli_title_scroll      ; Chain scroll DLI handler            ; [2]
    sta VDSLST                  ;                                     ; [4]
    lda #>dli_title_scroll      ;                                     ; [2]
    sta VDSLST+1                ;                                     ; [4]
    pla                         ; Restore accumulator                 ; [4]
    rti                         ; Return from interrupt               ; [6]
.endp

; ==============================================================================
; DLI ROUTINE — Triggered on DL_BLANK1 before ANTIC Mode 2 scroll line
; 1. Waits for buffer blank scanline, sets fine horizontal scroll (HSCROL),
;    and sets text foreground color (COLPF1).
; 2. Renders 8-scanline rainbow background gradient ($C0, $C2, $C4, $C6, $C6, $C4, $C2, $C0)
;    into COLPF2 synchronized with WSYNC.
; 3. On post-scroll blank line, resets HSCROL and restores Mode D/E playfield colors.
; 4. Self-resets VDSLST back to dli_title_color_call for the next frame.
; ==============================================================================
.proc dli_title_scroll
    pha                         ; Save accumulator                    ; [3]
    sta WSYNC                   ; Wait for end of DLI blank line      ; [4]

    ; --- Buffer Blank Scanline ---
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

    ; --- Post-Scroll Blank Scanline: Restore Mode D/E State ---
    lda #0                      ; Reset fine horizontal scroll        ; [2]
    sta HSCROL                  ;                                     ; [4]
    lda #TITLE_COLOR_PF1        ; Restore Mode D/E PF1 color          ; [2]
    sta COLPF1                  ;                                     ; [4]
    lda #TITLE_COLOR_PF2        ; Restore Mode D/E PF2 color          ; [2]
    sta COLPF2                  ;                                     ; [4]

    ; Reset DLI chain back to first handler (CALL colors) for next frame
    lda #<dli_title_color_call  ;                                     ; [2]
    sta VDSLST                  ;                                     ; [4]
    lda #>dli_title_color_call  ;                                     ; [2]
    sta VDSLST+1                ;                                     ; [4]

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

; ==============================================================================
; TITLE TEXT GENERATOR TABLES & PROCEDURES
; ==============================================================================
; Screen codes, lengths, and centering offsets compiled from texts/title.txt
    icl 'gen/title_text_data.asm'

; 16-byte nibble-to-2bpp lookup table for high nibble (bits 7-4, left 4 pixels: 0 -> 00, 1 -> 10 = COLPF1)
title_text_lut:
title_text_lut_hi:
    .byte $00,$02,$08,$0A,$20,$22,$28,$2A
    .byte $80,$82,$88,$8A,$A0,$A2,$A8,$AA

; 16-byte nibble-to-2bpp lookup table for low nibble (bits 3-0, right 4 pixels: 0 -> 00, 1 -> 01 = COLPF0)
title_text_lut_lo:
    .byte $00,$01,$04,$05,$10,$11,$14,$15
    .byte $40,$41,$44,$45,$50,$51,$54,$55

; Row offset lookup tables for pitch = 40 (rows 0..7)
title_text_row_lo:
    .byte <0, <40, <80, <120, <160, <200, <240, <280
title_text_row_hi:
    .byte >0, >40, >80, >120, >160, >200, >240, >280

; Descriptor tables for title_generate_all_texts
title_text_ptrs_text_lo:
    .byte <title_text_call_codes, <title_text_of_the_codes, <title_text_wintermoon_codes
title_text_ptrs_text_hi:
    .byte >title_text_call_codes, >title_text_of_the_codes, >title_text_wintermoon_codes
title_text_ptrs_dst_lo:
    .byte <title_text_call, <title_text_of_the, <title_text_wintermoon
title_text_ptrs_dst_hi:
    .byte >title_text_call, >title_text_of_the, >title_text_wintermoon
title_text_lens:
    .byte TITLE_CALL_LEN, TITLE_OF_THE_LEN, TITLE_WINTERMOON_LEN
title_text_offsets:
    .byte TITLE_CALL_OFFSET, TITLE_OF_THE_OFFSET, TITLE_WINTERMOON_OFFSET

title_gen_idx .byte 0

.proc title_generate_all_texts
    lda <intro_font
    sta title_gen_charset
    lda >intro_font
    sta title_gen_charset+1

    lda #0
    sta title_gen_idx
@loop
    ldy title_gen_idx
    lda title_text_ptrs_text_lo,y
    sta title_gen_text
    lda title_text_ptrs_text_hi,y
    sta title_gen_text+1

    lda title_text_ptrs_dst_lo,y
    sta title_gen_dst
    lda title_text_ptrs_dst_hi,y
    sta title_gen_dst+1

    lda title_text_lens,y
    sta title_gen_len
    lda title_text_offsets,y
    sta title_gen_x

    jsr title_text_generate

    inc title_gen_idx
    lda title_gen_idx
    cmp #3
    bne @loop
    rts
.endp

; ==============================================================================
; TITLE_TEXT_GENERATE — Reusable 2bpp Text Generator
; Inputs:
;   title_gen_charset ($DC, 2B): Pointer to 1 KB 1bpp font (intro_font)
;   title_gen_text    ($DE, 2B): Pointer to screen codes text
;   title_gen_dst     ($E0, 2B): Pointer to destination buffer (320 bytes, 8 rows x 40 B)
;   title_gen_len     ($E2, 1B): Text length in characters (1..20)
;   title_gen_x       ($E3, 1B): Horizontal offset in bytes from row start (0..38)
; Outputs:
;   Carry: 0 (CLC) on success, 1 (SEC) on invalid parameters (no memory modified)
; Clobbers:
;   A, X, Y, zp_ptr_src ($83-$84), zp_ptr_dst ($85-$86), zp_temp_a/x/y ($80-$82)
; ==============================================================================
.proc title_text_generate
    ; --- Parameter Validation ---
    ; 1. length >= 1
    lda title_gen_len
    beq @invalid
    ; 2. length <= 20
    cmp #21
    bcs @invalid
    ; 3. x_offset < 40
    lda title_gen_x
    cmp #40
    bcs @invalid
    ; 4. x_offset + 2 * length <= 40 (prevent 8-bit overflow by checking len <= 20 first)
    lda title_gen_len
    asl                     ; 2 * length (max 40)
    clc
    adc title_gen_x         ; x_offset + 2 * length (max 79)
    cmp #41                 ; must be <= 40
    bcc @valid

@invalid
    sec
    rts

@valid
    ; --- Generation Loop ---
    lda #0
    sta zp_temp_a           ; i = 0 (char index)

@char_loop
    ; col_offset = title_gen_x + i * 2
    lda zp_temp_a
    asl
    clc
    adc title_gen_x
    sta zp_temp_y           ; zp_temp_y = col_offset

    ; Read char code: c = text[i]
    ldy zp_temp_a
    lda (title_gen_text),y

    ; Compute glyph address: charset + c * 8
    sta zp_ptr_src
    lda #0
    sta zp_ptr_src+1
    asl zp_ptr_src
    rol zp_ptr_src+1
    asl zp_ptr_src
    rol zp_ptr_src+1
    asl zp_ptr_src
    rol zp_ptr_src+1

    clc
    lda zp_ptr_src
    adc title_gen_charset
    sta zp_ptr_src
    lda zp_ptr_src+1
    adc title_gen_charset+1
    sta zp_ptr_src+1

    ; Row loop: r = 0..7
    lda #0
    sta zp_temp_x           ; r = 0

@row_loop
    ; zp_ptr_dst = title_gen_dst + row_offset[r]
    ldx zp_temp_x
    clc
    lda title_gen_dst
    adc title_text_row_lo,x
    sta zp_ptr_dst
    lda title_gen_dst+1
    adc title_text_row_hi,x
    sta zp_ptr_dst+1

    ; Read glyph byte for row r: b = glyph[r]
    ldy zp_temp_x
    lda (zp_ptr_src),y

    ; Convert high nibble (bits 7-4) -> left 2bpp byte (1 -> 10, COLPF1)
    tax
    lsr
    lsr
    lsr
    lsr
    tay
    lda title_text_lut_hi,y
    ldy zp_temp_y
    sta (zp_ptr_dst),y

    ; Convert low nibble (bits 3-0) -> right 2bpp byte (1 -> 01, COLPF0)
    txa
    and #$0F
    tay
    lda title_text_lut_lo,y
    ldy zp_temp_y
    iny
    sta (zp_ptr_dst),y

    ; Next row
    inc zp_temp_x
    lda zp_temp_x
    cmp #8
    bne @row_loop

    ; Next character
    inc zp_temp_a
    lda zp_temp_a
    cmp title_gen_len
    bne @char_loop

    clc
    rts
.endp
