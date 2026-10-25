; ==============================================================================
; SCROLL.ASM — platform row colour scroll (profiles with "scroll" set)
; Target: Atari 800XL / 65XE (MOS 6502)
;
; The compiler emits one scroll code per platform row (6 bytes per scene,
; scene_<scene>_plat_scroll): 0 = static, 1 = slow (10 frames/step), 2 = medium (5),
; 3 = fast (2). A step rotates the row's 8 scanline colours (dli_pas_color_sl0..7) by one
; position UP in both DLI double buffers, so a row's gradient scrolls while the rest of the
; screen stays still.
;
; The phase is global for the whole game: scroll_step is never reset when a scene changes.
; dli_stage_scene reloads the static colours, so scroll_reset re-applies the accumulated
; step right after staging (scroll_reapply).
; ==============================================================================

MAX_PAS = 6
SCROLL_STEPS = 8

; Frames per step, indexed by the scroll code (0 is never used: static rows are skipped)
plat_scroll_periods
    .byte 0, 10, 5, 2

plat_scroll_speed  :MAX_PAS .byte 0   ; scroll code of each pas (copied from the scene)
plat_scroll_timer  :MAX_PAS .byte 0   ; frames left until the next step
plat_scroll_step   :MAX_PAS .byte 0   ; accumulated steps (0..7), global across scenes
plat_scroll_scene  .byte $FF          ; scene the codes were copied from ($FF = not staged yet)

; ==============================================================================
; ROTATE ONE ROW (PAS) UP BY ONE POSITION IN ONE DLI BUFFER
; value[s] = value[s+1] for s = 0..6, value[7] = old value[0].
; The 8 colour tables are contiguous with a 16 byte stride (6 pas + 2 padding per buffer,
; see engine/dli.asm); the second buffer lives 8 bytes further into every table.
; Input: A = pas index (0..5), zp_temp_x = buffer offset (0 or 8)
; Preserves: X
; ==============================================================================
.proc scroll_rotate_row
    clc
    adc zp_temp_x               ; A = pas + buffer offset
    clc
    adc #<dli_pas_color_sl0
    sta zp_ptr_src
    lda #>dli_pas_color_sl0
    adc #0
    sta zp_ptr_src+1

    ldy #0
    lda (zp_ptr_src),y          ; value[0] - it moves to the last slot
    sta zp_temp_a

    ; dst = src - 16, so (dst),y reads slot y/16 and writes slot y/16 - 1
    lda zp_ptr_src
    sec
    sbc #16
    sta zp_ptr_dst
    lda zp_ptr_src+1
    sbc #0
    sta zp_ptr_dst+1

    ldy #16
@shift
    lda (zp_ptr_src),y          ; value[s]
    sta (zp_ptr_dst),y          ; value[s-1] = value[s]
    tya
    clc
    adc #16
    tay
    cpy #128
    bcc @shift

    ldy #112
    lda zp_temp_a
    sta (zp_ptr_src),y          ; value[7] = old value[0]
    rts
.endp

; ==============================================================================
; SCROLL REAPPLY
; Re-applies every row's accumulated step to the freshly staged colours.
; Called by scroll_reset after dli_stage_scene.
; Preserves: X
; ==============================================================================
.proc scroll_reapply
    ldx #0
@row
    cpx #MAX_PAS
    bcs @done
    lda plat_scroll_speed,x
    beq @next                   ; static row
    lda plat_scroll_step,x
    beq @next                   ; nothing accumulated yet
    sta zp_temp_y
@rotate
    lda #0
    sta zp_temp_x
    txa
    jsr scroll_rotate_row
    lda #8
    sta zp_temp_x
    txa
    jsr scroll_rotate_row
    dec zp_temp_y
    bne @rotate
@next
    inx
    jmp @row
@done
    rts
.endp

; ==============================================================================
; SCROLL RESET
; Copies the active scene's scroll codes and arms the step timers. The accumulated
; step is intentionally kept: the animation phase is global for the whole game.
; Called by dli_stage_scene.
; Preserves: X
; ==============================================================================
.proc scroll_reset
    ldx active_scene_id
    lda scene_plat_scroll_lo,x
    sta zp_ptr_src
    lda scene_plat_scroll_hi,x
    sta zp_ptr_src+1
    ldy #MAX_PAS-1
@copy
    lda (zp_ptr_src),y
    sta plat_scroll_speed,y
    dey
    bpl @copy

    ldx #MAX_PAS-1
@arm
    ldy plat_scroll_speed,x
    lda plat_scroll_periods,y
    sta plat_scroll_timer,x
    dex
    bpl @arm

    jsr scroll_reapply
    rts
.endp

; ==============================================================================
; SCROLL UPDATE
; One frame of the colour scroll: counts down each scrolling row's timer and rotates
; the row up by one position (both buffers) when it expires.
; Called once per frame from dli_vblank_update.
; Preserves: X (Y and A are clobbered)
; ==============================================================================
.proc scroll_update
    ; Scene change detection: dli_stage_scene overwrites the colours with the scene's static
    ; values, so on every change re-copy the scroll codes, re-arm the timers and re-apply the
    ; accumulated (global) phase. $FF forces the first frame to run it too.
    lda active_scene_id
    cmp plat_scroll_scene
    beq @same_scene
    sta plat_scroll_scene
    jsr scroll_reset
@same_scene

    inc zp_frame_cnt
    ldx #0
@row
    cpx #MAX_PAS
    bcs @done
    lda plat_scroll_speed,x
    beq @next                   ; static row
    dec plat_scroll_timer,x
    bne @next

    ; Reload the period and advance the (global) step
    ldy plat_scroll_speed,x
    lda plat_scroll_periods,y
    sta plat_scroll_timer,x
    lda plat_scroll_step,x
    clc
    adc #1
    and #SCROLL_STEPS-1
    sta plat_scroll_step,x

    ; Rotate this row in both DLI buffers
    lda #0
    sta zp_temp_x
    txa
    jsr scroll_rotate_row
    lda #8
    sta zp_temp_x
    txa
    jsr scroll_rotate_row

@next
    inx
    jmp @row
@done
    rts
.endp
