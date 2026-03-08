from types import SimpleNamespace

from core.action import create_action
from core.enums import ActionType
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
    errors = pregame.handle_create_player(
        session,
        id="player_1",
        name="Player",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )
    assert errors == []
    return session


def test_handle_move_requires_cleared_and_connected_room() -> None:
    dungeon = _dungeon()
    session = _session_with_player_and_dungeon(dungeon)

    errors = session.exploration.handle_move(session, "missing")
    assert errors and "not connected" in errors[0]

    errors = session.exploration.handle_move(session, "room_2")
    assert errors == []
    assert session.exploration.current_room.id == "room_2"
    assert session.exploration.current_room.is_visited is True

    errors = session.exploration.handle_move(session, "room_1")
    assert errors and "not cleared" in errors[0]


def test_handle_rest_applies_and_blocks_second_rest() -> None:
    dungeon = _dungeon()
    session = _session_with_player_and_dungeon(dungeon)
    player = session.party[0]
    player.hp = 1
    player.spell_slots = 0

    errors = session.exploration.handle_rest(session, RestType.SHORT)
    assert errors == []
    assert player.hp > 1
    assert player.spell_slots > 0

    errors = session.exploration.handle_rest(session, RestType.SHORT)
    assert errors and "already been rested" in errors[0]


def test_handle_rest_rejects_disallowed_rest_type() -> None:
    dungeon = _dungeon()
    session = _session_with_player_and_dungeon(dungeon)

    errors = session.exploration.handle_move(session, "room_2")
    assert errors == []

    errors = session.exploration.handle_rest(session, RestType.LONG)
    assert errors and "not allowed" in errors[0]


def test_handle_action_routes_move_and_rest() -> None:
    dungeon = _dungeon()
    session = _session_with_player_and_dungeon(dungeon)

    move_action = create_action(
        ActionType.MOVE,
        parameters={"destination_room_id": "room_2"},
        actor_instance_id="player_1",
    )
    errors = session.exploration.handle_action(session, move_action)
    assert errors == []
    assert session.exploration.current_room.id == "room_2"

    rest_action = create_action(
        ActionType.REST,
        parameters={"rest_type": "long"},
        actor_instance_id="player_1",
    )
    errors = session.exploration.handle_action(session, rest_action)
    assert errors and "not allowed" in errors[0]


def test_handle_action_rejects_invalid_rest_type() -> None:
    dungeon = _dungeon()
    session = _session_with_player_and_dungeon(dungeon)

    action = create_action(
        ActionType.REST,
        parameters={"rest_type": "nap"},
        actor_instance_id="player_1",
    )
    errors = session.exploration.handle_action(session, action)
    assert errors and "Invalid rest type" in errors[0]
