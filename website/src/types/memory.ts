/**
 * TypeScript definitions for Atari Memory Map and Zero Page Reports.
 * Conforms to JSON Schema Draft 2020-12 (website/src/data/schemas/memory-report.schema.json).
 */

export interface SystemRegion {
  name: string;
  range_hex: string;
  start: number;
  end: number;
  size: number;
  type: 'RAM' | 'ROM' | 'HARDWARE' | 'SYSTEM' | 'USER_RAM';
  color: string;
  description: string;
}

export interface MemorySegment {
  start: number;
  end: number;
  start_hex: string;
  end_hex: string;
  size: number;
  name: string;
  category: 'CODE' | 'GRAPHICS' | 'BITMAPS' | 'DLIST' | 'PMG' | 'AUDIO' | 'METADATA' | 'DATA' | 'FREE';
  color: string;
  details: string;
}

export interface FreeGap {
  start: number;
  end: number;
  start_hex: string;
  end_hex: string;
  size: number;
  name: string;
  category: 'FREE';
  color: string;
  details: string;
}

export interface ZeroPageAllocation {
  range_hex: string;
  start: number;
  end: number;
  size: number;
  label: string;
  color: string;
  description: string;
}

export interface ZeroPageReport {
  total_bytes: number;
  os_reserved_bytes: number;
  user_allocated_bytes: number;
  free_bytes: number;
  allocations: ZeroPageAllocation[];
}

export interface MemorySummary {
  user_ram_start: number;
  user_ram_end: number;
  total_user_ram_bytes: number;
  total_allocated_bytes: number;
  total_free_bytes: number;
  utilization_percent: number;
  largest_free_block_bytes?: number;
  largest_free_block_range?: string;
  is_valid?: boolean;
  category_totals?: Record<string, number>;
}

export interface HardwareEquates {
  ANTIC_DMACTL?: string;
  ANTIC_CHBASE?: string;
  GTIA_COLBK?: string;
  GTIA_COLPF0?: string;
  GTIA_GRACTL?: string;
  POKEY_SKCTL?: string;
  PIA_PORTB?: string;
  PIA_PORTB_VALUE?: string;
  OS_ROM_ENABLED?: boolean;
  BASIC_ROM_DISABLED?: boolean;
}

export interface GameInfo {
  name: string;
  version: string;
  target: string;
  executable: string;
  binary_size_bytes: number;
  binary_sha256: string;
}

export interface BuildInfo {
  commit_sha: string;
  ref: string;
  mads_version?: string;
}

export interface MemoryReport {
  schema_version: string;
  generated_at: string;
  game: GameInfo;
  build: BuildInfo;
  memory_summary: MemorySummary;
  allocated_segments: MemorySegment[];
  free_gaps: FreeGap[];
  zero_page: ZeroPageReport;
  hardware_equates?: HardwareEquates;
  system_memory_map?: SystemRegion[];
}
