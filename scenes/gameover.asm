; ==============================================================================
; SCENES/GAMEOVER.ASM — Game Over / Victory screens (FAILURE and SUCCESS)
; Target: Atari 800XL / 65XE
;
; Two separate display lists with an identical structure; only the header text,
; the ANTIC 2 text data and the colours differ:
;
;   24 scanlines   3 x DL_BLANK8 top margin, the last one with the DLI bit
;                   -> dli_gameover_header sets the header colours
;   32 scanlines   header: 16 x (DL_MODE_D | DL_LMS), 8 glyph rows shown twice each
;    8 scanlines   DL_BLANK8 | DL_DLI margin -> dli_gameover_text sets text colours
;  144 scanlines   text: DL_MODE_2 | DL_LMS + 17 x DL_MODE_2 (18 lines x 40 columns)
;   (DL_JVB back to the start of the same display list)
;   total 208 of the 240 PAL scanlines
;
; The header glyphs are generated at run time by title_text_generate (the same
; 2bpp generator as the title screen, three column bands) into
; gameover_header_buf, and the ANTIC 2 text lines come from gen/gameover_texts.inc
; (scripts/convert_gameover_texts.py), centred while copying.
;
; The discriminator is the existing game_result value: GAME_FAILED (set by
; player.asm when the last life is lost) shows the FAILURE screen, GAME_SUCCESS
; (set by game.asm after the final scene) shows the SUCCESS screen.
; ==============================================================================

; --- Screen geometry ---
GAMEOVER_TOP_BLANKS   = 3        ; 3 x DL_BLANK8 = 24 scanlines (>= 1, last one has DLI)
GAMEOVER_HEADER_LINES = 16       ; ANTIC D lines: 8 glyph rows, each shown twice
GAMEOVER_HEADER_BYTES = 320      ; 8 rows x 40 bytes (title_text_generate output)
GAMEOVER_TEXT_LINES   = 18       ; ANTIC 2 lines in the display list
GAMEOVER_LINE_WIDTH   = 40
GAMEOVER_TEXT_BYTES   = GAMEOVER_TEXT_LINES * GAMEOVER_LINE_WIDTH   ; 720
GAMEOVER_CLEAR_BYTES  = GAMEOVER_HEADER_BYTES + GAMEOVER_TEXT_BYTES ; 1040
GAMEOVER_HOLD_FRAMES  = 50       ; Minimum hold delay (50 PAL frames = 1.0 second)

; --- Buffers inside GAME_VRAM (no new XEX segment; cleared on every entry) ---
gameover_header_buf = GAME_VRAM + $0000    ; $3000-$313F, 320 B
gameover_text_buf   = GAME_VRAM + $0140    ; $3140-$340F, 720 B

; --- Variant ids (gameover_result) ---
GAMEOVER_FAILURE = 0
GAMEOVER_SUCCESS = 1

; --- Header character codes (all verified in fonts/font.fnt) ---
gameover_text_failure_codes:       ; "GAME OVER" - 9 characters, space = $00
    .byte $27,$21,$2D,$25,$00,$2F,$36,$25,$32
gameover_text_success_codes:       ; "VICTORY!" - 8 characters, '!' = $01
    .byte $36,$29,$23,$34,$2F,$32,$39,$01

GAMEOVER_FAILURE_LEN    = 9

; --- Colours (ANTIC D header = 2bpp: COLPF1 left, COLPF2 middle, COLPF0 right;
;     ANTIC 2 text: the glyph pixels take COLPF1, COLPF2 is the background) ---
GAMEOVER_COLOR_BK        = $00     ; Black border/background (COLBK)

; FAILURE: warm red/orange header on black, light red text
GAMEOVER_FAIL_HDR_PF0    = $1A     ; (right columns)
GAMEOVER_FAIL_HDR_PF1    = $1E     ; (left columns)
GAMEOVER_FAIL_HDR_PF2    = $1C     ; (middle columns)
GAMEOVER_FAIL_TXT_PF1    = $3D     ; light red tex
GAMEOVER_FAIL_TXT_PF2    = $00     ; black text background

; SUCCESS: green family (as on the title screen), bright green text
GAMEOVER_SUCCESS_HDR_PF0 = $88     ;  (right columns)
GAMEOVER_SUCCESS_HDR_PF1 = $8C     ; (left columns)
GAMEOVER_SUCCESS_HDR_PF2 = $8A     ; (middle columns)
GAMEOVER_SUCCESS_TXT_PF1 = $0D     ; light text
GAMEOVER_SUCCESS_TXT_PF2 = $00     ; black text background

