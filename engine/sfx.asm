; ==============================================================================
; ENGINE/SFX.ASM — Sound Effects Engine for Atari 8-bit (POKEY)
; Target: Atari 800XL / 65XE (MOS 6502)
;
; Sound Effects:
;   1. Footstep   (Walk)   - Ch 1: crisp poly4 noise click (3 frames)
;   2. Jump       (Jump)   - Ch 1: pure tone upward pitch sweep (14 frames)
;   3. Free Fall  (Fall)   - Ch 2: ambient poly17 rushing wind whoosh
;   4. Death      (Death)  - Ch 1+2: crash impact + 4-note mournful minor arpeggio (72 frames)
;   5. Victory    (Level)  - Ch 1: rising 4-note major arpeggio fanfare (64 frames)
;                            (implemented in engine/sfx_victory.asm, which lives in
;                             the $2A30 segment to keep the $5000 block from overflowing)
;   6. Secret     (Collect)- Ch 3: short rising blip (6 frames, or 9 for a secret with
;                            "special": true), skipped when the collected secret is the
;                            last one of the scene (that plays the victory fanfare)
;                            (implemented in engine/sfx_secret.asm, $2A30 segment)
;
; Public API:
;   sfx_init         - Reset POKEY & all SFX state
;   sfx_update       - Advance SFX frame (call once per 50 Hz frame)
;   sfx_play_step    - Trigger footstep sound
;   sfx_play_jump    - Trigger jump sound
;   sfx_play_fall    - Start free-fall wind sound (Channel 2)
;   sfx_stop_fall    - Stop free-fall wind sound (Channel 2)
;   sfx_play_death   - Trigger death sound sequence
;   sfx_play_victory - Trigger level-complete victory fanfare (engine/sfx_victory.asm)
;   sfx_play_secret_collect - Trigger the secret-collect blip, A = 0 normal / 1 special
;                             (engine/sfx_secret.asm)
;   sfx_stop_all     - Silence all channels & reset timers
; ==============================================================================

; --- Internal SFX State Variables (Standard RAM) ---
sfx_walk_timer      .byte 0     ; Walk footstep frame countdown (0 = inactive)
sfx_jump_timer      .byte 0     ; Jump pitch sweep countdown (0 = inactive)
sfx_fall_active     .byte 0     ; Fall sound active flag (1 = active, 0 = inactive)
sfx_fall_frame      .byte 0     ; Fall wind modulation cycle counter
sfx_death_timer     .byte 0     ; Death sequence frame countdown (72..0)
; NOTE: sfx_victory_timer lives in engine/sfx_victory.asm ($2A30 segment)

; ==============================================================================
; SFX DATA TABLES
; ==============================================================================

; --- Footstep Tables (3 frames, distortion $C0 = poly4 crisp noise) ---
sfx_step_audf
    .byte $28, $34, $40
sfx_step_audc
    .byte $C5, $C3, $C1

; --- Jump Tables (14 frames, distortion $A0 = pure tone upward sweep) ---
SFX_JUMP_DURATION   = 14

sfx_jump_audf
    .byte $84, $74, $66, $5A, $50, $46, $3E, $36, $30, $2A, $25, $21, $1D, $1A
sfx_jump_audc
    .byte $A7, $A7, $A7, $A6, $A6, $A6, $A5, $A5, $A4, $A4, $A3, $A2, $A1, $A0

; --- Free Fall Wind Modulation Table (8 frames cycle, distortion $80) ---
sfx_fall_audf
    .byte $50, $58, $60, $68, $70, $68, $60, $58
sfx_fall_audc
    .byte $83, $84, $84, $83, $83, $84, $84, $83

; --- Death Sequence Constants & Arpeggio Frequencies ---
SFX_DEATH_DURATION  = 72        ; 72 frames (~1.44s)

; Mournful descending minor notes: E4, D4, C4, A3
sfx_death_notes
    .byte $6A                   ; Note index 0: A3 (AUDF = $6A)
    .byte $58                   ; Note index 1: C4 (AUDF = $58)
    .byte $4E                   ; Note index 2: D4 (AUDF = $4E)
    .byte $42                   ; Note index 3: E4 (AUDF = $42)

; Victory fanfare data (sfx_victory_notes, SFX_VICTORY_DURATION) and its per-frame
; driver sfx_victory_tick live in engine/sfx_victory.asm ($2A30 segment).


; ==============================================================================
; SFX_INIT
; Resets POKEY audio control registers and zeroes all SFX timers.
; ==============================================================================
.proc sfx_init
    lda #3
    sta SKCTL                   ; Enable two-tone mode / normal POKEY operation
    lda #0
    sta AUDCTL                  ; 64 kHz main clock, standard filters
    jsr sfx_stop_all
    rts
