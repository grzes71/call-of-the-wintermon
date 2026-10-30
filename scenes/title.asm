; ==============================================================================
; SCENES/TITLE.ASM — Title Screen State Handler & 2bpp Text Generator
; Target: Atari 800XL / 65XE
; Mode: ANTIC Mode E (CALL) + Mode D (OF THE & WINTERMOON) + ANTIC Mode 2 Vertical Scroller (Normal width, 40 bytes/line)
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
TITLE_BELOW_PF1       = $00   ; Black COLPF1 below vertical scroll window
TITLE_BELOW_PF2       = $00   ; Black COLPF2 below vertical scroll window

; --- Title Vertical Scroll Window Constants & Geometry ---
; ANTIC Mode 2 VSCROL geometry:
; 1 line with DL_VSCROL ($20) + 1 buffer line without DL_VSCROL ($00).
; In ANTIC, a vertical scroll region starts on the first line with DL_VSCROL set
; (rendered from scanline VSCROL to 7, height = 8 - VSCROL), and is terminated by
; the first line WITHOUT DL_VSCROL (buffer line, rendered from scanline 0 to VSCROL,
; height = VSCROL + 1). Total window height is strictly constant: (8 - V) + (V + 1) = 9 scanlines.
; Buffer has 3 lines of 40 bytes (L0, L1, L2).
; p (0..15) = 8*k + V (k = p >> 3, V = p & 7):
;   LMS address = title_vs_buf + 40 * k
;   VSCROL      = V
; Window displays rows p..p+8 of buffer:
;   p = 7:  rows 7..15  -> L0 and L1 spaces (hidden)
;   p = 8:  rows 8..16  -> row 16 (L2 row 0) appears at bottom scanline 8 of window
;   p = 15: rows 15..23 -> message fully visible in bottom 8 scanlines of window
TITLE_VS_HIDDEN           = 7
TITLE_VS_SHOWN            = 15

TITLE_FPS                 = 50      ; PAL (50 Hz); 60 for NTSC
TITLE_VS_FRAMES_PER_STEP  = 3       ; Frames per 1 scanline step (24 frames total per movement)
TITLE_VS_HOLD_FRAMES      = 4 * TITLE_FPS   ; 200 frames (4 seconds)
TITLE_VS_PAUSE_FRAMES     = 2 * TITLE_FPS   ; 100 frames (2 seconds)

; 8-bit timer bounds assertions
.if TITLE_VS_HOLD_FRAMES > 255
    .error "TITLE_VS_HOLD_FRAMES exceeds 8-bit limit (255)"
.endif
.if TITLE_VS_PAUSE_FRAMES > 255
    .error "TITLE_VS_PAUSE_FRAMES exceeds 8-bit limit (255)"
.endif

TITLE_VS_STATE_IN         = 0
TITLE_VS_STATE_HOLD       = 1
TITLE_VS_STATE_OUT        = 2
TITLE_VS_STATE_PAUSE      = 3

; Default color triples for each of the three title lines (COLPF0 = right 2 cols, COLPF1 = left 2 cols, COLPF2 = center 4 cols)
TITLE_COLOR_PF2_TEXT  = $EE   ; Bright yellow-green moon glow (COLPF2: center 4 pixels of glyphs)

TITLE_CALL_PF0        = $18        
TITLE_CALL_PF1        = $1C     
TITLE_CALL_PF2        = $1A  

TITLE_OFTHE_PF0       = $38                    
TITLE_OFTHE_PF1       = $3C                   
TITLE_OFTHE_PF2       = $3A   

TITLE_WINTER_PF0      = $78                   
TITLE_WINTER_PF1      = $7C                  
TITLE_WINTER_PF2      = $7A

TITLE_LOGO_PF0        = $08   ; COLPF0
TITLE_LOGO_PF1        = $0c   ; COLPF1
TITLE_LOGO_PF2        = $0a   ; COLPF2

; --- Title Text Generator Constants & Buffer Equates ---
TITLE_TEXT_PITCH      = 40
TITLE_TEXT_ROWS       = 8
TITLE_TEXT_BYTES      = 320

