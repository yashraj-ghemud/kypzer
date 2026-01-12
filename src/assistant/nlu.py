import json
import re
import difflib
from typing import Any, Dict, List, Optional, Tuple

from .config import settings
from .conversation import ConversationMemory
from .llm_adapter import llm_plan
try:
    from .spacy_nlu import interpret as _spacy_interpret
except (ImportError, OSError):
    _spacy_interpret = None

# Import new enhanced modules
try:
    from .spotify_controller import parse_spotify_command as _parse_spotify_command
except (ImportError, OSError):
    _parse_spotify_command = None

try:
    from .whatsapp_enhanced import parse_whatsapp_command as _parse_whatsapp_enhanced
except (ImportError, OSError):
    _parse_whatsapp_enhanced = None

try:
    from .task_scheduler import parse_scheduled_task_command as _parse_scheduled_task
except (ImportError, OSError):
    _parse_scheduled_task = None

try:
    from .multi_task_parser import (
        parse_multi_task_command as _parse_multi_task,
        is_multi_task_command as _is_multi_task,
    )
except (ImportError, OSError):
    _parse_multi_task = None
    _is_multi_task = None

# Minimal system prompt
SYSTEM_PROMPT = (
    "You are a helpful, polite, and concise multilingual PC voice assistant. "
    "When given a user message, produce a friendly short reply and a safe, deterministic list of actions. "
    "Return only JSON with two keys: `response` (a short natural-language string) and `actions` (an array). "
    "Each action must be an object with `type` and a `parameters` object. "
    "Keep replies short and helpful."
)


def _has_valid_openai_key(raw: str) -> bool:
    token = (raw or "").strip()
    if not token:
        return False
    # Treat obvious placeholder values as invalid so we never hit the remote API
    upper = token.upper()
    if "YOUR_" in upper or upper.endswith("_HERE"):
        return False
    if token.startswith("sk-PLACEHOLDER") or token.startswith("sk_test"):
        return False
    return True


def _llm_plan(user_text: str, memory: Optional[ConversationMemory] = None) -> Dict[str, Any]:
    """Delegates to the real LLM adapter."""
    return llm_plan(user_text, memory=memory)


def _contains_term(text: str, term: str) -> bool:
    if not term:
        return False
    if " " in term:
        return term in text
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def _contains_any(text: str, terms: List[str]) -> bool:
    return any(_contains_term(text, t) for t in terms)


COMMON_TERMS = [
    "battery", "saver", "wifi", "bluetooth", "volume",
    "brightness", "notepad", "whatsapp", "shutdown", "restart",
]


TIME_UNIT_SECONDS = {
    "ms": 0.001,
    "millisecond": 0.001,
    "milliseconds": 0.001,
    "s": 1.0,
    "sec": 1.0,
    "secs": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "m": 60.0,
    "min": 60.0,
    "mins": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hrs": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
}


BROWSER_KEYWORDS = {
    "chrome",
    "edge",
    "firefox",
    "brave",
    "opera",
}


APP_ALIAS_MAP = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
}


QUICK_SETTING_ALIASES = {
    "airplane mode": ["airplane mode", "flight mode", "aeroplane mode"],
    "focus assist": ["focus assist", "focus mode", "focus assist mode"],
    "battery saver": ["battery saver", "battery saving", "power saver"],
    "mobile hotspot": ["mobile hotspot", "hotspot", "hot spot", "wi-fi hotspot"],
}


def _normalize_contact_name(name: str) -> str:
    cleaned = re.sub(r"(?i)\bon\s+whatsapp\b", "", name)
    cleaned = re.sub(r"(?i)\bwith\s+ai.*$", "", cleaned)
    cleaned = re.sub(r"(?i)\bclose\s+whatsapp\b", "", cleaned)
    cleaned = re.sub(r"(?i)^\s*(aur|and)\s+", "", cleaned)
    val = cleaned.strip(" .,:;\n")
    
    # Common Alias Mapping
    aliases = {
        "mum": "Mom",
        "mummy": "Mom",
        "mama": "Mom",
        "mommy": "Mom",
        "papa": "Papa",
        "dad": "Papa"
    }
    return aliases.get(val.lower(), val)


def _parse_time_value(number: str, unit: Optional[str]) -> Optional[float]:
    try:
        value = float(number)
    except (TypeError, ValueError):
        return None
    value = max(0.0, value)
    if value == 0:
        return 0.0
    if not unit:
        return value
    unit_key = unit.strip().lower()
    unit_key = unit_key.replace("sec", "sec")
    if unit_key in TIME_UNIT_SECONDS:
        return value * TIME_UNIT_SECONDS[unit_key]
    # pluralization fallback (e.g., 'secondes')
    unit_key = unit_key.rstrip("s")
    if unit_key in TIME_UNIT_SECONDS:
        return value * TIME_UNIT_SECONDS[unit_key]
    return value


def _format_seconds_brief_nlu(seconds: float) -> str:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return ""
    value = max(0.0, value)
    if value >= 3600:
        hours = value / 3600.0
        if abs(round(hours) - hours) < 0.01:
            hours = float(round(hours))
        return f"{hours:g} hour{'s' if hours >= 1.5 else ''}"
    if value >= 90:
        minutes = value / 60.0
        if abs(round(minutes) - minutes) < 0.01:
            minutes = float(round(minutes))
        return f"{minutes:g} minute{'s' if minutes >= 1.5 else ''}"
    if value >= 1:
        return f"{value:g} seconds"
    return f"{value:.2f} seconds"


def _parse_hotkey_loop_command(text: str) -> Optional[Dict[str, Any]]:
    lowered = text.lower().strip()
    if not lowered.startswith("press "):
        return None

    interval_match = re.search(
        r"(?i)\b(?:every|each|per)\s+(\d+(?:\.\d+)?)\s*([a-z]+)?",
        text,
    )
    if not interval_match:
        return None

    interval_value = interval_match.group(1)
    interval_unit = interval_match.group(2)
    interval_seconds = _parse_time_value(interval_value, interval_unit)
    if interval_seconds is None or interval_seconds <= 0:
        interval_seconds = None

    keys_segment = text[len("press ") : interval_match.start()].strip(" ,.;:")
    if not keys_segment:
        return None

    remainder = text[interval_match.end() :]

    duration_match = re.search(
        r"(?i)\b(?:for|during|over)\s+(\d+(?:\.\d+)?)\s*([a-z]+)?",
        remainder,
    )
    duration_seconds: Optional[float] = None
    if duration_match:
        duration_seconds = _parse_time_value(duration_match.group(1), duration_match.group(2))
        if duration_seconds is not None and duration_seconds <= 0:
            duration_seconds = None

    repeat_match = re.search(
        r"(?i)\b(?:repeat|repeats|times|x)\s*(\d+)",
        remainder,
    )
    repeat_count: Optional[int] = None
    if repeat_match:
        try:
            repeat_count = max(1, int(float(repeat_match.group(1))))
        except (TypeError, ValueError):
            repeat_count = None

    params: Dict[str, Any] = {"keys": keys_segment}
    desc_parts: List[str] = []
    if interval_seconds is not None:
        params["interval_seconds"] = interval_seconds
        desc_parts.append(f"every {interval_seconds:g} seconds")
    if duration_seconds is not None:
        params["duration_seconds"] = duration_seconds
        human = _format_seconds_brief_nlu(duration_seconds)
        if human:
            desc_parts.append(f"for {human}")
    if repeat_count is not None:
        params["repeat_count"] = repeat_count
        desc_parts.append(f"{repeat_count} times")

    desc_text = "on a loop" if not desc_parts else " ".join(desc_parts)
    response = f"Pressing {keys_segment} {desc_text}.".strip()
    return {
        "response": response,
        "actions": [
            {
                "type": "hotkey_loop",
                "parameters": params,
            }
        ],
    }


_HASHTAG_RE = re.compile(r"#([A-Za-z0-9_\-/]+)")


def _extract_hashtags(text: str) -> List[str]:
    if not text:
        return []
    return [match.group(1) for match in _HASHTAG_RE.finditer(text)]


def _split_task_body_and_due(body: str) -> Tuple[str, Optional[str]]:
    body = (body or "").strip()
    due = None
    match = re.search(r"\bby\s+(.+)$", body, flags=re.I)
    if match:
        due = match.group(1).strip()
        body = body[: match.start()].strip()
    else:
        timing = re.search(
            r"\b(tomorrow|tonight|today|next\s+[a-z]+|next\s+week|this\s+evening|this\s+afternoon)\b",
            body,
            flags=re.I,
        )
        if timing:
            due = timing.group(0)
    return body.strip().strip(",."), due


def _priority_hint_from_text(text: str) -> Optional[str]:
    low = text.lower()
    if any(word in low for word in ["urgent", "asap", "important", "critical"]):
        return "high"
    if any(word in low for word in ["someday", "later", "low priority", "chill"]):
        return "low"
    return None


