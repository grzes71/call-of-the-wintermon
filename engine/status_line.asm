; ==============================================================================
; ENGINE/STATUS_LINE.ASM — In-Game Status Line (ANTIC Mode 2, 40 Columns)
; Target: Atari 800XL / 65XE (MOS 6502)
; Layout (40 chars):
; - Columns 0..2: Player lives (initially 3), displayed as heart glyphs (code 64)
; - Column 3: spacer
; - Columns 4..37: Scene name, left-aligned from column 4 - pre-formatted by the
;   compiler in scene_<scene>_hud_line. The centred scene_<scene>_name_line is
;   only used by the scene title card (dlist_scene_title).
; - Columns 38..39: Collected CDs count (0..99, 2-digit number in screen codes $10..$19)
; ==============================================================================

STATUS_LINE_WIDTH   = 40
STATUS_GLYPH_HEART  = 64    ; Decimal 64 (heart icon in intro_font)
STATUS_GLYPH_SPACE  = 0     ; Blank space in Atari screen codes
STATUS_DIGIT_BASE   = $10   ; Screen code offset for '0'..'9' ($10 = '0')
STATUS_MAX_CDS      = 99
STATUS_INIT_LIVES   = 3

; ==============================================================================
; STATUS LINE RESET
; Resets player lives to 3 and collected CDs to 0.
; Call on new game start.
; ==============================================================================
.proc status_line_reset
    lda #STATUS_INIT_LIVES
    sta player_lives
    lda #0
    sta player_cds
    sta game_result
    rts
.endp

; ==============================================================================
; STATUS LINE INIT
; Initializes status line for the specified scene.
; Copies the pre-formatted HUD line (scene name left-aligned from column 4) into
; status_line_vram, then writes player lives (hearts) at columns 0..2 and collected
; CDs at columns 38..39.
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

    ; 1. Point zp_ptr_src to the pre-formatted HUD line for this scene
    ldx active_scene_id
    lda scene_hud_line_lo,x
    sta zp_ptr_src
    lda scene_hud_line_hi,x
    sta zp_ptr_src+1

    ; 2. Copy the 40 bytes of the HUD line (name already at column 4) to status_line_vram
    ldy #STATUS_LINE_WIDTH - 1
@copy_name
    lda (zp_ptr_src),y
    sta status_line_vram,y
    dey
    bpl @copy_name

    ; 3. Render lives (hearts) at left (columns 0..2)
    jsr status_line_refresh_lives

    ; 4. Render CD count at right (columns 38..39)
    jsr status_line_refresh_cds

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
; STATUS LINE REFRESH CDS
; Formats player_cds (clamped to 99) as two decimal digits at columns 38..39.
; ==============================================================================
.proc status_line_refresh_cds
    lda player_cds
    cmp #STATUS_MAX_CDS
    bcc @clamp_ok
    lda #STATUS_MAX_CDS
@clamp_ok
    ldx #0
@div10
    cmp #10
    bcc @got_digits
    sec
    sbc #10
    inx
    bne @div10

@got_digits
    ; A = units (0..9), X = tens (0..9)
    ora #STATUS_DIGIT_BASE  ; Screen code for '0'..'9'
    sta status_line_vram + 39
    txa
    ora #STATUS_DIGIT_BASE
    sta status_line_vram + 38
    rts
.endp

; ==============================================================================
; STATUS LINE ADD CD
; Increments player_cds (max 99) and updates status line display.
; ==============================================================================
.proc status_line_add_cd
    lda player_cds
    cmp #STATUS_MAX_CDS
    bcs @done
    inc player_cds
    jsr status_line_refresh_cds
@done
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
; Refreshes both lives and CD counters.
; ==============================================================================
.proc status_line_update
    jsr status_line_refresh_lives
    jsr status_line_refresh_cds
    rts
.endp