TITLE_LOGO_OFFSET     = 15    ; (40 - 5 * 2) / 2
TITLE_LOGO_LINE_BYTES = 320   ; 8 rows * 40 bytes per character row
TITLE_LOGO_BYTES      = 1280  ; 4 * 320 bytes

title_text_call       = GAME_VRAM + $0000 ; $3000–$313F
title_text_of_the     = GAME_VRAM + $0140 ; $3140–$327F
title_text_wintermoon = GAME_VRAM + $0280 ; $3280–$33BF
title_text_logo       = GAME_VRAM + $03C0 ; $33C0–$38BF (1,280 bytes)

; Compile-time bounds assertions
.if (title_text_logo + TITLE_LOGO_BYTES - 1) > $38BF
    .error "title_text_logo exceeds $38BF"
.endif


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

    ; Clear active PMG memory buffer ($6B00-$6FFF, 1,280 bytes: Missiles + P0..P3)
    tax
@clr_pmg
    sta PMG_MISSILES,x
    sta PMG_PLAYER0,x
    sta PMG_PLAYER1,x
    sta PMG_PLAYER2,x
    sta PMG_PLAYER3,x
    inx
    bne @clr_pmg

    ; Clear 120-byte vertical scroll buffer with spaces ($00: L0, L1, L2)
    ldx #TITLE_VS_BUF_LEN - 1
@clr_vs
    sta title_vs_buf,x
    dex
    bpl @clr_vs

    ; Initialize vertical scroll state machine
    lda #TITLE_VS_HIDDEN
    sta title_vs_pos
    lda #TITLE_VS_STATE_IN      ; 0
    sta title_vs_state
    sta title_vs_index
    lda #TITLE_VS_FRAMES_PER_STEP
    sta title_vs_timer

    ; Load first message into L2 (title_vs_buf + 80)
    jsr title_vs_load_message

    ; Synchronize hardware VSCROL and DL LMS address for p = TITLE_VS_HIDDEN (7)
    lda #7
    sta VSCROL
    lda #<title_vs_buf
    sta title_dl_vs_addr
    lda #>title_vs_buf
    sta title_dl_vs_addr+1

    ; Require releasing fire button before accepting next press
    lda #0
    sta fire_released

    ; Clear exactly 2,240 bytes of title text overlay & logo ($3000-$38BF)
    ldx #0
@clr_text
    sta GAME_VRAM + $0000,x
    sta GAME_VRAM + $0100,x
    sta GAME_VRAM + $0200,x
    sta GAME_VRAM + $0300,x
    sta GAME_VRAM + $0400,x
    sta GAME_VRAM + $0500,x
    sta GAME_VRAM + $0600,x
    sta GAME_VRAM + $0700,x
    cpx #$C0
    bcs @skip_p8
    sta GAME_VRAM + $0800,x
@skip_p8
    inx
    bne @clr_text

    ; Generate title texts: CALL, OF THE, WINTERMOON
    jsr title_generate_all_texts

    ; Generate Atari logo (4 lines x 5 characters, ANTIC Mode D)
    jsr title_generate_logo

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

    ; Update smooth vertical scroll state machine (once per frame)
    jsr update_title_vscroll

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

    ; Reset horizontal and vertical scroll and disable DLI
    lda #0
    sta HSCROL
    sta VSCROL
    lda #$40            ; VBLANK only ($40), DLI disabled
    sta NMIEN

    ; Transition to INTRO screen
    lda #STATE_INTRO
    sta game_state
    rts
.endp

; ==============================================================================
; TITLE ROW COLORS TABLE (Runtime-writable in RAM)
; Layout: 3 bytes per row (COLPF0 = right 2 cols, COLPF1 = left 2 cols, COLPF2 = center 4 cols)
; ==============================================================================
title_row_colors:
    .byte TITLE_CALL_PF0,   TITLE_CALL_PF1,   TITLE_CALL_PF2
    .byte TITLE_OFTHE_PF0,  TITLE_OFTHE_PF1,  TITLE_OFTHE_PF2
    .byte TITLE_WINTER_PF0, TITLE_WINTER_PF1, TITLE_WINTER_PF2
    .byte TITLE_LOGO_PF0,   TITLE_LOGO_PF1,   TITLE_LOGO_PF2

