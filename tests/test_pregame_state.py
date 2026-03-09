from types import SimpleNamespace

from core.action import create_action
from core.enums import ActionType
from game.dungeons.dungeon import Dungeon, Room
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
from game.states.pregame import MAX_PARTY_SIZE, PreGameState


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
    room = Room(
        id="room_1",
        name="Start",
        description="",
        is_visited=False,
        is_cleared=False,
        is_rested=False,
    )
    return Dungeon(
        id="dungeon_1",
        name="Dungeon",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="room_1",
        end_room="room_1",
        rooms=[room],
    )


def _session() -> SimpleNamespace:
    return SimpleNamespace(
        party=[],
        dungeon=None,
        available_dungeons=[],
        exploration=SimpleNamespace(current_room=None),
        state=GameState.PREGAME,
    )


def test_handle_create_player_enforces_max_party_size() -> None:
    pregame = PreGameState()
    session = _session()

    for index in range(MAX_PARTY_SIZE):
        result = pregame.handle_create_player(
            session,
            id=f"player_{index + 1}",
            name=f"Player {index + 1}",
            description="",
            race=_race(),
            archetype=_archetype(),
            weapons=[_weapon()],
        )
        assert result.ok is True

    result = pregame.handle_create_player(
        session,
        id="player_overflow",
        name="Overflow",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )
    assert result.errors and "Party is full" in result.errors[0]


def test_handle_remove_and_edit_player_by_instance_id() -> None:
    pregame = PreGameState()
    session = _session()

    result = pregame.handle_create_player(
        session,
        id="old_id",
        name="Old Name",
        description="old",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )
    assert result.ok is True
    player_instance_id = session.party[0].player_instance_id

    result = pregame.handle_edit_player(
        session,
        player_instance_id=player_instance_id,
        id="new_id",
        name="New Name",
        description="new",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )
    assert result.ok is True

    assert session.party[0].id == "new_id"
    assert session.party[0].name == "New Name"
    assert session.party[0].player_instance_id == player_instance_id

    result = pregame.handle_remove_player(session, player_instance_id)
    assert result.ok is True
    assert session.party == []

    result = pregame.handle_remove_player(session, player_instance_id)
    assert result.errors and "was not found" in result.errors[0]


def test_handle_choose_dungeon_validates_shape() -> None:
    pregame = PreGameState()
    session = _session()

    result = pregame.handle_choose_dungeon(session, None)
    assert result.errors and "cannot be None" in result.errors[0]

    invalid = Dungeon(
        id="bad",
        name="Bad",
        description="",
        difficulty=DifficultyType.EASY,
        start_room="missing",
        end_room="missing",
        rooms=[],
    )
    result = pregame.handle_choose_dungeon(session, invalid)
    assert result.errors and "at least one room" in result.errors[0]

    dungeon = _dungeon()
    result = pregame.handle_choose_dungeon(session, dungeon)
    assert result.ok is True
    assert session.dungeon is dungeon


def test_handle_start_moves_session_to_exploration() -> None:
    pregame = PreGameState()
    session = _session()

    result = pregame.handle_start(session)
    assert any("without at least one player" in error for error in result.errors)
    assert any("without selecting a dungeon" in error for error in result.errors)

    result = pregame.handle_create_player(
        session,
        id="player_1",
        name="Player",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )
    assert result.ok is True

    result = pregame.handle_start(session)
    assert result.errors and "without selecting a dungeon" in result.errors[0]

    dungeon = _dungeon()
    result = pregame.handle_choose_dungeon(session, dungeon)
    assert result.ok is True

    result = pregame.handle_start(session)
    assert result.ok is True

    assert pregame.started is True
    assert session.state is GameState.EXPLORATION
    assert session.exploration.current_room.id == dungeon.start_room


def test_handle_action_routes_pregame_actions() -> None:
    pregame = PreGameState()
    session = _session()

    create_player_action = create_action(
        ActionType.CREATE_PLAYER,
        parameters={
            "id": "player_1",
            "name": "Player",
            "description": "New recruit",
            "race": _race(),
            "archetype": _archetype(),
            "weapons": [_weapon()],
        },
        actor_instance_id="system",
    )
    result = pregame.handle_action(session, create_player_action)
    assert result.ok is True
    assert len(session.party) == 1

    choose_dungeon_action = create_action(
        ActionType.CHOOSE_DUNGEON,
        parameters={"dungeon": _dungeon()},
        actor_instance_id="system",
    )
    result = pregame.handle_action(session, choose_dungeon_action)
    assert result.ok is True

    start_action = create_action(ActionType.START, parameters={}, actor_instance_id="system")
    result = pregame.handle_action(session, start_action)
    assert result.ok is True
    assert session.state is GameState.EXPLORATION


def test_handle_action_choose_dungeon_by_id() -> None:
    pregame = PreGameState()
    session = _session()
    dungeon = _dungeon()
    session.available_dungeons = [dungeon]

    action = create_action(
        ActionType.CHOOSE_DUNGEON,
        parameters={"dungeon_id": "dungeon_1"},
        actor_instance_id="system",
    )
    result = pregame.handle_action(session, action)
    assert result.ok is True
    assert session.dungeon is dungeon

    bad_action = create_action(
        ActionType.CHOOSE_DUNGEON,
        parameters={"dungeon_id": "missing_dungeon"},
        actor_instance_id="system",
    )
    result = pregame.handle_action(session, bad_action)
    assert result.errors and "was not found" in result.errors[0]
