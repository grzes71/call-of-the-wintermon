; ==============================================================================
; ENGINE/SFX_VICTORY.ASM — Level-Complete Victory Fanfare (POKEY Channel 1)
; Target: Atari 800XL / 65XE (MOS 6502)
;
; Plays a short, triumphant rising 4-note major arpeggio (C4 -> E4 -> G4 -> C5),
; 4 notes x 16 frames = 64 frames (~1.28s at 50 Hz PAL), with a crescendo inside
; every note window.
;
; Triggered from game_next_scene as soon as all secrets of a scene are collected;
; game_run calls sfx_update in every phase, so the fanfare plays out over the next
; scene's title card (before gameplay resumes).
;
; MEMORY: this module lives in the TILES_META segment ($2A30) next to
; engine/status_line.asm, because the SCENES_DATA block ($5000) has no headroom
; left. sfx_update (engine/sfx.asm) reaches it through sfx_victory_tick.
;
; Priority: only the death sequence preempts the fanfare (sfx_play_death clears
; the timer). Walk/jump/fall cannot interrupt it in practice, because the fanfare
; runs while the scene title card is displayed and player_update is not running.
; ==============================================================================

; --- Victory Fanfare State & Data ---
sfx_victory_timer   .byte 0     ; Fanfare frame countdown (64..0, 0 = inactive)

SFX_VICTORY_DURATION    = 64    ; 64 frames (~1.28s)
SFX_VICTORY_NOTE_FRAMES = 16    ; 4 notes x 16 frames (power of two -> shift indexing)

; Rising C major arpeggio: C4, E4, G4, C5 (AUDF falls -> pitch rises)
sfx_victory_notes
    .byte $79                   ; Note index 0: C4 (AUDF = $79)
    .byte $60                   ; Note index 1: E4 (AUDF = $60)
    .byte $51                   ; Note index 2: G4 (AUDF = $51)
    .byte $3C                   ; Note index 3: C5 (AUDF = $3C)


; ==============================================================================
; SFX_PLAY_VICTORY
; Starts the fanfare and silences walk/jump/fall sounds (level complete).
; ==============================================================================
.proc sfx_play_victory
    lda #0
    sta sfx_walk_timer
    sta sfx_jump_timer
    sta sfx_fall_active
    sta AUDC2                   ; Silence the free-fall wind (Channel 2)
    sta AUDF2

    lda #SFX_VICTORY_DURATION
    sta sfx_victory_timer
    rts
.endp


; ==============================================================================
; SFX_VICTORY_TICK
; Per-frame fanfare driver, called from sfx_update (engine/sfx.asm).
; Returns A = 0 / Z = 1 when the fanfare is inactive (the caller then falls through
; to the remaining sounds); returns A != 0 / Z = 0 after handling a fanfare frame.
; Clobbers A, X and Y - sfx_update restores all three on exit.
; ==============================================================================
.proc sfx_victory_tick
    lda sfx_victory_timer
    beq @inactive

    dec sfx_victory_timer
    beq @finished

    ; Elapsed frame index (0-based) = SFX_VICTORY_DURATION - 1 - timer
    lda #SFX_VICTORY_DURATION - 1
    sec
    sbc sfx_victory_timer
    tay

    ; Note index = elapsed >> 4 (0..3): the pitch climbs C4 -> E4 -> G4 -> C5
    lsr
    lsr
    lsr
    lsr
    tax
    lda sfx_victory_notes,x
    sta AUDF1

    ; Crescendo inside each note window: (elapsed & $0F) >> 2 -> volume $A4..$A7
    tya
    and #$0F
    lsr
    lsr
    ora #$A4                    ; Pure tone ($A0) + volume nibble
    sta AUDC1
    lda #1
    rts

@finished
    lda #0
    sta AUDC1
    sta AUDF1
    rts

@inactive
    lda #0
    rts
.endp