; ==============================================================================
; DLI ROUTINES — Title Line Colors (Self-Resetting Chain)
; Handlers trigger during DL_BLANK8 lines preceding each title line.
; No graphics are rendered during blank scanlines, making color updates invisible
; without requiring WSYNC synchronization (~49 CPU cycles per handler).
; ==============================================================================
.proc dli_title_color_call
    pha                         ; Save accumulator                    ; [3]
    lda title_row_colors + 0    ; COLPF0 for CALL (right 2 cols)      ; [4]
    sta COLPF0                  ;                                     ; [4]
    lda title_row_colors + 1    ; COLPF1 for CALL (left 2 cols)       ; [4]
    sta COLPF1                  ;                                     ; [4]
    lda title_row_colors + 2    ; COLPF2 for CALL (center 4 cols)     ; [4]
    sta COLPF2                  ;                                     ; [4]
    lda #<dli_title_color_of_the; Chain next DLI handler              ; [2]
    sta VDSLST                  ;                                     ; [4]
    lda #>dli_title_color_of_the;                                     ; [2]
    sta VDSLST+1                ;                                     ; [4]
    pla                         ; Restore accumulator                 ; [4]
    rti                         ; Return from interrupt               ; [6]
.endp

.proc dli_title_color_of_the
    pha                         ; Save accumulator                    ; [3]
    lda title_row_colors + 3    ; COLPF0 for OF THE (right 2 cols)    ; [4]
    sta COLPF0                  ;                                     ; [4]
    lda title_row_colors + 4    ; COLPF1 for OF THE (left 2 cols)     ; [4]
    sta COLPF1                  ;                                     ; [4]
    lda title_row_colors + 5    ; COLPF2 for OF THE (center 4 cols)   ; [4]
    sta COLPF2                  ;                                     ; [4]
    lda #<dli_title_color_winter; Chain next DLI handler              ; [2]
    sta VDSLST                  ;                                     ; [4]
    lda #>dli_title_color_winter;                                     ; [2]
    sta VDSLST+1                ;                                     ; [4]
    pla                         ; Restore accumulator                 ; [4]
    rti                         ; Return from interrupt               ; [6]
.endp

.proc dli_title_color_winter
    pha                         ; Save accumulator                    ; [3]
    lda title_row_colors + 6    ; COLPF0 for WINTERMOON (right 2 cols); [4]
    sta COLPF0                  ;                                     ; [4]
    lda title_row_colors + 7    ; COLPF1 for WINTERMOON (left 2 cols) ; [4]
    sta COLPF1                  ;                                     ; [4]
    lda title_row_colors + 8    ; COLPF2 for WINTERMOON (center 4 cols); [4]
    sta COLPF2                  ;                                     ; [4]
    lda #<dli_title_color_logo  ; Chain logo DLI handler              ; [2]
    sta VDSLST                  ;                                     ; [4]
    lda #>dli_title_color_logo  ;                                     ; [2]
    sta VDSLST+1                ;                                     ; [4]
    pla                         ; Restore accumulator                 ; [4]
    rti                         ; Return from interrupt               ; [6]
.endp

.proc dli_title_color_logo
    pha                         ; Save accumulator                    ; [3]
    lda title_row_colors + 9    ; COLPF0 for LOGO (right 2 cols)      ; [4]
    sta COLPF0                  ;                                     ; [4]
    lda title_row_colors + 10   ; COLPF1 for LOGO (left 2 cols)       ; [4]
    sta COLPF1                  ;                                     ; [4]
    lda title_row_colors + 11   ; COLPF2 for LOGO (center 4 cols)     ; [4]
    sta COLPF2                  ;                                     ; [4]
    lda #<dli_title_scroll      ; Chain scroll DLI handler            ; [2]
    sta VDSLST                  ;                                     ; [4]
    lda #>dli_title_scroll      ;                                     ; [2]
    sta VDSLST+1                ;                                     ; [4]
    pla                         ; Restore accumulator                 ; [4]
    rti                         ; Return from interrupt               ; [6]
