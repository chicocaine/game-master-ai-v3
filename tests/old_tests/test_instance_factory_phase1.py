from game.actors.enemy import create_enemy
from game.catalog.models import Catalog, DungeonTemplate, EncounterTemplate, EnemyTemplate, RoomTemplate
from game.entity.blocks.archetype import Archetype, WeaponConstraints
from game.entity.blocks.race import Race
from game.entity.blocks.weapon import Weapon
from game.enums import (
    DifficultyType,
    RestType,
    WeaponDelivery,
    WeaponHandling,
    WeaponMagicType,
    WeaponProficiency,
    WeaponWeightClass,
)
from game.factories.instance_factory import InstanceFactory, SimpleInstanceIdGenerator


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


def _enemy_template(template_id: str) -> EnemyTemplate:
    enemy = create_enemy(
        id=template_id,
        name=f"Enemy {template_id}",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )
    return EnemyTemplate.from_enemy(template_id, enemy)


def test_phase1_factory_generates_simple_instance_ids() -> None:
    enemy_template = _enemy_template("enemy_goblin")
    encounter_1 = EncounterTemplate(
        id="enc_1",
        name="Encounter One",
        description="",
        difficulty=DifficultyType.EASY,
        clear_reward=10,
        enemy_template_ids=("enemy_goblin",),
    )
    encounter_2 = EncounterTemplate(
        id="enc_2",
        name="Encounter Two",
        description="",
        difficulty=DifficultyType.EASY,
        clear_reward=10,
        enemy_template_ids=("enemy_goblin",),
    )
    room_template = RoomTemplate(
        id="room_1",
        name="Room",
        description="",
        connections=("room_2",),
        encounters=(encounter_1, encounter_2),
        allowed_rests=(RestType.SHORT,),
    )
    dungeon_template = DungeonTemplate(
        id="dng_1",
        name="Dungeon",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_1",
        end_room="room_1",
        rooms=(room_template,),
    )
    catalog = Catalog(
        enemy_templates={"enemy_goblin": enemy_template},
        dungeon_templates={"dng_1": dungeon_template},
    )

    instance = InstanceFactory.dungeon_from_template(
        dungeon_template,
        catalog,
        id_gen=SimpleInstanceIdGenerator(),
    )

    assert instance.instance_id == "dungeon_1"
    assert instance.rooms[0].instance_id == "room_1"
    assert instance.rooms[0].encounters[0].instance_id == "encounter_1"
    assert instance.rooms[0].encounters[1].instance_id == "encounter_2"
    assert instance.rooms[0].encounters[0].enemies[0].instance_id == "enemy_1"
    assert instance.rooms[0].encounters[1].enemies[0].instance_id == "enemy_2"


def test_phase1_factory_same_enemy_template_id_creates_distinct_enemy_instances() -> None:
    enemy_template = _enemy_template("enemy_shared")
    encounter_1 = EncounterTemplate(
        id="enc_1",
        name="Encounter One",
        description="",
        difficulty=DifficultyType.EASY,
        clear_reward=10,
        enemy_template_ids=("enemy_shared",),
    )
    encounter_2 = EncounterTemplate(
        id="enc_2",
        name="Encounter Two",
        description="",
        difficulty=DifficultyType.EASY,
        clear_reward=10,
        enemy_template_ids=("enemy_shared",),
    )
    room_template = RoomTemplate(
        id="room_1",
        name="Room",
        description="",
        connections=(),
        encounters=(encounter_1, encounter_2),
        allowed_rests=(),
    )
    dungeon_template = DungeonTemplate(
        id="dng_1",
        name="Dungeon",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_1",
        end_room="room_1",
        rooms=(room_template,),
    )
    catalog = Catalog(
        enemy_templates={"enemy_shared": enemy_template},
        dungeon_templates={"dng_1": dungeon_template},
    )

    instance = InstanceFactory.dungeon_from_template(dungeon_template, catalog)
    enemy_a = instance.rooms[0].encounters[0].enemies[0]
    enemy_b = instance.rooms[0].encounters[1].enemies[0]

    enemy_a.hp = 1

    assert enemy_a.template_id == "enemy_shared"
    assert enemy_b.template_id == "enemy_shared"
    assert enemy_a is not enemy_b
    assert enemy_b.hp != enemy_a.hp


def test_phase1_factory_duplicate_enemy_template_id_in_one_encounter_isolated_by_instance() -> None:
    enemy_template = _enemy_template("enemy_dupe")
    encounter = EncounterTemplate(
        id="enc_1",
        name="Encounter",
        description="",
        difficulty=DifficultyType.EASY,
        clear_reward=10,
        enemy_template_ids=("enemy_dupe", "enemy_dupe"),
    )
    room_template = RoomTemplate(
        id="room_1",
        name="Room",
        description="",
        connections=(),
        encounters=(encounter,),
        allowed_rests=(),
    )
    dungeon_template = DungeonTemplate(
        id="dng_1",
        name="Dungeon",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_1",
        end_room="room_1",
        rooms=(room_template,),
    )
    catalog = Catalog(
        enemy_templates={"enemy_dupe": enemy_template},
        dungeon_templates={"dng_1": dungeon_template},
    )

    instance = InstanceFactory.dungeon_from_template(dungeon_template, catalog)
    enemies = instance.rooms[0].encounters[0].enemies

    assert len(enemies) == 2
    assert enemies[0].template_id == "enemy_dupe"
    assert enemies[1].template_id == "enemy_dupe"
    assert enemies[0] is not enemies[1]
    assert enemies[0].instance_id == "enemy_1"
    assert enemies[1].instance_id == "enemy_2"