; --- Runtime state (this module is loaded into RAM, so it is writable) ---
gameover_result   .byte GAMEOVER_FAILURE   ; 0 = FAILURE, 1 = SUCCESS (from game_result)
gameover_colors                            ; 6 bytes read by the DLI handlers
                  .byte GAMEOVER_FAIL_HDR_PF0, GAMEOVER_FAIL_HDR_PF1, GAMEOVER_FAIL_HDR_PF2
                  .byte GAMEOVER_FAIL_TXT_PF1, GAMEOVER_FAIL_TXT_PF2, GAMEOVER_COLOR_BK
gameover_lines    .byte 0          ; number of text lines in the chosen variant data
gameover_line     .byte 0          ; current text line while copying
gameover_len      .byte 0          ; length of the current text line
gameover_left     .byte 0          ; centring margin of the current text line
gameover_dst      .word 0          ; destination line start while copying
gameover_timer    .byte 0          ; minimum hold delay timer before accepting input

; --- Variant tables ---
gameover_text_ptrs_lo:
    .byte <gameover_failure_text, <gameover_success_text
gameover_text_ptrs_hi:
    .byte >gameover_failure_text, >gameover_success_text
gameover_header_ptrs_lo:
    .byte <gameover_text_failure_codes, <gameover_text_success_codes
gameover_header_ptrs_hi:
    .byte >gameover_text_failure_codes, >gameover_text_success_codes
gameover_header_lens:
    .byte GAMEOVER_FAILURE_LEN, GAMEOVER_SUCCESS_LEN
gameover_header_offsets:
    .byte GAMEOVER_FAILURE_OFFSET, GAMEOVER_SUCCESS_OFFSET
gameover_color_ptrs_lo:
    .byte <gameover_colors_failure, <gameover_colors_success
gameover_color_ptrs_hi:
    .byte >gameover_colors_failure, >gameover_colors_success
gameover_dlist_ptrs_lo:
    .byte <dlist_gameover_failure, <dlist_gameover_success
gameover_dlist_ptrs_hi:
    .byte >dlist_gameover_failure, >dlist_gameover_success

gameover_colors_failure:
    .byte GAMEOVER_FAIL_HDR_PF0, GAMEOVER_FAIL_HDR_PF1, GAMEOVER_FAIL_HDR_PF2
    .byte GAMEOVER_FAIL_TXT_PF1, GAMEOVER_FAIL_TXT_PF2, GAMEOVER_COLOR_BK
gameover_colors_success:
    .byte GAMEOVER_SUCCESS_HDR_PF0, GAMEOVER_SUCCESS_HDR_PF1, GAMEOVER_SUCCESS_HDR_PF2
    .byte GAMEOVER_SUCCESS_TXT_PF1, GAMEOVER_SUCCESS_TXT_PF2, GAMEOVER_COLOR_BK

; --- Game Over texts live in their own segment (GAMEOVER_TEXT at $BC00): the
;     compact data is ~850 B, so the code+display-list page stays under 1 KB.
;     The include happens in main.asm; the labels below are resolved there.

; --- Compile-time checks of the header parameters ---
.if GAMEOVER_TOP_BLANKS < 1
    .error "GAMEOVER_TOP_BLANKS must be at least 1"
.endif
.if (GAMEOVER_FAILURE_LEN < 1) || (GAMEOVER_FAILURE_LEN > 20)
    .error "GAMEOVER_FAILURE_LEN must be between 1 and 20"
.endif
.if (GAMEOVER_FAILURE_OFFSET + 2 * GAMEOVER_FAILURE_LEN > GAMEOVER_LINE_WIDTH)
    .error "GAMEOVER_FAILURE header exceeds the 40-byte row"
.endif
.if (GAMEOVER_SUCCESS_LEN < 1) || (GAMEOVER_SUCCESS_LEN > 20)
    .error "GAMEOVER_SUCCESS_LEN must be between 1 and 20"
.endif
.if (GAMEOVER_SUCCESS_OFFSET + 2 * GAMEOVER_SUCCESS_LEN > GAMEOVER_LINE_WIDTH)
    .error "GAMEOVER_SUCCESS header exceeds the 40-byte row"
