from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from core.data_engine.data_loader import DataLoader, load_game_data
from game.combat.attack import Attack
from game.combat.spell import Spell
from game.combat.status_effect import StatusEffect
from game.entity.blocks.archetype import Archetype, WeaponConstraints
from game.entity.blocks.race import Race
from game.entity.blocks.weapon import Weapon
from game.enums import StatusEffectType
from game.enums import (
    AttackType,
    DamageType,
    SpellType,
    WeaponDelivery,
    WeaponHandling,
    WeaponMagicType,
    WeaponProficiency,
    WeaponWeightClass,
)


def test_status_effect_is_frozen_definition() -> None:
    effect = StatusEffect(
        id="se_1",
        name="Stun",
        description="",
        type=StatusEffectType.CONTROL,
        parameters={"control_type": "stunned"},
    )

    with pytest.raises(FrozenInstanceError):
        effect.name = "Renamed"

    with pytest.raises(TypeError):
        effect.parameters["control_type"] = "asleep"


def test_attack_and_spell_are_frozen_and_parameters_are_immutable() -> None:
    attack = Attack(
        id="atk_1",
        name="Strike",
        description="",
        type=AttackType.MELEE,
        parameters={"damage_roll": "1d6+0", "damage_types": [DamageType.SLASHING.value]},
    )
    spell = Spell(
        id="spl_1",
        name="Spark",
        description="",
        type=SpellType.ATTACK,
        spell_cost=1,
        parameters={"damage_roll": "1d4+0", "damage_types": [DamageType.FIRE.value]},
    )

    with pytest.raises(FrozenInstanceError):
        attack.name = "Renamed"
    with pytest.raises(FrozenInstanceError):
        spell.name = "Renamed"

    with pytest.raises(TypeError):
        attack.parameters["damage_roll"] = "9d9+9"
    with pytest.raises(TypeError):
        spell.parameters["damage_roll"] = "9d9+9"


def test_race_archetype_weapon_are_frozen_and_normalize_to_tuples() -> None:
    attack = Attack(id="atk_1", name="Strike", description="", type=AttackType.MELEE, parameters={})
    spell = Spell(id="spl_1", name="Spark", description="", type=SpellType.ATTACK, spell_cost=1, parameters={})
    weapon = Weapon(
        id="wpn_1",
        name="Blade",
        description="",
        proficiency=WeaponProficiency.SIMPLE,
        handling=WeaponHandling.ONE_HANDED,
        weight_class=WeaponWeightClass.LIGHT,
        delivery=WeaponDelivery.MELEE,
        magic_type=WeaponMagicType.MUNDANE,
        known_attacks=[attack],
        known_spells=[spell],
    )
    race = Race(
        id="race_1",
        name="Race",
        description="",
        base_hp=10,
        base_AC=10,
        base_spell_slots=2,
        resistances=[DamageType.FIRE],
        known_attacks=[attack],
        known_spells=[spell],
    )
    archetype = Archetype(
        id="arch_1",
        name="Archetype",
        description="",
        hp_mod=1,
        AC_mod=1,
        spell_slot_mod=1,
        initiative_mod=0,
        weapon_constraints=WeaponConstraints(
            proficiency=[WeaponProficiency.SIMPLE],
            handling=[WeaponHandling.ONE_HANDED],
        ),
        known_attacks=[attack],
        known_spells=[spell],
    )

    assert isinstance(weapon.known_attacks, tuple)
    assert isinstance(weapon.known_spells, tuple)
    assert isinstance(race.resistances, tuple)
    assert isinstance(race.known_attacks, tuple)
    assert isinstance(archetype.weapon_constraints.proficiency, tuple)
    assert isinstance(archetype.known_spells, tuple)

    with pytest.raises(FrozenInstanceError):
        weapon.name = "Renamed"
    with pytest.raises(FrozenInstanceError):
        race.name = "Renamed"
    with pytest.raises(FrozenInstanceError):
        archetype.name = "Renamed"


def test_load_hydrated_emits_deprecation_warning() -> None:
    loader = DataLoader(data_dir=Path("data"), schema_dir=Path("data/schemata"))
    with pytest.deprecated_call(match="load_hydrated"):
        loader.load_hydrated()


def test_load_game_data_emits_deprecation_warning() -> None:
    with pytest.deprecated_call(match="load_game_data"):
        payload = load_game_data(data_dir=Path("data"), schema_dir=Path("data/schemata"))
    assert "dungeons" in payload
