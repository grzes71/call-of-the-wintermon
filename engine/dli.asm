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

dli_pas_c1_sl0      :16 .byte 0
dli_pas_c1_sl1      :16 .byte 0
dli_pas_c1_sl2      :16 .byte 0
dli_pas_c1_sl3      :16 .byte 0
dli_pas_c1_sl4      :16 .byte 0
dli_pas_c1_sl5      :16 .byte 0
dli_pas_c1_sl6      :16 .byte 0
dli_pas_c1_sl7      :16 .byte 0

dli_pas_c2_sl0      :16 .byte 0
dli_pas_c2_sl1      :16 .byte 0
dli_pas_c2_sl2      :16 .byte 0
dli_pas_c2_sl3      :16 .byte 0
dli_pas_c2_sl4      :16 .byte 0
dli_pas_c2_sl5      :16 .byte 0
dli_pas_c2_sl6      :16 .byte 0
dli_pas_c2_sl7      :16 .byte 0

dli_pas_c3_sl0      :16 .byte 0
dli_pas_c3_sl1      :16 .byte 0
dli_pas_c3_sl2      :16 .byte 0
dli_pas_c3_sl3      :16 .byte 0
dli_pas_c3_sl4      :16 .byte 0
dli_pas_c3_sl5      :16 .byte 0
dli_pas_c3_sl6      :16 .byte 0
dli_pas_c3_sl7      :16 .byte 0

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

; Table base pointers for 50 tables (used by dli_stage_scene)
DLI_TABLE_COUNT = 50
dli_table_ptrs_lo
    .byte <dli_hpos_p1, <dli_hpos_p2, <dli_hpos_p3
    .byte <dli_hpos_m0, <dli_hpos_m1, <dli_hpos_m2, <dli_hpos_m3
    .byte <dli_sizep1, <dli_sizep2, <dli_sizep3, <dli_sizem
    .byte <dli_bg_colpf0, <dli_bg_colpf1, <dli_bg_colpf2
    .byte <dli_pas_c1_sl0, <dli_pas_c1_sl1, <dli_pas_c1_sl2, <dli_pas_c1_sl3
    .byte <dli_pas_c1_sl4, <dli_pas_c1_sl5, <dli_pas_c1_sl6, <dli_pas_c1_sl7
    .byte <dli_pas_c2_sl0, <dli_pas_c2_sl1, <dli_pas_c2_sl2, <dli_pas_c2_sl3
    .byte <dli_pas_c2_sl4, <dli_pas_c2_sl5, <dli_pas_c2_sl6, <dli_pas_c2_sl7
    .byte <dli_pas_c3_sl0, <dli_pas_c3_sl1, <dli_pas_c3_sl2, <dli_pas_c3_sl3
    .byte <dli_pas_c3_sl4, <dli_pas_c3_sl5, <dli_pas_c3_sl6, <dli_pas_c3_sl7
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
    .byte >dli_pas_c1_sl0, >dli_pas_c1_sl1, >dli_pas_c1_sl2, >dli_pas_c1_sl3
    .byte >dli_pas_c1_sl4, >dli_pas_c1_sl5, >dli_pas_c1_sl6, >dli_pas_c1_sl7
    .byte >dli_pas_c2_sl0, >dli_pas_c2_sl1, >dli_pas_c2_sl2, >dli_pas_c2_sl3
    .byte >dli_pas_c2_sl4, >dli_pas_c2_sl5, >dli_pas_c2_sl6, >dli_pas_c2_sl7
    .byte >dli_pas_c3_sl0, >dli_pas_c3_sl1, >dli_pas_c3_sl2, >dli_pas_c3_sl3
    .byte >dli_pas_c3_sl4, >dli_pas_c3_sl5, >dli_pas_c3_sl6, >dli_pas_c3_sl7
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

    ; 3. Pre-fill platform rows in PMG memory (8 scanlines solid per pas)
    ; Pas 0: lines 8..11   -> scanlines 16..23 ($10..$17)
    ; Pas 1: lines 24..27  -> scanlines 48..55 ($30..$37)
    ; Pas 2: lines 40..43  -> scanlines 80..87 ($50..$57)
    ; Pas 3: lines 56..59  -> scanlines 112..119 ($70..$77)
    ; Pas 4: lines 72..75  -> scanlines 144..151 ($90..$97)
    ; Pas 5: lines 88..91  -> scanlines 176..183 ($B0..$B7)
    ldx #7
