from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from core.data_engine.data_loader import DataLoader, load_game_data
from game.combat.status_effect import StatusEffect
from game.enums import StatusEffectType


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


def test_load_hydrated_emits_deprecation_warning() -> None:
    loader = DataLoader(data_dir=Path("data"), schema_dir=Path("data/schemata"))
    with pytest.deprecated_call(match="load_hydrated"):
        loader.load_hydrated()


def test_load_game_data_emits_deprecation_warning() -> None:
    with pytest.deprecated_call(match="load_game_data"):
        payload = load_game_data(data_dir=Path("data"), schema_dir=Path("data/schemata"))
    assert "dungeons" in payload
