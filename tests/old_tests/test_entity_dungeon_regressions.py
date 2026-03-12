from game.actors.enemy import Enemy
from game.actors.player import PlayerInstance, create_player_instance
from game.combat.attack import Attack
from game.combat.spell import Spell
from game.dungeons.dungeon import Dungeon, Encounter, Room
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
    race = Race(
        id="race_1",
        name="Race",
        description="",
        base_hp=10,
        base_AC=10,
        base_spell_slots=2,
        known_spells=[_spell("race_spell")],
        known_attacks=[_attack("race_attack")],
    )
    archetype = Archetype(
        id="arch_1",
        name="Archetype",
        description="",
        hp_mod=2,
        AC_mod=1,
        spell_slot_mod=1,
        initiative_mod=0,
        weapon_constraints=WeaponConstraints(),
        known_spells=[_spell("arch_spell")],
        known_attacks=[_attack("arch_attack")],
    )
    weapon = Weapon(
        id="wpn_1",
        name="Weapon",
        description="",
        proficiency=WeaponProficiency.SIMPLE,
        handling=WeaponHandling.ONE_HANDED,
        weight_class=WeaponWeightClass.LIGHT,
        delivery=WeaponDelivery.MELEE,
        magic_type=WeaponMagicType.MUNDANE,
        known_spells=[_spell("weapon_spell")],
        known_attacks=[_attack("weapon_attack")],
    )

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
    race = Race(
        id="race_1",
        name="Race",
        description="",
        base_hp=10,
        base_AC=10,
        base_spell_slots=2,
        cc_immunities=[ControlType.SILENCED],
    )
    archetype = Archetype(
        id="arch_1",
        name="Archetype",
        description="",
        hp_mod=2,
        AC_mod=1,
        spell_slot_mod=1,
        initiative_mod=0,
        weapon_constraints=WeaponConstraints(),
        cc_immunities=[ControlType.STUNNED],
    )

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
    race = Race(
        id="race_1",
        name="Race",
        description="",
        base_hp=10,
        base_AC=10,
        base_spell_slots=2,
        cc_immunities=[ControlType.SILENCED],
    )
    archetype = Archetype(
        id="arch_1",
        name="Archetype",
        description="",
        hp_mod=2,
        AC_mod=1,
        spell_slot_mod=1,
        initiative_mod=0,
        weapon_constraints=WeaponConstraints(),
        cc_immunities=[ControlType.STUNNED],
    )

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
    player = PlayerInstance.from_dict(
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


def test_create_player_assigns_default_instance_id_when_missing() -> None:
    player = create_player_instance(
        id="player_default",
        name="Player Default",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )

    assert player.player_instance_id == "player_1"


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


def test_dungeon_round_trip_preserves_allowed_rests_and_connections() -> None:
    room = Room(
        id="room_1",
        name="Start",
        description="",
        is_visited=False,
        is_cleared=False,
        is_rested=False,
        connections=["room_2"],
        encounters=[],
        allowed_rests=[RestType.SHORT, RestType.LONG],
    )
    dungeon = Dungeon(
        id="dng_1",
        name="Dungeon",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_1",
        end_room="room_1",
        rooms=[room],
    )

    restored = Dungeon.from_dict(dungeon.to_dict())

    assert restored.rooms[0].connections == ["room_2"]
    assert restored.rooms[0].allowed_rests == [RestType.SHORT, RestType.LONG]


def test_room_from_dict_defaults_to_uncleared_when_encounters_present() -> None:
    payload = {
        "id": "room_1",
        "name": "Room",
        "description": "",
        "is_visited": False,
        "is_rested": False,
        "connections": [],
        "encounters": [
            {
                "id": "enc_1",
                "name": "Encounter",
                "description": "",
                "difficulty": "easy",
                "cleared": False,
                "clear_reward": 0,
                "enemies": [],
            }
        ],
        "allowed_rests": ["short"],
    }

    room = Room.from_dict(payload)

    assert room.is_cleared is False
