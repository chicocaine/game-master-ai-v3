from core.action import create_action
from core.enums import ActionType
from game.actors.enemy import create_enemy
from game.catalog.models import Catalog, DungeonTemplate, EncounterTemplate, EnemyTemplate, RoomTemplate
from game.dungeons.dungeon import Dungeon, Encounter, Room
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


def _dungeon() -> Dungeon:
    room_1 = Room(
        id="room_1",
        name="Start",
        description="",
        is_visited=True,
        is_cleared=True,
        is_rested=False,
        connections=["room_2"],
        allowed_rests=[RestType.SHORT],
    )
    room_2 = Room(
        id="room_2",
        name="Hall",
        description="",
        is_visited=False,
        is_cleared=False,
        is_rested=False,
        connections=["room_1"],
        allowed_rests=[RestType.SHORT],
    )
    return Dungeon(
        id="dungeon_1",
        name="Dungeon",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_1",
        end_room="room_2",
        rooms=[room_1, room_2],
    )


def _encounter() -> Encounter:
    enemy = create_enemy(
        id="enemy_1",
        name="Enemy",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        enemy_instance_id="enemy_inst_1",
    )
    return Encounter(
        id="enc_1",
        name="Encounter",
        description="",
        difficulty=DifficultyType.EASY,
        cleared=False,
        clear_reward=10,
        enemies=[enemy],
    )


def _dungeon_with_encounter() -> Dungeon:
    room_1 = Room(
        id="room_1",
        name="Start",
        description="",
        is_visited=True,
        is_cleared=False,
        is_rested=False,
        connections=["room_2"],
        allowed_rests=[RestType.SHORT],
        encounters=[_encounter()],
    )
    room_2 = Room(
        id="room_2",
        name="Hall",
        description="",
        is_visited=False,
        is_cleared=True,
        is_rested=False,
        connections=["room_1"],
        allowed_rests=[RestType.SHORT],
    )
    return Dungeon(
        id="dungeon_2",
        name="Dungeon With Encounter",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_1",
        end_room="room_2",
        rooms=[room_1, room_2],
    )


def _session() -> GameSession:
    return GameSession()


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


def test_game_session_routes_pregame_actions() -> None:
    session = _session()

    create_player_action = create_action(
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
    result = session.handle_action(create_player_action)
    assert result.ok is True

    choose_dungeon_action = create_action(
        ActionType.CHOOSE_DUNGEON,
        parameters={"dungeon": _dungeon()},
        actor_instance_id="system",
    )
    result = session.handle_action(choose_dungeon_action)
    assert result.ok is True

    start_action = create_action(ActionType.START, actor_instance_id="system")
    result = session.handle_action(start_action)
    assert result.ok is True
    assert session.state is GameState.EXPLORATION
    event_types = [event["type"] for event in result.events]
    assert "action_submitted" in event_types
    assert "action_validated" in event_types
    assert "action_resolved" in event_types


def test_game_session_routes_exploration_actions() -> None:
    session = _session()

    setup_actions = [
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
        ),
        create_action(
            ActionType.CHOOSE_DUNGEON,
            parameters={"dungeon": _dungeon()},
            actor_instance_id="system",
        ),
        create_action(ActionType.START, actor_instance_id="system"),
    ]
    for action in setup_actions:
        assert session.handle_action(action).ok is True

    move_action = create_action(
        ActionType.MOVE,
        parameters={"destination_room_id": "room_2"},
        actor_instance_id="player_1",
    )
    result = session.handle_action(move_action)
    assert result.ok is True
    assert session.exploration.current_room.id == "room_2"

    attack_action = create_action(
        ActionType.ATTACK,
        parameters={"attack_id": "attack_1", "target_instance_ids": ["enemy_1"]},
        actor_instance_id="player_1",
    )
    result = session.handle_action(attack_action)
    assert result.errors and "Unsupported exploration action type" in result.errors[0]
    assert any(event["type"] == "action_rejected" for event in result.events)


def test_game_session_routes_encounter_actions() -> None:
    session = _session()

    setup_actions = [
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
        ),
        create_action(
            ActionType.CHOOSE_DUNGEON,
            parameters={"dungeon": _dungeon()},
            actor_instance_id="system",
        ),
        create_action(ActionType.START, actor_instance_id="system"),
    ]
    for action in setup_actions:
        assert session.handle_action(action).ok is True

    encounter = _encounter()
    assert session.start_encounter(encounter).ok is True

    attack_action = create_action(
        ActionType.ATTACK,
        parameters={"attack_id": "attack_1", "target_instance_ids": ["enemy_1"]},
        actor_instance_id="player_1",
    )
    result = session.handle_action(attack_action)
    assert result.errors and "is not known by actor" in result.errors[0]
    assert any(event["type"] == "action_rejected" for event in result.events)

    end_turn = create_action(ActionType.END_TURN, actor_instance_id="player_1")
    assert session.handle_action(end_turn).ok is True


