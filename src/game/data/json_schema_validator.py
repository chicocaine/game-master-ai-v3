from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
	from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # pragma: no cover - environment dependent
	Draft202012Validator = None


DEFAULT_SCHEMA_MAP: Dict[str, str] = {
	"status_effects": "status_effect.schema.json",
	"attacks": "attack.schema.json",
	"spells": "spell.schema.json",
	"weapons": "weapon.schema.json",
	"races": "race.schema.json",
	"archetypes": "archetype.schema.json",
	"players": "player.schema.json",
	"enemies": "enemy.schema.json",
	"dungeons": "dungeon.schema.json",
}


class JsonSchemaValidationError(ValueError):
	"""Raised when one or more JSON schema validation errors are found."""


class JsonSchemaValidator:
	"""Validate game data files against their JSON Schemas."""

	def __init__(
		self,
		schema_dir: Path | str,
		schema_map: Optional[Dict[str, str]] = None,
	) -> None:
		self.schema_dir = Path(schema_dir)
		self.schema_map = dict(DEFAULT_SCHEMA_MAP)
		if schema_map:
			self.schema_map.update(schema_map)

	def _read_json_file(self, path: Path | str) -> Any:
		with Path(path).open("r", encoding="utf-8") as f:
			return json.load(f)

	def _load_schema(self, schema_filename: str) -> dict:
		schema_path = self.schema_dir / schema_filename
		if not schema_path.exists():
			raise FileNotFoundError(f"Schema file not found: {schema_path}")
		schema = self._read_json_file(schema_path)
		if not isinstance(schema, dict):
			raise JsonSchemaValidationError(
				f"Schema must be a JSON object: {schema_path}"
			)
		return schema

	def validate_data(self, data: Any, schema_filename: str) -> None:
		if Draft202012Validator is None:
			raise ModuleNotFoundError(
				"jsonschema package is required for schema validation. "
				"Install dependencies with: pip install -r requirements.txt"
			)
		schema = self._load_schema(schema_filename)
		validator = Draft202012Validator(schema)
		errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
		if not errors:
			return

		lines: List[str] = [
			f"Schema validation failed ({len(errors)} error(s)) using '{schema_filename}':"
		]
		for error in errors:
			pointer = "$"
			for part in error.path:
				if isinstance(part, int):
					pointer += f"[{part}]"
				else:
					pointer += f".{part}"
			lines.append(f"- {pointer}: {error.message}")
		raise JsonSchemaValidationError("\n".join(lines))

	def validate_file(self, data_file: Path | str, schema_filename: str) -> None:
		data = self._read_json_file(data_file)
		self.validate_data(data, schema_filename)

	def validate_named_dataset(self, dataset_name: str, data: Any) -> None:
		if dataset_name not in self.schema_map:
			raise KeyError(f"No schema mapping configured for dataset '{dataset_name}'")
		self.validate_data(data, self.schema_map[dataset_name])

	def validate_all(
		self,
		data_dir: Path | str,
		dataset_names: Optional[Iterable[str]] = None,
	) -> None:
		data_root = Path(data_dir)
		names = list(dataset_names) if dataset_names is not None else list(self.schema_map.keys())

		collected_errors: List[str] = []
		for name in names:
			schema_filename = self.schema_map.get(name)
			if schema_filename is None:
				collected_errors.append(f"- {name}: missing schema mapping")
				continue

			data_path = data_root / f"{name}.json"
			if not data_path.exists():
				collected_errors.append(f"- {name}: data file not found ({data_path})")
				continue

			try:
				self.validate_file(data_path, schema_filename)
			except Exception as exc:  # pylint: disable=broad-except
				collected_errors.append(f"- {name}: {exc}")

		if collected_errors:
			raise JsonSchemaValidationError(
				"Validation failed for one or more datasets:\n" + "\n".join(collected_errors)
			)

