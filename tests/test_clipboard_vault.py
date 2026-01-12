import importlib


def _reload(monkeypatch, tmp_path):
    monkeypatch.setenv("ASSISTANT_STATE_DIR", str(tmp_path))
    from src.assistant import clipboard_vault as _clipboard_module

    module = importlib.reload(_clipboard_module)
    monkeypatch.setattr(module, "_write_clipboard_text", lambda text: True)
    return module


def test_clipboard_save_search_restore(tmp_path, monkeypatch):
    clipboard = _reload(monkeypatch, tmp_path)

    save = clipboard.clipboard_save_action({"text": "Launch rockets", "tags": ["idea"]})
    assert save["ok"]
    snippet_id = save["snippet"]["snippet_id"]

    listing = clipboard.clipboard_list_action({"limit": 3})
    assert listing["ok"]
    assert "Launch" in listing["say"]

    search = clipboard.clipboard_search_action({"keyword": "rocket"})
    assert search["ok"]
    assert search["snippets"]

    restore = clipboard.clipboard_restore_action({"id": snippet_id})
    assert restore["ok"]
    assert restore["copied"] is True
