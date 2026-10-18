; ==============================================================================
; ENGINE/PLAYER.ASM — Hero (Player 0) State Machine, Physics & PMG Renderer
; Target: Atari 800XL / 65XE (MOS 6502)
; Hardware: Atari GTIA Player 0 (HPOSP0, SIZEP0, COLPM0) + PMG_PLAYER0 ($6C00)
; ==============================================================================

; --- Player Direction Equates ---
PLAYER_DIR_RIGHT    = 0
PLAYER_DIR_LEFT     = 1

; --- Player Movement State Equates ---
PLAYER_STATE_IDLE   = 0
PLAYER_STATE_WALK   = 1

; --- Player Geometry & Movement Constants (Canvas 160x96) ---
PLAYER_MIN_X        = 0
PLAYER_MAX_X        = 152       ; 160 - 8 (player width)
PLAYER_HPOS_OFFSET  = 48        ; Normal playfield starts at HPOS 48 ($30)
PLAYER_COLOR        = $98       ; Royal cyan/blue for Player 0 (COLPM0 / PCOLR0)

; ==============================================================================
; PLAYER_INIT
; Initializes Hero Player 0 spawn position, direction, hardware registers and PMG.
; Input: A = active_scene_id (0..SCENE_COUNT-1)
; ==============================================================================
.proc player_init
    tax

    ; 1. Set initial canvas coordinates from scene data
    lda scene_player_start_x,x
    sta player_x

    ; PMG scanline: player_pmg_y = (player_start_y << 1) + 52
    ; Maps editor player start Y (e.g. 68) to PMG single-line scanline (e.g. 188)
    lda scene_player_start_y,x
    asl
    clc
    adc #52
    sta player_pmg_y

    ; 2. Initialize movement state: Facing right, standing idle
    lda #PLAYER_DIR_RIGHT
    sta player_dir
    lda #PLAYER_STATE_IDLE
    sta player_state
    lda #0
    sta player_frame_idx
    sta player_sub_x
    lda #PLAYER_FRAME_DUR
    sta player_frame_timer

    ; 3. Setup GTIA hardware registers for Player 0
    lda #PLAYER_COLOR
    sta COLPM0
    sta PCOLR0

    lda #0                  ; Normal width 1x (8 color clocks)
    sta SIZEP0

    ; 4. Set horizontal position HPOSP0 = 48 + player_x
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    ; 5. Clear entire PMG Player 0 buffer ($6C00-$6CFF, 256 bytes)
    lda #0
    tax
@clr_p0
    sta PMG_PLAYER0,x
    inx
    bne @clr_p0

    ; 6. Render initial standing frame into PMG_PLAYER0
    jsr player_render_frame
    rts
.endp

; ==============================================================================
; PLAYER_RENDER_FRAME
; Copies the active animation frame (20 bytes) into PMG_PLAYER0 memory.
; Uses: player_dir (0=right, 1=left), player_frame_idx (0..PLAYER_FRAME_COUNT-1),
;       player_pmg_y (scanline offset in PMG_PLAYER0).
; ==============================================================================
.proc player_render_frame
    ; 1. Select animation frame table based on player_dir
    ldy player_dir
    lda player_anim_table_lo,y
    sta zp_ptr_src
    lda player_anim_table_hi,y
    sta zp_ptr_src+1

    ; 2. Resolve frame address from .word pointer array
    lda player_frame_idx
    asl
    tay
    lda (zp_ptr_src),y
    sta zp_temp_a           ; Frame addr low
    iny
    lda (zp_ptr_src),y
    sta zp_temp_x           ; Frame addr high

    lda zp_temp_a
    sta zp_ptr_src
    lda zp_temp_x
    sta zp_ptr_src+1

    ; 3. Set destination pointer = PMG_PLAYER0 + player_pmg_y
    lda #>PMG_PLAYER0
    sta zp_ptr_dst+1
    lda player_pmg_y
    sta zp_ptr_dst

    ; 4. Copy PLAYER_SPRITE_HEIGHT scanlines
    ldy #PLAYER_SPRITE_HEIGHT - 1
@copy_loop
    lda (zp_ptr_src),y
    sta (zp_ptr_dst),y
    dey
    bpl @copy_loop

    rts
.endp

; ==============================================================================
; PLAYER_UPDATE
; Called once per frame during active gameplay (GAME_PHASE_PLAYING).
; Reads joystick STICK0, handles horizontal walk, updates animation and renders.
; Speed: 0.5 pixels/frame (moves 1 pixel every 2 frames).
; ==============================================================================
.proc player_update
    ; 1. Poll Joystick 0
    ; STICK0 bits: bit 2 = Left (0 = active), bit 3 = Right (0 = active)
    lda STICK0
    and #%00001100          ; Mask bits 2 and 3
    cmp #%00001100          ; Neither left nor right pressed?
    beq @do_idle

    ; Check Left direction (bit 2 == 0)
    lda STICK0
    and #%00000100
    beq @move_left

    ; Check Right direction (bit 3 == 0)
    lda STICK0
    and #%00001000
    beq @move_right

@do_idle
    ; Set idle state: stop walk animation, show standing frame (frame 0)
    lda #PLAYER_STATE_IDLE
    sta player_state
    lda #0
    sta player_frame_idx
    sta player_sub_x
    lda #PLAYER_FRAME_DUR
    sta player_frame_timer
    jmp @finish_update

@move_left
    lda #PLAYER_DIR_LEFT
    sta player_dir
    lda #PLAYER_STATE_WALK
    sta player_state

    ; Half speed: step 1 pixel every 2 frames
    inc player_sub_x
    lda player_sub_x
    lsr
    bcc @tick_anim

    ; Move left: clamp to PLAYER_MIN_X
    lda player_x
    beq @tick_anim
    dec player_x
    jmp @tick_anim

@move_right
    lda #PLAYER_DIR_RIGHT
    sta player_dir
    lda #PLAYER_STATE_WALK
    sta player_state

    ; Half speed: step 1 pixel every 2 frames
    inc player_sub_x
    lda player_sub_x
    lsr
    bcc @tick_anim

    ; Move right: clamp to PLAYER_MAX_X
    lda player_x
    cmp #PLAYER_MAX_X
    bcs @tick_anim
    inc player_x

@tick_anim
    ; Advance animation timer
    dec player_frame_timer
    bne @finish_update

    ; Timer expired: reset timer and advance frame index
    lda #PLAYER_FRAME_DUR
    sta player_frame_timer

    inc player_frame_idx
    lda player_frame_idx
    cmp #PLAYER_FRAME_COUNT
    bcc @finish_update
    lda #0
    sta player_frame_idx

@finish_update
    ; Update hardware horizontal position: HPOSP0 = 48 + player_x
    lda player_x
    clc
    adc #PLAYER_HPOS_OFFSET
    sta HPOSP0

    ; Re-render current frame into PMG buffer
    jsr player_render_frame
    rts
.endp
