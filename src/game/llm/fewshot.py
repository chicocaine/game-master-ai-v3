from typing import Any, Dict, Iterable, List

from game.llm.context_window import build_recent_window
from game.llm.prompts import converse, encounter, enemy_ai, exploration, narration, postgame, pregame


_DOMAIN_TO_EXAMPLES = {
    "pregame": pregame.few_shot_examples,
    "exploration": exploration.few_shot_examples,
    "encounter": encounter.few_shot_examples,
    "postgame": postgame.few_shot_examples,
    "enemy_ai": enemy_ai.few_shot_examples,
    "narration": narration.few_shot_examples,
    "converse": converse.few_shot_examples,
}


def available_domains() -> list[str]:
    return sorted(_DOMAIN_TO_EXAMPLES.keys())


def get_few_shot_examples(
    domain: str,
    include_domains: Iterable[str] | None = None,
    exclude_domains: Iterable[str] | None = None,
    max_examples: int | None = None,
) -> List[Dict[str, Any]]:
    include_set = set(include_domains or [])
    exclude_set = set(exclude_domains or [])

    if include_set and domain not in include_set:
        return []
    if domain in exclude_set:
        return []

    loader = _DOMAIN_TO_EXAMPLES.get(domain)
    if loader is None:
        return []

    examples = list(loader())
    if max_examples is None:
        return examples
    if max_examples <= 0:
        return []
    return examples[:max_examples]


def get_few_shot_examples_with_budget(
    domain: str,
    max_examples: int,
    max_tokens: int,
    include_domains: Iterable[str] | None = None,
    exclude_domains: Iterable[str] | None = None,
) -> List[Dict[str, Any]]:
    examples = get_few_shot_examples(
        domain=domain,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        max_examples=max_examples,
    )
    return build_recent_window(examples, max_items=max_examples, max_tokens=max_tokens)