.endif

GAMEOVER_SUCCESS_LEN    = 8
GAMEOVER_FAILURE_OFFSET = 11       ; (40 - 2 * 9) / 2
GAMEOVER_SUCCESS_OFFSET = 12       ; (40 - 2 * 8) / 2


; ==============================================================================
; DISPLAY LISTS — one per variant (identical structure, different labels)
; ==============================================================================
dlist_gameover_failure:
    .byte DL_BLANK8, DL_BLANK8
    .byte DL_BLANK8 | DL_DLI
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 0
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 0
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 1
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 1
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 2
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 2
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 3
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 3
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 4
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 4
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 5
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 5
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 6
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 6
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 7
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 7
    .byte DL_BLANK8 | DL_DLI
    .byte DL_MODE_2 | DL_LMS
    .word gameover_text_buf
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_JVB
    .word dlist_gameover_failure

dlist_gameover_success:
    .byte DL_BLANK8, DL_BLANK8
    .byte DL_BLANK8 | DL_DLI
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 0
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 0
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 1
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 1
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 2
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 2
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 3
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 3
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 4
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 4
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 5
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 5
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 6
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 6
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 7
    .byte DL_MODE_D | DL_LMS
    .word gameover_header_buf + 40 * 7
    .byte DL_BLANK8 | DL_DLI
    .byte DL_MODE_2 | DL_LMS
    .word gameover_text_buf
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_MODE_2
    .byte DL_JVB
    .word dlist_gameover_success


; ==============================================================================
; GAMEOVER INIT
; Entry point from the state machine (main.asm) for STATE_OVER. It picks FAILURE or
; SUCCESS from the existing game_result value, rebuilds both screen buffers, installs
; the display list + DLI chain and enables the screen.
; ==============================================================================
.proc gameover_init
    ; 1. Turn off DMA and disable NMIs while rebuilding the screen
    lda #0
    sta SDMCTL
    sta DMACTL
    sta NMIEN
    sta NMIRES

    ; 2. Disable GTIA PMG graphics and clear all player/missile positions, sizes, and colors ($D000-$D01D)
    ldx #$1D
@clr_gtia
    sta HPOSP0,x
    dex
    bpl @clr_gtia

    ; 3. Clear the active PMG memory buffer ($6B00-$6FFF, 1,280 bytes)
    tax
@clr_pmg
    sta PMG_MISSILES,x
    sta PMG_PLAYER0,x
    sta PMG_PLAYER1,x
    sta PMG_PLAYER2,x
    sta PMG_PLAYER3,x
    inx
    bne @clr_pmg

    ; 4. Black border/background
    sta COLOR4
    sta COLBK

    ; 5. Variant from the existing game result: GAME_SUCCESS -> SUCCESS, everything
    ;    else (GAME_FAILED, GAME_RESULT_NONE) -> FAILURE.
    ldx #GAMEOVER_FAILURE
    lda game_result
    cmp #GAME_SUCCESS
    bne @variant_ready
    ldx #GAMEOVER_SUCCESS
@variant_ready
    stx gameover_result

    ; 6. Repoint Display List early to prevent ANTIC from executing orphaned gameplay lines
    lda gameover_dlist_ptrs_lo,x
    sta SDLSTL
    sta DLISTL
    lda gameover_dlist_ptrs_hi,x
    sta SDLSTH
    sta DLISTH

    ; 7. Clear exactly 1040 bytes of GAME_VRAM (header + text buffers)
    jsr gameover_clear_buffers

    ; 8. Header glyphs (same 2bpp generator as the title screen)
    jsr gameover_generate_header

    ; 9. ANTIC 2 text lines, centred while copying
    jsr gameover_copy_text

    ; 10. Colours of this variant (read by the DLI chain)
    ldx gameover_result
    lda gameover_color_ptrs_lo,x
    sta zp_ptr_src
    lda gameover_color_ptrs_hi,x
    sta zp_ptr_src+1
    ldy #5
