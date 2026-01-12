"""
================================================================================
VICZO_LEARNING_CORE.PY - ACTION RECORDER & PATTERN ANALYZER (1200+ lines)
Complete implementation for recording demonstrations and learning patterns
================================================================================
"""

import json
import time
import os
import threading
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import pickle
import logging

try:
    import pyautogui
    import numpy as np
    from PIL import Image, ImageGrab
    HAS_RECORDING = True
except ImportError:
    HAS_RECORDING = False

try:
    import uiautomation as auto
    HAS_UI_AUTOMATION = True
except ImportError:
    HAS_UI_AUTOMATION = False

logger = logging.getLogger(__name__)


def _notify_local(message: str):
    """Local notifier: prints and attempts to speak without importing actions (avoid circular imports)."""
    try:
        print(message)
    except Exception:
        pass
    try:
        from .tts import speak_async
        speak_async(str(message))
    except Exception:
        try:
            from src.assistant.tts import speak_async
            speak_async(str(message))
        except Exception:
            pass


# ============================================================================
# ACTION TYPE ENUMS & DATA CLASSES
# ============================================================================

class ActionType(Enum):
    """Types of actions Viczo can learn"""
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    MOUSE_DOUBLE_CLICK = "mouse_double_click"
    MOUSE_RIGHT_CLICK = "mouse_right_click"
    KEY_PRESS = "key_press"
    KEY_COMBINATION = "key_combo"
    TEXT_TYPE = "text_type"
    WAIT = "wait"
    WINDOW_FOCUS = "window_focus"
    UI_ELEMENT_CLICK = "ui_element_click"


class LearningMode(Enum):
    """Learning modes"""
    IDLE = "idle"
    RECORDING = "recording"
    ANALYZING = "analyzing"
    READY = "ready"


@dataclass
class RecordedAction:
    """Single recorded action during demonstration"""
    action_type: ActionType
    timestamp: float
    position: Optional[Tuple[int, int]] = None
    key: Optional[str] = None
    text: Optional[str] = None
    window_title: Optional[str] = None
    screenshot_path: Optional[str] = None
    ui_element: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LearnedPattern:
    """A learned pattern that can be generalized"""
    pattern_id: str
    pattern_name: str
    task_description: str
    actions: List[RecordedAction]
    generalizable: bool
    confidence_score: float
    usage_count: int = 0
    success_rate: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: List[str] = field(default_factory=list)
    learning_iterations: int = 1
    last_used: Optional[str] = None


# ============================================================================
# ACTION RECORDER - RECORDS DEMONSTRATIONS
# ============================================================================