.endp

; ==============================================================================
; DLI ROUTINE — Triggered on DL_BLANK1 before ANTIC Mode 2 scroll window
; 1. Waits for buffer blank scanline and sets text foreground color (COLPF1).
; 2. Renders 9-scanline rainbow background gradient ($C0, $C2, $C4, $C6, $C6, $C4, $C2, $C0, $C0)
;    into COLPF2 synchronized with WSYNC. Scanline 8 repeats $C0 to smoothly extend gradient.
; 3. On post-scroll blank line, restores Mode D/E playfield colors (COLPF1 and COLPF2).
; 4. Self-resets VDSLST back to dli_title_color_call for the next frame.
; ==============================================================================
.proc dli_title_scroll
    pha                         ; Save accumulator                    ; [3]
    sta WSYNC                   ; Wait for end of DLI blank line      ; [4]

    ; --- Buffer Blank Scanline ---
    lda #TITLE_COLOR_SCROLL     ; Text foreground color               ; [2]
    sta COLPF1                  ;                                     ; [4]

    ; Wait for end of buffer line -> start of Mode 2 Scanline 0
    sta WSYNC                   ;                                     ; [4]

    ; --- 9-Scanline Rainbow Gradient on COLPF2 ---
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
    sta WSYNC                   ; Wait for Scanline 8                 ; [4]

    ; Scanline 8: $C0
    lda #$C0                    ;                                     ; [2]
    sta COLPF2                  ; Background: $C0                     ; [4]
    sta WSYNC                   ; Wait for post-scroll blank line     ; [4]

    ; --- Post-Scroll Blank Scanline: Set Below-Window Colors to Black ---
    lda #TITLE_BELOW_PF1        ; Set COLPF1 below window (Black)     ; [2]
    sta COLPF1                  ;                                     ; [4]
    lda #TITLE_BELOW_PF2        ; Set COLPF2 below window (Black)     ; [2]
    sta COLPF2                  ;                                     ; [4]
    sta COLBK                   ; Ensure COLBK is Black               ; [4]

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
; TITLE VERTICAL SCROLL STATE MACHINE UPDATE (Once per frame in title_run)
; State flow:
;   1. IN:    p steps from 7 to 15 every TITLE_VS_FRAMES_PER_STEP frames (24 frames)
;             -> transitions to HOLD
;   2. HOLD:  p = 15 for TITLE_VS_HOLD_FRAMES frames (200 frames / 4 sec)
;             -> transitions to OUT
;   3. OUT:   p steps from 15 to 7 every TITLE_VS_FRAMES_PER_STEP frames (24 frames)
;             -> when reaching 7, loads next message into L2, transitions to PAUSE
;   4. PAUSE: p = 7 for TITLE_VS_PAUSE_FRAMES frames (100 frames / 2 sec)
;             -> transitions to IN
;
; In EVERY frame, updates:
;   - VSCROL = p & 7
;   - title_dl_vs_addr = title_vs_buf (if p < 8) or title_vs_buf + 40 (if p >= 8)
; ==============================================================================
.proc update_title_vscroll
    lda title_vs_state
    cmp #TITLE_VS_STATE_IN
    bne @check_hold
    jmp @do_in
@check_hold
    cmp #TITLE_VS_STATE_HOLD
    bne @check_out
    jmp @do_hold
@check_out
    cmp #TITLE_VS_STATE_OUT
    bne @check_pause
    jmp @do_out
@check_pause
    jmp @do_pause

; --- Faza IN ---
@do_in
    dec title_vs_timer
    bne @apply_hw
    lda #TITLE_VS_FRAMES_PER_STEP
    sta title_vs_timer

    inc title_vs_pos
    lda title_vs_pos
    cmp #TITLE_VS_SHOWN
    bcc @apply_hw

    ; Reached TITLE_VS_SHOWN (15) -> transition to HOLD
    lda #TITLE_VS_SHOWN
    sta title_vs_pos
    lda #TITLE_VS_STATE_HOLD
    sta title_vs_state
    lda #TITLE_VS_HOLD_FRAMES
    sta title_vs_timer
    jmp @apply_hw

