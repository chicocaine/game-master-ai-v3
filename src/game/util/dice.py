from typing import Optional, Tuple
import random
import re

_DICE_PATTERN = re.compile(r"^(\d+)d(\d+)([+\-]\d+)?$")


def _parse_dice_notation(dice_str: str) -> Tuple[int, int, int]:
	match = _DICE_PATTERN.match(dice_str.strip())
	if not match:
		raise ValueError(f"Invalid dice notation: {dice_str}")
	count = int(match.group(1))
	sides = int(match.group(2))
	modifier = int(match.group(3)) if match.group(3) else 0
	return count, sides, modifier


def _roll_d20(rng: Optional[random.Random] = None) -> int:
	rng = rng or random
	return rng.randint(1, 20)


def roll_dice(dice_str: str, rng: Optional[random.Random] = None) -> int:
	count, sides, modifier = _parse_dice_notation(dice_str)
	rng = rng or random
	rolls = [rng.randint(1, sides) for _ in range(count)]
	total = sum(rolls) + modifier
	return total


def roll_for_initiative(rng: Optional[random.Random] = None) -> int:
	return _roll_d20(rng)


def roll_save_throw(rng: Optional[random.Random] = None) -> int:
	return _roll_d20(rng)






