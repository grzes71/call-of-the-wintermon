/**
 * Data access and formatting layer for Call of the Wintermon Portal.
 * Pure build-time data reader with zero runtime network calls.
 */

import fs from 'node:fs';
import path from 'node:path';
import type { MemoryReport } from '../types/memory';
import type { GameStats } from '../types/stats';
import type { ReleasesData, ReleaseSnapshot } from '../types/releases';
import type { AssetManifest } from '../types/assets';

// Resolve project root reports directory relative to website/
const PORTAL_REPORTS_DIR = path.resolve(process.cwd(), '../reports/portal');
const SNAPSHOTS_DIR = path.join(PORTAL_REPORTS_DIR, 'snapshots');
const SPRITES_DIR = path.resolve(process.cwd(), '../sprites');

export interface SpriteFrame {
  pixels: string[];
}

export interface SpriteItem {
  id: number;
  description: string;
  width: number;
  height: number;
  color: number;
  animation?: { frame_duration: number; loop: boolean };
  frames: SpriteFrame[];
}

export interface SpriteSheet {
  version: number;
  sprites: SpriteItem[];
}

function readJsonFile<T>(filePath: string): T {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Data file not found: ${filePath}. Run 'make portal_data' to generate it.`);
  }
  const content = fs.readFileSync(filePath, 'utf-8');
  return JSON.parse(content) as T;
}

export function getLatestMemoryReport(): MemoryReport {
  return readJsonFile<MemoryReport>(path.join(PORTAL_REPORTS_DIR, 'latest.json'));
}

export function getGameStats(): GameStats {
  return readJsonFile<GameStats>(path.join(PORTAL_REPORTS_DIR, 'game_stats.json'));
}

export function getReleases(): ReleasesData {
  return readJsonFile<ReleasesData>(path.join(PORTAL_REPORTS_DIR, 'releases.json'));
}

export function getAssetManifest(): AssetManifest {
  return readJsonFile<AssetManifest>(path.join(PORTAL_REPORTS_DIR, 'assets.json'));
}

export function getHistoricalSnapshots(): ReleaseSnapshot[] {
  if (!fs.existsSync(SNAPSHOTS_DIR)) {
    return [];
  }
  const files: string[] = fs.readdirSync(SNAPSHOTS_DIR);
  const jsonFiles = files.filter((f: string) => f.endsWith('.json'));
  const snapshots: ReleaseSnapshot[] = jsonFiles.map((f: string) =>
    readJsonFile<ReleaseSnapshot>(path.join(SNAPSHOTS_DIR, f))
  );

  // Sort by version (semantic comparison)
  return snapshots.sort((a, b) => a.version.localeCompare(b.version, undefined, { numeric: true }));
}

export function formatBytes(bytes: number): string {
  return new Intl.NumberFormat('en-US').format(bytes) + ' B';
}

export function formatHex(val: number, length: 2 | 4 = 4): string {
  return '$' + val.toString(16).toUpperCase().padStart(length, '0');
}

export function getPlayerSprites(): SpriteSheet {
  return readJsonFile<SpriteSheet>(path.join(SPRITES_DIR, 'player.sprite.json'));
}

export function getObjectSprites(): SpriteSheet {
  return readJsonFile<SpriteSheet>(path.join(SPRITES_DIR, 'objects.sprite.json'));
}

