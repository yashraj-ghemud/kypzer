"""
Task Scheduler - Scheduled message storage and execution.

Features:
- Schedule messages for later delivery ("send msg to X at 7:30pm")
- Natural time parsing (afternoon, evening, morning, tonight, specific times)
- Persistent storage of scheduled tasks
- Background execution of scheduled tasks
- Multi-recipient scheduled messages
- Recurring scheduled messages (daily, weekly)
- Task cancellation and modification

This module provides scheduled task functionality for the PC Controller assistant.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Union
from uuid import uuid4
import hashlib


# -----------------------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------------------

# Default storage location
DEFAULT_STORAGE_DIR = Path(__file__).parent.parent.parent / "data" / "scheduled_tasks"
TASKS_FILE = "scheduled_tasks.json"

# Time word mappings
TIME_WORDS: Dict[str, tuple] = {
    # Format: word -> (hour, minute)
    "morning": (9, 0),
    "early morning": (6, 30),
    "late morning": (11, 0),
    "noon": (12, 0),
    "afternoon": (14, 30),
    "early afternoon": (13, 0),
    "late afternoon": (16, 30),
    "evening": (18, 30),
    "early evening": (17, 30),
    "late evening": (20, 30),
    "night": (21, 0),
    "tonight": (21, 0),
    "midnight": (0, 0),
    "lunch": (12, 30),
    "lunchtime": (12, 30),
    "dinner": (19, 30),
    "dinnertime": (19, 30),
    "breakfast": (8, 0),
}

# Day word mappings
DAY_WORDS: Dict[str, int] = {
    # Days from today
    "today": 0,
    "tonight": 0,
    "tomorrow": 1,
    "day after tomorrow": 2,
    "day after": 2,
}

# Recurrence patterns
class RecurrenceType(Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# Task status
class TaskStatus(Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# -----------------------------------------------------------------------------
# DATA CLASSES
# -----------------------------------------------------------------------------

@dataclass
class ScheduledTask:
    """Represents a scheduled task."""
    task_id: str
    task_type: str  # e.g., "whatsapp_send", "volume_set", "play_song"
    parameters: Dict[str, Any]
    scheduled_time: datetime
    created_at: datetime = field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.PENDING
    recurrence: RecurrenceType = RecurrenceType.NONE
    description: str = ""
    execution_count: int = 0
    last_executed: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "parameters": self.parameters,
            "scheduled_time": self.scheduled_time.isoformat(),
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "recurrence": self.recurrence.value,
            "description": self.description,
            "execution_count": self.execution_count,
            "last_executed": self.last_executed.isoformat() if self.last_executed else None,
            "error_message": self.error_message,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledTask":
        """Create from dictionary."""
        return cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            parameters=data["parameters"],
            scheduled_time=datetime.fromisoformat(data["scheduled_time"]),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            status=TaskStatus(data.get("status", "pending")),
            recurrence=RecurrenceType(data.get("recurrence", "none")),
            description=data.get("description", ""),
            execution_count=data.get("execution_count", 0),
            last_executed=datetime.fromisoformat(data["last_executed"]) if data.get("last_executed") else None,
            error_message=data.get("error_message"),
        )
    
    @property
    def is_due(self) -> bool:
        """Check if task is due for execution."""
        return (
            self.status == TaskStatus.PENDING and
            datetime.now() >= self.scheduled_time
        )
    
    @property
    def time_until(self) -> timedelta:
        """Get time until scheduled execution."""
        return self.scheduled_time - datetime.now()
    
    def get_friendly_time(self) -> str:
        """Get human-friendly time description."""
        now = datetime.now()
        diff = self.scheduled_time - now
        
        if diff.days < 0:
            return "overdue"
        elif diff.days == 0:
            if diff.seconds < 60:
                return "in less than a minute"
            elif diff.seconds < 3600:
                mins = diff.seconds // 60
                return f"in {mins} minute{'s' if mins > 1 else ''}"
            else:
                hours = diff.seconds // 3600
                return f"in {hours} hour{'s' if hours > 1 else ''}"
        elif diff.days == 1:
            return f"tomorrow at {self.scheduled_time.strftime('%I:%M %p')}"
        else:
            return f"in {diff.days} days"


# -----------------------------------------------------------------------------
# TIME PARSING
# -----------------------------------------------------------------------------

def parse_time_expression(text: str, base_time: Optional[datetime] = None) -> Optional[datetime]:
    """
    Parse a natural language time expression into a datetime.
    
    Examples:
        - "7:30pm" -> today at 7:30 PM (or tomorrow if already passed)
        - "afternoon" -> today at 2:30 PM
        - "tomorrow morning" -> tomorrow at 9:00 AM
        - "at 8pm tomorrow" -> tomorrow at 8:00 PM
        - "in 2 hours" -> now + 2 hours
        - "after 30 minutes" -> now + 30 minutes
    """
    if not text:
        return None
    
    base = base_time or datetime.now()
    low = text.lower().strip()
    
    # Pattern: "in X hours/minutes"
    relative_match = re.search(r"(?:in|after)\s+(\d+)\s*(hours?|minutes?|mins?|hrs?)", low)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2).lower()
        
        if unit.startswith("h"):
            return base + timedelta(hours=amount)
        else:
            return base + timedelta(minutes=amount)
    
    # Find day offset
    day_offset = 0
    for day_word, offset in DAY_WORDS.items():
        if day_word in low:
            day_offset = offset
            break
    
    # Pattern: explicit time like "7:30pm", "19:30", "8 pm", "1:55 a.m.", "215am"
    # Handles optional dots in am/pm and optional colon
    time_match = re.search(r"(\d{1,2})(?::?(\d{2}))?\s*([ap]\.?m\.?)?", low)
    
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        period = (time_match.group(3) or "").replace(".", "").lower()
        
        # Convert to 24-hour format
        if period:
            if period == "pm" and hour != 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0
        elif hour <= 7 and not period:
            # Assume PM for small numbers without AM/PM unless context implies likely AM (handled by logic above/below)
            # Actually, without period, small numbers like 'at 2' usually mean 2 PM unless it's clearly night.
            # But let's stick to the existing logic: <= 7 -> +12 (PM).
            hour += 12
        
        result = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        result += timedelta(days=day_offset)
        
        # If time already passed today and no explicit day, schedule for tomorrow
        if day_offset == 0 and result <= base:
            result += timedelta(days=1)
        
        return result
    
    # Check for time words (morning, afternoon, etc.)
    for time_word, (hour, minute) in TIME_WORDS.items():
        if time_word in low:
            result = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            result += timedelta(days=day_offset)
            
            # If time already passed today, schedule for tomorrow
            if day_offset == 0 and result <= base:
                result += timedelta(days=1)
            
            return result
    
    return None


def format_time_friendly(dt: datetime) -> str:
    """Format datetime in a friendly way."""
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    
    if dt.date() == today:
        return f"today at {dt.strftime('%I:%M %p')}"
    elif dt.date() == tomorrow:
        return f"tomorrow at {dt.strftime('%I:%M %p')}"
    else:
        return dt.strftime("%A, %B %d at %I:%M %p")


# -----------------------------------------------------------------------------
# TASK STORAGE
# -----------------------------------------------------------------------------

class TaskStorage:
    """Persistent storage for scheduled tasks."""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = Path(storage_dir) if storage_dir else DEFAULT_STORAGE_DIR
        self.tasks_file = self.storage_dir / TASKS_FILE
        self._lock = threading.Lock()
        self._ensure_storage_dir()
    
    def _ensure_storage_dir(self) -> None:
        """Ensure storage directory exists."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def load_tasks(self) -> List[ScheduledTask]:
        """Load all tasks from storage."""
        with self._lock:
            if not self.tasks_file.exists():
                return []
            
            try:
                with open(self.tasks_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return [ScheduledTask.from_dict(t) for t in data]
            except Exception:
                return []
    
    def save_tasks(self, tasks: List[ScheduledTask]) -> bool:
        """Save all tasks to storage."""
        with self._lock:
            try:
                self._ensure_storage_dir()
                data = [t.to_dict() for t in tasks]
                with open(self.tasks_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                return True
            except Exception:
                return False
    
    def add_task(self, task: ScheduledTask) -> bool:
        """Add a new task."""
        tasks = self.load_tasks()
        tasks.append(task)
        return self.save_tasks(tasks)
    
    def remove_task(self, task_id: str) -> bool:
        """Remove a task by ID."""
        tasks = self.load_tasks()
        original_count = len(tasks)
        tasks = [t for t in tasks if t.task_id != task_id]
        if len(tasks) < original_count:
            return self.save_tasks(tasks)
        return False
    
    def update_task(self, task: ScheduledTask) -> bool:
        """Update an existing task."""
        tasks = self.load_tasks()
        for i, t in enumerate(tasks):
            if t.task_id == task.task_id:
                tasks[i] = task
                return self.save_tasks(tasks)
        return False
    
    def get_pending_tasks(self) -> List[ScheduledTask]:
        """Get all pending tasks."""
        return [t for t in self.load_tasks() if t.status == TaskStatus.PENDING]
    
    def get_due_tasks(self) -> List[ScheduledTask]:
        """Get all tasks that are due for execution."""
        return [t for t in self.load_tasks() if t.is_due]


# -----------------------------------------------------------------------------
# TASK SCHEDULER ENGINE
# -----------------------------------------------------------------------------

class TaskScheduler:
    """Background scheduler that executes tasks at scheduled times."""
    
    def __init__(
        self,
        storage: Optional[TaskStorage] = None,
        executor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        poll_interval: float = 5.0,
    ):
        self.storage = storage or TaskStorage()
        self.executor = executor  # Function to execute actions
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self) -> None:
        """Start the scheduler background thread."""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
    
    def stop(self) -> None:
        """Stop the scheduler."""
        with self._lock:
            self._running = False
            if self._thread:
                self._thread.join(timeout=5.0)
                self._thread = None
    
    def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                self._process_due_tasks()
            except Exception:
                pass
            time.sleep(self.poll_interval)
    
    def _process_due_tasks(self) -> None:
        """Process all due tasks."""
        due_tasks = self.storage.get_due_tasks()
        
        for task in due_tasks:
            try:
                self._execute_task(task)
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                self.storage.update_task(task)
    
    def _execute_task(self, task: ScheduledTask) -> None:
        """Execute a single task."""
        if not self.executor:
            return
        
        action = {
            "type": task.task_type,
            "parameters": task.parameters,
        }
        
        try:
            result = self.executor(action)
            
            task.execution_count += 1
            task.last_executed = datetime.now()
            
            if result.get("ok"):
                if task.recurrence == RecurrenceType.NONE:
                    task.status = TaskStatus.EXECUTED
                else:
                    # Reschedule for next occurrence
                    task.scheduled_time = self._get_next_occurrence(task)
            else:
                task.error_message = result.get("say", "Unknown error")
            
            self.storage.update_task(task)
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            self.storage.update_task(task)
    
    def _get_next_occurrence(self, task: ScheduledTask) -> datetime:
        """Calculate next occurrence for recurring tasks."""
        base = task.scheduled_time
        
        if task.recurrence == RecurrenceType.DAILY:
            return base + timedelta(days=1)
        elif task.recurrence == RecurrenceType.WEEKLY:
            return base + timedelta(weeks=1)
        elif task.recurrence == RecurrenceType.MONTHLY:
            # Approximate month as 30 days
            return base + timedelta(days=30)
        
        return base


# -----------------------------------------------------------------------------
# GLOBAL SCHEDULER INSTANCE
# -----------------------------------------------------------------------------

_scheduler: Optional[TaskScheduler] = None
_scheduler_lock = threading.Lock()


def get_scheduler(
    executor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
) -> TaskScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    
    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = TaskScheduler(executor=executor)
        elif executor and _scheduler.executor is None:
            _scheduler.executor = executor
        return _scheduler


def start_scheduler(
    executor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
) -> None:
    """Start the global scheduler."""
    scheduler = get_scheduler(executor)
    scheduler.start()


def stop_scheduler() -> None:
    """Stop the global scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()


# -----------------------------------------------------------------------------
# HIGH-LEVEL API
# -----------------------------------------------------------------------------

def schedule_task(
    task_type: str,
    parameters: Dict[str, Any],
    scheduled_time: Union[datetime, str],
    description: str = "",
    recurrence: RecurrenceType = RecurrenceType.NONE,
) -> Dict[str, Any]:
    """
    Schedule a new task.
    
    Args:
        task_type: Type of action (e.g., "whatsapp_send")
        parameters: Action parameters
        scheduled_time: When to execute (datetime or natural language)
        description: Human-readable description
        recurrence: Recurrence pattern
    
    Returns:
        Result dict with task_id if successful
    """
    # Parse time if string
    if isinstance(scheduled_time, str):
        parsed_time = parse_time_expression(scheduled_time)
        if not parsed_time:
            return {"ok": False, "say": f"Couldn't understand time: {scheduled_time}"}
    else:
        parsed_time = scheduled_time
    
    # Create task
    task = ScheduledTask(
        task_id=str(uuid4())[:8],
        task_type=task_type,
        parameters=parameters,
        scheduled_time=parsed_time,
        description=description,
        recurrence=recurrence,
    )
    
    # Save to storage
    storage = TaskStorage()
    if storage.add_task(task):
        friendly_time = format_time_friendly(parsed_time)
        return {
            "ok": True,
            "say": f"Scheduled for {friendly_time}.",
            "task_id": task.task_id,
            "scheduled_time": parsed_time.isoformat(),
        }
    
    return {"ok": False, "say": "Failed to save scheduled task."}


def cancel_scheduled_task(task_id: str) -> Dict[str, Any]:
    """Cancel a scheduled task."""
    storage = TaskStorage()
    tasks = storage.load_tasks()
    
    for task in tasks:
        if task.task_id == task_id:
            task.status = TaskStatus.CANCELLED
            if storage.update_task(task):
                return {"ok": True, "say": f"Cancelled task {task_id}."}
            break
    
    return {"ok": False, "say": f"Task {task_id} not found."}


def list_scheduled_tasks() -> Dict[str, Any]:
    """List all pending scheduled tasks."""
    storage = TaskStorage()
    pending = storage.get_pending_tasks()
    
    if not pending:
        return {"ok": True, "say": "No scheduled tasks.", "tasks": []}
    
    tasks_info = []
    for task in sorted(pending, key=lambda t: t.scheduled_time):
        tasks_info.append({
            "id": task.task_id,
            "type": task.task_type,
            "time": format_time_friendly(task.scheduled_time),
            "description": task.description,
        })
    
    summary = f"You have {len(pending)} scheduled task{'s' if len(pending) > 1 else ''}."
    return {"ok": True, "say": summary, "tasks": tasks_info}


def list_scheduler_status() -> Dict[str, Any]:
    """Get the status of the scheduler."""
    global _scheduler
    
    is_running = _scheduler is not None and _scheduler.running
    storage = TaskStorage()
    pending = storage.get_pending_tasks()
    
    status_str = "active" if is_running else "inactive"
    count = len(pending)
    
    say = f"Scheduler is {status_str} with {count} pending tasks."
    return {
        "ok": True, 
        "say": say, 
        "status": status_str,
        "pending_count": count
    }


def get_task_details(task_id: str) -> Optional[ScheduledTask]:
    """Get details of a specific task."""
    storage = TaskStorage()
    tasks = storage.load_tasks()
    
    for task in tasks:
        if task.task_id == task_id:
            return task
    
    return None


# -----------------------------------------------------------------------------
# NLU HELPER - PARSE SCHEDULED TASK COMMANDS
# -----------------------------------------------------------------------------

def parse_scheduled_task_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse natural language commands for scheduling tasks.
    
    Examples:
        - "send good morning to mom at 7am"
        - "remind me to call dad tomorrow afternoon"
        - "schedule volume 50% at 10pm"
        - "at 8pm send hi to everyone"
    
    Returns action dict if recognized, None otherwise.
    """
    if not text:
        return None
    
    low = text.lower().strip()
    
    # Check for scheduling keywords
    schedule_triggers = [
        "at", "on", "schedule", "remind", "later", "tomorrow",
        "morning", "afternoon", "evening", "tonight", "pm", "am"
    ]
    
    has_schedule_context = any(t in low for t in schedule_triggers)
    if not has_schedule_context:
        return None
    
    # Pattern: action at/on time
    # Examples:
    #   - "send hi to mom at 7:30pm"
    #   - "at 8pm send hi to dad"
    #   - "tomorrow morning send good morning to parents"
    
    # Extract time expression
    time_patterns = [
        r"(?:at|on)\s+(\d{1,2}(?::?\d{2})?\s*(?:[ap]\.?m\.?)?)",
        r"(tomorrow\s+(?:morning|afternoon|evening|night)?)",
        r"(tonight|this\s+evening|this\s+afternoon)",
        r"(?:in|after)\s+(\d+\s+(?:hours?|minutes?))",
        r"(morning|afternoon|evening)\s+(?:at\s+)?(\d{1,2}(?::?\d{2})?\s*(?:[ap]\.?m\.?)?)?",
    ]
    
    time_expr = None
    action_text = low
    
    for pattern in time_patterns:
        match = re.search(pattern, low)
        if match:
            time_expr = match.group(0)
            # Remove time from action text
            action_text = low.replace(match.group(0), " ").strip()
            break
    
    if not time_expr:
        return None
    
    # Parse the time
    parsed_time = parse_time_expression(time_expr)
    if not parsed_time:
        return None
    
    # Try to extract the actual action
    # Common patterns: "send X to Y", "set volume to Z", "play X"
    
    # WhatsApp message
    # Enhanced to handle 'tu' (typo for 'to') and 'ko' (Hindi)
    wa_match = re.search(r"(?:send|message|msg|bhej)\s+(.+?)\s+(?:to|for|tu|ko)\s+(.+)", action_text, flags=re.IGNORECASE)
    if wa_match:
        message = wa_match.group(1).strip()
        recipients = wa_match.group(2).strip()
        
        return {
            "type": "schedule_task",
            "parameters": {
                "task_type": "whatsapp_send_multi",
                "task_parameters": {
                    "message": message,
                    "contacts": recipients,
                },
                "scheduled_time": time_expr,
                "parsed_time": parsed_time.isoformat(),
                "description": f"Send '{message[:30]}...' to {recipients}",
            }
        }
    
    # Volume setting
    vol_match = re.search(r"(?:set\s+)?volume\s+(?:to\s+)?(\d+)%?", action_text)
    if vol_match:
        level = int(vol_match.group(1))
        return {
            "type": "schedule_task",
            "parameters": {
                "task_type": "volume",
                "task_parameters": {"percent": level},
                "scheduled_time": time_expr,
                "parsed_time": parsed_time.isoformat(),
                "description": f"Set volume to {level}%",
            }
        }
    
    # Play song
    play_match = re.search(r"play\s+(.+)", action_text)
    if play_match:
        song = play_match.group(1).strip()
        return {
            "type": "schedule_task",
            "parameters": {
                "task_type": "play_song",
                "task_parameters": {"song": song},
                "scheduled_time": time_expr,
                "parsed_time": parsed_time.isoformat(),
                "description": f"Play '{song}'",
            }
        }
    
    # Generic reminder
    if "remind" in low:
        reminder_match = re.search(r"remind\s+(?:me\s+)?(?:to\s+)?(.+)", action_text)
        if reminder_match:
            reminder = reminder_match.group(1).strip()
            return {
                "type": "schedule_task",
                "parameters": {
                    "task_type": "reminder",
                    "task_parameters": {"text": reminder},
                    "scheduled_time": time_expr,
                    "parsed_time": parsed_time.isoformat(),
                    "description": f"Reminder: {reminder}",
                }
            }
            
    # Fallback: Generic Command (Memory Planning)
    # If we have a valid time but matched no specific pattern, assume the whole text is a command
    # to be interpreted at runtime.
    if action_text.strip():
        cleaned_cmd = action_text.strip()
        # Remove common filler words
        cleaned_cmd = re.sub(r"^(please|kindly)\s+", "", cleaned_cmd, flags=re.IGNORECASE)
        
        return {
            "type": "schedule_task",
            "parameters": {
                "task_type": "general_command", 
                "task_parameters": {"command": cleaned_cmd},
                "scheduled_time": time_expr,
                "parsed_time": parsed_time.isoformat(),
                "description": f"Execute later: {cleaned_cmd}",
            }
        }
    
    return None


# -----------------------------------------------------------------------------
# ACTION EXECUTOR
# -----------------------------------------------------------------------------

def execute_scheduler_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a parsed scheduler action.
    
    Args:
        action: Dict with "type" and "parameters" keys
    
    Returns:
        Result dict with ok/say keys
    """
    atype = (action.get("type") or "").lower()
    params = action.get("parameters") or {}
    
    if atype in {"schedule_task", "scheduled_task_add"}:
        task_type = params.get("task_type")
        task_params = params.get("task_parameters", {})
        time_expr = params.get("scheduled_time")
        description = params.get("description", "")
        
        return schedule_task(
            task_type=task_type,
            parameters=task_params,
            scheduled_time=time_expr,
            description=description,
        )
    
    if atype in {"cancel_scheduled", "scheduled_task_cancel"}:
        task_id = params.get("task_id")
        return cancel_scheduled_task(task_id)
    
    if atype in {"list_scheduled", "scheduled_task_list"}:
        return list_scheduled_tasks()

    if atype in {"scheduled_task_status", "scheduler_status"}:
        return list_scheduler_status()
    
    return {"ok": False, "say": f"Unknown scheduler action: {atype}"}


# -----------------------------------------------------------------------------
# TEST
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("Testing Task Scheduler...")
    
    # Test time parsing
    test_times = [
        "7:30pm",
        "at 8pm",
        "tomorrow morning",
        "afternoon",
        "tonight",
        "in 2 hours",
        "after 30 minutes",
        "tomorrow at 9am",
    ]
    
    for t in test_times:
        parsed = parse_time_expression(t)
        if parsed:
            print(f"'{t}' -> {format_time_friendly(parsed)}")
        else:
            print(f"'{t}' -> FAILED")
    
    print("\n--- Testing command parsing ---")
    
    test_commands = [
        "send good morning to mom at 7am",
        "at 8pm send hi to dad",
        "tomorrow morning send hello to parents",
        "remind me to call dad at 5pm",
        "set volume to 50% at 10pm",
    ]
    
    for cmd in test_commands:
        result = parse_scheduled_task_command(cmd)
        print(f"'{cmd}' -> {result}")
