from dataclasses import dataclass

from game.entity.entity import Entity


def _get_str(data: dict, key: str) -> str:
	return str(data.get(key, ""))


@dataclass
class PlayerInstance(Entity):
	player_instance_id: str = ""

	def to_dict(self) -> dict:
		payload = super().to_dict()
		payload["player_instance_id"] = self.player_instance_id
		return payload

	@classmethod
	def from_dict(cls, data: dict) -> "PlayerInstance":
		entity = Entity.from_dict(data)
		return cls(
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
			player_instance_id=_get_str(data, "player_instance_id"),
		)


def create_player_instance(
	id: str,
	name: str,
	description: str,
	race,
	archetype,
	weapons,
	player_instance_id: str = "",
) -> PlayerInstance:
	assigned_instance_id = player_instance_id or "player_1"
	entity = Entity.create(
		id=id,
		name=name,
		description=description,
		race=race,
		archetype=archetype,
		weapons=weapons,
	)
	return PlayerInstance(
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
		player_instance_id=assigned_instance_id,
	)
