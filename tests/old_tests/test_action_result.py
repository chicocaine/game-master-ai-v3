from game.core.action_result import ActionResult


def test_action_result_success_and_failure_helpers() -> None:
    success = ActionResult.success(state_changes={"state": {"from": "pregame", "to": "exploration"}})
    assert success.ok is True
    assert success.errors == []
    assert success.state_changes["state"]["to"] == "exploration"

    failure = ActionResult.failure(errors=["bad action"])
    assert failure.ok is False
    assert failure.errors == ["bad action"]
def test_action_result_to_dict_contains_ok_flag() -> None:
    payload = ActionResult.failure(errors=["error_1"]).to_dict()
    assert payload["ok"] is False
    assert payload["errors"] == ["error_1"]


def test_action_result_from_errors_classmethod() -> None:
    ok_result = ActionResult.from_errors([])
    assert ok_result.ok is True

    error_result = ActionResult.from_errors(["error_1"])
    assert error_result.ok is False
    assert error_result.errors == ["error_1"]
