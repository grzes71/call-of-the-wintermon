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
    dependency: Optional[int] = None

    def validate(self) -> None:
        super().validate()
        if self.dependency is not None:
            if isinstance(self.dependency, str) and self.dependency.strip().isdigit():
                self.dependency = int(self.dependency.strip())

            if isinstance(self.dependency, bool) or not isinstance(self.dependency, int) or not (1 <= self.dependency <= 255):
                raise InvalidDefinitionError(
                    f"Secret 'dependency' must be an integer between 1 and 255, got {self.dependency!r}."
                )

            if self.dependency == self.id:
                raise InvalidDefinitionError(
                    f"Secret '{self.id}' cannot depend on itself."
                )

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.dependency is not None:
            d["dependency"] = int(self.dependency)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecretDefinition:
        if not isinstance(data, dict):
            raise InvalidDefinitionError("Definition data must be a dictionary.")

        base_defn = super().from_dict(data)
        raw_dep = data.get("dependency")
        dep: Optional[int] = None
        if raw_dep is not None:
            if isinstance(raw_dep, str) and raw_dep.strip().isdigit():
                dep = int(raw_dep.strip())
            elif isinstance(raw_dep, int) and not isinstance(raw_dep, bool):
                dep = raw_dep
            elif raw_dep == "" or raw_dep is False:
                dep = None
            else:
                raise InvalidDefinitionError(
                    f"Secret 'dependency' must be an integer between 1 and 255, got {raw_dep!r}."
                )

        defn = cls(
            id=base_defn.id,
            name=base_defn.name,
            rgb_color=base_defn.rgb_color,
            atari_color=base_defn.atari_color,
            blink=base_defn.blink,
            dependency=dep,
        )
        defn.validate()
        return defn


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
        """Validate all definitions and relationship integrity."""
        for enemy in self.enemies.values():
            enemy.validate()
        for secret in self.secrets.values():
            secret.validate()
        self.validate_secrets_chain()

    def get_secret_stage(self, defn_id: Any) -> int:
        """Calculate the stage index (1-based) for a secret definition.
        Secrets with no dependency (or unresolvable) belong to Stage 1.
        Each dependency link increments the stage by 1."""
        if defn_id is None:
            return 1
        try:
            norm_id = self._normalize_id(defn_id)
        except KeyError:
            return 1

        curr_id = norm_id
        stage = 1
        visited = set()
        while curr_id in self.secrets:
            if curr_id in visited:
                break
            visited.add(curr_id)
            dep = self.secrets[curr_id].dependency
            if dep is None or dep not in self.secrets or dep == curr_id:
                break
            stage += 1
            curr_id = dep
        return stage

    def get_all_secret_stages(self) -> dict[int, int]:
        """Return a mapping of secret ID to its calculated stage number."""
        return {s_id: self.get_secret_stage(s_id) for s_id in self.secrets}

    def validate_secrets_chain(self) -> None:
        """Validate that secrets form a valid, non-cyclic, non-branching linear chain.
        - All referenced dependencies must exist in secrets catalogue.
        - No self-dependencies.
        - No cycles (A -> B -> A).
        - No branching: no secret definition may have more than one child depending on it.
        - No multiple independent chains: if dependencies exist, they must all belong
          to a single linear chain sequence."""
        if not self.secrets:
            return

        # 1. Basic validation and missing dependency check
        children_map: dict[int, list[int]] = {}
        for s_id, s in self.secrets.items():
            s.validate()
            if s.dependency is not None:
                dep_id = self._normalize_id(s.dependency)
                if dep_id not in self.secrets:
                    raise InvalidDefinitionError(
                        f"Secret '{s.name}' [{s_id}] depends on non-existent secret ID '{dep_id}'."
                    )
                if dep_id == s_id:
                    raise InvalidDefinitionError(
                        f"Secret '{s.name}' [{s_id}] cannot depend on itself."
                    )
                children_map.setdefault(dep_id, []).append(s_id)

        # 2. Check branching (multiple dependents on the same secret)
        for parent_id, children in children_map.items():
            if len(children) > 1:
                parent_name = self.secrets[parent_id].name
                child_names = [f"'{self.secrets[cid].name}' [{cid}]" for cid in children]
                raise InvalidDefinitionError(
                    f"Branching is not allowed in secret dependency chain: "
                    f"Secret '{parent_name}' [{parent_id}] is a dependency for multiple secrets: "
                    f"{', '.join(child_names)}."
                )

        # 3. Check cycles
        for s_id in self.secrets:
            visited = set()
            curr = s_id
            while curr in self.secrets:
                if curr in visited:
                    cycle_path = " -> ".join(str(i) for i in visited)
                    raise InvalidDefinitionError(
                        f"Cyclic dependency detected involving secret ID '{curr}': {cycle_path}."
                    )
                visited.add(curr)
                dep = self.secrets[curr].dependency
                if dep is None:
                    break
                curr = dep

        # 4. Check multiple independent chains
        # Chains with dependencies have edges.
        # If there are secrets with dependencies, there can only be ONE chain with dependents.
        chain_roots_with_dependents = [
            s_id for s_id, s in self.secrets.items()
            if s.dependency is None and s_id in children_map
        ]
        if len(chain_roots_with_dependents) > 1:
            roots_desc = [f"'{self.secrets[rid].name}' [{rid}]" for rid in chain_roots_with_dependents]
            raise InvalidDefinitionError(
                f"Multiple independent dependency chains are not allowed: "
                f"found separate chains starting at {', '.join(roots_desc)}."
            )

    def get_valid_dependencies_for(self, secret_id: Optional[int]) -> list[SecretDefinition]:
        """Return secret definitions that can be chosen as a dependency for secret_id
        without causing cycles, branching, or multiple independent chains."""
        valid: list[SecretDefinition] = []
        target_id = self._normalize_id(secret_id) if secret_id is not None else None

        for cand_id, cand_defn in self.secrets.items():
            if target_id is not None and cand_id == target_id:
                continue

            # Check branching: cand_defn cannot already have a dependent other than target_id
            other_dependents = [
                s.id for s in self.secrets.values()
                if s.dependency == cand_id and (target_id is None or s.id != target_id)
            ]
            if other_dependents:
                continue

            # Check cycle: cand_defn cannot depend on target_id
            if target_id is not None:
                curr = cand_defn.dependency
                has_cycle = False
                visited = {target_id}
                while curr is not None and curr in self.secrets:
                    if curr in visited:
                        has_cycle = True
                        break
                    visited.add(curr)
                    curr = self.secrets[curr].dependency
                if has_cycle:
                    continue

            # Check multiple chains: test-run simulation
            sim_catalogues = self.clone()
            if target_id is not None and target_id in sim_catalogues.secrets:
                sim_catalogues.secrets[target_id].dependency = cand_id
            else:
                avail_ids = sorted(set(range(1, 256)) - set(sim_catalogues.secrets.keys()))
                dummy_id = avail_ids[0] if avail_ids else 255
                sim_catalogues.secrets[dummy_id] = SecretDefinition(id=dummy_id, name="Temp", dependency=cand_id)
            try:
                sim_catalogues.validate_secrets_chain()
                valid.append(cand_defn)
            except InvalidDefinitionError:
                continue

        # Sort by stage order
        return sorted(valid, key=lambda s: (self.get_secret_stage(s.id), s.id))

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
        try:
            self.validate_secrets_chain()
        except Exception:
            del self.secrets[norm_id]
            raise

    def update_secret(self, defn_id: Any, defn: SecretDefinition) -> None:
        defn.validate()
        old_id = self._normalize_id(defn_id)
        new_id = self._normalize_id(defn.id)
        if old_id not in self.secrets:
            raise KeyError(f"Secret with ID '{old_id}' not found.")
        if new_id != old_id and new_id in self.secrets:
            raise DuplicateDefinitionIdError(f"Secret with ID '{new_id}' already exists.")

        backup_secrets = {k: v.clone() for k, v in self.secrets.items()}
        if new_id != old_id:
            del self.secrets[old_id]
            for s in self.secrets.values():
                if s.dependency == old_id:
                    s.dependency = new_id

        self.secrets[new_id] = defn.clone()
        try:
            self.validate_secrets_chain()
        except Exception:
            self.secrets = backup_secrets
            raise

    def remove_secret(self, defn_id: Any) -> SecretDefinition:
        norm_id = self._normalize_id(defn_id)
        if norm_id not in self.secrets:
            raise KeyError(f"Secret with ID '{norm_id}' not found.")

        # Guard against breaking dependencies
        dependents = [s for s in self.secrets.values() if s.dependency == norm_id]
        if dependents:
            dep_names = ", ".join(f"'{s.name}' [{s.id}]" for s in dependents)
            raise DefinitionInUseError(
                f"Cannot delete secret '{self.secrets[norm_id].name}' [{norm_id}]: "
                f"the following secret(s) depend on it: {dep_names}."
            )
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
        enemies_path: Optional[Path | str] = None,
        secrets_path: Optional[Path | str] = None,
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

            try:
                catalogues.validate_secrets_chain()
            except Exception as err:
                raise CorruptedCatalogueFileError(
                    f"Invalid secret dependency chain in {s_path.name}: {err}"
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

    def save_to_paths(
        self,
        enemies_path: Optional[Path | str] = None,
        secrets_path: Optional[Path | str] = None,
    ) -> None:
        """Atomically save catalogues to specific file paths if provided."""
        if enemies_path is not None:
            e_p = Path(enemies_path).resolve()
            e_p.parent.mkdir(parents=True, exist_ok=True)
            enemies_data = {
                "version": 1,
                "enemies": [e.to_dict() for e in sorted(self.enemies.values(), key=lambda e: e.id)],
            }
            self._atomic_save_json(e_p, enemies_data)
        if secrets_path is not None:
            s_p = Path(secrets_path).resolve()
            s_p.parent.mkdir(parents=True, exist_ok=True)
            secrets_data = {
                "version": 1,
                "secrets": [s.to_dict() for s in sorted(self.secrets.values(), key=lambda s: s.id)],
            }
            self._atomic_save_json(s_p, secrets_data)


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