def test_game_session_start_and_end_encounter_helpers_validate_state() -> None:
    session = _session()
    encounter = _encounter()

    result = session.start_encounter(encounter)
    assert result.errors and "only start while in exploration" in result.errors[0]

    setup_actions = [
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
        ),
        create_action(
            ActionType.CHOOSE_DUNGEON,
            parameters={"dungeon": _dungeon()},
            actor_instance_id="system",
        ),
        create_action(ActionType.START, actor_instance_id="system"),
    ]
    for action in setup_actions:
        assert session.handle_action(action).ok is True

    assert session.start_encounter(encounter).ok is True
    assert session.state is GameState.ENCOUNTER

    assert session.end_encounter().ok is True
    assert session.state is GameState.EXPLORATION
    assert session.points == 10

    end_result = session.start_encounter(_encounter())
    assert end_result.ok is True
    end_result = session.end_encounter()
    assert end_result.ok is True
    assert any(event["type"] == "reward_granted" for event in end_result.events)
    assert session.points == 20

    result = session.end_encounter()
    assert result.errors and "only end while in encounter" in result.errors[0]


def test_game_session_start_room_encounter_and_room_clear_sync() -> None:
    session = _session()

    setup_actions = [
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
        ),
        create_action(
            ActionType.CHOOSE_DUNGEON,
            parameters={"dungeon": _dungeon_with_encounter()},
            actor_instance_id="system",
        ),
        create_action(ActionType.START, actor_instance_id="system"),
    ]
    for action in setup_actions:
        assert session.handle_action(action).ok is True

    assert session.state is GameState.EXPLORATION
    assert session.exploration.current_room is not None
    assert session.exploration.current_room.is_cleared is False

    result = session.start_room_encounter()
    assert result.ok is True
    assert session.state is GameState.ENCOUNTER
    assert session.encounter.current_encounter is not None
    assert session.encounter.current_encounter.id == "enc_1"

    result = session.end_encounter()
    assert result.ok is True
    assert session.state is GameState.EXPLORATION
    assert session.exploration.current_room is not None
    assert session.exploration.current_room.is_cleared is True
    assert session.points == 10
    assert any(event["type"] == "reward_granted" for event in result.events)

    result = session.start_room_encounter()
    assert result.errors and "No uncleared encounters" in result.errors[0]


def test_game_session_transition_matrix_and_postgame_contract() -> None:
    session = _session()

    result = session.transition_to(GameState.ENCOUNTER)
    assert result.errors and "Invalid state transition" in result.errors[0]

    assert session.transition_to(GameState.POSTGAME).ok is True
    assert session.state is GameState.POSTGAME

    move_action = create_action(
        ActionType.MOVE,
        parameters={"destination_room_id": "room_2"},
        actor_instance_id="player_1",
    )
    result = session.handle_action(move_action)
    assert result.errors and "Unsupported postgame action type" in result.errors[0]
    assert any(event["type"] == "action_rejected" for event in result.events)

    finish_action = create_action(ActionType.FINISH, actor_instance_id="system")
    result = session.handle_action(finish_action)
    assert result.ok is True
    assert any(event["type"] == "game_finished" for event in result.events)
    assert any(event["type"] == "action_resolved" for event in result.events)
    assert result.state_changes["postgame"]["outcome"] == "abandoned"


