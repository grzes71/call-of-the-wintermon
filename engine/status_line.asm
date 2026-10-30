; ==============================================================================
; ENGINE/STATUS_LINE.ASM — In-Game HUD (ANTIC Mode D Narrow, 32 Bytes x 8 Lines)
; Target: Atari 800XL / 65XE (MOS 6502)
;
; Layout:
; - Narrow playfield (32 bytes = 16 characters wide, columns 0..15)
; - Height: 8 lines in ANTIC Mode D (16 scanlines) = 256 bytes (HUD_VRAM = $3E60)
; - Columns 0..7: Player lives (up to 8 heart glyphs, code 64, color %01 = RED)
; - Columns 8..11: Space (0)
; - Column 12: Special disc glyph (code 61, color %11 = GOLD)
; - Column 13: '*' glyph (code 10, color %10 = WHITE)
; - Column 14: First digit ('0'..'9', or '1' when >= 10, color %10 = WHITE)
; - Column 15: Second digit ('0'..'4' when >= 10, or space when < 10, color %10 = WHITE)
; ==============================================================================

STATUS_LINE_WIDTH    = 16    ; 16 characters across the narrow Mode D HUD
STATUS_LINE_BYTES    = 32    ; 32 bytes per row (Narrow Mode D)
STATUS_GLYPH_HEART   = 64    ; Decimal 64 (heart icon in intro_font)
STATUS_GLYPH_SPECIAL = 61    ; Decimal 61 (disc icon in intro_font)
STATUS_GLYPH_STAR    = 10    ; Decimal 10 (asterisk '*' in internal screen codes)
STATUS_GLYPH_X       = STATUS_GLYPH_STAR ; Compatibility alias
STATUS_GLYPH_DIGIT0  = 16    ; Decimal 16 (digit '0' in internal screen codes)
STATUS_GLYPH_SPACE   = 0     ; Blank space in Atari screen codes
STATUS_INIT_LIVES    = 3
STATUS_MAX_LIVES     = 8     ; Maximum lives displayed on HUD (columns 0..7)

status_line_vram = HUD_VRAM

; 16-character shadow text buffer
status_line_chars
    :STATUS_LINE_WIDTH .byte 0

; 16-byte nibble-to-2bpp lookup table for color %01 (RED)
; Color %10 (WHITE) is (val << 1); Color %11 (GOLD) is (val | (val << 1))
hud_lut_color1
    .byte $00,$01,$04,$05,$10,$11,$14,$15,$40,$41,$44,$45,$50,$51,$54,$55

hud_temp_col    .byte 0
hud_temp_char   .byte 0
hud_temp_color  .byte 0
hud_temp_glyph  .byte 0
hud_temp_dst    .byte 0

; ==============================================================================
; HUD RENDER COL
; Renders a single 8x8 character at column X (0..15) into HUD_VRAM.
; Input: X = column index (0..15)
; Preserves: none
; ==============================================================================
.proc hud_render_col
    stx hud_temp_col
    lda status_line_chars,x
    sta hud_temp_char
    bne @draw

    ; Space (0): clear 8 rows at this column
    txa
    asl
    tax
    ldy #8
@cl_loop
    lda #0
    sta HUD_VRAM,x
    sta HUD_VRAM+1,x
    txa
    clc
    adc #32
    tax
    dey
    bne @cl_loop
    rts

@draw
    ; Determine color:
    ; - cols 0..7 (Hearts) & col 13 ('*' / 'x') -> 1 (Hearts color / COLPF0)
    ; - col 12 (Disc) -> 3 (Gold / COLPF2)
    ; - cols 14..15 (Digits) -> 2 (White / COLPF1)
    lda #1
    cpx #STATUS_MAX_LIVES
    bcc @set_col
    cpx #13
    beq @set_col
    lda #3
    cpx #12
    beq @set_col
    lda #2
@set_col
    sta hud_temp_color

    ; font ptr = intro_font ($2400) + (char << 3)
    ; Since intro_font is 1 KB aligned, low byte is (char * 8) & $FF
    lda hud_temp_char
    asl
    asl
    asl
    sta zp_ptr_dst
    lda hud_temp_char
    lsr
    lsr
    lsr
    lsr
    lsr
    clc
    adc #>intro_font
    sta zp_ptr_dst+1

    ; destination byte offset = col * 2
    lda hud_temp_col
    asl
    sta hud_temp_dst

    ldy #0
@row_loop
    lda (zp_ptr_dst),y
    sta hud_temp_glyph

    ; High nibble
    lsr
    lsr
    lsr
    lsr
    jsr hud_expand_nibble
    ldx hud_temp_dst
    sta HUD_VRAM,x

    ; Low nibble
    lda hud_temp_glyph
    and #$0F
    jsr hud_expand_nibble
    ldx hud_temp_dst
    sta HUD_VRAM+1,x

    ; Advance destination by 32 bytes for next row
    lda hud_temp_dst
    clc
    adc #32
    sta hud_temp_dst

    iny
    cpy #8
    bne @row_loop
    rts
.endp

