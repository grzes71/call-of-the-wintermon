; ==============================================================================
; LIB/AUDIO.ASM — Atari POKEY Audio Manager
; Target: Atari 800XL / 65XE
; Wraps lib/player.asm for high-level song playback and control
; ==============================================================================

    icl 'player.asm'

; --- Start Title Music ---
audio_play_title
    ldx #<music_title_data
    ldy #>music_title_data
    jsr music_init
    jsr music_play
    rts

; --- Start Intro Music ---
audio_play_intro
    ldx #<music_intro_data
    ldy #>music_intro_data
    jsr music_init
    jsr music_play
    rts

; --- Start Game Over (Failure) Music ---
audio_play_gameover
    ldx #<music_gameover_data
    ldy #>music_gameover_data
    jsr music_init
    jsr music_play
    rts

; --- Start Victory (Success) Music ---
audio_play_victory
    ldx #<music_victory_data
    ldy #>music_victory_data
    jsr music_init
    jsr music_play
    rts

; --- Advance Audio Frame (call once per 50 Hz frame) ---
audio_update
    jsr music_update
    rts

; --- Stop Music and Silence POKEY ---
audio_stop
    jsr music_stop
    rts