.endp


; ==============================================================================
; SFX_STOP_ALL
; Silences all POKEY channels and resets all SFX internal timers.
; ==============================================================================
.proc sfx_stop_all
    lda #0
    sta sfx_walk_timer
    sta sfx_jump_timer
    sta sfx_fall_active
    sta sfx_fall_frame
    sta sfx_death_timer
    sta sfx_victory_timer
    sta sfx_secret_timer

    ; Silence channels 1..4
    sta AUDC1
    sta AUDC2
    sta AUDC3
    sta AUDC4
    sta AUDF1
    sta AUDF2
    sta AUDF3
    sta AUDF4
    rts
.endp


; ==============================================================================
; SFX_PLAY_STEP
; Triggers footstep sound effect on Channel 1.
; Ignored if Death or Jump SFX is currently playing.
; ==============================================================================
.proc sfx_play_step
    lda sfx_death_timer
    bne @ignore
    lda sfx_jump_timer
    bne @ignore

    lda #3
    sta sfx_walk_timer
    lda sfx_step_audf + 0
    sta AUDF1
    lda sfx_step_audc + 0
    sta AUDC1
@ignore
    rts
.endp


; ==============================================================================
; SFX_PLAY_JUMP
; Triggers jump sound effect on Channel 1 (overrides footstep).
; Ignored if Death SFX is currently playing.
; ==============================================================================
.proc sfx_play_jump
    lda sfx_death_timer
    bne @ignore

    lda #0
    sta sfx_walk_timer          ; Preempt walk step sound

    lda #SFX_JUMP_DURATION
    sta sfx_jump_timer

    lda sfx_jump_audf + 0
    sta AUDF1
    lda sfx_jump_audc + 0
    sta AUDC1
@ignore
    rts
.endp


; ==============================================================================
; SFX_PLAY_FALL
; Starts continuous free-fall wind whoosh sound on Channel 2.
; ==============================================================================
.proc sfx_play_fall
    lda sfx_death_timer
    bne @ignore

    lda #1
    sta sfx_fall_active
@ignore
    rts
.endp


; ==============================================================================
; SFX_STOP_FALL
; Stops free-fall wind sound and silences Channel 2.
; ==============================================================================
.proc sfx_stop_fall
    lda sfx_fall_active
    beq @already_stopped

    lda #0
    sta sfx_fall_active
    sta AUDC2
    sta AUDF2
@already_stopped
    rts
.endp


; ==============================================================================
; SFX_PLAY_DEATH
; Initiates death sound sequence (crash impact + descending arpeggio).
; Highest priority: preempts walk, jump, and fall sounds.
; ==============================================================================
.proc sfx_play_death
    ; Clear other sounds (death has the highest priority)
    lda #0
    sta sfx_walk_timer
    sta sfx_jump_timer
    sta sfx_fall_active
    sta sfx_victory_timer
    sta sfx_secret_timer        ; Stop a running collect blip (Channel 3 below)

    lda #SFX_DEATH_DURATION     ; 72 frames
    sta sfx_death_timer

    ; Initial impact crash on Ch 1 and Ch 2
    lda #$10
    sta AUDF1
    lda #$8C                    ; Heavy 17-bit noise crash, volume 12
    sta AUDC1

    lda #$24
    sta AUDF2
    lda #$C8                    ; Poly4 crunch noise, volume 8
    sta AUDC2

    lda #0                      ; Silence the collect blip channel
    sta AUDC3
    sta AUDF3
    rts
.endp


; ==============================================================================
; SFX_UPDATE
; Per-frame update routine for all active sound effects.
; Call once per frame (50 Hz). Preserves X and Y registers.
; ==============================================================================
.proc sfx_update
    txa
    pha
    tya
    pha

    ; --------------------------------------------------------------------------
    ; 1. DEATH SFX UPDATE
    ; --------------------------------------------------------------------------
    lda sfx_death_timer
    beq @chk_victory_sfx

    dec sfx_death_timer
    beq @death_finished

    lda sfx_death_timer
    cmp #64
    bcc @death_arpeggio

    ; --- Impact Crash Decay (frames 71..64) ---
    ; Channel 1: volume decays from $8B down to $84
    sec
    sbc #64                     ; Range 7..0
    lsr                         ; Range 3..0
    ora #$84                    ; Volume $84..$87
    sta AUDC1

    ; Channel 2: volume decays from $C7 down to $C0
    lda sfx_death_timer
    sec
    sbc #64
    lsr
    ora #$C0
    sta AUDC2
    jmp @sfx_exit

