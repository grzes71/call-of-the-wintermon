; ==============================================================================
; ENGINE/HUD_DLI.ASM — DLI Handlers for Mode D Narrow HUD
; Target: Atari 800XL / 65XE (MOS 6502)
; ==============================================================================

; ==============================================================================
; HUD Palette Configuration
; Modify these equates to customize the in-game Mode D HUD colors.
; ==============================================================================
HUD_COLOR_BK    = $00          ; Black background (COLBK)
HUD_COLOR_HEART = $34          ; Player hearts (COLPF0, color %01)
HUD_COLOR_TEXT  = $1C          ; Crisp white for 'x' and digits (COLPF1, color %10)
HUD_COLOR_DISC  = $88          ; Blue for special discs (COLPF2, color %11)

; ==============================================================================
; DLI STATUS LINE / HUD START (DLI 7)
; Executed on the 8 blank scanlines margin right before ANTIC Mode D HUD.
; Switches DMACTL to Narrow playfield ($21 = 32 bytes/line), sets HUD palette
; (black background, red hearts, white text, gold specials), and clears PMG positions/sizes.
; Chains VDSLST to dli_hud_restore (DLI 8) for the post-HUD blank scanlines.
; ==============================================================================
.proc dli_status_line
    sta dli_save_a         ; [3]
    sty dli_save_y         ; [3]

    ; Switch to Narrow playfield ($21) and disable PMG latching during the blank margin
    lda #$21               ; [2] Enable DL DMA | Narrow playfield (32 bytes / line)
    sta DMACTL             ; [4]
    lda #0                 ; [2] Disable PMG latching in GTIA
    sta GRACTL             ; [4]

    lda #HUD_COLOR_BK      ; [2] Background color for HUD
    sta COLBK              ; [4]
    lda #HUD_COLOR_HEART   ; [2] Hearts (COLPF0, color %01)
    sta COLPF0             ; [4]
    lda #HUD_COLOR_TEXT    ; [2] Text and digits (COLPF1, color %10)
    sta COLPF1             ; [4]
    lda #HUD_COLOR_DISC    ; [2] Special discs (COLPF2, color %11)
    sta COLPF2             ; [4]

    ldy #7                 ; [2]
    lda #0                 ; [2] Clear PMG positions so no sprites bleed into HUD
@cl_hpos
    sta HPOSP0,y           ; [4]
    dey                    ; [2]
    bpl @cl_hpos           ; [2/3]

    ; Chain VDSLST to dli_hud_restore (DLI 8)
    lda <dli_hud_restore   ; [2]
    sta VDSLST             ; [4]
    lda >dli_hud_restore   ; [2]
    sta VDSLST+1           ; [4]

    lda dli_save_a         ; [3]
    ldy dli_save_y         ; [3]
    rti                    ; [6]
.endp

; ==============================================================================
; DLI HUD RESTORE (DLI 8)
; Executed on the bottom 8 blank scanlines margin right under the HUD.
; Restores DMACTL to Normal playfield width + PMG DMA ($3E = 40 bytes/line).
; Restores GRACTL to 3 and points VDSLST back to dli_handler for next frame.
; ==============================================================================
.proc dli_hud_restore
    sta dli_save_a         ; [3]
    sty dli_save_y         ; [3]

    lda #$3E               ; [2] Enable DL DMA | 1-line PMG | Normal playfield (40 bytes / line)
    sta DMACTL             ; [4]
    lda #3                 ; [2] Re-enable PMG latching in GTIA
    sta GRACTL             ; [4]

    ; Point VDSLST back to dli_handler and reset pas index for next frame
    lda dli_active_offset  ; [3]
    sta dli_pas_idx        ; [3]
    lda <dli_handler       ; [2]
    sta VDSLST             ; [4]
    lda >dli_handler       ; [2]
    sta VDSLST+1           ; [4]

    lda dli_save_a         ; [3]
    ldy dli_save_y         ; [3]
    rti                    ; [6]
.endp
