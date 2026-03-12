from game.core.action import create_action
from game.core.enums import ActionType
from game.actors.enemy import create_enemy
from game.catalog.models import Catalog, DungeonTemplate, EncounterTemplate, EnemyTemplate, RoomTemplate
from game.entity.blocks.archetype import Archetype, WeaponConstraints
from game.entity.blocks.race import Race
from game.entity.blocks.weapon import Weapon
from game.enums import (
    DifficultyType,
    GameState,
    RestType,
    WeaponDelivery,
    WeaponHandling,
    WeaponMagicType,
    WeaponProficiency,
    WeaponWeightClass,
)
from game.states.game_session import GameSession


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


def _catalog_with_template() -> Catalog:
    enemy = create_enemy(
        id="enemy_tpl_1",
        name="Enemy",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        enemy_instance_id="",
    )
    encounter_template = EncounterTemplate(
        id="enc_tpl_1",
        name="Encounter",
        description="",
        difficulty=DifficultyType.EASY,
        clear_reward=10,
        enemy_template_ids=("enemy_tpl_1",),
    )
    room_template = RoomTemplate(
        id="room_tpl_1",
        name="Start",
        description="",
        connections=(),
        encounters=(encounter_template,),
        allowed_rests=(RestType.SHORT,),
    )
    dungeon_template = DungeonTemplate(
        id="dungeon_tpl_1",
        name="Dungeon Template",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_tpl_1",
        end_room="room_tpl_1",
        rooms=(room_template,),
    )
    return Catalog(
        enemy_templates={"enemy_tpl_1": EnemyTemplate.from_enemy("enemy_tpl_1", enemy)},
        dungeon_templates={"dungeon_tpl_1": dungeon_template},
    )


def _session_in_encounter() -> GameSession:
    session = GameSession()
    session.catalog = _catalog_with_template()

    assert session.handle_action(
        create_action(
            ActionType.CREATE_PLAYER,
            parameters={
                "id": "player_1",
                "name": "Player",
                "description": "Recruit",
                "race": _race(),
                "archetype": _archetype(),
                "weapons": [_weapon()],
            },
            actor_instance_id="system",
        )
    ).ok

    assert session.handle_action(
        create_action(
            ActionType.CHOOSE_DUNGEON,
            parameters={"dungeon": "dungeon_tpl_1"},
            actor_instance_id="system",
        )
    ).ok

    assert session.handle_action(create_action(ActionType.START, actor_instance_id="system")).ok
    assert session.start_room_encounter().ok
    assert session.state is GameState.ENCOUNTER
    return session


def test_game_session_to_dict_from_dict_round_trip_restores_runtime_links() -> None:
    session = _session_in_encounter()
    payload = session.to_dict()

    restored = GameSession.from_dict(payload, catalog=session.catalog)

    assert restored.state is GameState.ENCOUNTER
    assert restored.catalog is session.catalog
    assert restored.points == session.points

    assert len(restored.party) == 1
    assert restored.party[0].player_instance_id == "player_1"

    assert restored.dungeon is not None
    assert restored.dungeon.template_id == "dungeon_tpl_1"

    assert restored.exploration.current_room is not None
    assert restored.exploration.current_room.id == "room_tpl_1"

    assert restored.encounter.current_encounter is not None
    assert restored.encounter.current_encounter.id == "enc_tpl_1"
    assert restored.encounter.current_encounter.enemies[0].template_id == "enemy_tpl_1"