; --- Faza HOLD ---
@do_hold
    dec title_vs_timer
    bne @apply_hw

    ; HOLD expired -> transition to OUT
    lda #TITLE_VS_STATE_OUT
    sta title_vs_state
    lda #TITLE_VS_FRAMES_PER_STEP
    sta title_vs_timer
    jmp @apply_hw

; --- Faza OUT ---
@do_out
    dec title_vs_timer
    bne @apply_hw
    lda #TITLE_VS_FRAMES_PER_STEP
    sta title_vs_timer

    dec title_vs_pos
    lda title_vs_pos
    cmp #TITLE_VS_HIDDEN
    bne @check_hidden_out
    jmp @reached_hidden
@check_hidden_out
    bcs @apply_hw

@reached_hidden
    ; Reached TITLE_VS_HIDDEN (7) -> transition to PAUSE
    lda #TITLE_VS_HIDDEN
    sta title_vs_pos
    lda #TITLE_VS_STATE_PAUSE
    sta title_vs_state
    lda #TITLE_VS_PAUSE_FRAMES
    sta title_vs_timer

    ; Advance message index and load next message while hidden (p = 7)
    inc title_vs_index
    lda title_vs_index
    cmp #TITLE_VS_COUNT
    bcc @idx_ok
    lda #0
    sta title_vs_index
@idx_ok
    jsr title_vs_load_message
    jmp @apply_hw

; --- Faza PAUSE ---
@do_pause
    dec title_vs_timer
    bne @apply_hw

    ; PAUSE expired -> transition to IN
    lda #TITLE_VS_STATE_IN
    sta title_vs_state
    lda #TITLE_VS_FRAMES_PER_STEP
    sta title_vs_timer
    ; Fallthrough to apply_hw

; --- Apply hardware VSCROL & DL LMS address atomically in the same frame ---
@apply_hw
    lda title_vs_pos
    and #$07
    sta VSCROL

    lda title_vs_pos
    cmp #8
    bcc @lms_k0
    ; k = 1: p >= 8 -> LMS = title_vs_buf + 40
    lda #<(title_vs_buf + 40)
    sta title_dl_vs_addr
    lda #>(title_vs_buf + 40)
    sta title_dl_vs_addr+1
    rts

@lms_k0
    ; k = 0: p < 8 -> LMS = title_vs_buf
    lda #<title_vs_buf
    sta title_dl_vs_addr
    lda #>title_vs_buf
    sta title_dl_vs_addr+1
    rts
.endp

; ==============================================================================
; LOAD MESSAGE INTO L2 BUFFER (title_vs_buf + 80)
; Loads 40 bytes from title_vs_lines at title_vs_index
; Uses zp_ptr_src ($83-$84)
; ==============================================================================
.proc title_vs_load_message
    ldx title_vs_index
    lda title_vs_lines_ptr_lo,x
    sta title_vs_ptr
    sta zp_ptr_src
    lda title_vs_lines_ptr_hi,x
    sta title_vs_ptr+1
    sta zp_ptr_src+1

    ldy #39
@copy_loop
    lda (zp_ptr_src),y
    sta title_vs_buf + 80,y
    dey
    bpl @copy_loop
    rts
.endp

; --- Title Vertical Scroll State Variables ---
title_vs_pos    .byte TITLE_VS_HIDDEN
title_vs_state  .byte TITLE_VS_STATE_IN
title_vs_timer  .byte 0
title_vs_index  .byte 0
title_vs_ptr    .word 0

; ==============================================================================
; TITLE TEXT GENERATOR TABLES & PROCEDURES
; ==============================================================================
; Screen codes, lengths, and centering offsets compiled from texts/title.txt
    icl 'gen/title_text_data.asm'

; 16-byte nibble-to-2bpp lookup table for high nibble (bits 7-4: b7,b6 -> 10 = COLPF1, b5,b4 -> 11 = COLPF2)
title_text_lut:
title_text_lut_hi:
    .byte $00,$03,$0C,$0F,$20,$23,$2C,$2F
    .byte $80,$83,$8C,$8F,$A0,$A3,$AC,$AF

