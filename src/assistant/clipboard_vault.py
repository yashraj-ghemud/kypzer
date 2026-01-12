"""Clipboard snippet vault for the assistant.

The assistant frequently copies text on behalf of the user (WhatsApp drafts,
notes, URLs). Remembering the last thing copied is nice but a rolling history is
better—especially when the user can tag snippets, search them later, and restore
them back to the clipboard with a single voice command.

Implementation notes:
- Snippets are stored in ~/.kypzer/clipboard_snippets.json as plain JSON.
- We attempt to read/write the real OS clipboard via tkinter, falling back to
  purely in-memory operations if Tk is unavailable.
- Public entry points follow the action contract returning {ok/say/...} dicts.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

STATE_DIR_ENV = "ASSISTANT_STATE_DIR"
STATE_DIR = Path(os.environ.get(STATE_DIR_ENV) or (Path.home() / ".kypzer"))
SNIPPET_PATH = STATE_DIR / "clipboard_snippets.json"
_MAX_SNIPPETS = 200


def _read_clipboard_text() -> Optional[str]:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return text
    except Exception:
        return None


def _write_clipboard_text(text: str) -> bool:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


@dataclass
class Snippet:
    snippet_id: str
    text: str
    created_at: float
    tags: List[str] = field(default_factory=list)
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Snippet":
        return cls(
            snippet_id=payload.get("snippet_id") or payload.get("id") or str(int(time.time() * 1000)),
            text=payload.get("text") or "",
            created_at=float(payload.get("created_at") or time.time()),
            tags=list(payload.get("tags") or []),
            source=payload.get("source"),
        )


class SnippetStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        self._snippets: List[Snippet] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        raw: Iterable[Any]
        if isinstance(payload, dict) and "snippets" in payload:
            raw = payload.get("snippets") or []
        elif isinstance(payload, list):
            raw = payload
        else:
            raw = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            self._snippets.append(Snippet.from_dict(entry))

    def _save(self) -> None:
        with self._lock:
            payload = {
                "version": 1,
                "snippets": [snippet.to_dict() for snippet in self._snippets[-_MAX_SNIPPETS:]],
            }
            tmp = self._path.with_suffix(".tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(self._path)

    def add(self, snippet: Snippet) -> Snippet:
        with self._lock:
            self._snippets.append(snippet)
            self._snippets = self._snippets[-_MAX_SNIPPETS:]
            self._save()
            return snippet

    def list_recent(self, limit: int = 5) -> List[Snippet]:
        with self._lock:
            return list(self._snippets[-limit:])

    def search(self, keyword: str) -> List[Snippet]:
        with self._lock:
            keyword_low = keyword.lower()
            return [s for s in self._snippets if keyword_low in s.text.lower() or any(keyword_low in t.lower() for t in s.tags)]

    def get(self, identifier: str) -> Optional[Snippet]:
        with self._lock:
            identifier = identifier.lower().strip()
            if identifier.isdigit():
                idx = int(identifier) - 1
                recents = self.list_recent(limit=_MAX_SNIPPETS)
                if 0 <= idx < len(recents):
                    return recents[-(idx + 1)]
            for snippet in reversed(self._snippets):
                if snippet.snippet_id.lower() == identifier:
                    return snippet
                if snippet.tags and identifier in [t.lower() for t in snippet.tags]:
                    return snippet
        return None


_STORE = SnippetStore(SNIPPET_PATH)


def _normalize_tags(raw: Optional[Any]) -> List[str]:
    if isinstance(raw, str):
        parts = re.split(r"[,\s]+", raw)
    else:
        parts = list(raw or [])
    return [part.strip().lower() for part in parts if part]


def clipboard_save_action(params: Dict[str, Any]) -> Dict[str, Any]:
    text = params.get("text")
    if not text:
        text = _read_clipboard_text()
    if not text:
        return {"ok": False, "say": "Clipboard is empty."}
    tags = _normalize_tags(params.get("tags"))
    snippet = Snippet(snippet_id=str(int(time.time() * 1000)), text=text.strip(), created_at=time.time(), tags=tags, source=params.get("source"))
    _STORE.add(snippet)
    tag_text = f" with tags {', '.join(tags)}" if tags else ""
    return {"ok": True, "say": f"Saved snippet{tag_text}.", "snippet": snippet.to_dict()}


def clipboard_list_action(params: Dict[str, Any]) -> Dict[str, Any]:
    limit = int(params.get("limit") or 5)
    limit = max(1, min(20, limit))
    snippets = _STORE.list_recent(limit=limit)
    if not snippets:
        return {"ok": True, "say": "No snippets saved yet.", "snippets": []}
    lines = []
    for idx, snippet in enumerate(reversed(snippets), start=1):
        preview = snippet.text.replace("\n", " ")
        if len(preview) > 60:
            preview = preview[:57] + "..."
        lines.append(f"{idx}. {preview}")
    return {"ok": True, "say": " | ".join(lines), "snippets": [s.to_dict() for s in snippets]}


def clipboard_search_action(params: Dict[str, Any]) -> Dict[str, Any]:
    keyword = (params.get("keyword") or params.get("text") or "").strip()
    if not keyword:
        return {"ok": False, "say": "Search term?"}
    results = _STORE.search(keyword)
    if not results:
        return {"ok": True, "say": f"No snippets matching {keyword}.", "snippets": []}
    lines = []
    for snippet in results[:5]:
        preview = snippet.text.strip().replace("\n", " ")
        if len(preview) > 50:
            preview = preview[:47] + "..."
        lines.append(f"[{snippet.snippet_id}] {preview}")
    return {"ok": True, "say": " | ".join(lines), "snippets": [s.to_dict() for s in results]}


def clipboard_restore_action(params: Dict[str, Any]) -> Dict[str, Any]:
    identifier = (params.get("id") or params.get("snippet_id") or params.get("tag") or params.get("keyword") or "").strip()
    if not identifier:
        return {"ok": False, "say": "Which snippet should I restore?"}
    snippet = _STORE.get(identifier)
    if not snippet:
        return {"ok": False, "say": f"No snippet named {identifier}."}
    ok = _write_clipboard_text(snippet.text)
    action = "Restored" if ok else "Found"
    return {"ok": True, "say": f"{action} snippet {snippet.snippet_id}.", "snippet": snippet.to_dict(), "copied": ok}


__all__ = [
    "clipboard_save_action",
    "clipboard_list_action",
    "clipboard_search_action",
    "clipboard_restore_action",
]
