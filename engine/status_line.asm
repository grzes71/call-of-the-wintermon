; ==============================================================================
; ENGINE/STATUS_LINE.ASM — In-Game Status Line (ANTIC Mode 2, 40 Columns)
; Target: Atari 800XL / 65XE (MOS 6502)
; Layout (40 chars):
; - Columns 0..2: Player lives (initially 3), displayed as heart glyphs (code 64)
; - Middle (columns 3..N): blank space
; - Right end (columns N+1..39): one disc glyph (code 61) per collected secret whose
;   catalogue definition carries "special": true, filled from column 39 leftwards.
;   The counter (player_specials) survives scene changes - only status_line_reset
;   (a new game) clears it.
; ==============================================================================

STATUS_LINE_WIDTH    = 40
STATUS_GLYPH_HEART   = 64    ; Decimal 64 (heart icon in intro_font)
STATUS_GLYPH_SPECIAL = 61    ; Decimal 61 (disc icon in intro_font)
STATUS_GLYPH_SPACE   = 0     ; Blank space in Atari screen codes
STATUS_INIT_LIVES    = 3

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
; Clears status_line_vram with spaces, then writes player lives (hearts) at
; columns 0..2 and collected-special icons at the right end.
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

    ; 1. Clear status_line_vram with spaces
    lda #STATUS_GLYPH_SPACE
    ldy #STATUS_LINE_WIDTH - 1
@clear_line
    sta status_line_vram,y
    dey
    bpl @clear_line

    ; 2. Render lives (hearts) at left (columns 0..2)
    jsr status_line_refresh_lives

    ; 3. Render collected-special icons at the right end (columns 39, 38, ...)
    jsr status_line_refresh_specials

    pla
    tax
    rts
.endp

; ==============================================================================
; STATUS LINE REFRESH LIVES
; Updates columns 0..2 with heart glyphs (code 64) based on player_lives.
; ==============================================================================
.proc status_line_refresh_lives
    ldy #0
@loop
    cpy #3
    bcs @done
    cpy player_lives
    bcc @set_heart
    lda #STATUS_GLYPH_SPACE
    jmp @store
@set_heart
    lda #STATUS_GLYPH_HEART
@store
    sta status_line_vram,y
    iny
    jmp @loop
@done
    rts
.endp

; ==============================================================================
; STATUS LINE REFRESH SPECIALS
; Draws one disc glyph (code 61) per collected special secret, filling the right end
; of the status line from column 39 leftwards - the first one collected ends up
; rightmost. The counter survives scene changes, so icons collected earlier stay
; visible in later scenes; only status_line_reset (a new game) clears them.
; Preserves: X, Y
; ==============================================================================
.proc status_line_refresh_specials
    txa
    pha
    tya
    pha

    lda player_specials
    beq @done
    ldx #STATUS_LINE_WIDTH - 1      ; rightmost status line column
    tay
@draw
    lda #STATUS_GLYPH_SPECIAL
    sta status_line_vram,x
    dex
    bmi @done                       ; never write left of the status line
    dey
    bne @draw

@done
    pla
    tay
    pla
    tax
    rts
.endp

; ==============================================================================
; STATUS LINE ADD SPECIAL
; Marks one collected special secret: increments the counter and redraws the icons.
; Called from secret_collect (scenes/game.asm) only for secrets whose catalogue
; definition carries "special": true. The compiler guarantees that the number of
; special secrets in all scenes never exceeds the reserved status line columns.
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
