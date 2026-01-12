"""
Multi-Task Parser - Parse and execute compound commands with multiple actions.

Features:
- Parse compound commands like "send msg to X then play Y then volume 100%"
- Chain execution of multiple actions in sequence
- Support for Hinglish connectors (aur, phir, fir, baad mein)
- Dependency tracking between actions
- Parallel vs sequential execution decisions
- Action priority ordering
- Error handling with partial completion
- Action result aggregation

This module enables the PC Controller to handle complex multi-part commands.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from datetime import datetime


# -----------------------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------------------

# Connectors that indicate sequence (then, after)
SEQUENCE_CONNECTORS = [
    r"\band\s+then\b",     # Must come before 'then' alone
    r"\bthen\b",
    r"\bafter\s+that\b",
    r"\bafter\s+this\b",
    r"\bnext\b",
    r"\bfollowed\s+by\b",
    r"\bphir\b",           # Hinglish: then
    r"\bfir\b",            # Hinglish: then (variation)
    r"\buske\s+baad\b",   # Hinglish: after that
    r"\bbaad\s+mein\b",   # Hinglish: later
    r"\bke\s+baad\b",     # Hinglish: after
]

# Connectors that indicate parallel/combined actions (and)
PARALLEL_CONNECTORS = [
    r"\band\b",
    r"\balso\b",
    r"\bplus\b",
    r"\baur\b",       # Hinglish: and
    r"\bbhi\b",       # Hinglish: also
    r"&",
]

# Action type keywords for classification
ACTION_KEYWORDS = {
    # WhatsApp actions
    "whatsapp": ["send", "message", "msg", "bhej", "bhejo", "text", "whatsapp"],
    # Volume actions
    "volume": ["volume", "sound", "loud", "quiet", "mute", "unmute", "awaz"],
    # Brightness actions
    "brightness": ["brightness", "bright", "dim", "screen"],
    # Music/playback actions
    "music": ["play", "pause", "stop", "next", "previous", "song", "music", "gaana", "bajao", "chalao"],
    # App actions
    "app": ["open", "launch", "start", "close", "khol", "band"],
    # Search actions
    "search": ["search", "google", "find", "lookup"],
    # System actions
    "system": ["shutdown", "restart", "sleep", "lock", "hibernate"],
    # Settings actions
    "settings": ["wifi", "bluetooth", "hotspot", "airplane"],
}


# -----------------------------------------------------------------------------
# DATA CLASSES
# -----------------------------------------------------------------------------

class ActionPriority(Enum):
    """Priority levels for action execution order."""
    HIGH = 1      # System critical (shutdown, etc.)
    MEDIUM = 2    # User-facing (UI, apps)
    LOW = 3       # Background (notifications)


class ExecutionMode(Enum):
    """How actions should be executed."""
    SEQUENTIAL = "sequential"  # One after another
    PARALLEL = "parallel"      # All at once (where possible)


@dataclass
class ParsedAction:
    """Represents a single parsed action from a compound command."""
    action_type: str
    parameters: Dict[str, Any]
    raw_text: str
    priority: ActionPriority = ActionPriority.MEDIUM
    depends_on: Optional[str] = None  # ID of action this depends on
    action_id: str = ""
    
    def __post_init__(self):
        if not self.action_id:
            import hashlib
            self.action_id = hashlib.md5(self.raw_text.encode()).hexdigest()[:8]


@dataclass
class ActionResult:
    """Result of executing a single action."""
    action_id: str
    success: bool
    message: str
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MultiTaskResult:
    """Result of executing multiple actions."""
    total_actions: int
    successful: int
    failed: int
    results: List[ActionResult] = field(default_factory=list)
    execution_time: float = 0.0
    
    @property
    def all_succeeded(self) -> bool:
        return self.failed == 0 and self.successful > 0
    
    @property
    def partial_success(self) -> bool:
        return self.successful > 0 and self.failed > 0
    
    def get_summary(self) -> str:
        if self.all_succeeded:
            return f"Completed all {self.successful} tasks."
        elif self.partial_success:
            return f"Completed {self.successful} of {self.total_actions} tasks."
        elif self.successful == 0:
            return "Failed to complete any tasks."
        return "Unknown result."


# -----------------------------------------------------------------------------
# TEXT SPLITTING
# -----------------------------------------------------------------------------

def split_compound_command(text: str) -> List[Tuple[str, ExecutionMode]]:
    """
    Split a compound command into individual action segments.
    
    Returns list of (segment_text, execution_mode) tuples.
    """
    if not text:
        return []
    
    # Normalize whitespace
    text = " ".join(text.split())
    
    # First, identify all connector positions
    connector_positions: List[Tuple[int, int, ExecutionMode]] = []
    
    # Find sequence connectors
    for pattern in SEQUENCE_CONNECTORS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            connector_positions.append((match.start(), match.end(), ExecutionMode.SEQUENTIAL))
    
    # Find parallel connectors (only if not already marked as sequence)
    for pattern in PARALLEL_CONNECTORS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # Check if this position overlaps with a sequence connector
            overlaps = False
            for start, end, _ in connector_positions:
                if not (match.end() <= start or match.start() >= end):
                    overlaps = True
                    break
            if not overlaps:
                # Heuristic: Don't split "and" if it looks like a recipient list (e.g. "to mum and dad")
                # Look at text immediately preceding the 'and'
                pre_text = text[:match.start()]
                # Check for "to/for/send <names>" pattern immediately before, avoiding digits (like "volume to 100%")
                if re.search(r"(?i)\b(?:to|for|ko|bhej|send|msg|message|text|tell|ask)\s+(?:[a-zA-Z']+\s*){1,5}$", pre_text):
                    continue

                connector_positions.append((match.start(), match.end(), ExecutionMode.PARALLEL))
    
    # Sort by position
    connector_positions.sort(key=lambda x: x[0])
    
    if not connector_positions:
        return [(text.strip(), ExecutionMode.SEQUENTIAL)]
    
    # Split text at connector positions
    segments: List[Tuple[str, ExecutionMode]] = []
    last_end = 0
    current_mode = ExecutionMode.SEQUENTIAL
    
    for start, end, mode in connector_positions:
        segment = text[last_end:start].strip()
        if segment:
            segments.append((segment, current_mode))
        current_mode = mode
        last_end = end
    
    # Add final segment
    final_segment = text[last_end:].strip()
    if final_segment:
        segments.append((final_segment, current_mode))
    
    return segments


# -----------------------------------------------------------------------------
# ACTION CLASSIFICATION
# -----------------------------------------------------------------------------

def classify_action_type(text: str) -> str:
    """
    Classify the type of action based on keywords in the text.
    
    Returns the action category string.
    """
    if not text:
        return "unknown"
    
    low = text.lower()
    
    # Check each category
    scores: Dict[str, int] = {}
    for category, keywords in ACTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in low)
        if score > 0:
            scores[category] = score
    
    if not scores:
        return "unknown"
    
    # Return category with highest score
    return max(scores.items(), key=lambda x: x[1])[0]


def get_action_priority(action_type: str) -> ActionPriority:
    """Get execution priority for an action type."""
    high_priority = ["system"]
    low_priority = ["search"]
    
    if action_type in high_priority:
        return ActionPriority.HIGH
    elif action_type in low_priority:
        return ActionPriority.LOW
    return ActionPriority.MEDIUM


# -----------------------------------------------------------------------------
# ACTION PARSING
# -----------------------------------------------------------------------------

def parse_single_action(text: str) -> Optional[ParsedAction]:
    """
    Parse a single action segment into a structured action.
    
    This delegates to specific parsers based on action type.
    """
    if not text:
        return None
    
    action_type = classify_action_type(text)
    parameters: Dict[str, Any] = {"raw_text": text}
    
    # WhatsApp message
    if action_type == "whatsapp":
        wa_result = _parse_whatsapp_action(text)
        if wa_result:
            return ParsedAction(
                action_type=wa_result["type"],
                parameters=wa_result["parameters"],
                raw_text=text,
                priority=ActionPriority.MEDIUM,
            )
    
    # Volume control
    if action_type == "volume":
        vol_result = _parse_volume_action(text)
        if vol_result:
            return ParsedAction(
                action_type=vol_result["type"],
                parameters=vol_result["parameters"],
                raw_text=text,
                priority=ActionPriority.MEDIUM,
            )
    
    # Music/playback
    if action_type == "music":
        music_result = _parse_music_action(text)
        if music_result:
            return ParsedAction(
                action_type=music_result["type"],
                parameters=music_result["parameters"],
                raw_text=text,
                priority=ActionPriority.MEDIUM,
            )
    
    # Brightness
    if action_type == "brightness":
        bright_result = _parse_brightness_action(text)
        if bright_result:
            return ParsedAction(
                action_type=bright_result["type"],
                parameters=bright_result["parameters"],
                raw_text=text,
                priority=ActionPriority.MEDIUM,
            )
    
    # App control
    if action_type == "app":
        app_result = _parse_app_action(text)
        if app_result:
            return ParsedAction(
                action_type=app_result["type"],
                parameters=app_result["parameters"],
                raw_text=text,
                priority=ActionPriority.MEDIUM,
            )
    
    # Settings (wifi, bluetooth, etc.)
    if action_type == "settings":
        settings_result = _parse_settings_action(text)
        if settings_result:
            return ParsedAction(
                action_type=settings_result["type"],
                parameters=settings_result["parameters"],
                raw_text=text,
                priority=ActionPriority.MEDIUM,
            )
    
    # System actions
    if action_type == "system":
        sys_result = _parse_system_action(text)
        if sys_result:
            return ParsedAction(
                action_type=sys_result["type"],
                parameters=sys_result["parameters"],
                raw_text=text,
                priority=ActionPriority.HIGH,
            )
    
    # Generic fallback - return raw action
    return ParsedAction(
        action_type="generic",
        parameters={"text": text},
        raw_text=text,
        priority=get_action_priority(action_type),
    )


# -----------------------------------------------------------------------------
# SPECIFIC ACTION PARSERS
# -----------------------------------------------------------------------------

def _parse_whatsapp_action(text: str) -> Optional[Dict[str, Any]]:
    """Parse WhatsApp-related action."""
    low = text.lower()
    original = text  # Keep original case for message
    
    # Pattern: send <message> to <contacts>
    # Note: Include common typos like "tu" for "to"
    patterns = [
        # English patterns (with typo tolerance: tu/toh/2 for "to")
        r"(?:send|message|msg|text)\s+(?:a\s+)?(.+?)\s+(?:message\s+)?(?:to|tu|toh|2|for)\s+(.+)",
        r"(?:whatsapp)\s+(.+?)\s+(?:to|tu|toh|for)\s+(.+)",
        # Hinglish patterns
        r"(?:bhej|bhejo)\s+(.+?)\s+(?:ko|ke\s+liye)\s+(.+)",
        r"(?:send|bhej|bhejo)\s+(.+?)\s+(.+?)\s+ko",
        # Simpler fallback: send X Y where Y looks like a contact
        r"(?:send|bhej|bhejo)\s+(.+?)\s+([a-z]+(?:\s+(?:and|aur)\s+[a-z]+)?)$",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, low)
        if match:
            message = match.group(1).strip()
            recipients = match.group(2).strip()
            
            # Clean up message - remove "message" word if attached
            message = re.sub(r"^(?:a\s+)?(?:msg|message)\s+", "", message).strip()
            message = re.sub(r"\s+(?:msg|message)$", "", message).strip()
            
            # Clean up recipients
            recipients = re.sub(r"\s+on\s+whatsapp\b", "", recipients)
            recipients = re.sub(r"\s+ko$", "", recipients)
            recipients = re.sub(r"\s+(?:and|aur)\s+then\b.*$", "", recipients)  # Remove trailing 'and then...'
            
            if message and recipients:
                return {
                    "type": "whatsapp_send",
                    "parameters": {
                        "message": message,
                        "contact": recipients,
                        "contacts": recipients,
                    }
                }
    
    return None


def _parse_volume_action(text: str) -> Optional[Dict[str, Any]]:
    """Parse volume-related action."""
    low = text.lower()
    
    # Mute/unmute
    if re.search(r"\bmute\b", low) and not re.search(r"\bunmute\b", low):
        return {"type": "volume", "parameters": {"mute": True}}
    
    if re.search(r"\bunmute\b", low):
        return {"type": "volume", "parameters": {"mute": False}}
    
    # Volume percentage
    vol_match = re.search(r"(?:volume|sound|awaz)(?:\s+(?:to|at|ko))?\s*(\d+)\s*%?", low)
    if vol_match:
        level = int(vol_match.group(1))
        return {"type": "volume", "parameters": {"percent": min(100, max(0, level))}}
    
    # Volume keywords
    if re.search(r"\b(?:max|maximum|full|loudest)\b", low):
        return {"type": "volume", "parameters": {"percent": 100}}
    
    if re.search(r"\b(?:min|minimum|zero|quietest)\b", low):
        return {"type": "volume", "parameters": {"percent": 0}}
    
    if re.search(r"\b(?:half|medium|mid)\b", low):
        return {"type": "volume", "parameters": {"percent": 50}}
    
    # Increase/decrease
    if re.search(r"\b(?:increase|raise|up|louder|badhao)\b", low):
        return {"type": "volume", "parameters": {"delta": 10}}
    
    if re.search(r"\b(?:decrease|lower|down|softer|kam|ghatao)\b", low):
        return {"type": "volume", "parameters": {"delta": -10}}
    
    return None


def _parse_music_action(text: str) -> Optional[Dict[str, Any]]:
    """Parse music/playback action."""
    low = text.lower()
    
    # Stop playback
    if re.search(r"\b(?:stop|ruk|band\s+kar)\b.*\b(?:song|music|gaana|spotify|track)?\b", low):
        return {"type": "stop_music", "parameters": {}}
    
    # Pause
    if re.search(r"\b(?:pause|rok)\b.*\b(?:song|music|gaana|spotify|track)?\b", low):
        return {"type": "stop_music", "parameters": {}}
    
    # Next track
    if re.search(r"\b(?:next|skip|agla|agli)\b.*\b(?:song|music|gaana|track)?\b", low):
        return {"type": "next_song", "parameters": {}}
    
    # Previous track
    if re.search(r"\b(?:previous|prev|back|pichla|pichli)\b.*\b(?:song|music|gaana|track)?\b", low):
        return {"type": "previous_song", "parameters": {}}
    
    # Play specific song - extract actual song name
    play_patterns = [
        r"(?:play|bajao|chalao)\s+(?:song\s+)?(.+?)\s+(?:on\s+)?(?:spotify|music)$",
        r"(?:play|bajao|chalao)\s+(.+?)\s+(?:song|gaana)$",
        r"(?:play|bajao|chalao)\s+(.+?)$",
    ]
    
    for pattern in play_patterns:
        play_match = re.search(pattern, low)
        if play_match:
            song = play_match.group(1).strip()
            # Clean up: remove 'spotify', 'song', 'music' etc from song name
            song = re.sub(r"^(?:a\s+)?(?:spotify\s+)?(?:song|music|gaana)\s*$", "", song).strip()
            song = re.sub(r"\s+(?:song|music|gaana|on\s+spotify)$", "", song).strip()
            song = re.sub(r"^(?:spotify|some)\s+", "", song).strip()
            # If song is empty or just 'spotify', it's a resume command
            if not song or song.lower() in ["spotify", "song", "music", "spotify song"]:
                return {"type": "spotify_play", "parameters": {}}
            return {"type": "play_song", "parameters": {"song": song}}
    
    # Resume/play (no specific song)
    if re.search(r"\b(?:play|resume|start|shuru)\b.*\b(?:spotify|music|song)?\b", low):
        return {"type": "spotify_play", "parameters": {}}
    
    return None


def _parse_brightness_action(text: str) -> Optional[Dict[str, Any]]:
    """Parse brightness-related action."""
    low = text.lower()
    
    # Brightness percentage
    bright_match = re.search(r"(?:brightness|bright)(?:\s+(?:to|at))?\s*(\d+)\s*%?", low)
    if bright_match:
        level = int(bright_match.group(1))
        return {"type": "brightness", "parameters": {"level": min(100, max(0, level))}}
    
    # Keywords
    if re.search(r"\b(?:max|maximum|full|brightest)\b", low):
        return {"type": "brightness", "parameters": {"level": 100}}
    
    if re.search(r"\b(?:min|minimum|zero|darkest)\b", low):
        return {"type": "brightness", "parameters": {"level": 0}}
    
    if re.search(r"\b(?:half|medium|mid)\b", low):
        return {"type": "brightness", "parameters": {"level": 50}}
    
    # Increase/decrease
    if re.search(r"\b(?:increase|raise|up|brighten)\b", low):
        return {"type": "brightness", "parameters": {"level": 80}}
    
    if re.search(r"\b(?:decrease|lower|down|dim)\b", low):
        return {"type": "brightness", "parameters": {"level": 30}}
    
    return None


def _parse_app_action(text: str) -> Optional[Dict[str, Any]]:
    """Parse app-related action."""
    low = text.lower()
    
    # Close app
    close_match = re.search(r"(?:close|exit|quit|band)\s+(.+)", low)
    if close_match:
        app = close_match.group(1).strip()
        return {"type": "close_app", "parameters": {"name": app}}
    
    # Open app
    open_match = re.search(r"(?:open|launch|start|khol)\s+(.+)", low)
    if open_match:
        app = open_match.group(1).strip()
        return {"type": "open_app_start", "parameters": {"name": app}}
    
    return None


def _parse_settings_action(text: str) -> Optional[Dict[str, Any]]:
    """Parse settings-related action (wifi, bluetooth, etc.)."""
    low = text.lower()
    
    # WiFi
    if "wifi" in low or "wi-fi" in low:
        if re.search(r"\b(?:on|enable|chalu|turn\s+on)\b", low):
            return {"type": "wifi", "parameters": {"state": "on"}}
        if re.search(r"\b(?:off|disable|band|turn\s+off)\b", low):
            return {"type": "wifi", "parameters": {"state": "off"}}
        return {"type": "wifi", "parameters": {"state": "toggle"}}
    
    # Bluetooth
    if "bluetooth" in low or "bt" in low:
        if re.search(r"\b(?:on|enable|chalu|turn\s+on)\b", low):
            return {"type": "bluetooth", "parameters": {"state": "on"}}
        if re.search(r"\b(?:off|disable|band|turn\s+off)\b", low):
            return {"type": "bluetooth", "parameters": {"state": "off"}}
        return {"type": "bluetooth", "parameters": {"state": "toggle"}}
    
    # Hotspot
    if "hotspot" in low:
        if re.search(r"\b(?:on|enable|chalu)\b", low):
            return {"type": "qs_toggle", "parameters": {"name": "mobile hotspot", "state": "on"}}
        if re.search(r"\b(?:off|disable|band)\b", low):
            return {"type": "qs_toggle", "parameters": {"name": "mobile hotspot", "state": "off"}}
    
    # Airplane mode
    if "airplane" in low or "flight" in low:
        if re.search(r"\b(?:on|enable)\b", low):
            return {"type": "qs_toggle", "parameters": {"name": "airplane mode", "state": "on"}}
        if re.search(r"\b(?:off|disable)\b", low):
            return {"type": "qs_toggle", "parameters": {"name": "airplane mode", "state": "off"}}
    
    return None


def _parse_system_action(text: str) -> Optional[Dict[str, Any]]:
    """Parse system-related action."""
    low = text.lower()
    
    if re.search(r"\b(?:shutdown|shut\s+down)\b", low):
        return {"type": "power", "parameters": {"mode": "shutdown"}}
    
    if re.search(r"\b(?:restart|reboot)\b", low):
        return {"type": "power", "parameters": {"mode": "restart"}}
    
    if re.search(r"\b(?:sleep)\b", low):
        return {"type": "power", "parameters": {"mode": "sleep"}}
    
    if re.search(r"\b(?:lock)\b", low):
        return {"type": "power", "parameters": {"mode": "lock"}}
    
    if re.search(r"\b(?:hibernate)\b", low):
        return {"type": "power", "parameters": {"mode": "hibernate"}}
    
    return None


# -----------------------------------------------------------------------------
# MULTI-TASK PARSING (MAIN ENTRY)
# -----------------------------------------------------------------------------

def parse_multi_task_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse a compound command into multiple actions.
    
    Returns:
        Dict with "type": "multi_task" and "parameters" containing action list,
        or None if not a multi-task command.
    """
    if not text:
        return None
    
    # Split into segments
    segments = split_compound_command(text)
    
    if len(segments) <= 1:
        # Not a multi-task command, let regular NLU handle it
        return None
    
    # Parse each segment
    actions: List[Dict[str, Any]] = []
    execution_modes: List[str] = []
    
    for segment_text, mode in segments:
        parsed = parse_single_action(segment_text)
        if parsed:
            actions.append({
                "action_id": parsed.action_id,
                "action_type": parsed.action_type,
                "parameters": parsed.parameters,
                "priority": parsed.priority.value,
                "raw_text": parsed.raw_text,
            })
            execution_modes.append(mode.value)
    
    if len(actions) < 2:
        return None
    
    return {
        "type": "multi_task",
        "parameters": {
            "actions": actions,
            "execution_modes": execution_modes,
            "total_actions": len(actions),
            "raw_command": text,
        }
    }


