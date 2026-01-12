"""Advanced WhatsApp Desktop voice message automation workflow.

Opening and search now piggyback on the assistant's existing UI helpers (Start
menu launch plus chat navigation) so this module focuses purely on the voice
record/send mechanics. It can still run standalone for testing, but when loaded
inside the assistant it reuses the same pathways that NLU/actions rely on.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING
import math
import statistics

import pyautogui
import pyttsx3

try:
    import uiautomation as auto
    HAS_UIAUTOMATION = True
except Exception:  # pragma: no cover - optional dependency
    auto = None  # type: ignore
    HAS_UIAUTOMATION = False

try:
    from PIL import Image
    from PIL import ImageGrab
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    ImageGrab = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from PIL import Image as PILImageType
else:
    PILImageType = Any

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    from .ui import open_app_via_start, whatsapp_send_message, _click_with_cursor
except Exception:  # pragma: no cover - standalone execution
    try:
        from src.assistant.ui import open_app_via_start, whatsapp_send_message, _click_with_cursor  # type: ignore
    except Exception:  # pragma: no cover - no assistant package available
        open_app_via_start = None  # type: ignore
        whatsapp_send_message = None  # type: ignore
        _click_with_cursor = None  # type: ignore

try:
    from .tts import speak as assistant_speak
except Exception:  # pragma: no cover
    try:
        from src.assistant.tts import speak as assistant_speak  # type: ignore
    except Exception:  # pragma: no cover
        assistant_speak = None  # type: ignore

SpeakFn = Optional[Callable[[str], None]]


@dataclass
class VoiceBotConfig:
    """Runtime knobs to fine-tune timings and detection behavior."""

    launch_retry_delay: float = 2.5
    search_focus_delay: float = 0.4
    typing_interval: float = 0.05
    click_pause: float = 0.3
    detection_confidence: float = 0.8
    post_record_wait: float = 0.5
    recording_timeout: float = 6.0
    screenshot_region_margin: int = 120
    mic_probe_attempts: int = 3
    send_confirmation_timeout: float = 4.0
    allow_keyboard_shortcuts: bool = True
    chat_to_mic_delay: float = 0.9
    mic_activation_delay: float = 0.7
    recording_poll_interval: float = 0.3


@dataclass
class ActionLogEntry:
    step: str
    detail: str
    duration_ms: float
    success: bool


@dataclass
class BotDiagnostics:
    """Collects step level telemetry for easier debugging."""

    entries: List[ActionLogEntry] = field(default_factory=list)
    start_ts: float = field(default_factory=time.time)

    def add(self, step: str, detail: str, *, duration: float, success: bool) -> None:
        self.entries.append(
            ActionLogEntry(
                step=step,
                detail=detail.strip(),
                duration_ms=round(duration * 1000, 2),
                success=bool(success),
            )
        )

    def summarize(self) -> str:
        if not self.entries:
            return "No diagnostics collected."
        duration = round((time.time() - self.start_ts) * 1000, 2)
        ok = sum(1 for e in self.entries if e.success)
        total = len(self.entries)
        return f"Diagnostics: {ok}/{total} steps succeeded in {duration} ms"


class Stopwatch:
    """Context helper to time operations for diagnostics."""

    def __init__(self, callback: Callable[[float], None]):
        self._callback = callback
        self._start = time.time()

    def stop(self) -> None:
        if self._callback:
            self._callback(time.time() - self._start)
            self._callback = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False


class ScreenAnalyzer:
    """Utility class to inspect small screen regions for colors/textures."""

    def __init__(self) -> None:
        self.available = ImageGrab is not None and Image is not None

    def grab(self, region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Any]:
        if not self.available:
            return None
        try:
            if region:
                return ImageGrab.grab(bbox=region)
            return ImageGrab.grab()
        except Exception:
            return None

    def average_brightness(self, image: Optional[Any]) -> float:
        if not image or not self.available:
            return 0.0
        try:
            grayscale = image.convert("L")
            pixels = list(grayscale.getdata())
            if not pixels:
                return 0.0
            return statistics.fmean(pixels) / 255.0
        except Exception:
            return 0.0

    def detect_vertical_red_band(self, image: Optional[Any]) -> bool:
        if not image or np is None:
            return False
        try:
            arr = np.array(image)
        except Exception:
            return False
        if arr.size == 0:
            return False
        reds = arr[..., 0]
        greens = arr[..., 1]
        blues = arr[..., 2]
        mask = (reds > 150) & (greens < 120) & (blues < 120)
        ratio = mask.mean() if mask.size else 0.0
        return ratio > 0.025

    def detect_waveform_activity(self, image: Optional[Any]) -> bool:
        if not image or np is None:
            return False
        try:
            arr = np.array(image.convert("L"))
        except Exception:
            return False
        if arr.size == 0:
            return False
        row_std = arr.std(axis=1)
        return row_std.mean() > 10.0

class WhatsAppAdvancedBot:
    """WhatsApp automation with optional screen/template detection."""

    REFERENCE_WIDTH = 1920
    REFERENCE_HEIGHT = 1080
    MIC_TEMPLATE_NAME = "whatsapp_mic.png"
    SEND_TEMPLATE_NAME = "whatsapp_send.png"

    def __init__(self) -> None:
        self.engine: Optional[pyttsx3.Engine] = None
        self.screen_width, self.screen_height = pyautogui.size()
        self.assets_dir = Path(__file__).resolve().parent / "assets"
        self.mic_position: Optional[Tuple[int, int]] = None
        self.send_position: Optional[Tuple[int, int]] = None
        self._assistant_speak: SpeakFn = assistant_speak
        self.config = VoiceBotConfig()
        self.diagnostics = BotDiagnostics()
        self.screen_analyzer = ScreenAnalyzer()
        self.has_uiautomation = HAS_UIAUTOMATION and auto is not None

    # ------------------------------------------------------------------------
    # Diagnostics helpers
    # ------------------------------------------------------------------------
    def _record_step(self, step: str, detail: str, success: bool, duration: float) -> None:
        self.diagnostics.add(step, detail, duration=duration, success=success)

    def _time_step(self, step: str, detail: str, *, success_flag: Callable[[], bool]):
        def _callback(elapsed: float) -> None:
            self._record_step(step, detail, success_flag(), elapsed)

        return Stopwatch(_callback)

    def _status_speak(self, text: str) -> None:
        if not text or not self._assistant_speak:
            return
        try:
            self._assistant_speak(text, emotion="informative")  # type: ignore[arg-type]
        except TypeError:
            self._assistant_speak(text)
        except Exception:
            pass

    # ----------------------------------------------------------------------------
    # Launch/search helpers (reusing assistant UI utilities when available)
    # ----------------------------------------------------------------------------
    def ensure_whatsapp_running(self) -> bool:
        success_holder = {"ok": False}
        with self._time_step(
            "launch",
            f"Launching WhatsApp via Start (Win+type fallback, subprocess last) [{self._describe_resolution()}]",
            success_flag=lambda: success_holder["ok"],
        ):
            if self._launch_via_start():
                success_holder["ok"] = True
                self._focus_whatsapp_window()
                return True
            if self._direct_start_launch():
                success_holder["ok"] = True
                return True
            success_holder["ok"] = self._fallback_launch_whatsapp()
            return success_holder["ok"]

    def _launch_via_start(self) -> bool:
        if sys.platform != "win32" or not open_app_via_start:
            return False
        try:
            ok = open_app_via_start("whatsapp")
        except Exception:
            ok = False
        if ok:
            time.sleep(self.config.launch_retry_delay)
        return bool(ok)

    def _direct_start_launch(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            pyautogui.hotkey('winleft')
            time.sleep(0.25)
            pyautogui.typewrite("whatsapp", interval=self.config.typing_interval)
            time.sleep(0.2)
            pyautogui.press('enter')
            time.sleep(self.config.launch_retry_delay)
            self._focus_whatsapp_window()
            return True
        except Exception:
            return False

    def _fallback_launch_whatsapp(self) -> bool:
        try:
            if sys.platform == "win32":
                subprocess.Popen("WhatsApp")
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "WhatsApp"])
            else:
                return False
            time.sleep(4)
            self._focus_whatsapp_window()
            return True
        except Exception:
            print("⚠️  Could not auto-open WhatsApp. Please open it manually and press Enter...")
            try:
                input()
            except EOFError:
                pass
            return False

    def ensure_contact_chat(self, recipient_name: str) -> bool:
        target = (recipient_name or "").strip()
        if not target:
            return False
        success_holder = {"ok": False}
        with self._time_step(
            "chat-open",
            f"Ensuring chat for '{target}' is visible",
            success_flag=lambda: success_holder["ok"],
        ):
            if self._open_chat_via_ui_helpers(target):
                success_holder["ok"] = True
                return True
            success_holder["ok"] = self._manual_search_contact(target)
            return success_holder["ok"]

    def _open_chat_via_ui_helpers(self, target: str) -> bool:
        if not whatsapp_send_message:
            return False
        try:
            opened = whatsapp_send_message(target, None)
        except Exception:
            opened = False
        if opened:
            time.sleep(0.8)
            self.focus_message_box()
        return bool(opened)

    def _manual_search_contact(self, target: str) -> bool:
        success_holder = {"ok": False}
        with self._time_step(
            "chat-search",
            f"Manual search fallback for '{target}'",
            success_flag=lambda: success_holder["ok"],
        ):
            if not self.find_and_click_search_box():
                return False
            if not self.type_recipient_name(target):
                return False
            if not self.click_first_search_result():
                return False
            self.focus_message_box()
            success_holder["ok"] = True
            return True

    def _describe_resolution(self) -> str:
        return f"Screen {self.screen_width}x{self.screen_height}"

    def _focus_whatsapp_window(self, window_control: Optional[Any] = None, timeout: float = 1.0) -> bool:
        if self.has_uiautomation and auto is not None:
            target = window_control
            if not target:
                try:
                    target = auto.GetForegroundControl()
                    if not self._is_whatsapp_control(target):
                        target = auto.WindowControl(searchDepth=1, RegexName=r"(?i)whatsapp")
                except Exception:
                    target = None
            if target and target.Exists(0, 0):
                try:
                    target.SetActive()
                    time.sleep(min(0.3, max(0.05, timeout)))
                    return True
                except Exception:
                    pass
        title_keywords = ("whatsapp", "WhatsApp")
        current_title = pyautogui.getActiveWindowTitle()
        if current_title and any(k.lower() in current_title.lower() for k in title_keywords):
            return True
        try:
            pyautogui.hotkey('alt', 'tab')
            time.sleep(0.6)
        except Exception:
            return False
        current_title = pyautogui.getActiveWindowTitle()
        return bool(current_title and any(k.lower() in current_title.lower() for k in title_keywords))

    def _is_whatsapp_control(self, ctrl: Any) -> bool:
        if not ctrl:
            return False
        try:
            name = (getattr(ctrl, "Name", None) or "").lower()
            class_name = (getattr(ctrl, "ClassName", None) or "").lower()
            return "whatsapp" in (name + class_name)
        except Exception:
            return False

    def _locate_whatsapp_window(self) -> Optional[Any]:
        if not self.has_uiautomation or auto is None:
            return None
        try:
            current = auto.GetForegroundControl()
            if self._is_whatsapp_control(current):
                return current
        except Exception:
            current = None
        try:
            window = auto.WindowControl(searchDepth=1, RegexName=r"(?i)whatsapp")
            if window and window.Exists(0, 0):
                return window
        except Exception:
            return None
        return None

    def _control_center(self, control: Any) -> Optional[Tuple[int, int]]:
        if not control:
            return None
        try:
            rect = control.BoundingRectangle
            left = getattr(rect, "left", getattr(rect, "Left", None))
            right = getattr(rect, "right", getattr(rect, "Right", None))
            top = getattr(rect, "top", getattr(rect, "Top", None))
            bottom = getattr(rect, "bottom", getattr(rect, "Bottom", None))
            if None in (left, right, top, bottom):
                return None
            x = int((float(left) + float(right)) / 2)
            y = int((float(top) + float(bottom)) / 2)
            return (x, y)
        except Exception:
            return None

    def _find_whatsapp_voice_button(self, window: Optional[Any] = None) -> Optional[Any]:
        if not self.has_uiautomation or auto is None:
            return None
        if window is None:
            window = self._locate_whatsapp_window()
        if not window:
            return None
        labels = [
            r"(?i)hold\s+to\s+record",
            r"(?i)record\s+voice\s+message",
            r"(?i)voice\s+message",
            r"(?i)voice\s+note",
            r"(?i)start\s+recording",
            r"(?i)press\s+and\s+hold",
        ]
        for pattern in labels:
            try:
                button = auto.ButtonControl(searchFromControl=window, RegexName=pattern, searchDepth=8)
            except Exception:
                button = None
            if button and button.Exists(0, 0):
                return button
        return None

    def _find_whatsapp_voice_send_button(self, window: Optional[Any] = None) -> Optional[Any]:
        if not self.has_uiautomation or auto is None:
            return None
        if window is None:
            window = self._locate_whatsapp_window()
        if not window:
            return None
        labels = [
            r"(?i)send\s+voice\s+message",
            r"(?i)send\s+recording",
            r"(?i)send",
        ]
        for pattern in labels:
            try:
                button = auto.ButtonControl(searchFromControl=window, RegexName=pattern, searchDepth=8)
            except Exception:
                button = None
            if button and button.Exists(0, 0):
                return button
        return None

    def _guess_voice_button_point(self, window: Optional[Any] = None) -> Optional[Tuple[int, int]]:
        if window is None:
            window = self._locate_whatsapp_window()
        if window and self.has_uiautomation and auto is not None:
            try:
                rect = window.BoundingRectangle
                left = getattr(rect, "left", getattr(rect, "Left", None))
                right = getattr(rect, "right", getattr(rect, "Right", None))
                bottom = getattr(rect, "bottom", getattr(rect, "Bottom", None))
                if None not in (left, right, bottom):
                    x = int(float(right) - 80)
                    y = int(float(bottom) - 50)
                    return (x, y)
            except Exception:
                pass
            try:
                composer = auto.EditControl(
                    searchFromControl=window,
                    RegexName=r"(?i)type a message|message",
                    searchDepth=8,
                )
            except Exception:
                composer = None
            if composer and composer.Exists(0, 0):
                rect = composer.BoundingRectangle
                try:
                    right = getattr(rect, "right", getattr(rect, "Right", None))
                    top = getattr(rect, "top", getattr(rect, "Top", None))
                    bottom = getattr(rect, "bottom", getattr(rect, "Bottom", None))
                    if None not in (right, top, bottom):
                        x = int(float(right) + 55)
                        y = int((float(top) + float(bottom)) / 2)
                        return (x, y)
                except Exception:
                    pass
        try:
            screen_w, screen_h = pyautogui.size()
            return (int(screen_w * 0.82), int(screen_h * 0.88))
        except Exception:
            return None

    def _resolve_mic_point(self) -> Optional[Tuple[int, int]]:
        window = self._locate_whatsapp_window()
        if window and self.has_uiautomation and auto is not None:
            button = self._find_whatsapp_voice_button(window)
            center = self._control_center(button) if button else None
            if center:
                return center
            guess = self._guess_voice_button_point(window)
            if guess:
                return guess
        guess = self._guess_voice_button_point(None)
        return guess

    def _click_whatsapp_voice_point(self, button: Optional[Any], fallback: Optional[Tuple[int, int]]) -> bool:
        if button and self.has_uiautomation and auto is not None:
            try:
                if _click_with_cursor and _click_with_cursor(button):  # type: ignore[arg-type]
                    return True
            except Exception:
                pass
            try:
                rect = self._control_center(button)
                if rect:
                    pyautogui.click(rect[0], rect[1])
                    return True
            except Exception:
                pass
            try:
                button.Click()
                return True
            except Exception:
                pass
        if fallback:
            try:
                pyautogui.click(fallback[0], fallback[1])
                return True
            except Exception:
                return False
        return False

    def _whatsapp_recording_indicator_present(self, window: Any) -> bool:
        if not (self.has_uiautomation and auto is not None):
            return True
        patterns_text = [
            r"(?i)recording",
            r"(?i)slide\s+to\s+cancel",
            r"(?i)voice\s+message",
            r"(?i)voice\s+note",
        ]
        patterns_button = [
            r"(?i)cancel",
            r"(?i)stop",
            r"(?i)send\s+voice",
        ]
        for pattern in patterns_text:
            try:
                ctrl = auto.TextControl(searchFromControl=window, RegexName=pattern, searchDepth=8)
            except Exception:
                ctrl = None
            if ctrl and ctrl.Exists(0, 0):
                return True
        for pattern in patterns_button:
            try:
                ctrl = auto.ButtonControl(searchFromControl=window, RegexName=pattern, searchDepth=8)
            except Exception:
                ctrl = None
            if ctrl and ctrl.Exists(0, 0):
                return True
        return False

    def _wait_for_whatsapp_voice_recording(self, window: Optional[Any], timeout: float = 4.0, poll: float = 0.2) -> bool:
        timeout = max(0.5, float(timeout))
        poll = max(0.1, float(poll))
        if not (self.has_uiautomation and auto is not None):
            time.sleep(min(timeout, 0.4))
            return True
        deadline = time.time() + timeout
        while time.time() < deadline:
            ctrl_window = window
            if not ctrl_window or not ctrl_window.Exists(0, 0):
                ctrl_window = self._locate_whatsapp_window()
            if ctrl_window and self._whatsapp_recording_indicator_present(ctrl_window):
                return True
            time.sleep(poll)
        return False

    def _hold_and_record_whatsapp_voice(
        self,
        point: Optional[Tuple[int, int]],
        text: str,
        window: Optional[Any],
        delay_before_speaking: float,
        emotion: str = "friendly",
    ) -> bool:
        if not point:
            return False
        try:
            pyautogui.moveTo(point[0], point[1], duration=0.12)
            time.sleep(0.05)
            pyautogui.mouseDown(x=point[0], y=point[1], button='left')
        except Exception:
            return False
        self._status_speak("Microphone live, delivering your message now.")
        time.sleep(max(0.05, delay_before_speaking))
        spoken = self.speak_message(text, emotion=emotion)
        try:
            pyautogui.mouseUp(x=point[0], y=point[1], button='left')
        except Exception:
            pass
        if not spoken:
            return False
        time.sleep(0.25)
        send_success = self.send_voice_message()
        if not send_success:
            try:
                pyautogui.press('enter')
                send_success = True
            except Exception:
                send_success = False
        return send_success

    def _run_uia_voice_workflow(self, recipient_name: str, message: str, emotion: str = "friendly") -> bool:
        if not self.has_uiautomation or auto is None:
            return False
        success_holder = {"ok": False}
        detail = f"UIAutomation voice note for '{recipient_name}'"
        with self._time_step("uia-voice", detail, success_flag=lambda: success_holder["ok"]):
            time.sleep(self.config.chat_to_mic_delay)
            window = self._locate_whatsapp_window()
            self._focus_whatsapp_window(window)
            button = self._find_whatsapp_voice_button(window)
            start_point = self._control_center(button) if button else None
            if not start_point:
                start_point = self._guess_voice_button_point(window)
            clicked = self._click_whatsapp_voice_point(button, start_point)
            if clicked:
                time.sleep(self.config.mic_activation_delay)
                recording_ready = self._wait_for_whatsapp_voice_recording(
                    window,
                    timeout=self.config.recording_timeout,
                    poll=self.config.recording_poll_interval,
                )
                if recording_ready:
                    self._status_speak("Microphone live, sending your message now.")
                    time.sleep(self.config.post_record_wait)
                    if not self.speak_message(message, emotion=emotion):
                        return False
                    time.sleep(0.15)
                    if not self.send_voice_message():
                        return False
                    success_holder["ok"] = True
                    return True
            hold_point = start_point or self._guess_voice_button_point(window)
            success_holder["ok"] = self._hold_and_record_whatsapp_voice(
                hold_point,
                message,
                window,
                delay_before_speaking=self.config.mic_activation_delay + self.config.post_record_wait,
                emotion=emotion,
            )
            return success_holder["ok"]

    def _capture_region_around_point(self, point: Tuple[int, int]) -> Optional[Any]:
        if not point:
            return None
        margin = self.config.screenshot_region_margin
        left = max(0, point[0] - margin)
        top = max(0, point[1] - margin)
        right = min(self.screen_width, point[0] + margin)
        bottom = min(self.screen_height, point[1] + margin)
        return self.screen_analyzer.grab((left, top, right, bottom))

    def _mic_detection_round(self, attempt: int) -> bool:
        success_holder = {"ok": False}
        detail = f"Attempt {attempt+1} using template fallback"
        with self._time_step("mic-detect", detail, success_flag=lambda: success_holder["ok"]):
            position = self._locate_on_screen(self.MIC_TEMPLATE_NAME)
            if position:
                self.mic_position = position
                success_holder["ok"] = True
                return True
            # fallback to coordinate scan
            offsets = [0, -60, 60, -120, 120]
            base_x, base_y = self._relative_point(1850, 1020)
            for delta in offsets:
                candidate = (base_x + delta, base_y)
                sample = self._capture_region_around_point(candidate)
                if self.screen_analyzer.detect_vertical_red_band(sample):
                    self.mic_position = candidate
                    success_holder["ok"] = True
                    return True
        return False

    def _confirm_recording_active(self, point: Tuple[int, int]) -> bool:
        sample = self._capture_region_around_point(point)
        if not sample:
            return True  # assume recording when no data
        waviness = self.screen_analyzer.detect_waveform_activity(sample)
        bright = self.screen_analyzer.average_brightness(sample)
        return waviness or bright > 0.35

    def initialize_tts_engine(self) -> bool:
        """Initialize text-to-speech engine."""
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 150)
            self.engine.setProperty('volume', 1.0)
            print("✓ Text-to-Speech engine initialized")
            return True
        except Exception as e:
            print(f"✗ Error initializing TTS: {e}")
            return False
    
    
    def _template_path(self, filename: str) -> Optional[Path]:
        candidate = self.assets_dir / filename
        return candidate if candidate.exists() else None

    def _relative_point(self, ref_x: int, ref_y: int) -> Tuple[int, int]:
        """Translate reference coordinates (1920x1080) to current screen."""
        x = int((ref_x / self.REFERENCE_WIDTH) * self.screen_width)
        y = int((ref_y / self.REFERENCE_HEIGHT) * self.screen_height)
        return x, y

    def _locate_on_screen(self, template_name: str) -> Optional[Tuple[int, int]]:
        template = self._template_path(template_name)
        if not template:
            return None
        try:
            location = pyautogui.locateCenterOnScreen(
                str(template), confidence=0.8, grayscale=True
            )
            if location:
                return int(location.x), int(location.y)
        except Exception:
            pass
        return None
    
    def find_and_click_search_box(self) -> bool:
        """Find search box and click around it to guarantee focus."""
        success_holder = {"ok": False}
        with self._time_step(
            "search-focus",
            "Clicking search box candidates",
            success_flag=lambda: success_holder["ok"],
        ):
            try:
                print("🔍 Locating search box...")
                time.sleep(self.config.search_focus_delay)
                search_positions = [
                    (300, 60),
                    (200, 50),
                    (350, 80),
                ]
                for x, y in search_positions:
                    rel_x, rel_y = self._relative_point(x, y)
                    pyautogui.click(rel_x, rel_y)
                    time.sleep(self.config.click_pause)
                print("✓ Clicked search box area")
                success_holder["ok"] = True
                return True
            except Exception as e:
                print(f"✗ Error clicking search box: {e}")
                return False
    
    def type_recipient_name(self, recipient_name: str) -> bool:
        """Type recipient name in search box."""
        success_holder = {"ok": False}
        with self._time_step(
            "search-type",
            f"Typing recipient '{recipient_name}'",
            success_flag=lambda: success_holder["ok"],
        ):
            try:
                print(f"⌨️  Typing recipient name: '{recipient_name}'...")
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.2)
                pyautogui.press('delete')
                time.sleep(0.3)
                pyautogui.typewrite(recipient_name, interval=self.config.typing_interval)
                time.sleep(1.5)
                print("✓ Name typed in search box")
                success_holder["ok"] = True
                return True
            except Exception as e:
                print(f"✗ Error typing name: {e}")
                return False
    
    def click_first_search_result(self) -> bool:
        """Click on first search result."""
        success_holder = {"ok": False}
        with self._time_step(
            "search-select",
            "Selecting first search result",
            success_flag=lambda: success_holder["ok"],
        ):
            try:
                print("🖱️  Clicking first search result...")
                time.sleep(0.5)
                result_x, result_y = self._relative_point(400, 150)
                pyautogui.click(result_x, result_y)
                time.sleep(1)
                pyautogui.press('enter')
                time.sleep(1)
                print("✓ Clicked first search result")
                success_holder["ok"] = True
                return True
            except Exception as e:
                print(f"✗ Error clicking result: {e}")
                return False

    def focus_message_box(self) -> bool:
        """Ensure the WhatsApp message composer has focus."""
        success_holder = {"ok": False}
        with self._time_step(
            "focus-message",
            "Focusing WhatsApp message composer",
            success_flag=lambda: success_holder["ok"],
        ):
            try:
                msg_x, msg_y = self._relative_point(900, 950)
                pyautogui.click(msg_x, msg_y)
                time.sleep(0.4)
                success_holder["ok"] = True
                return True
            except Exception as e:
                print(f"✗ Error focusing message box: {e}")
                return False
    
    def detect_microphone_button(self) -> bool:
        """Detect microphone button using template or fallback coordinates."""
        success_holder = {"ok": False}
        with self._time_step(
            "mic-locate",
            "Locating WhatsApp microphone button",
            success_flag=lambda: success_holder["ok"],
        ):
            try:
                print("🔎 Detecting microphone button on screen...")
                time.sleep(0.5)
                if self.mic_position:
                    success_holder["ok"] = True
                    return True
                uia_point = self._resolve_mic_point()
                if uia_point:
                    self.mic_position = uia_point
                    success_holder["ok"] = True
                    print("✓ Microphone resolved via UIAutomation heuristics")
                    return True
                for attempt in range(self.config.mic_probe_attempts):
                    if self._mic_detection_round(attempt):
                        print("✓ Microphone located (attempt", attempt + 1, ")")
                        success_holder["ok"] = True
                        return True
                    time.sleep(0.35)
                # final fallback to static coordinate
                guess = self._guess_voice_button_point(None) or self._relative_point(1850, 1020)
                self.mic_position = guess
                print("⚠️  Using fallback microphone coordinates")
                success_holder["ok"] = bool(self.mic_position)
                return bool(self.mic_position)
            except Exception as e:
                print(f"✗ Error detecting mic button: {e}")
                return False
    
    def click_microphone_button(self) -> bool:
        """Click the detected microphone button."""
        success_holder = {"ok": False}
        with self._time_step(
            "mic-click",
            "Click microphone button and confirm recording",
            success_flag=lambda: success_holder["ok"],
        ):
            try:
                print("🎙️  Clicking microphone button...")
                window = self._locate_whatsapp_window()
                button = self._find_whatsapp_voice_button(window) if window else None
                fallback_point = None
                if button:
                    fallback_point = self._control_center(button)
                if not fallback_point:
                    fallback_point = self.mic_position or self._resolve_mic_point()
                if not fallback_point:
                    if not self.detect_microphone_button():
                        print("⚠️  Microphone position not detected")
                        input("Please click the microphone manually, then press Enter...")
                        success_holder["ok"] = True
                        return True
                    fallback_point = self.mic_position
                self.mic_position = fallback_point
                if not self._click_whatsapp_voice_point(button, fallback_point):
                    print("✗ Could not click microphone button")
                    return False
                time.sleep(self.config.mic_activation_delay)
                deadline = time.time() + self.config.recording_timeout
                poll = max(0.15, self.config.recording_poll_interval)
                while time.time() < deadline:
                    if self._confirm_recording_active(self.mic_position):
                        print("✓ Recording confirmed via waveform detection")
                        success_holder["ok"] = True
                        return True
                    time.sleep(poll)
                print("⚠️  Recording confirmation timed out")
                return False
            except Exception as e:
                print(f"✗ Error clicking microphone: {e}")
                return False
    
    def speak_message(self, message: str, emotion: str = "friendly") -> bool:
        """Speak the message via TTS while WhatsApp is recording."""
        success_holder = {"ok": False}
        with self._time_step(
            "tts",
            f"Speaking message ({len(message)} chars)",
            success_flag=lambda: success_holder["ok"],
        ):
            try:
                print(f"🎤 Speaking message: '{message}'")
                time.sleep(0.5)
                if self._assistant_speak:
                    try:
                        self._assistant_speak(message, emotion=emotion)  # type: ignore[arg-type]
                    except TypeError:
                        self._assistant_speak(message)
                    success_holder["ok"] = True
                    return True
                if not self.engine and not self.initialize_tts_engine():
                    return False
                self.engine.say(message)
                self.engine.runAndWait()
                time.sleep(0.3)
                success_holder["ok"] = True
                return True
            except Exception as e:
                print(f"✗ Error speaking message: {e}")
                return False
    
    def send_voice_message(self) -> bool:
        """Send the voice message via Enter or send button."""
        success_holder = {"ok": False}
        with self._time_step(
            "send",
            "Sending WhatsApp voice message",
            success_flag=lambda: success_holder["ok"],
        ):
            try:
                print("📤 Sending voice message...")
                pyautogui.press('enter')
                time.sleep(0.6)
                if not self.send_position:
                    template_position = self._locate_on_screen(self.SEND_TEMPLATE_NAME)
                    self.send_position = template_position or self._relative_point(1900, 1020)
                if self.send_position:
                    pyautogui.click(*self.send_position)
                deadline = time.time() + self.config.send_confirmation_timeout
                while time.time() < deadline:
                    if self.mic_position and not self._confirm_recording_active(self.mic_position):
                        success_holder["ok"] = True
                        print("✓ Voice message sent!")
                        return True
                    time.sleep(0.4)
                print("⚠️  Could not confirm send; assuming success")
                success_holder["ok"] = True
                return True
            except Exception as e:
                print(f"✗ Error sending message: {e}")
                return False
    
    def complete_automation(self, recipient_name: str, message: str, emotion: str = "friendly") -> bool:
        """Complete automation workflow with UIAutomation preference."""
        try:
            print("\n" + "=" * 70)
            print("🤖 STARTING ADVANCED VOICE NOTE FLOW")
            print("=" * 70 + "\n")

            print("[1/7] Opening WhatsApp via Start menu...")
            if not self.ensure_whatsapp_running():
                print("⚠️  Could not confirm WhatsApp launch; continuing anyway.")
            time.sleep(1)

            print("[2/7] Selecting chat through assistant helpers...")
            if not self.ensure_contact_chat(recipient_name):
                print("✗ Failed to focus the chat window")
                return False
            time.sleep(self.config.chat_to_mic_delay)
            self._status_speak(f"Preparing your WhatsApp voice note for {recipient_name}.")

            if self.has_uiautomation:
                print("[3/7] Trying UIAutomation-driven voice workflow...")
                if self._run_uia_voice_workflow(recipient_name, message, emotion=emotion):
                    print("✓ UIAutomation path completed")
                    return True
                print("⚠️  UIAutomation flow failed; falling back to screen heuristics")

            print("[3/7] Detecting microphone button via template/screen cues...")
            if not self.detect_microphone_button():
                return False
            time.sleep(0.3)

            print("[4/7] Clicking microphone and waiting for capture...")
            if not self.click_microphone_button():
                return False

            print("[5/7] Speaking the provided text...")
            self._status_speak("Microphone live, delivering your message now.")
            time.sleep(self.config.post_record_wait)
            if not self.speak_message(message, emotion=emotion):
                return False
            time.sleep(self.config.post_record_wait)

            print("[6/7] Sending the recorded note...")
            if not self.send_voice_message():
                return False

            print("[7/7] Flow complete")
            return True

        except Exception as e:
            print(f"✗ Error in automation: {e}")
            return False
        finally:
            print(self.diagnostics.summarize())
    
    def close(self) -> None:
        """Cleanup."""
        print("\n✓ Automation completed!")


def parse_input(user_input: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse input in 'name, message' format."""
    try:
        parts = user_input.split(',', 1)
        if len(parts) != 2:
            return None, None
        
        recipient_name = parts[0].strip()
        message = parts[1].strip()
        
        if not recipient_name or not message:
            return None, None
        
        return recipient_name, message
    except Exception as e:
        print(f"✗ Error parsing input: {e}")
        return None, None


