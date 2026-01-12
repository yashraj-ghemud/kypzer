"""Simple habit tracking helpers for the desktop assistant.

The assistant already ships with lightweight task, note, and focus helpers. This
module complements them with habit tracking so recurring goals like
"stretch every hour" or "drink water" can be logged and summarized via voice.

Design goals:
- Keep state locally in the same ~/.kypzer directory as other helpers.
- Avoid external dependencies so the feature works out of the box.
- Provide deterministic analytics (streaks, rolling completion score) that can be
  narrated back to the user without requiring charts.
- Offer small pure-Python entry points that integrate nicely with action routing.

The code is intentionally verbose with extra dataclasses and helper routines so
that the logic is easy to test and extend. Most functions return dictionaries in
the same "ok/say" shape used by the assistant's action dispatcher.
"""

from __future__ import annotations

import json
import os
import threading
import time
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
HABIT_PATH = STATE_DIR / "habits.json"


def _now() -> float:
    return time.time()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


@dataclass
class HabitLog:
    ts: float
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "HabitLog":
        return cls(ts=float(payload.get("ts") or _now()), note=payload.get("note"))


@dataclass
class Habit:
    name: str
    description: str
    cadence: str = "daily"
    target_per_day: int = 1
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=_now)
    logs: List[HabitLog] = field(default_factory=list)

    def record(self, *, note: Optional[str] = None, timestamp: Optional[float] = None) -> HabitLog:
        entry = HabitLog(ts=float(timestamp or _now()), note=note.strip() if note else None)
        self.logs.append(entry)
        return entry

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["logs"] = [log.to_dict() for log in self.logs]
        return data

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Habit":
        logs = [HabitLog.from_dict(item) for item in payload.get("logs", []) if isinstance(item, dict)]
        return cls(
            name=payload.get("name") or payload.get("title") or "habit",
            description=payload.get("description") or payload.get("note") or "",
            cadence=payload.get("cadence") or "daily",
            target_per_day=int(payload.get("target_per_day") or payload.get("target") or 1),
            tags=list(payload.get("tags") or []),
            created_at=float(payload.get("created_at") or _now()),
            logs=logs,
        )


class HabitStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        self._habits: Dict[str, Habit] = {}
        self._load()

    def _load(self) -> None:
        payload = _read_json(self._path)
        items: Iterable[Any] = []
        if isinstance(payload, dict) and "habits" in payload:
            items = payload.get("habits") or []
        elif isinstance(payload, list):
            items = payload
        for entry in items:
            if not isinstance(entry, dict):
                continue
            habit = Habit.from_dict(entry)
            self._habits[self._key(habit.name)] = habit

    def _save(self) -> None:
        with self._lock:
            data = {
                "version": 1,
                "updated_at": _now(),
                "habits": [habit.to_dict() for habit in sorted(self._habits.values(), key=lambda h: h.name.lower())],
            }
            _write_json(self._path, data)

    def _key(self, name: str) -> str:
        return (name or "").strip().lower()

    def get(self, name: str) -> Optional[Habit]:
        with self._lock:
            return self._habits.get(self._key(name))

    def upsert(self, habit: Habit) -> Habit:
        with self._lock:
            self._habits[self._key(habit.name)] = habit
            self._save()
            return habit

    def all(self) -> List[Habit]:
        with self._lock:
            return list(self._habits.values())

    def remove(self, name: str) -> bool:
        with self._lock:
            key = self._key(name)
            if key in self._habits:
                self._habits.pop(key)
                self._save()
                return True
            return False


_HABIT_STORE = HabitStore(HABIT_PATH)


def _slug(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text.lower())
    cleaned = cleaned.strip("-")
    return cleaned or "habit"