class ActionRecorder:
    """
    Records everything you do during teaching mode.
    Captures mouse, keyboard, UI elements, and screenshots.
    Advanced recording with filtering and compression.
    """
    
    def __init__(self, output_dir: str = "viczo_recordings"):
        self.output_dir = output_dir
        self.is_recording = False
        self.recorded_actions: List[RecordedAction] = []
        self.start_time: Optional[float] = None
        self.session_id: Optional[str] = None
        self.screenshot_counter = 0
        self.recording_mode = "normal"  # normal, detailed, minimal
        self.last_action_position: Optional[Tuple[int, int]] = None
        self.last_action_time = 0.0
        
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"[RECORDER] Initialized. Output: {output_dir}")
    
    def start_recording(
        self,
        task_name: str,
        mode: str = "normal"
    ) -> str:
        """Start recording a new demonstration"""
        if self.is_recording:
            logger.warning("[RECORDER] Already recording!")
            return self.session_id or ""
        
        self.session_id = f"{task_name}_{int(time.time())}"
        self.start_time = time.time()
        self.recorded_actions = []
        self.screenshot_counter = 0
        self.is_recording = True
        self.recording_mode = mode
        self.last_action_time = 0.0
        
        session_dir = os.path.join(self.output_dir, self.session_id)
        os.makedirs(session_dir, exist_ok=True)
        
        _notify_local(f"\n{'='*70}")
        _notify_local(f"[RECORDER] 🎬 STARTED RECORDING: {task_name}")
        _notify_local(f"[RECORDER] Session ID: {self.session_id}")
        _notify_local(f"[RECORDER] Mode: {mode}")
        _notify_local(f"[RECORDER] Watching your actions...")
        _notify_local(f"{'='*70}\n")
        
        logger.info(f"Recording started: {task_name}")
        
        return self.session_id
    
    def record_mouse_click(
        self,
        x: int,
        y: int,
        button: str = "left",
        click_type: str = "single"
    ):
        """Record a mouse click with context"""
        if not self.is_recording:
            return
        
        # Take screenshot before click
        screenshot_path = self._take_screenshot("before_click")
        
        # Determine action type
        if click_type == "double":
            action_type = ActionType.MOUSE_DOUBLE_CLICK
        elif button == "right":
            action_type = ActionType.MOUSE_RIGHT_CLICK
        else:
            action_type = ActionType.MOUSE_CLICK
        
        # Get window title
        window_title = self._get_current_window_title()
        
        # Try to identify UI element at position
        ui_element = self._identify_ui_element_at(x, y)
        
        # Calculate time delta from last action
        current_time = time.time() - self.start_time
        time_delta = current_time - self.last_action_time
        self.last_action_time = current_time
        
        action = RecordedAction(
            action_type=action_type,
            timestamp=current_time,
            position=(x, y),
            window_title=window_title,
            screenshot_path=screenshot_path,
            ui_element=ui_element,
            metadata={
                "button": button,
                "click_type": click_type,
                "time_delta": time_delta,
            }
        )
        
        self.recorded_actions.append(action)
        self.last_action_position = (x, y)
        # Optionally log click activity (kept inside the method)
        logger.info(f"[RECORDER] Click at ({x}, {y}) - {window_title}")
        _notify_local(f"[RECORDER] ✓ Click at ({x}, {y})")
    
    def record_key_press(self, key: str):
        """Record a keyboard key press"""
        if not self.is_recording:
            return
        
        window_title = self._get_current_window_title()
        current_time = time.time() - self.start_time
        
        action = RecordedAction(
            action_type=ActionType.KEY_PRESS,
            timestamp=current_time,
            key=key,
            window_title=window_title,
            metadata={"time_delta": current_time - self.last_action_time}
        )
        
        self.recorded_actions.append(action)
        self.last_action_time = current_time
        logger.info(f"[RECORDER] Key: {key}")
        _notify_local(f"[RECORDER] ✓ Key: {key}")
    
    def record_key_combination(self, keys: List[str]):
        """Record a key combination (e.g., Ctrl+C)"""
        if not self.is_recording:
            return
        
        window_title = self._get_current_window_title()
        current_time = time.time() - self.start_time
        
        action = RecordedAction(
            action_type=ActionType.KEY_COMBINATION,
            timestamp=current_time,
            key="+".join(keys),
            window_title=window_title,
            metadata={"keys_count": len(keys), "time_delta": current_time - self.last_action_time}
        )
        
        self.recorded_actions.append(action)
        self.last_action_time = current_time
        logger.info(f"[RECORDER] Combo: {'+'.join(keys)}")
        _notify_local(f"[RECORDER] ✓ Combo: {'+'.join(keys)}")
    
    def record_text_input(self, text: str):
        """Record text typing"""
        if not self.is_recording:
            return
        
        window_title = self._get_current_window_title()
        current_time = time.time() - self.start_time
        
        action = RecordedAction(
            action_type=ActionType.TEXT_TYPE,
            timestamp=current_time,
            text=text,
            window_title=window_title,
            metadata={"text_length": len(text), "time_delta": current_time - self.last_action_time}
        )
        
        self.recorded_actions.append(action)
        self.last_action_time = current_time
        logger.info(f"[RECORDER] Typed: {text[:50]}...")
        _notify_local(f"[RECORDER] ✓ Typed: {text[:50]}...")
    
    def record_mouse_move(self, x: int, y: int):
        """Record significant mouse movements"""
        if not self.is_recording:
            return
        
        # Only record if it's a significant move (> 50 pixels from last position)
        if self.last_action_position:
            dx = abs(x - self.last_action_position[0])
            dy = abs(y - self.last_action_position[1])
            if dx < 50 and dy < 50:
                return  # Skip small movements
        
        current_time = time.time() - self.start_time
        
        action = RecordedAction(
            action_type=ActionType.MOUSE_MOVE,
            timestamp=current_time,
            position=(x, y),
            metadata={"time_delta": current_time - self.last_action_time}
        )
        
        self.recorded_actions.append(action)
        self.last_action_time = current_time
    
    def record_wait(self, duration: float):
        """Record a wait/pause"""
        if not self.is_recording:
            return
        
        current_time = time.time() - self.start_time
        
        action = RecordedAction(
            action_type=ActionType.WAIT,
            timestamp=current_time,
            metadata={"duration": duration}
        )
        
        self.recorded_actions.append(action)
        self.last_action_time = current_time
        logger.info(f"[RECORDER] Wait: {duration}s")
        _notify_local(f"[RECORDER] ✓ Wait: {duration}s")
    
    def stop_recording(self) -> List[RecordedAction]:
        """Stop recording and return actions"""
        if not self.is_recording:
            logger.warning("[RECORDER] Not recording!")
            return []
        
        self.is_recording = False
        
        # Take final screenshot
        self._take_screenshot("final_state")
        
        total_duration = time.time() - self.start_time if self.start_time else 0
        
        _notify_local(f"\n{'='*70}")
        _notify_local(f"[RECORDER] 🎬 STOPPED RECORDING")
        _notify_local(f"[RECORDER] Total actions: {len(self.recorded_actions)}")
        _notify_local(f"[RECORDER] Duration: {total_duration:.2f}s")
        _notify_local(f"[RECORDER] Screenshots: {self.screenshot_counter}")
        _notify_local(f"{'='*70}\n")

        logger.info(f"Recording stopped. Actions: {len(self.recorded_actions)}, Duration: {total_duration:.2f}s")
        
        # Save recording
        self._save_recording()
        
        return self.recorded_actions.copy()
    
    def _take_screenshot(self, label: str) -> str:
        """Take and save a screenshot"""
        try:
            if not HAS_RECORDING:
                return ""
            
            self.screenshot_counter += 1
            filename = f"screenshot_{self.screenshot_counter:03d}_{label}.png"
            filepath = os.path.join(self.output_dir, self.session_id or "", filename)
            
            screenshot = ImageGrab.grab()
            screenshot.save(filepath)
            
            logger.info(f"Screenshot saved: {filename}")
            _notify_local(f"Screenshot saved: {filename}")
            return filepath
        except Exception as e:
            logger.error(f"[RECORDER] Screenshot error: {e}")
            return ""
    
    def _get_current_window_title(self) -> str:
        """Get the title of the current active window"""
        try:
            if not HAS_UI_AUTOMATION:
                return "Unknown"
            
            window = auto.GetForegroundControl()
            title = getattr(window, 'Name', 'Unknown')
            return title if title else "Unknown"
        except Exception:
            return "Unknown"
    
    def _identify_ui_element_at(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        """Try to identify UI element at given position"""
        try:
            if not HAS_UI_AUTOMATION:
                return None
            
            control = auto.ControlFromPoint(x, y)
            if not control:
                return None
            
            return {
                "name": getattr(control, 'Name', ''),
                "type": getattr(control, 'ControlTypeName', ''),
                "automation_id": getattr(control, 'AutomationId', ''),
                "class_name": getattr(control, 'ClassName', ''),
                "rect": str(getattr(control, 'BoundingRectangle', '')),
            }
        except Exception:
            return None
    
    def _save_recording(self):
        """Save recording to disk"""
        try:
            filepath = os.path.join(
                self.output_dir,
                self.session_id or "",
                "recording.json"
            )
            
            # Convert actions to serializable format
            actions_data = []
            for action in self.recorded_actions:
                actions_data.append({
                    "action_type": action.action_type.value,
                    "timestamp": action.timestamp,
                    "position": action.position,
                    "key": action.key,
                    "text": action.text,
                    "window_title": action.window_title,
                    "screenshot_path": action.screenshot_path,
                    "ui_element": action.ui_element,
                    "metadata": action.metadata,
                })
            
            data = {
                "session_id": self.session_id,
                "start_time": self.start_time,
                "duration": time.time() - self.start_time if self.start_time else 0,
                "action_count": len(self.recorded_actions),
                "mode": self.recording_mode,
                "actions": actions_data,
                "saved_at": datetime.now().isoformat(),
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"[RECORDER] Saved to: {filepath}")
            print(f"[RECORDER] ✓ Saved to: {filepath}")
        
        except Exception as e:
            logger.error(f"[RECORDER] Save error: {e}")


# ============================================================================
# PATTERN ANALYZER - LEARNS FROM DEMONSTRATIONS
# ============================================================================

class PatternAnalyzer:
    """
    Analyzes recorded actions to extract learnable patterns.
    Understands which parts are specific and which can be generalized.
    """
    
    def __init__(self):
        logger.info("[ANALYZER] Initialized")
        self.analysis_history: List[Dict[str, Any]] = []
    
    def analyze_recording(
        self,
        actions: List[RecordedAction],
        task_description: str
    ) -> LearnedPattern:
        """
        Analyze a recording and extract a learnable pattern.
        
        Args:
            actions: List of recorded actions
            task_description: What task was being performed
        
        Returns:
            LearnedPattern that can be reused
        """
        _notify_local(f"\n[ANALYZER] 🧠 Analyzing {len(actions)} actions...")
        logger.info(f"[ANALYZER] Starting analysis for: {task_description}")
        
        # Extract key steps (remove noise)
        key_steps = self._extract_key_steps(actions)
        _notify_local(f"[ANALYZER] Key steps: {len(key_steps)}")
        logger.info(f"[ANALYZER] Key steps extracted: {len(key_steps)}")
        
        # Identify patterns
        patterns = self._identify_patterns(key_steps)
        _notify_local(f"[ANALYZER] Found {len(patterns)} patterns")
        
        # Determine if generalizable
        is_generalizable = self._check_generalizability(key_steps)
        _notify_local(f"[ANALYZER] Generalizable: {is_generalizable}")
        
        # Calculate confidence
        confidence = self._calculate_confidence(key_steps)
        _notify_local(f"[ANALYZER] Confidence: {confidence:.2f}")
        
        # Extract tags
        tags = self._extract_tags(task_description, key_steps)
        
        # Create pattern ID
        pattern_id = hashlib.md5(
            f"{task_description}_{time.time()}".encode()
        ).hexdigest()[:12]
        
        learned = LearnedPattern(
            pattern_id=pattern_id,
            pattern_name=task_description,
            task_description=task_description,
            actions=key_steps,
            generalizable=is_generalizable,
            confidence_score=confidence,
            tags=tags,
            learning_iterations=1,
        )
        
        _notify_local(f"[ANALYZER] ✓ Pattern learned: {pattern_id}")
        logger.info(f"[ANALYZER] Pattern created: {pattern_id}")
        
        # Record analysis
        self.analysis_history.append({
            "pattern_id": pattern_id,
            "task": task_description,
            "timestamp": datetime.now().isoformat(),
            "confidence": confidence,
            "actions_count": len(key_steps),
        })
        
        return learned
    
    def _extract_key_steps(
        self,
        actions: List[RecordedAction]
    ) -> List[RecordedAction]:
        """Extract important actions, remove noise"""
        key_steps = []
        
        for action in actions:
            # Skip excessive mouse moves
            if action.action_type == ActionType.MOUSE_MOVE:
                continue
            
            # Keep all important actions
            if action.action_type in [
                ActionType.MOUSE_CLICK,
                ActionType.MOUSE_DOUBLE_CLICK,
                ActionType.MOUSE_RIGHT_CLICK,
                ActionType.KEY_PRESS,
                ActionType.KEY_COMBINATION,
                ActionType.TEXT_TYPE,
                ActionType.WAIT,
            ]:
                key_steps.append(action)
        
        return key_steps
    
    def _identify_patterns(
        self,
        actions: List[RecordedAction]
    ) -> List[Dict[str, Any]]:
        """Identify repeating patterns in actions"""
        patterns = []
        
        for i in range(len(actions) - 2):
            sequence = actions[i:i+3]
            
            for j in range(i+3, len(actions)-2):
                compare_seq = actions[j:j+3]
                
                if self._sequences_similar(sequence, compare_seq):
                    patterns.append({
                        "type": "repeating_sequence",
                        "sequence": sequence,
                        "positions": [i, j],
                        "similarity": 1.0
                    })
        
        return patterns
    
    def _sequences_similar(
        self,
        seq1: List[RecordedAction],
        seq2: List[RecordedAction]
    ) -> bool:
        """Check if two action sequences are similar"""
        if len(seq1) != len(seq2):
            return False
        
        for a1, a2 in zip(seq1, seq2):
            if a1.action_type != a2.action_type:
                return False
        
        return True
    
    def _check_generalizability(
        self,
        actions: List[RecordedAction]
    ) -> bool:
        """Check if pattern can be generalized to similar tasks"""
        # Pattern is generalizable if:
        # 1. It has UI element information
        # 2. It follows logical steps
        # 3. It's not too specific
        
        has_ui_info = any(
            action.ui_element is not None
            for action in actions
        )
        
        has_logical_flow = len(actions) >= 3
        
        has_readable_text = any(
            action.text and len(action.text) > 2
            for action in actions
            if action.action_type == ActionType.TEXT_TYPE
        )
        
        generalizability_score = 0
        if has_ui_info:
            generalizability_score += 1
        if has_logical_flow:
            generalizability_score += 1
        if has_readable_text:
            generalizability_score += 1
        
        return generalizability_score >= 2
    
    def _calculate_confidence(
        self,
        actions: List[RecordedAction]
    ) -> float:
        """Calculate confidence score for pattern"""
        score = 0.5
        
        # More actions = more confident
        if len(actions) >= 5:
            score += 0.15
        elif len(actions) >= 3:
            score += 0.1
        
        # Has UI element info = more confident
        ui_actions = sum(
            1 for a in actions if a.ui_element is not None
        )
        if ui_actions > len(actions) * 0.5:
            score += 0.15
        elif ui_actions > 0:
            score += 0.1
        
        # Has screenshots = more confident
        screenshot_actions = sum(
            1 for a in actions if a.screenshot_path
        )
        if screenshot_actions > len(actions) * 0.5:
            score += 0.1
        
        # Has text input = more confident (indicates search, input, etc.)
        text_actions = sum(
            1 for a in actions if a.action_type == ActionType.TEXT_TYPE
        )
        if text_actions > 0:
            score += 0.05
        
        return min(1.0, score)
    
    def _extract_tags(
        self,
        task_description: str,
        actions: List[RecordedAction]
    ) -> List[str]:
        """Extract tags for categorizing the pattern"""
        tags = []
        
        # Add task-based tags
        desc_lower = task_description.lower()
        
        keywords = {
            "uninstall": ["uninstall", "remove", "delete"],
            "open_app": ["open", "launch", "start"],
            "close": ["close", "exit", "quit"],
            "file_operation": ["file", "folder", "copy", "move"],
            "search": ["search", "find", "look for"],
            "configuration": ["settings", "config", "configure"],
        }
        
        for tag, keywords_list in keywords.items():
            if any(kw in desc_lower for kw in keywords_list):
                tags.append(tag)
        
        # Add action-based tags
        action_types = set(a.action_type for a in actions)
        
        if ActionType.TEXT_TYPE in action_types:
            tags.append("text_input")
        if ActionType.KEY_COMBINATION in action_types:
            tags.append("keyboard_shortcut")
        if ActionType.MOUSE_DOUBLE_CLICK in action_types:
            tags.append("double_click")
        
        # Remove duplicates and return
        return list(set(tags))


# ============================================================================
# KNOWLEDGE BASE - STORES LEARNED PATTERNS
# ============================================================================

class KnowledgeBase:
    """
    Stores all learned patterns.
    Can retrieve relevant patterns based on task description.
    Provides advanced search and filtering capabilities.
    """
    
    def __init__(self, db_path: str = "viczo_knowledge.json"):
        self.db_path = db_path
        self.patterns: Dict[str, LearnedPattern] = {}
        self.access_count: Dict[str, int] = {}
        
        self.load()
        logger.info(f"[KNOWLEDGE] Loaded {len(self.patterns)} patterns")
    
    def add_pattern(self, pattern: LearnedPattern):
        """Add a new learned pattern"""
        self.patterns[pattern.pattern_id] = pattern
        self.access_count[pattern.pattern_id] = 0
        self.save()
        
        logger.info(f"[KNOWLEDGE] Added pattern: {pattern.pattern_name}")
        print(f"[KNOWLEDGE] ✓ Added pattern: {pattern.pattern_name}")
    
    def get_pattern(self, pattern_id: str) -> Optional[LearnedPattern]:
        """Get a specific pattern"""
        if pattern_id in self.patterns:
            self.access_count[pattern_id] = self.access_count.get(pattern_id, 0) + 1
        return self.patterns.get(pattern_id)
    
    def search_patterns(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        min_confidence: float = 0.0
    ) -> List[LearnedPattern]:
        """
        Search for relevant patterns.
        
        Args:
            query: Search query string
            tags: Optional tag filters
            min_confidence: Minimum confidence threshold
        
        Returns:
            List of matching patterns sorted by relevance
        """
        results = []
        query_lower = query.lower()
        
        for pattern in self.patterns.values():
            # Check confidence threshold
            if pattern.confidence_score < min_confidence:
                continue
            
            # Check if query matches
            if query_lower in pattern.task_description.lower():
                results.append(pattern)
                continue
            
            if query_lower in pattern.pattern_name.lower():
                results.append(pattern)
                continue
            
            # Check tags
            if tags:
                if any(tag in pattern.tags for tag in tags):
                    results.append(pattern)
                    continue
            
            # Fuzzy match on description words
            query_words = query_lower.split()
            description_lower = pattern.task_description.lower()
            matches = sum(1 for word in query_words if word in description_lower)
            if matches >= len(query_words) * 0.5:
                results.append(pattern)
        
        # Remove duplicates
        results = list(dict.fromkeys(results))
        
        # Sort by relevance
        results.sort(
            key=lambda p: (
                p.confidence_score * p.success_rate,
                self.access_count.get(p.pattern_id, 0),
                p.usage_count
            ),
            reverse=True
        )
        
        return results
    
    def update_pattern_stats(
        self,
        pattern_id: str,
        success: bool
    ):
        """Update pattern statistics after use"""
        pattern = self.patterns.get(pattern_id)
        if not pattern:
            return
        
        pattern.usage_count += 1
        pattern.last_used = datetime.now().isoformat()
        
        # Update success rate
        total_attempts = pattern.usage_count
        successes = int(pattern.success_rate * (total_attempts - 1))
        if success:
            successes += 1
        
        pattern.success_rate = successes / total_attempts
        
        logger.info(f"[KNOWLEDGE] Updated: {pattern_id} - Success rate: {pattern.success_rate:.2f}")
        
        self.save()
    
    def list_all_patterns(self) -> List[LearnedPattern]:
        """List all patterns"""
        return list(self.patterns.values())
    
    def get_pattern_statistics(self) -> Dict[str, Any]:
        """Get statistics about all patterns"""
        if not self.patterns:
            return {
                "total_patterns": 0,
                "total_uses": 0,
                "average_success_rate": 0.0,
            }
        
        total_uses = sum(p.usage_count for p in self.patterns.values())
        avg_success = sum(p.success_rate for p in self.patterns.values()) / len(self.patterns)
        
        return {
            "total_patterns": len(self.patterns),
            "total_uses": total_uses,
            "average_success_rate": avg_success,
            "patterns": [
                {
                    "name": p.pattern_name,
                    "id": p.pattern_id,
                    "uses": p.usage_count,
                    "success_rate": p.success_rate,
                    "confidence": p.confidence_score,
                    "tags": p.tags,
                }
                for p in self.patterns.values()
            ]
        }
    
    def save(self):
        """Save knowledge base to disk"""
        try:
            data = {}
            for pid, pattern in self.patterns.items():
                # Convert actions to serializable format
                actions_data = []
                for action in pattern.actions:
                    actions_data.append({
                        "action_type": action.action_type.value,
                        "timestamp": action.timestamp,
                        "position": action.position,
                        "key": action.key,
                        "text": action.text,
                        "window_title": action.window_title,
                        "screenshot_path": action.screenshot_path,
                        "ui_element": action.ui_element,
                        "metadata": action.metadata,
                    })
                
                data[pid] = {
                    "pattern_id": pattern.pattern_id,
                    "pattern_name": pattern.pattern_name,
                    "task_description": pattern.task_description,
                    "actions": actions_data,
                    "generalizable": pattern.generalizable,
                    "confidence_score": pattern.confidence_score,
                    "usage_count": pattern.usage_count,
                    "success_rate": pattern.success_rate,
                    "created_at": pattern.created_at,
                    "last_used": pattern.last_used,
                    "tags": pattern.tags,
                    "learning_iterations": pattern.learning_iterations,
                }
            
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"[KNOWLEDGE] Saved to {self.db_path}")
        
        except Exception as e:
            logger.error(f"[KNOWLEDGE] Save error: {e}")
    
    def load(self):
        """Load knowledge base from disk"""
        try:
            if not os.path.exists(self.db_path):
                logger.info(f"[KNOWLEDGE] No existing database: {self.db_path}")
                return
            
            with open(self.db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for pid, pattern_data in data.items():
                # Reconstruct actions
                actions = []
                for action_data in pattern_data["actions"]:
                    action = RecordedAction(
                        action_type=ActionType(action_data["action_type"]),
                        timestamp=action_data["timestamp"],
                        position=tuple(action_data["position"]) if action_data["position"] else None,
                        key=action_data.get("key"),
                        text=action_data.get("text"),
                        window_title=action_data.get("window_title"),
                        screenshot_path=action_data.get("screenshot_path"),
                        ui_element=action_data.get("ui_element"),
                        metadata=action_data.get("metadata", {}),
                    )
                    actions.append(action)
                
                pattern = LearnedPattern(
                    pattern_id=pattern_data["pattern_id"],
                    pattern_name=pattern_data["pattern_name"],
                    task_description=pattern_data["task_description"],
                    actions=actions,
                    generalizable=pattern_data["generalizable"],
                    confidence_score=pattern_data["confidence_score"],
                    usage_count=pattern_data.get("usage_count", 0),
                    success_rate=pattern_data.get("success_rate", 1.0),
                    created_at=pattern_data.get("created_at", ""),
                    last_used=pattern_data.get("last_used"),
                    tags=pattern_data.get("tags", []),
                    learning_iterations=pattern_data.get("learning_iterations", 1),
                )
                
                self.patterns[pid] = pattern
            
            logger.info(f"[KNOWLEDGE] Loaded {len(self.patterns)} patterns from {self.db_path}")
        
        except Exception as e:
            logger.error(f"[KNOWLEDGE] Load error: {e}")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'ActionType',
    'LearningMode',
    'RecordedAction',
    'LearnedPattern',
    'ActionRecorder',
    'PatternAnalyzer',
    'KnowledgeBase',
]
