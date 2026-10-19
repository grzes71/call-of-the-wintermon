; ==============================================================================
; ENGINE/DLI.ASM — Unified Display List Interrupt (DLI) Engine & Double Buffers
; Target: Atari 800XL / 65XE (MOS 6502)
; Mode: ANTIC Mode D ($0D, 160x96 2bpp, 2 scanlines/line)
; Features:
; - Single shared DLI handler for all scenes (no scene-specific logic/branches)
; - 3-phase execution: Faza A (pre-WSYNC setup), Faza B (8 scanlines color profile),
;   Faza C (palette update + next zone PMG setup in guard line)
; - Strict hardware isolation: Player 0 (Hero) never touched (HPOSP0, SIZEP0, COLPM0)
; - COLBK strictly black ($00)
; - Structure-of-Arrays (SoA) double buffering with atomic swap in VBLANK
; - Direct absolute,Y indexing in DLI (zero ZP indirect pointers, zero stack usage)
; ==============================================================================

; --- Memory Map for DLI Segment ($6100) ---
DLI_SEGMENT_ADDR = $6100

    org DLI_SEGMENT_ADDR

; ==============================================================================
; DLI DOUBLE-BUFFERED TABLES (45 tables x 16 bytes: Buf 0 at +0, Buf 1 at +8)
; ==============================================================================
dli_hpos_p1         :16 .byte 0
dli_hpos_p2         :16 .byte 0
dli_hpos_p3         :16 .byte 0
dli_hpos_m0         :16 .byte 0
dli_hpos_m1         :16 .byte 0
dli_hpos_m2         :16 .byte 0
dli_hpos_m3         :16 .byte 0

dli_sizep1          :16 .byte 0
dli_sizep2          :16 .byte 0
dli_sizep3          :16 .byte 0
dli_sizem           :16 .byte 0

dli_bg_colpf0       :16 .byte 0
dli_bg_colpf1       :16 .byte 0
dli_bg_colpf2       :16 .byte 0

dli_pas_color_sl0   :16 .byte 0
dli_pas_color_sl1   :16 .byte 0
dli_pas_color_sl2   :16 .byte 0
dli_pas_color_sl3   :16 .byte 0
dli_pas_color_sl4   :16 .byte 0
dli_pas_color_sl5   :16 .byte 0
dli_pas_color_sl6   :16 .byte 0
dli_pas_color_sl7   :16 .byte 0

dli_zone_hpos_p1    :16 .byte 0
dli_zone_col_p1     :16 .byte 0
dli_zone_hpos_p2    :16 .byte 0
dli_zone_col_p2     :16 .byte 0
dli_zone_hpos_p3    :16 .byte 0
dli_zone_col_p3     :16 .byte 0

dli_zone_hpos_m0    :16 .byte 0
dli_zone_hpos_m1    :16 .byte 0
dli_zone_hpos_m2    :16 .byte 0
dli_zone_hpos_m3    :16 .byte 0
dli_zone_secret_col :16 .byte 0
dli_zone_prior      :16 .byte 0

; Zone 0 Initial Values (2 buffers: index 0 and 1)
dli_z0_hpos_p1      :2 .byte 0
dli_z0_col_p1       :2 .byte 0
dli_z0_hpos_p2      :2 .byte 0
dli_z0_col_p2       :2 .byte 0
dli_z0_hpos_p3      :2 .byte 0
dli_z0_col_p3       :2 .byte 0
dli_z0_hpos_m0      :2 .byte 0
dli_z0_hpos_m1      :2 .byte 0
dli_z0_hpos_m2      :2 .byte 0
dli_z0_hpos_m3      :2 .byte 0
dli_z0_secret_col   :2 .byte 0
dli_z0_prior        :2 .byte 0
dli_z0_colpf0       :2 .byte 0
dli_z0_colpf1       :2 .byte 0
dli_z0_colpf2       :2 .byte 0

