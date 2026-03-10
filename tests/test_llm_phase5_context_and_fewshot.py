from game.llm.context_window import build_recent_window, estimate_tokens, fit_dict_to_token_budget, truncate_text_to_token_budget
from game.llm.fewshot import available_domains, get_few_shot_examples, get_few_shot_examples_with_budget


def test_truncate_text_to_token_budget_is_deterministic():
    text = "abcdefghijklmnopqrstuvwxyz" * 20
    first = truncate_text_to_token_budget(text, max_tokens=10)
    second = truncate_text_to_token_budget(text, max_tokens=10)

    assert first == second
    assert len(first) == 40  # 10 tokens * 4 chars


def test_build_recent_window_honors_item_and_token_limits():
    items = [{"id": i, "content": "x" * 20} for i in range(10)]
    # Small budget should keep only a few latest items.
    window = build_recent_window(items, max_items=5, max_tokens=25)

    assert len(window) <= 5
    assert sum(estimate_tokens(item) for item in window) <= 25
    # Must preserve chronological order from older to newer among selected items.
    ids = [item["id"] for item in window]
    assert ids == sorted(ids)
    assert ids[-1] == 9


def test_fit_dict_to_token_budget_keeps_priority_keys():
    payload = {
        "domain": "narration",
        "events": [{"type": "damage_applied", "amount": 3}] * 20,
        "state_summary": {"state": "encounter", "points": 12},
        "extra_1": "A" * 200,
        "extra_2": "B" * 200,
    }

    compact = fit_dict_to_token_budget(
        payload,
        max_tokens=40,
        priority_keys=["domain", "events", "state_summary"],
    )

    assert "domain" in compact
    assert "events" in compact
    assert "state_summary" in compact
    assert estimate_tokens(compact) <= estimate_tokens(payload)


def test_fewshot_include_exclude_logic_by_domain():
    domains = available_domains()
    assert "pregame" in domains
    assert "enemy_ai" in domains

    included = get_few_shot_examples(domain="pregame", include_domains=["pregame", "encounter"])
    excluded = get_few_shot_examples(domain="pregame", exclude_domains=["pregame"])

    assert len(included) > 0
    assert excluded == []


def test_fewshot_budget_truncates_examples_deterministically():
    examples_first = get_few_shot_examples_with_budget(
        domain="encounter",
        max_examples=3,
        max_tokens=20,
    )
    examples_second = get_few_shot_examples_with_budget(
        domain="encounter",
        max_examples=3,
        max_tokens=20,
    )

    assert examples_first == examples_second
    assert len(examples_first) <= 3
