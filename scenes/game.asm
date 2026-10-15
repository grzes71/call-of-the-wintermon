; ==============================================================================
; SCENES/GAME.ASM — Main Gameplay State Handler (Stub)
; Transitions to STATE_OVER upon Fire / Keypress
; ==============================================================================

.proc game_init
    ; Blank playfield DMA during setup
    lda #0
    sta SDMCTL
    sta DMACTL

    ; Point display list to dlist_game
    lda <dlist_game
    sta SDLSTL
    sta DLISTL
    lda >dlist_game
    sta SDLSTH
    sta DLISTH

    ; Set PMBASE (Player-Missile Graphics buffer page)
    lda #PMBASE_PAGE
    sta PMBASE

    ; Configure default palette: Forest theme (tileset_trees)
    lda #$00
    sta COLOR4
    sta COLBK           ; Background: Black ($00)

    lda tileset_colpf0+TILESET_TREES
    sta COLOR0
    sta COLPF0          ; Dark green ($C4)

    lda tileset_colpf1+TILESET_TREES
    sta COLOR1
    sta COLPF1          ; Medium emerald ($C8)

    lda tileset_colpf2+TILESET_TREES
    sta COLOR2
    sta COLPF2          ; Bright lime ($DC)

    ; Require releasing fire button before accepting next press
    lda #0
    sta fire_released
    rts
.endp

.proc game_run
    ; Enable ANTIC Mode E playfield DMA (standard width 40 cols + DLIST)
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
    ; Transition to GAME OVER screen
    lda #STATE_OVER
    sta game_state
    rts
.endp
