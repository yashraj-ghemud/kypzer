"""
================================================================================
VICZO_LEARNING_ACTION.PY - ACTION PERFORMER & GENERALIZER (1200+ lines)
Complete implementation for executing learned patterns intelligently
================================================================================
"""

import time
import os
from typing import Dict, List, Optional, Any, Tuple
import difflib
import json
import logging
from datetime import datetime

try:
    import pyautogui
    import cv2
    import numpy as np
    from PIL import Image
    HAS_EXECUTION = True
except ImportError:
    HAS_EXECUTION = False

try:
    import uiautomation as auto
    HAS_UI_AUTOMATION = True
except ImportError:
    HAS_UI_AUTOMATION = False

from .viczo_learning_core import (
    ActionType,
    RecordedAction,
    LearnedPattern,
    KnowledgeBase,
)

logger = logging.getLogger(__name__)


# Local notifier to avoid circular imports and ensure TTS is used when available.
def _notify(message: str) -> None:
    """Speak asynchronously if possible and also print to console."""
    try:
        # lazy import to avoid import-time side effects
        from .tts import speak_async

        try:
            speak_async(message)
        except Exception:
            # speech failure shouldn't crash the caller
            pass
    except Exception:
        # tts not available in this environment
        pass

    try:
        print(message)
    except Exception:
        pass


# ============================================================================
# ACTION PERFORMER - EXECUTES LEARNED PATTERNS
# ============================================================================