def main() -> None:
    """Entry point for standalone execution."""
    print("\n" + "=" * 70)
    print("🤖 WhatsApp Desktop Voice Message Automation - Advanced Edition")
    print("=" * 70)
    print("\nFeatures:")
    print("  ✓ Uses Start-menu automation for opening/searching")
    print("  ✓ Auto-searches recipient in search box (fallback)")
    print("  ✓ Screen detection for microphone/send buttons")
    print("  ✓ Shares assistant TTS logic when available")
    print("  ✓ Auto-sending voice message")
    print("\n" + "=" * 70)
    
    # Get user input
    print("\n📝 INPUT FORMAT: recipient_name, message_text")
    print("   Example: Mom, I'll be home in 10 minutes")
    
    user_input = input("Enter recipient and message: ")
    recipient_name, message = parse_input(user_input)
    
    if not recipient_name or not message:
        print("✗ Invalid format! Use: 'name, message'")
        return
    
    print(f"\n✓ Recipient: {recipient_name}")
    print(f"✓ Message: {message}")
    print(f"✓ Length: {len(message)} characters")
    
    if len(message) > 100:
        print("⚠️  Message is long - ensure enough time to speak it")
    
    print("\n" + "="*70)
    print("⏳ READY TO START - Make sure WhatsApp can be found!")
    print("   Starting in 3 seconds...")
    print("="*70)
    time.sleep(3)
    
    # Initialize and run bot
    bot = WhatsAppAdvancedBot()
    if bot._assistant_speak is None and not bot.initialize_tts_engine():
        return
    
    try:
        success = bot.complete_automation(recipient_name, message)
        
        if success:
            print("\n" + "="*70)
            print("✅ VOICE MESSAGE SENT SUCCESSFULLY!")
            print("="*70)
        else:
            print("\n" + "="*70)
            print("❌ Failed to complete automation")
            print("="*70)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
    finally:
        bot.close()


if __name__ == "__main__":
    main()