; ==============================================================================
; HUD EXPAND NIBBLE
; Helper subroutine to expand a 4-bit nibble into a 2bpp byte for hud_temp_color.
; Input: A = 4-bit nibble
; Output: A = 8-bit 2bpp pattern
; ==============================================================================
hud_expand_nibble
    tax
    lda hud_lut_color1,x
    ldx hud_temp_color
    cpx #2
    bcc @done
    beq @c2
    sta zp_temp_x
    asl
    ora zp_temp_x
    rts
@c2
    asl
@done
    rts

; ==============================================================================
; HUD CLEAR VRAM
; Clears all 256 bytes of HUD_VRAM ($3E60-$3F5F) to 0.
; ==============================================================================
.proc hud_clear_vram
    lda #0
    tax
@loop
    sta HUD_VRAM,x
    inx
    bne @loop
    rts
.endp

; ==============================================================================
; STATUS LINE RESET
; Resets player lives to 3 and collected CDs to 0.
; Call on new game start.
; ==============================================================================
.proc status_line_reset
    lda #STATUS_INIT_LIVES
    sta player_lives
    lda #0
    sta player_specials
    sta game_result
    rts
.endp

; ==============================================================================
; STATUS LINE INIT
; Initializes status line for the specified scene.
; Clears HUD_VRAM with zeros, clears shadow chars, then renders lives and specials.
; Input: A = scene_id (0..SCENE_COUNT-1)
; Preserves: X
; ==============================================================================
.proc status_line_init
    cmp #SCENE_COUNT
    bcc @valid_id
    rts

@valid_id
    sta active_scene_id
    txa
    pha

    ; 1. Clear HUD_VRAM and shadow character buffer
    jsr hud_clear_vram
    ldy #STATUS_LINE_WIDTH - 1
    lda #STATUS_GLYPH_SPACE
@clear_chars
    sta status_line_chars,y
    dey
    bpl @clear_chars

    ; 2. Render lives (hearts) at left (columns 0..9)
    jsr status_line_refresh_lives

    ; 3. Render collected-special counter at right (columns 11..15)
    jsr status_line_refresh_specials

    pla
    tax
    rts
.endp

; ==============================================================================
; STATUS LINE REFRESH LIVES
; Updates columns 0..STATUS_MAX_LIVES-1 with heart glyphs (code 64) based on
; player_lives (up to STATUS_MAX_LIVES hearts).
; ==============================================================================
.proc status_line_refresh_lives
    txa
    pha
    tya
    pha

    ldx #0
@loop
    cpx player_lives
    lda #STATUS_GLYPH_HEART
    bcc @draw
    lda #STATUS_GLYPH_SPACE
@draw
    sta status_line_chars,x
    jsr hud_render_col
    ldx hud_temp_col
    inx
    cpx #STATUS_MAX_LIVES
    bcc @loop

    pla
    tay
    pla
    tax
    rts
.endp

; ==============================================================================
; STATUS LINE REFRESH SPECIALS
; Draws:
; Column 11: Special disc icon (code 61, gold)
; Column 13: 'X' (code 56, white)
; Column 15: Decimal digit of player_specials (codes 16..25, white)
; Preserves: X, Y
; ==============================================================================
.proc status_line_refresh_specials
    txa
    pha
    tya
    pha

    ; Setup shadow chars: "💿*N" (cols 12..15)
    lda #STATUS_GLYPH_SPECIAL
    sta status_line_chars + 12

    lda #STATUS_GLYPH_STAR
    sta status_line_chars + 13

    lda player_specials
    cmp #10
    bcc @under_10

    ; Specials >= 10 (10..14): col 14 = '1', col 15 = '0' + (specials - 10)
    lda #STATUS_GLYPH_DIGIT0 + 1
    sta status_line_chars + 14
    lda player_specials
    sec
    sbc #10
    cmp #10
    bcc @units_ok
    lda #9
@units_ok
    clc
    adc #STATUS_GLYPH_DIGIT0
    sta status_line_chars + 15
    jmp @render

@under_10
    ; Specials < 10 (0..9): col 14 = '0' + specials, col 15 = space
    clc
    adc #STATUS_GLYPH_DIGIT0
    sta status_line_chars + 14
    lda #STATUS_GLYPH_SPACE
    sta status_line_chars + 15

@render
    ldx #12
    jsr hud_render_col
    ldx #13
    jsr hud_render_col
    ldx #14
    jsr hud_render_col
    ldx #15
    jsr hud_render_col

    pla
    tay
    pla
    tax
    rts
.endp

; ==============================================================================
; STATUS LINE ADD SPECIAL
; Marks one collected special secret: increments the counter and redraws the icons.
; Preserves: X, Y
; ==============================================================================
.proc status_line_add_special
    inc player_specials
    jsr status_line_refresh_specials
    rts
.endp

; ==============================================================================
; STATUS LINE LOSE LIFE
; Decrements player_lives and updates status line display.
; ==============================================================================
.proc status_line_lose_life
    lda player_lives
    beq @done
    dec player_lives
    jsr status_line_refresh_lives
@done
    rts
.endp

; ==============================================================================
; STATUS LINE UPDATE
; Refreshes both lives and collected-special icons.
; ==============================================================================
.proc status_line_update
    jsr status_line_refresh_lives
    jsr status_line_refresh_specials
    rts
.endp
