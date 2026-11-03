/**
 * TypeScript definitions for Game Telemetry and Asset Statistics.
 * Matches output of scripts/game_stats.py exactly.
 */

export interface GameStatsSummary {
  scene_count: number;
  total_platforms: number;
  total_static_platforms: number;
  total_moving_platforms: number;
  total_enemies: number;
  total_secrets: number;
}

export interface EnemyTypeStat {
  id: number;
  name: string;
  total_count: number;
  scenes: string[];
}

export interface SecretTypeStat {
  id: number;
  name: string;
  total_count: number;
  scenes: string[];
}

export interface SceneEntityStat {
  id: number;
  name: string;
  count: number;
}

export interface ScenePlatformsDetail {
  total: number;
  static: number;
  moving: number;
  widths: Record<string, number>;
}

export interface SceneEnemiesDetail {
  total: number;
  by_type: SceneEntityStat[];
}

export interface SceneSecretsDetail {
  total: number;
  by_type: SceneEntityStat[];
}

export interface SceneDetail {
  filename: string;
  name: string;
  platforms: ScenePlatformsDetail;
  enemies: SceneEnemiesDetail;
  secrets: SceneSecretsDetail;
}

export interface GameStats {
  summary: GameStatsSummary;
  enemy_types: EnemyTypeStat[];
  secret_types: SecretTypeStat[];
  scenes: SceneDetail[];
}