@death_arpeggio
    ; Silence Channel 2 (crash finished)
    lda #0
    sta AUDC2
    sta AUDF2

    ; Arpeggio: 4 notes of 16 frames each (frames 63..0)
    ; Note index: (sfx_death_timer - 1) / 16 (0..3)
    lda sfx_death_timer
    sec
    sbc #1
    lsr
    lsr
    lsr
    lsr
    tax
    lda sfx_death_notes,x
    sta AUDF1

    ; Volume decay within the 16-frame note window:
    ; Sub-step: (sfx_death_timer - 1) & $0F -> range 0..15
    lda sfx_death_timer
    sec
    sbc #1
    and #$0F
    lsr
    lsr                         ; Range 0..3
    ora #$A4                    ; Volume $A4..$A7 (pure tone $A0)
    sta AUDC1
    jmp @sfx_exit

@death_finished
    lda #0
    sta AUDC1
    sta AUDF1
    sta AUDC2
    sta AUDF2
    jmp @sfx_exit

    ; --------------------------------------------------------------------------
    ; 2. VICTORY FANFARE UPDATE (Channel 1)
    ; The driver lives in engine/sfx_victory.asm ($2A30 segment) because the
    ; $5000 block has almost no headroom left. It returns Z=1 (A=0) while the
    ; fanfare is inactive, so the remaining sounds still get their turn.
    ; --------------------------------------------------------------------------
@chk_victory_sfx
    jsr sfx_victory_tick
    beq @chk_secret_sfx
    jmp @sfx_exit

    ; --------------------------------------------------------------------------
    ; 3. SECRET-COLLECT BLIP UPDATE (Channel 3)
    ; The driver lives in engine/sfx_secret.asm ($2A30 segment). The blip owns
    ; Channel 3, so it never takes the frame exclusively - unlike the fanfare the
    ; chain always falls through to the sounds below.
    ; --------------------------------------------------------------------------
@chk_secret_sfx
    jsr sfx_secret_tick

    ; --------------------------------------------------------------------------
    ; 4. FREE FALL SFX UPDATE (Channel 2)
    ; Checks player state: active when fall animation is shown.
    ; --------------------------------------------------------------------------
@chk_fall_sfx
    ; Determine if Hero is in fall animation
    lda player_state
    cmp #PLAYER_STATE_FALL
    beq @hero_is_falling
    cmp #PLAYER_STATE_EMERGE
    beq @hero_is_falling

    ; Check if in descent phase of vertical jump
    cmp #PLAYER_STATE_JUMP
    bne @hero_not_falling

    lda player_jump_type
    bne @hero_not_falling       ; Not JUMP_TYPE_UP -> normal jump
    lda player_jump_step
    cmp #13                     ; Step >= 13 is vertical descent (fall animation)
    bcs @hero_is_falling

@hero_not_falling
    ; Not falling: if fall was active, silence Channel 2
    lda sfx_fall_active
    beq @chk_jump_sfx
    lda #0
    sta sfx_fall_active
    sta AUDC2
    sta AUDF2
    jmp @chk_jump_sfx

@hero_is_falling
    lda #1
    sta sfx_fall_active
    inc sfx_fall_frame
    lda sfx_fall_frame
    and #$07
    tax
    lda sfx_fall_audf,x
    sta AUDF2
    lda sfx_fall_audc,x
    sta AUDC2

    ; --------------------------------------------------------------------------
    ; 5. JUMP SFX UPDATE (Channel 1)
    ; --------------------------------------------------------------------------
@chk_jump_sfx
    lda sfx_jump_timer
    beq @chk_walk_sfx

    dec sfx_jump_timer
    beq @jump_finished

    ; Index = SFX_JUMP_DURATION - sfx_jump_timer
    lda #SFX_JUMP_DURATION
    sec
    sbc sfx_jump_timer
    tax
    lda sfx_jump_audf,x
    sta AUDF1
    lda sfx_jump_audc,x
    sta AUDC1
    jmp @sfx_exit               ; Jump occupies Channel 1 -> skip walk

@jump_finished
    lda #0
    sta AUDC1
    sta AUDF1
    jmp @sfx_exit

    ; --------------------------------------------------------------------------
    ; 6. WALK FOOTSTEP SFX UPDATE (Channel 1)
    ; --------------------------------------------------------------------------
@chk_walk_sfx
    lda sfx_walk_timer
    beq @sfx_exit

    dec sfx_walk_timer
    beq @walk_finished

    ; Index = 3 - sfx_walk_timer
    lda #3
    sec
    sbc sfx_walk_timer
    tax
    lda sfx_step_audf,x
    sta AUDF1
    lda sfx_step_audc,x
    sta AUDC1
    jmp @sfx_exit

@walk_finished
    lda #0
    sta AUDC1
    sta AUDF1

@sfx_exit
    pla
    tay
    pla
    tax
    rts
.endp
