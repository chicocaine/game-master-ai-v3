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

    finish_action = create_action(ActionType.FINISH, actor_instance_id="system")
    result = session.handle_action(finish_action)
    assert result.errors and "not implemented yet" in result.errors[0]


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
    assert result.events and result.events[0]["type"] == "converse"

    result = session.handle_action(
        create_action(
            ActionType.CONVERSE,
            parameters={"message": "   "},
            actor_instance_id="player_1",
        )
    )
    assert any("cannot be blank" in error for error in result.errors)