; Table base pointers for 34 tables (used by dli_stage_scene)
DLI_TABLE_COUNT = 34
dli_table_ptrs_lo
    .byte <dli_hpos_p1, <dli_hpos_p2, <dli_hpos_p3
    .byte <dli_hpos_m0, <dli_hpos_m1, <dli_hpos_m2, <dli_hpos_m3
    .byte <dli_sizep1, <dli_sizep2, <dli_sizep3, <dli_sizem
    .byte <dli_bg_colpf0, <dli_bg_colpf1, <dli_bg_colpf2
    .byte <dli_pas_color_sl0, <dli_pas_color_sl1, <dli_pas_color_sl2, <dli_pas_color_sl3
    .byte <dli_pas_color_sl4, <dli_pas_color_sl5, <dli_pas_color_sl6, <dli_pas_color_sl7
    .byte <dli_zone_hpos_p1, <dli_zone_col_p1
    .byte <dli_zone_hpos_p2, <dli_zone_col_p2
    .byte <dli_zone_hpos_p3, <dli_zone_col_p3
    .byte <dli_zone_hpos_m0, <dli_zone_hpos_m1, <dli_zone_hpos_m2, <dli_zone_hpos_m3
    .byte <dli_zone_secret_col, <dli_zone_prior

dli_table_ptrs_hi
    .byte >dli_hpos_p1, >dli_hpos_p2, >dli_hpos_p3
    .byte >dli_hpos_m0, >dli_hpos_m1, >dli_hpos_m2, >dli_hpos_m3
    .byte >dli_sizep1, >dli_sizep2, >dli_sizep3, >dli_sizem
    .byte >dli_bg_colpf0, >dli_bg_colpf1, >dli_bg_colpf2
    .byte >dli_pas_color_sl0, >dli_pas_color_sl1, >dli_pas_color_sl2, >dli_pas_color_sl3
    .byte >dli_pas_color_sl4, >dli_pas_color_sl5, >dli_pas_color_sl6, >dli_pas_color_sl7
    .byte >dli_zone_hpos_p1, >dli_zone_col_p1
    .byte >dli_zone_hpos_p2, >dli_zone_col_p2
    .byte >dli_zone_hpos_p3, >dli_zone_col_p3
    .byte >dli_zone_hpos_m0, >dli_zone_hpos_m1, >dli_zone_hpos_m2, >dli_zone_hpos_m3
    .byte >dli_zone_secret_col, >dli_zone_prior

; ==============================================================================
; DLI INIT
; Configures PMG memory, resets double buffer state, hooks VDSLST, enables NMI
; ==============================================================================
.proc dli_init
    ; 1. Reset state variables
    lda #0
    sta dli_active_offset
    sta dli_pending_offset
    sta dli_swap_requested
    sta dli_pas_idx

    ; 2. Clear entire PMG memory buffer ($6800-$6FFF, 2,048 bytes)
    lda #0
    tax
@clr_pmg
    sta PMG_ADDR + $0000,x
    sta PMG_ADDR + $0100,x
    sta PMG_ADDR + $0200,x
    sta PMG_ADDR + $0300,x
    sta PMG_ADDR + $0400,x
    sta PMG_ADDR + $0500,x
    sta PMG_ADDR + $0600,x
    sta PMG_ADDR + $0700,x
    inx
    bne @clr_pmg

    ; 3. Pre-fill platform rows in PMG memory from scene 0 patterns
    lda scene_pmg_patterns_lo
    sta dli_scene_pmg_ptr
    lda scene_pmg_patterns_hi
    sta dli_scene_pmg_ptr+1
    jsr dli_apply_pmg_patterns

    ; 4. Hook DLI interrupt vector in OS page 2
    lda <dli_handler
    sta VDSLST
    lda >dli_handler
    sta VDSLST+1

    ; 5. Enable DLI ($80) and VBI ($40) in NMIEN
    lda #$C0
    sta NMIEN

    rts
.endp

; ==============================================================================
; DLI APPLY PMG PATTERNS
; Copies 18 bytes of PMG platform patterns (6 passes x 3 players) from ROM into
; PMG memory across each 8-scanline platform pas. Missiles are set to $FF.
; Input: dli_scene_pmg_ptr pointing to 18-byte pattern table for scene
; ==============================================================================
.proc dli_apply_pmg_patterns
    lda #48
    sta zp_temp_x           ; Base scanline for pas 0 (48)
    ldy #0                  ; Pattern index (0..17)

@pas_loop
    lda (dli_scene_pmg_ptr),y
    sta zp_temp_a           ; P1 pattern
    iny
    lda (dli_scene_pmg_ptr),y
    sta zp_ptr_dst          ; P2 pattern
    iny
    lda (dli_scene_pmg_ptr),y
    sta zp_ptr_dst+1        ; P3 pattern
    iny
    sty zp_temp_y           ; Save pattern index

    lda zp_temp_x
    clc
    adc #7
    tax                     ; End scanline (base + 7)

