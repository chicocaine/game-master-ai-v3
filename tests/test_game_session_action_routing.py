from core.action import create_action
from core.enums import ActionType
from game.actors.enemy import create_enemy
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
    errors = session.handle_action(create_player_action)
    assert errors == []

    choose_dungeon_action = create_action(
        ActionType.CHOOSE_DUNGEON,
        parameters={"dungeon": _dungeon()},
        actor_instance_id="system",
    )
    errors = session.handle_action(choose_dungeon_action)
    assert errors == []

    start_action = create_action(ActionType.START, actor_instance_id="system")
    errors = session.handle_action(start_action)
    assert errors == []
    assert session.state is GameState.EXPLORATION


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
        assert session.handle_action(action) == []

    move_action = create_action(
        ActionType.MOVE,
        parameters={"destination_room_id": "room_2"},
        actor_instance_id="player_1",
    )
    errors = session.handle_action(move_action)
    assert errors == []
    assert session.exploration.current_room.id == "room_2"

    attack_action = create_action(
        ActionType.ATTACK,
        parameters={"attack_id": "attack_1", "target_instance_ids": ["enemy_inst_1"]},
        actor_instance_id="player_1",
    )
    errors = session.handle_action(attack_action)
    assert errors and "Unsupported exploration action type" in errors[0]


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
        assert session.handle_action(action) == []

    encounter = _encounter()
    assert session.start_encounter(encounter) == []

    attack_action = create_action(
        ActionType.ATTACK,
        parameters={"attack_id": "attack_1", "target_instance_ids": ["enemy_inst_1"]},
        actor_instance_id="player_1",
    )
    errors = session.handle_action(attack_action)
    assert errors and "not implemented yet" in errors[0]

    end_turn = create_action(ActionType.END_TURN, actor_instance_id="player_1")
    assert session.handle_action(end_turn) == []


def test_game_session_start_and_end_encounter_helpers_validate_state() -> None:
    session = _session()
    encounter = _encounter()

    errors = session.start_encounter(encounter)
    assert errors and "only start while in exploration" in errors[0]

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
        assert session.handle_action(action) == []

    assert session.start_encounter(encounter) == []
    assert session.state is GameState.ENCOUNTER

    assert session.end_encounter() == []
    assert session.state is GameState.EXPLORATION

    errors = session.end_encounter()
    assert errors and "only end while in encounter" in errors[0]


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
        assert session.handle_action(action) == []

    assert session.state is GameState.EXPLORATION
    assert session.exploration.current_room is not None
    assert session.exploration.current_room.is_cleared is False

    errors = session.start_room_encounter()
    assert errors == []
    assert session.state is GameState.ENCOUNTER
    assert session.encounter.current_encounter is not None
    assert session.encounter.current_encounter.id == "enc_1"

    errors = session.end_encounter()
    assert errors == []
    assert session.state is GameState.EXPLORATION
    assert session.exploration.current_room is not None
    assert session.exploration.current_room.is_cleared is True

    errors = session.start_room_encounter()
    assert errors and "No uncleared encounters" in errors[0]


def test_game_session_transition_matrix_and_postgame_contract() -> None:
    session = _session()

    errors = session.transition_to(GameState.ENCOUNTER)
    assert errors and "Invalid state transition" in errors[0]

    assert session.transition_to(GameState.POSTGAME) == []
    assert session.state is GameState.POSTGAME

    move_action = create_action(
        ActionType.MOVE,
        parameters={"destination_room_id": "room_2"},
        actor_instance_id="player_1",
    )
    errors = session.handle_action(move_action)
    assert errors and "Unsupported postgame action type" in errors[0]

    finish_action = create_action(ActionType.FINISH, actor_instance_id="system")
    errors = session.handle_action(finish_action)
    assert errors and "not implemented yet" in errors[0]