def test_game_session_result_wrappers_capture_state_changes() -> None:
    session = _session()

    result = session.transition_to(GameState.POSTGAME)
    assert result.ok is True
    assert result.state_changes["state"]["from"] == "pregame"
    assert result.state_changes["state"]["to"] == "postgame"

    session = _session()
    create_player_action = create_action(
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
    assert session.handle_action(create_player_action).ok is True

    choose_dungeon_action = create_action(
        ActionType.CHOOSE_DUNGEON,
        parameters={"dungeon": _dungeon()},
        actor_instance_id="system",
    )
    assert session.handle_action(choose_dungeon_action).ok is True

    start_action = create_action(ActionType.START, actor_instance_id="system")
    result = session.handle_action(start_action)
    assert result.ok is True
    assert result.state_changes["state"]["from"] == "pregame"
    assert result.state_changes["state"]["to"] == "exploration"


def test_game_session_handles_converse_action() -> None:
    session = _session()

    result = session.handle_action(
        create_action(
            ActionType.CONVERSE,
            parameters={"message": "Can I inspect the room?"},
            actor_instance_id="player_1",
        )
    )
    assert result.ok is True
    event_types = [event["type"] for event in result.events]
    assert "action_submitted" in event_types
    assert "action_validated" in event_types
    assert "converse" in event_types
    assert "action_resolved" in event_types

    result = session.handle_action(
        create_action(
            ActionType.CONVERSE,
            parameters={"message": "   "},
            actor_instance_id="player_1",
        )
    )
    assert any("cannot be blank" in error for error in result.errors)
    assert any(event["type"] == "action_rejected" for event in result.events)


def test_game_session_action_lifecycle_event_payload_shape() -> None:
    session = _session()
    action = create_action(
        ActionType.CONVERSE,
        parameters={"message": "hello"},
        actor_instance_id="player_1",
    )

    result = session.handle_action(action)
    assert result.ok is True

    lifecycle_events = [
        event for event in result.events
        if event["type"] in {"action_submitted", "action_validated", "action_resolved"}
    ]
    assert len(lifecycle_events) == 3
    for event in lifecycle_events:
        assert event["action_id"] == action.action_id
        assert event["action_type"] == action.type.value
        assert event["actor_instance_id"] == "player_1"


def test_game_session_template_dungeon_path_materializes_runtime_instance_and_runs_encounter() -> None:
    session = _session()
    session.catalog = _catalog_with_template()
    session.available_dungeons = [session.catalog.dungeon_templates["dungeon_tpl_1"]]

    setup_actions = [
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
        ),
        create_action(
            ActionType.CHOOSE_DUNGEON,
            parameters={"dungeon_id": "dungeon_tpl_1"},
            actor_instance_id="system",
        ),
        create_action(ActionType.START, actor_instance_id="system"),
    ]
    for action in setup_actions:
        assert session.handle_action(action).ok is True

    assert session.dungeon is not None
    assert session.dungeon.id == "dungeon_tpl_1"
    assert session.exploration.current_room is not None
    assert session.exploration.current_room.id == "room_tpl_1"

    result = session.start_room_encounter()
    assert result.ok is True
    assert session.encounter.current_encounter is not None
    assert session.encounter.current_encounter.id == "enc_tpl_1"
    assert session.encounter.current_encounter.enemies[0].enemy_instance_id == "enemy_1"


def test_game_session_room_with_multiple_encounters_progresses_until_room_clear() -> None:
    session = _session()

    first_enemy = create_enemy(
        id="enemy_a",
        name="Enemy A",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        enemy_instance_id="enemy_inst_a",
    )
    second_enemy = create_enemy(
        id="enemy_b",
        name="Enemy B",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        enemy_instance_id="enemy_inst_b",
    )
    encounter_1 = Encounter(
        id="enc_1",
        name="Encounter One",
        description="",
        difficulty=DifficultyType.EASY,
        cleared=False,
        clear_reward=10,
        enemies=[first_enemy],
    )
    encounter_2 = Encounter(
        id="enc_2",
        name="Encounter Two",
        description="",
        difficulty=DifficultyType.EASY,
        cleared=False,
        clear_reward=20,
        enemies=[second_enemy],
    )
    dungeon = Dungeon(
        id="dungeon_multi_enc",
        name="Dungeon Multi Encounter",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_1",
        end_room="room_2",
        rooms=[
            Room(
                id="room_1",
                name="Start",
                description="",
                is_visited=True,
                is_cleared=False,
                is_rested=False,
                connections=["room_2"],
                allowed_rests=[RestType.SHORT],
                encounters=[encounter_1, encounter_2],
            ),
            Room(
                id="room_2",
                name="End",
                description="",
                is_visited=False,
                is_cleared=True,
                is_rested=False,
                connections=["room_1"],
                allowed_rests=[RestType.SHORT],
            ),
        ],
    )

    setup_actions = [
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
        ),
        create_action(
            ActionType.CHOOSE_DUNGEON,
            parameters={"dungeon": dungeon},
            actor_instance_id="system",
        ),
        create_action(ActionType.START, actor_instance_id="system"),
    ]
    for action in setup_actions:
        assert session.handle_action(action).ok is True

    result = session.start_room_encounter()
    assert result.ok is True
    assert session.encounter.current_encounter is not None
    assert session.encounter.current_encounter.id == "enc_1"

    result = session.end_encounter()
    assert result.ok is True
    assert encounter_1.cleared is True
    assert encounter_2.cleared is False
    assert session.exploration.current_room is not None
    assert session.exploration.current_room.is_cleared is False

    result = session.start_room_encounter()
    assert result.ok is True
    assert session.encounter.current_encounter is not None
    assert session.encounter.current_encounter.id == "enc_2"

    result = session.end_encounter()
    assert result.ok is True
    assert encounter_2.cleared is True
    assert session.exploration.current_room is not None
    assert session.exploration.current_room.is_cleared is True
    assert session.points == 30

    result = session.start_room_encounter()
    assert result.errors and "No uncleared encounters" in result.errors[0]