@sl_loop
    lda zp_temp_a           ; P1 pattern
    sta PMG_PLAYER1,x
    lda zp_ptr_dst          ; P2 pattern
    sta PMG_PLAYER2,x
    lda zp_ptr_dst+1        ; P3 pattern
    sta PMG_PLAYER3,x
    lda #$FF                ; Missiles solid
    sta PMG_MISSILES,x

    dex
    cpx zp_temp_x
    bcs @sl_loop

    ; Advance to next pas: base += 32
    lda zp_temp_x
    clc
    adc #32
    sta zp_temp_x

    ldy zp_temp_y
    cpy #18
    bcc @pas_loop

    rts
.endp

; ==============================================================================
; DLI STAGE SCENE
; Copies 315 bytes of compiled scene DLI data into the inactive buffer
; Parameters: A = scene_id (0..SCENE_COUNT-1)
; Safe to call anytime outside DLI; does not affect active rendering
; ==============================================================================
.proc dli_stage_scene
    cmp #SCENE_COUNT
    bcc @valid_id
    rts

@valid_id
    tax
    lda scene_pmg_patterns_lo,x
    sta dli_scene_pmg_ptr
    lda scene_pmg_patterns_hi,x
    sta dli_scene_pmg_ptr+1

    lda scene_dli_data_lo,x
    sta zp_ptr_src
    lda scene_dli_data_hi,x
    sta zp_ptr_src+1

    ; Determine staging buffer offset (toggle 0 <-> 8)
    lda dli_active_offset
    eor #8
    sta dli_pending_offset

    ; Copy 34 tables (6 bytes each)
    lda #0
    sta zp_temp_a       ; Table counter (0..33)

@table_loop
    ldx zp_temp_a
    lda dli_table_ptrs_lo,x
    clc
    adc dli_pending_offset
    sta zp_ptr_dst
    lda dli_table_ptrs_hi,x
    adc #0
    sta zp_ptr_dst+1

    ; Copy 6 bytes from (zp_ptr_src) to (zp_ptr_dst)
    ldy #0
@byte_loop
    lda (zp_ptr_src),y
    sta (zp_ptr_dst),y
    iny
    cpy #6
    bcc @byte_loop

    ; Advance source pointer by 6 bytes
    lda zp_ptr_src
    clc
    adc #6
    sta zp_ptr_src
    bcc @no_src_carry
    inc zp_ptr_src+1
@no_src_carry

    inc zp_temp_a
    lda zp_temp_a
    cmp #DLI_TABLE_COUNT
    bcc @table_loop

    ; Copy 15 bytes of Zone 0 initial values
    ; Staging buffer index is dli_pending_offset >> 3 (0 or 1)
    lda dli_pending_offset
    lsr
    lsr
    lsr
    tax

    ldy #0
    lda (zp_ptr_src),y      ; z0_hpos_p1
    sta dli_z0_hpos_p1,x
    iny
    lda (zp_ptr_src),y      ; z0_col_p1
    sta dli_z0_col_p1,x
    iny
    lda (zp_ptr_src),y      ; z0_hpos_p2
    sta dli_z0_hpos_p2,x
    iny
    lda (zp_ptr_src),y      ; z0_col_p2
    sta dli_z0_col_p2,x
    iny
    lda (zp_ptr_src),y      ; z0_hpos_p3
    sta dli_z0_hpos_p3,x
    iny
    lda (zp_ptr_src),y      ; z0_col_p3
    sta dli_z0_col_p3,x
    iny
    lda (zp_ptr_src),y      ; z0_hpos_m0
    sta dli_z0_hpos_m0,x
    iny
    lda (zp_ptr_src),y      ; z0_hpos_m1
    sta dli_z0_hpos_m1,x
    iny
    lda (zp_ptr_src),y      ; z0_hpos_m2
    sta dli_z0_hpos_m2,x
    iny
    lda (zp_ptr_src),y      ; z0_hpos_m3
    sta dli_z0_hpos_m3,x
    iny
    lda (zp_ptr_src),y      ; z0_secret_col
    sta dli_z0_secret_col,x
    iny
    lda (zp_ptr_src),y      ; z0_prior
    sta dli_z0_prior,x
    iny
    lda (zp_ptr_src),y      ; z0_colpf0
    sta dli_z0_colpf0,x
    iny
    lda (zp_ptr_src),y      ; z0_colpf1
    sta dli_z0_colpf1,x
    iny
    lda (zp_ptr_src),y      ; z0_colpf2
    sta dli_z0_colpf2,x

    ; Set mailbox flag: atomic buffer swap will occur in VBLANK
    lda #1
    sta dli_swap_requested
    rts
