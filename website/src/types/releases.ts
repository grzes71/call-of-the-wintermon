/**
 * TypeScript definitions for Historical Release Snapshots and Release Index.
 */

import type { MemoryReport } from './memory';

export interface FrozenGameStats {
  scene_count: number;
  total_platforms: number;
  total_static_platforms: number;
  total_moving_platforms: number;
  total_enemies: number;
  total_secrets: number;
}

export interface ReleaseSnapshot {
  schema_version: string;
  release_tag: string;
  version: string;
  published_at: string;
  source_commit_sha: string;
  binary_size_bytes: number;
  binary_sha256: string;
  xex_download_url: string;
  pdf_download_url: string | null;
  changelog_body: string;
  memory_report: MemoryReport;
  frozen_game_stats: FrozenGameStats;
}

export interface ReleaseAssetInfo {
  name: string;
  size_bytes: number;
  download_url: string;
  content_type?: string;
}

export interface ReleaseSummaryEntry {
  tag_name: string;
  tag?: string;
  version: string;
  name: string;
  published_at: string;
  source_commit_sha: string;
  commit_sha?: string;
  prerelease: boolean;
  draft: boolean;
  html_url: string;
  xex_asset: ReleaseAssetInfo | null;
  xex_pl_asset?: ReleaseAssetInfo | null;
  xex_en_asset?: ReleaseAssetInfo | null;
  pdf_asset: ReleaseAssetInfo | null;
  xex_download_url?: string;
  xex_pl_download_url?: string;
  xex_en_download_url?: string;
  pdf_download_url?: string | null;
  body: string;
  changelog_body?: string;
  binary_size_bytes?: number;
  binary_sha256?: string;
  memory_metrics?: {
    total_allocated_bytes: number;
    total_free_bytes: number;
    utilization_percent: number;
  };
  game_metrics?: FrozenGameStats;
}

export interface ReleasesData {
  repository: string;
  total_releases: number;
  generated_at: string;
  releases: ReleaseSummaryEntry[];
}