@copy_colors
    lda (zp_ptr_src),y
    sta gameover_colors,y
    dey
    bpl @copy_colors

    ; 11. Character set for the ANTIC 2 text (same 1 KB font as the intro/title)
    lda >intro_font
    sta CHBAS
    sta CHBASE

    ; 12. DLI chain starts with the header colour handler
    lda #<dli_gameover_header
    sta VDSLST
    lda #>dli_gameover_header
    sta VDSLST+1

    ; 13. Enable VBLANK ($40) + DLI ($80) and normal-width playfield DMA
    lda #$C0
    sta NMIEN
    lda #$22
    sta SDMCTL
    sta DMACTL

    ; 14. Purge OS keyboard latch and initialize debounce & hold delay timer
    lda #$FF
    sta CH
    lda #0
    sta fire_released
    lda #GAMEOVER_HOLD_FRAMES
    sta gameover_timer

    ; 15. Silence the sound effects engine
    jsr sfx_stop_all

    ; 16. Start appropriate music (victory or failure)
    lda gameover_result
    cmp #GAMEOVER_SUCCESS
    beq @start_victory
    jsr audio_play_gameover
    rts
@start_victory
    jsr audio_play_victory
    rts
.endp


; ==============================================================================
; GAMEOVER CLEAR BUFFERS
; Clears exactly GAMEOVER_CLEAR_BYTES (1040) of GAME_VRAM: the 320-byte header
; buffer and the 720-byte text buffer ($3000-$340F). Nothing at $3410 or beyond is
; touched - the rest of the playfield buffer is refilled when gameplay resumes.
; ==============================================================================
.proc gameover_clear_buffers
    lda #0
    ldx #0
@main_loop
    sta gameover_header_buf + 0*256,x
    sta gameover_header_buf + 1*256,x
    sta gameover_header_buf + 2*256,x
    sta gameover_header_buf + 3*256,x
    inx
    bne @main_loop

    ; Remaining 16 bytes (1040 - 4 * 256)
    ldx #0
@tail_loop
    sta gameover_header_buf + 4*256,x
    inx
    cpx #(GAMEOVER_CLEAR_BYTES - 4 * 256)
    bne @tail_loop
    rts
.endp


