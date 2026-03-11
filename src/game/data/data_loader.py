from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from game.data.json_schema_validator import JsonSchemaValidator
from game.actors.player import PlayerInstance
from game.actors.enemy import Enemy
from game.catalog.models import Catalog, DungeonTemplate, EncounterTemplate, EnemyTemplate, PlayerTemplate, RoomTemplate
from game.combat.attack import Attack
from game.combat.spell import Spell
from game.combat.status_effect import StatusEffect
from game.entity.entity import Entity
from game.entity.blocks.archetype import Archetype, WeaponConstraints
from game.entity.blocks.race import Race
from game.entity.blocks.weapon import Weapon
from game.enums import (
	AttackType,
	ControlType,
	DamageType,
	DifficultyType,
	RestType,
	SpellType,
	StatusEffectType,
	WeaponDelivery,
	WeaponHandling,
	WeaponMagicType,
	WeaponProficiency,
	WeaponWeightClass,
)


class DataLoaderError(ValueError):
	"""Raised when loading or cross-reference hydration fails."""


DATASET_LOAD_ORDER = [
	"status_effects",
	"attacks",
	"spells",
	"weapons",
	"races",
	"archetypes",
	"players",
	"enemies",
	"dungeons",
]


class DataLoader:
	"""Load, validate, and hydrate game data from JSON files."""

	def __init__(
		self,
		data_dir: Path | str,
		schema_dir: Optional[Path | str] = None,
		validate_schema: bool = True,
	) -> None:
		self.data_dir = Path(data_dir)
		self.schema_dir = Path(schema_dir) if schema_dir else self.data_dir / "schemata"
		self.validate_schema = validate_schema
		self.validator = JsonSchemaValidator(self.schema_dir)

	def _read_json(self, path: Path) -> Any:
		if not path.exists():
			raise FileNotFoundError(f"Data file not found: {path}")
		with path.open("r", encoding="utf-8") as f:
			return json.load(f)

	def _read_dataset(self, dataset_name: str) -> List[dict]:
		path = self.data_dir / f"{dataset_name}.json"
		payload = self._read_json(path)
		if not isinstance(payload, list):
			raise DataLoaderError(f"Dataset '{dataset_name}' must be a JSON array")
		if self.validate_schema:
			self.validator.validate_named_dataset(dataset_name, payload)
		return payload

	def load_raw_data(self) -> Dict[str, List[dict]]:
		return {name: self._read_dataset(name) for name in DATASET_LOAD_ORDER}

	def _index_by_id(self, rows: List[dict], dataset_name: str) -> Dict[str, dict]:
		index: Dict[str, dict] = {}
		for row in rows:
			item_id = str(row.get("id", ""))
			if not item_id:
				raise DataLoaderError(f"Dataset '{dataset_name}' has row without 'id'")
			if item_id in index:
				raise DataLoaderError(
					f"Dataset '{dataset_name}' has duplicate id '{item_id}'"
				)
			index[item_id] = row
		return index

	def _require_id(self, index: Dict[str, Any], item_id: str, source: str) -> Any:
		if item_id not in index:
			raise DataLoaderError(f"Missing reference '{item_id}' in {source}")
		return index[item_id]

	def _validate_cross_references(self, raw: Dict[str, List[dict]]) -> None:
		idx = {name: self._index_by_id(rows, name) for name, rows in raw.items()}

		for attack in raw["attacks"]:
			for effect_ref in attack.get("parameters", {}).get("applied_status_effects", []):
				effect_id = str(effect_ref.get("status_effect_id", ""))
				self._require_id(idx["status_effects"], effect_id, "status_effects")

		for spell in raw["spells"]:
			for effect_ref in spell.get("parameters", {}).get("applied_status_effects", []):
				effect_id = str(effect_ref.get("status_effect_id", ""))
				self._require_id(idx["status_effects"], effect_id, "status_effects")

		for weapon in raw["weapons"]:
			for attack_id in weapon.get("known_attack_ids", []):
				self._require_id(idx["attacks"], attack_id, "attacks")
			for spell_id in weapon.get("known_spell_ids", []):
				self._require_id(idx["spells"], spell_id, "spells")

		for race in raw["races"]:
			for archetype_id in race.get("archetype_constraints", []):
				self._require_id(idx["archetypes"], archetype_id, "archetypes")
			for attack_id in race.get("known_attack_ids", []):
				self._require_id(idx["attacks"], attack_id, "attacks")
			for spell_id in race.get("known_spell_ids", []):
				self._require_id(idx["spells"], spell_id, "spells")

		for archetype in raw["archetypes"]:
			for attack_id in archetype.get("known_attack_ids", []):
				self._require_id(idx["attacks"], attack_id, "attacks")
			for spell_id in archetype.get("known_spell_ids", []):
				self._require_id(idx["spells"], spell_id, "spells")

		for dataset in ["players", "enemies"]:
			for entity in raw[dataset]:
				self._require_id(idx["races"], entity.get("race_id", ""), "races")
				self._require_id(idx["archetypes"], entity.get("archetype_id", ""), "archetypes")
				for weapon_id in entity.get("weapon_ids", []):
					self._require_id(idx["weapons"], weapon_id, "weapons")

		for dungeon in raw["dungeons"]:
			room_ids = {str(room.get("id", "")) for room in dungeon.get("rooms", [])}
			start_room = str(dungeon.get("start_room_id", ""))
			end_room = str(dungeon.get("end_room_id", ""))
			if start_room not in room_ids:
				raise DataLoaderError(
					f"Dungeon '{dungeon.get('id')}' references missing start room '{start_room}'"
				)
			if end_room not in room_ids:
				raise DataLoaderError(
					f"Dungeon '{dungeon.get('id')}' references missing end room '{end_room}'"
				)
			for room in dungeon.get("rooms", []):
				for connection_id in room.get("connection_room_ids", []):
					if connection_id not in room_ids:
						raise DataLoaderError(
							f"Room '{room.get('id')}' references missing room '{connection_id}'"
						)
				for encounter in room.get("encounters", []):
					for enemy_id in encounter.get("enemy_ids", []):
						self._require_id(idx["enemies"], enemy_id, "enemies")

	def validate(self) -> None:
		raw = self.load_raw_data()
		self._validate_cross_references(raw)

	def load_catalog(self) -> Catalog:
		"""Load catalog templates for runtime instantiation without hydrating mutable dungeon state."""
		raw = self.load_raw_data()
		self._validate_cross_references(raw)

		status_effects: Dict[str, StatusEffect] = {}
		for row in raw["status_effects"]:
			effect_id = row["id"]
			status_effects[effect_id] = StatusEffect(
				id=effect_id,
				name=str(row.get("name", "")),
				description=str(row.get("description", "")),
				type=StatusEffectType(str(row.get("type", "control"))),
				parameters=dict(row.get("parameters", {})),
			)

		def _hydrate_applied_effects(effect_refs: List[dict]) -> List[dict]:
			hydrated: List[dict] = []
			for effect_ref in effect_refs:
				effect_id = str(effect_ref.get("status_effect_id", ""))
				effect = status_effects[effect_id]
				hydrated.append(
					{
						"status_effect": effect,
						"duration": int(effect_ref.get("duration", 0)),
					}
				)
			return hydrated

		attacks: Dict[str, Attack] = {}
		for row in raw["attacks"]:
			params = dict(row.get("parameters", {}))
			applied_refs = list(params.get("applied_status_effects", []))
			params["applied_status_effects"] = _hydrate_applied_effects(applied_refs)
			attacks[row["id"]] = Attack(
				id=row["id"],
				name=str(row.get("name", "")),
				description=str(row.get("description", "")),
				type=AttackType(str(row.get("type", "melee"))),
				parameters=params,
			)

		spells: Dict[str, Spell] = {}
		for row in raw["spells"]:
			params = dict(row.get("parameters", {}))
			applied_refs = list(params.get("applied_status_effects", []))
			params["applied_status_effects"] = _hydrate_applied_effects(applied_refs)
			spells[row["id"]] = Spell(
				id=row["id"],
				name=str(row.get("name", "")),
				description=str(row.get("description", "")),
				type=SpellType(str(row.get("type", "attack"))),
				spell_cost=int(row.get("spell_cost", 0)),
				parameters=params,
			)

		weapons: Dict[str, Weapon] = {}
		for row in raw["weapons"]:
			weapons[row["id"]] = Weapon(
				id=row["id"],
				name=str(row.get("name", "")),
				description=str(row.get("description", "")),
				proficiency=WeaponProficiency(str(row.get("proficiency", "simple"))),
				handling=WeaponHandling(str(row.get("handling", "one_handed"))),
				weight_class=WeaponWeightClass(str(row.get("weight_class", "light"))),
				delivery=WeaponDelivery(str(row.get("delivery", "melee"))),
				magic_type=WeaponMagicType(str(row.get("magic_type", "mundane"))),
				known_attacks=[attacks[item_id] for item_id in row.get("known_attack_ids", [])],
				known_spells=[spells[item_id] for item_id in row.get("known_spell_ids", [])],
			)

		races: Dict[str, Race] = {}
		for row in raw["races"]:
			races[row["id"]] = Race(
				id=row["id"],
				name=str(row.get("name", "")),
				description=str(row.get("description", "")),
				base_hp=int(row.get("base_hp", 0)),
				base_AC=int(row.get("base_AC", 0)),
				base_spell_slots=int(row.get("base_spell_slots", 0)),
				resistances=[DamageType(item) for item in row.get("resistances", [])],
				immunities=[DamageType(item) for item in row.get("immunities", [])],
				vulnerabilities=[DamageType(item) for item in row.get("vulnerabilities", [])],
				cc_immunities=[ControlType(item) for item in row.get("cc_immunities", [])],
				archetype_constraints=list(row.get("archetype_constraints", [])),
				known_spells=[spells[item_id] for item_id in row.get("known_spell_ids", [])],
				known_attacks=[attacks[item_id] for item_id in row.get("known_attack_ids", [])],
			)

		archetypes: Dict[str, Archetype] = {}
		for row in raw["archetypes"]:
			constraints = dict(row.get("weapon_constraints", {}))
			archetypes[row["id"]] = Archetype(
				id=row["id"],
				name=str(row.get("name", "")),
				description=str(row.get("description", "")),
				hp_mod=int(row.get("hp_mod", 0)),
				AC_mod=int(row.get("AC_mod", 0)),
				spell_slot_mod=int(row.get("spell_slot_mod", 0)),
				initiative_mod=int(row.get("initiative_mod", 0)),
				resistances=[DamageType(item) for item in row.get("resistances", [])],
				immunities=[DamageType(item) for item in row.get("immunities", [])],
				vulnerabilities=[DamageType(item) for item in row.get("vulnerabilities", [])],
				cc_immunities=[ControlType(item) for item in row.get("cc_immunities", [])],
				weapon_constraints=WeaponConstraints(
					proficiency=[WeaponProficiency(item) for item in constraints.get("proficiency", [])],
					handling=[WeaponHandling(item) for item in constraints.get("handling", [])],
					weight_class=[WeaponWeightClass(item) for item in constraints.get("weight_class", [])],
					delivery=[WeaponDelivery(item) for item in constraints.get("delivery", [])],
					magic_type=[WeaponMagicType(item) for item in constraints.get("magic_type", [])],
				),
				known_spells=[spells[item_id] for item_id in row.get("known_spell_ids", [])],
				known_attacks=[attacks[item_id] for item_id in row.get("known_attack_ids", [])],
			)

		player_templates: Dict[str, PlayerTemplate] = {}
		for row in raw["players"]:
			player_id = row["id"]
			entity = Entity.create(
				id=player_id,
				name=str(row.get("name", "")),
				description=str(row.get("description", "")),
				race=races[row["race_id"]],
				archetype=archetypes[row["archetype_id"]],
				weapons=[weapons[item_id] for item_id in row.get("weapon_ids", [])],
			)
			player_seed = PlayerInstance(
				id=entity.id,
				name=entity.name,
				description=entity.description,
				race=entity.race,
				archetype=entity.archetype,
				hp=entity.hp,
				max_hp=entity.max_hp,
				base_AC=entity.base_AC,
				AC=entity.AC,
				spell_slots=entity.spell_slots,
				max_spell_slots=entity.max_spell_slots,
				initiative_mod=entity.initiative_mod,
				attack_modifier_bonus=entity.attack_modifier_bonus,
				active_status_effects=entity.active_status_effects,
				weapons=entity.weapons,
				known_attacks=entity.known_attacks,
				known_spells=entity.known_spells,
				resistances=entity.resistances,
				immunities=entity.immunities,
				vulnerabilities=entity.vulnerabilities,
				cc_immunities=entity.cc_immunities,
				player_instance_id="",
			)
			player_templates[player_id] = PlayerTemplate.from_player(player_id, player_seed)

		enemy_templates: Dict[str, EnemyTemplate] = {}
		for row in raw["enemies"]:
			enemy_id = row["id"]
			entity = Entity.create(
				id=enemy_id,
				name=str(row.get("name", "")),
				description=str(row.get("description", "")),
				race=races[row["race_id"]],
				archetype=archetypes[row["archetype_id"]],
				weapons=[weapons[item_id] for item_id in row.get("weapon_ids", [])],
			)
			enemy = Enemy(
				id=entity.id,
				name=entity.name,
				description=entity.description,
				race=entity.race,
				archetype=entity.archetype,
				hp=entity.hp,
				max_hp=entity.max_hp,
				base_AC=entity.base_AC,
				AC=entity.AC,
				spell_slots=entity.spell_slots,
				max_spell_slots=entity.max_spell_slots,
				initiative_mod=entity.initiative_mod,
				attack_modifier_bonus=entity.attack_modifier_bonus,
				active_status_effects=entity.active_status_effects,
				weapons=entity.weapons,
				known_attacks=entity.known_attacks,
				known_spells=entity.known_spells,
				resistances=entity.resistances,
				immunities=entity.immunities,
				vulnerabilities=entity.vulnerabilities,
				cc_immunities=entity.cc_immunities,
				enemy_instance_id="",
				persona=str(row.get("persona", "")),
			)
			enemy_templates[enemy_id] = EnemyTemplate.from_enemy(enemy_id, enemy)

		dungeon_templates: Dict[str, DungeonTemplate] = {}
		for dungeon_row in raw["dungeons"]:
			room_templates: List[RoomTemplate] = []
			for room_row in dungeon_row.get("rooms", []):
				encounter_templates: List[EncounterTemplate] = []
				for encounter_row in room_row.get("encounters", []):
					encounter_templates.append(
						EncounterTemplate(
							id=str(encounter_row.get("id", "")),
							name=str(encounter_row.get("name", "")),
							description=str(encounter_row.get("description", "")),
							difficulty=DifficultyType(str(encounter_row.get("difficulty", "easy"))),
							clear_reward=int(encounter_row.get("clear_reward", 0)),
							enemy_template_ids=tuple(str(enemy_id) for enemy_id in encounter_row.get("enemy_ids", [])),
						)
					)

				room_templates.append(
					RoomTemplate(
						id=str(room_row.get("id", "")),
						name=str(room_row.get("name", "")),
						description=str(room_row.get("description", "")),
						connections=tuple(str(item) for item in room_row.get("connection_room_ids", [])),
						encounters=tuple(encounter_templates),
						allowed_rests=tuple(RestType(item) for item in room_row.get("allowed_rests", [])),
					)
				)

			dungeon_id = str(dungeon_row.get("id", ""))
			dungeon_templates[dungeon_id] = DungeonTemplate(
				id=dungeon_id,
				name=str(dungeon_row.get("name", "")),
				description=str(dungeon_row.get("description", "")),
				difficulty=DifficultyType(str(dungeon_row.get("difficulty", "easy"))),
				start_room=str(dungeon_row.get("start_room_id", "")),
				end_room=str(dungeon_row.get("end_room_id", "")),
				rooms=tuple(room_templates),
			)

		return Catalog(
			player_templates=player_templates,
			enemy_templates=enemy_templates,
			dungeon_templates=dungeon_templates,
		)


def load_game_catalog(
	data_dir: Path | str = Path("data"),
	schema_dir: Optional[Path | str] = None,
	validate_schema: bool = True,
) -> Catalog:
	"""Convenience wrapper to load catalog templates for runtime instantiation."""
	return DataLoader(
		data_dir=data_dir,
		schema_dir=schema_dir,
		validate_schema=validate_schema,
	).load_catalog()