; 16-byte nibble-to-2bpp lookup table for low nibble (bits 3-0: b3,b2 -> 11 = COLPF2, b1,b0 -> 01 = COLPF0)
title_text_lut_lo:
    .byte $00,$01,$04,$05,$30,$31,$34,$35
    .byte $C0,$C1,$C4,$C5,$F0,$F1,$F4,$F5

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
; ATARI LOGO DATA & GENERATOR
; 4 lines x 5 characters from intro_font (screen codes 0..127)
; Centered at x_offset = 15 (10 bytes width across 40-byte row)
; ==============================================================================
    icl 'gen/title_logo.inc'
title_logo_codes_end:

; Compile-time bounds assertions for logo
.if (TITLE_LOGO_COLS < 1) || (TITLE_LOGO_COLS > 20)
    .error "TITLE_LOGO_COLS must be between 1 and 20"
.endif
.if (TITLE_LOGO_OFFSET + 2 * TITLE_LOGO_COLS > 40)
    .error "TITLE_LOGO_OFFSET + 2 * TITLE_LOGO_COLS exceeds 40"
.endif
.if (title_logo_codes_end - title_logo_codes) != (TITLE_LOGO_COLS * TITLE_LOGO_LINES)
    .error "title_logo_codes size must equal TITLE_LOGO_COLS * TITLE_LOGO_LINES"
.endif

; Pointer tables for title_generate_logo
title_logo_ptrs_text_lo:
    .byte <(title_logo_codes + 0 * TITLE_LOGO_COLS)
    .byte <(title_logo_codes + 1 * TITLE_LOGO_COLS)
    .byte <(title_logo_codes + 2 * TITLE_LOGO_COLS)
    .byte <(title_logo_codes + 3 * TITLE_LOGO_COLS)
title_logo_ptrs_text_hi:
    .byte >(title_logo_codes + 0 * TITLE_LOGO_COLS)
    .byte >(title_logo_codes + 1 * TITLE_LOGO_COLS)
    .byte >(title_logo_codes + 2 * TITLE_LOGO_COLS)
    .byte >(title_logo_codes + 3 * TITLE_LOGO_COLS)

title_logo_ptrs_dst_lo:
    .byte <(title_text_logo + 0 * TITLE_LOGO_LINE_BYTES)
    .byte <(title_text_logo + 1 * TITLE_LOGO_LINE_BYTES)
    .byte <(title_text_logo + 2 * TITLE_LOGO_LINE_BYTES)
    .byte <(title_text_logo + 3 * TITLE_LOGO_LINE_BYTES)
title_logo_ptrs_dst_hi:
    .byte >(title_text_logo + 0 * TITLE_LOGO_LINE_BYTES)
    .byte >(title_text_logo + 1 * TITLE_LOGO_LINE_BYTES)
    .byte >(title_text_logo + 2 * TITLE_LOGO_LINE_BYTES)
    .byte >(title_text_logo + 3 * TITLE_LOGO_LINE_BYTES)

title_logo_gen_k .byte 0

.proc title_generate_logo
    lda <intro_font
    sta title_gen_charset
    lda >intro_font
    sta title_gen_charset+1

    lda #TITLE_LOGO_COLS
    sta title_gen_len
    lda #TITLE_LOGO_OFFSET
    sta title_gen_x

    lda #0
    sta title_logo_gen_k
@loop
    ldy title_logo_gen_k
    lda title_logo_ptrs_text_lo,y
    sta title_gen_text
    lda title_logo_ptrs_text_hi,y
    sta title_gen_text+1

    lda title_logo_ptrs_dst_lo,y
    sta title_gen_dst
    lda title_logo_ptrs_dst_hi,y
    sta title_gen_dst+1

    jsr title_text_generate
    bcs @done                   ; If parameter validation failed, abort

    inc title_logo_gen_k
    lda title_logo_gen_k
    cmp #TITLE_LOGO_LINES
    bne @loop
@done
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
