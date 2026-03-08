from game.actors.enemy import Enemy
from game.actors.player import Player
from game.combat.attack import Attack
from game.combat.spell import Spell
from game.dungeons.dungeon import Encounter
from game.entity.entity import Entity
from game.entity.blocks.archetype import Archetype, WeaponConstraints
from game.entity.blocks.race import Race
from game.entity.blocks.weapon import Weapon
from game.enums import (
    AttackType,
    ControlType,
    DamageType,
    DifficultyType,
    SpellType,
    WeaponDelivery,
    WeaponHandling,
    WeaponMagicType,
    WeaponProficiency,
    WeaponWeightClass,
)


def _spell(spell_id: str) -> Spell:
    return Spell(
        id=spell_id,
        name=spell_id,
        description="",
        type=SpellType.ATTACK,
        spell_cost=1,
        parameters={},
    )


def _attack(attack_id: str) -> Attack:
    return Attack(
        id=attack_id,
        name=attack_id,
        description="",
        type=AttackType.MELEE,
        parameters={},
    )


def _race() -> Race:
    return Race(
        id="race_1",
        name="Race",
        description="",
        base_hp=10,
        base_AC=10,
        base_spell_slots=2,
    )


def _archetype() -> Archetype:
    return Archetype(
        id="arch_1",
        name="Archetype",
        description="",
        hp_mod=2,
        AC_mod=1,
        spell_slot_mod=1,
        initiative_mod=0,
        weapon_constraints=WeaponConstraints(),
    )


def _weapon() -> Weapon:
    return Weapon(
        id="wpn_1",
        name="Weapon",
        description="",
        proficiency=WeaponProficiency.SIMPLE,
        handling=WeaponHandling.ONE_HANDED,
        weight_class=WeaponWeightClass.LIGHT,
        delivery=WeaponDelivery.MELEE,
        magic_type=WeaponMagicType.MUNDANE,
    )


def test_entity_merged_spells_uses_spell_sources() -> None:
    race = _race()
    archetype = _archetype()
    weapon = _weapon()

    race.known_spells = [_spell("race_spell")]
    archetype.known_spells = [_spell("arch_spell")]
    weapon.known_spells = [_spell("weapon_spell")]

    # Give attacks too so this test would fail if spells accidentally read attacks.
    race.known_attacks = [_attack("race_attack")]
    archetype.known_attacks = [_attack("arch_attack")]
    weapon.known_attacks = [_attack("weapon_attack")]

    entity = Entity.create(
        id="entity_1",
        name="Entity",
        description="",
        race=race,
        archetype=archetype,
        weapons=[weapon],
    )

    merged_spell_ids = {spell.id for spell in entity.merged_spells}
    assert merged_spell_ids == {"race_spell", "arch_spell", "weapon_spell"}


def test_entity_to_dict_uses_weapons_and_merged_cc_immunities() -> None:
    race = _race()
    archetype = _archetype()

    race.cc_immunities = [ControlType.SILENCED]
    archetype.cc_immunities = [ControlType.STUNNED]

    entity = Entity.create(
        id="entity_2",
        name="Entity",
        description="",
        race=race,
        archetype=archetype,
        weapons=[],
    )
    entity.cc_immunities = [ControlType.ASLEEP]

    payload = entity.to_dict()

    assert "weapon" not in payload
    assert payload["weapons"] == []
    assert set(payload["cc_immunities"]) == {"silenced", "stunned", "asleep"}


def test_entity_merged_cc_immunities_include_entity_specific_values() -> None:
    race = _race()
    archetype = _archetype()
    race.cc_immunities = [ControlType.SILENCED]
    archetype.cc_immunities = [ControlType.STUNNED]

    entity = Entity.create(
        id="entity_3",
        name="Entity",
        description="",
        race=race,
        archetype=archetype,
        weapons=[],
    )
    entity.cc_immunities = [ControlType.RESTRAINED]
    entity.vulnerabilities = [DamageType.FIRE]

    merged_values = {value.value for value in entity.merged_cc_immunities}
    assert merged_values == {"silenced", "stunned", "restrained"}


def test_player_from_dict_preserves_attack_modifier_bonus() -> None:
    player = Player.from_dict(
        {
            "id": "player_1",
            "name": "Player",
            "description": "",
            "race": {},
            "archetype": {},
            "attack_modifier_bonus": 7,
            "player_instance_id": "p_inst_1",
        }
    )

    assert player.attack_modifier_bonus == 7


def test_enemy_from_dict_preserves_attack_modifier_bonus() -> None:
    enemy = Enemy.from_dict(
        {
            "id": "enemy_1",
            "name": "Enemy",
            "description": "",
            "race": {},
            "archetype": {},
            "attack_modifier_bonus": 5,
            "enemy_instance_id": "e_inst_1",
            "persona": "aggressive",
        }
    )

    assert enemy.attack_modifier_bonus == 5


def test_encounter_enemy_round_trip_and_legacy_id_list() -> None:
    base_enemy = Enemy.from_dict(
        {
            "id": "enemy_x",
            "name": "Enemy X",
            "description": "",
            "race": {},
            "archetype": {},
        }
    )

    encounter = Encounter(
        id="enc_1",
        name="Encounter",
        description="",
        difficulty=DifficultyType.EASY,
        cleared=False,
        clear_reward=1,
        enemies=[base_enemy],
    )

    round_trip = Encounter.from_dict(encounter.to_dict())
    assert len(round_trip.enemies) == 1
    assert round_trip.enemies[0].id == "enemy_x"

    legacy_payload = {
        "id": "enc_legacy",
        "name": "Legacy",
        "description": "",
        "difficulty": "easy",
        "cleared": False,
        "clear_reward": 0,
        "enemies": ["enemy_legacy"],
    }
    legacy = Encounter.from_dict(legacy_payload)
    assert len(legacy.enemies) == 1
    assert legacy.enemies[0].id == "enemy_legacy"
