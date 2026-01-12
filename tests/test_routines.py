import importlib


def _reload(monkeypatch, tmp_path):
    monkeypatch.setenv("ASSISTANT_STATE_DIR", str(tmp_path))
    from src.assistant import routines as _routines_module

    module = importlib.reload(_routines_module)
    monkeypatch.setattr(module, "open_app_via_start", lambda name: True)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    return module


def test_routine_create_and_run(tmp_path, monkeypatch):
    routines = _reload(monkeypatch, tmp_path)

    create = routines.routine_create_action({
        "name": "Deep Work",
        "instructions": "create a routine called deep work to open notion.so and remind me to breathe",
    })
    assert create["ok"]
    assert create["routine"]["name"] == "Deep Work"

    listed = routines.routine_list_action({})
    assert listed["ok"]
    assert "Deep Work" in listed["say"]

    result = routines.routine_run_action({"name": "Deep Work"})
    assert result["ok"]
    assert "Routine Deep Work" in result["say"]

    deleted = routines.routine_delete_action({"name": "Deep Work"})
    assert deleted["ok"]