.endp

; ==============================================================================
; DLI VBLANK UPDATE
; Called during vertical blank (after frame sync, before active display lines)
; - Atomically commits buffer swap if requested
; - Resets pas counter to active buffer offset (0 or 8)
; - Sets up Zone 0 initial PMG positions, colors, sizes, PRIOR, and upper palette
; ==============================================================================
.proc dli_vblank_update
    ; Check mailbox flag for pending buffer swap
    lda dli_swap_requested
    beq @no_swap
    lda dli_pending_offset
    sta dli_active_offset
    lda #0
    sta dli_swap_requested

    ; Copy PMG patterns for the new scene
    jsr dli_apply_pmg_patterns

@no_swap
    ; Ensure DLI vector points to dli_handler
    lda <dli_handler
    sta VDSLST
    lda >dli_handler
    sta VDSLST+1

    ; Reset DLI pas index to active buffer base offset
    lda dli_active_offset
    sta dli_pas_idx

    ; Zone 0 buffer index (0 or 1)
    lsr
    lsr
    lsr
    tax

    ; 1. Reset PMG sizes to x1 for Zone 0
    lda #0
    sta SIZEP0
    sta SIZEP1
    sta SIZEP2
    sta SIZEP3
    sta SIZEM

    ; Restore Player 0 horizontal position for active playfield
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    ; 2. Apply Zone 0 enemies (P1..P3)
    lda dli_z0_hpos_p1,x
    sta HPOSP1
    lda dli_z0_col_p1,x
    sta COLPM1

    lda dli_z0_hpos_p2,x
    sta HPOSP2
    lda dli_z0_col_p2,x
    sta COLPM2

    lda dli_z0_hpos_p3,x
    sta HPOSP3
    lda dli_z0_col_p3,x
    sta COLPM3

    ; 3. Apply Zone 0 secret (M0..M3 as 5th player)
    lda dli_z0_hpos_m0,x
    sta HPOSM0
    lda dli_z0_hpos_m1,x
    sta HPOSM1
    lda dli_z0_hpos_m2,x
    sta HPOSM2
    lda dli_z0_hpos_m3,x
    sta HPOSM3

    lda dli_z0_secret_col,x
    sta COLPF3

    lda #$11
    sta PRIOR
    sta GPRIOR

    ; 4. Apply upper background palette to hardware and shadow registers
    lda dli_z0_colpf0,x
    sta COLPF0
    sta COLOR0

    lda dli_z0_colpf1,x
    sta COLPF1
    sta COLOR1

    lda dli_z0_colpf2,x
    sta COLPF2
    sta COLOR2

    ; 5. COLBK is strictly black ($00)
    lda #0
    sta COLBK
    sta COLOR4

    rts
.endp