def _strip_priority_tokens(text: str) -> str:
    text = re.sub(r"(?i)\burgent\b|\basap\b|\bimportant\b", "", text)
    text = re.sub(r"(?i)\blow priority\b|\bsomeday\b|\blater\b|\bchill\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_task_productivity_command(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return None
    tags = _extract_hashtags(stripped)

    def _build_add_plan(body: str, due_hint: Optional[str], priority_hint: Optional[str]) -> Dict[str, Any]:
        params: Dict[str, Any] = {"description": body.strip()}
        if due_hint:
            params["due"] = due_hint.strip()
        if priority_hint:
            params["priority"] = priority_hint
        if tags:
            params["tags"] = tags
        return {
            "response": f"Adding task: {body.strip()}",
            "actions": [{"type": "task_add", "parameters": params}],
        }

    add_patterns = [
        re.compile(r"(?i)^(?:add|create|new)\s+(?:a\s+)?(?:task|todo)\s+(?:to\s+)?(?P<body>.+)$"),
        re.compile(r"(?i)^(?:todo|task)\s*[:\-]\s*(?P<body>.+)$"),
        re.compile(r"(?i)^remind\s+me\s+to\s+(?P<body>.+)$"),
        re.compile(r"(?i)^remember\s+to\s+(?P<body>.+)$"),
        re.compile(r"(?i)^add\s+(?P<body>.+)\s+to\s+(?:my\s+)?(?:todo|task)\s+list$"),
    ]

    for pattern in add_patterns:
        match = pattern.match(stripped)
        if not match:
            continue
        body = match.group("body") or ""
        body, due = _split_task_body_and_due(body)
        priority = _priority_hint_from_text(body)
        body = _strip_priority_tokens(body)
        body = re.sub(r"#\w+", "", body).strip()
        if not body:
            continue
        return _build_add_plan(body, due, priority)

    low = stripped.lower()

    if re.search(r"\b(list|show|display|view|what)\b.*\b(tasks?|todos?)\b", low):
        params: Dict[str, Any] = {}
        if "done" in low or "completed" in low:
            params["include_completed"] = True
        return {
            "response": "Fetching your task list.",
            "actions": [{"type": "task_list", "parameters": params}],
        }

    complete_patterns = [
        re.compile(r"(?i)^(?:mark|make|set)\s+(?P<body>.+)\s+(?:done|complete)$"),
        re.compile(r"(?i)^(?:complete|finish|close)\s+(?:task|todo)?\s*(?P<body>.+)$"),
        re.compile(r"(?i)^check\s+off\s+(?P<body>.+)$"),
    ]
    for pattern in complete_patterns:
        match = pattern.match(stripped)
        if not match:
            continue
        body = match.group("body") or ""
        body = re.sub(r"\btask\b|\btodo\b", "", body, flags=re.I).strip()
        if not body:
            continue
        params = {"keyword": body, "title": body}
        return {
            "response": f"Marking {body} done.",
            "actions": [{"type": "task_complete", "parameters": params}],
        }

    if "clear" in low and ("done" in low or "completed" in low) and ("task" in low or "todo" in low):
        return {
            "response": "Clearing completed tasks.",
            "actions": [{"type": "task_clear_completed", "parameters": {}}],
        }

    return None


def _parse_focus_command(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    low = stripped.lower()
    if "focus" not in low and "pomodoro" not in low:
        return None

    duration_match = re.search(
        r"(?:for|lasting|last|run|set|start)\s+(\d+(?:\.\d+)?)\s*(seconds?|minutes?|hours?|secs?|mins?|hrs?|s|m|h)",
        stripped,
        flags=re.I,
    )
    duration_seconds: Optional[int] = None
    if duration_match:
        duration_seconds = int(_parse_time_value(duration_match.group(1), duration_match.group(2)) or 0)

    label_match = re.search(r"focus\s+(?:on\s+)?([A-Za-z0-9'\- ]{3,60})", stripped, flags=re.I)
    label = label_match.group(1).strip() if label_match else None

    if any(word in low for word in ["start", "begin", "kick", "launch", "initiate"]) or "pomodoro" in low:
        params: Dict[str, Any] = {}
        if label:
            params["label"] = label
        if duration_seconds:
            params["seconds"] = duration_seconds
        elif "pomodoro" in low:
            params["minutes"] = 25
        response = f"Starting focus session{f' for {label}' if label else ''}."
        return {"response": response, "actions": [{"type": "focus_start", "parameters": params}]}

    if any(word in low for word in ["stop", "cancel", "end", "finish"]) and "focus" in low:
        params = {"canceled": "cancel" in low}
        return {
            "response": "Stopping the focus timer.",
            "actions": [{"type": "focus_stop", "parameters": params}],
        }

    if any(word in low for word in ["status", "left", "remaining", "time"]):
        if "focus" in low or "timer" in low:
            return {
                "response": "Checking focus timer status.",
                "actions": [{"type": "focus_status", "parameters": {}}],
            }

    return None


def _parse_note_command(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    low = stripped.lower()
    if low.startswith("remember to"):
        return None

    patterns = [
        re.compile(r"(?i)^(?:note|remember|save|capture)\s+(?:that\s+)?(?P<body>.+)$"),
        re.compile(r"(?i)^quick\s+note\s*:?\s*(?P<body>.+)$"),
        re.compile(r"(?i)^log\s+(?P<body>.+)$"),
        re.compile(r"(?i)^jot\s+down\s+(?P<body>.+)$"),
    ]
    for pattern in patterns:
        match = pattern.match(stripped)
        if not match:
            continue
        body = match.group("body") or ""
        body = re.sub(r"#\w+", "", body).strip()
        if not body:
            continue
        params: Dict[str, Any] = {"text": body}
        tags = _extract_hashtags(stripped)
        if tags:
            params["tags"] = tags
        return {
            "response": f"Capturing note: {body}",
            "actions": [{"type": "quick_note", "parameters": params}],
        }
    return None


def _parse_daily_briefing_command(text: str) -> Optional[Dict[str, Any]]:
    low = text.lower()
    triggers = [
        "daily briefing",
        "morning briefing",
        "daily update",
        "daily summary",
        "status update",
        "how's my day",
        "plan my day",
    ]
    if any(trigger in low for trigger in triggers):
        return {
            "response": "Preparing your daily briefing.",
            "actions": [{"type": "daily_briefing", "parameters": {}}],
        }
    return None


def _parse_cleanup_command(text: str) -> Optional[Dict[str, Any]]:
    low = text.lower()
    keywords = [
        "clean temp",
        "clean the temp",
        "clear temp",
        "delete temp",
        "clean junk",
        "clear junk",
        "remove junk",
        "cleanup junk",
        "cleanup pc",
        "clean my pc",
        "empty temp folder",
        "%temp%",
        "temp files",
    ]
    if any(term in low for term in keywords):
        return {
            "response": "Cleaning temporary files and skipping anything locked.",
            "actions": [
                {
                    "type": "cleanup_temp",
                    "parameters": {"natural": text},
                }
            ],
        }
    return None


def _parse_habit_command(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    low = stripped.lower()
    if "habit" not in low:
        return None

    tags = _extract_hashtags(stripped)

    def _extract_name() -> Optional[str]:
        match = re.search(r"(?i)habit(?:\s+(?:called|named))?\s+([A-Za-z0-9' ]{3,60})", stripped)
        if match:
            return match.group(1).strip()
        match = re.search(r"(?i)(?:log|track|start|create|add)\s+([A-Za-z0-9' ]{2,50})\s+habit", stripped)
        if match:
            return match.group(1).strip()
        return None

    def _target_from_text() -> Optional[int]:
        match = re.search(r"(\d{1,2})\s*(?:times?|x)\s*(?:a\s+)?(?:day|daily|each\s+day)", stripped, flags=re.I)
        if match:
            try:
                return max(1, int(match.group(1)))
            except Exception:
                return None
        return None

    if any(word in low for word in ["log", "logged", "mark", "check in", "check-in", "record"]) and "habit" in low:
        name = _extract_name()
        if not name:
            # Handle pattern "log water"
            match = re.search(r"(?i)(?:log|record|mark)\s+([A-Za-z0-9' ]{2,40})", stripped)
            if match:
                name = match.group(1).strip()
        if not name:
            return None
        params: Dict[str, Any] = {"name": name}
        note_match = re.search(r"(?i)(?:because|note|details?)\s+(.+)$", stripped)
        if note_match:
            params["note"] = note_match.group(1).strip()
        return {
            "response": f"Logging {name} habit.",
            "actions": [{"type": "habit_log", "parameters": params}],
        }

    if any(word in low for word in ["status", "progress", "streak", "report", "show"]):
        name = _extract_name()
        params: Dict[str, Any] = {}
        if name:
            params["name"] = name
        day_match = re.search(r"(?i)last\s+(\d{1,2})\s+days?", stripped)
        if day_match:
            params["days"] = int(day_match.group(1))
        return {
            "response": "Checking habit stats.",
            "actions": [{"type": "habit_status", "parameters": params}],
        }

    if any(word in low for word in ["reset", "clear", "forget"]) and "habit" in low:
        name = _extract_name()
        if not name:
            return None
        return {
            "response": f"Clearing history for {name}.",
            "actions": [{"type": "habit_reset", "parameters": {"name": name}}],
        }

    if any(word in low for word in ["create", "start", "add", "track", "begin"]):
        name = _extract_name()
        if not name:
            # pattern "create a habit to drink water"
            match = re.search(r"(?i)habit\s+to\s+(.+)", stripped)
            if match:
                name = match.group(1).split(" to ")[0].strip().title()
        if not name:
            return None
        params: Dict[str, Any] = {"name": name}
        if tags:
            params["tags"] = tags
        desc_match = re.search(r"(?i)to\s+(.+)$", stripped)
        if desc_match:
            params["description"] = desc_match.group(1).strip()
        target = _target_from_text()
        if target:
            params["target_per_day"] = target
        return {
            "response": f"Tracking habit {name}.",
            "actions": [{"type": "habit_create", "parameters": params}],
        }

    return None


def _parse_routine_command(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    low = stripped.lower()
    if "routine" not in low:
        return None

    def _extract_name(default_pattern: str = r"routine\s+(?:called|named)?\s*([A-Za-z0-9' ]{3,60})") -> Optional[str]:
        match = re.search(default_pattern, stripped, flags=re.I)
        if match:
            return match.group(1).strip()
        match = re.search(r"(?i)(?:run|start|delete|remove)\s+([A-Za-z0-9' ]{3,60})\s+routine", stripped)
        if match:
            return match.group(1).strip()
        return None

    if any(word in low for word in ["list", "show", "what", "which"]) and "routine" in low:
        return {
            "response": "Listing saved routines.",
            "actions": [{"type": "routine_list", "parameters": {}}],
        }

    if any(word in low for word in ["delete", "remove", "forget"]) and "routine" in low:
        name = _extract_name()
        if not name:
            return None
        return {
            "response": f"Deleting routine {name}.",
            "actions": [{"type": "routine_delete", "parameters": {"name": name}}],
        }

    if any(word in low for word in ["run", "start", "execute", "launch", "play"]) and "routine" in low:
        name = _extract_name()
        if not name:
            return None
        return {
            "response": f"Running routine {name}.",
            "actions": [{"type": "routine_run", "parameters": {"name": name}}],
        }

    if any(word in low for word in ["create", "build", "make", "design", "save"]):
        name = _extract_name()
        if not name:
            # e.g. "create morning routine"
            match = re.search(r"(?i)create\s+([A-Za-z0-9' ]{3,40})\s+routine", stripped)
            if match:
                name = match.group(1).strip()
        if not name:
            return None
        instructions = stripped
        return {
            "response": f"Saving routine {name}.",
            "actions": [
                {
                    "type": "routine_create",
                    "parameters": {"name": name, "instructions": instructions},
                }
            ],
        }

    return None


def _parse_system_health_command(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    low = stripped.lower()
    keywords = [
        "system health",
        "pc health",
        "diagnostic",
        "diagnostics",
        "cpu usage",
        "memory usage",
        "ram usage",
        "performance",
        "resource monitor",
        "system status",
        "temperature",
    ]
    if not any(term in low for term in keywords):
        return None

    wants_watch = any(term in low for term in ["watch", "monitor", "over time", "graph", "track"])
    duration_match = re.search(r"(?i)for\s+(\d+(?:\.\d+)?)\s*(seconds?|minutes?|mins?|hours?|hrs?)", stripped)
    interval_match = re.search(r"(?i)every\s+(\d+(?:\.\d+)?)\s*(seconds?|minutes?|mins?|hours?|hrs?)", stripped)
    if wants_watch:
        params: Dict[str, Any] = {}
        if duration_match:
            params["duration"] = _parse_time_value(duration_match.group(1), duration_match.group(2))
        if interval_match:
            params["interval"] = _parse_time_value(interval_match.group(1), interval_match.group(2))
        return {
            "response": "Monitoring system health over time.",
            "actions": [{"type": "system_health_watch", "parameters": params}],
        }

    params: Dict[str, Any] = {}
    samples_match = re.search(r"(?i)(\d+)\s+samples", stripped)
    if samples_match:
        params["samples"] = int(samples_match.group(1))
    return {
        "response": "Collecting a quick health snapshot.",
        "actions": [{"type": "system_health", "parameters": params}],
    }


def _parse_clipboard_command(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    low = stripped.lower()
    if not any(keyword in low for keyword in ["clipboard", "snippet", "snippets", "history"]):
        return None

    tags = _extract_hashtags(stripped)
    quote_match = re.search(r"\"([^\"]{3,200})\"", stripped)
    quoted_text = quote_match.group(1).strip() if quote_match else None

    if any(term in low for term in ["save", "store", "remember", "capture"]):
        params: Dict[str, Any] = {}
        if quoted_text:
            params["text"] = quoted_text
        if tags:
            params["tags"] = tags
        return {
            "response": "Saving clipboard snippet.",
            "actions": [{"type": "clipboard_save", "parameters": params}],
        }

    if any(term in low for term in ["list", "show", "recent", "history"]):
        limit_match = re.search(r"(?i)last\s+(\d{1,2})", stripped)
        params: Dict[str, Any] = {}
        if limit_match:
            params["limit"] = int(limit_match.group(1))
        return {
            "response": "Listing clipboard history.",
            "actions": [{"type": "clipboard_list", "parameters": params}],
        }

    if any(term in low for term in ["search", "find", "look for"]):
        match = re.search(r"(?i)(?:for|about)\s+([A-Za-z0-9#' ]{2,60})", stripped)
        keyword = match.group(1).strip() if match else quoted_text
        if not keyword:
            keyword = stripped
        return {
            "response": f"Searching snippets for {keyword}.",
            "actions": [{"type": "clipboard_search", "parameters": {"keyword": keyword}}],
        }

    if any(term in low for term in ["restore", "copy back", "bring", "paste"]):
        identifier_match = re.search(r"(?i)(?:snippet|entry|item)\s+(\d{1,3}|#[A-Za-z0-9_]+)", stripped)
        identifier = quoted_text or (identifier_match.group(1) if identifier_match else None)
        params: Dict[str, Any] = {}
        if identifier:
            params["id"] = identifier.strip("#")
        return {
            "response": "Restoring clipboard snippet.",
            "actions": [{"type": "clipboard_restore", "parameters": params}],
        }

    return None


def _autocorrect_text(text: str) -> str:
    """Return a lightly corrected version of text for better parsing."""
    if not text:
        return text

    text = text.strip()
    phrase_map = {
        "baterry saver": "battery saver",
        "bluetooh": "bluetooth",
        "blutooth": "bluetooth",
        "wi fi": "wifi",
    }

    lowered = text.lower()
    for src, dst in phrase_map.items():
        if src in lowered:
            lowered = re.sub(re.escape(src), dst, lowered)

    tokens = re.split(r"(\s+|[^\w'])", lowered)
    out_tokens: List[str] = []
    for tok in tokens:
        if not tok or tok.isspace() or re.match(r"[^\w']", tok):
            out_tokens.append(tok)
            continue

        if len(tok) <= 3 or tok.isdigit():
            out_tokens.append(tok)
            continue

        candidates = [t for t in COMMON_TERMS if " " not in t]
        match = difflib.get_close_matches(tok, candidates, n=1, cutoff=0.8)
        if match:
            out_tokens.append(match[0])
        else:
            out_tokens.append(tok)

    return "".join(out_tokens)


def _clamp_percent(value: int) -> int:
    return max(0, min(100, value))


def _extract_level(text: str, keywords: List[str]) -> Optional[int]:
    for m in re.finditer(r"(\d{1,3})\s*(?:%|percent|per\s*cent|pc)\b", text):
        val = int(m.group(1))
        window = text[max(0, m.start() - 20): m.end() + 20]
        if any(k in window for k in keywords):
            return _clamp_percent(val)

    for m in re.finditer(r"(?:to|at|make|set|keep|about|around)\s*(\d{1,3})", text):
        val = int(m.group(1))
        return _clamp_percent(val)

    numbers = re.findall(r"\b(\d{1,3})\b", text)
    if len(numbers) == 1:
        return _clamp_percent(int(numbers[0]))

    return None


def _level_from_words(text: str, kind: str) -> Optional[int]:
    if kind == "brightness":
        if _contains_any(text, ["max", "maximum", "full", "brightest"]):
            return 100
        if _contains_any(text, ["min", "minimum", "zero", "darkest"]):
            return 0
        if _contains_any(text, ["half", "medium", "mid", "fifty"]):
            return 50
    if kind == "volume":
        if _contains_any(text, ["max", "maximum", "full", "loudest"]):
            return 100
        if _contains_any(text, ["min", "minimum", "zero", "quietest"]):
            return 0
        if _contains_any(text, ["half", "medium", "mid", "fifty"]):
            return 50
    return None


def _parse_desired_state(
    text: str,
    keywords: Optional[List[str]] = None,
    extra_positive: Optional[List[str]] = None,
    extra_negative: Optional[List[str]] = None,
    allow_toggle: bool = True,
) -> Optional[str]:
    base_positive = [r"\bturn\b.{0,20}\bon\b", r"\bswitch\b.{0,20}\bon\b", r"\benable\b", r"\bstart\b", r"\bactivate\b"]
    base_negative = [r"\bturn\b.{0,20}\boff\b", r"\bswitch\b.{0,20}\boff\b", r"\bdisable\b", r"\bstop\b", r"\bdeactivate\b"]
    
    if extra_positive:
        for term in extra_positive:
            if term:
                if " " in term:
                    base_positive.append(re.escape(term))
                else:
                    base_positive.append(r"\b" + re.escape(term) + r"\b")
    
    if extra_negative:
        for term in extra_negative:
            if term:
                if " " in term:
                    base_negative.append(re.escape(term))
                else:
                    base_negative.append(r"\b" + re.escape(term) + r"\b")
    
    for pattern in base_negative:
        if re.search(pattern, text):
            return "off"
    
    for pattern in base_positive:
        if re.search(pattern, text):
            return "on"
    
    if keywords:
        for kw in keywords:
            esc = re.escape(kw)
            if re.search(rf"{esc}\b.{0,10}\bon\b", text):
                return "on"
            if re.search(rf"{esc}\b.{0,10}\boff\b", text):
                return "off"
    
    if allow_toggle:
        for pattern in [r"\btoggle\b", r"\bflip\b", r"\bchange\b"]:
            if re.search(pattern, text):
                return "toggle"
    
    return None


def _split_recipients(text: str) -> List[str]:
    parts = re.split(r"\s*,\s*|\s+(?:and|aur)\s+|\s*&\s*", text.strip(), flags=re.IGNORECASE)
    cleaned: List[str] = []
    for part in parts:
        token = part.strip()
        if not token:
            continue
        token = re.sub(r"(?i)\b(to|ko|ke\s+liye)\b$", "", token).strip(" .,:;-\n")
        if token:
            cleaned.append(token)
    return cleaned


def _generate_ai_message(topic: str, memory: Optional[ConversationMemory] = None) -> str:
    prompt = f"Write a short, warm message for: {topic}. Keep to 1-2 sentences."
    try:
        plan = _llm_plan(prompt, memory=memory)
        if isinstance(plan, dict):
            resp = plan.get("response") or ""
            if resp and resp.strip():
                return " ".join(resp.strip().split())
    except Exception:
        pass
    
    return f"Hi — here's a message: {topic}"


def _extract_site(segment: str) -> tuple[Optional[str], str]:
    site_match = re.search(r"(?i)\b(on|in)\s+([a-z0-9.-]+)(?:\s+website|\s+site)?$", segment)
    if not site_match:
        return None, segment.strip()
    site = site_match.group(2).lower().strip()
    if site in {"first", "firstlink", "first-result"}:
        site = None
    query = segment[: site_match.start()].strip(" ,")
    return site, query if query else segment.strip()


def _parse_browser_search(original_text: str) -> Optional[Dict[str, Any]]:
    text = original_text.strip()
    if not text:
        return None

    lowered = text.lower()

    # Remove trailing instruction about opening the first link if present
    open_first = False
    if re.search(r"(?i)(?:and\s+)?(?:click|open)\s+(?:on\s+)?first\s+link", lowered):
        open_first = True
        text = re.sub(
            r"(?i)[,\s]*(?:and\s+)?(?:click|open)\s+(?:on\s+)?first\s+link",
            "",
            text,
        ).strip()
        lowered = text.lower()

    # Plain "search ..." commands
    if lowered.startswith("search "):
        segment = text[7:].strip()
        site, query = _extract_site(segment)
        params: Dict[str, Any] = {"query": query}
        if site:
            params["site"] = site
        if open_first or site:
            params["open_first"] = True
        return {
            "response": f"Searching for {query}.",
            "action": {"type": "search", "parameters": params},
        }

    # "open <browser> and search ..."
    for browser in sorted(BROWSER_KEYWORDS, key=len, reverse=True):
        prefix = f"open {browser}"
        if not lowered.startswith(prefix):
            continue
        remainder = text[len(prefix):].strip()
        if remainder.lower().startswith("and "):
            remainder = remainder[4:].strip()
        if not remainder.lower().startswith("search "):
            continue
        query_segment = remainder[7:].strip()
        site, query = _extract_site(query_segment)
        params = {"browser": browser, "query": query}
        if site:
            params["site"] = site
        if open_first or site:
            params["open_first"] = True
        return {
            "response": f"Searching for {query} in {browser}.",
            "action": {"type": "search", "parameters": params},
        }

    # "open <topic> in <browser>"
    for browser in sorted(BROWSER_KEYWORDS, key=len, reverse=True):
        token = f" in {browser}"
        if token not in lowered:
            continue
        if not lowered.startswith("open "):
            continue
        idx = lowered.rfind(token)
        if idx <= 5:
            continue
        topic = text[5:idx].strip(" ,")
        if not topic:
            continue
        params = {"browser": browser, "query": topic, "open_first": True}
        return {
            "response": f"Searching for {topic} in {browser}.",
            "action": {"type": "search", "parameters": params},
        }

    # "open <topic> website" or "open <topic> site"
    if lowered.startswith("open ") and (" website" in lowered or " site" in lowered):
        if re.search(r"(?i)\bbluetooth\b|\bsettings\b", lowered):
            return None
        topic = re.sub(r"(?i)\b(open)\s+", "", text, count=1).strip()
        topic = re.sub(r"(?i)\b(website|site)\b", "", topic).strip(" ,")
        if not topic:
            return None
        params = {"query": topic, "open_first": True}
        return {
            "response": f"Opening results for {topic}.",
            "action": {"type": "search", "parameters": params},
        }

    # Generic "open <topic>" fallback if not an app alias
    if lowered.startswith("open "):
        rest = text[5:].strip()
        rest_lower = rest.lower()
        first_token = rest_lower.split()[0] if rest_lower else ""
        # Avoid hijacking WhatsApp flows like "open whatsapp and send ..."
        if first_token == "whatsapp":
            return None
        if first_token not in APP_ALIAS_MAP and first_token not in {"bluetooth", "settings"}:
            params = {"query": rest, "open_first": True}
            return {
                "response": f"Searching for {rest}.",
                "action": {"type": "search", "parameters": params},
            }

    return None


def _parse_quick_setting(low: str) -> Optional[Dict[str, Any]]:
    for canonical, aliases in QUICK_SETTING_ALIASES.items():
        if not any(alias in low for alias in aliases):
            continue
        state = _parse_desired_state(low, keywords=aliases, allow_toggle=True)
        if state is None:
            state = "toggle"
        if state == "toggle" and "on" in low and "off" not in low:
            state = "on"
        response = {
            "on": f"Turning {canonical} on.",
            "off": f"Turning {canonical} off.",
            "toggle": f"Toggling {canonical}.",
        }.get(state, f"Toggling {canonical}.")
        params = {"name": canonical, "state": state}
        return {"response": response, "parameters": params}
    return None


def _extract_message_and_contacts(text: str) -> Optional[Dict[str, Any]]:
    working = text.strip()
    close_whatsapp = False
    if re.search(r"(?i)\bclose\s+whatsapp\b", working):
        close_whatsapp = True
        working = re.sub(r"(?i)\band\s+(?:then\s+)?close\s+whatsapp\b", "", working).strip()

    explicit_open = False
    if re.match(r"(?i)^open\s+whatsapp", working):
        explicit_open = True
        working = re.sub(r"(?i)^open\s+whatsapp\s*(?:and\s+)?", "", working, count=1).strip()

    patterns = [
        r"(?i)(?:send|message|msg|bhej|bhejo)\s+(.+?)\s+(?:to|for)\s+(.+)$",
        r"(?i)(?:send|message|msg|bhej|bhejo)\s+(.+?)\s+(.+)$",
    ]

    message = None
    contacts_raw = None
    for pat in patterns:
        match = re.match(pat, working)
        if match:
            message = match.group(1).strip()
            contacts_raw = match.group(2).strip()
            break

    if not message or not contacts_raw:
        return None

    contacts_raw = re.sub(r"(?i)\bon\s+whatsapp\b", "", contacts_raw)
    contacts_raw = re.sub(r"(?i)\b(?:aur|and)\s+", ", ", contacts_raw)
    contacts_raw = contacts_raw.strip(" .,:;\n")
    contacts: List[str] = []
    seen = set()
    for part in _split_recipients(contacts_raw):
        contact = _normalize_contact_name(part)
        if not contact:
            continue
        key = contact.lower()
        if key not in seen:
            seen.add(key)
            contacts.append(contact)

    if not contacts:
        return None

    return {
        "message": message,
        "contacts": contacts,
        "close": close_whatsapp,
        "open_first": explicit_open,
    }


def _build_whatsapp_actions(message: str, contacts: List[str], close_app: bool) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = [
        {"type": "open_app_start", "parameters": {"name": "whatsapp"}}
    ]
    for contact in contacts:
        actions.append(
            {
                "type": "whatsapp_send",
                "parameters": {
                    "contact": contact,
                    "message": message,
                },
            }
        )
    if close_app:
        actions.append({"type": "close_app", "parameters": {"name": "whatsapp"}})
    return actions


def _parse_whatsapp_call_command(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    low = stripped.lower()
    if "whatsapp" not in low or "call" not in low:
        return None

    message: Optional[str] = None
    call_segment = stripped

    msg_match = re.search(
        r"(?i)\band\s+(?:tell|say|inform|let\s+(?:them|him|her)\s+know)\s+(?:that\s+)?(.+)$",
        stripped,
    )
    if msg_match:
        message = msg_match.group(1).strip(" .,:;\n")
        call_segment = stripped[: msg_match.start()].strip()

    contact: Optional[str] = None
    patterns = [
        r"(?i)call\s+([A-Za-z0-9' ]{2,60})\s+(?:on|via|over|using)\s+whatsapp",
        r"(?i)whatsapp\s+call\s+(?:to\s+)?([A-Za-z0-9' ]{2,60})",
        r"(?i)on\s+whatsapp\s+call\s+(?:to\s+)?([A-Za-z0-9' ]{2,60})",
        r"(?i)call\s+([A-Za-z0-9' ]{2,60})\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, call_segment)
        if match:
            contact = match.group(1).strip(" .,:;")
            break

    if not contact:
        return None

    contact = _normalize_contact_name(contact)
    if not contact:
        return None

    params: Dict[str, Any] = {"contact": contact}
    response = f"Calling {contact} on WhatsApp."
    action_type = "whatsapp_call"

    if message:
        params["message"] = message
        action_type = "whatsapp_call_and_tell"
        response = f"Calling {contact} on WhatsApp and saying '{message}'."

    return {"response": response, "actions": [{"type": action_type, "parameters": params}]}


def _parse_whatsapp_voice_message_command(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    low = stripped.lower()
    if not re.search(r"(?i)voice\s+(message|note|recording)|audio\s+(message|note)", low):
        return None
    if not any(keyword in low for keyword in ["send", "record", "bhej", "make", "create"]):
        return None

    message: Optional[str] = None
    command_segment = stripped

    msg_tail = re.search(r"(?i)\b(?:saying|that|with)\s+(.+)$", stripped)
    if msg_tail:
        message = msg_tail.group(1).strip(" .,:;\n")
        command_segment = stripped[: msg_tail.start()].strip()

    quoted = re.search(r"['\"]([^'\"]{2,200})['\"]", stripped)
    if not message and quoted:
        message = quoted.group(1).strip(" .,:;\n")

    prefix_pattern = re.search(
        r"(?i)(?:send|bhej|record|make|create)\s+(.+?)\s+(?:voice|audio)\s+(?:message|note|recording|msg)\s+(?:to|for)\s+(.+)$",
        stripped,
    )
    contact_section: Optional[str] = None
    if prefix_pattern:
        if not message:
            message = prefix_pattern.group(1).strip(" .,:;\n")
        contact_section = prefix_pattern.group(2).strip()
    else:
        patterns = [
            r"(?i)(?:send|bhej|record|make|create)\s+(?:a\s+)?(?:voice|audio)\s+(?:message|note|recording|msg)\s+(?:to|for)\s+(.+)$",
            r"(?i)(?:send|bhej|record|make|create)\s+(?:a\s+)?(?:voice|audio)\s+(?:message|note|recording|msg)\s+(.+)$",
        ]
        for pat in patterns:
            mm = re.search(pat, command_segment)
            if mm:
                contact_section = mm.group(1).strip(" .,:;\n")
                break

    if not contact_section:
        return None

    contact_section = re.sub(r"(?i)\bon\s+whatsapp\b", "", contact_section)
    contact_section = re.sub(r"(?i)\bvia\s+whatsapp\b", "", contact_section)
    contact_section = contact_section.strip()

    contacts: List[str] = []
    seen: Set[str] = set()
    for part in _split_recipients(contact_section):
        name = _normalize_contact_name(part)
        if not name:
            continue
        key = name.lower()
        if key not in seen:
            seen.add(key)
            contacts.append(name)

    if not contacts:
        return None

    if not message:
        return None

    params: Dict[str, Any] = {
        "contact": contacts[0],
        "message": message,
        "natural": text,
    }
    response = f"Recording a WhatsApp voice note for {contacts[0]} and saying '{message}'."
    return {"response": response, "actions": [{"type": "whatsapp_voice_message", "parameters": params}]}


def interpret(user_text: str, memory: Optional[ConversationMemory] = None) -> Dict[str, Any]:
    user_text = (user_text or "").strip()
    if not user_text:
        return {"response": "", "actions": []}

    def _clean(text: str) -> str:
        t = text.strip()
        t = re.sub(r"^(you\s*:\s*)", "", t, flags=re.I)
        t = re.sub(r"^(assistant|buddy|hey|hello|hi)[,\s]+", "", t, flags=re.I)
        t = re.sub(r"\b(please|kripya|kindly)\b[ ,]*", "", t, flags=re.I)
        t = re.sub(r"\bblutooth\b|\bbluetoth\b|\bbluetoothh\b", "bluetooth", t, flags=re.I)
        t = re.sub(r"\bwi\s*fi\b|\bwifi\b", "wifi", t, flags=re.I)
        # Common Hinglish -> English normalizations
        # Map common transliterated Hindi words to English verbs/phrases to help parsing
        t = re.sub(r"\bchalu\b|\bchalu\s+karo\b", "turn on", t, flags=re.I)
        t = re.sub(r"\bband\b|\bbandh\b|\bband\s+karo\b", "turn off", t, flags=re.I)
        t = re.sub(r"\bkar\b|\bkaro\b|\bkrna\b|\bkrna\b", "", t, flags=re.I)
        t = re.sub(r"\baur\b", "and", t, flags=re.I)
        t = re.sub(r"\bbhej\b|\bsend\b", "send", t, flags=re.I)
        return t.strip()

    text = _clean(user_text)
    
    # --- FIRST: Multi-task command parsing (compound commands) ---
    # Check for compound commands BEFORE any other parsers to avoid partial matching
    if _is_multi_task and _parse_multi_task:
        try:
            if _is_multi_task(text):
                multi_result = _parse_multi_task(text)
                if multi_result and multi_result.get("parameters", {}).get("actions"):
                    return {
                        "response": f"I'll handle {multi_result['parameters']['total_actions']} tasks for you.",
                        "actions": [multi_result],
                    }
        except Exception as exc:
            print(f"[NLU] Multi-task parser error: {exc}")

    # --- Browser search parsing (compound commands like "open chrome and search X") ---
    # Must run BEFORE spaCy to catch compound browser commands correctly
    browser = _parse_browser_search(text)
    if browser:
        act = browser.get("action") or {}
        action = act if isinstance(act, dict) else {}
        if action:
            return {"response": browser.get("response", ""), "actions": [action]}

    # Try spaCy NLU if available (after multi-task and browser-search checks)
    if _spacy_interpret:
        try:
            spacy_res = _spacy_interpret(text)
            if spacy_res and spacy_res.get("actions"):
                return spacy_res
        except Exception as exc:
            print(f"[NLU] SpaCy Model Error: {exc}")
            # Continue to other parsers

    # --- NEW: Enhanced Spotify controls ---
    if _parse_spotify_command:
        try:
            spotify_result = _parse_spotify_command(text)
            if spotify_result and spotify_result.get("type"):
                return {
                    "response": spotify_result.get("response", ""),
                    "actions": [spotify_result],
                }
        except Exception as exc:
            print(f"[NLU] Spotify parser error: {exc}")

    # --- NEW: Scheduled/timed task parsing ---
    if _parse_scheduled_task:
        try:
            scheduled_result = _parse_scheduled_task(text)
            if scheduled_result and scheduled_result.get("type"):
                return {
                    "response": scheduled_result.get("response", "Scheduling your task."),
                    "actions": [scheduled_result],
                }
        except Exception as exc:
            print(f"[NLU] Scheduled task parser error: {exc}")

    # --- NEW: Enhanced WhatsApp multi-recipient parsing ---
    if _parse_whatsapp_enhanced:
        try:
            wa_result = _parse_whatsapp_enhanced(text)
            if wa_result and wa_result.get("type"):
                return {
                    "response": wa_result.get("response", "Sending message."),
                    "actions": [wa_result],
                }
        except Exception as exc:
            print(f"[NLU] WhatsApp enhanced parser error: {exc}")

    try:
        corrected = _autocorrect_text(text)
        if corrected and corrected != text.lower():
            text = corrected
    except Exception:
        pass
    
    low = text.lower()

    task_plan = _parse_task_productivity_command(text)
    if task_plan:
        return task_plan

    note_plan = _parse_note_command(text)
    if note_plan:
        return note_plan

    focus_plan = _parse_focus_command(text)
    if focus_plan:
        return focus_plan

    briefing_plan = _parse_daily_briefing_command(text)
    if briefing_plan:
        return briefing_plan

    cleanup_plan = _parse_cleanup_command(text)
    if cleanup_plan:
        return cleanup_plan

    habit_plan = _parse_habit_command(text)
    if habit_plan:
        return habit_plan

    routine_plan = _parse_routine_command(text)
    if routine_plan:
        return routine_plan

    health_plan = _parse_system_health_command(text)
    if health_plan:
        return health_plan

    clipboard_plan = _parse_clipboard_command(text)
    if clipboard_plan:
        return clipboard_plan

    whatsapp_call_plan = _parse_whatsapp_call_command(text)
    if whatsapp_call_plan:
        return whatsapp_call_plan

    whatsapp_voice_plan = _parse_whatsapp_voice_message_command(text)
    if whatsapp_voice_plan:
        return whatsapp_voice_plan

    # Screen describe (include UK spelling)
    if low in {"describe screen", "describe my screen", "screen", "screenshot", "analyze screen", "analyse screen"}:
        return {"response": "Describing your screen.", "actions": [{"type": "screen_describe", "parameters": {}}]}

    # Bluetooth settings
    if re.search(r"\b(open|show)\b.*\bbluetooth\b.*\bsettings\b", low):
        return {"response": "Opening Bluetooth settings.", "actions": [{"type": "settings", "parameters": {"name": "bluetooth"}}]}

    # Power controls
    if re.search(r"\b(shut\s*down|shutdown)\b", low):
        return {"response": "Shutting down.", "actions": [{"type": "power", "parameters": {"mode": "shutdown"}}]}
    if re.search(r"\b(restart|reboot)\b", low):
        return {"response": "Restarting.", "actions": [{"type": "power", "parameters": {"mode": "restart"}}]}
    if re.search(r"\bhibernate\b", low):
        return {"response": "Hibernating.", "actions": [{"type": "power", "parameters": {"mode": "hibernate"}}]}
    if re.search(r"\bsleep\b", low):
        return {"response": "Going to sleep.", "actions": [{"type": "power", "parameters": {"mode": "sleep"}}]}
    if re.search(r"\block\b", low) and ("pc" in low or "computer" in low or "system" in low):
        return {"response": "Locking.", "actions": [{"type": "power", "parameters": {"mode": "lock"}}]}

    # Volume
    volume_terms = ["volume", "sound", "speaker", "audio", "awaz"]
    if _contains_any(low, volume_terms):
        if re.search(r"\b(mute|silent|silence|quiet)\b", low):
            return {"response": "Muting volume.", "actions": [{"type": "volume", "parameters": {"mute": True}}]}
        if re.search(r"\b(unmute|awaz chalu|sound on)\b", low):
            return {"response": "Unmuting volume.", "actions": [{"type": "volume", "parameters": {"mute": False}}]}
        
        pct = _extract_level(low, volume_terms)
        if pct is None:
            pct = _level_from_words(low, "volume")
        if pct is not None:
            return {"response": f"Setting volume to {pct}%.", "actions": [{"type": "volume", "parameters": {"percent": pct}}]}
        
        # Hinglish synonyms: 'kam' (less), 'ghatao' (decrease), 'badhao' (increase)
        if re.search(r"\b(badhao|zyada|zyaada)\b", low):
            return {"response": "Turning volume up.", "actions": [{"type": "volume", "parameters": {"delta": 10}}]}
        if re.search(r"\b(kam|ghatao|ghataao|thoda\s+kam)\b", low):
            return {"response": "Turning volume down.", "actions": [{"type": "volume", "parameters": {"delta": -10}}]}

        if _contains_any(low, ["increase", "raise", "up", "higher", "louder", "boost"]):
            return {"response": "Turning volume up.", "actions": [{"type": "volume", "parameters": {"delta": 10}}]}
        if _contains_any(low, ["decrease", "lower", "reduce", "down", "softer", "less"]):
            return {"response": "Turning volume down.", "actions": [{"type": "volume", "parameters": {"delta": -10}}]}

    # Brightness
    brightness_terms = ["brightness", "bright", "brighten", "brighter", "dim", "darker"]
    if _contains_any(low, brightness_terms):
        pct = _extract_level(low, brightness_terms)
        if pct is None:
            pct = _level_from_words(low, "brightness")
        if pct is not None:
            return {"response": f"Setting brightness to {pct}%.", "actions": [{"type": "brightness", "parameters": {"level": pct}}]}
        
        if _contains_any(low, ["increase", "raise", "up", "brighten"]):
            return {"response": "Increasing brightness.", "actions": [{"type": "brightness", "parameters": {"level": 80}}]}
        if _contains_any(low, ["decrease", "lower", "reduce", "down", "dim"]):
            return {"response": "Decreasing brightness.", "actions": [{"type": "brightness", "parameters": {"level": 30}}]}

    # WiFi
    wifi_terms = ["wifi", "wireless", "network", "internet"]
    if _contains_any(low, wifi_terms):
        state = _parse_desired_state(low, keywords=wifi_terms, extra_positive=["connect"], extra_negative=["disconnect"])
        if state:
            say = f"Turning WiFi {state}."
            return {"response": say, "actions": [{"type": "wifi", "parameters": {"state": state}}]}

    # Bluetooth
    bt_terms = ["bluetooth", "bt"]
    if _contains_any(low, bt_terms):
        state = _parse_desired_state(low, keywords=bt_terms, extra_positive=["connect"], extra_negative=["disconnect"])
        if state:
            say = f"Turning Bluetooth {state}."
            return {"response": say, "actions": [{"type": "bluetooth", "parameters": {"state": state}}]}

    qs_toggle = _parse_quick_setting(low)
    if qs_toggle:
        return {
            "response": qs_toggle.get("response", ""),
            "actions": [
                {
                    "type": "qs_toggle",
                    "parameters": qs_toggle.get("parameters", {}),
                }
            ],
        }

    loop_plan = _parse_hotkey_loop_command(text)
    if loop_plan is not None:
        return loop_plan

    # Browser search parsing (advanced variants)
    browser = _parse_browser_search(text)
    if browser:
        act = browser.get("action") or {}
        action = act if isinstance(act, dict) else {}
        return {"response": browser.get("response", ""), "actions": [action] if action else []}

    # Uninstall
    m = re.search(r"\b(uninstall|remove|delete)\b\s+(?:the\s+)?(?:app(?:lication)?\s+)?(.+)$", text, flags=re.I)
    if m:
        app = m.group(2).strip()
        app = re.sub(r"\b(from|on|in)\b.*$", "", app, flags=re.I).strip()
        if app:
            return {
                "response": f"Okay, uninstalling {app}.",
                "actions": [
                    {
                        "type": "uninstall",
                        "parameters": {
                            "name": app,
                            "confirmed": True,
                            "require_confirm": False,
                        },
                    }
                ],
            }

    # Instagram notifications
    if any(alias in low for alias in ["instagram", "insta", "ig"]):
        if re.search(r"\b(notify|notification|notifications|alerts?|check|update|message|dm)\b", low):
            return {
                "response": "Checking Instagram to see if anything new popped up.",
                "actions": [
                    {
                        "type": "instagram_check_notifications",
                        "parameters": {"natural": text},
                    }
                ],
            }

    if _contains_any(low, ["recycle bin", "recyclebin", "trash", "bin"]):
        if _contains_any(low, ["empty", "clear", "clean", "flush", "dump", "remove", "delete"]):
            return {
                "response": "Emptying the Recycle Bin.",
                "actions": [
                    {
                        "type": "empty_recycle_bin",
                        "parameters": {"natural": text},
                    }
                ],
            }

    # Special-case Hinglish AI compose: "bhej <topic> aai ko aur yashraj ko ai se"
    m_hinglish_ai = re.match(
        r"(?i)^(?:send|bhej)\s+(.+?)\s+([A-Za-z][A-Za-z0-9.'-]{0,30})\s+ko\s+(?:aur|and)\s+([A-Za-z][A-Za-z0-9.'-]{0,30})\s+ko\s+ai\s+se\s*$",
        text.strip(),
    )
    if m_hinglish_ai:
        topic_raw = m_hinglish_ai.group(1).strip(" .,:;-\n")
        c1 = _normalize_contact_name(m_hinglish_ai.group(2) or "").strip()
        c2 = _normalize_contact_name(m_hinglish_ai.group(3) or "").strip()
        # Sanitize contacts by removing topic words accidentally included
        contacts_raw = [c for c in [c1, c2] if c]
        topic_words = {w for w in re.split(r"\W+", topic_raw.lower()) if w}
        def _clean_contact(c: str) -> str:
            toks = [t for t in re.split(r"\s+", c.strip()) if t]
            kept = [t for t in toks if t.lower() not in topic_words and t.lower() not in {"aur", "and", "ko", "to"}]
            if kept:
                return " ".join(kept)
            return toks[-1] if toks else c
        contacts = [_clean_contact(c) for c in contacts_raw]
        # Keep only the last token if spaces remain (e.g., 'law application aai' -> 'aai')
        contacts = [c.split()[-1] if " " in c else c for c in contacts]
        if contacts:
            params = {
                "topic": topic_raw,
                "topic_raw": topic_raw,
                "contacts": contacts,
                "contact": contacts[0],
                "natural": text,
            }
            return {
                "response": f"Preparing AI notes on {topic_raw} for {contacts[0]}",
                "actions": [
                    {"type": "whatsapp_ai_compose_send", "parameters": params}
                ],
            }

    ai_clause_regex = re.compile(
        r"(?:with|using|via|through)\s+(?:the\s+)?(?:ai|chatgpt|chat\s*gpt|gpt|openai)"
        r"(?:\s+(?:info|information|notes?|summary|details|message|text|content|update))?"
        r"|(?:ai|chatgpt|chat\s*gpt)\s+(?:se|se\s+hi|ke\s+through|ki\s+madad\s+se)",
        re.IGNORECASE,
    )
    if ai_clause_regex.search(text):
        cleaned = ai_clause_regex.sub(" ", text)
        cleaned = re.sub(r"(?i)\bon\s+whatsapp(?:\s+chat)?", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        send_terms = r"(?:send|message|msg|bhej|bhejo|bhejna|bhejne|bhejde|bhejdo|bhej\s*do|bhej\s*de)"
        to_terms = r"(?:to|for|ko|ke\s+liye)"
        # Special-case: '<topic> aai ko aur yashraj ko' pattern
        m_special = re.match(
            r"(?i)^(?:please\s+)?(?:send|message|msg|bhej(?:\s*do|\s*de)?)\s+(?P<topic>.+?)\s+(?P<c1>[A-Za-z][A-Za-z0-9.'-]{0,30})\s+ko\s+(?:aur|and)\s+(?P<c2>[A-Za-z][A-Za-z0-9.'-]{0,30})\s+ko(?:\s+.*)?$",
            cleaned,
        )
        if m_special:
            topic_raw = (m_special.group("topic") or "").strip(" .,:;-\n")
            c1 = _normalize_contact_name(m_special.group("c1") or "").strip()
            c2 = _normalize_contact_name(m_special.group("c2") or "").strip()
            contacts = [c for c in [c1, c2] if c]
            if contacts:
                topic_clean = topic_raw
                params: Dict[str, Any] = {
                    "topic": topic_clean,
                    "topic_raw": topic_raw,
                    "contacts": contacts,
                    "contact": contacts[0],
                    "natural": text,
                }
                resp = f"Preparing AI notes on {topic_clean} for {contacts[0]}"
                return {
                    "response": resp,
                    "actions": [
                        {
                            "type": "whatsapp_ai_compose_send",
                            "parameters": params,
                        }
                    ],
                }
        base_pattern = re.compile(
            rf"^(?:please\s+)?{send_terms}\s+(?P<payload>.+?)\s+(?:{to_terms})\s+(?P<contacts>.+?)$",
            re.IGNORECASE,
        )
        # If the structure looks like '... aai ko aur yashraj ko', prefer the fallback parser
        ko_chain_regex = re.search(r"(?i)\b[\w .'-]{1,40}\s+ko\s+(?:aur|and)\s+[\w .'-]{1,40}\s+ko\b", cleaned)
        ko_chain_simple = " ko aur " in cleaned.lower() or " ko and " in cleaned.lower()
        mm = None if (ko_chain_regex or ko_chain_simple) else base_pattern.match(cleaned)
        if mm:
            payload = (mm.group("payload") or "").strip(" .,:;-\n")
            contacts_raw = (mm.group("contacts") or "").strip()
            contacts_raw = re.sub(r"(?i)\b(?:also|too|as\s*well|please)\b$", "", contacts_raw).strip(" .,:;-\n")
            contacts_raw = re.sub(r"(?i)\bwith\s+ai.*$", "", contacts_raw).strip()
            contacts: List[str] = []
            if contacts_raw:
                seen = set()
                for part in _split_recipients(contacts_raw):
                    contact = _normalize_contact_name(part)
                    if not contact:
                        continue
                    key = contact.lower()
                    if key not in seen:
                        seen.add(key)
                        contacts.append(contact)
            if contacts:
                # Sanitize contacts by removing topic words that bled in due to parsing
                topic_words = {w for w in re.split(r"\W+", payload.lower()) if w}
                def _clean_contact_ai(c: str) -> str:
                    toks = [t for t in re.split(r"\s+", c.strip()) if t]
                    kept = [t for t in toks if t.lower() not in topic_words and t.lower() not in {"aur", "and", "ko", "to"}]
                    return " ".join(kept) if kept else (toks[-1] if toks else c)
                contacts = [_clean_contact_ai(c) for c in contacts]
                contacts = [c.split()[-1] if " " in c else c for c in contacts]
                message_kind = ""
                topic_raw = payload
                kind_match = re.match(
                    r"(?i)(info|information|note|notes|summary|details|message|text|update|paragraph|content)\s+(?:about|on|regarding|of)\s+(.+)",
                    payload,
                )
                if kind_match:
                    message_kind = kind_match.group(1).lower()
                    topic_raw = kind_match.group(2).strip()
                else:
                    simple_kind = re.match(
                        r"(?i)(info|information|note|notes|summary|details|message|text|update|paragraph|content)\s+(.+)",
                        payload,
                    )
                    if simple_kind:
                        message_kind = simple_kind.group(1).lower()
                        topic_raw = simple_kind.group(2).strip()
                    else:
                        alt_topic = re.match(r"(?i)(?:about|on|regarding|of)\s+(.+)", payload)
                        if alt_topic:
                            topic_raw = alt_topic.group(1).strip()

                topic_clean = re.sub(r"(?i)^(?:about|on|regarding|of)\s+", "", topic_raw).strip(" .,:;-\n")
                topic_clean = re.sub(r"(?i)\bfor\s+(?:me|us)\b", "", topic_clean).strip(" .,:;-\n")
                if len(topic_clean) < 2:
                    topic_clean = topic_raw.strip()
                topic_clean = topic_clean.strip(" .,:;-\n")
                if topic_clean:
                    low = text.lower()
                    length_pref = ""
                    if re.search(r"\b(short|brief|quick)\b", low):
                        length_pref = "short"
                    elif re.search(r"\b(detailed|long|elaborate|full)\b", low):
                        length_pref = "detailed"
                    format_hint = ""
                    if re.search(r"\b(bullet|points|bullet points)\b", low):
                        format_hint = "bullets"
                    params: Dict[str, Any] = {
                        "topic": topic_clean,
                        "topic_raw": topic_raw,
                        "contacts": contacts,
                        "contact": contacts[0],
                        "natural": text,
                    }
                    if message_kind:
                        params["message_kind"] = message_kind
                    if length_pref:
                        params["length_preference"] = length_pref
                    if format_hint:
                        params["format_hint"] = format_hint
                    resp = f"Preparing AI notes on {topic_clean} for {contacts[0]}"
                    return {
                        "response": resp,
                        "actions": [
                            {
                                "type": "whatsapp_ai_compose_send",
                                "parameters": params,
                            }
                        ],
                    }
        else:
            # If we detected '... X ko aur Y ko', split at the first '<name> ko'
            if ko_chain_regex or ko_chain_simple:
                first_ko = re.search(r"(?i)\b[^\s]+\s+ko\b", cleaned)
                if first_ko:
                    payload = cleaned[: first_ko.start()].strip(" .,:;-\n")
                    contacts_area = cleaned[first_ko.start():].strip()
                    contacts_area = re.sub(r"(?i)\bon\s+whatsapp\b", "", contacts_area)
                    contacts_area = re.sub(r"(?i)\sko\b", "", contacts_area)
                    raw_contacts = _split_recipients(contacts_area)
                    contacts: List[str] = []
                    seen = set()
                    for c in raw_contacts:
                        c2 = _normalize_contact_name(c)
                        if not c2:
                            continue
                        key = c2.lower()
                        if key not in seen:
                            seen.add(key)
                            contacts.append(c2)
                    if contacts:
                        topic_clean = payload.strip(" .,:;-\n")
                        params: Dict[str, Any] = {
                            "topic": topic_clean,
                            "topic_raw": payload,
                            "contacts": contacts,
                            "contact": contacts[0],
                            "natural": text,
                        }
                        resp = f"Preparing AI notes on {topic_clean} for {contacts[0]}"
                        return {
                            "response": resp,
                            "actions": [
                                {
                                    "type": "whatsapp_ai_compose_send",
                                    "parameters": params,
                                }
                            ],
                        }
            # Fallback: handle patterns like 'bhej <topic> aai ko aur yashraj ko'
            mm2 = re.match(
                rf"^(?:please\s+)?{send_terms}\s+(?P<payload>.+?)\s+(?P<contacts>.+)$",
                cleaned,
                re.IGNORECASE,
            )
            if mm2:
                payload = (mm2.group("payload") or "").strip(" .,:;-\n")
                contacts_area = (mm2.group("contacts") or "").strip()
                # Remove trailing 'on whatsapp' and duplicate AI hints if any
                contacts_area = re.sub(r"(?i)\bon\s+whatsapp\b", "", contacts_area)
                # Normalize separators and strip 'ko' suffixes
                contacts_area = re.sub(r"(?i)\sko\b", "", contacts_area)
                raw_contacts = _split_recipients(contacts_area)
                contacts: List[str] = []
                seen = set()
                for c in raw_contacts:
                    c2 = _normalize_contact_name(c)
                    if not c2:
                        continue
                    key = c2.lower()
                    if key not in seen:
                        seen.add(key)
                        contacts.append(c2)
                if contacts:
                    topic_words = {w for w in re.split(r"\W+", payload.lower()) if w}
                    def _clean_contact_ai2(c: str) -> str:
                        toks = [t for t in re.split(r"\s+", c.strip()) if t]
                        kept = [t for t in toks if t.lower() not in topic_words and t.lower() not in {"aur", "and", "ko", "to"}]
                        return " ".join(kept) if kept else (toks[-1] if toks else c)
                    contacts = [_clean_contact_ai2(c) for c in contacts]
                    contacts = [c.split()[-1] if " " in c else c for c in contacts]
                    topic_clean = payload.strip(" .,:;-\n")
                    params: Dict[str, Any] = {
                        "topic": topic_clean,
                        "topic_raw": payload,
                        "contacts": contacts,
                        "contact": contacts[0],
                        "natural": text,
                    }
                    resp = f"Preparing AI notes on {topic_clean} for {contacts[0]}"
                    return {
                        "response": resp,
                        "actions": [
                            {
                                "type": "whatsapp_ai_compose_send",
                                "parameters": params,
                            }
                        ],
                    }

    if re.search(r"(?i)\b(send|bhej|message|msg)\b", text):
        info = _extract_message_and_contacts(text)
        if info:
            actions = _build_whatsapp_actions(info["message"], info["contacts"], info["close"])
            resp = f"Sending message to {', '.join(info['contacts'])}."
            return {"response": resp, "actions": actions}

    # WhatsApp send (English + Hinglish lightweight parser) - local, no LLM
    # Examples: "send hi to mummy", "bhej hello papa ko", "msg bye to john and sarah"
    whatsapp_patterns = [
        r'send\s+(.+?)\s+to\s+(.+?)(?:\s+and\s+(.+))?$',
        r'(?:msg|message)\s+(.+?)\s+(?:to\s+)?(.+?)(?:\s+and\s+(.+))?$',
        r'bhej\s+(.+?)\s+(?:ko\s+)?(.+?)(?:\s+ko)?(?:\s+aur\s+(.+))?$',
        r'msg\s+(.+?)\s+(.+?)(?:\s+ko)?(?:\s+aur\s+(.+))?$',
    ]
    for pat in whatsapp_patterns:
        try:
            mm = re.search(pat, text, flags=re.I)
            if mm:
                message = mm.group(1).strip()
                c1 = mm.group(2).strip() if mm.group(2) else ""
                c2 = mm.group(3).strip() if mm.group(3) else None
                contacts = [c1]
                if c2:
                    contacts.append(c2)
                actions = []
                for c in contacts:
                    # split recipients by commas/and/aur
                    parts = _split_recipients(c)
                    for p in parts:
                        actions.append({"type": "whatsapp_send", "parameters": {"contact": p, "message": message}})
                resp = f"Sending message to {', '.join([p for p in contacts])}."
                return {"response": resp, "actions": actions}
        except Exception:
            continue
    # Play song
    play_verbs = [r"\bplay\b", r"\bplay me\b", r"\bjaoue\b"]
    if any(re.search(pv, text, re.IGNORECASE) for pv in play_verbs):
        try:
            from .actions import _parse_play_song_query
            parsed = _parse_play_song_query(text)
            if parsed:
                cleaned = re.sub(r"(?i)^(?:play\s+me|play|reproducir)\s+", '', parsed).strip()
                song = cleaned if cleaned else parsed
                return {"response": f"Playing {song}.", "actions": [{"type": "play_song", "parameters": {"song": song}}]}
        except Exception:
            return {"response": "Playing song.", "actions": [{"type": "play_song", "parameters": {"text": text}}]}

    # Stop/Pause song/music - explicit patterns for better recognition
    if re.search(r"\b(stop|pause|band|bandh|rok|roko)\b.*\b(song|music|gaana|gana|spotify|track)\b", low):
        return {"response": "Stopping music.", "actions": [{"type": "stop_music", "parameters": {}}]}
    if re.search(r"\b(stop|pause)\b\s*(the)?\s*(song|music|track|playback)?\s*$", low):
        return {"response": "Stopping music.", "actions": [{"type": "stop_music", "parameters": {}}]}
    
    # Next/Skip song
    if re.search(r"\b(next|skip|agla|agli)\b.*\b(song|music|gaana|gana|track)\b", low):
        return {"response": "Skipping to next track.", "actions": [{"type": "next_song", "parameters": {}}]}
    if re.search(r"\b(next|skip)\b\s*(song|track)?\s*$", low):
        return {"response": "Skipping to next track.", "actions": [{"type": "next_song", "parameters": {}}]}
    
    # Previous song
    if re.search(r"\b(previous|prev|pichla|pichli|back)\b.*\b(song|music|gaana|gana|track)\b", low):
        return {"response": "Going to previous track.", "actions": [{"type": "previous_song", "parameters": {}}]}

    # Search (handled above by browser parser). Keep lightweight fallback if needed
    if low.startswith("search "):
        parsed = _parse_browser_search(text)
        if parsed:
            act = parsed.get("action") or {}
            return {"response": parsed.get("response", ""), "actions": [act] if act else []}
        query = low[7:].strip()
        return {"response": f"Searching for {query}.", "actions": [{"type": "search", "parameters": {"query": query}}]}

    # Calculator quick access
    if re.match(r"(?i)^(?:open\s+)?(?:calculator|calc)\b", text):
        return {
            "response": "Opening calculator.",
            "actions": [{"type": "open", "parameters": {"target": "calc.exe"}}],
        }

    # Open
    if low.startswith("open "):
        rest = text[5:].strip()
        if rest.startswith("http://") or rest.startswith("https://"):
            return {"response": f"Opening {rest}", "actions": [{"type": "open", "parameters": {"url": rest}}]}
        
        # Allow forms like 'open calc and 2+2'
        rest_main = re.split(r"\s+and\s+|,", rest, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        alias = {"notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe", "paint": "mspaint.exe"}
        if rest_main.lower() in alias:
            exe = alias.get(rest_main.lower(), rest_main)
            return {"response": f"Opening {rest}", "actions": [{"type": "open", "parameters": {"target": exe}}]}
        
        return {"response": f"Opening {rest}.", "actions": [{"type": "open_app_start", "parameters": {"name": rest}}]}

    # Type
    if low.startswith("type "):
        return {"response": "", "actions": [{"type": "type", "parameters": {"text": text[5:]}}]}

    # Hotkey
    if low.startswith("press "):
        combo = re.sub(r"^press\s+", "", text, flags=re.I).strip()
        return {"response": "", "actions": [{"type": "hotkey", "parameters": {"keys": combo}}]}

    # Teaching commands
    if "start teaching" in low or "teach you" in low:
        task = re.sub(r".*(teaching|teach)\s+", "", text).strip()
        return {
            "response": f"Okay Final Boss! I'm watching for: {task}",
            "actions": [{"type": "start_teaching", "parameters": {"task_name": task}}]
        }
    
    if "stop teaching" in low or "done teaching" in low:
        return {
            "response": "Analyzing what you showed me...",
            "actions": [{"type": "stop_teaching", "parameters": {"description": text}}]
        }
    
    if "do the task" in low or "perform" in low:
        task = re.sub(r".*(do|perform)\s+(the\s+)?(task\s+)?", "", text).strip()
        return {
            "response": f"On it, Final Boss! Performing: {task}",
            "actions": [{"type": "do_learned_task", "parameters": {"task": task}}]
        }
    
    if "list learned" in low or "what can you do" in low:
        return {
            "response": "Let me show you what I've learned...",
            "actions": [{"type": "list_learned_tasks", "parameters": {}}]
        }

    # Fallback
    # Fallback - Local Only
    if low.strip() in {"uninstall", "remove", "delete"}:
        return {"response": "Which application should I uninstall?", "actions": []}

    # Fallback to Gemini if native parsing failed
    try:
        plan = _llm_plan(text, memory=memory)
        if plan and (plan.get("response") or plan.get("actions")):
            return plan
    except Exception:
        pass

    return {
        "response": "I didn't quite catch that. Try commands like 'open calculator', 'play music', or 'set volume to 50%'.", 
        "actions": []
    }