; ==============================================================================
; ZEROPAGE.ASM — Zero Page Variable Allocations ($80-$FF)
; Reserved strictly for application use (OS uses $00-$7F)
; ==============================================================================

; --- State Constants ---
STATE_TITLE     = 0
STATE_INTRO     = 1
STATE_GAME      = 2
STATE_OVER      = 3

; --- Engine Temporary & Frame Variables ($80-$8F) ---
zp_temp_a       = $80
zp_temp_x       = $81
zp_temp_y       = $82
zp_ptr_src      = $83   ; 2 bytes ($83-$84)
zp_ptr_dst      = $85   ; 2 bytes ($85-$86)
zp_frame_cnt    = $87

; --- State Machine Variables ---
game_state      = $88   ; Target / current state (0..3)
current_state   = $89   ; Active running state ($FF = uninitialized)
title_first_run = $8A   ; 1 = first display (fade in), 0 = subsequent (immediate)
fade_frame      = $8B   ; Frame counter for 28-frame fade-in (0..28)
fire_released   = $8C   ; Debounce flag: 1 = fire button was released
game_phase      = $8D   ; Gameplay phase (0=title in, 1=title hold, 2=title out, 3=playing)
scene_card_step = $8E   ; Fade step index (0..7)
scene_card_timer= $8F   ; Frame counter within title card phase

; --- Audio Player Zero Page Base ($90-$99, 10 bytes) ---
; lib/player.asm uses PLAYER_ZP_BASE + 0..9 for track and temporary pointers
PLAYER_ZP_BASE  = $90

; --- Scene Renderer Zero Page Variables ($9A-$B7) ---
active_scene_id     = $9A   ; Currently active / loaded scene index (0..SCENE_COUNT-1)
zp_elem_idx         = $9B   ; Current element index within scene (0..elem_count-1)
zp_elem_count       = $9C   ; Total elements in scene
zp_elem_w           = $9D   ; Element width in bytes
zp_elem_h           = $9E   ; Element height in scanlines
zp_stride           = $9F   ; Tileset stride (bytes per line)
zp_flags            = $A0   ; Element flags (bit 0 = flip_x)
zp_ptr_row_lo       = $A1   ; 2 bytes: Pointer to tileset row_lo table
zp_ptr_row_hi       = $A3   ; 2 bytes: Pointer to tileset row_hi table
zp_src_idx          = $A5   ; Temporary index for flip loop
zp_dst_idx          = $A6   ; Temporary index for flip loop
zp_bytes_left       = $A7   ; Loop counter for columns
zp_ptr_elem_ts      = $A8   ; 2 bytes: Pointer to scene elem tileset table
zp_ptr_elem_sx      = $AA   ; 2 bytes: Pointer to scene elem src_x_byte table
zp_ptr_elem_sy      = $AC   ; 2 bytes: Pointer to scene elem src_y table
zp_ptr_elem_w       = $AE   ; 2 bytes: Pointer to scene elem w_byte table
zp_ptr_elem_h       = $B0   ; 2 bytes: Pointer to scene elem h_lines table
zp_ptr_elem_dx      = $B2   ; 2 bytes: Pointer to scene elem dst_x_byte table
zp_ptr_elem_dy      = $B4   ; 2 bytes: Pointer to scene elem dst_y table
zp_ptr_elem_fl      = $B6   ; 2 bytes: Pointer to scene elem flags table
; --- DLI Engine Zero Page Variables ($B8-$C0) ---
dli_save_a          = $B8   ; DLI accumulator save (no stack)
dli_save_x          = $B9   ; DLI X register save (no stack)
dli_save_y          = $BA   ; DLI Y register save (no stack)
dli_pas_idx         = $BB   ; Active pas index counter (buffer offset + 0..5)
dli_active_offset   = $BC   ; Active double buffer offset (0 or 8)
dli_pending_offset  = $BD   ; Inactive/staging buffer offset (8 or 0)
dli_swap_requested  = $BE   ; Mailbox flag: 1 = swap pending for next VBLANK
dli_scene_pmg_ptr   = $BF   ; 2 bytes ($BF-$C0): Pointer to active scene PMG patterns in ROM

; --- Game Result Equates ---
GAME_RESULT_NONE    = 0
GAME_FAILED         = 1
GAME_SUCCESS        = 2

; --- Player 0 Movement State Equates ---
PLAYER_STATE_IDLE   = 0
PLAYER_STATE_WALK   = 1
PLAYER_STATE_FALL   = 2

; --- Gameplay Status Variables ($C1-$C2) ---
player_lives        = $C1   ; Remaining player lives (initially 3, displayed as heart glyphs 64)
player_cds          = $C2   ; Collected CDs count (0..99, displayed as 2-digit number)

; --- Player 0 Engine Zero Page Variables ($C3-$CF) ---
player_x            = $C3   ; Player horizontal position on canvas (0..152)
player_pmg_y        = $C4   ; Player top scanline in PMG memory ($6C00 + Y)
player_dir          = $C5   ; Movement direction (0 = right, 1 = left)
player_state        = $C6   ; Movement state (0 = idle, 1 = walk, 2 = fall)
player_frame_idx    = $C7   ; Animation frame index (0..PLAYER_FRAME_COUNT-1)
player_frame_timer  = $C8   ; Frame countdown timer (4..1)
player_x_sub        = $C9   ; Sub-pixel position accumulator (0..255)
player_speed        = $CA   ; Horizontal speed magnitude (0..PLAYER_MAX_SPEED subpixels/frame)
player_color        = $CB   ; Active Hero color byte (from scene_player_color)
player_y            = $CC   ; Player canvas Y coordinate (0..104+)
player_plat_idx     = $CD   ; Active standing platform index ($FF = airborne/falling)
player_prev_pmg_y   = $CE   ; Previous frame PMG scanline (for PMG erasing)
game_result         = $CF   ; Outcome status (0 = none, 1 = GAME_FAILED, 2 = GAME_SUCCESS)

; --- Platform Collision Zero Page Variables ($D0-$D6) ---
zp_plat_ptr_x       = $D0   ; 2 bytes ($D0-$D1): Pointer to scene platform X table
zp_plat_ptr_y       = $D2   ; 2 bytes ($D2-$D3): Pointer to scene platform Y table
zp_plat_ptr_w       = $D4   ; 2 bytes ($D4-$D5): Pointer to scene platform W table
zp_plat_count       = $D6   ; Platform count in active scene