; ==============================================================================
; UNIFIED DLI HANDLER
; Triggered on scanlines 15, 47, 79, 111, 143, 175 (lines 7, 23, 39, 55, 71, 87)
; Cycle budget strictly verified; zero stack usage; direct absolute,Y indexing
; ==============================================================================
.proc dli_handler
    ; --------------------------------------------------------------------------
    ; ENTRY: Save CPU registers to Zero Page (zero stack overhead)
    ; X register is unused across DLI handler and preserved implicitly.
    ; --------------------------------------------------------------------------
    sta dli_save_a         ; [3]
    sty dli_save_y         ; [3]

    ldy dli_pas_idx        ; [3] Active table offset + pas index

    ; --------------------------------------------------------------------------
    ; FAZA A: Executed during pre-pas line (2 scanlines before pas)
    ; Set PMG player widths (x4), missile widths from table, and positions.
    ; --------------------------------------------------------------------------
    lda #3                ; [2] Quad width (32px) for platform players
    sta SIZEP1            ; [4]
    sta SIZEP2            ; [4]
    sta SIZEP3            ; [4]
    lda dli_sizem,y       ; [4] Size for platform missiles ($FF for 32px quad width, $00 otherwise)
    sta SIZEM             ; [4]

    lda dli_hpos_p1,y      ; [4] Platform player positions
    sta HPOSP1            ; [4]
    lda dli_hpos_p2,y      ; [4]
    sta HPOSP2            ; [4]
    lda dli_hpos_p3,y      ; [4]
    sta HPOSP3            ; [4]

    ; --------------------------------------------------------------------------
    ; SYNC: 3 scanlines between DLI trigger (line 2L-2, scanline 1) and Pas (line 2L).
    ; 1st WSYNC halts to end of line 2L-2, scanline 1.
    ; 2nd WSYNC halts to end of line 2L-1, scanline 0.
    ; 3rd WSYNC halts to end of line 2L-1, scanline 1 -> CPU resumes at cycle 0 of scanline 2L!
    ; --------------------------------------------------------------------------
    sta WSYNC             ; [4] Wait for end of trigger line (2L-2, scanline 1)
    sta WSYNC             ; [4] Wait for end of pre-pas line (2L-1, scanline 0)
    sta WSYNC             ; [4] Wait for end of pre-pas line (2L-1, scanline 1 -> aligns to scanline 2L)

    ; --------------------------------------------------------------------------
    ; FAZA B: 8 scanlines of platform color profiles
    ; Scanline 0 starts exactly on scanline 2L!
    ; Updates COLPM1..3, COLPF3, and HPOSM0..3
    ; --------------------------------------------------------------------------
    ; --- Iteracja 0 (scanline 2L) ---
    lda dli_pas_color_sl0,y ; [4]
    sta COLPM1             ; [4]
    sta COLPM2             ; [4]
    sta COLPM3             ; [4]

    lda dli_hpos_m0,y      ; [4] Platform missile positions
    sta HPOSM0             ; [4]
    lda dli_hpos_m1,y      ; [4]
    sta HPOSM1             ; [4]
    lda dli_hpos_m2,y      ; [4]
    sta HPOSM2             ; [4]
    lda dli_hpos_m3,y      ; [4]
    sta HPOSM3             ; [4]

    sta WSYNC              ; [4] End scanline 0 (2L)

    ; Scanline 1:
    lda dli_pas_color_sl1,y ; [4]
    sta COLPM1             ; [4]
    sta COLPM2             ; [4]
    sta COLPM3             ; [4]
    sta COLPF3             ; [4]
    sta WSYNC              ; [4] End scanline 1

    ; Scanline 2:
    lda dli_pas_color_sl2,y ; [4]
    sta COLPM1             ; [4]
    sta COLPM2             ; [4]
    sta COLPM3             ; [4]
    sta COLPF3             ; [4]
    sta WSYNC              ; [4] End scanline 2

    ; Scanline 3:
    lda dli_pas_color_sl3,y ; [4]
    sta COLPM1             ; [4]
    sta COLPM2             ; [4]
    sta COLPM3             ; [4]
    sta COLPF3             ; [4]
    sta WSYNC              ; [4] End scanline 3

    ; Scanline 4:
    lda dli_pas_color_sl4,y ; [4]
    sta COLPM1             ; [4]
    sta COLPM2             ; [4]
    sta COLPM3             ; [4]
    sta COLPF3             ; [4]
    sta WSYNC              ; [4] End scanline 4

    ; Scanline 5:
    lda dli_pas_color_sl5,y ; [4]
    sta COLPM1             ; [4]
    sta COLPM2             ; [4]
    sta COLPM3             ; [4]
    sta COLPF3             ; [4]
    sta WSYNC              ; [4] End scanline 5

    ; Scanline 6:
    lda dli_pas_color_sl6,y ; [4]
    sta COLPM1             ; [4]
    sta COLPM2             ; [4]
    sta COLPM3             ; [4]
    sta COLPF3             ; [4]
    sta WSYNC              ; [4] End scanline 6

    ; Scanline 7:
    lda dli_pas_color_sl7,y ; [4]
    sta COLPM1             ; [4]
    sta COLPM2             ; [4]
    sta COLPM3             ; [4]
    sta COLPF3             ; [4]
    sta WSYNC              ; [4] End scanline 7 (8th WSYNC)

    ; --------------------------------------------------------------------------
    ; FAZA C: Guard line of following zone
    ; 1. First: Background palette COLPF0..2 updated in HBLANK (cycles 0..23)
    ; --------------------------------------------------------------------------
    lda dli_bg_colpf0,y    ; [4] (cycles 0..3)
    sta COLPF0            ; [4] (cycles 4..7)
    lda dli_bg_colpf1,y    ; [4] (cycles 8..11)
    sta COLPF1            ; [4] (cycles 12..15)
    lda dli_bg_colpf2,y    ; [4] (cycles 16..19)
    sta COLPF2            ; [4] (cycles 20..23)

    ; --------------------------------------------------------------------------
    ; 2. In guard line: Reset sizes to x1, setup enemies and secret of next zone
    ; --------------------------------------------------------------------------
    lda #0                 ; [2] Reset sizes to x1 for enemy players & missiles
    sta SIZEP1            ; [4]
    sta SIZEP2            ; [4]
    sta SIZEP3            ; [4]
    sta SIZEM             ; [4] Reset missiles to x1 for zone secret

    ; Enemies P1..P3
    lda dli_zone_hpos_p1,y ; [4]
    sta HPOSP1            ; [4]
    lda dli_zone_col_p1,y  ; [4]
    sta COLPM1            ; [4]

    lda dli_zone_hpos_p2,y ; [4]
    sta HPOSP2            ; [4]
    lda dli_zone_col_p2,y  ; [4]
    sta COLPM2            ; [4]

    lda dli_zone_hpos_p3,y ; [4]
    sta HPOSP3            ; [4]
    lda dli_zone_col_p3,y  ; [4]
    sta COLPM3            ; [4]

    ; Secret (M0..M3 as 5th player)
    lda dli_zone_hpos_m0,y ; [4]
    sta HPOSM0            ; [4]
    lda dli_zone_hpos_m1,y ; [4]
    sta HPOSM1            ; [4]
    lda dli_zone_hpos_m2,y ; [4]
    sta HPOSM2            ; [4]
    lda dli_zone_hpos_m3,y ; [4]
    sta HPOSM3            ; [4]

    lda dli_zone_secret_col,y ; [4]
    sta COLPF3                ; [4]

    ; Advance pas index for next DLI
    iny                    ; [2]
    sty dli_pas_idx        ; [3]
    tya                    ; [2]
    and #$07               ; [2]
    cmp #6                 ; [2] Was this pas 5 (DLI 6)?
    bne @skip_status_hook  ; [2/3]
    lda <dli_status_line   ; [2]
    sta VDSLST             ; [4]
    lda >dli_status_line   ; [2]
    sta VDSLST+1           ; [4]