@fill_pas
    lda #$FF            ; Solid pixels for player platforms
    sta PMG_PLAYER1 + 16,x
    sta PMG_PLAYER1 + 48,x
    sta PMG_PLAYER1 + 80,x
    sta PMG_PLAYER1 + 112,x
    sta PMG_PLAYER1 + 144,x
    sta PMG_PLAYER1 + 176,x

    sta PMG_PLAYER2 + 16,x
    sta PMG_PLAYER2 + 48,x
    sta PMG_PLAYER2 + 80,x
    sta PMG_PLAYER2 + 112,x
    sta PMG_PLAYER2 + 144,x
    sta PMG_PLAYER2 + 176,x

    sta PMG_PLAYER3 + 16,x
    sta PMG_PLAYER3 + 48,x
    sta PMG_PLAYER3 + 80,x
    sta PMG_PLAYER3 + 112,x
    sta PMG_PLAYER3 + 144,x
    sta PMG_PLAYER3 + 176,x

    lda #$FF            ; All 4 missiles solid
    sta PMG_MISSILES + 16,x
    sta PMG_MISSILES + 48,x
    sta PMG_MISSILES + 80,x
    sta PMG_MISSILES + 112,x
    sta PMG_MISSILES + 144,x
    sta PMG_MISSILES + 176,x
    dex
    bpl @fill_pas

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
    lda scene_dli_data_lo,x
    sta zp_ptr_src
    lda scene_dli_data_hi,x
    sta zp_ptr_src+1

    ; Determine staging buffer offset (toggle 0 <-> 8)
    lda dli_active_offset
    eor #8
    sta dli_pending_offset

    ; Copy 45 tables (6 bytes each)
    lda #0
    sta zp_temp_a       ; Table counter (0..44)

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

