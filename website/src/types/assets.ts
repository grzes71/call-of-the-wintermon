/**
 * TypeScript definitions for Compiled Asset Manifest.
 */

export interface AssetManifest {
  manifest_version?: string;
  game_title?: string;
  target_platform?: string;
  generated_at?: string;
  assets?: Record<string, unknown>;
  [key: string]: unknown;
}

