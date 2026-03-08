from dataclasses import dataclass, field
from typing import Any, Dict, List
from uuid import uuid4

from core.enums import ActionType


def _get_str(data: dict, key: str, default: str = "") -> str:
	return str(data.get(key, default))


def _get_dict(data: dict, key: str) -> Dict[str, Any]:
	value = data.get(key, {})
	if isinstance(value, dict):
		return value
	return {}


def _normalize_action_parameters(action_type: ActionType, parameters: Dict[str, Any]) -> Dict[str, Any]:
	normalized = dict(parameters)
	if action_type == ActionType.ATTACK:
		if "target_instance_ids" not in normalized and "target_instance_id" in normalized:
			normalized["target_instance_ids"] = normalized["target_instance_id"]

	if action_type == ActionType.CREATE_PLAYER:
		if "race" not in normalized and "race_id" in normalized:
			normalized["race"] = normalized["race_id"]
		if "archetype" not in normalized and "archetype_id" in normalized:
			normalized["archetype"] = normalized["archetype_id"]
		if "weapons" not in normalized and "weapon_ids" in normalized:
			normalized["weapons"] = normalized["weapon_ids"]

	if action_type == ActionType.EDIT_PLAYER:
		if "race" not in normalized and "race_id" in normalized:
			normalized["race"] = normalized["race_id"]
		if "archetype" not in normalized and "archetype_id" in normalized:
			normalized["archetype"] = normalized["archetype_id"]
		if "weapons" not in normalized and "weapon_ids" in normalized:
			normalized["weapons"] = normalized["weapon_ids"]

	if action_type == ActionType.CHOOSE_DUNGEON:
		if "dungeon" not in normalized and "dungeon_id" in normalized:
			normalized["dungeon"] = normalized["dungeon_id"]

	if action_type == ActionType.CONVERSE and "message" in normalized:
		normalized["message"] = str(normalized["message"]).strip()
	return normalized


@dataclass
class Action:
	type: ActionType
	parameters: Dict[str, Any] = field(default_factory=dict)
	actor_instance_id: str = ""
	raw_input: str = ""
	reasoning: str = ""
	metadata: Dict[str, Any] = field(default_factory=dict)
	action_id: str = field(default_factory=lambda: str(uuid4()))

	def to_dict(self) -> dict:
		return {
			"action_id": self.action_id,
			"type": self.type.value,
			"actor_instance_id": self.actor_instance_id,
			"parameters": self.parameters,
			"raw_input": self.raw_input,
			"reasoning": self.reasoning,
			"metadata": self.metadata,
		}

	@classmethod
	def from_dict(cls, data: dict) -> "Action":
		action_type = ActionType(_get_str(data, "type"))
		parameters = _normalize_action_parameters(action_type, _get_dict(data, "parameters"))
		return cls(
			type=action_type,
			parameters=parameters,
			actor_instance_id=_get_str(data, "actor_instance_id"),
			raw_input=_get_str(data, "raw_input"),
			reasoning=_get_str(data, "reasoning"),
			metadata=_get_dict(data, "metadata"),
			action_id=_get_str(data, "action_id", str(uuid4())),
		)


REQUIRED_PARAMETERS: Dict[ActionType, List[str]] = {
	ActionType.ABANDON: [],
	ActionType.QUERY: ["question"],
	ActionType.CONVERSE: ["message"],
	ActionType.MOVE: ["destination_room_id"],
	ActionType.REST: ["rest_type"],
	ActionType.ATTACK: ["attack_id", "target_instance_ids"],
	ActionType.CAST_SPELL: ["spell_id", "target_instance_ids"],
	ActionType.END_TURN: [],
	ActionType.START: [],
	ActionType.CREATE_PLAYER: ["name", "description", "race", "archetype", "weapons"],
	ActionType.REMOVE_PLAYER: ["player_instance_id"],
	ActionType.EDIT_PLAYER: ["player_instance_id", "name", "description", "race", "archetype", "weapons"],
	ActionType.CHOOSE_DUNGEON: ["dungeon"],
	ActionType.FINISH: [],
}


def validate_action(action: Action) -> List[str]:
	errors: List[str] = []

	missing_keys = [
		key
		for key in REQUIRED_PARAMETERS.get(action.type, [])
		if key not in action.parameters or action.parameters[key] in (None, "")
	]
	for key in missing_keys:
		errors.append(f"Missing required parameter '{key}' for action '{action.type.value}'")

	if action.type == ActionType.CONVERSE and "message" in action.parameters:
		if not str(action.parameters["message"]).strip():
			errors.append("Parameter 'message' for action 'converse' cannot be blank")

	if action.type == ActionType.ATTACK and "target_instance_ids" in action.parameters:
		targets = action.parameters["target_instance_ids"]
		if not isinstance(targets, (str, list)):
			errors.append("Parameter 'target_instance_ids' for action 'attack' must be string or list of strings")
		elif isinstance(targets, list):
			if not targets or any(not isinstance(target, str) or not target.strip() for target in targets):
				errors.append("Parameter 'target_instance_ids' for action 'attack' list must contain non-blank strings")
		elif not targets.strip():
			errors.append("Parameter 'target_instance_ids' for action 'attack' cannot be blank")

	if action.type == ActionType.CAST_SPELL and "target_instance_ids" in action.parameters:
		targets = action.parameters["target_instance_ids"]
		if not isinstance(targets, (str, list)):
			errors.append("Parameter 'target_instance_ids' for action 'cast_spell' must be string or list of strings")
		elif isinstance(targets, list):
			if not targets or any(not isinstance(target, str) or not target.strip() for target in targets):
				errors.append("Parameter 'target_instance_ids' for action 'cast_spell' list must contain non-blank strings")
		elif not targets.strip():
			errors.append("Parameter 'target_instance_ids' for action 'cast_spell' cannot be blank")

	return errors


def create_action(
	action_type: ActionType,
	parameters: Dict[str, Any] | None = None,
	actor_instance_id: str = "",
	raw_input: str = "",
	reasoning: str = "",
	metadata: Dict[str, Any] | None = None,
) -> Action:
	normalized_parameters = _normalize_action_parameters(action_type, parameters or {})
	return Action(
		type=action_type,
		parameters=normalized_parameters,
		actor_instance_id=actor_instance_id,
		raw_input=raw_input,
		reasoning=reasoning,
		metadata=metadata or {},
	)