; ==============================================================================
; GAMEOVER GENERATE HEADER
; Renders the variant header ("GAME OVER" / "VICTORY!") into gameover_header_buf
; with title_text_generate (the title screen's 2bpp generator, three column bands).
; The generator's carry is checked: on invalid parameters the header stays blank.
; ==============================================================================
.proc gameover_generate_header
    ldx gameover_result

    lda #<intro_font
    sta title_gen_charset
    lda #>intro_font
    sta title_gen_charset+1

    lda gameover_header_ptrs_lo,x
    sta title_gen_text
    lda gameover_header_ptrs_hi,x
    sta title_gen_text+1

    lda #<gameover_header_buf
    sta title_gen_dst
    lda #>gameover_header_buf
    sta title_gen_dst+1

    lda gameover_header_lens,x
    sta title_gen_len
    lda gameover_header_offsets,x
    sta title_gen_x

    jsr title_text_generate
    bcs @invalid
    rts
@invalid
    ; The parameters are compile-time constants checked by .if assertions, so this
    ; should never happen; leaving the (already cleared) header blank is the fallback.
    rts
.endp


; ==============================================================================
; GAMEOVER COPY TEXT
; Copies the variant's compact text data (line count, then len + codes per line)
; into gameover_text_buf, centring every line with a left margin of
; (GAMEOVER_LINE_WIDTH - len) / 2. Lines beyond the file (or beyond the 18 display
; list lines) stay blank because the buffer was cleared first.
; ==============================================================================
.proc gameover_copy_text
    ldx gameover_result
    lda gameover_text_ptrs_lo,x
    sta zp_ptr_src
    lda gameover_text_ptrs_hi,x
    sta zp_ptr_src+1

    lda #<gameover_text_buf
    sta gameover_dst
    lda #>gameover_text_buf
    sta gameover_dst+1

    ldy #0
    lda (zp_ptr_src),y          ; number of lines in this variant
    sta gameover_lines
    inc zp_ptr_src              ; skip the line count byte
    bne @counted
    inc zp_ptr_src+1
@counted
    lda #0
    sta gameover_line

@line_loop
    lda gameover_line
    cmp gameover_lines
    bcc @line_ok                ; every line of the file copied?
    jmp @done
@line_ok
    cmp #GAMEOVER_TEXT_LINES
    bcc @line_fits              ; display list is full - the rest stays blank
    jmp @done
@line_fits

    ldy #0
    lda (zp_ptr_src),y          ; line length (0 = empty line)
    sta gameover_len
    inc zp_ptr_src
    bne @len_read
    inc zp_ptr_src+1
@len_read

    ; left margin = (40 - len) / 2
    lda #GAMEOVER_LINE_WIDTH
    sec
    sbc gameover_len
    lsr
    sta gameover_left

    ; destination row start + left margin
    clc
    adc gameover_dst
    sta zp_ptr_dst
    lda gameover_dst+1
    adc #0
    sta zp_ptr_dst+1



    ; Copy backwards so that one Y indexes both source and destination.
    ldy gameover_len
    beq @line_copied
@copy
    dey
    lda (zp_ptr_src),y
    sta (zp_ptr_dst),y
    cpy #0
    bne @copy

@line_copied
    ; advance the source past this line's codes
    clc
    lda zp_ptr_src
    adc gameover_len
    sta zp_ptr_src
    bcc @src_ok
    inc zp_ptr_src+1
@src_ok

    ; next destination row
    clc
    lda gameover_dst
    adc #GAMEOVER_LINE_WIDTH
    sta gameover_dst
    bcc @dst_ok
    inc gameover_dst+1
@dst_ok

    inc gameover_line
    jmp @line_loop

@done
    rts
.endp

; ==============================================================================
; DLI HANDLERS — two chained, self-resetting handlers shared by both variants.
; Colours are read from gameover_colors (filled by gameover_init), so the handlers
; are variant-agnostic. Only A is used, no WSYNC, writes go to hardware registers
; and VDSLST only.
;
; Cycle budget: pha (3) + 4 x (lda zp + sta abs = 7) + 2 x (lda # + sta abs = 6)
; + pla (4) + rti (6) = 53 cycles, well inside one scanline (both DLIs fire on
; blank lines, so no DMA contention).
; ==============================================================================
.proc dli_gameover_header
    pha
    lda gameover_colors+0       ; header COLPF0
    sta COLPF0
    lda gameover_colors+1       ; header COLPF1
    sta COLPF1
    lda gameover_colors+2       ; header COLPF2
    sta COLPF2
    lda gameover_colors+5       ; background
    sta COLBK
    lda #<dli_gameover_text     ; chain the text colour handler
    sta VDSLST
    lda #>dli_gameover_text
    sta VDSLST+1
    pla
    rti
.endp

.proc dli_gameover_text
    pha
    lda gameover_colors+3       ; ANTIC 2 text colour (glyph pixels)
    sta COLPF1
    lda gameover_colors+4       ; ANTIC 2 text background
    sta COLPF2
    lda gameover_colors+5       ; background
    sta COLBK
    lda #<dli_gameover_header   ; self-reset for the next frame
    sta VDSLST
    lda #>dli_gameover_header
    sta VDSLST+1
    pla
    rti
.endp


; ==============================================================================
; GAMEOVER RUN
; Per-frame handler for STATE_OVER: waits for VBLANK, keeps the display list and
; the first DLI of the chain installed, then leaves back to the title screen when
; fire is pressed (after the button was released once).
; ==============================================================================
.proc gameover_run
    ; Keep normal-width playfield DMA
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

    ; Advance music playback frame
    jsr audio_update

    ; Keep the DLI chain head installed at the start of each frame (fallback safety)
    lda #<dli_gameover_header
    sta VDSLST
    lda #>dli_gameover_header
    sta VDSLST+1

    ; Check minimum hold delay timer
    lda gameover_timer
    beq @check_input
    dec gameover_timer
    lda #$FF
    sta CH              ; Purge key buffer during hold delay
    lda #0
    sta fire_released   ; Ensure release flag stays 0 during hold
    rts

@check_input
    ; Check if button was released first
    lda fire_released
    bne @can_press

    ; Both fire button (STRIG0 = 1) and keyboard (CH = $FF) must be released
    lda STRIG0
    beq @still_pressed
    lda CH
    cmp #$FF
    bne @still_pressed
    lda #1
    sta fire_released
@still_pressed
    rts

@can_press
    ; Fire button (STRIG0 = 0) or any keypress (CH != $FF)
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
    ; Silence music before leaving Game Over screen
    jsr audio_stop

    ; Leave the screen clean for the title screen: no scroll, DLI disabled
    lda #0
    sta HSCROL
    sta VSCROL
    lda #$40            ; VBLANK only ($40), DLI disabled
    sta NMIEN

    ; Transition back to the TITLE screen (as before this change)
    lda #STATE_TITLE
    sta game_state
    rts
.endp
