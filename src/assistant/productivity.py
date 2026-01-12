"""Lightweight productivity helpers for tasks, focus sessions, and quick notes.

The goal is to keep all state on disk in a single directory so the assistant can
survive restarts and voice-only sessions without losing context. The helpers in
this module deliberately avoid external dependencies to stay portable.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STATE_DIR_ENV = "ASSISTANT_STATE_DIR"
_DEFAULT_STATE_DIR = Path(os.environ.get(STATE_DIR_ENV) or (Path.home() / ".kypzer"))
_STATE_DIR_LOCK = threading.Lock()


def _ensure_state_dir() -> Path:
    with _STATE_DIR_LOCK:
        try:
            _DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return _DEFAULT_STATE_DIR


STATE_DIR = _ensure_state_dir()


def _safe_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, indent=2, sort_keys=True)
    tmp_path.write_text(data, encoding="utf-8")
    tmp_path.replace(path)


def _safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = path.read_text(encoding="utf-8")
        return json.loads(data) or {}
    except Exception:
        return {}


def _now() -> float:
    return time.time()


def _human_delta(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        minutes = seconds / 60.0
        return f"{minutes:.1f}m" if minutes - int(minutes) else f"{int(minutes)}m"
    hours = seconds / 3600.0
    return f"{hours:.1f}h" if hours - int(hours) else f"{int(hours)}h"


def _human_time(ts: Optional[float]) -> str:
    if not ts:
        return "unscheduled"
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%a %d %b %H:%M")


def _priority_sort_key(priority: str) -> int:
    order = {"high": 0, "normal": 1, "low": 2}
    return order.get(priority.lower(), 1)


@dataclass
class Task:
    task_id: str
    title: str
    created_at: float
    due_ts: Optional[float] = None
    priority: str = "normal"
    tags: List[str] = field(default_factory=list)
    note: Optional[str] = None
    completed_at: Optional[float] = None

    def is_done(self) -> bool:
        return bool(self.completed_at)

    def short_summary(self) -> str:
        due = _human_time(self.due_ts)
        status = "done" if self.is_done() else "pending"
        tag_text = f" [{' '.join(self.tags)}]" if self.tags else ""
        return f"{self.title}{tag_text} ({status}, due {due})"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Task":
        return cls(
            task_id=payload.get("task_id") or payload.get("id") or str(uuid.uuid4()),
            title=payload.get("title") or payload.get("text") or "Untitled",
            created_at=float(payload.get("created_at") or _now()),
            due_ts=payload.get("due_ts"),
            priority=(payload.get("priority") or "normal").lower(),
            tags=list(payload.get("tags") or []),
            note=payload.get("note"),
            completed_at=payload.get("completed_at"),
        )


class TaskManager:
    def __init__(self, storage_path: Path):
        self._path = storage_path
        self._lock = threading.RLock()
        self._tasks: Dict[str, Task] = {}
        self._load()

    def _load(self) -> None:
        payload = _safe_read_json(self._path)
        tasks: Dict[str, Task] = {}
        raw_list: Iterable[Any]
        if isinstance(payload, dict) and "tasks" in payload:
            raw_list = payload.get("tasks") or []
        elif isinstance(payload, list):
            raw_list = payload
        else:
            raw_list = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            task = Task.from_dict(item)
            tasks[task.task_id] = task
        self._tasks = tasks

    def _save(self) -> None:
        with self._lock:
            safe_tasks = [task.to_dict() for task in self._tasks.values()]
            _safe_write_json(self._path, {"tasks": safe_tasks, "version": 1})

    def add_task(
        self,
        title: str,
        *,
        due_ts: Optional[float] = None,
        priority: str = "normal",
        tags: Optional[Iterable[str]] = None,
        note: Optional[str] = None,
    ) -> Task:
        title = title.strip()
        if not title:
            raise ValueError("Task title required")
        task = Task(
            task_id=str(uuid.uuid4()),
            title=title,
            created_at=_now(),
            due_ts=due_ts,
            priority=priority.lower(),
            tags=[t.strip() for t in (tags or []) if t],
            note=note.strip() if note else None,
        )
        with self._lock:
            self._tasks[task.task_id] = task
            self._save()
        return task

    def list_tasks(self, include_completed: bool = False) -> List[Task]:
        with self._lock:
            tasks = list(self._tasks.values())
        filtered = [t for t in tasks if include_completed or not t.is_done()]
        return sorted(
            filtered,
            key=lambda t: (
                t.is_done(),
                1 if t.due_ts is None else 0,
                t.due_ts or 0,
                _priority_sort_key(t.priority),
                t.created_at,
            ),
        )

    def find_task(self, keyword: str) -> Optional[Task]:
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return None
        with self._lock:
            for task in self._tasks.values():
                haystack = " ".join([task.title.lower(), " ".join(task.tags).lower()])
                if keyword in task.task_id.lower() or keyword in haystack:
                    return task
        return None

    def complete_task(self, keyword: str) -> Optional[Task]:
        with self._lock:
            task = self.find_task(keyword)
            if not task:
                return None
            task.completed_at = _now()
            self._save()
            return task

    def clear_completed(self, max_age_days: int = 7) -> int:
        cutoff = _now() - (max_age_days * 86400)
        removed = 0
        with self._lock:
            to_delete = [tid for tid, task in self._tasks.items() if task.completed_at and task.completed_at < cutoff]
            for tid in to_delete:
                removed += 1
                self._tasks.pop(tid, None)
            if removed:
                self._save()
        return removed

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for task in self._tasks.values() if not task.is_done())

    def as_lines(self, limit: int = 5) -> List[str]:
        tasks = self.list_tasks()
        lines: List[str] = []
        for idx, task in enumerate(tasks[:limit], start=1):
            due = _human_time(task.due_ts)
            badge = "!" if task.priority == "high" else ("-" if task.priority == "low" else " ")
            note = f" // {task.note}" if task.note else ""
            tags = f" [{' '.join(task.tags)}]" if task.tags else ""
            lines.append(f"{idx:02d}{badge} {task.title}{tags} (due {due}){note}")
        if len(tasks) > limit:
            lines.append(f"...and {len(tasks) - limit} more tasks")
        if not lines:
            lines.append("No pending tasks. Enjoy the calm!")
        return lines


@dataclass
class FocusSession:
    label: str
    duration_seconds: int
    started_at: float
    completed_at: Optional[float] = None
    canceled: bool = False
    notes: List[str] = field(default_factory=list)

    def remaining_seconds(self) -> float:
        if self.completed_at:
            return 0.0
        elapsed = _now() - self.started_at
        return max(0.0, self.duration_seconds - elapsed)

    def status(self) -> str:
        if self.completed_at and not self.canceled:
            return "completed"
        if self.canceled:
            return "canceled"
        return "running"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FocusSession":
        return cls(
            label=payload.get("label") or "Focus",
            duration_seconds=int(payload.get("duration_seconds") or 1500),
            started_at=float(payload.get("started_at") or _now()),
            completed_at=payload.get("completed_at"),
            canceled=bool(payload.get("canceled")),
            notes=list(payload.get("notes") or []),
        )


class FocusSessionManager:
    def __init__(self, storage_path: Path):
        self._path = storage_path
        self._lock = threading.RLock()
        self._session: Optional[FocusSession] = None
        self._load()

    def _load(self) -> None:
        payload = _safe_read_json(self._path)
        if payload.get("session"):
            self._session = FocusSession.from_dict(payload["session"])
        elif payload:
            self._session = FocusSession.from_dict(payload)
        else:
            self._session = None

    def _save(self) -> None:
        if self._session is None:
            if self._path.exists():
                self._path.unlink(missing_ok=True)
            return
        _safe_write_json(self._path, {"session": self._session.to_dict(), "version": 1})

    def start(self, label: str, duration_seconds: int) -> FocusSession:
        label = label.strip() or "Focus"
        duration_seconds = max(60, min(duration_seconds, 4 * 3600))
        session = FocusSession(label=label, duration_seconds=duration_seconds, started_at=_now())
        with self._lock:
            self._session = session
            self._save()
        return session

    def stop(self, *, canceled: bool = False, note: Optional[str] = None) -> Optional[FocusSession]:
        with self._lock:
            if not self._session:
                return None
            session = self._session
            session.completed_at = _now()
            session.canceled = canceled
            if note:
                session.notes.append(note)
            self._session = session
            self._save()
            return session

    def status(self) -> Optional[FocusSession]:
        with self._lock:
            return self._session

    def add_note(self, text: str) -> Optional[FocusSession]:
        text = text.strip()
        if not text:
            return None
        with self._lock:
            if not self._session:
                return None
            self._session.notes.append(text)
            self._save()
            return self._session


@dataclass
class QuickNote:
    text: str
    created_at: float
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "QuickNote":
        return cls(
            text=payload.get("text") or "",
            created_at=float(payload.get("created_at") or _now()),
            tags=list(payload.get("tags") or []),
        )


class QuickCaptureBoard:
    def __init__(self, storage_path: Path, max_notes: int = 50):
        self._path = storage_path
        self._lock = threading.RLock()
        self._max_notes = max_notes
        self._notes: List[QuickNote] = []
        self._load()

    def _load(self) -> None:
        payload = _safe_read_json(self._path)
        raw_notes: Iterable[Any]
        if isinstance(payload, dict) and "notes" in payload:
            raw_notes = payload.get("notes") or []
        elif isinstance(payload, list):
            raw_notes = payload
        else:
            raw_notes = []
        self._notes = [QuickNote.from_dict(item) for item in raw_notes if isinstance(item, dict)]

    def _save(self) -> None:
        with self._lock:
            safe_notes = [note.to_dict() for note in self._notes[-self._max_notes :]]
            _safe_write_json(self._path, {"notes": safe_notes, "version": 1})

    def add(self, text: str, tags: Optional[Iterable[str]] = None) -> QuickNote:
        note = QuickNote(text=text.strip(), created_at=_now(), tags=[t.strip() for t in (tags or []) if t])
        with self._lock:
            self._notes.append(note)
            self._notes = self._notes[-self._max_notes :]
            self._save()
        return note

    def recent(self, limit: int = 5) -> List[QuickNote]:
        with self._lock:
            return list(self._notes[-limit:])


_TASK_MANAGER = TaskManager(STATE_DIR / "tasks.json")
_FOCUS_MANAGER = FocusSessionManager(STATE_DIR / "focus_session.json")
_NOTE_BOARD = QuickCaptureBoard(STATE_DIR / "quick_notes.json")


def _parse_tags(raw: Optional[Any]) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw)
    parts = [p.strip() for p in text.replace("#", " ").split() if p.strip()]
    return parts


def _parse_duration_seconds(raw: Optional[Any]) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(max(0, raw))
    text = str(raw).strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    units = {
        "second": 1,
        "seconds": 1,
        "sec": 1,
        "s": 1,
        "minute": 60,
        "minutes": 60,
        "min": 60,
        "m": 60,
        "hour": 3600,
        "hours": 3600,
        "hr": 3600,
        "h": 3600,
    }
    parts = text.replace("-", " ").split()
    total = 0
    idx = 0
    while idx < len(parts):
        part = parts[idx]
        if part.replace(".", "", 1).isdigit():
            value = float(part)
            unit = "minutes"
            if idx + 1 < len(parts) and parts[idx + 1] in units:
                unit = parts[idx + 1]
                idx += 1
            total += value * units.get(unit, 60)
        elif part == "in" and idx + 1 < len(parts):
            idx += 1
            continue
        idx += 1
    return int(total) if total else None


def _parse_due_spec(raw: Optional[Any]) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if raw > 32503680000:  # year 3000 guard
            return None
        if raw > 600 and raw < 864000:
            return _now() + float(raw)
        if raw > 0:
            return float(raw)
    text = str(raw).strip().lower()
    if not text:
        return None
    now = datetime.now()
    if text in {"today", "tonight"}:
        target = now.replace(hour=21, minute=0, second=0, microsecond=0)
        if target < now:
            target = target + timedelta(days=1)
        return target.timestamp()
    if text in {"tomorrow", "tmrw"}:
        target = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return target.timestamp()
    if text.startswith("in "):
        dur = _parse_duration_seconds(text[3:])
        if dur:
            return _now() + dur
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d/%m", "%m/%d", "%b %d", "%d %b"]:
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=now.year)
            return parsed.timestamp()
        except ValueError:
            continue
    if "tom" in text:
        return (now + timedelta(days=1)).timestamp()
    if "next week" in text:
        return (now + timedelta(days=7)).timestamp()
    return None


def _priority_from_text(raw: Optional[Any]) -> str:
    if raw is None:
        return "normal"
    text = str(raw).strip().lower()
    if any(word in text for word in ["high", "urgent", "important"]):
        return "high"
    if any(word in text for word in ["low", "chill", "someday"]):
        return "low"
    if text in {"high", "low", "normal"}:
        return text
    return "normal"


def productivity_add_task(params: Dict[str, Any]) -> Dict[str, Any]:
    description = params.get("description") or params.get("text") or params.get("title")
    if not description:
        return {"ok": False, "say": "Task description missing."}
    priority = _priority_from_text(params.get("priority"))
    tags = _parse_tags(params.get("tags"))
    note = params.get("note") or params.get("details")
    due_spec = params.get("due") or params.get("when")
    due_ts = _parse_due_spec(due_spec)
    task = _TASK_MANAGER.add_task(description, due_ts=due_ts, priority=priority, tags=tags, note=note)
    due_text = _human_time(task.due_ts)
    summary = f"Task added: {task.title} (due {due_text})"
    return {"ok": True, "say": summary, "task": task.to_dict()}


def productivity_list_tasks(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    include_completed = bool((params or {}).get("include_completed"))
    lines = _TASK_MANAGER.as_lines(limit=(params or {}).get("limit") or 7)
    if include_completed:
        completed = [task for task in _TASK_MANAGER.list_tasks(include_completed=True) if task.is_done()]
        done_lines = [f"✔ {task.short_summary()}" for task in completed[:3]]
        if len(completed) > 3:
            done_lines.append("...more completed tasks hidden")
    else:
        done_lines = []
    say_lines = lines + done_lines
    say = "\n".join(say_lines)
    return {"ok": True, "say": say, "tasks": [task.to_dict() for task in _TASK_MANAGER.list_tasks(include_completed=False)]}


def productivity_complete_task(params: Dict[str, Any]) -> Dict[str, Any]:
    keyword = params.get("id") or params.get("title") or params.get("text") or params.get("keyword")
    if not keyword:
        return {"ok": False, "say": "Which task should I complete?"}
    task = _TASK_MANAGER.complete_task(keyword)
    if not task:
        return {"ok": False, "say": "I could not find that task."}
    return {"ok": True, "say": f"Marked '{task.title}' done."}


def productivity_clear_tasks(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    removed = _TASK_MANAGER.clear_completed(max_age_days=int((params or {}).get("max_age_days") or 7))
    if not removed:
        return {"ok": True, "say": "No completed tasks to clear."}
    return {"ok": True, "say": f"Cleared {removed} completed task{'s' if removed != 1 else ''}."}


def productivity_capture_note(params: Dict[str, Any]) -> Dict[str, Any]:
    text = params.get("text") or params.get("note") or params.get("idea")
    if not text:
        return {"ok": False, "say": "Need a note to capture."}
    tags = _parse_tags(params.get("tags"))
    note = _NOTE_BOARD.add(text, tags=tags)
    hint = " ".join(f"#{tag}" for tag in note.tags)
    response = f"Note saved ({hint.strip()}" if hint else "Note saved"
    response = response.rstrip() + ")" if hint else response
    lines = [response]
    recent = _NOTE_BOARD.recent(limit=3)
    if recent:
        lines.append("Recent snippets:")
        for item in recent:
            when = _human_delta(_now() - item.created_at)
            tag_text = f" [{' '.join(item.tags)}]" if item.tags else ""
            lines.append(f"- {item.text[:60]}{tag_text} ({when} ago)")
    return {"ok": True, "say": "\n".join(lines)}


def productivity_focus_start(params: Dict[str, Any]) -> Dict[str, Any]:
    label = params.get("label") or params.get("task") or params.get("text") or "Focus"
    duration = _parse_duration_seconds(params.get("seconds") or params.get("minutes") or params.get("duration"))
    if not duration:
        duration = 25 * 60
    session = _FOCUS_MANAGER.start(label, duration)
    return {
        "ok": True,
        "say": f"Starting {label} focus session for {_human_delta(duration)}.",
        "session": session.to_dict(),
    }


def productivity_focus_stop(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    note = (params or {}).get("note")
    canceled = bool((params or {}).get("canceled"))
    session = _FOCUS_MANAGER.stop(canceled=canceled, note=note)
    if not session:
        return {"ok": False, "say": "No active focus session."}
    state = "completed" if not canceled else "canceled"
    return {"ok": True, "say": f"Focus session {state}. Well done!"}


def productivity_focus_status(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    session = _FOCUS_MANAGER.status()
    if not session:
        return {"ok": False, "say": "No focus session running."}
    remaining = _human_delta(session.remaining_seconds())
    return {
        "ok": True,
        "say": f"Focus '{session.label}' is {session.status()} with {remaining} left.",
        "session": session.to_dict(),
    }


def productivity_daily_briefing(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    lines: List[str] = []
    now = datetime.now().strftime("%A, %b %d")
    lines.append(f"Good {('morning' if datetime.now().hour < 12 else 'day')}! Today is {now}.")
    pending = _TASK_MANAGER.list_tasks()
    if pending:
        lines.append(f"You have {len(pending)} active task{'s' if len(pending) != 1 else ''}.")
        for task in pending[:3]:
            badge = "!" if task.priority == "high" else "-"
            lines.append(f"  {badge} {task.title} (due {_human_time(task.due_ts)})")
    else:
        lines.append("No pending tasks. Maybe stretch or take a walk.")
    session = _FOCUS_MANAGER.status()
    if session and not session.completed_at:
        lines.append(f"Focus session '{session.label}' still has {_human_delta(session.remaining_seconds())} remaining.")
    else:
        lines.append("No focus session running. Ready when you are.")
    recent_notes = _NOTE_BOARD.recent(limit=2)
    if recent_notes:
        lines.append("Latest quick notes:")
        for note in recent_notes:
            when = _human_delta(_now() - note.created_at)
            lines.append(f"  - {note.text[:80]} ({when} ago)")
    tips = [
        "Try batching similar tasks to stay in flow.",
        "Remember to blink and sip water.",
        "A two-minute stretch can reset your posture.",
        "Review your notes before meetings for context.",
        "Micro-breaks keep focus sharp.",
    ]
    lines.append(random.choice(tips))
    return {"ok": True, "say": "\n".join(lines)}


__all__ = [
    "productivity_add_task",
    "productivity_list_tasks",
    "productivity_complete_task",
    "productivity_clear_tasks",
    "productivity_capture_note",
    "productivity_focus_start",
    "productivity_focus_stop",
    "productivity_focus_status",
    "productivity_daily_briefing",
]