# -----------------------------------------------------------------------------
# MULTI-TASK EXECUTION
# -----------------------------------------------------------------------------

def execute_multi_task(
    action: Dict[str, Any],
    executor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Execute a multi-task action.
    
    Args:
        action: The multi_task action dict
        executor: Function to execute individual actions
    
    Returns:
        Result dict with summary
    """
    params = action.get("parameters", {})
    actions = params.get("actions", [])
    
    if not actions:
        return {"ok": False, "say": "No actions to execute."}
    
    if not executor:
        return {"ok": False, "say": "No executor available."}
    
    result = MultiTaskResult(total_actions=len(actions), successful=0, failed=0)
    start_time = time.time()
    
    # Sort by priority
    sorted_actions = sorted(actions, key=lambda a: a.get("priority", 2))
    
    for act in sorted_actions:
        act_start = time.time()
        
        try:
            # Build action for executor
            single_action = {
                "type": act["action_type"],
                "parameters": act["parameters"],
            }
            
            exec_result = executor(single_action)
            act_time = time.time() - act_start
            
            action_result = ActionResult(
                action_id=act.get("action_id", ""),
                success=exec_result.get("ok", False),
                message=exec_result.get("say", ""),
                execution_time=act_time,
                metadata=exec_result.get("metadata", {}),
            )
            
            result.results.append(action_result)
            
            if action_result.success:
                result.successful += 1
            else:
                result.failed += 1
                
        except Exception as e:
            result.failed += 1
            result.results.append(ActionResult(
                action_id=act.get("action_id", ""),
                success=False,
                message=str(e),
            ))
        
        # Small delay between actions
        time.sleep(0.3)
    
    result.execution_time = time.time() - start_time
    
    return {
        "ok": result.successful > 0,
        "say": result.get_summary(),
        "metadata": {
            "total": result.total_actions,
            "successful": result.successful,
            "failed": result.failed,
            "execution_time": round(result.execution_time, 2),
        }
    }


# -----------------------------------------------------------------------------
# UTILITY FUNCTIONS
# -----------------------------------------------------------------------------

def is_multi_task_command(text: str) -> bool:
    """
    Quick check if a command looks like a multi-task command.
    More sophisticated check to avoid false positives.
    
    Returns True only if:
    1. There's a sequence connector (then, after, phir) AND the command involves 
       truly distinct tasks (not just browser+search which is one operation)
    2. There's a parallel connector AND multiple distinct action keywords that
       represent separate tasks
    """
    if not text:
        return False
    
    low = text.lower()
    
    # EXCLUSION PATTERNS: These are single compound commands, NOT multi-task
    # "open <browser> and search X" - this is ONE search action
    # "open X and click Y" - this is ONE browser automation
    exclusion_patterns = [
        # Browser + search is one compound search command
        r'\bopen\s+(?:chrome|brave|edge|firefox|browser)\s+and\s+search\b',
        # Open X in browser - one command
        r'\bopen\s+\w+\s+in\s+(?:chrome|brave|edge|firefox|browser)\b',
        # search and click is one search-with-click
        r'\bsearch\s+.+?\s+and\s+(?:click|open)\s+(?:on\s+)?(?:first|1st)\b',
        # open app and type - calculator pattern
        r'\bopen\s+(?:calc|calculator|notepad)\s+and\s+(?:type|\d)',
    ]
    
    for pattern in exclusion_patterns:
        if re.search(pattern, low, re.IGNORECASE):
            return False
    
    # First check for SEQUENCE connectors - these are strong indicators
    # But only if the tasks are truly distinct (e.g., send message THEN play song)
    for pattern in SEQUENCE_CONNECTORS:
        if re.search(pattern, low, re.IGNORECASE):
            # Verify we have distinct major task types, not just browser operations
            has_messaging = any(kw in low for kw in ['send', 'message', 'whatsapp', 'bhej'])
            has_music = any(kw in low for kw in ['play', 'spotify', 'song', 'music'])
            has_system = any(kw in low for kw in ['volume', 'brightness', 'mute', 'wifi', 'bluetooth'])
            has_power = any(kw in low for kw in ['shutdown', 'restart', 'sleep', 'hibernate'])
            
            distinct_domains = sum([has_messaging, has_music, has_system, has_power])
            if distinct_domains >= 2:
                return True
            
            # Also check if there are clearly separate action verbs with "then"
            # e.g., "do X then do Y"
            parts = re.split(r'\band\s+then\b|\bthen\b|\bphir\b|\bfir\b|\buske\s+baad\b', low, flags=re.IGNORECASE)
            if len(parts) >= 2:
                # Check if both parts have action verbs
                action_verbs = ['send', 'play', 'open', 'close', 'set', 'turn', 'mute', 'search']
                parts_with_actions = sum(1 for part in parts if any(v in part.lower() for v in action_verbs))
                if parts_with_actions >= 2:
                    return True
    
    # For PARALLEL connectors (just "and"), we need strong evidence
    # Only trigger if we have truly separate task domains
    has_parallel_connector = False
    for pattern in PARALLEL_CONNECTORS:
        if re.search(pattern, low, re.IGNORECASE):
            has_parallel_connector = True
            break
    
    if not has_parallel_connector:
        return False
    
    # For parallel connectors, require at least 2 of these major domains
    has_messaging = any(kw in low for kw in ['send', 'message', 'whatsapp', 'bhej'])
    has_music = any(kw in low for kw in ['play', 'spotify', 'song', 'music', 'gaana'])
    has_system = any(kw in low for kw in ['volume', 'brightness', 'mute', 'wifi', 'bluetooth'])
    has_power = any(kw in low for kw in ['shutdown', 'restart', 'sleep', 'hibernate'])
    
    distinct_domains = sum([has_messaging, has_music, has_system, has_power])
    return distinct_domains >= 2


def get_action_description(action: Dict[str, Any]) -> str:
    """Get a human-readable description of an action."""
    atype = action.get("action_type", "unknown")
    params = action.get("parameters", {})
    
    if atype == "whatsapp_send_multi":
        contacts = params.get("contacts", "someone")
        return f"Send message to {contacts}"
    
    if atype == "volume":
        if params.get("mute"):
            return "Mute volume"
        if params.get("percent") is not None:
            return f"Set volume to {params['percent']}%"
        return "Adjust volume"
    
    if atype.startswith("spotify_"):
        sub = atype.replace("spotify_", "")
        if sub == "play_song":
            return f"Play '{params.get('song', 'music')}'"
        return f"Spotify {sub}"
    
    if atype == "brightness":
        if params.get("level") is not None:
            return f"Set brightness to {params['level']}%"
        return "Adjust brightness"
    
    if atype == "open_app_start":
        return f"Open {params.get('name', 'app')}"
    
    if atype == "close_app":
        return f"Close {params.get('name', 'app')}"
    
    return action.get("raw_text", atype)


# -----------------------------------------------------------------------------
# TEST
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("Testing Multi-Task Parser...")
    
    test_commands = [
        "send good morning to mummy and papa then volume 100% then play hanuman chalisa",
        "open spotify and play my playlist and set volume to 80%",
        "send hi to mom then send hello to dad",
        "turn on wifi and bluetooth",
        "play music then send message hi to bro",
        "bhej hello papa ko aur mummy ko phir volume 50% kar",
        "volume 100 and brightness 80 and open chrome",
    ]
    
    for cmd in test_commands:
        print(f"\nCommand: '{cmd}'")
        print(f"Is multi-task: {is_multi_task_command(cmd)}")
        
        result = parse_multi_task_command(cmd)
        if result:
            print(f"Parsed {result['parameters']['total_actions']} actions:")
            for act in result['parameters']['actions']:
                desc = get_action_description(act)
                print(f"  - {desc} ({act['action_type']})")
        else:
            print("  Not parsed as multi-task")
