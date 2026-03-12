from pathlib import Path

import pytest

from game.data.json_schema_validator import JsonSchemaValidationError, JsonSchemaValidator


def test_schema_validator_rejects_non_array_payload() -> None:
    schema_dir = Path(__file__).resolve().parents[2] / "data" / "schemata"
    validator = JsonSchemaValidator(schema_dir)

    with pytest.raises(JsonSchemaValidationError):
        validator.validate_named_dataset("attacks", {"not": "a list"})
