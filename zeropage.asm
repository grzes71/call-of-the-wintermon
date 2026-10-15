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

; --- Audio Player Zero Page Base ($90-$99, 10 bytes) ---
; lib/player.asm uses PLAYER_ZP_BASE + 0..9 for track and temporary pointers
PLAYER_ZP_BASE  = $90
