from game.actors.enemy import create_enemy
from game.actors.player import create_player
from game.catalog.models import Catalog, DungeonTemplate, EncounterTemplate, EnemyTemplate, RoomTemplate
from game.entity.blocks.archetype import Archetype, WeaponConstraints
from game.entity.blocks.race import Race
from game.entity.blocks.weapon import Weapon
from game.enums import (
    DifficultyType,
    GameState,
    WeaponDelivery,
    WeaponHandling,
    WeaponMagicType,
    WeaponProficiency,
    WeaponWeightClass,
)
from game.factories.game_factory import GameFactory


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


def _catalog() -> Catalog:
    enemy = create_enemy(
        id="enemy_tpl_1",
        name="Enemy",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        enemy_instance_id="",
    )
    encounter_1 = EncounterTemplate(
        id="enc_tpl_1",
        name="Encounter 1",
        description="",
        difficulty=DifficultyType.EASY,
        clear_reward=10,
        enemy_template_ids=("enemy_tpl_1",),
    )
    encounter_2 = EncounterTemplate(
        id="enc_tpl_2",
        name="Encounter 2",
        description="",
        difficulty=DifficultyType.EASY,
        clear_reward=10,
        enemy_template_ids=("enemy_tpl_1",),
    )
    room = RoomTemplate(
        id="room_tpl_1",
        name="Room",
        description="",
        connections=(),
        encounters=(encounter_1, encounter_2),
        allowed_rests=(),
    )
    dungeon = DungeonTemplate(
        id="dungeon_tpl_1",
        name="Dungeon",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_tpl_1",
        end_room="room_tpl_1",
        rooms=(room,),
    )
    return Catalog(
        enemy_templates={"enemy_tpl_1": EnemyTemplate(id="enemy_tpl_1", enemy=enemy)},
        dungeon_templates={"dungeon_tpl_1": dungeon},
    )


def test_game_factory_create_session_sets_catalog_and_templates() -> None:
    catalog = _catalog()
    session = GameFactory.create_session(catalog)

    assert session.catalog is catalog
    assert len(session.available_dungeons) == 1
    assert session.available_dungeons[0].id == "dungeon_tpl_1"
    assert session.state is GameState.PREGAME


def test_game_factory_create_session_with_selected_dungeon_instantiates_runtime_dungeon() -> None:
    catalog = _catalog()
    player = create_player(
        id="player_1",
        name="Player",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        player_instance_id="",
    )

    session = GameFactory.create_session(
        catalog,
        selected_dungeon_id="dungeon_tpl_1",
        party=[player],
        seed=42,
    )

    assert session.dungeon is not None
    assert session.dungeon.id == "dungeon_tpl_1"
    assert session.state is GameState.EXPLORATION
    assert session.exploration.current_room is not None
    assert session.exploration.current_room.id == "room_tpl_1"
    assert session.party[0].player_instance_id == "player_1"


def test_game_factory_create_session_runtime_enemies_do_not_leak_between_encounters() -> None:
    catalog = _catalog()
    player = create_player(
        id="player_1",
        name="Player",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        player_instance_id="",
    )

    session = GameFactory.create_session(
        catalog,
        selected_dungeon_id="dungeon_tpl_1",
        party=[player],
    )
    room = session.dungeon.rooms[0]
    enemy_a = room.encounters[0].enemies[0]
    enemy_b = room.encounters[1].enemies[0]

    before_b = enemy_b.hp
    enemy_a.hp = max(0, enemy_a.hp - 2)

    assert enemy_a is not enemy_b
    assert enemy_a.enemy_instance_id == "enemy_1"
    assert enemy_b.enemy_instance_id == "enemy_2"
    assert enemy_b.hp == before_b


def test_game_factory_assigns_sequential_player_instance_ids_for_unassigned_players() -> None:
    catalog = _catalog()
    player_a = create_player(
        id="player_a",
        name="Player A",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )
    player_b = create_player(
        id="player_b",
        name="Player B",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )

    session = GameFactory.create_session(catalog, party=[player_a, player_b])

    assert [player.player_instance_id for player in session.party] == ["player_1", "player_2"]