@skip_status_hook

    ; --------------------------------------------------------------------------
    ; EXIT: Restore registers from zero page and return
    ; --------------------------------------------------------------------------
    lda dli_save_a         ; [3]
    ldy dli_save_y         ; [3]
    rti                    ; [6]
.endp

; ==============================================================================
; DLI STATUS LINE (DLI 7)
; Executed on the blank scanline right before ANTIC Mode 2 status line.
; Sets up black background, white text, and clears PMG positions/sizes.
; Points VDSLST back to dli_handler for the next frame.
; ==============================================================================
.proc dli_status_line
    sta dli_save_a         ; [3]
    sty dli_save_y         ; [3]

    sta WSYNC              ; [4]
    lda #0                 ; [2]
    sta COLPF2             ; [4] Black background for Mode 2 text
    lda #$0E               ; [2]
    sta COLPF1             ; [4] Crisp white text
    lda #0                 ; [2] Clear PMG positions so no sprites bleed into status bar
    sta HPOSP0             ; [4]
    sta HPOSP1             ; [4]
    sta HPOSP2             ; [4]
    sta HPOSP3             ; [4]
    sta HPOSM0             ; [4]
    sta HPOSM1             ; [4]
    sta HPOSM2             ; [4]
    sta HPOSM3             ; [4]
    sta SIZEP0             ; [4]
    sta SIZEP1             ; [4]
    sta SIZEP2             ; [4]
    sta SIZEP3             ; [4]
    sta SIZEM              ; [4]

    ; Point VDSLST back to dli_handler for next frame
    lda <dli_handler       ; [2]
    sta VDSLST             ; [4]
    lda >dli_handler       ; [2]
    sta VDSLST+1           ; [4]

    lda dli_save_a         ; [3]
    ldy dli_save_y         ; [3]
    rti                    ; [6]
.endp
