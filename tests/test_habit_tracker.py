import importlib


def _reload(monkeypatch, tmp_path):
    monkeypatch.setenv("ASSISTANT_STATE_DIR", str(tmp_path))
    from src.assistant import habit_tracker as _habit_tracker_module

    return importlib.reload(_habit_tracker_module)


def test_habit_create_log_and_status(tmp_path, monkeypatch):
    habit_tracker = _reload(monkeypatch, tmp_path)

    create = habit_tracker.habit_create_action({
        "name": "Water",
        "description": "Drink water",
        "target_per_day": 3,
        "tags": ["health"],
    })
    assert create["ok"]
    assert create["habit"]["name"] == "Water"

    log = habit_tracker.habit_log_action({"name": "Water", "note": "500ml"})
    assert log["ok"]
    assert log["stats"]["log_count"] == 1

    status = habit_tracker.habit_status_action({"name": "Water", "days": 7})
    assert status["ok"]
    assert "Water" in status["say"]

    reset = habit_tracker.habit_reset_action({"name": "Water"})
    assert reset["ok"]
