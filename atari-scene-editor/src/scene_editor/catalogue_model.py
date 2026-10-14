"""Data models and storage for project-wide catalogues: Enemies and Secrets."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import json
from pathlib import Path
import tempfile
from typing import Any, Optional


class CatalogueError(Exception):
    """Base exception for catalogue validation and persistence errors."""
    pass


class DuplicateDefinitionIdError(CatalogueError):
    """Raised when an ID is duplicated within the same catalogue."""
    pass


class InvalidDefinitionError(CatalogueError):
    """Raised when definition fields fail validation."""
    pass


CatalogueValidationError = InvalidDefinitionError


class DefinitionInUseError(CatalogueError):
    """Raised when trying to delete a definition that is referenced by scene objects."""
    pass


class CorruptedCatalogueFileError(CatalogueError):
    """Raised when a catalogue JSON file is malformed or corrupted."""
    pass


@dataclass
class CatalogDefinition:
    """Base definition for an enemy or secret type in project catalogues."""
    id: int
    name: str
    rgb_color: Optional[tuple[int, int, int]] = None
    atari_color: Optional[int] = None
    blink: bool = False

    def validate(self) -> None:
        """Validate definition integrity."""
        # Allow numeric string conversion to int
        if isinstance(self.id, str) and self.id.strip().isdigit():
            self.id = int(self.id.strip())

        if isinstance(self.id, bool) or not isinstance(self.id, int) or not (1 <= self.id <= 255):
            raise InvalidDefinitionError(
                f"Definition 'id' must be an integer between 1 and 255, got {self.id!r}."
            )
        
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidDefinitionError("Definition 'name' must be a non-empty string.")

        if self.rgb_color is not None:
            if (
                not isinstance(self.rgb_color, (tuple, list))
                or len(self.rgb_color) != 3
                or not all(isinstance(c, int) and 0 <= c <= 255 for c in self.rgb_color)
            ):
                raise InvalidDefinitionError(
                    f"rgb_color must be a tuple/list of 3 integers (0-255), got {self.rgb_color}."
                )

        if self.atari_color is not None:
            if not isinstance(self.atari_color, int) or not (0 <= self.atari_color <= 255):
                raise InvalidDefinitionError(
                    f"atari_color must be an integer between 0 and 255 ($00-$FF), got {self.atari_color}."
                )

        if not isinstance(self.blink, bool):
            raise InvalidDefinitionError(f"blink must be a boolean, got {type(self.blink).__name__}.")

    def clone(self) -> CatalogDefinition:
        """Create a deep copy."""
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        """Serialize definition to JSON-serializable dictionary."""
        d: dict[str, Any] = {
            "id": int(self.id),
            "name": self.name,
            "blink": bool(self.blink),
        }
        if self.rgb_color is not None:
            d["rgb_color"] = [int(c) for c in self.rgb_color]
        if self.atari_color is not None:
            d["atari_color"] = int(self.atari_color)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogDefinition:
        """Construct definition from dictionary with strict validation."""
        if not isinstance(data, dict):
            raise InvalidDefinitionError("Definition data must be a dictionary.")

        if "id" not in data or "name" not in data:
            raise InvalidDefinitionError("Definition must have 'id' and 'name' fields.")

        raw_id = data["id"]
        if isinstance(raw_id, str) and raw_id.strip().isdigit():
            defn_id = int(raw_id.strip())
        elif isinstance(raw_id, int) and not isinstance(raw_id, bool):
            defn_id = raw_id
        else:
            raise InvalidDefinitionError(
                f"Definition 'id' must be an integer between 1 and 255, got {raw_id!r}."
            )

        rgb: Optional[tuple[int, int, int]] = None
        if "rgb_color" in data and data["rgb_color"] is not None:
            raw_rgb = data["rgb_color"]
            if not isinstance(raw_rgb, (list, tuple)) or len(raw_rgb) != 3:
                raise InvalidDefinitionError(f"rgb_color must be 3 integers: {raw_rgb}")
            rgb = (int(raw_rgb[0]), int(raw_rgb[1]), int(raw_rgb[2]))

        atari: Optional[int] = None
        if "atari_color" in data and data["atari_color"] is not None:
            atari = int(data["atari_color"])

        blink = bool(data.get("blink", False))

        defn = cls(
            id=defn_id,
            name=str(data["name"]).strip(),
            rgb_color=rgb,
            atari_color=atari,
            blink=blink,
        )
        defn.validate()
        return defn


@dataclass
class EnemyDefinition(CatalogDefinition):
    """Specific definition for an enemy type."""
    pass


@dataclass
class SecretDefinition(CatalogDefinition):
    """Specific definition for a secret / collectible type."""
    pass


@dataclass
class ProjectCatalogues:
    """Project-wide manager for Enemies and Secrets catalogues."""
    enemies: dict[int, EnemyDefinition] = field(default_factory=dict)
    secrets: dict[int, SecretDefinition] = field(default_factory=dict)
    enemies_path: Optional[Path] = None
    secrets_path: Optional[Path] = None

    @staticmethod
    def _normalize_id(defn_id: Any) -> int:
        """Normalize an ID (int or numeric str) to int; raises KeyError on failure."""
        if isinstance(defn_id, int) and not isinstance(defn_id, bool):
            return defn_id
        try:
            return int(str(defn_id).strip())
        except (ValueError, TypeError):
            raise KeyError(f"Invalid definition ID '{defn_id}'. Must be an integer 1-255.")

    def validate(self) -> None:
        """Validate all definitions."""
        for enemy in self.enemies.values():
            enemy.validate()
        for secret in self.secrets.values():
            secret.validate()

    def add_enemy(self, defn: EnemyDefinition) -> None:
        defn.validate()
        norm_id = self._normalize_id(defn.id)
        if norm_id in self.enemies:
            raise DuplicateDefinitionIdError(f"Enemy with ID '{norm_id}' already exists.")
        self.enemies[norm_id] = defn.clone()

    def update_enemy(self, defn_id: Any, defn: EnemyDefinition) -> None:
        defn.validate()
        old_id = self._normalize_id(defn_id)
        new_id = self._normalize_id(defn.id)
        if old_id not in self.enemies:
            raise KeyError(f"Enemy with ID '{old_id}' not found.")
        if new_id != old_id and new_id in self.enemies:
            raise DuplicateDefinitionIdError(f"Enemy with ID '{new_id}' already exists.")
        if new_id != old_id:
            del self.enemies[old_id]
        self.enemies[new_id] = defn.clone()

    def remove_enemy(self, defn_id: Any) -> EnemyDefinition:
        norm_id = self._normalize_id(defn_id)
        if norm_id not in self.enemies:
            raise KeyError(f"Enemy with ID '{norm_id}' not found.")
        return self.enemies.pop(norm_id)

    def add_secret(self, defn: SecretDefinition) -> None:
        defn.validate()
        norm_id = self._normalize_id(defn.id)
        if norm_id in self.secrets:
            raise DuplicateDefinitionIdError(f"Secret with ID '{norm_id}' already exists.")
        self.secrets[norm_id] = defn.clone()

    def update_secret(self, defn_id: Any, defn: SecretDefinition) -> None:
        defn.validate()
        old_id = self._normalize_id(defn_id)
        new_id = self._normalize_id(defn.id)
        if old_id not in self.secrets:
            raise KeyError(f"Secret with ID '{old_id}' not found.")
        if new_id != old_id and new_id in self.secrets:
            raise DuplicateDefinitionIdError(f"Secret with ID '{new_id}' already exists.")
        if new_id != old_id:
            del self.secrets[old_id]
        self.secrets[new_id] = defn.clone()

    def remove_secret(self, defn_id: Any) -> SecretDefinition:
        norm_id = self._normalize_id(defn_id)
        if norm_id not in self.secrets:
            raise KeyError(f"Secret with ID '{norm_id}' not found.")
        return self.secrets.pop(norm_id)

    def get_enemy(self, defn_id: Any) -> Optional[EnemyDefinition]:
        try:
            norm_id = self._normalize_id(defn_id)
            return self.enemies.get(norm_id)
        except KeyError:
            return None

    def get_secret(self, defn_id: Any) -> Optional[SecretDefinition]:
        try:
            norm_id = self._normalize_id(defn_id)
            return self.secrets.get(norm_id)
        except KeyError:
            return None

    def get_definition(self, kind: str, defn_id: Any) -> Optional[CatalogDefinition]:
        norm_kind = kind.lower()
        if norm_kind == "enemy":
            return self.get_enemy(defn_id)
        elif norm_kind in ("secret", "treasure"):
            return self.get_secret(defn_id)
        return None

    def clone(self) -> ProjectCatalogues:
        return copy.deepcopy(self)

    # -------------------------------------------------------------------------
    # Persistence: enemies.json & secrets.json
    # -------------------------------------------------------------------------
    @classmethod
    def find_catalogue_paths(cls, base_dir: Path | str) -> tuple[Path, Path]:
        """Locate enemies.json and secrets.json in base_dir or base_dir/data."""
        base = Path(base_dir).resolve()
        data_dir = base / "data"
        if (data_dir / "enemies.json").is_file() or (data_dir / "secrets.json").is_file():
            return data_dir / "enemies.json", data_dir / "secrets.json"
        if (base / "enemies.json").is_file() or (base / "secrets.json").is_file():
            return base / "enemies.json", base / "secrets.json"
        if data_dir.is_dir():
            return data_dir / "enemies.json", data_dir / "secrets.json"
        return base / "enemies.json", base / "secrets.json"

    def set_paths(
        self,
        enemies_path: Optional[Path | str],
        secrets_path: Optional[Path | str],
    ) -> None:
        """Set explicit file paths for enemies.json and secrets.json."""
        self.enemies_path = Path(enemies_path).resolve() if enemies_path else None
        self.secrets_path = Path(secrets_path).resolve() if secrets_path else None

    def get_effective_paths(self, base_dir: Path | str | None = None) -> tuple[Path, Path]:
        """Return the effective (enemies_path, secrets_path).
        If custom paths were set, use them. Otherwise, locate them relative to base_dir."""
        default_enemies, default_secrets = self.find_catalogue_paths(base_dir or Path.cwd())
        eff_enemies = self.enemies_path if self.enemies_path is not None else default_enemies
        eff_secrets = self.secrets_path if self.secrets_path is not None else default_secrets
        return eff_enemies, eff_secrets

    @classmethod
    def load_from_paths(
        cls,
        enemies_path: Optional[Path | str],
        secrets_path: Optional[Path | str],
    ) -> ProjectCatalogues:
        """Load catalogues from specific file paths."""
        e_path = Path(enemies_path).resolve() if enemies_path else None
        s_path = Path(secrets_path).resolve() if secrets_path else None
        catalogues = cls(enemies_path=e_path, secrets_path=s_path)

        # Load enemies
        if e_path and e_path.is_file():
            try:
                with open(e_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    raise CorruptedCatalogueFileError(f"Enemies catalogue file is empty: {e_path}")
                data = json.loads(content)
            except json.JSONDecodeError as err:
                raise CorruptedCatalogueFileError(f"Invalid JSON in {e_path.name}: {err}") from err

            if not isinstance(data, dict):
                raise CorruptedCatalogueFileError(f"Top-level JSON in {e_path.name} must be an object.")

            enemies_list = data.get("enemies", [])
            if not isinstance(enemies_list, list):
                raise CorruptedCatalogueFileError(f"'enemies' key in {e_path.name} must be a list.")

            for idx, item in enumerate(enemies_list):
                try:
                    defn = EnemyDefinition.from_dict(item)
                    if defn.id in catalogues.enemies:
                        raise DuplicateDefinitionIdError(
                            f"Duplicate enemy ID '{defn.id}' in {e_path.name}."
                        )
                    catalogues.enemies[defn.id] = defn
                except Exception as err:
                    raise CorruptedCatalogueFileError(
                        f"Error in {e_path.name} at entry {idx}: {err}"
                    ) from err

        # Load secrets
        if s_path and s_path.is_file():
            try:
                with open(s_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    raise CorruptedCatalogueFileError(f"Secrets catalogue file is empty: {s_path}")
                data = json.loads(content)
            except json.JSONDecodeError as err:
                raise CorruptedCatalogueFileError(f"Invalid JSON in {s_path.name}: {err}") from err

            if not isinstance(data, dict):
                raise CorruptedCatalogueFileError(f"Top-level JSON in {s_path.name} must be an object.")

            secrets_list = data.get("secrets", [])
            if not isinstance(secrets_list, list):
                raise CorruptedCatalogueFileError(f"'secrets' key in {s_path.name} must be a list.")

            for idx, item in enumerate(secrets_list):
                try:
                    defn = SecretDefinition.from_dict(item)
                    if defn.id in catalogues.secrets:
                        raise DuplicateDefinitionIdError(
                            f"Duplicate secret ID '{defn.id}' in {s_path.name}."
                        )
                    catalogues.secrets[defn.id] = defn
                except Exception as err:
                    raise CorruptedCatalogueFileError(
                        f"Error in {s_path.name} at entry {idx}: {err}"
                    ) from err

        return catalogues

    @classmethod
    def load_from_dir(cls, base_dir: Path | str) -> ProjectCatalogues:
        """Load catalogues from directory. If files do not exist, return empty catalogues.
        If file exists but is corrupted, raise CorruptedCatalogueFileError without overwriting."""
        enemies_path, secrets_path = cls.find_catalogue_paths(base_dir)
        return cls.load_from_paths(enemies_path, secrets_path)

    def save_to_dir(self, base_dir: Path | str | None = None) -> None:
        """Atomically save both catalogues into enemies.json and secrets.json."""
        enemies_path, secrets_path = self.get_effective_paths(base_dir)
        enemies_path.parent.mkdir(parents=True, exist_ok=True)
        secrets_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Save enemies.json
        enemies_data = {
            "version": 1,
            "enemies": [e.to_dict() for e in sorted(self.enemies.values(), key=lambda e: e.id)],
        }
        self._atomic_save_json(enemies_path, enemies_data)

        # 2. Save secrets.json
        secrets_data = {
            "version": 1,
            "secrets": [s.to_dict() for s in sorted(self.secrets.values(), key=lambda s: s.id)],
        }
        self._atomic_save_json(secrets_path, secrets_data)

    @staticmethod
    def _atomic_save_json(target_path: Path, data: dict[str, Any]) -> None:
        target_dir = target_path.parent
        fd, temp_file_path = tempfile.mkstemp(
            prefix=f".{target_path.stem}_",
            suffix=".tmp",
            dir=str(target_dir),
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            # Atomic rename / replace
            Path(temp_file_path).replace(target_path)
        except Exception:
            try:
                Path(temp_file_path).unlink(missing_ok=True)
            except Exception:
                pass
            raise