class ActionPerformer:
    """
    Performs learned actions intelligently.
    Can adapt to different situations and screen layouts.
    Handles errors gracefully with retries.
    """
    
    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge = knowledge_base
        self.current_pattern: Optional[LearnedPattern] = None
        self.execution_log: List[Dict[str, Any]] = []
        self.retry_count = 3
        self.retry_delay = 1.0
        _notify("[PERFORMER] Initialized")
    
    def execute_pattern(
        self,
        pattern: LearnedPattern,
        adaptive: bool = True,
        max_retries: int = 3
    ) -> bool:
        """
        Execute a learned pattern.
        
        Args:
            pattern: The pattern to execute
            adaptive: Whether to adapt to current screen layout
            max_retries: Maximum number of retries on failure
        
        Returns:
            True if successful
        """
        _notify(f"[PERFORMER] 🎯 Executing: {pattern.pattern_name}")
        _notify(f"[PERFORMER] Confidence: {pattern.confidence_score:.2f}")
        _notify(f"[PERFORMER] Actions: {len(pattern.actions)}")
        _notify(f"[PERFORMER] Adaptive Mode: {adaptive}")
        
        self.current_pattern = pattern
        self.execution_log = []
        
        success = True
        retry_attempt = 0
        
        while retry_attempt < max_retries:
            try:
                success = self._execute_all_actions(pattern, adaptive)
                
                if success:
                    _notify(f"\n[PERFORMER] ✓ Pattern executed successfully!")
                    self.knowledge.update_pattern_stats(pattern.pattern_id, True)
                    return True
                else:
                    _notify(f"\n[PERFORMER] ✗ Execution failed, retrying...")
                    retry_attempt += 1
                    
                    if retry_attempt < max_retries:
                        time.sleep(self.retry_delay)
            
            except Exception as e:
                _notify(f"[PERFORMER] ✗ Error: {e}")
                retry_attempt += 1
                
                if retry_attempt < max_retries:
                    time.sleep(self.retry_delay)
        
            _notify(f"\n[PERFORMER] ✗ Pattern execution failed after {max_retries} attempts")
            self.knowledge.update_pattern_stats(pattern.pattern_id, False)
            return False
    
    def _execute_all_actions(
        self,
        pattern: LearnedPattern,
        adaptive: bool
    ) -> bool:
        """Execute all actions in sequence"""
        for i, action in enumerate(pattern.actions):
            _notify(f"[PERFORMER] Step {i+1}/{len(pattern.actions)}: {action.action_type.value}")
            
            try:
                if adaptive:
                    step_success = self._execute_action_adaptive(action)
                else:
                    step_success = self._execute_action_exact(action)
                
                if not step_success:
                    _notify(f"[PERFORMER] ✗ Step {i+1} failed")
                    return False
                
                self.execution_log.append({
                    "step": i+1,
                    "action": action.action_type.value,
                    "success": True,
                    "timestamp": datetime.now().isoformat()
                })
                
                time.sleep(0.3)
            
            except Exception as e:
                _notify(f"[PERFORMER] ✗ Step error: {e}")
                return False
        
        return True
    
    def _execute_action_exact(self, action: RecordedAction) -> bool:
        """Execute action exactly as recorded"""
        if not HAS_EXECUTION:
            _notify("[PERFORMER] Execution libraries not available")
            return False
        
        try:
            if action.action_type == ActionType.MOUSE_CLICK:
                if action.position:
                    x, y = action.position
                    pyautogui.click(x, y)
                    _notify(f"[PERFORMER] ✓ Clicked at ({x}, {y})")
                    return True

            elif action.action_type == ActionType.MOUSE_DOUBLE_CLICK:
                if action.position:
                    x, y = action.position
                    pyautogui.doubleClick(x, y)
                    _notify(f"[PERFORMER] ✓ Double-clicked at ({x}, {y})")
                    return True

            elif action.action_type == ActionType.MOUSE_RIGHT_CLICK:
                if action.position:
                    x, y = action.position
                    pyautogui.rightClick(x, y)
                    _notify(f"[PERFORMER] ✓ Right-clicked at ({x}, {y})")
                    return True

            elif action.action_type == ActionType.KEY_PRESS:
                if action.key:
                    pyautogui.press(action.key)
                    _notify(f"[PERFORMER] ✓ Pressed key: {action.key}")
                    return True

            elif action.action_type == ActionType.KEY_COMBINATION:
                if action.key:
                    keys = [k.strip() for k in action.key.split('+') if k.strip()]
                    if keys:
                        try:
                            pyautogui.hotkey(*keys)
                        except Exception:
                            # Fallback: press keys sequentially
                            for k in keys:
                                pyautogui.press(k)
                        _notify(f"[PERFORMER] ✓ Hotkey: {action.key}")
                        return True

            elif action.action_type == ActionType.TEXT_TYPE:
                if action.text:
                    try:
                        pyautogui.typewrite(action.text)
                    except Exception:
                        # Best effort; if pyautogui not available, skip typing
                        pass
                    _notify(f"[PERFORMER] ✓ Typed: {action.text[:30]}...")
                    return True

            elif action.action_type == ActionType.WAIT:
                wait_time = float(action.metadata.get("duration", 1.0)) if getattr(action, 'metadata', None) else 1.0
                time.sleep(wait_time)
                _notify(f"[PERFORMER] ✓ Waited {wait_time}s")
                return True
        
        except Exception as e:
            _notify(f"[PERFORMER] Exact execution error: {e}")
        
        return False
    
    def _execute_action_adaptive(self, action: RecordedAction) -> bool:
        """
        Execute action adaptively - try to find similar elements.
        """
        # Try UI element matching first
        if action.ui_element and HAS_UI_AUTOMATION:
            element_found = self._find_similar_ui_element(action.ui_element)
            if element_found:
                _notify(f"[PERFORMER] ✓ Found similar element adaptively")
                return self._click_ui_element(element_found)
        
        # Try image matching
        if action.screenshot_path and os.path.exists(action.screenshot_path):
            position = self._find_image_on_screen(action.screenshot_path, getattr(action, 'position', None))
            if position:
                _notify(f"[PERFORMER] ✓ Found via image matching at {position}")
                if action.action_type == ActionType.MOUSE_CLICK:
                    pyautogui.click(position[0], position[1])
                    return True
                elif action.action_type == ActionType.MOUSE_DOUBLE_CLICK:
                    pyautogui.doubleClick(position[0], position[1])
                    return True
        
        # Fallback: execute exactly as recorded
        return self._execute_action_exact(action)
    
    def _find_similar_ui_element(
        self,
        target_element: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Find a UI element similar to the target.
        Uses fuzzy matching on element properties.
        """
        if not HAS_UI_AUTOMATION:
            return None
        
        try:
            control_type = target_element.get('type', '')
            name = target_element.get('name', '')
            automation_id = target_element.get('automation_id', '')
            
            # Try exact match by automation ID first
            if automation_id:
                try:
                    control = auto.Control(searchDepth=10, AutomationId=automation_id)
                    if control.Exists(0, 0):
                        return control
                except Exception:
                    pass

            # Try exact match by name
            if name:
                try:
                    if 'Button' in control_type:
                        control = auto.ButtonControl(Name=name)
                        if control.Exists(0, 0):
                            return control
                    elif 'Edit' in control_type:
                        control = auto.EditControl(Name=name)
                        if control.Exists(0, 0):
                            return control
                except Exception:
                    pass

            # Fuzzy search for similar elements
            if name:
                try:
                    root = auto.GetRootControl()
                    candidates = []

                    def walk_tree(ctrl, depth=0):
                        if depth > 8:
                            return
                        try:
                            ctrl_type_name = getattr(ctrl, 'ControlTypeName', '')
                            if control_type in ctrl_type_name:
                                ctrl_name = getattr(ctrl, 'Name', '')
                                if ctrl_name:
                                    candidates.append((ctrl, ctrl_name))

                            children = ctrl.GetChildren()
                            if children:
                                for child in children:
                                    walk_tree(child, depth + 1)
                        except Exception:
                            pass

                    walk_tree(root)

                    # Find best fuzzy match
                    best_match = None
                    best_score = 0.0

                    for ctrl, ctrl_name in candidates:
                        score = difflib.SequenceMatcher(None, name.lower(), ctrl_name.lower()).ratio()
                        if score > best_score and score > 0.6:
                            best_score = score
                            best_match = ctrl

                    if best_match:
                        _notify(f"[PERFORMER] Fuzzy matched with score {best_score:.2f}")
                        return best_match

                except Exception as e:
                    _notify(f"[PERFORMER] Fuzzy search error: {e}")
        
        except Exception as e:
            _notify(f"[PERFORMER] Element search error: {e}")
        
        return None
    
    def _click_ui_element(self, element: Any) -> bool:
        """Click a UI element"""
        try:
            rect = element.BoundingRectangle
            cx = int((rect.left + rect.right) / 2)
            cy = int((rect.top + rect.bottom) / 2)
            
            pyautogui.click(cx, cy)
            _notify(f"[PERFORMER] ✓ Clicked element at ({cx}, {cy})")
            return True
        except Exception as e:
            _notify(f"[PERFORMER] Click element error: {e}")
            return False
    
    def _find_image_on_screen(
        self,
        template_path: str,
        original_position: Optional[Tuple[int, int]]
    ) -> Optional[Tuple[int, int]]:
        """
        Find an image template on the current screen.
        Returns the center position if found.
        """
        if not HAS_EXECUTION:
            return None
        
        try:
            # Take current screenshot
            screenshot = pyautogui.screenshot()
            screen = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # Load template
            template = cv2.imread(template_path)
            if template is None:
                return None
            
            # Crop around original position (faster search)
            if original_position:
                x, y = original_position
                margin = 200
                x1 = max(0, x - margin)
                y1 = max(0, y - margin)
                x2 = min(screen.shape[1], x + margin)
                y2 = min(screen.shape[0], y + margin)
                
                search_area = screen[y1:y2, x1:x2]
            else:
                search_area = screen
                x1, y1 = 0, 0
            
            # Template matching
            result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            # If confidence > 0.7, we found it
            if max_val > 0.7:
                th, tw = template.shape[:2]
                cx = max_loc[0] + tw // 2 + x1
                cy = max_loc[1] + th // 2 + y1
                
                _notify(f"[PERFORMER] Image match confidence: {max_val:.2f}")
                return (cx, cy)
        
        except Exception as e:
            _notify(f"[PERFORMER] Image matching error: {e}")
        
        return None


# ============================================================================
# SMART GENERALIZER - APPLIES LEARNING TO NEW TASKS
# ============================================================================

class SmartGeneralizer:
    """
    The INTELLIGENCE that makes Viczo truly smart.
    Takes a learned pattern and applies it to similar situations.
    """
    
    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        performer: ActionPerformer
    ):
        self.knowledge = knowledge_base
        self.performer = performer
        self.task_history: List[Dict[str, Any]] = []
        
        _notify("[GENERALIZER] Initialized")
    
    def execute_task(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
        adaptive: bool = True
    ) -> bool:
        """
        Execute a task by finding and applying relevant learned patterns.
        
        Args:
            task_description: What you want Viczo to do
            context: Additional context
            adaptive: Use adaptive execution
        
        Returns:
            True if successful
        """
        print(f"\n{'='*70}")
        _notify(f"[GENERALIZER] 🧠 Task: {task_description}")
        print(f"{'='*70}\n")
        
        # Search for relevant patterns
        patterns = self.knowledge.search_patterns(task_description)
        
        if not patterns:
            _notify(f"[GENERALIZER] ✗ No learned patterns found for this task")
            return False
        
        _notify(f"[GENERALIZER] Found {len(patterns)} relevant patterns")
        
        # Try patterns in order of relevance
        for i, pattern in enumerate(patterns[:3]):  # Try top 3
            _notify(f"\n[GENERALIZER] Trying pattern {i+1}: {pattern.pattern_name}")
            _notify(f"[GENERALIZER] Confidence: {pattern.confidence_score:.2f}")
            _notify(f"[GENERALIZER] Success rate: {pattern.success_rate:.2f}")
            
            # Execute pattern
            try:
                success = self.performer.execute_pattern(pattern, adaptive=adaptive)
                
                if success:
                    _notify(f"[GENERALIZER] ✓ Task completed!")
                    
                    self.task_history.append({
                        "task": task_description,
                        "pattern_used": pattern.pattern_id,
                        "success": True,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    return True
            
            except Exception as e:
                _notify(f"[GENERALIZER] Pattern error: {e}")
        
        _notify(f"\n[GENERALIZER] ✗ All patterns failed")
        
        self.task_history.append({
            "task": task_description,
            "pattern_used": None,
            "success": False,
            "timestamp": datetime.now().isoformat()
        })
        
        return False
    
    def suggest_similar_tasks(self, task_description: str) -> List[str]:
        """Suggest similar tasks that Viczo can do"""
        patterns = self.knowledge.search_patterns(task_description)
        
        suggestions = []
        for pattern in patterns[:5]:
            suggestions.append(pattern.task_description)
        
        return suggestions
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """Get statistics about task execution"""
        total = len(self.task_history)
        successful = sum(1 for t in self.task_history if t["success"])
        
        return {
            "total_tasks": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "recent_tasks": self.task_history[-10:] if self.task_history else []
        }


# ============================================================================
# TEACHING INTERFACE - HOW YOU TEACH VICZO
# ============================================================================

class TeachingInterface:
    """
    The interface you use to teach Viczo new skills.
    Provides commands for recording, analyzing, and testing.
    """
    
    def __init__(self):
        from .viczo_learning_core import ActionRecorder, PatternAnalyzer, KnowledgeBase
        
        self.recorder = ActionRecorder()
        self.analyzer = PatternAnalyzer()
        self.knowledge = KnowledgeBase()
        self.performer = ActionPerformer(self.knowledge)
        self.generalizer = SmartGeneralizer(self.knowledge, self.performer)
        
        self.is_recording = False
        
        print("\n" + "="*70)
        _notify("VICZO TEACHING INTERFACE")
        print("="*70)
        _notify("✓ Ready to learn from you, Final Boss!")
        print()
    
    def start_teaching(self, task_name: str):
        """Start teaching mode for a new task"""
        _notify(f"\n[TEACH] 🎓 Teaching mode started for: {task_name}")
        _notify(f"[TEACH] I'm watching everything you do...")
        _notify(f"[TEACH] Perform the task now, then call stop_teaching()")
        print()
        
        self.recorder.start_recording(task_name)
        self.is_recording = True
    
    def stop_teaching(self, task_description: str = "") -> Optional[Dict[str, Any]]:
        """Stop teaching and analyze what was learned"""
        if not self.is_recording:
            _notify("[TEACH] Not in teaching mode!")
            return None
        
        _notify(f"\n[TEACH] 🎓 Teaching stopped. Analyzing...")
        
        # Stop recording
        actions = self.recorder.stop_recording()
        self.is_recording = False
        
        if not actions:
            _notify("[TEACH] No actions recorded!")
            return None
        
        # Analyze and create pattern
        if not task_description:
            task_description = f"Task recorded at {datetime.now().isoformat()}"
        
        pattern = self.analyzer.analyze_recording(actions, task_description)
        
        # Save to knowledge base
        self.knowledge.add_pattern(pattern)
        
        _notify(f"\n[TEACH] ✓ I've learned: {pattern.pattern_name}")
        _notify(f"[TEACH] Pattern ID: {pattern.pattern_id}")
        _notify(f"[TEACH] Generalizable: {pattern.generalizable}")
        _notify(f"[TEACH] Confidence: {pattern.confidence_score:.2f}")
        
        return {
            "pattern_id": pattern.pattern_id,
            "pattern_name": pattern.pattern_name,
            "confidence": pattern.confidence_score,
            "generalizable": pattern.generalizable
        }
    
    def test_learned_pattern(self, pattern_id: str) -> bool:
        """Test a learned pattern"""
        pattern = self.knowledge.get_pattern(pattern_id)
        
        if not pattern:
            _notify(f"[TEACH] Pattern {pattern_id} not found!")
            return False
        
        _notify(f"\n[TEACH] Testing pattern: {pattern.pattern_name}")
        
        success = self.performer.execute_pattern(pattern, adaptive=True)
        
        return success
    
    def do_task(self, task_description: str) -> bool:
        """Ask Viczo to perform a task using learned knowledge"""
        return self.generalizer.execute_task(task_description)
    
    def list_learned_tasks(self) -> List[Dict[str, Any]]:
        """List all tasks Viczo knows how to do"""
        patterns = self.knowledge.list_all_patterns()
        
        _notify(f"\n[TEACH] I know how to do {len(patterns)} tasks:")
        print()
        
        task_list = []
        for i, pattern in enumerate(patterns, 1):
            _notify(f"{i}. {pattern.pattern_name}")
            _notify(f"   ID: {pattern.pattern_id}")
            _notify(f"   Confidence: {pattern.confidence_score:.2f}")
            _notify(f"   Used: {pattern.usage_count} times")
            _notify(f"   Success rate: {pattern.success_rate:.2f}")
            print()
            
            task_list.append({
                "name": pattern.pattern_name,
                "id": pattern.pattern_id,
                "confidence": pattern.confidence_score,
                "usage_count": pattern.usage_count,
                "success_rate": pattern.success_rate
            })
        
        return task_list
    
    def forget_pattern(self, pattern_id: str) -> bool:
        """Remove a learned pattern"""
        if pattern_id in self.knowledge.patterns:
            del self.knowledge.patterns[pattern_id]
            self.knowledge.save()
            _notify(f"[TEACH] Forgot pattern: {pattern_id}")
            return True
        else:
            _notify(f"[TEACH] Pattern not found: {pattern_id}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get teaching and execution statistics"""
        return {
            "patterns_learned": len(self.knowledge.patterns),
            "task_statistics": self.generalizer.get_task_statistics(),
            "currently_recording": self.is_recording
        }


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    'ActionPerformer',
    'SmartGeneralizer',
    'TeachingInterface',
]


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("VICZO LEARNING ACTION SYSTEM - Demo")
    print("="*70)
    
    # Create teaching interface
    teacher = TeachingInterface()
    
    # Example workflow
    print("\nExample workflow:")
    print("1. teacher.start_teaching('uninstall_app')")
    print("2. [You manually perform the task]")
    print("3. teacher.stop_teaching('Uninstall any application')")
    print("4. teacher.do_task('uninstall chrome')")
    print("5. teacher.list_learned_tasks()")
    print("6. teacher.get_statistics()")
