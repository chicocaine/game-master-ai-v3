from dataclasses import dataclass

from game.entity.entity import Entity


def _get_str(data: dict, key: str) -> str:
	return str(data.get(key, ""))


@dataclass
class Enemy(Entity):
	enemy_instance_id: str = ""
	persona: str = ""

	def to_dict(self) -> dict:
		payload = super().to_dict()
		payload["enemy_instance_id"] = self.enemy_instance_id
		payload["persona"] = self.persona
		return payload

	@classmethod
	def from_dict(cls, data: dict) -> "Enemy":
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
			enemy_instance_id=_get_str(data, "enemy_instance_id"),
			persona=_get_str(data, "persona"),
		)


def create_enemy(
	id: str,
	name: str,
	description: str,
	race,
	archetype,
	weapons,
	enemy_instance_id: str,
	persona: str = "",
) -> Enemy:
	entity = Entity.create(
		id=id,
		name=name,
		description=description,
		race=race,
		archetype=archetype,
		weapons=weapons,
	)
	return Enemy(
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
		enemy_instance_id=enemy_instance_id,
		persona=persona,
	)
