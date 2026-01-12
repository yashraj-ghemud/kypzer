"""Personal routine builder and executor for the assistant.

A routine is a named list of deterministic steps such as opening URLs, launching
apps, waiting, or reading reminders out loud. Users can create routines with
natural language instructions ("create a routine called deep work to open notion
and start a 45 minute focus block"), list existing routines, run them, or delete
them entirely. This module owns routine persistence plus the tiny execution
engine that runs each step.

Key ideas:
- Routines are stored in ~/.kypzer/routines.json alongside other assistant state.
- Steps are simple dictionaries with a "kind" identifier and payload metadata.
- A small inference helper scans natural language instructions to build a first
  version of the step list so that voice commands remain short.
- Execution tries to be safe: launching apps uses the existing Start-menu helper,
  waits are capped, and shell commands require explicit confirmation fields.

The API mirrors the assistant's action convention by returning dictionaries with
"ok" booleans, "say" responses, and optional metadata.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .ui import open_app_via_start

STATE_DIR_ENV = "ASSISTANT_STATE_DIR"
STATE_DIR = Path(os.environ.get(STATE_DIR_ENV) or (Path.home() / ".kypzer"))
ROUTINE_PATH = STATE_DIR / "routines.json"


@dataclass
class RoutineStep:
    kind: str
    summary: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "summary": self.summary, "payload": self.payload}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RoutineStep":
        return cls(
            kind=(payload.get("kind") or "say").strip().lower(),
            summary=payload.get("summary") or payload.get("label") or "",
            payload=dict(payload.get("payload") or {}),
        )


@dataclass
class Routine:
    name: str
    description: str
    steps: List[RoutineStep]
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    usage_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "usage_count": self.usage_count,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Routine":
        steps = [RoutineStep.from_dict(item) for item in payload.get("steps", []) if isinstance(item, dict)]
        return cls(
            name=payload.get("name") or "routine",
            description=payload.get("description") or payload.get("summary") or "",
            tags=list(payload.get("tags") or []),
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
            usage_count=int(payload.get("usage_count") or 0),
            steps=steps,
        )


class RoutineStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        self._items: Dict[str, Routine] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        raw: Iterable[Any]
        if isinstance(data, dict) and "routines" in data:
            raw = data.get("routines") or []
        elif isinstance(data, list):
            raw = data
        else:
            raw = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            routine = Routine.from_dict(entry)
            self._items[self._key(routine.name)] = routine

    def _save(self) -> None:
        with self._lock:
            payload = {
                "version": 1,
                "updated_at": time.time(),
                "routines": [r.to_dict() for r in sorted(self._items.values(), key=lambda r: r.name.lower())],
            }
            tmp = self._path.with_suffix(".tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(self._path)

    def _key(self, name: str) -> str:
        return name.strip().lower()

    def get(self, name: str) -> Optional[Routine]:
        with self._lock:
            return self._items.get(self._key(name))

    def upsert(self, routine: Routine) -> Routine:
        with self._lock:
            routine.updated_at = time.time()
            self._items[self._key(routine.name)] = routine
            self._save()
            return routine

    def remove(self, name: str) -> bool:
        with self._lock:
            key = self._key(name)
            if key in self._items:
                self._items.pop(key)
                self._save()
                return True
            return False

    def all(self) -> List[Routine]:
        with self._lock:
            return list(self._items.values())


_STORE = RoutineStore(ROUTINE_PATH)


class RoutineExecutor:
    def __init__(self):
        self._log: List[str] = []

    def run(self, routine: Routine) -> Dict[str, Any]:
        for step in routine.steps:
            handler = getattr(self, f"_run_{step.kind}", None)
            if not handler:
                self._log.append(f"Skipped unsupported step {step.kind}.")
                continue
            try:
                handler(step)
            except Exception as exc:
                self._log.append(f"Step {step.kind} failed: {exc}")
        routine.usage_count += 1
        _STORE.upsert(routine)
        summary = f"Routine {routine.name} complete with {len(routine.steps)} steps."
        return {"ok": True, "say": summary, "log": list(self._log)}

    def _run_say(self, step: RoutineStep) -> None:
        text = step.payload.get("text") or step.summary
        if text:
            self._log.append(f"Say: {text}")

    def _run_wait(self, step: RoutineStep) -> None:
        seconds = float(step.payload.get("seconds") or 0)
        seconds = max(0.5, min(90.0, seconds))
        self._log.append(f"Waiting {seconds} seconds")
        time.sleep(seconds)

    def _run_open_url(self, step: RoutineStep) -> None:
        url = step.payload.get("url") or step.summary
        if not url:
            return
        if not re.match(r"^[a-zA-Z]+://", url):
            url = "https://" + url
        webbrowser.open(url)
        self._log.append(f"Opened {url}")

    def _run_open_app(self, step: RoutineStep) -> None:
        name = step.payload.get("name") or step.summary
        if not name:
            return
        ok = open_app_via_start(name)
        self._log.append(f"Launch {name}: {'ok' if ok else 'failed'}")

    def _run_command(self, step: RoutineStep) -> None:
        command = step.payload.get("command")
        if not command:
            return
        if not step.payload.get("allow_shell"):
            self._log.append("Skipped shell command (allow_shell not set)")
            return
        if isinstance(command, str):
            cmd_list = shlex.split(command)
        else:
            cmd_list = list(command)
        subprocess.Popen(cmd_list, shell=False)
        self._log.append(f"Ran command: {command}")

    def _run_focus(self, step: RoutineStep) -> None:
        minutes = int(step.payload.get("minutes") or 25)
        topic = step.payload.get("topic") or step.summary or "Focus"
        self._log.append(f"Focus reminder: {topic} for {minutes} minutes.")


def _infer_steps_from_text(text: str) -> List[RoutineStep]:
    steps: List[RoutineStep] = []
    low = text.lower()
    url_pattern = re.compile(r"https?://\S+|\b[a-z0-9\-]+\.[a-z]{2,5}\b", re.I)
    for match in url_pattern.findall(text):
        url = match
        if not url.startswith("http"):
            url = "https://" + url
        steps.append(RoutineStep(kind="open_url", summary=f"Open {url}", payload={"url": url}))
    app_keywords = ["figma", "notion", "spotify", "slack", "vscode", "chrome", "edge"]
    for app in app_keywords:
        if app in low:
            steps.append(RoutineStep(kind="open_app", summary=f"Open {app}", payload={"name": app}))
    focus_match = re.search(r"(\d{1,3})\s*(minutes?|mins?)\s+focus", low)
    if focus_match:
        minutes = int(focus_match.group(1))
        steps.append(RoutineStep(kind="focus", summary="Focus timer", payload={"minutes": minutes}))
    reminder_match = re.search(r"remind\s+me\s+to\s+(.+)$", text, flags=re.I)
    if reminder_match:
        steps.append(RoutineStep(kind="say", summary=reminder_match.group(1).strip(), payload={"text": reminder_match.group(1).strip()}))
    if not steps:
        steps.append(RoutineStep(kind="say", summary="Routine started", payload={"text": text.strip()}))
    return steps


def routine_create_action(params: Dict[str, Any]) -> Dict[str, Any]:
    name = (params.get("name") or params.get("title") or "").strip()
    if not name:
        return {"ok": False, "say": "Routine name?"}
    description = (params.get("description") or params.get("summary") or params.get("instructions") or "").strip()
    tags = [t.strip() for t in params.get("tags") or [] if t]
    steps_payload = params.get("steps")
    steps: List[RoutineStep] = []
    if isinstance(steps_payload, list):
        for entry in steps_payload:
            if not isinstance(entry, dict):
                continue
            steps.append(RoutineStep.from_dict(entry))
    if not steps and description:
        steps = _infer_steps_from_text(description)
    if not steps:
        return {"ok": False, "say": "Need at least one step."}

    routine = _STORE.get(name)
    if routine:
        routine.description = description or routine.description
        routine.tags = sorted(set(routine.tags + tags)) if tags else routine.tags
        routine.steps = steps
    else:
        routine = Routine(name=name, description=description or name, tags=tags, steps=steps)
    _STORE.upsert(routine)
    return {"ok": True, "say": f"Routine {name} saved with {len(steps)} steps.", "routine": routine.to_dict()}


def routine_list_action(params: Dict[str, Any]) -> Dict[str, Any]:
    routines = _STORE.all()
    if not routines:
        return {"ok": True, "say": "No routines yet. Say 'create routine' to add one.", "routines": []}
    lines = []
    for routine in sorted(routines, key=lambda r: (-(r.usage_count), r.name.lower())):
        lines.append(f"{routine.name}: {len(routine.steps)} steps, used {routine.usage_count} times.")
    return {"ok": True, "say": " | ".join(lines), "routines": [r.to_dict() for r in routines]}


def routine_delete_action(params: Dict[str, Any]) -> Dict[str, Any]:
    name = (params.get("name") or params.get("title") or "").strip()
    if not name:
        return {"ok": False, "say": "Which routine should I delete?"}
    removed = _STORE.remove(name)
    if removed:
        return {"ok": True, "say": f"Deleted routine {name}."}
    return {"ok": False, "say": f"Couldn't find routine {name}."}


def routine_run_action(params: Dict[str, Any]) -> Dict[str, Any]:
    name = (params.get("name") or params.get("title") or "").strip()
    if not name:
        return {"ok": False, "say": "Which routine should I run?"}
    routine = _STORE.get(name)
    if not routine:
        return {"ok": False, "say": f"No routine named {name}."}
    executor = RoutineExecutor()
    result = executor.run(routine)
    result["routine"] = routine.to_dict()
    return result


__all__ = [
    "routine_create_action",
    "routine_list_action",
    "routine_delete_action",
    "routine_run_action",
]
