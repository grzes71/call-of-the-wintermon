"""Data models and storage for project-wide catalogues: Enemies and Secrets."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import json
from pathlib import Path
import tempfile
from typing import Any, Optional

from .atari_palette import (
    atari_color_to_hex_rgb,
    atari_color_to_rgb,
    format_atari_color_hex,
    parse_atari_color_hex,
)


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


ProfileInUseError = DefinitionInUseError


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
    sprite_id: Optional[int] = None
    sprite: Optional[str] = None

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

        if self.sprite_id is not None:
            if isinstance(self.sprite_id, str) and self.sprite_id.strip().isdigit():
                self.sprite_id = int(self.sprite_id.strip())
            if isinstance(self.sprite_id, bool) or not isinstance(self.sprite_id, int) or not (1 <= self.sprite_id <= 255):
                raise InvalidDefinitionError(
                    f"Definition 'sprite_id' must be an integer between 1 and 255, got {self.sprite_id!r}."
                )

        if self.sprite is not None and not isinstance(self.sprite, str):
            raise InvalidDefinitionError(f"Definition 'sprite' must be a string, got {type(self.sprite).__name__}.")

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
        if self.sprite_id is not None:
            d["sprite_id"] = int(self.sprite_id)
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

        raw_sprite_id = data.get("sprite_id")
        sprite_id: Optional[int] = None
        if raw_sprite_id is not None and str(raw_sprite_id).strip() != "":
            if isinstance(raw_sprite_id, str) and raw_sprite_id.strip().isdigit():
                sprite_id = int(raw_sprite_id.strip())
            elif isinstance(raw_sprite_id, int) and not isinstance(raw_sprite_id, bool):
                sprite_id = raw_sprite_id
            else:
                raise InvalidDefinitionError(
                    f"Definition 'sprite_id' must be an integer between 1 and 255, got {raw_sprite_id!r}."
                )

        raw_sprite = data.get("sprite")
        sprite: Optional[str] = str(raw_sprite).strip() if (raw_sprite is not None and str(raw_sprite).strip()) else None
        if sprite is not None:
            import warnings
            warnings.warn(
                f"Ostrzeżenie: typ katalogu '{data.get('name')}' używa przestarzałego pola 'sprite': '{sprite}'. "
                f"Zalecane pole 'sprite_id'.",
                UserWarning,
                stacklevel=2,
            )

        defn = cls(
            id=defn_id,
            name=str(data["name"]).strip(),
            rgb_color=rgb,
            atari_color=atari,
            blink=blink,
            sprite_id=sprite_id,
            sprite=sprite,
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
            sprite_id=base_defn.sprite_id,
            sprite=base_defn.sprite,
            dependency=dep,
        )
        defn.validate()
        return defn


@dataclass
class PlatformColorProfile:
    """Color and luminance profile for an Atari 8-bit platform (8 scanlines)."""
    id: int
    name: str
    colors: list[int] = field(default_factory=lambda: [0x8E, 0x8C, 0x8A, 0x88, 0x86, 0x84, 0x82, 0x80])
    description: str = ""

    def validate(self) -> None:
        """Validate profile integrity."""
        if isinstance(self.id, str) and self.id.strip().isdigit():
            self.id = int(self.id.strip())
        if isinstance(self.id, bool) or not isinstance(self.id, int) or not (1 <= self.id <= 255):
            raise InvalidDefinitionError(
                f"Platform color profile 'id' must be an integer between 1 and 255, got {self.id!r}."
            )
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidDefinitionError("Platform color profile 'name' must be a non-empty string.")
        if not isinstance(self.colors, (list, tuple)) or len(self.colors) != 8:
            raise InvalidDefinitionError(
                f"Platform color profile must define exactly 8 scanline colors, got {len(self.colors) if isinstance(self.colors, (list, tuple)) else type(self.colors)}."
            )
        for idx, c in enumerate(self.colors):
            if not isinstance(c, int) or isinstance(c, bool) or not (0 <= c <= 255):
                raise InvalidDefinitionError(
                    f"Color at scanline {idx + 1} must be an integer between 0x00 and 0xFF ($00-$FF), got {c!r}."
                )
            if (c & 1) != 0:
                raise InvalidDefinitionError(
                    f"Color at scanline {idx + 1} (0x{c:02X}) has bit 0 set. Atari color registers require even values."
                )
        if not isinstance(self.description, str):
            raise InvalidDefinitionError("Platform color profile 'description' must be a string.")

    def clone(self) -> PlatformColorProfile:
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": int(self.id),
            "name": self.name,
            "colors": [format_atari_color_hex(c) for c in self.colors],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlatformColorProfile:
        if not isinstance(data, dict):
            raise InvalidDefinitionError("PlatformColorProfile data must be a dictionary.")
        if "id" not in data or "name" not in data:
            raise InvalidDefinitionError("PlatformColorProfile missing 'id' or 'name'.")

        raw_id = data["id"]
        if isinstance(raw_id, str) and raw_id.strip().isdigit():
            prof_id = int(raw_id.strip())
        elif isinstance(raw_id, int) and not isinstance(raw_id, bool):
            prof_id = raw_id
        else:
            raise InvalidDefinitionError(
                f"Platform color profile 'id' must be an integer between 1 and 255, got {raw_id!r}."
            )

        raw_colors = data.get("colors", [])
        if not isinstance(raw_colors, (list, tuple)) or len(raw_colors) != 8:
            raise InvalidDefinitionError(
                f"Profile 'colors' must contain exactly 8 values, got {len(raw_colors) if isinstance(raw_colors, (list, tuple)) else raw_colors}."
            )

        parsed_colors: list[int] = []
        for idx, val in enumerate(raw_colors):
            try:
                parsed_colors.append(parse_atari_color_hex(val))
            except Exception as exc:
                raise InvalidDefinitionError(f"Invalid color at scanline {idx + 1}: {exc}") from exc

        prof = cls(
            id=prof_id,
            name=str(data["name"]).strip(),
            colors=parsed_colors,
            description=str(data.get("description", "")),
        )
        prof.validate()
        return prof


DEFAULT_PLATFORM_PROFILES: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Glacial Ice",
        "description": "Cyan/blue gradient suitable for winter/ice platforms",
        "colors": ["0x8E", "0x8C", "0x8A", "0x88", "0x86", "0x84", "0x82", "0x80"],
    },
    {
        "id": 2,
        "name": "Ancient Gold",
        "description": "Amber/gold gradient for royal platforms and castle trim",
        "colors": ["0x1E", "0x1C", "0x1A", "0x18", "0x16", "0x14", "0x12", "0x10"],
    },
    {
        "id": 3,
        "name": "Castle Stone",
        "description": "Neutral grayscale rock and stone ledges",
        "colors": ["0x0E", "0x0C", "0x0A", "0x08", "0x06", "0x04", "0x02", "0x00"],
    },
    {
        "id": 4,
        "name": "Forest Moss",
        "description": "Verdant green gradient for living branches and roots",
        "colors": ["0xCE", "0xCC", "0xCA", "0xC8", "0xC6", "0xC4", "0xC2", "0xC0"],
    },
]


@dataclass
class ProjectCatalogues:
    """Project-wide manager for Enemies, Secrets, and Platform Profiles catalogues."""
    enemies: dict[int, EnemyDefinition] = field(default_factory=dict)
    secrets: dict[int, SecretDefinition] = field(default_factory=dict)
    platform_profiles: dict[int, PlatformColorProfile] = field(default_factory=dict)
    sprites: dict[int, Any] = field(default_factory=dict)
    sprites_by_name: dict[str, Any] = field(default_factory=dict)
    sprites_path: Optional[Path] = None
    definitions_path: Optional[Path] = None
    enemies_path: Optional[Path] = None
    secrets_path: Optional[Path] = None
    platform_profiles_path: Optional[Path] = None

    def load_sprites_from_json(self, path: Path | str) -> int:
        """Load sprite definitions from a Sprite Studio JSON file."""
        target_path = Path(path).resolve()
        if not target_path.is_file():
            raise FileNotFoundError(f"Sprite file not found: {target_path}")

        try:
            from sprite_studio.io import load_project
            project = load_project(target_path)
            sprites_list = project.sprites
        except Exception:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sprites_list = []
            from types import SimpleNamespace
            for s_data in data.get("sprites", []):
                raw_id = s_data.get("id", 1)
                try:
                    s_id = int(raw_id)
                except (ValueError, TypeError):
                    s_id = 1
                desc = str(s_data.get("description", ""))
                sprites_list.append(SimpleNamespace(id=s_id, description=desc))

        self.sprites.clear()
        self.sprites_by_name.clear()
        for spr in sprites_list:
            norm_name = str(getattr(spr, "description", "")).strip().lower()
            if not norm_name:
                norm_name = f"sprite_{spr.id}"
            if norm_name in self.sprites_by_name:
                prev_spr = self.sprites_by_name[norm_name]
                raise DuplicateDefinitionIdError(
                    f"Błąd pliku sprite'ów '{target_path.name}': zduplikowana nazwa sprite'a '{getattr(spr, 'description', '')}' "
                    f"dla ID {prev_spr.id} oraz ID {spr.id}."
                )
            self.sprites[spr.id] = spr
            self.sprites_by_name[norm_name] = spr
        self.sprites_path = target_path

        # Sync in-memory definitions
        for defn in list(self.enemies.values()) + list(self.secrets.values()):
            if defn.sprite and defn.sprite.strip().lower() in self.sprites_by_name:
                defn.sprite_id = self.sprites_by_name[defn.sprite.strip().lower()].id
            elif not defn.sprite and defn.sprite_id in self.sprites:
                defn.sprite = getattr(self.sprites[defn.sprite_id], "description", f"Sprite_{defn.sprite_id}")

        return len(self.sprites)

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
        for profile in self.platform_profiles.values():
            profile.validate()
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

    def get_secret_dependency(self, defn_id: Any) -> Optional[int]:
        """Return the dependency secret ID (or None) for the given secret definition ID."""
        sec = self.get_secret(defn_id)
        if sec is not None:
            return sec.dependency
        return None

    def get_dependency_display_name(self, dependency: Optional[int]) -> str:
        """Return human-readable representation of a dependency."""
        if dependency is None:
            return "None"
        sec = self.get_secret(dependency)
        if sec is not None:
            return f"'{sec.name}' (ID {dependency})"
        return f"ID {dependency}"

    def check_scene_secret_dependency_conflict(
        self, scene: Any, target_secret_id: int, new_dependency: Optional[int]
    ) -> tuple[bool, str]:
        """Check if changing target_secret_id's dependency to new_dependency causes a row conflict on scene."""
        if scene is None or not hasattr(scene, "objects") or not hasattr(scene, "get_platform"):
            return True, ""

        try:
            target_id_norm = self._normalize_id(target_secret_id)
        except KeyError:
            return True, ""

        target_objs = [
            o for o in scene.objects
            if getattr(o, "type", None) in ("secret", "treasure")
            and getattr(o, "definition_id", None) is not None
            and self._safe_match_id(getattr(o, "definition_id", None), target_id_norm)
        ]
        if not target_objs:
            return True, ""

        for obj in target_objs:
            plat = scene.get_platform(obj.platform_id)
            if plat is None:
                continue
            row_y = plat.position.y
            row_secrets = [
                o for o in scene.get_row_objects(row_y, exclude_id=obj.id)
                if getattr(o, "type", None) in ("secret", "treasure")
            ]
            for other in row_secrets:
                other_def_raw = getattr(other, "definition_id", None)
                if self._safe_match_id(other_def_raw, target_id_norm):
                    other_dep = new_dependency
                else:
                    other_dep = self.get_secret_dependency(other_def_raw)
                if other_dep == new_dependency:
                    dep_name = self.get_dependency_display_name(new_dependency)
                    sec_name = self.secrets[target_id_norm].name if target_id_norm in self.secrets else f"ID {target_id_norm}"
                    return (
                        False,
                        f"Changing dependency of secret '{sec_name}' [{target_id_norm}] "
                        f"to {dep_name} causes a conflict on platform row y={row_y}:\n"
                        f"Secret '{obj.id}' and secret '{other.id}' would both have dependency {dep_name}.\n"
                        f"Only one secret per unique dependency is allowed per row.",
                    )
        return True, ""

    @staticmethod
    def _safe_match_id(val: Any, target_id: int) -> bool:
        if val is None:
            return False
        if isinstance(val, int) and not isinstance(val, bool):
            return val == target_id
        try:
            return int(str(val).strip()) == target_id
        except (ValueError, TypeError):
            return False

    def get_definition(self, kind: str, defn_id: Any) -> Optional[CatalogDefinition]:
        norm_kind = kind.lower()
        if norm_kind == "enemy":
            return self.get_enemy(defn_id)
        elif norm_kind in ("secret", "treasure"):
            return self.get_secret(defn_id)
        return None

    # -------------------------------------------------------------------------
    # Platform Color Profiles Management
    # -------------------------------------------------------------------------
    def add_platform_profile(self, profile: PlatformColorProfile) -> None:
        """Add a new platform color profile to the catalogue."""
        profile.validate()
        norm_id = self._normalize_id(profile.id)
        if norm_id in self.platform_profiles:
            raise DuplicateDefinitionIdError(
                f"Platform color profile with ID '{norm_id}' already exists."
            )
        self.platform_profiles[norm_id] = profile.clone()

    def update_platform_profile(self, profile: PlatformColorProfile) -> None:
        """Update an existing platform color profile."""
        profile.validate()
        norm_id = self._normalize_id(profile.id)
        self.platform_profiles[norm_id] = profile.clone()

    def get_platform_profile(self, profile_id: Optional[Any]) -> Optional[PlatformColorProfile]:
        """Look up a platform color profile by its ID (integer 1-255)."""
        if profile_id is None:
            return None
        try:
            norm_id = self._normalize_id(profile_id)
            return self.platform_profiles.get(norm_id)
        except (KeyError, ValueError, TypeError):
            return None

    def get_profile_platform_usage(self, profile_id: Any, scene: Optional[Any] = None) -> list[Any]:
        """Return all platforms in scene referencing the given profile ID."""
        if scene is None or not hasattr(scene, "platforms"):
            return []
        try:
            norm_id = self._normalize_id(profile_id)
        except (KeyError, ValueError, TypeError):
            return []
        return [p for p in scene.platforms if getattr(p, "color_profile_id", None) == norm_id]

    def remove_platform_profile(
        self,
        profile_id: Any,
        scene: Optional[Any] = None,
        force: bool = False,
    ) -> PlatformColorProfile:
        """Remove a platform color profile from the catalogue.

        If force=False and platforms in scene reference this profile, raises ProfileInUseError.
        If force=True, unassigns the profile from all referencing platforms and deletes it.
        """
        norm_id = self._normalize_id(profile_id)
        if norm_id not in self.platform_profiles:
            raise KeyError(f"Platform profile '{profile_id}' not found.")

        used = self.get_profile_platform_usage(norm_id, scene)
        if used and not force:
            plat_ids = ", ".join(getattr(p, "id", str(p)) for p in used)
            raise ProfileInUseError(
                f"Cannot delete profile '{self.platform_profiles[norm_id].name}' [{norm_id}]: "
                f"it is currently assigned to {len(used)} platform(s): {plat_ids}."
            )

        if used and force:
            for p in used:
                p.color_profile_id = None
            if scene is not None and hasattr(scene, "row_color_profiles"):
                for r in range(len(scene.row_color_profiles)):
                    if scene.row_color_profiles[r] == norm_id:
                        scene.row_color_profiles[r] = None

        return self.platform_profiles.pop(norm_id)

    def duplicate_platform_profile(
        self,
        profile_id: Any,
        new_id: Optional[Any] = None,
        new_name: Optional[str] = None,
    ) -> PlatformColorProfile:
        """Create a duplicate / variant of an existing platform profile."""
        norm_id = self._normalize_id(profile_id)
        if norm_id not in self.platform_profiles:
            raise KeyError(f"Platform profile '{profile_id}' not found.")

        src = self.platform_profiles[norm_id]
        if new_id is None:
            avail_ids = [i for i in range(1, 256) if i not in self.platform_profiles]
            if not avail_ids:
                raise InvalidDefinitionError("Cannot duplicate profile: all profile IDs (1-255) are in use.")
            target_id = avail_ids[0]
        else:
            target_id = self._normalize_id(new_id)

        if not new_name:
            new_name = f"{src.name} (Copy)"

        copied = PlatformColorProfile(
            id=target_id,
            name=new_name,
            colors=list(src.colors),
            description=src.description,
        )
        self.add_platform_profile(copied)
        return copied

    def clone(self) -> ProjectCatalogues:
        return copy.deepcopy(self)

    # -------------------------------------------------------------------------
    # Persistence: enemies.json, secrets.json & platform_profiles.json
    # -------------------------------------------------------------------------
    @classmethod
    def find_definitions_path(cls, base_dir: Path | str) -> Path:
        """Locate definitions.json in base_dir/scenes, base_dir, or base_dir/data."""
        base = Path(base_dir).resolve()
        scenes_dir = base / "scenes"
        data_dir = base / "data"
        if (scenes_dir / "definitions.json").is_file():
            return scenes_dir / "definitions.json"
        if (base / "definitions.json").is_file():
            return base / "definitions.json"
        if (data_dir / "definitions.json").is_file():
            return data_dir / "definitions.json"
        if scenes_dir.is_dir():
            return scenes_dir / "definitions.json"
        if data_dir.is_dir():
            return data_dir / "definitions.json"
        return scenes_dir / "definitions.json"

    @classmethod
    def find_catalogue_paths(cls, base_dir: Path | str) -> tuple[Path, Path]:
        """Locate definitions or legacy enemies.json and secrets.json."""
        base = Path(base_dir).resolve()
        scenes_dir = base / "scenes"
        data_dir = base / "data"
        def_path = cls.find_definitions_path(base)
        if def_path.is_file():
            return def_path, def_path
        if (scenes_dir / "enemies.json").is_file() or (scenes_dir / "secrets.json").is_file():
            return scenes_dir / "enemies.json", scenes_dir / "secrets.json"
        if (base / "enemies.json").is_file() or (base / "secrets.json").is_file():
            return base / "enemies.json", base / "secrets.json"
        if (data_dir / "enemies.json").is_file() or (data_dir / "secrets.json").is_file():
            return data_dir / "enemies.json", data_dir / "secrets.json"
        return def_path, def_path

    @classmethod
    def find_platform_profiles_path(cls, base_dir: Path | str) -> Path:
        """Locate definitions or legacy platform_profiles.json."""
        base = Path(base_dir).resolve()
        scenes_dir = base / "scenes"
        data_dir = base / "data"
        def_path = cls.find_definitions_path(base)
        if def_path.is_file():
            return def_path
        if (scenes_dir / "platform_profiles.json").is_file():
            return scenes_dir / "platform_profiles.json"
        if (base / "platform_profiles.json").is_file():
            return base / "platform_profiles.json"
        if (data_dir / "platform_profiles.json").is_file():
            return data_dir / "platform_profiles.json"
        return def_path

    def set_paths(
        self,
        enemies_path: Optional[Path | str] = None,
        secrets_path: Optional[Path | str] = None,
        platform_profiles_path: Optional[Path | str] = None,
        definitions_path: Optional[Path | str] = None,
    ) -> None:
        """Set explicit file paths for catalogues."""
        self.definitions_path = Path(definitions_path).resolve() if definitions_path else None
        self.enemies_path = Path(enemies_path).resolve() if enemies_path else None
        self.secrets_path = Path(secrets_path).resolve() if secrets_path else None
        self.platform_profiles_path = Path(platform_profiles_path).resolve() if platform_profiles_path else None
        if self.definitions_path is None and self.enemies_path and self.enemies_path == self.secrets_path:
            self.definitions_path = self.enemies_path

    def get_effective_definitions_path(self, base_dir: Path | str | None = None) -> Path:
        """Return the effective definitions_path."""
        if self.definitions_path is not None:
            return self.definitions_path
        return self.find_definitions_path(base_dir or Path.cwd())

    def get_effective_paths(self, base_dir: Path | str | None = None) -> tuple[Path, Path]:
        """Return the effective (enemies_path, secrets_path)."""
        if self.definitions_path is not None:
            return self.definitions_path, self.definitions_path
        default_enemies, default_secrets = self.find_catalogue_paths(base_dir or Path.cwd())
        eff_enemies = self.enemies_path if self.enemies_path is not None else default_enemies
        eff_secrets = self.secrets_path if self.secrets_path is not None else default_secrets
        return eff_enemies, eff_secrets

    def get_effective_platform_profiles_path(self, base_dir: Path | str | None = None) -> Path:
        """Return the effective platform_profiles_path."""
        if self.definitions_path is not None:
            return self.definitions_path
        if self.platform_profiles_path is not None:
            return self.platform_profiles_path
        return self.find_platform_profiles_path(base_dir or Path.cwd())

    @classmethod
    def load_from_paths(
        cls,
        enemies_path: Optional[Path | str] = None,
        secrets_path: Optional[Path | str] = None,
        platform_profiles_path: Optional[Path | str] = None,
        definitions_path: Optional[Path | str] = None,
    ) -> ProjectCatalogues:
        """Load catalogues from specific file path(s)."""
        d_path = Path(definitions_path).resolve() if definitions_path else None
        e_path = Path(enemies_path).resolve() if enemies_path else None
        s_path = Path(secrets_path).resolve() if secrets_path else None
        p_path = Path(platform_profiles_path).resolve() if platform_profiles_path else None

        if d_path is None and e_path and e_path == s_path:
            d_path = e_path

        catalogues = cls(
            definitions_path=d_path,
            enemies_path=e_path,
            secrets_path=s_path,
            platform_profiles_path=p_path,
        )

        # 1. Load from unified definitions.json if present
        if d_path and d_path.is_file():
            try:
                with open(d_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    raise CorruptedCatalogueFileError(f"Definitions file is empty: {d_path}")
                data = json.loads(content)
            except json.JSONDecodeError as err:
                raise CorruptedCatalogueFileError(f"Invalid JSON in {d_path.name}: {err}") from err

            if not isinstance(data, dict):
                raise CorruptedCatalogueFileError(f"Top-level JSON in {d_path.name} must be an object.")

            # Load enemies
            for idx, item in enumerate(data.get("enemies", [])):
                try:
                    defn = EnemyDefinition.from_dict(item)
                    if defn.id in catalogues.enemies:
                        raise DuplicateDefinitionIdError(f"Duplicate enemy ID '{defn.id}' in {d_path.name}.")
                    catalogues.enemies[defn.id] = defn
                except Exception as err:
                    raise CorruptedCatalogueFileError(f"Error in {d_path.name} enemies at entry {idx}: {err}") from err

            # Load secrets
            for idx, item in enumerate(data.get("secrets", [])):
                try:
                    defn = SecretDefinition.from_dict(item)
                    if defn.id in catalogues.secrets:
                        raise DuplicateDefinitionIdError(f"Duplicate secret ID '{defn.id}' in {d_path.name}.")
                    catalogues.secrets[defn.id] = defn
                except Exception as err:
                    raise CorruptedCatalogueFileError(f"Error in {d_path.name} secrets at entry {idx}: {err}") from err

            try:
                catalogues.validate_secrets_chain()
            except Exception as err:
                raise CorruptedCatalogueFileError(f"Invalid secret dependency chain in {d_path.name}: {err}") from err

            # Load platform profiles
            raw_profiles = data.get("platform_profiles") or data.get("profiles", [])
            for idx, item in enumerate(raw_profiles):
                try:
                    prof = PlatformColorProfile.from_dict(item)
                    if prof.id in catalogues.platform_profiles:
                        raise DuplicateDefinitionIdError(f"Duplicate platform profile ID '{prof.id}' in {d_path.name}.")
                    catalogues.platform_profiles[prof.id] = prof
                except Exception as err:
                    raise CorruptedCatalogueFileError(f"Error in {d_path.name} profiles at entry {idx}: {err}") from err

            if not catalogues.platform_profiles:
                for def_item in DEFAULT_PLATFORM_PROFILES:
                    prof = PlatformColorProfile.from_dict(def_item)
                    catalogues.platform_profiles[prof.id] = prof

            return catalogues

        # 2. Legacy fallback: separate individual files
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

        # Load platform profiles
        if p_path and p_path.is_file():
            try:
                with open(p_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    raise CorruptedCatalogueFileError(f"Platform profiles catalogue file is empty: {p_path}")
                data = json.loads(content)
            except json.JSONDecodeError as err:
                raise CorruptedCatalogueFileError(f"Invalid JSON in {p_path.name}: {err}") from err

            if not isinstance(data, dict):
                raise CorruptedCatalogueFileError(f"Top-level JSON in {p_path.name} must be an object.")

            profiles_list = data.get("profiles") or data.get("platform_profiles", [])
            if not isinstance(profiles_list, list):
                raise CorruptedCatalogueFileError(f"'profiles' key in {p_path.name} must be a list.")

            for idx, item in enumerate(profiles_list):
                try:
                    prof = PlatformColorProfile.from_dict(item)
                    if prof.id in catalogues.platform_profiles:
                        raise DuplicateDefinitionIdError(
                            f"Duplicate platform profile ID '{prof.id}' in {p_path.name}."
                        )
                    catalogues.platform_profiles[prof.id] = prof
                except Exception as err:
                    raise CorruptedCatalogueFileError(
                        f"Error in {p_path.name} at entry {idx}: {err}"
                    ) from err
        else:
            for def_item in DEFAULT_PLATFORM_PROFILES:
                prof = PlatformColorProfile.from_dict(def_item)
                catalogues.platform_profiles[prof.id] = prof

        return catalogues

    @classmethod
    def load_from_dir(cls, base_dir: Path | str) -> ProjectCatalogues:
        """Load catalogues from directory, preferring definitions.json."""
        def_path = cls.find_definitions_path(base_dir)
        if def_path.is_file():
            return cls.load_from_paths(definitions_path=def_path)
        enemies_path, secrets_path = cls.find_catalogue_paths(base_dir)
        profiles_path = cls.find_platform_profiles_path(base_dir)
        return cls.load_from_paths(enemies_path, secrets_path, profiles_path)

    def save_to_dir(self, base_dir: Path | str | None = None) -> None:
        """Atomically save all catalogues. If custom individual paths were set, save to those paths; otherwise save to definitions.json."""
        if self.definitions_path is None and (self.enemies_path is not None or self.secrets_path is not None or self.platform_profiles_path is not None):
            self.save_to_paths(
                enemies_path=self.enemies_path,
                secrets_path=self.secrets_path,
                platform_profiles_path=self.platform_profiles_path,
            )
            return

        def_path = self.get_effective_definitions_path(base_dir)
        def_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "enemies": [e.to_dict() for e in sorted(self.enemies.values(), key=lambda e: e.id)],
            "secrets": [s.to_dict() for s in sorted(self.secrets.values(), key=lambda s: s.id)],
            "platform_profiles": [p.to_dict() for p in sorted(self.platform_profiles.values(), key=lambda p: p.id)],
        }
        self._atomic_save_json(def_path, data)

    def save_to_paths(
        self,
        enemies_path: Optional[Path | str] = None,
        secrets_path: Optional[Path | str] = None,
        platform_profiles_path: Optional[Path | str] = None,
        definitions_path: Optional[Path | str] = None,
    ) -> None:
        """Atomically save catalogues to specific file paths if provided."""
        if definitions_path is not None:
            d_p = Path(definitions_path).resolve()
            d_p.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "enemies": [e.to_dict() for e in sorted(self.enemies.values(), key=lambda e: e.id)],
                "secrets": [s.to_dict() for s in sorted(self.secrets.values(), key=lambda s: s.id)],
                "platform_profiles": [p.to_dict() for p in sorted(self.platform_profiles.values(), key=lambda p: p.id)],
            }
            self._atomic_save_json(d_p, data)
            return

        # Legacy separate files save
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
        if platform_profiles_path is not None:
            p_p = Path(platform_profiles_path).resolve()
            p_p.parent.mkdir(parents=True, exist_ok=True)
            profiles_data = {
                "version": 1,
                "profiles": [p.to_dict() for p in sorted(self.platform_profiles.values(), key=lambda p: p.id)],
            }
            self._atomic_save_json(p_p, profiles_data)

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