def _format_ts(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%a %d %b %H:%M")


def _calc_daily_counts(logs: List[HabitLog], *, days: int = 14) -> List[Tuple[str, int]]:
    today = datetime.fromtimestamp(_now()).date()
    buckets: List[Tuple[str, int]] = []
    for offset in range(days):
        day = today - timedelta(days=offset)
        buckets.append((day.isoformat(), 0))
    bucket_map = {day: idx for idx, (day, _) in enumerate(buckets)}
    for log in logs:
        date_str = datetime.fromtimestamp(log.ts).date().isoformat()
        idx = bucket_map.get(date_str)
        if idx is not None:
            stamp, count = buckets[idx]
            buckets[idx] = (stamp, count + 1)
    return list(reversed(buckets))


def _streak(logs: List[HabitLog]) -> int:
    if not logs:
        return 0
    today = datetime.fromtimestamp(_now()).date()
    log_dates = {datetime.fromtimestamp(log.ts).date() for log in logs}
    streak = 0
    cursor = today
    while cursor in log_dates:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


def _score_for_day(count: int, target: int) -> float:
    if target <= 0:
        return 1.0
    return min(1.0, max(0.0, count / float(target)))


def _progress_summary(habit: Habit, *, window: int = 7) -> Tuple[float, str]:
    counts = _calc_daily_counts(habit.logs, days=window)
    if not counts:
        return 0.0, "No history yet."
    scores = [_score_for_day(count, habit.target_per_day) for _, count in counts]
    avg = sum(scores) / len(scores)
    pct = int(round(avg * 100))
    trend = "steady"
    if len(scores) >= 4:
        first = sum(scores[: len(scores)//2])
        second = sum(scores[len(scores)//2 :])
        if second > first + 0.5:
            trend = "improving"
        elif first > second + 0.5:
            trend = "slipping"
    text = f"{pct}% average over the last {window} days ({trend})."
    return avg, text


def _summarize_habit(habit: Habit) -> str:
    streak_days = _streak(habit.logs)
    _, trend_text = _progress_summary(habit)
    desc = habit.description or habit.name
    tags = f" [{' '.join(habit.tags)}]" if habit.tags else ""
    return f"{habit.name}{tags}: {desc}. {streak_days} day streak, {trend_text}"


def habit_create_action(params: Dict[str, Any]) -> Dict[str, Any]:
    name = (params.get("name") or params.get("title") or "").strip()
    if not name:
        return {"ok": False, "say": "Habit name?"}
    description = (params.get("description") or params.get("text") or "Track this habit.").strip()
    cadence = (params.get("cadence") or "daily").strip().lower()
    try:
        target = int(params.get("target_per_day") or params.get("target") or params.get("times") or 1)
    except Exception:
        target = 1
    tags = [t.strip() for t in params.get("tags") or [] if t]

    existing = _HABIT_STORE.get(name)
    if existing:
        existing.description = description or existing.description
        existing.cadence = cadence or existing.cadence
        existing.target_per_day = target or existing.target_per_day
        if tags:
            existing.tags = sorted(set(existing.tags + tags))
        habit = _HABIT_STORE.upsert(existing)
        say = f"Updated habit {habit.name}."
    else:
        habit = Habit(name=name, description=description, cadence=cadence, target_per_day=max(1, target), tags=tags)
        _HABIT_STORE.upsert(habit)
        say = f"Tracking habit {habit.name}."

    summary = _summarize_habit(habit)
    return {"ok": True, "say": f"{say} {summary}", "habit": habit.to_dict()}


def habit_log_action(params: Dict[str, Any]) -> Dict[str, Any]:
    name = (params.get("name") or params.get("habit") or params.get("title") or "").strip()
    if not name:
        return {"ok": False, "say": "Which habit should I log?"}
    note = (params.get("note") or params.get("text") or params.get("details") or "").strip()
    habit = _HABIT_STORE.get(name)
    if not habit:
        return {"ok": False, "say": f"I don't recognize the habit {name}."}
    habit.record(note=note or None)
    _HABIT_STORE.upsert(habit)
    streak_days = _streak(habit.logs)
    say = f"Logged {habit.name}. Streak is {streak_days} days."
    return {
        "ok": True,
        "say": say,
        "habit": habit.to_dict(),
        "stats": {
            "streak_days": streak_days,
            "log_count": len(habit.logs),
        },
    }


def habit_status_action(params: Dict[str, Any]) -> Dict[str, Any]:
    name = (params.get("name") or params.get("habit") or "").strip()
    window = int(params.get("window") or params.get("days") or 7)
    window = max(3, min(30, window))

    habits = [_HABIT_STORE.get(name)] if name else _HABIT_STORE.all()
    habits = [h for h in habits if h]
    if not habits:
        return {"ok": False, "say": "No habits tracked yet."}

    lines: List[str] = []
    for habit in habits:
        avg, trend = _progress_summary(habit, window=window)
        streak_days = _streak(habit.logs)
        last_log = habit.logs[-1] if habit.logs else None
        last_text = f"last logged {_format_ts(last_log.ts)}" if last_log else "no logs yet"
        lines.append(
            f"{habit.name}: {int(avg*100)}% avg, {streak_days} day streak, {last_text}. {trend}"
        )

    say = " | ".join(lines)
    return {"ok": True, "say": say, "habits": [h.to_dict() for h in habits], "window_days": window}


def habit_reset_action(params: Dict[str, Any]) -> Dict[str, Any]:
    name = (params.get("name") or params.get("habit") or "").strip()
    if not name:
        return {"ok": False, "say": "Which habit should I reset?"}
    habit = _HABIT_STORE.get(name)
    if not habit:
        return {"ok": False, "say": f"No habit named {name}."}
    habit.logs = []
    _HABIT_STORE.upsert(habit)
    return {"ok": True, "say": f"Cleared history for {habit.name}."}


__all__ = [
    "habit_create_action",
    "habit_log_action",
    "habit_status_action",
    "habit_reset_action",
]