def test_game_session_reused_enemy_id_across_encounters_can_leak_enemy_state() -> None:
    session = _session()

    shared_enemy = create_enemy(
        id="enemy_shared",
        name="Enemy Shared",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        enemy_instance_id="enemy_inst_shared",
    )
    encounter_1 = Encounter(
        id="enc_1",
        name="Encounter One",
        description="",
        difficulty=DifficultyType.EASY,
        cleared=False,
        clear_reward=10,
        enemies=[shared_enemy],
    )
    encounter_2 = Encounter(
        id="enc_2",
        name="Encounter Two",
        description="",
        difficulty=DifficultyType.EASY,
        cleared=False,
        clear_reward=10,
        enemies=[shared_enemy],
    )
    dungeon = Dungeon(
        id="dungeon_shared_enemy",
        name="Dungeon Shared Enemy",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_1",
        end_room="room_2",
        rooms=[
            Room(
                id="room_1",
                name="Start",
                description="",
                is_visited=True,
                is_cleared=False,
                is_rested=False,
                connections=["room_2"],
                allowed_rests=[RestType.SHORT],
                encounters=[encounter_1, encounter_2],
            ),
            Room(
                id="room_2",
                name="End",
                description="",
                is_visited=False,
                is_cleared=True,
                is_rested=False,
                connections=["room_1"],
                allowed_rests=[RestType.SHORT],
            ),
        ],
    )

    setup_actions = [
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
        ),
        create_action(
            ActionType.CHOOSE_DUNGEON,
            parameters={"dungeon": dungeon},
            actor_instance_id="system",
        ),
        create_action(ActionType.START, actor_instance_id="system"),
    ]
    for action in setup_actions:
        assert session.handle_action(action).ok is True

    assert session.start_room_encounter().ok is True
    assert session.encounter.current_encounter is encounter_1
    shared_enemy.hp = 0
    assert session.end_encounter().ok is True

    assert session.start_room_encounter().ok is True
    assert session.encounter.current_encounter is encounter_2
    assert encounter_2.enemies[0].id == "enemy_shared"
    assert encounter_2.enemies[0].hp == 0


def test_game_session_single_encounter_allows_duplicate_enemy_ids_with_unique_instances() -> None:
    session = _session()

    duplicate_enemy_1 = create_enemy(
        id="enemy_dup",
        name="Enemy Duplicate A",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        enemy_instance_id="enemy_inst_1",
    )
    duplicate_enemy_2 = create_enemy(
        id="enemy_dup",
        name="Enemy Duplicate B",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        enemy_instance_id="enemy_inst_2",
    )
    encounter = Encounter(
        id="enc_dup",
        name="Duplicate Enemy Encounter",
        description="",
        difficulty=DifficultyType.EASY,
        cleared=False,
        clear_reward=10,
        enemies=[duplicate_enemy_1, duplicate_enemy_2],
    )

    setup_actions = [
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
        ),
        create_action(
            ActionType.CHOOSE_DUNGEON,
            parameters={"dungeon": _dungeon()},
            actor_instance_id="system",
        ),
        create_action(ActionType.START, actor_instance_id="system"),
    ]
    for action in setup_actions:
        assert session.handle_action(action).ok is True

    result = session.start_encounter(encounter)
    assert result.ok is True
    assert session.encounter.current_encounter is not None
    encounter_enemies = session.encounter.current_encounter.enemies
    assert len(encounter_enemies) == 2
    assert [enemy.id for enemy in encounter_enemies] == ["enemy_dup", "enemy_dup"]

    assigned_instance_ids = [enemy.enemy_instance_id for enemy in encounter_enemies]
    assert assigned_instance_ids == ["enemy_1", "enemy_2"]
    assert len(set(assigned_instance_ids)) == 2
