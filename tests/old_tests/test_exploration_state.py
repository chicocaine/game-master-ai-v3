from types import SimpleNamespace

from game.core.action import create_action
from game.core.enums import ActionType
from game.dungeons.dungeon import Dungeon, Room
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
from game.states.exploration import ExplorationState
from game.states.pregame import PreGameState


def _race() -> Race:
    return Race(
        id="race_1",
        name="Race",
        description="",
        base_hp=10,
        base_AC=10,
        base_spell_slots=4,
    )


def _archetype() -> Archetype:
    return Archetype(
        id="arch_1",
        name="Archetype",
        description="",
        hp_mod=2,
        AC_mod=1,
        spell_slot_mod=2,
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
        allowed_rests=[RestType.SHORT, RestType.LONG],
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


def _session_with_player_and_dungeon(dungeon: Dungeon) -> SimpleNamespace:
    session = SimpleNamespace(
        party=[],
        dungeon=dungeon,
        exploration=ExplorationState(current_room=dungeon.rooms[0]),
    )
    pregame = PreGameState()
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
    return session


def test_handle_move_requires_cleared_and_connected_room() -> None:
    dungeon = _dungeon()
    session = _session_with_player_and_dungeon(dungeon)

    result = session.exploration.handle_move(session, "missing")
    assert result.errors and "not connected" in result.errors[0]

    result = session.exploration.handle_move(session, "room_2")
    assert result.ok is True
    assert session.exploration.current_room.id == "room_2"
    assert session.exploration.current_room.is_visited is True

    result = session.exploration.handle_move(session, "room_1")
    assert result.errors and "not cleared" in result.errors[0]


def test_handle_rest_applies_and_blocks_second_rest() -> None:
    dungeon = _dungeon()
    session = _session_with_player_and_dungeon(dungeon)
    player = session.party[0]
    player.hp = 1
    player.spell_slots = 0

    result = session.exploration.handle_rest(session, RestType.SHORT)
    assert result.ok is True
    assert player.hp > 1
    assert player.spell_slots > 0

    result = session.exploration.handle_rest(session, RestType.SHORT)
    assert result.errors and "already been rested" in result.errors[0]


def test_handle_rest_rejects_disallowed_rest_type() -> None:
    dungeon = _dungeon()
    session = _session_with_player_and_dungeon(dungeon)

    result = session.exploration.handle_move(session, "room_2")
    assert result.ok is True

    result = session.exploration.handle_rest(session, RestType.LONG)
    assert result.errors and "not allowed" in result.errors[0]


def test_handle_action_routes_move_and_rest() -> None:
    dungeon = _dungeon()
    session = _session_with_player_and_dungeon(dungeon)

    move_action = create_action(
        ActionType.MOVE,
        parameters={"destination_room_id": "room_2"},
        actor_instance_id="player_1",
    )
    result = session.exploration.handle_action(session, move_action)
    assert result.ok is True
    assert session.exploration.current_room.id == "room_2"

    rest_action = create_action(
        ActionType.REST,
        parameters={"rest_type": "long"},
        actor_instance_id="player_1",
    )
    result = session.exploration.handle_action(session, rest_action)
    assert result.errors and "not allowed" in result.errors[0]




def test_can_rest_false_when_room_missing_allowed_rests() -> None:
    state = ExplorationState(current_room=None)
    assert state.can_rest is False

    state.current_room = SimpleNamespace(allowed_rests=None, is_rested=False)
    assert state.can_rest is False


def test_exploration_state_round_trip_preserves_current_room_id() -> None:
    state = ExplorationState(current_room=None, current_room_id="room_9")
    restored = ExplorationState.from_dict(state.to_dict())

    assert restored.current_room is None
    assert restored.current_room_id == "room_9"