@no_swap
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
    sta SIZEP1
    sta SIZEP2
    sta SIZEP3
    sta SIZEM

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

    lda dli_z0_prior,x
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
    ; --------------------------------------------------------------------------
    sta dli_save_a         ; [3]
    stx dli_save_x         ; [3]
    sty dli_save_y         ; [3]

    ldy dli_pas_idx        ; [3] Active table offset + pas index

    ; --------------------------------------------------------------------------
    ; FAZA A: Last scanline before pas (pre-WSYNC setup)
    ; Set PMG widths (x4), positions for 3 channels, PRIOR (bit 4 cleared)
    ; --------------------------------------------------------------------------
    lda dli_sizep1,y      ; [4] Size for platform player 1
    sta SIZEP1            ; [4]
    lda dli_sizep2,y      ; [4] Size for platform player 2
    sta SIZEP2            ; [4]
    lda dli_sizep3,y      ; [4] Size for platform player 3
    sta SIZEP3            ; [4]
    lda dli_sizem,y       ; [4] Size for platform missiles
    sta SIZEM             ; [4]

    lda dli_hpos_p1,y      ; [4] Platform player positions
    sta HPOSP1            ; [4]
    lda dli_hpos_p2,y      ; [4]
    sta HPOSP2            ; [4]
    lda dli_hpos_p3,y      ; [4]
    sta HPOSP3            ; [4]

    lda dli_hpos_m0,y      ; [4] Platform missile positions
    sta HPOSM0            ; [4]
    lda dli_hpos_m1,y      ; [4]
    sta HPOSM1            ; [4]
    lda dli_hpos_m2,y      ; [4]
    sta HPOSM2            ; [4]
    lda dli_hpos_m3,y      ; [4]
    sta HPOSM3            ; [4]

    lda #$01               ; [2] PRIOR: bit 4 = 0 (no 5th player), Hero/P0 in front
    sta PRIOR             ; [4]

    sta WSYNC             ; [4] Wait for scanline 0 of the pas

    ; --------------------------------------------------------------------------
    ; FAZA B: 8 scanlines of platform color profiles
    ; Updates COLPM1..3 in HBLANK (cycles 0..23) of each scanline
    ; --------------------------------------------------------------------------
    ; Scanline 0:
    lda dli_pas_c1_sl0,y   ; [4]
    sta COLPM1            ; [4]
    lda dli_pas_c2_sl0,y   ; [4]
    sta COLPM2            ; [4]
    lda dli_pas_c3_sl0,y   ; [4]
    sta COLPM3            ; [4]
    sta WSYNC             ; [4] End scanline 0

    ; Scanline 1:
    lda dli_pas_c1_sl1,y   ; [4]
    sta COLPM1            ; [4]
    lda dli_pas_c2_sl1,y   ; [4]
    sta COLPM2            ; [4]
    lda dli_pas_c3_sl1,y   ; [4]
    sta COLPM3            ; [4]
    sta WSYNC             ; [4] End scanline 1

    ; Scanline 2:
    lda dli_pas_c1_sl2,y   ; [4]
    sta COLPM1            ; [4]
    lda dli_pas_c2_sl2,y   ; [4]
    sta COLPM2            ; [4]
    lda dli_pas_c3_sl2,y   ; [4]
    sta COLPM3            ; [4]
    sta WSYNC             ; [4] End scanline 2

    ; Scanline 3:
    lda dli_pas_c1_sl3,y   ; [4]
    sta COLPM1            ; [4]
    lda dli_pas_c2_sl3,y   ; [4]
    sta COLPM2            ; [4]
    lda dli_pas_c3_sl3,y   ; [4]
    sta COLPM3            ; [4]
    sta WSYNC             ; [4] End scanline 3

    ; Scanline 4:
    lda dli_pas_c1_sl4,y   ; [4]
    sta COLPM1            ; [4]
    lda dli_pas_c2_sl4,y   ; [4]
    sta COLPM2            ; [4]
    lda dli_pas_c3_sl4,y   ; [4]
    sta COLPM3            ; [4]
    sta WSYNC             ; [4] End scanline 4

    ; Scanline 5:
    lda dli_pas_c1_sl5,y   ; [4]
    sta COLPM1            ; [4]
    lda dli_pas_c2_sl5,y   ; [4]
    sta COLPM2            ; [4]
    lda dli_pas_c3_sl5,y   ; [4]
    sta COLPM3            ; [4]
    sta WSYNC             ; [4] End scanline 5

    ; Scanline 6:
    lda dli_pas_c1_sl6,y   ; [4]
    sta COLPM1            ; [4]
    lda dli_pas_c2_sl6,y   ; [4]
    sta COLPM2            ; [4]
    lda dli_pas_c3_sl6,y   ; [4]
    sta COLPM3            ; [4]
    sta WSYNC             ; [4] End scanline 6

    ; Scanline 7:
    lda dli_pas_c1_sl7,y   ; [4]
    sta COLPM1            ; [4]
    lda dli_pas_c2_sl7,y   ; [4]
    sta COLPM2            ; [4]
    lda dli_pas_c3_sl7,y   ; [4]
    sta COLPM3            ; [4]
    sta WSYNC             ; [4] End scanline 7 (8th WSYNC)

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
    lda #0                 ; [2] Reset sizes to x1
    sta SIZEP1            ; [4]
    sta SIZEP2            ; [4]
    sta SIZEP3            ; [4]
    sta SIZEM             ; [4]

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

    lda dli_zone_prior,y      ; [4] ($11 if secret active, else $01)
    sta PRIOR                 ; [4]

    ; Advance pas index for next DLI
    iny                    ; [2]
    sty dli_pas_idx        ; [3]

    ; --------------------------------------------------------------------------
    ; EXIT: Restore registers from zero page and return
    ; --------------------------------------------------------------------------
    lda dli_save_a         ; [3]
    ldx dli_save_x         ; [3]
    ldy dli_save_y         ; [3]
    rti                    ; [6]
.endp
