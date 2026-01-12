import os
import ctypes
import threading
import subprocess
import webbrowser
from urllib.parse import quote_plus
from typing import Any, Dict, Optional, Tuple, List, Set
import shutil
import pyautogui
import time
import requests
import difflib
import re
import tempfile
import datetime
import random
from dataclasses import dataclass, field
from enum import Enum

# Import custom modules
from .browser import resolve_first_result, open_and_click_first
from .browser import verify_navigated_non_search
from .ui import (
    click_first_hyperlink_in_foreground,
    click_first_search_result,
    toggle_quick_action,
    quick_toggle,
    set_quick_slider,
    toggle_in_settings_page,
    _click_with_cursor,
    open_app_via_start,
    whatsapp_send_message,
    close_app,
)
from .screen import describe_screen
try:
    from .screen import advise_next_step as _advise_next_step
except Exception:
    _advise_next_step = None

from .system_controls import (
    shutdown as system_shutdown,
    set_display_brightness,
    change_wifi_state,
    open_bluetooth_settings,
    set_volume,
    set_microphone_mute,
    get_volume_percent,
    get_volume_percent,
    nudge_volume_steps,
    set_volume_percent_via_steps,
    play_pause_media,
    stop_media,
    next_track,
    prev_track,
)
from .ai_notepad_workflow import (
    AINotepadWorkflow,
    BrowserOpenError,
    NotepadAutomationError,
    PromptSubmissionError,
    ResponseCollectionError,
    WorkflowConfig,
    WorkflowResult,
)
from .llm_adapter import llm_plan as _llm_plan
from .instagram_monitor import (
    InstagramNotificationMonitor,
    InstagramNotificationConfig,
    NotificationDecision,
)
from .cleanup import cleanup_temp_dirs
from .productivity import (
    productivity_add_task,
    productivity_capture_note,
    productivity_clear_tasks,
    productivity_complete_task,
    productivity_daily_briefing,
    productivity_focus_start,
    productivity_focus_status,
    productivity_focus_stop,
    productivity_list_tasks,
)
from .habit_tracker import (
    habit_create_action,
    habit_log_action,
    habit_status_action,
    habit_reset_action,
)
from .routines import (
    routine_create_action,
    routine_list_action,
    routine_delete_action,
    routine_run_action,
)
from .system_health import (
    system_health_report_action,
    system_health_watch_action,
)
from .clipboard_vault import (
    clipboard_save_action,
    clipboard_list_action,
    clipboard_search_action,
    clipboard_restore_action,
)
from .whatsapp_advanced_voice import WhatsAppAdvancedBot

# Import new enhanced modules
try:
    from .spotify_controller import (
        execute_spotify_action as _execute_spotify_action,
        play_song as spotify_play_song,
        stop_playback as spotify_stop_playback,
        next_track as spotify_next_track,
        previous_track as spotify_previous_track,
    )
    HAS_SPOTIFY_CONTROLLER = True
except (ImportError, OSError):
    HAS_SPOTIFY_CONTROLLER = False
    _execute_spotify_action = None

try:
    from .whatsapp_enhanced import (
        execute_whatsapp_action as _execute_whatsapp_enhanced,
        send_message_to_multiple as whatsapp_send_multiple,
    )
    HAS_WHATSAPP_ENHANCED = True
except (ImportError, OSError):
    HAS_WHATSAPP_ENHANCED = False
    _execute_whatsapp_enhanced = None

try:
    from .task_scheduler import (
        execute_scheduler_action as _execute_scheduler_action,
        schedule_task as schedule_delayed_task,
        list_scheduled_tasks as list_delayed_tasks,
        cancel_scheduled_task as cancel_delayed_task,
    )
    HAS_TASK_SCHEDULER = True
except (ImportError, OSError):
    HAS_TASK_SCHEDULER = False
    _execute_scheduler_action = None

try:
    from .multi_task_parser import (
        execute_multi_task as _execute_multi_task,
    )
    HAS_MULTI_TASK = True
except (ImportError, OSError):
    HAS_MULTI_TASK = False
    _execute_multi_task = None

# Import UI Automation and Registry
try:
    import uiautomation as auto
    HAS_UIAUTOMATION = True
except ImportError:
    HAS_UIAUTOMATION = False
    auto = None

try:
    import pygetwindow as _pygetwindow
except Exception:  # pragma: no cover - optional dependency
    _pygetwindow = None

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False
    winreg = None

# Track apps opened during this session
_OPENED_APPS: Set[str] = set()

# Teaching interface singleton
_TEACHER_INSTANCE = None

PERSONA_NAME = "Kypzer"
BOSS_NAME = "Krishna"

_FRIENDLY_OPENERS = []

def _get_teacher():
    """Lazily create or return the TeachingInterface singleton."""
    global _TEACHER_INSTANCE
    if _TEACHER_INSTANCE is not None:
        return _TEACHER_INSTANCE
    try:
        from .viczo_learning_action import TeachingInterface
        _TEACHER_INSTANCE = TeachingInterface()
        return _TEACHER_INSTANCE
    except Exception as e:
        _notify(f"Teaching interface not available: {e}")
        return None


# Global toggle: when True Viczo will speak-only (suppress console prints).
# Can be controlled via environment variable ASSISTANT_SPEAK_ONLY (1/0, true/false).
ASSISTANT_SPEAK_ONLY = os.environ.get("ASSISTANT_SPEAK_ONLY", "0").lower() in ("1", "true", "yes", "on")


def _notify(message: str):
    """Speak a short progress/update message. When ASSISTANT_SPEAK_ONLY is False,
    also print to console. Uses lazy import for TTS and falls back silently.
    """
    try:
        base_text = str(message or "").strip()
        # Friendly openers removed per strict user requirement
        friendly_text = base_text
        
        # Try speaking first so audible feedback comes before any blocking prints.
        spoken = False
        try:
            from .tts import speak_async
            speak_async(friendly_text)
            spoken = True
        except Exception:
            # Fallback: try package import path used by main
            try:
                from src.assistant.tts import speak_async
                speak_async(friendly_text)
                spoken = True
            except Exception:
                spoken = False

        # Only print when speak-only mode is disabled.
        if not ASSISTANT_SPEAK_ONLY:
            print(f"{PERSONA_NAME}: {friendly_text}")

    except Exception:
        # Nothing we can do; keep silent
        pass


# Global AI Notepad workflow cache
_AI_NOTEPAD_WORKFLOW: Optional[AINotepadWorkflow] = None
_AI_NOTEPAD_LOCK = threading.Lock()
_AI_NOTEPAD_ACTIVE = False


_INSTAGRAM_MONITOR: Optional[InstagramNotificationMonitor] = None
_INSTAGRAM_MONITOR_LOCK = threading.Lock()

_CHATGPT_SESSION_STATE: Dict[str, Any] = {}


_APP_NAME_ALIASES: Dict[str, List[str]] = {
    "360 extreme browser": [
        "360极速浏览器",
        "360安全浏览器",
        "360chrome",
        "360chrome.exe",
        "360 extreme explorer",
        "360浏览器",
        "360安全浏览器（极速版）",
    ],
    "360 browser": [
        "360极速浏览器",
        "360安全浏览器",
        "360chrome",
        "360浏览器",
    ],
}


def _ai_log(message: str) -> None:
    if not message:
        return
    if not ASSISTANT_SPEAK_ONLY:
        print(f"[AI-Notepad] {message}")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _get_ai_notepad_workflow() -> AINotepadWorkflow:
    global _AI_NOTEPAD_WORKFLOW
    if _AI_NOTEPAD_WORKFLOW is not None:
        return _AI_NOTEPAD_WORKFLOW

    config = WorkflowConfig()
    config.boot_wait_seconds = _env_float("CHATGPT_BOOT_WAIT", config.boot_wait_seconds)
    config.base_wait_seconds = _env_float("CHATGPT_WAIT_SECONDS", config.base_wait_seconds)
    config.max_wait_seconds = _env_float("CHATGPT_MAX_WAIT", config.max_wait_seconds)
    config.wait_poll_seconds = _env_float("CHATGPT_POLL_SECONDS", config.wait_poll_seconds)
    config.wait_stable_threshold = max(2, _env_int("CHATGPT_STABLE_THRESHOLD", int(config.wait_stable_threshold)))
    config.wait_minimum_growth = max(2, _env_int("CHATGPT_MIN_GROWTH", int(config.wait_minimum_growth)))
    config.copy_retries = max(1, _env_int("CHATGPT_COPY_RETRIES", config.copy_retries))
    config.scroll_attempts = max(0, _env_int("CHATGPT_SCROLL_ATTEMPTS", config.scroll_attempts))
    config.preferred_browser = os.environ.get("CHATGPT_BROWSER") or None
    config.allow_paste_mode = os.environ.get("AI_NOTEPAD_PASTE_MODE", "1").lower() not in {"0", "false"}
    config.quality_min_words = max(20, _env_int("AI_NOTEPAD_MIN_WORDS", config.quality_min_words))
    config.quality_min_sentences = max(2, _env_int("AI_NOTEPAD_MIN_SENTENCES", config.quality_min_sentences))
    config.quality_min_bullets = max(1, _env_int("AI_NOTEPAD_MIN_BULLETS", config.quality_min_bullets))
    config.quality_max_chars = max(500, _env_int("AI_NOTEPAD_MAX_CHARS", config.quality_max_chars))

    def _logger(msg: str) -> None:
        if msg:
            _ai_log(msg)

    config.logger = _logger
    config.random_seed = _env_int("AI_NOTEPAD_RANDOM_SEED", config.random_seed or 0) or None
    _AI_NOTEPAD_WORKFLOW = AINotepadWorkflow(config=config)
    return _AI_NOTEPAD_WORKFLOW


def _get_instagram_monitor() -> InstagramNotificationMonitor:
    """Return a shared Instagram monitor configured via environment toggles."""
    global _INSTAGRAM_MONITOR
    if _INSTAGRAM_MONITOR is not None:
        return _INSTAGRAM_MONITOR

    with _INSTAGRAM_MONITOR_LOCK:
        if _INSTAGRAM_MONITOR is None:
            config = InstagramNotificationConfig()
            try:
                config.max_attempts = max(2, int(os.environ.get("INSTAGRAM_MONITOR_MAX_ATTEMPTS", config.max_attempts)))
                config.min_attempts = max(1, int(os.environ.get("INSTAGRAM_MONITOR_MIN_ATTEMPTS", config.min_attempts)))
            except Exception:
                pass

            debug_env = os.environ.get("INSTAGRAM_MONITOR_DEBUG", "0").lower()
            config.debug_samples = debug_env in {"1", "true", "yes", "on"}

            disable_numpy_env = os.environ.get("INSTAGRAM_MONITOR_DISABLE_NUMPY", "0").lower()
            if disable_numpy_env in {"1", "true", "yes", "on"}:
                config.allow_numpy = False
                config.enable_circularity = False
                config.enable_compactness = False
                config.enable_cluster_analysis = False

            _INSTAGRAM_MONITOR = InstagramNotificationMonitor(config)

    return _INSTAGRAM_MONITOR


def _active_window_title() -> Optional[str]:
    try:
        title = pyautogui.getActiveWindowTitle()
        if isinstance(title, str):
            return title.strip()
    except Exception:
        pass
    return None


def _title_matches_keywords(title: Optional[str], keywords: Tuple[str, ...]) -> bool:
    if not title:
        return False
    lower = title.lower()
    return any(keyword.lower() in lower for keyword in keywords if keyword)


def _focus_window_by_keywords(keywords: Tuple[str, ...], timeout: float = 8.0, allow_alt_tab: bool = True) -> bool:
    """Bring to front a window whose title contains any of the keywords."""
    deadline = time.time() + max(timeout, 1.0)
    alt_tab_attempted = False
    while time.time() < deadline:
        current = _active_window_title()
        if _title_matches_keywords(current, keywords):
            return True

        if _pygetwindow is not None:
            try:
                for keyword in keywords:
                    if not keyword:
                        continue
                    windows = _pygetwindow.getWindowsWithTitle(keyword)
                    for window in windows:
                        try:
                            if window.isMinimized:
                                window.restore()
                            window.activate()
                            time.sleep(0.6)
                            current = _active_window_title()
                            if _title_matches_keywords(current, keywords):
                                return True
                        except Exception:
                            continue
            except Exception:
                pass

        if allow_alt_tab and not alt_tab_attempted:
            try:
                pyautogui.hotkey('alt', 'tab')
                alt_tab_attempted = True
                time.sleep(0.7)
                continue
            except Exception:
                alt_tab_attempted = True

        time.sleep(0.4)

    return False


def _focus_instagram_window(keywords: Tuple[str, ...] = ("instagram", "brave"), timeout: float = 8.0) -> bool:
    return _focus_window_by_keywords(keywords, timeout=timeout, allow_alt_tab=True)


def _expand_app_name_aliases(app_name: str) -> List[str]:
    raw = (app_name or "").strip()
    if not raw:
        return []

    candidates: List[str] = []
    seen: Set[str] = set()

    def _add(name: str) -> None:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            candidates.append(name.strip())

    _add(raw)
    lower = raw.lower()

    if lower in _APP_NAME_ALIASES:
        for alias in _APP_NAME_ALIASES[lower]:
            _add(alias)

    # Heuristic: replace "browser" with Chinese equivalent if digits present
    if "browser" in lower and "360" in lower:
        _add(raw.replace("browser", "浏览器"))
        _add(raw.replace("browser", "極速浏览器"))

    # Add variations without words like "browser", "app", etc.
    trimmed = re.sub(r"(?i)\b(browser|app|application|software)\b", "", lower).strip()
    if trimmed and trimmed != lower:
        _add(trimmed)

    return candidates


def _query_recycle_bin_info() -> Optional[Dict[str, int]]:
    if not hasattr(ctypes, "windll"):
        return None

    class SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("i64Size", ctypes.c_longlong),
            ("i64NumItems", ctypes.c_longlong),
        ]

    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    try:
        result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    except Exception:
        return None

    if result != 0:
        return None

    return {
        "items": int(info.i64NumItems),
        "bytes": int(info.i64Size),
    }


def _open_recycle_bin_window() -> bool:
    try:
        subprocess.Popen(["explorer.exe", "shell:RecycleBinFolder"], shell=False)
        return True
    except Exception:
        pass

    try:
        return open_app_via_start("recycle bin") or False
    except Exception:
        return False


def _focus_recycle_bin_window(timeout: float = 8.0) -> bool:
    return _focus_window_by_keywords(("recycle bin", "bin"), timeout=timeout, allow_alt_tab=False)


# ============================================================================
# ADVANCED UNINSTALL SYSTEM - COMPREHENSIVE IMPLEMENTATION
# ============================================================================

class InstallerType(Enum):
    """Detected installer technology types"""
    MSI = "msi"
    INNO_SETUP = "inno"
    NSIS = "nsis"
    INSTALLSHIELD = "installshield"
    WIX = "wix"
    SQUIRREL = "squirrel"
    ELECTRON = "electron"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class WizardStep(Enum):
    """Common uninstaller wizard steps"""
    INITIAL_PROMPT = "initial"
    UAC_CONSENT = "uac"
    WELCOME = "welcome"
    CONFIRMATION = "confirmation"
    OPTIONS = "options"
    PROGRESS = "progress"
    COMPLETION = "completion"
    ERROR = "error"
    REBOOT_PROMPT = "reboot"


@dataclass
class UninstallEntry:
    """Registry uninstall entry with all metadata"""
    display_name: str
    uninstall_string: Optional[str] = None
    quiet_uninstall_string: Optional[str] = None
    product_code: Optional[str] = None
    publisher: Optional[str] = None
    version: Optional[str] = None
    install_location: Optional[str] = None
    is_windows_installer: bool = False
    registry_path: str = ""
    installer_type: InstallerType = InstallerType.UNKNOWN
    estimated_size_kb: int = 0
    install_date: Optional[str] = None
    uninstall_exe_path: Optional[str] = None
    silent_switches: List[str] = field(default_factory=list)


@dataclass
class WizardState:
    """Current state of the uninstaller wizard"""
    current_step: WizardStep = WizardStep.INITIAL_PROMPT
    window_title: str = ""
    window_handle: Optional[Any] = None
    buttons_found: List[str] = field(default_factory=list)
    checkboxes_found: List[str] = field(default_factory=list)
    radio_buttons_found: List[str] = field(default_factory=list)
    text_content: str = ""
    has_progress_bar: bool = False
    progress_value: int = 0
    last_action_time: float = field(default_factory=time.time)
    interaction_count: int = 0
    stuck_count: int = 0
    error_detected: bool = False
    completion_detected: bool = False


def _fuzzy_name_match(query: str, candidate: str, threshold: float = 0.60) -> bool:
    """
    Advanced fuzzy matching with multiple heuristics.
    Returns True if candidate matches query within tolerance.
    """
    if not query or not candidate:
        return False
    
    q = query.strip().lower()
    c = candidate.strip().lower()
    
    # Direct substring match
    if q in c or c in q:
        return True
    
    # Token-based matching
    q_tokens = [t for t in re.split(r'\W+', q) if t and len(t) > 2]
    if q_tokens:
        matched = sum(1 for t in q_tokens if t in c)
        if matched >= max(1, (len(q_tokens) + 1) // 2):
            return True
    
    # Sequence matcher ratio
    try:
        ratio = difflib.SequenceMatcher(None, q, c).ratio()
        if ratio >= threshold:
            return True
    except Exception:
        pass
    
    # Token close matches
    try:
        c_tokens = [t for t in re.split(r'\W+', c) if t and len(t) > 2]
        for qt in q_tokens:
            close = difflib.get_close_matches(qt, c_tokens, n=1, cutoff=0.85)
            if close:
                return True
    except Exception:
        pass
    
    return False


def _iter_uninstall_registry_keys():
    """
    Iterate through all Windows uninstall registry locations.
    Yields (root_key, full_path, opened_key) tuples.
    """
    if not HAS_WINREG:
        return
    
    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    
    for root, subkey_path in registry_paths:
        try:
            with winreg.OpenKey(root, subkey_path) as parent_key:
                num_subkeys = winreg.QueryInfoKey(parent_key)[0]
                for i in range(num_subkeys):
                    try:
                        subkey_name = winreg.EnumKey(parent_key, i)
                        full_path = f"{subkey_path}\\{subkey_name}"
                        with winreg.OpenKey(parent_key, subkey_name) as subkey:
                            yield (root, full_path, subkey)
                    except (OSError, WindowsError):
                        continue
        except (OSError, WindowsError):
            continue


def _registry_read_string(key, value_name: str, default: Optional[str] = None) -> Optional[str]:
    """Safely read a string value from registry key"""
    try:
        value, reg_type = winreg.QueryValueEx(key, value_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    except (OSError, WindowsError):
        pass
    return default


def _registry_read_dword(key, value_name: str, default: int = 0) -> int:
    """Safely read a DWORD value from registry key"""
    try:
        value, reg_type = winreg.QueryValueEx(key, value_name)
        if isinstance(value, int):
            return value
    except (OSError, WindowsError):
        pass
    return default


def _detect_installer_type_from_string(uninstall_string: str) -> InstallerType:
    """
    Detect installer technology from uninstall command string.
    Analyzes executable name and command-line patterns.
    """
    if not uninstall_string:
        return InstallerType.UNKNOWN
    
    us_lower = uninstall_string.lower()
    
    if "msiexec" in us_lower or us_lower.endswith(".msi"):
        return InstallerType.MSI
    
    if "unins" in us_lower and ".exe" in us_lower:
        return InstallerType.INNO_SETUP
    
    if "uninst" in us_lower and ".exe" in us_lower:
        return InstallerType.NSIS
    
    if any(x in us_lower for x in ["installshield", "isuninst", "setup.exe -runfromtemp"]):
        return InstallerType.INSTALLSHIELD
    
    if "wixburn" in us_lower or "bundle" in us_lower:
        return InstallerType.WIX
    
    if "update.exe" in us_lower and "--uninstall" in us_lower:
        return InstallerType.SQUIRREL
    
    if "electron" in us_lower:
        return InstallerType.ELECTRON
    
    return InstallerType.CUSTOM


def _extract_executable_path(command_string: str) -> Optional[str]:
    """Extract the executable path from a command string."""
    if not command_string:
        return None
    
    cmd = command_string.strip()
    
    if cmd.startswith('"'):
        end_quote = cmd.find('"', 1)
        if end_quote > 0:
            return cmd[1:end_quote]
    
    parts = cmd.split()
    if parts:
        return parts[0]
    
    return None


def _get_silent_switches_for_installer(installer_type: InstallerType, uninstall_string: str = "") -> List[str]:
    """Return appropriate silent/automated switches for each installer type."""
    switches = []
    
    if installer_type == InstallerType.MSI:
        switches = ["/passive", "/norestart", "/qn"]
    elif installer_type == InstallerType.INNO_SETUP:
        switches = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
    elif installer_type == InstallerType.NSIS:
        switches = ["/S"]
    elif installer_type == InstallerType.INSTALLSHIELD:
        switches = ["/s", "/x", "/uninst"]
    elif installer_type == InstallerType.WIX:
        switches = ["/quiet", "/norestart"]
    elif installer_type == InstallerType.SQUIRREL:
        switches = ["--uninstall", "-s"]
    
    return switches


def get_installed_application(app_name: str) -> Optional[UninstallEntry]:
    """
    Search registry for installed application matching the given name.
    Returns the best fuzzy match with complete metadata.
    """
    if not HAS_WINREG:
        return None
    
    best_match = None
    best_score = -1.0
    
    for root, reg_path, key in _iter_uninstall_registry_keys():
        display_name = _registry_read_string(key, "DisplayName")
        if not display_name:
            continue
        
        if not _fuzzy_name_match(app_name, display_name):
            continue
        
        uninstall_str = _registry_read_string(key, "UninstallString")
        quiet_uninstall_str = _registry_read_string(key, "QuietUninstallString")
        product_code = _registry_read_string(key, "ProductCode")
        publisher = _registry_read_string(key, "Publisher")
        version = _registry_read_string(key, "DisplayVersion")
        install_location = _registry_read_string(key, "InstallLocation")
        install_date = _registry_read_string(key, "InstallDate")
        is_msi = _registry_read_dword(key, "WindowsInstaller", 0) == 1
        estimated_size = _registry_read_dword(key, "EstimatedSize", 0)
        
        installer_type = _detect_installer_type_from_string(uninstall_str or "")
        if is_msi and installer_type == InstallerType.UNKNOWN:
            installer_type = InstallerType.MSI
        
        uninstall_exe = _extract_executable_path(uninstall_str or "")
        silent_switches = _get_silent_switches_for_installer(installer_type, uninstall_str or "")
        
        entry = UninstallEntry(
            display_name=display_name,
            uninstall_string=uninstall_str,
            quiet_uninstall_string=quiet_uninstall_str,
            product_code=product_code,
            publisher=publisher,
            version=version,
            install_location=install_location,
            is_windows_installer=is_msi,
            registry_path=reg_path,
            installer_type=installer_type,
            estimated_size_kb=estimated_size,
            install_date=install_date,
            uninstall_exe_path=uninstall_exe,
            silent_switches=silent_switches,
        )
        
        score = len(display_name)
        if entry.is_windows_installer:
            score += 5
        if entry.quiet_uninstall_string:
            score += 3
        
        if score > best_score:
            best_match = entry
            best_score = score
    
    return best_match


def _execute_command(command: str, wait: bool = True, timeout: int = 1800, 
                     shell: bool = True) -> Tuple[bool, Optional[int]]:
    """Execute a command with optional timeout."""
    try:
        process = subprocess.Popen(
            command,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        
        if not wait:
            return True, None
        
        try:
            return_code = process.wait(timeout=timeout)
            return return_code == 0, return_code
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            return False, None
    except Exception as e:
        _notify(f"Command execution error: {e}")
        return False, None


def try_winget_uninstall(app_name: str) -> bool:
    """Attempt uninstall using Windows Package Manager (winget)."""
    winget_exe = shutil.which("winget")
    if not winget_exe:
        return False
    
    command = (
        f'"{winget_exe}" uninstall '
        f'--exact --name "{app_name}" '
        f'--silent --force --disable-interactivity '
        f'--accept-source-agreements --source winget'
    )
    
    success, _ = _execute_command(command, wait=True, timeout=1800)
    
    if not success:
        command = (
            f'"{winget_exe}" uninstall '
            f'--name "{app_name}" '
            f'--silent --force --disable-interactivity '
            f'--accept-source-agreements --source winget'
        )
        success, _ = _execute_command(command, wait=True, timeout=1800)
    
    return success


def try_msi_uninstall(entry: UninstallEntry) -> bool:
    """Attempt uninstall using Windows Installer (msiexec)."""
    if not entry.product_code or not entry.is_windows_installer:
        return False
    
    product_code = entry.product_code.strip()
    if not product_code.startswith("{"):
        product_code = f"{{{product_code}}}"
    
    command = f'msiexec.exe /x "{product_code}" /passive /norestart'
    success, rc = _execute_command(command, wait=True, timeout=1800)
    
    if success:
        return True
    
    command = f'msiexec.exe /x "{product_code}" /qn /norestart'
    success, rc = _execute_command(command, wait=True, timeout=1800)
    
    return success


def try_quiet_uninstall_string(entry: UninstallEntry) -> bool:
    """Execute QuietUninstallString if available."""
    if not entry.quiet_uninstall_string:
        return False
    
    success, _ = _execute_command(entry.quiet_uninstall_string, wait=True, timeout=1800)
    return success


def try_silent_with_switches(entry: UninstallEntry) -> bool:
    """Attempt uninstall using inferred silent switches."""
    if not entry.uninstall_string or not entry.silent_switches:
        return False
    
    base_command = entry.uninstall_string
    
    for switch in entry.silent_switches:
        if switch.lower() in base_command.lower():
            continue
        
        command = f"{base_command} {switch}"
        success, _ = _execute_command(command, wait=True, timeout=1800)
        
        if success:
            return True
    
    all_switches = " ".join(entry.silent_switches)
    command = f"{base_command} {all_switches}"
    success, _ = _execute_command(command, wait=True, timeout=1800)
    
    return success


def _safe_click_element(element) -> bool:
    """Safely click a UI element using cursor movement."""
    if not HAS_UIAUTOMATION:
        return False
    
    try:
        rect = element.BoundingRectangle
        center_x = int((rect.left + rect.right) / 2)
        center_y = int((rect.top + rect.bottom) / 2)
        
        pyautogui.moveTo(center_x, center_y, duration=0.15)
        time.sleep(0.05)
        pyautogui.click(center_x, center_y)
        time.sleep(0.2)
        
        return True
    except Exception as e:
        _notify(f"Click error: {e}")
        return False


def _get_all_buttons_from_window(window) -> List[Tuple[str, Any]]:
    """
    Recursively get all buttons from a window with their names.
    Returns list of (button_name, button_control) tuples.
    """
    buttons = []
    
    if not HAS_UIAUTOMATION or not window:
        return buttons
    
    def walk_controls(ctrl, depth=0):
        if depth > 15:
            return
        
        try:
            # Check if this is a button
            if hasattr(ctrl, 'ControlTypeName'):
                ctrl_type = getattr(ctrl, 'ControlTypeName', '')
                if 'Button' in ctrl_type:
                    name = getattr(ctrl, 'Name', '')
                    if name:
                        buttons.append((name, ctrl))
            
            # Recurse to children
            try:
                children = ctrl.GetChildren()
                if children:
                    for child in children:
                        walk_controls(child, depth + 1)
            except Exception:
                pass
        except Exception:
            pass
    
    try:
        walk_controls(window)
    except Exception as e:
        _notify(f"Error walking controls: {e}")
    
    return buttons


def _find_and_click_button_smart(window, patterns: List[str]) -> bool:
    """
    Smart button finder that gets ALL buttons and matches by pattern.
    More reliable than searchFromControl.
    """
    if not HAS_UIAUTOMATION or not window:
        return False
    
    # Get all buttons
    all_buttons = _get_all_buttons_from_window(window)
    
    if not all_buttons:
        _notify("No buttons found in window")
        return False
    
    _notify(f"Found {len(all_buttons)} buttons")
    
    # Try each pattern
    for pattern in patterns:
        for btn_name, btn_ctrl in all_buttons:
            try:
                if re.search(pattern, btn_name, re.IGNORECASE):
                    _notify(f"Matched button '{btn_name}' with pattern '{pattern}'")
                    return _safe_click_element(btn_ctrl)
            except Exception:
                continue
    
    return False


def handle_uac_prompt(max_attempts: int = 20, timeout_seconds: int = 45) -> bool:
    """
    ENHANCED UAC handler - more aggressive detection and clicking.
    Handles User Account Control consent dialog.
    """
    if not HAS_UIAUTOMATION:
        return False
    
    start_time = time.time()
    _notify("Watching for UAC prompt...")
    
    for attempt in range(max_attempts):
        if time.time() - start_time > timeout_seconds:
            break
        
        try:
            # Try multiple window detection methods
            uac_found = False
            uac_window = None
            
            # Method 1: Specific UAC window title
            try:
                uac_window = auto.WindowControl(
                    searchDepth=1,
                    RegexName=r"(?i)(user account control|do you want to allow)"
                )
                if uac_window and uac_window.Exists(0, 0):
                    uac_found = True
            except Exception:
                pass
            
            # Method 2: Check foreground window for UAC-like content
            if not uac_found:
                try:
                    fg = auto.GetForegroundControl()
                    if fg:
                        title = getattr(fg, 'Name', '').lower()
                        if 'user account control' in title or 'do you want to allow' in title:
                            uac_window = fg
                            uac_found = True
                except Exception:
                    pass
            
            if uac_found and uac_window:
                _notify(f"UAC detected on attempt {attempt + 1}!")

                # Get all buttons and try programmatic click first
                all_buttons = _get_all_buttons_from_window(uac_window)
                _notify(f"UAC window buttons: {[name for name, _ in all_buttons]}")

                for btn_name, btn_ctrl in all_buttons:
                    if re.search(r'(?i)^(yes|allow|continue|allow changes)$', btn_name):
                        _notify(f"Clicking UAC button: {btn_name}")
                        if _safe_click_element(btn_ctrl):
                            _notify("UAC approved programmatically")
                            time.sleep(1.0)
                            return True

                # Try keyboard fallbacks
                try:
                    pyautogui.hotkey('alt', 'y')
                    time.sleep(0.15)
                    pyautogui.press('enter')
                    _notify("Tried Alt+Y/Enter for UAC")
                    time.sleep(0.5)
                    return True
                except Exception:
                    pass

                # If we couldn't interact with the secure desktop, wait for manual approval instead of aborting.
                # Poll until the UAC window disappears (user will approve manually), or timeout.
                waited = 0.0
                poll = 0.5
                _notify("UAC on secure desktop; waiting for manual approval...")
                while waited < timeout_seconds:
                    time.sleep(poll)
                    waited += poll
                    try:
                        uac_check = auto.WindowControl(searchDepth=1, RegexName=r"(?i)(user account control|do you want to allow)")
                        if not (uac_check and uac_check.Exists(0, 0)):
                            _notify("UAC no longer present; continuing")
                            return True
                    except Exception:
                        # If probing fails, continue waiting
                        pass

                _notify("Timeout waiting for manual UAC approval")
                return False
        
        except Exception as e:
            _notify(f"UAC detection error: {e}")
        
        time.sleep(0.4)
    
    _notify("No UAC prompt detected")
    return False


def analyze_wizard_window(window) -> WizardState:
    """Analyze current uninstaller wizard window and determine state."""
    if not HAS_UIAUTOMATION:
        return WizardState()
    
    state = WizardState()
    
    try:
        if hasattr(window, "Name"):
            state.window_title = window.Name or ""
        
        state.window_handle = window
        
        # Get all text from window
        def get_all_text(ctrl, depth=0):
            texts = []
            if depth > 10:
                return texts
            try:
                name = getattr(ctrl, 'Name', '')
                if name and len(name) > 1:
                    texts.append(name)
                children = ctrl.GetChildren()
                if children:
                    for child in children:
                        texts.extend(get_all_text(child, depth + 1))
            except Exception:
                pass
            return texts
        
        all_texts = get_all_text(window)
        state.text_content = " ".join(all_texts).lower()
        
        # Get all buttons
        all_buttons = _get_all_buttons_from_window(window)
        state.buttons_found = [name for name, _ in all_buttons]
        
        # Check for progress bar
        try:
            pb = auto.ProgressBarControl(searchFromControl=window, searchDepth=10)
            if pb and pb.Exists(0, 0):
                state.has_progress_bar = True
                try:
                    state.progress_value = int(pb.RangeValue.Value)
                except:
                    state.progress_value = 0
        except Exception:
            pass
        
        state.current_step = _infer_wizard_step(state)
        
    except Exception as e:
        _notify(f"Error analyzing wizard window: {e}")
    
    return state


def _infer_wizard_step(state: WizardState) -> WizardStep:
    """Infer the current wizard step from window content."""
    text = state.text_content.lower()
    buttons = [b.lower() for b in state.buttons_found]
    title = state.window_title.lower()
    
    _notify(f"Analyzing window: title='{state.window_title}'")
    
    # Check for completion
    completion_kw = ["completed", "finished", "success", "removed", "uninstalled", "å®Œæˆ", "æˆåŠŸ"]
    if any(kw in text or kw in title for kw in completion_kw):
        if any(b in ["finish", "close", "ok", "å®Œæˆ", "å…³é—­"] for b in buttons):
            state.completion_detected = True
            return WizardStep.COMPLETION
    
    # Check for errors
    if any(kw in text for kw in ["error", "failed", "failure", "problem", "é”™è¯¯"]):
        state.error_detected = True
        return WizardStep.ERROR
    
    # Check for reboot
    if "restart" in text or "reboot" in text or "é‡å¯" in text:
        return WizardStep.REBOOT_PROMPT
    
    # Check for progress
    if state.has_progress_bar or "please wait" in text or "removing" in text or "uninstalling" in text or "å¸è½½ä¸­" in text:
        return WizardStep.PROGRESS
    
    # Check for confirmation
    confirm_kw = ["are you sure", "confirm", "really want", "permanently", "ç¡®è®¤", "ç¡®å®šè¦"]
    if any(kw in text for kw in confirm_kw):
        return WizardStep.CONFIRMATION
    
    # Check for welcome
    if "welcome" in text or "wizard" in text or "æ¬¢è¿Ž" in text:
        return WizardStep.WELCOME
    
    # Check for UAC
    if "user account control" in text or "allow changes" in text or "å…è®¸" in text:
        return WizardStep.UAC_CONSENT
    
    return WizardStep.INITIAL_PROMPT


def interact_with_wizard_step(state: WizardState) -> bool:
    """Perform appropriate actions based on current wizard step."""
    if not HAS_UIAUTOMATION or not state.window_handle:
        return False
    
    window = state.window_handle
    _notify(f"Current wizard step: {state.current_step.value}")
    _notify(f"Available buttons: {state.buttons_found}")
    
    if state.current_step == WizardStep.UAC_CONSENT:
        return handle_uac_prompt(max_attempts=5, timeout_seconds=10)
    
    if state.current_step == WizardStep.COMPLETION:
        patterns = [r"(?i)(finish|close|ok|exit|done|å®Œæˆ|å…³é—­)"]
        return _find_and_click_button_smart(window, patterns)
    
    if state.current_step == WizardStep.ERROR:
        patterns = [r"(?i)(ok|close|å…³é—­)"]
        return _find_and_click_button_smart(window, patterns)
    
    if state.current_step == WizardStep.REBOOT_PROMPT:
        patterns = [r"(?i)(later|no|restart later|å…³é—­)"]
        return _find_and_click_button_smart(window, patterns)
    
    if state.current_step == WizardStep.PROGRESS:
        _notify(f"Progress screen, waiting... ({state.progress_value}%)")
        return True
    
    if state.current_step == WizardStep.CONFIRMATION:
        patterns = [r"(?i)(yes|uninstall|remove|ok|ç¡®å®š|å¸è½½)"]
        return _find_and_click_button_smart(window, patterns)
    
    if state.current_step == WizardStep.WELCOME:
        patterns = [r"(?i)(next|continue|uninstall|ä¸‹ä¸€æ­¥|å¸è½½)"]
        return _find_and_click_button_smart(window, patterns)
    
    # For initial or unknown steps, try common progression buttons
    patterns = [
        r"(?i)(uninstall|å¸è½½)",
        r"(?i)(yes|æ˜¯)",
        r"(?i)(next|ä¸‹ä¸€æ­¥)",
        r"(?i)(continue|ç»§ç»­)",
        r"(?i)(ok|ç¡®å®š)"
    ]
    return _find_and_click_button_smart(window, patterns)


def drive_uninstaller_wizard(max_duration_seconds: int = 1800, 
                             max_stuck_iterations: int = 12) -> bool:
    """
    ENHANCED wizard driver with better UAC handling and smarter detection.
    """
    if not HAS_UIAUTOMATION:
        _notify("UI Automation not available")
        return False
    
    start_time = time.time()
    last_window_title = ""
    last_buttons = []
    stuck_count = 0
    total_interactions = 0
    
    _notify("Starting enhanced wizard driver...")
    
    # Give UAC time to appear first
    _notify("Waiting for UAC or installer window...")
    time.sleep(2.0)
    
    # Try UAC first
    if handle_uac_prompt(max_attempts=15, timeout_seconds=30):
        _notify("UAC handled, waiting for installer...")
        time.sleep(2.0)
    
    while (time.time() - start_time) < max_duration_seconds:
        try:
            # Check UAC again (might appear multiple times)
            if handle_uac_prompt(max_attempts=2, timeout_seconds=3):
                time.sleep(1.5)
                continue
            
            window = auto.GetForegroundControl()
            
            if not window:
                time.sleep(1.0)
                continue
            
            # CRITICAL FIX: Avoid getting stuck on the code editor or unrelated windows
            win_name = getattr(window, "Name", "") or ""
            if any(chk in win_name for chk in ["Visual Studio Code", "PC Controller", "cmd.exe", "PowerShell"]):
                # Don't analyze the editor itself - it's expensive and useless
                time.sleep(2.0)
                continue

            state = analyze_wizard_window(window)
            
            # More sophisticated stuck detection
            current_signature = (state.window_title, tuple(sorted(state.buttons_found)))
            last_signature = (last_window_title, tuple(sorted(last_buttons)))
            
            if current_signature == last_signature:
                stuck_count += 1
            else:
                stuck_count = 0
                last_window_title = state.window_title
                last_buttons = state.buttons_found.copy()
            
            if stuck_count >= max_stuck_iterations:
                _notify(f"Stuck for {stuck_count} iterations on: {state.window_title}")
                
                # Smart fallback actions
                fallback_worked = False
                
                # Try Enter key
                try:
                    pyautogui.press('enter')
                    time.sleep(1.0)
                    fallback_worked = True
                except Exception:
                    pass
                
                # Try clicking first visible button
                if not fallback_worked and state.buttons_found:
                    try:
                        all_btns = _get_all_buttons_from_window(window)
                        if all_btns:
                            _notify(f"Trying first button: {all_btns[0][0]}")
                            _safe_click_element(all_btns[0][1])
                            time.sleep(1.0)
                            fallback_worked = True
                    except Exception:
                        pass
                
                if fallback_worked:
                    stuck_count = 0
                    continue
                
                if stuck_count >= max_stuck_iterations + 5:
                    _notify("Completely stuck, giving up")
                    return False
            
            # Check completion
            if state.completion_detected:
                _notify("Completion detected!")
                _find_and_click_button_smart(window, [r"(?i)(finish|close|ok|å®Œæˆ)"])
                time.sleep(1.0)
                return True
            
            # Take action
            action_taken = interact_with_wizard_step(state)

            if action_taken:
                total_interactions += 1
                _notify(f"Action {total_interactions} taken")

                if state.current_step == WizardStep.PROGRESS:
                    time.sleep(2.5)
                else:
                    time.sleep(1.2)
            else:
                _notify("No action taken, waiting...")
                time.sleep(1.0)
        
        except Exception as e:
            _notify(f"Error in wizard loop: {e}")
            time.sleep(1.0)
    
    _notify("Wizard driver timeout")
    return False


def open_programs_and_features() -> Optional[Any]:
    """Open Windows Programs and Features control panel."""
    try:
        subprocess.Popen(["control", "appwiz.cpl"], shell=True)
        time.sleep(2.5)
        
        if not HAS_UIAUTOMATION:
            return None
        
        window = auto.WindowControl(
            searchDepth=2,
            RegexName=r"(?i)(programs and features|uninstall or change|ç¨‹åºå’ŒåŠŸèƒ½)"
        )
        
        if window and window.Exists(0, 0):
            return window
        
        return auto.GetForegroundControl()
    
    except Exception as e:
        _notify(f"Error opening Programs and Features: {e}")
        return None


def select_program_in_list(window, app_name: str) -> bool:
    """Find and select a program in the Programs and Features list."""
    if not HAS_UIAUTOMATION or not window:
        return False
    
    try:
        # Get all list items by walking the tree
        items = []
        
        def find_list_items(ctrl, depth=0):
            if depth > 8:
                return
            try:
                ctrl_type = getattr(ctrl, 'ControlTypeName', '')
                if 'ListItem' in ctrl_type or 'DataItem' in ctrl_type:
                    name = getattr(ctrl, 'Name', '')
                    if name:
                        items.append((name, ctrl))
                
                children = ctrl.GetChildren()
                if children:
                    for child in children:
                        find_list_items(child, depth + 1)
            except Exception:
                pass
        
        find_list_items(window)
        
        if not items:
            _notify("No list items found")
            return False
        
        _notify(f"Found {len(items)} programs in list")
        
        for item_name, item_ctrl in items:
            if _fuzzy_name_match(app_name, item_name):
                _notify(f"Found matching program: {item_name}")

                # Double-click to launch uninstaller
                _safe_click_element(item_ctrl)
                time.sleep(0.3)
                _safe_click_element(item_ctrl)
                time.sleep(0.3)

                return True

        _notify(f"No matching program found for: {app_name}")
        return False

    except Exception as e:
        _notify(f"Error selecting program: {e}")
        return False


def click_uninstall_button(window) -> bool:
    """Click the Uninstall/Change/Remove button in Programs and Features."""
    if not HAS_UIAUTOMATION or not window:
        return False
    
    # Get all buttons
    all_buttons = _get_all_buttons_from_window(window)
    
    for btn_name, btn_ctrl in all_buttons:
        if re.search(r'(?i)(uninstall|change|remove|å¸è½½)', btn_name):
            _notify(f"Found button: {btn_name}")
            return _safe_click_element(btn_ctrl)
    
    # Fallback: Alt+U
    try:
        pyautogui.hotkey('alt', 'u')
        time.sleep(0.5)
        return True
    except Exception:
        pass
    
    return False


def verify_uninstall_completion(app_name: str) -> bool:
    """Verify that the application has been removed."""
    entry = get_installed_application(app_name)
    
    if not entry:
        _notify(f"Verified: {app_name} no longer in registry")
        return True
    
    _notify(f"Warning: {app_name} still found in registry")
    return False


def uninstall_application(app_name: str, 
                          prefer_silent: bool = True,
                          allow_gui_fallback: bool = True,
                          dry_run: bool = False,
                          require_confirm: bool = False,
                          confirmed: bool = False) -> Dict[str, Any]:
    """
    Main uninstall orchestrator with comprehensive fallback chain.
    """
    
    if not app_name or not app_name.strip():
        return {"ok": False, "say": "No application name provided"}
    
    app_name = app_name.strip()
    _notify(f"Starting uninstall process for: {app_name}")
    _notify(f"I'll look for {app_name} in installed programs and try to remove it.")

    search_names = _expand_app_name_aliases(app_name)
    entry: Optional[UninstallEntry] = None
    matched_name = app_name
    for candidate in search_names:
        entry = get_installed_application(candidate)
        if entry:
            matched_name = candidate
            break

    if not entry:
        resp = {"ok": False, "say": f"Application '{app_name}' not found in installed programs"}
        _notify(resp["say"])
        return resp
    
    if matched_name.lower() != app_name.lower():
        _notify(f"Using alias match '{matched_name}' for uninstall search.")

    _notify(f"Found: {entry.display_name}")
    _notify(f"Publisher: {entry.publisher or 'Unknown'}")
    _notify(f"Version: {entry.version or 'Unknown'}")
    _notify(f"Installer Type: {entry.installer_type.value}")
    
    if dry_run:
        resp = {"ok": False, "say": f"Dry run: Would uninstall {entry.display_name} ({entry.installer_type.value})"}
        _notify(resp["say"])
        return resp

    # Safety: require explicit confirmation for destructive action unless caller passed confirmed=True
    if require_confirm and not confirmed:
        resp = {
            "ok": False,
            "say": f"Confirmation required to uninstall '{entry.display_name}'. To proceed call the action again with parameters: confirmed=True",
            "confirm_required": True,
            "app": entry.display_name
        }
        _notify(resp["say"])
        return resp
    
    resolved_names: List[str] = []
    _seen_names: Set[str] = set()

    def _collect_name(name: Optional[str]) -> None:
        if not name:
            return
        cleaned = name.strip()
        if not cleaned:
            return
        key = cleaned.lower()
        if key not in _seen_names:
            _seen_names.add(key)
            resolved_names.append(cleaned)

    _collect_name(entry.display_name)
    _collect_name(matched_name)
    for alias in search_names:
        _collect_name(alias)
    _collect_name(app_name)

    if prefer_silent:
        _notify("Attempting silent uninstall methods...")
        _notify("Method 2a: Trying winget...")
        for candidate_name in resolved_names:
            if try_winget_uninstall(candidate_name):
                if verify_uninstall_completion(entry.display_name):
                    resp = {"ok": True, "say": f"Successfully uninstalled {entry.display_name} via winget"}
                    _notify(resp["say"])
                    return resp
        _notify("Method 2b: Trying QuietUninstallString...")
        if try_quiet_uninstall_string(entry):
            time.sleep(2.0)
            if verify_uninstall_completion(entry.display_name):
                resp = {"ok": True, "say": f"Successfully uninstalled {entry.display_name} via QuietUninstallString"}
                _notify(resp["say"])
                return resp

        _notify("Method 2c: Trying MSI uninstall...")
        if try_msi_uninstall(entry):
            time.sleep(2.0)
            if verify_uninstall_completion(entry.display_name):
                resp = {"ok": True, "say": f"Successfully uninstalled {entry.display_name} via MSI"}
                _notify(resp["say"])
                return resp

        _notify("Method 2d: Trying silent switches...")
        if try_silent_with_switches(entry):
            time.sleep(2.0)
            if verify_uninstall_completion(entry.display_name):
                resp = {"ok": True, "say": f"Successfully uninstalled {entry.display_name} via silent switches"}
                _notify(resp["say"])
                return resp

        _notify("All silent methods failed or not applicable")
    
    if not allow_gui_fallback:
        resp = {"ok": False, "say": f"Silent uninstall failed for {entry.display_name} and GUI fallback is disabled"}
        _notify(resp["say"])
        return resp
    
    _notify("Falling back to GUI automation...")
    
    if not HAS_UIAUTOMATION:
        return {
            "ok": False,
            "say": "GUI automation not available (missing uiautomation)"
        }
    
    _notify("Opening Programs and Features...")
    window = open_programs_and_features()
    
    if not window:
        resp = {"ok": False, "say": "Failed to open Programs and Features"}
        _notify(resp["say"])
        return resp
    
    _notify("Selecting program in list...")
    if not select_program_in_list(window, entry.display_name or app_name):
        resp = {"ok": False, "say": f"Failed to locate {entry.display_name} in Programs and Features"}
        _notify(resp["say"])
        return resp
    
    _notify("Clicking Uninstall button...")
    if not click_uninstall_button(window):
        _notify("Uninstall button not found, but double-click may have triggered it")
        _notify("I tried to click the uninstall button; if nothing happened, you may need to confirm manually.")
    
    # Give time for uninstaller to start
    time.sleep(2.0)
    
    _notify("Starting enhanced wizard driver with UAC handling...")
    success = drive_uninstaller_wizard(
        max_duration_seconds=1800,
        max_stuck_iterations=12
    )
    
    _notify("Verifying uninstall completion...")
    
    try:
        pyautogui.press('f5')
        time.sleep(1.0)
    except Exception:
        pass
    
    is_removed = verify_uninstall_completion(entry.display_name)
    
    if is_removed:
        resp = {"ok": True, "say": f"Successfully uninstalled {entry.display_name}"}
        _notify(resp["say"])
        return resp
    elif success:
        resp = {"ok": True, "say": f"Uninstaller completed for {entry.display_name}. A restart may be required."}
        _notify(resp["say"])
        return resp
    else:
        resp = {"ok": False, "say": f"Uninstall process completed but {entry.display_name} may still be present. Check manually."}
        _notify(resp["say"])
        return resp


def _uninstall(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Integration point for execute_action system.
    """
    app_name = (
        parameters.get("name") or 
        parameters.get("app") or 
        parameters.get("target") or 
        ""
    ).strip()
    
    if not app_name:
        return {"ok": False, "say": "Which application should I uninstall?"}
    
    def _param_to_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "y"}
        return bool(value)

    dry_run = _param_to_bool(parameters.get("dry_run"), default=False)

    raw_require_confirm = parameters.get("require_confirm")
    require_confirm = _param_to_bool(raw_require_confirm, default=False)

    raw_confirmed = parameters.get("confirmed")
    if raw_confirmed is None:
        confirmed = not require_confirm
    else:
        confirmed = _param_to_bool(raw_confirmed, default=False)

    return uninstall_application(
        app_name=app_name,
        prefer_silent=True,
        allow_gui_fallback=True,
        dry_run=dry_run,
        require_confirm=require_confirm,
        confirmed=confirmed
    )


# ============================================================================
# EXISTING ACTION HANDLERS (PRESERVED FROM ORIGINAL FILE)
# ============================================================================

def _resolve_browser_exe(name: str) -> Optional[str]:
    """Resolve browser executable path."""
    n = (name or "").lower()
    path_in_path = shutil.which(f"{n}.exe") or shutil.which(n)
    if path_in_path:
        return path_in_path
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pfx86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", r"C:\Users\%USERNAME%\AppData\Local")
    candidates = []
    if n in {"brave"}:
        candidates += [
            os.path.join(pf, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]
    if n in {"chrome", "google"}:
        candidates += [
            os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(pfx86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
        ]
    if n in {"edge", "msedge"}:
        candidates += [
            os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(pfx86, "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
    if n in {"firefox", "mozilla"}:
        candidates += [
            os.path.join(pf, "Mozilla Firefox", "firefox.exe"),
            os.path.join(pfx86, "Mozilla Firefox", "firefox.exe"),
        ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _visible_search_and_click(query: str, browser: Optional[str], site_domain: Optional[str], engine: str, click_first: bool) -> Tuple[bool, bool, Optional[str]]:
    """Open a browser/search page, perform a search visibly, and optionally click the first result."""
    focused = False
    if engine == "youtube":
        base_url = "https://www.youtube.com"
    else:
        base_url = "https://www.google.com"

    try:
        exe = _resolve_browser_exe(browser) if browser else None
        if exe:
            try:
                subprocess.Popen([exe, base_url], shell=True)
                time.sleep(1.2)
                focused = True
            except Exception:
                focused = False
        if not focused:
            webbrowser.open(base_url)
            time.sleep(1.2)
            focused = True
    except Exception:
        focused = False

    if not focused:
        return False, False, None

    try:
        if engine == "youtube":
            try:
                pyautogui.press('/')
                time.sleep(0.15)
            except Exception:
                pass
        else:
            try:
                pyautogui.hotkey('ctrl', 'k')
                time.sleep(0.15)
            except Exception:
                pass
        pyautogui.typewrite(query if not site_domain else (f"site:{site_domain} {query}"), interval=0.02)
        pyautogui.press('enter')
    except Exception:
        return False, False, None

    time.sleep(2.0)

    try:
        analysis = describe_screen()
    except Exception:
        analysis = None

    clicked = False
    if click_first:
        try:
            hint = analysis if isinstance(analysis, str) and analysis else query
            clicked = click_first_search_result(min_y=140, verify=True, prefer_keyboard=False, hint_text=hint)
        except Exception:
            clicked = False

    return True, clicked, (analysis if isinstance(analysis, str) else None)


def _open(parameters: Dict[str, Any]) -> Dict[str, Any]:
    target = parameters.get("target") or parameters.get("path") or parameters.get("app")
    url = parameters.get("url")
    if url:
        _notify(f"Opening {url} in browser.")
    if url:
        try:
            webbrowser.open(url)
            time.sleep(0.6)
            return {"ok": True, "say": f"Opening {url}"}
        except Exception as e:
            return {"ok": False, "say": f"Couldn't open URL: {e}"}
    if target:
        tlow = str(target).lower()
        _notify(f"Opening {tlow} for you.")
        if ("calculator" in tlow) or (" calc" in tlow) or tlow == "calc":
            target = "calc.exe"
        elif "notepad" in tlow:
            target = "notepad.exe"
        elif "paint" in tlow or "mspaint" in tlow:
            target = "mspaint.exe"
        elif tlow in {"cmd", "command prompt", "cmd.exe"}:
            target = "cmd.exe"
        elif any(b in tlow for b in ["brave", "chrome", "google", "edge", "msedge", "firefox", "mozilla"]):
            for bname in ["brave", "chrome", "edge", "msedge", "firefox"]:
                if bname in tlow or (bname == "edge" and "msedge" in tlow) or (bname == "chrome" and "google" in tlow):
                    exe = _resolve_browser_exe(bname)
                    if exe:
                        try:
                            subprocess.Popen([exe], shell=True)
                            time.sleep(0.6)
                            return {"ok": True, "say": f"Opening {bname}"}
                        except Exception as e:
                            return {"ok": False, "say": f"Couldn't open {bname}: {e}"}
        try:
            os.startfile(target)
            time.sleep(0.8)
            resp = {"ok": True, "say": f"Opening {os.path.basename(target) or target}"}
            _notify(resp["say"])
            return resp
        except Exception:
            try:
                subprocess.Popen([target], shell=True)
                time.sleep(0.8)
                resp = {"ok": True, "say": f"Opening {target}"}
                _notify(resp["say"])
                return resp
            except Exception as e:
                resp = {"ok": False, "say": f"Couldn't open {target}: {e}"}
                _notify(resp["say"])
                return resp
    return {"ok": False, "say": "What should I open?"}


def _search(parameters: Dict[str, Any]) -> Dict[str, Any]:
    query = (parameters.get("query") or "").strip()
    browser = (parameters.get("browser") or "").lower().strip()
    engine = (parameters.get("engine") or "google").lower().strip()
    site = (parameters.get("site") or "").strip()
    open_first = bool(parameters.get("open_first", False))
    if not query:
        return {"ok": False, "say": "What should I search for?"}
    _notify(f"Searching for {query}.")
    site_arg = site or ("youtube.com" if engine == "youtube" else None)

    if open_first:
        visible_ok, clicked_first, analysis = _visible_search_and_click(
            query=query,
            browser=browser,
            site_domain=site_arg,
            engine=engine,
            click_first=True,
        )
        if visible_ok and clicked_first:
            say = f"Opened first result for {query}."
            return {"ok": True, "say": say}
        if open_and_click_first and open_and_click_first(query=query, browser=browser, site=site_arg):
            return {"ok": True, "say": f"Opened first result for {query}."}
        guidance = None
        if _advise_next_step:
            try:
                guidance = _advise_next_step(goal=f"Open the first search result for: {query}")
            except Exception:
                guidance = None
        say = "I couldn't open the first result automatically. "
        if guidance:
            say += f"Try these steps: {guidance}"
        else:
            say += "I can describe the screen or try again."
        return {"ok": False, "say": say}
    else:
        visible_ok, clicked_first, analysis = _visible_search_and_click(
            query=query,
            browser=browser,
            site_domain=site_arg,
            engine=engine,
            click_first=False,
        )
        if visible_ok:
            if clicked_first:
                return {"ok": True, "say": f"Opened first result for {query}."}
            else:
                return {"ok": True, "say": f"Searching for {query}."}
    if engine == "youtube":
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    else:
        url = f"https://www.google.com/search?q={quote_plus(query)}"
    try:
        if browser:
            exe = _resolve_browser_exe(browser)
            if exe:
                subprocess.Popen([exe, url], shell=True)
            else:
                webbrowser.open(url)
        else:
            webbrowser.open(url)
        return {"ok": True, "say": f"Searching for {query}"}
    except Exception:
        pass
    guidance = None
    if _advise_next_step:
        try:
            guidance = _advise_next_step(goal=f"Search and view results for: {query}")
        except Exception:
            guidance = None
    say = "I couldn't open the browser to search. "
    if guidance:
        say += f"Try this: {guidance}"
    else:
        say += "You can try opening the browser manually and I'll continue from there."
    return {"ok": False, "say": say}


def _type(parameters: Dict[str, Any]) -> Dict[str, Any]:
    text = parameters.get("text")
    if not text:
        return {"ok": False, "say": "What should I type?"}
    try:
        pyautogui.typewrite(text)
    except Exception:
        pass
    resp = {"ok": True, "say": f"Typed: {str(text)[:120]}"}
    _notify(resp["say"])
    return resp


def _normalize_key_name(token: Any) -> Optional[str]:
    if token is None:
        return None
    raw = str(token).strip().lower()
    if not raw:
        return None
    raw = re.sub(r"[\s\-]+", " ", raw)
    raw = re.sub(r"\s*(?:key|button)$", "", raw).strip()
    synonyms = {
        "control": "ctrl",
        "ctl": "ctrl",
        "ctrl": "ctrl",
        "shift": "shift",
        "alternate": "alt",
        "option": "alt",
        "alt": "alt",
        "menu": "alt",
        "windows": "win",
        "window": "win",
        "win": "win",
        "command": "win",
        "cmd": "win",
        "escape": "esc",
        "esc": "esc",
        "return": "enter",
        "enter": "enter",
        "spacebar": "space",
        "space": "space",
        "tab": "tab",
        "caps lock": "capslock",
        "capslock": "capslock",
        "page up": "pageup",
        "pageup": "pageup",
        "page down": "pagedown",
        "pagedown": "pagedown",
        "delete": "delete",
        "del": "delete",
        "backspace": "backspace",
        "bksp": "backspace",
        "print screen": "printscreen",
        "prtsc": "printscreen",
        "insert": "insert",
        "home": "home",
        "end": "end",
        "up arrow": "up",
        "arrow up": "up",
        "up": "up",
        "down arrow": "down",
        "arrow down": "down",
        "down": "down",
        "left arrow": "left",
        "arrow left": "left",
        "left": "left",
        "right arrow": "right",
        "arrow right": "right",
        "right": "right",
        "volume up": "volumeup",
        "volume down": "volumedown",
        "vol up": "volumeup",
        "vol down": "volumedown",
        "play pause": "playpause",
        "caps": "capslock",
    }
    if raw in synonyms:
        return synonyms[raw]
    compact = raw.replace(" ", "")
    if compact in synonyms:
        return synonyms[compact]
    if re.fullmatch(r"f\d{1,2}", compact):
        return compact
    if re.fullmatch(r"\d", compact):
        return compact
    if compact in {"up", "down", "left", "right"}:
        return compact
    return compact or None


def _parse_key_sequences(spec: Any) -> List[List[str]]:
    combos: List[List[str]] = []
    if spec is None:
        return combos
    if isinstance(spec, (list, tuple)):
        if spec and isinstance(spec[0], (list, tuple)):
            iterables = spec
        else:
            iterables = [spec]
        for seq in iterables:
            current: List[str] = []
            if isinstance(seq, (list, tuple)):
                for token in seq:
                    norm = _normalize_key_name(token)
                    if norm:
                        current.append(norm)
                    elif isinstance(token, str) and " " in token:
                        for part in token.split():
                            norm_part = _normalize_key_name(part)
                            if norm_part:
                                current.append(norm_part)
            else:
                norm = _normalize_key_name(seq)
                if norm:
                    current.append(norm)
            if current:
                combos.append(current)
        return combos
    text = str(spec)
    if not text.strip():
        return combos
    sequence_splitter = re.compile(r"(?i)\b(?:and then|then|after|followed by|phir)\b|,|;|->")
    combo_splitter = re.compile(r"(?i)\b(?:plus|and|with|along with|together with)\b|[+&]")
    for segment in sequence_splitter.split(text):
        seg = (segment or "").strip(" ,;-")
        if not seg:
            continue
        tokens = combo_splitter.split(seg)
        current: List[str] = []
        for token in tokens:
            tok = (token or "").strip()
            if not tok:
                continue
            norm = _normalize_key_name(tok)
            if norm:
                current.append(norm)
                continue
            if " " in tok:
                for part in tok.split():
                    norm_part = _normalize_key_name(part)
                    if norm_part:
                        current.append(norm_part)
        if current:
            combos.append(current)
    return combos


def _describe_key_combos(combos: List[List[str]]) -> str:
    if not combos:
        return ""
    def _pretty_key(name: str) -> str:
        if not name:
            return ""
        if len(name) == 1:
            return name.upper()
        return name.replace("_", " ").upper()
    parts: List[str] = []
    for combo in combos:
        pretty = [k for k in (_pretty_key(key) for key in combo) if k]
        if pretty:
            parts.append(" + ".join(pretty))
    return ", then ".join(parts)


def _press_key_combo(combo: List[str]) -> bool:
    keys = [k for k in combo if k]
    if not keys:
        return False
    try:
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            # Press all keys simultaneously using hotkey
            pyautogui.hotkey(*keys)
        if not ASSISTANT_SPEAK_ONLY:
            key_desc = " + ".join(keys) if len(keys) > 1 else keys[0]
            print(f"[hotkey] Pressed: {key_desc}")
        return True
    except Exception as e:
        if not ASSISTANT_SPEAK_ONLY:
            print(f"[hotkey] Failed to press {' + '.join(keys)}: {e}")
        return False


def _format_seconds_brief(seconds: float) -> str:
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


def _hotkey(parameters: Dict[str, Any]) -> Dict[str, Any]:
    combo_spec = parameters.get("keys") or parameters.get("combo") or parameters.get("sequence")
    combos = _parse_key_sequences(combo_spec)
    if not combos:
        return {"ok": False, "say": "Which keys should I press?"}
    if not ASSISTANT_SPEAK_ONLY:
        print(f"[hotkey] Parsed key sequences: {combos}")
    executed = 0
    for combo in combos:
        if _press_key_combo(combo):
            executed += 1
        time.sleep(0.08)  # Slightly longer delay for reliability
    if executed == 0:
        return {"ok": False, "say": "I couldn't press those keys."}
    description = _describe_key_combos(combos)
    resp = {"ok": True, "say": f"Pressed keys: {description}" if description else "Pressed the requested keys."}
    _notify(resp["say"])
    return resp

def _hotkey_loop(parameters: Dict[str, Any]) -> Dict[str, Any]:
    combo_spec = parameters.get("keys") or parameters.get("combo") or parameters.get("sequence")
    combos = _parse_key_sequences(combo_spec)
    if not combos:
        return {"ok": False, "say": "Which keys should I loop through?"}
    def _safe_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    def _safe_int(value: Any) -> Optional[int]:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    interval = parameters.get("interval_seconds") or parameters.get("interval")
    duration = parameters.get("duration_seconds") or parameters.get("duration")
    repeats = parameters.get("repeat_count") or parameters.get("repeats") or parameters.get("times")
    interval_seconds = _safe_float(interval)
    duration_seconds = _safe_float(duration)
    repeat_count = _safe_int(repeats)
    MAX_DURATION = 3600.0
    MAX_ITERATIONS = 360
    DEFAULT_INTERVAL = 5.0
    DEFAULT_ITERATIONS = 10
    if duration_seconds is not None:
        duration_seconds = max(0.0, min(duration_seconds, MAX_DURATION))
    if interval_seconds is None:
        if duration_seconds is not None and repeat_count:
            interval_seconds = duration_seconds / max(repeat_count, 1)
        elif duration_seconds is not None:
            interval_seconds = max(1.0, min(duration_seconds / 10.0 if duration_seconds > 10 else duration_seconds / 2 or DEFAULT_INTERVAL, 30.0))
        else:
            interval_seconds = DEFAULT_INTERVAL
    interval_seconds = max(0.1, min(interval_seconds, 300.0))
    if repeat_count is not None:
        repeat_count = max(1, min(repeat_count, MAX_ITERATIONS))
    description = _describe_key_combos(combos)
    parts: List[str] = []
    if repeat_count is not None:
        parts.append(f"{repeat_count} time{'s' if repeat_count != 1 else ''}")
    if interval_seconds:
        parts.append(f"every {interval_seconds:g} seconds")
    if duration_seconds:
        parts.append(f"for about {duration_seconds/60.0:g} minutes" if duration_seconds >= 60 else f"for about {duration_seconds:g} seconds")
    summary = (f"I'll keep pressing {description or 'those keys'} " + ", ".join(parts) + ".") if parts else f"I'll keep pressing {description or 'those keys'} for a bit."
    _notify(summary)
    iterations = 0
    start = time.time()
    last_success = False
    while True:
        last_success = False
        for combo in combos:
            if _press_key_combo(combo):
                last_success = True
            time.sleep(0.08)  # Slightly longer delay for reliability
        iterations += 1
        if repeat_count is not None and iterations >= repeat_count:
            break
        if duration_seconds is not None and (time.time() - start) >= duration_seconds:
            break
        if repeat_count is None and duration_seconds is None and iterations >= DEFAULT_ITERATIONS:
            break
        if iterations >= MAX_ITERATIONS:
            break
        # Iteration progress output every cycle
        if not ASSISTANT_SPEAK_ONLY:
            elapsed_so_far = time.time() - start
            print(f"[hotkey_loop] iteration {iterations} (elapsed: {elapsed_so_far:.1f}s, next in {interval_seconds}s)")
        time.sleep(interval_seconds)
    elapsed = time.time() - start
    say = f"Finished pressing {description or 'the keys'} {iterations} time{'s' if iterations != 1 else ''}" + (f" over {elapsed:.1f}s." if elapsed > 0 else ".") if last_success else "I couldn't trigger those keys reliably."
    resp = {"ok": last_success, "iterations": iterations, "elapsed_seconds": elapsed, "say": say}
    _notify(say)
    return resp


def _mouse(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Handle simple mouse automation helpers (move/click)."""
    action = (parameters.get("action") or "click").lower()
    x = parameters.get("x")
    y = parameters.get("y")
    button = (parameters.get("button") or "left").lower()

    try:
        if action == "move":
            if x is None or y is None:
                return {"ok": False, "say": "Where should I move the mouse?"}
            pyautogui.moveTo(int(x), int(y), duration=0.18)
            resp = {"ok": True, "say": f"Moved cursor to ({x}, {y})."}
            _notify(resp["say"])
            return resp

        if action in {"click", "single"}:
            if x is not None and y is not None:
                pyautogui.click(int(x), int(y), button=button)
            else:
                pyautogui.click(button=button)
            resp = {"ok": True, "say": "Clicked."}
            _notify(resp["say"])
            return resp

        if action == "double_click":
            if x is not None and y is not None:
                pyautogui.doubleClick(int(x), int(y), button=button)
            else:
                pyautogui.doubleClick(button=button)
            resp = {"ok": True, "say": "Double-clicked."}
            _notify(resp["say"])
            return resp

        if action == "right_click":
            if x is not None and y is not None:
                pyautogui.rightClick(int(x), int(y))
            else:
                pyautogui.rightClick()
            resp = {"ok": True, "say": "Right-clicked."}
            _notify(resp["say"])
            return resp

        return {"ok": False, "say": "I don't recognise that mouse action."}
    except Exception as exc:
        return {"ok": False, "say": "Mouse action failed.", "metadata": {"error": str(exc)}}


def _scroll(parameters: Dict[str, Any]) -> Dict[str, Any]:
    amount = parameters.get("amount")
    if amount is None:
        lines = parameters.get("lines")
        if isinstance(lines, (int, float)):
            amount = int(lines) * -120
        else:
            amount = -600

    try:
        pyautogui.scroll(int(amount))
    except Exception as exc:
        return {"ok": False, "say": "Couldn't scroll right now.", "metadata": {"error": str(exc)}}

    direction = "up" if amount > 0 else "down"
    magnitude = abs(int(amount))
    resp = {"ok": True, "say": f"Scrolled {direction} by {magnitude} steps."}
    _notify(resp["say"])
    return resp


def _get_llm_response(prompt: str) -> Optional[str]:
    """Try multiple AI backends to get a response."""
    text: Optional[str] = None

    try:
        plan = _llm_plan(prompt)
        if isinstance(plan, dict):
            text = (plan.get("response") or plan.get("text") or "").strip()
    except Exception:
        text = None

    if text:
        return text

    try:
        from .expressive_tts import request_text_from_ai as _request_text

        result = _request_text(prompt)
        if result and isinstance(result, str):
            text = result.strip()
    except Exception:
        text = None

    if text:
        return text

    return None


def _open_chatgpt_in_browser(preferred_browser: Optional[str] = None) -> bool:
    """Open the ChatGPT website in the default or preferred browser and try to focus it."""
    try:
        model = os.environ.get("CHATGPT_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        url = f"https://chat.openai.com/?model={quote_plus(model)}"
        exe = _resolve_browser_exe(preferred_browser) if preferred_browser else None
        if exe:
            try:
                subprocess.Popen([exe, url], shell=True)
                time.sleep(1.2)
                return True
            except Exception:
                pass
        webbrowser.open(url)
        time.sleep(1.2)
        return True
    except Exception:
        return False


def _safe_select_all_copy() -> str:
    """Try multiple combos to select all and copy, then return clipboard text (may be empty)."""
    text = ""
    try:
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.2)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.2)
        import pyperclip
        text = pyperclip.paste() or ""
    except Exception:
        # try Shift+Insert copy path as rare fallback
        try:
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'insert')
            time.sleep(0.2)
            import pyperclip as _pc
            text = _pc.paste() or ""
        except Exception:
            text = ""
    return text


def _chatgpt_submit_prompt_and_copy(prompt: str, preferred_browser: Optional[str] = None) -> Optional[str]:
    """Open ChatGPT, submit the prompt, adaptively wait for completion, and copy the answer.

    Heuristics:
    - Focus near bottom of the page (input box region) and type the prompt
    - Press Enter to submit
    - Adaptive wait: periodically copy page text and wait until content size stabilizes
    - Small scrolls to ensure full response is in view before copying final
    """
    # Ensure page is open
    if not _open_chatgpt_in_browser(preferred_browser):
        return None

    # Allow page to load or switch tab
    base_wait = float(os.environ.get("CHATGPT_BOOT_WAIT", "6"))
    time.sleep(max(2.0, min(base_wait, 15.0)))

    # Focus input box by clicking near bottom center then clear and type
    try:
        width, height = pyautogui.size()
        pyautogui.moveTo(width // 2, int(height * 0.92))
        pyautogui.click()
        time.sleep(0.25)
        # Clear any placeholder text
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.1)
        pyautogui.press('backspace')
        time.sleep(0.1)
        pyautogui.typewrite(prompt, interval=0.02)
        pyautogui.press('enter')
    except Exception:
        return None

    # Prepare to launch WhatsApp once the answer is ready

    _notify("Let me wait for ChatGPT to finish writing — I’ll grab the best bits.")

    # Adaptive wait loop
    total_timeout = float(os.environ.get("CHATGPT_WAIT_SECONDS", "28"))
    min_wait = min(6.0, total_timeout * 0.3)
    poll = 1.2
    start = time.time()
    last_len = 0
    stable_count = 0
    captured = ""

    while (time.time() - start) < total_timeout:
        time.sleep(poll)
        # Click response area around mid-screen to ensure selection targets content, then copy
        try:
            width, height = pyautogui.size()
            pyautogui.moveTo(width // 2, int(height * 0.55))
            pyautogui.click()
            time.sleep(0.15)
        except Exception:
            pass
        txt = _safe_select_all_copy()
        # If login screen or empty page, keep waiting
        if not txt or ("Log in" in txt and "ChatGPT" in txt):
            continue
        captured = txt
        n = len(txt)
        if (time.time() - start) < min_wait:
            last_len = n
            continue
        if n <= last_len + 5:
            stable_count += 1
        else:
            stable_count = 0
        last_len = n
        # Consider stable after a few consecutive polls without growth
        if stable_count >= 3:
            break

    # One more scroll up to ensure start is included, then select-all-copy again
    try:
        pyautogui.scroll(800)
        time.sleep(0.2)
        pyautogui.scroll(-800)
        time.sleep(0.2)
    except Exception:
        pass
    final_text = _safe_select_all_copy() or captured
    if not final_text:
        return None
    return final_text.strip()


def _fetch_notes_via_chatgpt_browser(topic: str) -> Optional[str]:
    """Open ChatGPT website in a browser, search there with a crafted prompt, then proceed.

    This explicitly follows the sequence the user described: go to ChatGPT in the browser,
    type the query, wait for the answer, and then continue by copying and cleaning the content.
    """
    try:
        prompt = (
            f"Please write concise, friendly notes about {topic}. "
            "Use 5-9 bullet points or short paragraphs with tips and examples. "
            "Avoid disclaimers, headings, or markdown decorations."
        )
        # Step 1: open ChatGPT site in a browser tab
        _notify("Opening ChatGPT and searching there first.")
        raw = _chatgpt_submit_prompt_and_copy(prompt)
        if not raw:
            return None
        # Step 2: clean up content and return
        cleaned = _strip_ai_fluff(raw, topic)
        return cleaned or raw.strip() or None
    except Exception:
        return None


def _strip_ai_fluff(text: str, topic: str = "") -> str:
    """Remove common AI disclaimers and keep concise content.
    Also lightly filter to lines relevant to topic keywords if provided.
    """
    if not text:
        return ""
    s = str(text)
    # Remove boilerplate disclaimers and filler lines
    patterns = [
        r"(?i)^\s*as an ai.*$",
        r"(?i)^\s*i am an ai.*$",
        r"(?i)^\s*i cannot.*$",
        r"(?i)^\s*disclaimer:.*$",
        r"(?i)^\s*note: this is.*$",
        r"(?i)^\s*here (are|is)\b.*$",
        r"(?i)^\s*certainly[!\.]*\s*$",
        r"(?i)^\s*of course[!\.]*\s*$",
        r"(?i)^\s*(in )?conclusion:?\s*$",
        r"(?i)^\s*summary:?\s*$",
        r"(?i)^\s*key takeaways:?\s*$",
        r"(?i)^\s*overall:?\s*$",
        r"(?i)^\s*remember:?\s*$",
        r"(?i)^\s*#\s+.*$",           # markdown heading
        r"(?i)^\s*##\s+.*$",          # markdown subheading
    ]
    for pat in patterns:
        s = re.sub(pat, "", s, flags=re.MULTILINE)
    # Trim extra blank lines
    lines = [ln.rstrip() for ln in s.splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    # If topic provided, keep lines that look more relevant (very light heuristic)
    if topic:
        topic_tokens = [t for t in re.split(r"\W+", topic.lower()) if len(t) > 2]
        if topic_tokens:
            scored = []
            for ln in lines:
                low = ln.lower()
                score = sum(1 for t in topic_tokens if t in low)
                scored.append((score, ln))
            # Keep all if overall content is short; otherwise prefer lines with some score
            if len(lines) > 10 and any(sc > 0 for sc, _ in scored):
                lines = [ln for sc, ln in scored if sc > 0]
    cleaned = "\n".join(lines)
    # Collapse 3+ blank lines to a single blank line
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _ai_write_notepad(parameters: Dict[str, Any]) -> Dict[str, Any]:
    global _AI_NOTEPAD_ACTIVE, _AI_NOTEPAD_LOCK
    if not _AI_NOTEPAD_LOCK.acquire(blocking=False):
        return {"ok": False, "say": "Still finishing the previous notes — give me a moment."}
    _AI_NOTEPAD_ACTIVE = True
    try:
        topic = (parameters.get("topic") or parameters.get("text") or "").strip()
        if not topic:
            return {"ok": False, "say": "What should I write about?"}

        _notify(f"I'll draft notes on '{topic}' with AI and put them in Notepad.")

        workflow_result: Optional[WorkflowResult] = None
        workflow_error: Optional[str] = None

        try:
            workflow = _get_ai_notepad_workflow()
            workflow_result = workflow.run(topic)
        except (BrowserOpenError, PromptSubmissionError, ResponseCollectionError, NotepadAutomationError) as exc:
            workflow_error = str(exc)
            _ai_log(f"Workflow raised recoverable error: {exc}")
        except Exception as exc:
            workflow_error = str(exc)
            _ai_log(f"Workflow raised unexpected error: {exc}")

        if workflow_result:
            if workflow_result.cleaned_text.strip():
                quality_status = workflow_result.quality.status.name
                quality_success = workflow_result.metadata.get(
                    "quality_success",
                    workflow_result.quality.is_success(),
                )
                quality_label = quality_status.replace("_", " ").title()
                if quality_success:
                    say = f"Drafted {quality_label.lower()} notes in Notepad."
                else:
                    say = "Drafted notes in Notepad. Give them a quick glance to be safe."
                    _ai_log(
                        "Workflow completed with quality warning; skipping legacy fallback to avoid duplicates."
                    )
                _notify(say)
                metadata = dict(workflow_result.metadata)
                metadata["quality_status"] = quality_status
                metadata["workflow_ok"] = workflow_result.ok
                metadata["note_written"] = workflow_result.note_written
                if not quality_success:
                    metadata["quality_warning"] = True
                return {
                    "ok": True,
                    "say": say,
                    "quality": quality_status,
                    "metadata": metadata,
                }
            if not workflow_error and workflow_result.metadata:
                workflow_error = workflow_result.metadata.get("error")

        if workflow_error:
            _notify("Workflow hit a snag. I couldn't finish the Notepad draft.")
            return {
                "ok": False,
                "say": "Couldn't prepare the Notepad draft right now.",
                "quality": workflow_result.quality.status.name if workflow_result else "ERROR",
                "metadata": {
                    "workflow_error": workflow_error,
                    "metadata": workflow_result.metadata if workflow_result else {},
                },
            }

        return {
            "ok": False,
            "say": "Workflow ended but no content was produced.",
            "quality": "EMPTY",
            "metadata": workflow_result.metadata if workflow_result else {"error": "empty"},
        }
    finally:
        _AI_NOTEPAD_ACTIVE = False
        try:
            _AI_NOTEPAD_LOCK.release()
        except Exception:
            pass


def _settings(parameters: Dict[str, Any]) -> Dict[str, Any]:
    name = (parameters.get("name") or "").lower()
    ms_map = {
        "bluetooth": "ms-settings:bluetooth",
        "bt": "ms-settings:bluetooth",
        "wifi": "ms-settings:network-wifi",
        "network": "ms-settings:network",
        "display": "ms-settings:display",
        "sound": "ms-settings:sound",
        "audio": "ms-settings:sound",
        "updates": "ms-settings:windowsupdate",
        "update": "ms-settings:windowsupdate",
        "privacy": "ms-settings:privacy",
        "apps": "ms-settings:appsfeatures",
        "personalization": "ms-settings:personalization",
        "date": "ms-settings:dateandtime",
        "time": "ms-settings:dateandtime",
        "power": "ms-settings:powersleep",
    }


    uri = ms_map.get(name)
    if uri:
        try:
            try:
                _notify(f"Opening {name} settings — one sec.")
            except Exception:
                pass
            subprocess.Popen(["start", uri], shell=True)

            return {"ok": True, "say": f"Opened {name} settings."}
        except Exception as e:
            return {"ok": False, "say": f"Couldn't open {name} settings: {e}"}
    return {"ok": False, "say": "Which setting?"}


def _screen_describe(parameters: Dict[str, Any]) -> Dict[str, Any]:
    try:
        _notify("Scanning the screen — narrating like a documentary host.")
    except Exception:
        pass
    text = describe_screen()
    return {"ok": True, "say": text}


def play_song_on_spotify(song: str, browser: Optional[str] = None) -> Dict[str, Any]:
    """Open Spotify DESKTOP APP ONLY and play the first result for `song`.

    Strategy (desktop-only, with proper timing):
    1. Launch Spotify desktop app via Start menu.
    2. WAIT 5 seconds for Spotify to fully load.
    3. Press Ctrl+K to open search, WAIT 1.5 seconds for search box.
    4. Type the song name, WAIT 3 seconds for results to appear.
    5. Use arrow down + Enter to select and play first result.
    """
    if not song or not str(song).strip():
        return {"ok": False, "say": "Which song should I play?"}
    
    q = str(song).strip()
    print(f"[Spotify] Play request: {q}")
    _notify(f"Opening Spotify and playing '{q}'...")

    # =========================================================================
    # STEP 1: Open Spotify Desktop App
    # =========================================================================
    print("[Spotify] STEP 1: Opening Spotify app...")
    opened = False
    
    # Try to open Spotify
    try:
        opened = bool(open_app_via_start('spotify'))
    except Exception:
        pass
    
    if not opened:
        try:
            # Fallback: Direct URI launch
            subprocess.Popen(['start', 'spotify:'], shell=True)
            opened = True
        except Exception:
            pass
    
    if not opened:
        return {"ok": False, "say": "Couldn't open Spotify app. Please make sure it's installed."}
    
    print("[Spotify] Spotify launched!")

    # =========================================================================
    # STEP 2: WAIT for Spotify to FULLY LOAD (5 seconds)
    # =========================================================================
    print("[Spotify] STEP 2: Waiting 5 seconds for Spotify to fully load...")
    time.sleep(5.0)
    
    # Try to focus the Spotify window
    if HAS_UIAUTOMATION:
        try:
            spotify_window = auto.WindowControl(searchDepth=2, RegexName=r"(?i)spotify")
            if spotify_window and spotify_window.Exists(1, 1):
                try:
                    spotify_window.SetFocus()
                    print("[Spotify] Focused Spotify window")
                except Exception:
                    pass
        except Exception:
            pass
    
    # Extra wait to ensure UI is interactive
    time.sleep(1.0)
    print("[Spotify] Spotify should be ready now")

    # =========================================================================
    # STEP 3: Press Ctrl+K to open search, WAIT 1.5 seconds
    # =========================================================================
    print("[Spotify] STEP 3: Pressing Ctrl+K to open search...")
    
    try:
        pyautogui.hotkey('ctrl', 'k')
        print("[Spotify] Ctrl+K pressed, waiting 1.5 seconds for search box...")
        time.sleep(1.5)
    except Exception as e:
        print(f"[Spotify] Ctrl+K failed: {e}")
        # Try alternative - click in the search area
        try:
            pyautogui.hotkey('ctrl', 'l')
            time.sleep(1.0)
        except Exception:
            pass

    # =========================================================================
    # STEP 4: Type song name and WAIT 3 seconds for results
    # =========================================================================
    print(f"[Spotify] STEP 4: Typing '{q}'...")
    
    try:
        # Clear any existing text first
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.2)
        pyautogui.press('delete')
        time.sleep(0.2)
        
        # Type the song name character by character for reliability
        for char in q:
            try:
                pyautogui.press(char)
            except Exception:
                # If character can't be pressed directly, try write
                pyautogui.write(char)
            time.sleep(0.03)
        
        print(f"[Spotify] Typed '{q}', waiting 3 seconds for search results...")
        time.sleep(3.0)
        
    except Exception as e:
        print(f"[Spotify] Failed to type: {e}")
        # Fallback to typewrite
        try:
            pyautogui.typewrite(q, interval=0.05)
            time.sleep(3.0)
        except Exception:
            return {"ok": False, "say": f"Failed to search for '{q}' in Spotify."}

    # =========================================================================
    # STEP 5: Press ENTER to play first result
    # =========================================================================
    print("[Spotify] STEP 5: Pressing Enter to play first result...")
    
    result_played = False
    
    # Just press Enter to play the first result
    try:
        pyautogui.press('enter')
        time.sleep(0.5)
        result_played = True
        print("[Spotify] Enter pressed - song should be playing now!")
    except Exception as e:
        print(f"[Spotify] Enter failed: {e}")
    
    # Method 3: Try clicking on the first result using UI Automation
    if HAS_UIAUTOMATION:
        try:
            print("[Spotify] Trying to click first result via UI Automation...")
            spotify_window = auto.WindowControl(searchDepth=2, RegexName=r"(?i)spotify")
            
            if spotify_window and spotify_window.Exists(0.5, 0.5):
                # Look for clickable items (songs/tracks)
                for idx in range(1, 10):
                    try:
                        # Try to find list items (song results)
                        item = auto.ListItemControl(searchFromControl=spotify_window, foundIndex=idx)
                        if not (item and item.Exists(0.2, 0.2)):
                            continue
                        
                        # Get bounding rectangle
                        try:
                            br = item.BoundingRectangle
                            l = br.left if hasattr(br, 'left') else br[0]
                            t = br.top if hasattr(br, 'top') else br[1]
                            r = br.right if hasattr(br, 'right') else br[2]
                            b = br.bottom if hasattr(br, 'bottom') else br[3]
                            w, h = int(r - l), int(b - t)
                        except Exception:
                            continue
                        
                        # Skip if too small
                        if w < 100 or h < 30:
                            continue
                        
                        # Move to center and double-click to play
                        cx = int((l + r) / 2)
                        cy = int((t + b) / 2)
                        print(f"[Spotify] Moving to result at ({cx}, {cy}) and double-clicking...")
                        
                        pyautogui.moveTo(cx, cy, duration=0.2)
                        time.sleep(0.2)
                        pyautogui.doubleClick()
                        time.sleep(0.3)
                        
                        result_played = True
                        print("[Spotify] Clicked on first result!")
                        break
                        
                    except Exception:
                        continue
        except Exception as e:
            print(f"[Spotify] UIA click failed: {e}")
    
    if result_played:
        return {"ok": True, "say": f"Playing '{q}' on Spotify!"}
    
    # Even if clicking failed, we at least searched
    return {"ok": True, "say": f"Searched for '{q}' in Spotify. Please click on the song to play."}


def _parse_play_song_query(phrase: Optional[str]) -> Optional[str]:
    """Extract a song query from a free-form phrase in many languages.

    Heuristics:
    - If the user quoted the song, extract text inside quotes.

    - Remove common "play" verbs and polite phrases in several languages.
    - Trim filler words like 'song', 'music', 'track' in multiple languages.
    - Fallback: return the whole phrase.
    This is intentionally permissive: if parsing fails, the caller can try the original phrase.
    """
    if not phrase:
        return None
    s = str(phrase).strip()
    if not s:
        return None


    # If quoted text present, prefer that
    m = re.search(r'"([^"]{2,})"', s)
    if not m:
        m = re.search(r"'([^']{2,})'", s)
    if m:
        return m.group(1).strip()


    low = s.lower()


    # Patterns that try to explicitly capture the title in many languages
    patterns = [
        # English: play <title> by <artist>
        r"(?i)play(?: me| the song| the)?\s+\"?(?P<title>[^\"]+?)\"?(?:\s+by\s+(?P<artist>.+))?$",
        r"(?i)can you play(?: the)?\s+\"?(?P<title>[^\"]+?)\"?(?:\s+by\s+(?P<artist>.+))?$",
        r"(?i)i want to hear(?: the)?\s+\"?(?P<title>[^\"]+?)\"?(?:\s+by\s+(?P<artist>.+))?$",
        # Spanish
        r"(?i)reproducir(?: la canciÃ³n| la)?\s+\"?(?P<title>[^\"]+?)\"?(?:\s+de\s+(?P<artist>.+))?$",
        r"(?i)pon(?: la canciÃ³n)?\s+\"?(?P<title>[^\"]+?)\"?(?:\s+de\s+(?P<artist>.+))?$",
        # French
        r"(?i)joue(?: moi)?\s+\"?(?P<title>[^\"]+?)\"?(?:\s+de\s+(?P<artist>.+))?$",

        # German
        r"(?i)spiele(?: mir)?\s+\"?(?P<title>[^\"]+?)\"?(?:\s+von\s+(?P<artist>.+))?$",
        # Hindi transliterated
        r"(?i)gaana(?:\s+chalao|\s+chalao|\s+chalao)?\s+\"?(?P<title>[^\"]+?)\"?",
        r"(?i)à¤•à¥ƒà¤ªà¤¯à¤¾.*?\"?(?P<title>[^\"]+?)\"?",
        # Chinese/Japanese/Korean
        r"(?P<title>[\u4e00-\u9fff\w\s]{2,})",
    ]

    for pat in patterns:
        try:
            mm = re.search(pat, s)
            if mm:
                title = mm.groupdict().get('title') or mm.groupdict().get('title1') or mm.groupdict().get('title2')
                if title:
                    title = title.strip()
                    # strip trailing polite words
                    title = re.sub(r"\bplease\b|\bpor favor\b|\bpls\b", '', title, flags=re.IGNORECASE).strip()
                    return title
        except Exception:
            continue

    # Generic cleanup: remove common play verbs and polite phrases
    remove_phrases = [
        r"\bplay\b", r"\bplease\b", r"\bpls\b", r"\bcan you play\b",
        r"\bcould you play\b", r"\bi want to hear\b", r"\bi want to listen to\b",
        r"\bplay the song\b", r"\bplay music\b", r"\bplay song\b",
        r"\bpor favor\b", r"\bporfa\b", r"\bpor favor reproduce la cancion\b",
        r"\bpls play\b", r"\bplease play\b", r"\bplay me\b",
        r"\bà¤•à¥ƒà¤ªà¤¯à¤¾\b", r"\bà¤•à¥ƒà¤ªà¤¯à¤¾ à¤—à¤¾à¤¨à¤¾\b", r"\bæ’­æ”¾\b", r"\bå†ç”Ÿ\b", r"\bìž¬ìƒ\b",
    ]

    cleaned = low
    try:
        for rp in remove_phrases:
            cleaned = re.sub(rp, ' ', cleaned, flags=re.IGNORECASE)
        # remove filler nouns
        cleaned = re.sub(r"\b(song|track|music|the song|la cancion|canciÃ³n|æ›²)\b", ' ', cleaned, flags=re.IGNORECASE)
        # remove polite leading pronouns like 'me', 'moi'
        cleaned = re.sub(r"^\s*(me|moi|por|para|please|pls)\s+", '', cleaned, flags=re.IGNORECASE)
        # remove leftover stop phrases
        cleaned = re.sub(r"\b(play|please|could you|i want|i'd like|want to hear|hear|give me|to)\b", ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[\-\_\:\;\,\?\!\"]", ' ', cleaned)
        cleaned = re.sub(r"\s+", ' ', cleaned).strip()
        if not cleaned:
            return None
        # If cleaned still contains leading verbs like 'to seÃ±orita', remove leading 'to'
        cleaned = re.sub(r"^to\s+", '', cleaned, flags=re.IGNORECASE)
        return cleaned
    except Exception:
        return s


# ============================================================================
# MAIN ACTION DISPATCHER
# ============================================================================


def _format_whatsapp_ai_message(text: str, max_chars: int = 1800) -> str:
    """Normalize AI output so WhatsApp receives clean ASCII-friendly text."""
    if not text:
        return ""
    cleaned = text.replace("\r\n", "\n")
    replacements = {
        "\u2022": "-",
        "\u2013": "-",
        "\u2014": "-",
    }
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)
    cleaned = re.sub(r"\t+", " ", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip() + "..."
    return cleaned


def _send_whatsapp_message_via_clipboard(contact: str, message: str) -> bool:
    """Open WhatsApp chat for contact and send message using granular steps explicitly."""
    if not contact or not message:
        return False
    
    # Delegate to granulized UI helpers for the requested "Open -> Wait -> Search -> Send" flow
    from .ui import (
        whatsapp_launch_and_wait,
        whatsapp_search_and_open_chat,
        whatsapp_paste_and_send
    )
    import time

    # Step 1: Open WhatsApp (Start/Search) & Wait for explicit load
    if not whatsapp_launch_and_wait():
        _ai_log("Failed to launch/verify WhatsApp.")
        return False
        
    # Step 2: Search for specific contact & Open Chat
    # Uses the primary contact name directly to avoid duplication loops.
    # The UI helper handles waiting for search results and clicking.
    if not whatsapp_search_and_open_chat(contact):
        _ai_log(f"Failed to find/open chat for: {contact}")
        return False
            
    # Step 3: Paste & Send
    # Message is already in clipboard from _visual_copy_to_notepad (usually),
    # but the helper ensures it's pasted securely.
    if whatsapp_paste_and_send(message):
        return True
        
    return False


def _ensure_whatsapp_chat(contact: str) -> bool:
    """Bring WhatsApp forward and open the requested chat."""
    if not contact:
        return False
    try:
        # Use the primary UI search mechanism
        if whatsapp_send_message(contact, None):
            return True
    except Exception:
        pass
    return False


def _relative_screen_point(x_ratio: float, y_ratio: float) -> Optional[Tuple[int, int]]:
    try:
        width, height = pyautogui.size()
        x = int(max(0.0, min(1.0, x_ratio)) * float(width))
        y = int(max(0.0, min(1.0, y_ratio)) * float(height))
        return (x, y)
    except Exception:
        return None





def _start_whatsapp_call(contact: str, *, wait_after_chat: float = 1.0) -> bool:
    """Best-effort voice call trigger using UIAutomation first, then keyboard."""
    if not _ensure_whatsapp_chat(contact):
        return False
    time.sleep(max(0.5, wait_after_chat))
    triggered = False

    if HAS_UIAUTOMATION and auto is not None:
        try:
            window = auto.GetForegroundControl()
            if not window or "whatsapp" not in (window.Name or "").lower():
                try:
                    window = auto.WindowControl(searchDepth=1, RegexName=r"(?i)whatsapp")
                    if window and window.Exists(0, 0):
                        window.SetActive()
                        time.sleep(0.3)
                except Exception:
                    window = None
            if window and window.Exists(0, 0):
                label_patterns = [r"(?i)voice\s+call", r"(?i)audio\s+call"]
                for pattern in label_patterns:
                    try:
                        button = auto.ButtonControl(searchFromControl=window, RegexName=pattern)
                    except Exception:
                        button = None
                    if button and button.Exists(0, 0):
                        try:
                            _click_with_cursor(button)
                            triggered = True
                            break
                        except Exception:
                            continue
        except Exception:
            pass

    if not triggered:
        try:
            pyautogui.hotkey('ctrl', 'shift', 'u')
            triggered = True
        except Exception:
            pass

    if triggered:
        time.sleep(1.2)
    return triggered


def _is_whatsapp_control(ctrl) -> bool:
    if not ctrl:
        return False
    try:
        name = (getattr(ctrl, "Name", None) or "").lower()
        class_name = (getattr(ctrl, "ClassName", None) or "").lower()
        return "whatsapp" in (name + class_name)
    except Exception:
        return False


def _locate_whatsapp_window() -> Optional[Any]:  # type: ignore[name-defined]
    if not (HAS_UIAUTOMATION and auto is not None):
        return None
    try:
        current = auto.GetForegroundControl()
        if _is_whatsapp_control(current):
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


def _focus_whatsapp_window(window: Optional[Any] = None, *, timeout: float = 1.0) -> bool:
    """Attempt to bring WhatsApp to foreground for reliable hotkeys/clicks."""
    if window and HAS_UIAUTOMATION and auto is not None:
        try:
            if window.Exists(0, 0):
                window.SetActive()
                time.sleep(0.1)
                return True
        except Exception:
            pass
    return _focus_window_by_keywords(("whatsapp",), timeout=max(0.5, timeout), allow_alt_tab=True)


def _await_whatsapp_call_connection(timeout: float = 18.0, poll: float = 0.6) -> Tuple[bool, Optional[Any]]:
    """Try to detect when a WhatsApp call transitions to 'connected'."""
    timeout = max(2.0, float(timeout))
    poll = max(0.3, float(poll))
    if not (HAS_UIAUTOMATION and auto is not None):
        time.sleep(min(3.0, timeout))
        return False, None

    deadline = time.time() + timeout
    search_depth = 8
    last_window = None

    def _match(window, control_factory, pattern: str) -> bool:
        if not window:
            return False
        try:
            ctrl = control_factory(searchFromControl=window, RegexName=pattern, searchDepth=search_depth)
            return bool(ctrl and ctrl.Exists(0, 0))
        except Exception:
            return False

    while time.time() < deadline:
        window = _locate_whatsapp_window()
        if window:
            last_window = window
        if not window:
            time.sleep(poll)
            continue
        if _match(window, auto.TextControl, r"(?i)call\s+ended|busy|declined|unavailable"):
            return False, window
        if _match(window, auto.TextControl, r"^\d{1,2}:\d{2}$") or _match(window, auto.TextControl, r"^\d{1,2}:\d{2}:\d{2}$"):
            return True, window
        if _match(window, auto.TextControl, r"(?i)connected|on\s+call|call\s+in\s+progress|duration"):
            return True, window
        if _match(window, auto.TextControl, r"(?i)ringing|calling|connecting"):
            time.sleep(poll)
            continue
        time.sleep(poll)
    return False, last_window


def _ensure_whatsapp_microphone_open(window: Optional[Any] = None) -> bool:
    """Best effort: unmute system mic and in-call mic toggle if visible."""
    unmuted = False
    try:
        if set_microphone_mute(False):
            unmuted = True
    except Exception:
        pass
    if not (HAS_UIAUTOMATION and auto is not None):
        return unmuted
    if window is None:
        window = _locate_whatsapp_window()
    if not window:
        return unmuted
    _focus_whatsapp_window(window)
    needs_unmute = False
    try:
        button = auto.ButtonControl(
            searchFromControl=window,
            RegexName=r"(?i)unmute|turn on microphone|mic off",
            searchDepth=6,
        )
    except Exception:
        button = None
    if button and button.Exists(0, 0):
        try:
            _click_with_cursor(button)
            time.sleep(0.25)
            return True
        except Exception:
            pass
        needs_unmute = True
    else:
        try:
            muted_indicator = auto.TextControl(
                searchFromControl=window,
                RegexName=r"(?i)mic off|microphone muted|you're muted|turn on mic",
                searchDepth=6,
            )
            needs_unmute = bool(muted_indicator and muted_indicator.Exists(0, 0))
        except Exception:
            needs_unmute = False
    # Fallback to keyboard shortcut (Ctrl+Shift+M toggles mute in WhatsApp Desktop)
    if needs_unmute:
        try:
            pyautogui.hotkey('ctrl', 'shift', 'm')
            time.sleep(0.2)
            unmuted = True
        except Exception:
            pass
    return unmuted


def _control_center(control: Any) -> Optional[Tuple[int, int]]:
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


def _speak_blocking(text: str, emotion: str = "friendly") -> bool:
    phrase = (text or "").strip()
    if not phrase:
        return False
    try:
        from .tts import speak
    except Exception:
        try:
            from src.assistant.tts import speak  # type: ignore
        except Exception:
            speak = None
    if not speak:
        return False
    try:
        speak(phrase, emotion=emotion)
        return True
    except Exception:
        return False


def _find_whatsapp_voice_button(window: Optional[Any] = None) -> Optional[Any]:
    if not (HAS_UIAUTOMATION and auto is not None):
        return None
    if window is None:
        window = _locate_whatsapp_window()
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


def _find_whatsapp_voice_send_button(window: Optional[Any] = None) -> Optional[Any]:
    if not (HAS_UIAUTOMATION and auto is not None):
        return None
    if window is None:
        window = _locate_whatsapp_window()
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


def _guess_voice_button_point(window: Optional[Any] = None) -> Optional[Tuple[int, int]]:
    if window is None:
        window = _locate_whatsapp_window()
    if window and HAS_UIAUTOMATION and auto is not None:
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


def _click_whatsapp_voice_point(button: Optional[Any], fallback: Optional[Tuple[int, int]]) -> bool:
    if button and HAS_UIAUTOMATION and auto is not None:
        try:
            _click_with_cursor(button)
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


def _whatsapp_recording_indicator_present(window: Any) -> bool:
    if not (HAS_UIAUTOMATION and auto is not None):
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


def _wait_for_whatsapp_voice_recording(window: Optional[Any], timeout: float = 4.0, poll: float = 0.2) -> bool:
    timeout = max(0.5, float(timeout))
    poll = max(0.1, float(poll))
    if not (HAS_UIAUTOMATION and auto is not None):
        time.sleep(min(timeout, 0.4))
        return True
    deadline = time.time() + timeout
    while time.time() < deadline:
        ctrl_window = window
        if not ctrl_window or not ctrl_window.Exists(0, 0):
            ctrl_window = _locate_whatsapp_window()
        if ctrl_window and _whatsapp_recording_indicator_present(ctrl_window):
            return True
        time.sleep(poll)
    return False


def _hold_and_record_whatsapp_voice(
    point: Optional[Tuple[int, int]],
    text: str,
    emotion: str,
    window: Optional[Any],
    delay_before_speaking: float,
) -> bool:
    if not point:
        return False
    try:
        pyautogui.moveTo(point[0], point[1], duration=0.12)
        time.sleep(0.05)
        pyautogui.mouseDown(x=point[0], y=point[1], button='left')
    except Exception:
        return False
    time.sleep(max(0.05, delay_before_speaking))
    spoken = _speak_blocking(text, emotion=emotion)
    try:
        pyautogui.mouseUp(x=point[0], y=point[1], button='left')
    except Exception:
        pass
    if not spoken:
        return False
    time.sleep(0.25)
    send_button = _find_whatsapp_voice_send_button(window)
    if send_button and send_button.Exists(0, 0):
        send_point = _control_center(send_button)
        if not _click_whatsapp_voice_point(send_button, send_point):
            try:
                pyautogui.press('enter')
            except Exception:
                pass
    return True


def _record_and_send_whatsapp_voice_message(contact: str, message: str, emotion: str = "friendly") -> bool:
    text = (message or "").strip()
    if not contact or not text:
        return False
    bot = WhatsAppAdvancedBot()
    if bot._assistant_speak is None:
        try:
            from .tts import speak as assistant_speak_local
        except Exception:
            assistant_speak_local = None
        bot._assistant_speak = assistant_speak_local
    try:
        if bot.complete_automation(contact, text, emotion=emotion):
            return True
    except Exception:
        pass
    finally:
        try:
            bot.close()
        except Exception:
            pass
    return _record_and_send_whatsapp_voice_message_legacy(contact, text, emotion=emotion)


def _record_and_send_whatsapp_voice_message_legacy(contact: str, message: str, emotion: str = "friendly") -> bool:
    """Fallback to the legacy coordinate/UIA workflow when the advanced bot fails."""
    text = (message or "").strip()
    if not contact or not text:
        return False
    if not _ensure_whatsapp_chat(contact):
        return False
    action_start = time.time()
    time.sleep(0.8)
    window = _locate_whatsapp_window()
    _focus_whatsapp_window(window)
    button = _find_whatsapp_voice_button(window)
    start_point = _control_center(button) if button else None
    if not start_point:
        start_point = _guess_voice_button_point(window)
    clicked = _click_whatsapp_voice_point(button, start_point)
    elapsed_before_click = time.time() - action_start
    speak_delay = min(6.0, max(0.05, elapsed_before_click))
    if clicked:
        recording_ready = _wait_for_whatsapp_voice_recording(window)
        if recording_ready:
            time.sleep(speak_delay)
            if not _speak_blocking(text, emotion=emotion):
                return False
            time.sleep(0.15)
            send_button = _find_whatsapp_voice_send_button(window)
            send_point = _control_center(send_button) if send_button else start_point
            if not _click_whatsapp_voice_point(send_button, send_point):
                try:
                    pyautogui.press('enter')
                except Exception:
                    return False
            time.sleep(0.35)
            return True
    hold_point = start_point or _guess_voice_button_point(window)
    return _hold_and_record_whatsapp_voice(hold_point, text, emotion, window, speak_delay)


def _speak_message_over_call(
    message: str,
    *,
    delay: float = 2.5,
    emotion: str = "friendly",
    wait_for_answer: bool = True,
    wait_timeout: float = 18.0,
) -> bool:
    """Speak a message via system speakers so the call recipient hears it."""
    text = (message or "").strip()
    if not text:
        return False
    window: Optional[Any] = None
    if wait_for_answer:
        answered, window = _await_whatsapp_call_connection(timeout=wait_timeout)
        if answered:
            _focus_whatsapp_window(window)
            _ensure_whatsapp_microphone_open(window)
    else:
        answered = False
    if not answered:
        if window is None:
            window = _locate_whatsapp_window()
        _focus_whatsapp_window(window)
        _ensure_whatsapp_microphone_open(window)
        time.sleep(max(0.0, delay))
    if not _speak_blocking(text, emotion=emotion):
        return False
    return True


def _launch_url_in_browser(url: str, preferred: Optional[str] = None) -> Tuple[bool, str]:
    """Attempt to open the given URL in a foreground browser window."""
    def _normalize(tag: str) -> str:
        return (tag or "").strip().lower()

    browser_map: Dict[str, List[str]] = {
        "brave": [
            os.path.join(os.environ.get("PROGRAMFILES", r"C:\\Program Files"), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", r"C:\\Users\\%USERNAME%\\AppData\\Local"), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ],
        "chrome": [
            os.path.join(os.environ.get("PROGRAMFILES", r"C:\\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", r"C:\\Users\\%USERNAME%\\AppData\\Local"), "Google", "Chrome", "Application", "chrome.exe"),
        ],
        "msedge": [
            os.path.join(os.environ.get("PROGRAMFILES", r"C:\\Program Files"), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\\Program Files (x86)"), "Microsoft", "Edge", "Application", "msedge.exe"),
        ],
        "firefox": [
            os.path.join(os.environ.get("PROGRAMFILES", r"C:\\Program Files"), "Mozilla Firefox", "firefox.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\\Program Files (x86)"), "Mozilla Firefox", "firefox.exe"),
        ],
    }

    priority: List[str] = []
    pref = _normalize(preferred)
    if pref in browser_map:
        priority.append(pref)
    for tag in ["brave", "chrome", "msedge", "firefox"]:
        if tag not in priority:
            priority.append(tag)

    for tag in priority:
        for pth in browser_map.get(tag, []):
            if pth and os.path.exists(pth):
                try:
                    subprocess.Popen([pth, url])
                    return True, tag
                except Exception:
                    continue

    try:
        ok = webbrowser.open(url)
        return bool(ok), "webbrowser"
    except Exception:
        return False, "webbrowser"


def _count_red_pixels(region) -> Tuple[int, int, float]:
    """Count reddish pixels in a PIL region and return counts plus ratio."""
    try:
        rgb = region.convert("RGB")
    except Exception:
        return (0, 0, 0.0)
    total = region.width * region.height or 1
    red = 0
    vivid = 0
    for r, g, b in rgb.getdata():
        if r > 165 and g < 130 and b < 140 and (r - max(g, b)) > 35:
            red += 1
            if r > 205 and g < 95 and b < 115:
                vivid += 1
    return red, vivid, red / total


def _analyze_instagram_topbar(image) -> Dict[str, Any]:
    """Inspect the top strip of Instagram for red notification/message badges."""
    width, height = image.size
    top_y1 = max(0, int(height * 0.03))
    top_y2 = min(height, int(height * 0.20))

    bands = {
        "notifications": [(0.54, 0.68), (0.58, 0.72), (0.62, 0.76)],
        "messages": [(0.72, 0.90), (0.75, 0.93), (0.78, 0.96)],
    }

    samples: Dict[str, List[Dict[str, float]]] = {"notifications": [], "messages": []}
    best_metrics: Dict[str, Dict[str, float]] = {}

    for label, ranges in bands.items():
        best = {"pixels": 0, "vivid": 0, "ratio": 0.0, "band": (0.0, 0.0)}
        for start, end in ranges:
            left = max(0, int(width * start))
            right = min(width, int(width * end))
            region = image.crop((left, top_y1, right, top_y2))
            red, vivid, ratio = _count_red_pixels(region)
            samples[label].append({
                "start": round(start, 3),
                "end": round(end, 3),
                "pixels": red,
                "vivid": vivid,
                "ratio": round(ratio, 5),
            })
            if red > best["pixels"] or vivid > best["vivid"]:
                best = {
                    "pixels": red,
                    "vivid": vivid,
                    "ratio": ratio,
                    "band": (round(start, 3), round(end, 3)),
                }
        best_metrics[label] = {
            "pixels": best["pixels"],
            "vivid": best["vivid"],
            "ratio": round(best["ratio"], 5),
            "band_start": best["band"][0],
            "band_end": best["band"][1],
        }

    notif_metrics = best_metrics.get("notifications", {})
    inbox_metrics = best_metrics.get("messages", {})

    has_notif = bool(notif_metrics) and (
        notif_metrics.get("vivid", 0) >= 5 or notif_metrics.get("ratio", 0.0) >= 0.003
    )
    has_inbox = bool(inbox_metrics) and (
        inbox_metrics.get("vivid", 0) >= 5 or inbox_metrics.get("ratio", 0.0) >= 0.003
    )

    return {
        "has_notifications": has_notif,
        "has_messages": has_inbox,
        "notif_metrics": notif_metrics,
        "inbox_metrics": inbox_metrics,
        "samples": samples,
    }


def _ensure_instagram_open() -> Tuple[bool, str]:
    """Open Instagram in Brave (preferred) and fall back to other browsers."""
    launched, method = _launch_url_in_browser("https://www.instagram.com/", preferred="brave")
    if launched and method:
        try:
            _OPENED_APPS.add(f"browser:{method}")
        except Exception:
            pass
    return launched, method or "unknown"


def _instagram_check_notifications(parameters: Dict[str, Any]) -> Dict[str, Any]:
    _notify("Let me take a detailed look at your Instagram notifications.")

    opened, method = _ensure_instagram_open()

    def _fail(message: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        _notify(message)
        metadata.setdefault("timestamp", time.time())
        metadata.setdefault("opened_via", method)
        return {"ok": False, "say": message, "metadata": metadata}

    if not opened:
        return _fail("I couldn't open Instagram to check notifications.", {"error": "launch_failed"})

    start_time = time.time()
    time.sleep(3.5)
    _notify("Keeping the Instagram window in focus.")
    if not _focus_instagram_window():
        return _fail(
            "Instagram opened, but I couldn't keep its window in front.",
            {"error": "focus_failed"},
        )

    current_title = _active_window_title()
    if _title_matches_keywords(current_title, ("instagram", "brave")):
        try:
            pyautogui.hotkey('ctrl', 'l')
            time.sleep(0.25)
            pyautogui.typewrite("https://www.instagram.com/", interval=0.02)
            pyautogui.press('enter')
            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'r')
        except Exception:
            pass

    _notify("Capturing the Instagram header with extra precision.")

    captured_frames: List[Any] = []
    monitor_decision: Optional[NotificationDecision] = None
    monitor_metadata: Dict[str, Any] = {}
    monitor_error: Optional[str] = None

    def _monitor_screenshot_provider() -> Any:
        shot = pyautogui.screenshot()
        captured_frames.append(shot)
        return shot

    try:
        monitor = _get_instagram_monitor()
        monitor_decision = monitor.scan_current_screen(_monitor_screenshot_provider)
        monitor_metadata = monitor.describe_decision(monitor_decision)
        monitor_metadata["engine"] = "advanced_monitor"
    except Exception as exc:
        monitor_error = str(exc)

    legacy_analysis: Optional[Dict[str, Any]] = None
    legacy_frames: List[Any] = []

    def _run_legacy_sampling(reason: str) -> None:
        nonlocal legacy_analysis, legacy_frames
        legacy_frames = []
        for attempt in range(3):
            wait = 2.0 if attempt else 3.0
            time.sleep(wait)
            try:
                shot = pyautogui.screenshot()
            except Exception as legacy_exc:
                legacy_analysis = {
                    "error": "screenshot_failed",
                    "details": str(legacy_exc),
                    "reason": reason,
                }
                return
            legacy_frames.append(shot)
            legacy_analysis = _analyze_instagram_topbar(shot)
            legacy_analysis["reason"] = reason
            if legacy_analysis.get("has_notifications") or legacy_analysis.get("has_messages") or attempt == 2:
                break
        if legacy_analysis is not None:
            legacy_analysis.setdefault("engine", "band_scan")

    low_confidence = False
    if monitor_decision is None:
        _run_legacy_sampling("monitor_unavailable")
    else:
        low_confidence = (
            not monitor_decision.has_notifications
            and not monitor_decision.has_messages
            and monitor_decision.notification_confidence < 0.52
            and monitor_decision.message_confidence < 0.52
        ) or monitor_decision.capture_failures > 0
        if low_confidence:
            _notify("No obvious red badges yet, giving it a manual double-check.")
            _run_legacy_sampling("low_confidence_crosscheck")

    if monitor_decision is None and (legacy_analysis is None or legacy_analysis.get("error")):
        return _fail(
            "Instagram is open, but I couldn't read the screen with enough clarity.",
            {
                "error": "screenshot_failed",
                "monitor_error": monitor_error,
                "latency_seconds": round(time.time() - start_time, 2),
            },
        )

    has_notif = False
    has_messages = False
    notif_conf = 0.0
    message_conf = 0.0

    if monitor_decision is not None:
        has_notif = monitor_decision.has_notifications
        has_messages = monitor_decision.has_messages
        notif_conf = monitor_decision.notification_confidence
        message_conf = monitor_decision.message_confidence

    if legacy_analysis:
        legacy_has_notif = legacy_analysis.get("has_notifications", False)
        legacy_has_messages = legacy_analysis.get("has_messages", False)
        notif_metrics = legacy_analysis.get("notif_metrics", {})
        inbox_metrics = legacy_analysis.get("inbox_metrics", {})
        if legacy_has_notif:
            has_notif = True
            ratio = float(notif_metrics.get("ratio", 0.0))
            vivid = float(notif_metrics.get("vivid", 0.0))
            notif_conf = max(notif_conf, min(0.92, 0.45 + ratio * 160 + vivid * 0.01))
        if legacy_has_messages:
            has_messages = True
            ratio = float(inbox_metrics.get("ratio", 0.0))
            vivid = float(inbox_metrics.get("vivid", 0.0))
            message_conf = max(message_conf, min(0.92, 0.45 + ratio * 160 + vivid * 0.01))
        if not legacy_has_notif and not legacy_has_messages and legacy_analysis.get("error") is None:
            calm_boost = max(notif_conf, message_conf)
            notif_conf = max(notif_conf, min(0.55, calm_boost))
            message_conf = max(message_conf, min(0.55, calm_boost))

    if has_notif and has_messages:
        say = f"Heads up! Instagram shows new notifications and fresh DMs (about {int(max(notif_conf, message_conf) * 100)}% sure)."
    elif has_notif:
        say = f"Yep, you have new Instagram notifications waiting (confidence {int(notif_conf * 100)}%)."
    elif has_messages:
        say = f"You have unread Instagram messages, but no fresh alerts (confidence {int(message_conf * 100)}%)."
    else:
        quiet_conf = max(0.0, min(0.99, 1.0 - max(notif_conf, message_conf)))
        say = f"Instagram looks quiet — no new alerts or messages right now (about {int(quiet_conf * 100)}% sure)."

    metadata: Dict[str, Any] = {
        "opened_via": method,
        "timestamp": time.time(),
        "latency_seconds": round(time.time() - start_time, 2),
        "captured_frames": len(captured_frames),
        "legacy_frames": len(legacy_frames),
        "monitor_error": monitor_error,
        "monitor_low_confidence": low_confidence,
    }

    if monitor_metadata:
        metadata["monitor"] = monitor_metadata
    if legacy_analysis:
        metadata["legacy_scan"] = legacy_analysis

    if monitor_decision is not None:
        metadata.setdefault("attempts", monitor_decision.attempts)
    elif legacy_analysis:
        metadata.setdefault("attempts", legacy_analysis.get("attempts", len(legacy_frames)))

    if has_notif or has_messages:
        _notify("On it — shouting out your Instagram updates!")

    _notify(say)
    return {"ok": True, "say": say, "metadata": metadata}


def _empty_recycle_bin(parameters: Dict[str, Any]) -> Dict[str, Any]:
    _notify("Let me empty the Recycle Bin.")

    start_time = time.time()
    stats_before = _query_recycle_bin_info()
    items_before = stats_before.get("items") if stats_before else None
    bytes_before = stats_before.get("bytes") if stats_before else None

    if items_before == 0:
        say = "Recycle Bin is already squeaky clean."
        metadata = {
            "items_before": items_before,
            "bytes_before": bytes_before,
            "timestamp": time.time(),
            "duration": round(time.time() - start_time, 2),
            "skipped_launch": True,
        }
        _notify(say)
        return {"ok": True, "say": say, "metadata": metadata}

    if not _open_recycle_bin_window():
        say = "Couldn't open the Recycle Bin window."
        metadata = {
            "error": "launch_failed",
            "items_before": items_before,
            "bytes_before": bytes_before,
            "timestamp": time.time(),
        }
        return {"ok": False, "say": say, "metadata": metadata}

    try:
        _OPENED_APPS.add("recycle bin")
    except Exception:
        pass

    time.sleep(2.5)
    focus_ok = _focus_recycle_bin_window(timeout=10.0)
    if not focus_ok:
        say = "Recycle Bin is open, but I couldn't keep it focused to clear it."
        metadata = {
            "error": "focus_failed",
            "items_before": items_before,
            "bytes_before": bytes_before,
            "timestamp": time.time(),
        }
        return {"ok": False, "say": say, "metadata": metadata}

    try:
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.35)
        pyautogui.press('delete')
        time.sleep(0.6)
        pyautogui.press('enter')
        time.sleep(0.35)
        pyautogui.press('enter')
    except Exception as exc:
        say = "Something went wrong while clearing the Recycle Bin."
        metadata = {
            "error": "key_sequence_failed",
            "details": str(exc),
            "items_before": items_before,
            "bytes_before": bytes_before,
            "timestamp": time.time(),
        }
        return {"ok": False, "say": say, "metadata": metadata}

    time.sleep(2.5)
    stats_after = _query_recycle_bin_info()
    items_after = stats_after.get("items") if stats_after else None
    bytes_after = stats_after.get("bytes") if stats_after else None

    success = items_after == 0 if items_after is not None else True

    if success:
        say = "Recycle Bin is empty now."
    else:
        say = "I cleared what I could, but something might still be in the Recycle Bin."

    metadata = {
        "items_before": items_before,
        "bytes_before": bytes_before,
        "items_after": items_after,
        "bytes_after": bytes_after,
        "timestamp": time.time(),
        "duration": round(time.time() - start_time, 2),
        "focus_ok": focus_ok,
    }

    _notify(say)
    return {"ok": success, "say": say, "metadata": metadata}


def _sanitize_contact_token(raw: Optional[str]) -> str:
    token = (raw or "").strip()
    if not token:
        return ""
    token = re.sub(r"(?i)\b(also|too|as\s*well)\b$", "", token).strip()
    token = re.sub(r"(?i)\b(to|ko|ke\s+liye)\b$", "", token).strip(" .,:;-\n")
    token = re.sub(r"(?i)\bko\s+bh[iy]?\b$", "", token).strip(" .,:;-\n")
    return token


def _ai_summary_too_shallow(message: str, topic: str, minimum_words: int = 9) -> bool:
    """Detect if AI output is basically the topic or otherwise too short."""
    if not message:
        return True
    text = re.sub(r"\s+", " ", message).strip().lower()
    topic_norm = re.sub(r"\s+", " ", (topic or "").strip().lower())
    if topic_norm and text in {topic_norm, topic_norm.strip(".:"), topic_norm.rstrip('.') + '.'}:
        return True
    if topic_norm and topic_norm in text and len(text.split()) <= len(topic_norm.split()) + 2:
        return True
    if len(text.split()) < minimum_words and len(text) < 120:
        return True
    return False


def _reinforce_whatsapp_ai_message(message: str,
                                   topic: str,
                                   contacts: List[str],
                                   format_hint: str) -> Tuple[str, bool]:
    """Ensure the AI message references recipients, topic, and a closing."""
    original = (message or "").strip()
    if not original or not contacts:
        return original, False

    raw_lines = original.replace("\r\n", "\n").split("\n")
    lines: List[str] = []
    for raw in raw_lines:
        stripped = raw.strip()
        if stripped:
            lines.append(stripped)
        elif lines and lines[-1] != "":
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()

    modified = False
    bullet_mode = any(line.startswith(("-", "*")) for line in lines)
    first_contact = contacts[0].strip()
    first_name = first_contact.split()[0] if first_contact else "there"

    greeting_pattern = re.compile(r"^(hi|hello|hey)\b", re.IGNORECASE)
    if lines:
        first_line = lines[0]
        if not greeting_pattern.search(first_line):
            lines.insert(0, f"Hi {first_name},")
            modified = True
            if bullet_mode and len(lines) > 1 and lines[1] and not lines[1].startswith(("-", "*", "Hi", "Hello", "Hey")):
                lines.insert(1, "")
    else:
        lines.append(f"Hi {first_name},")
        modified = True

    if len(contacts) > 1:
        others = [c.strip() for c in contacts[1:] if c.strip()]
        if others:
            lower_text = " ".join(line.lower() for line in lines)
            missing = [c for c in others if c.lower() not in lower_text]
            if missing:
                summary_line = f"Looping in {', '.join(missing)} as well."
                insert_idx = 2 if len(lines) >= 2 else len(lines)
                if insert_idx > len(lines):
                    insert_idx = len(lines)
                if insert_idx and lines[insert_idx - 1] != "":
                    lines.insert(insert_idx, "")
                    insert_idx += 1
                lines.insert(insert_idx, summary_line)
                modified = True

    topic_terms = [tok for tok in re.split(r"[^a-z0-9]+", topic.lower()) if len(tok) >= 4]
    if topic_terms:
        normalized_message = " ".join(line.lower() for line in lines if line)
        if not any(term in normalized_message for term in topic_terms):
            addition = f"Key point: {topic.strip()}."
            if bullet_mode or format_hint == "bullets":
                addition = f"- Key point: {topic.strip()}."
                if lines and lines[-1] and not lines[-1].startswith(("-", "*")):
                    lines.append("")
            else:
                if lines and lines[-1] != "":
                    lines.append("")
            lines.append(addition)
            modified = True

    closing_patterns = re.compile(r"(thanks|thank you|regards|let me know|cheers|take care|talk soon)", re.IGNORECASE)
    closing_present = any(closing_patterns.search(line) for line in lines if line)
    if not closing_present:
        closing_line = "Let me know if you need anything else."
        if bullet_mode or format_hint == "bullets":
            closing_line = f"- Let me know if you need anything else."
            if lines and lines[-1] and not lines[-1].startswith(("-", "*")):
                lines.append("")
        else:
            if lines and lines[-1] != "":
                lines.append("")
        lines.append(closing_line)
        modified = True

    while lines and lines[-1] == "":
        lines.pop()

    final = "\n".join(lines).strip()
    if final != original:
        modified = True
    return final, modified


def _collect_contacts_from_parameters(params: Dict[str, Any]) -> List[str]:
    contacts: List[str] = []
    primary = params.get("contact") or params.get("to")
    raw_list = params.get("contacts")
    if isinstance(raw_list, str) and raw_list.strip():
        for part in re.split(r',|and|&', raw_list):
            clean = _sanitize_contact_token(part)
            if clean:
                contacts.append(clean)
    elif isinstance(raw_list, (list, tuple, set)):
        for item in raw_list:
            if isinstance(item, str) and item.strip():
                clean = _sanitize_contact_token(item)
                if clean:
                    contacts.append(clean)
    if primary and isinstance(primary, str) and primary.strip():
        # Split primary contact string if it contains multiple names
        primary_parts = re.split(r',|\band\b|\baur\b|&', primary, flags=re.IGNORECASE)
        for part in reversed(primary_parts): # Reverse to maintain order when inserting at 0
            clean_part = _sanitize_contact_token(part)
            if clean_part:
                contacts.insert(0, clean_part)
    deduped: List[str] = []
    seen = set()
    for c in contacts:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    return deduped


def _visual_copy_to_notepad(text: str) -> bool:
    """Explicitly open Notepad, paste text, and copy it back to clipboard (Visual Step)."""
    if not text:
        return False
    
    from .ui import open_app_via_start, _try_focus_app_window
    import pyautogui as pg
    import pyperclip
    
    _notify("Opening Notepad to prepare your message.")
    
    # 1. Open Notepad via Start (Search)
    try:
        if not open_app_via_start('notepad'):
            # Fallback if start menu fails
            subprocess.Popen(['notepad.exe'])
    except Exception:
        pass
        
    # 2. Wait for Notepad to load
    notepad_ready = False
    for _ in range(10):
        time.sleep(0.5)
        if _try_focus_app_window(['notepad', 'untitled']):
            notepad_ready = True
            break
            
    if not notepad_ready:
        _ai_log("Could not open/focus Notepad.")
        return False
        
    time.sleep(0.5)
    
    # 3. Paste text into Notepad (Visually)
    try:
        # Clear any existing text
        pg.hotkey('ctrl', 'a')
        time.sleep(0.1)
        pg.press('backspace')
        time.sleep(0.1)
        
        # We need to put text in clipboard first to paste it into Notepad
        # (Writing directly to notepad via automation is hard, pasting is reliable)
        pyperclip.copy(text)
        time.sleep(0.1)
        pg.hotkey('ctrl', 'v')
        time.sleep(0.5) # Let user see it
        
    except Exception:
        _ai_log("Error pasting to Notepad")
        return False
        
    _notify("Copying this text for WhatsApp...")
    
    # 4. Select All and Copy (Ensure it's in clipboard for next step)
    try:
        pg.hotkey('ctrl', 'a')
        time.sleep(0.2)
        pg.hotkey('ctrl', 'c')
        time.sleep(0.2)
        return True
    except Exception:
        return False


def _whatsapp_ai_compose_send(parameters: Dict[str, Any]) -> Dict[str, Any]:
    global _AI_NOTEPAD_ACTIVE, _AI_NOTEPAD_LOCK

    topic = (parameters.get("topic") or parameters.get("subject") or "").strip()
    if not topic:
        return {"ok": False, "say": "What should I explain with AI?"}

    contacts = _collect_contacts_from_parameters(parameters)
    if not contacts:
        return {"ok": False, "say": "Who should I send it to?"}

    topic_label = (parameters.get("topic_raw") or topic).strip()
    message_kind = (parameters.get("message_kind") or "").strip()
    length_pref = (parameters.get("length_preference") or "").strip()
    format_hint = (parameters.get("format_hint") or "").strip()
    effective_topic = topic_label or topic

    first_contact = contacts[0]
    other_contacts = contacts[1:]

    instructions: List[str] = []
    if message_kind and message_kind.lower() not in topic.lower():
        instructions.append(f"focus on {message_kind}")
    if length_pref == "short":
        instructions.append("keep it short for WhatsApp")
    elif length_pref == "detailed":
        instructions.append("add a quick practical detail")
    if format_hint == "bullets":
        instructions.append("use short bullet points after a brief greeting")
    instructions.append("start with a warm greeting that directly addresses the main recipient")
    if other_contacts:
        instructions.append("mention that the note also covers additional recipients")
    instructions.append("close with a friendly invitation to respond")

    if not _AI_NOTEPAD_LOCK.acquire(blocking=False):
        return {"ok": False, "say": "Still finishing the previous notes — give me a moment."}
    _AI_NOTEPAD_ACTIVE = True

    metadata: Dict[str, Any] = {}
    workflow_result: Optional[WorkflowResult] = None
    workflow_error: Optional[str] = None
    message_text = ""
    used_fallback = False
    fallback_source: Optional[str] = None

    try:
        _notify(f"I'll prep a WhatsApp message on '{topic_label}' with AI.")

        workflow_topic = topic
        prompt_suffix: List[str] = []
        prompt_suffix.append(f"WhatsApp message about {effective_topic}.")
        if instructions:
            prompt_suffix.append("Requirements: " + "; ".join(instructions) + ".")
        prompt_suffix.append("Tone: friendly and helpful.")
        prompt_suffix.append("STRICT: Output EXACTLY the message body only. Do NOT include 'Here is the message', headers, or any conversational text.")
        workflow_topic = " ".join([workflow_topic] + prompt_suffix)
        reinforcement_applied = False

        try:
            workflow = _get_ai_notepad_workflow()
            workflow_result = workflow.run(workflow_topic)
        except (BrowserOpenError, PromptSubmissionError, ResponseCollectionError, NotepadAutomationError) as exc:
            workflow_error = str(exc)
            _ai_log(f"WhatsApp AI compose workflow error: {exc}")
        except Exception as exc:
            workflow_error = str(exc)
            _ai_log(f"WhatsApp AI compose unexpected error: {exc}")

        if workflow_result and workflow_result.cleaned_text.strip():
            message_text = _format_whatsapp_ai_message(workflow_result.cleaned_text)
            message_text, reinforced = _reinforce_whatsapp_ai_message(message_text, effective_topic, contacts, format_hint)
            if reinforced:
                reinforcement_applied = True
            message_text = _format_whatsapp_ai_message(message_text)
            
            # EXPLICIT STEP: VISUAL COPY TO NOTEPAD
            # This ensures the user sees the text in Notepad before it goes to WhatsApp
            _visual_copy_to_notepad(message_text)
            
            metadata = dict(workflow_result.metadata)
            metadata["quality_status"] = workflow_result.quality.status.name
            metadata["workflow_ok"] = workflow_result.ok
            metadata["ai_source"] = "ai_notepad_workflow"
        elif workflow_result and workflow_result.metadata:
            metadata = dict(workflow_result.metadata)

        if _ai_summary_too_shallow(message_text, effective_topic):
            try:
                preferred_browser = None
                try:
                    preferred_browser = _get_ai_notepad_workflow().config.preferred_browser
                except Exception:
                    preferred_browser = None
                fallback_prompt = (
                    f"Draft a WhatsApp message about {effective_topic}. "
                    "Keep it friendly, focused, and ready to paste. "
                    "STRICT: Output ONLY the message text. No intro/outro."
                )
                if other_contacts:
                    fallback_prompt += " Make it clear that the note is meant for multiple recipients."
                if message_kind:
                    fallback_prompt += f" Highlight the {message_kind}."
                if length_pref == "short":
                    fallback_prompt += " Stay under about 90 words."
                elif length_pref == "detailed":
                    fallback_prompt += " Include one practical detail or example."
                if format_hint == "bullets":
                    fallback_prompt += " Start with a greeting, then use short bullet points."
                if instructions:
                    fallback_prompt += " Requirements: " + "; ".join(instructions) + "."

                fallback_raw = _chatgpt_submit_prompt_and_copy(
                    fallback_prompt,
                    preferred_browser=preferred_browser,
                )
                if fallback_raw:
                    formatted = _format_whatsapp_ai_message(fallback_raw)
                    formatted, reinforced = _reinforce_whatsapp_ai_message(formatted, effective_topic, contacts, format_hint)
                    if reinforced:
                        reinforcement_applied = True
                    formatted = _format_whatsapp_ai_message(formatted)
                    if formatted and not _ai_summary_too_shallow(formatted, effective_topic):
                        message_text = formatted
                        used_fallback = True
                        fallback_source = "chatgpt_direct"
            except Exception as exc:
                _ai_log(f"Fallback ChatGPT prompt failed: {exc}")

        if not message_text:
            if workflow_error:
                _notify("Workflow hit a snag while preparing the WhatsApp draft.")
                err_meta = {"workflow_error": workflow_error, "topic": topic_label}
                err_meta.update(metadata)
                return {
                    "ok": False,
                    "say": "Couldn't prepare the WhatsApp draft right now.",
                    "metadata": err_meta,
                }
            err_meta = {"topic": topic_label, "error": "no_text"}
            err_meta.update(metadata)
            return {
                "ok": False,
                "say": "Workflow ended but no WhatsApp text was produced.",
                "metadata": err_meta,
            }

        if _ai_summary_too_shallow(message_text, effective_topic):
            shallow_meta = {"topic": topic_label, "error": "summary_too_short"}
            shallow_meta.update(metadata)
            return {
                "ok": False,
                "say": "AI reply was too short to send. Try rephrasing the request.",
                "metadata": shallow_meta,
            }

        metadata.setdefault("topic", topic_label)
        metadata["contacts"] = contacts
        metadata["message_chars"] = len(message_text)
        if message_kind:
            metadata["message_kind"] = message_kind
        if length_pref:
            metadata["length_preference"] = length_pref
        if format_hint:
            metadata["format_hint"] = format_hint
        if used_fallback and fallback_source:
            metadata["ai_fallback"] = fallback_source
        if reinforcement_applied:
            metadata["message_reinforced"] = True
        if instructions:
            metadata["instruction_hints"] = instructions
        preview_source = message_text.splitlines() or [message_text]
        metadata["message_preview"] = (preview_source[0] if preview_source else message_text)[:140]

        success_count = 0
        for name in contacts:
            _notify(f"Sending the AI summary to {name} on WhatsApp.")
            if _send_whatsapp_message_via_clipboard(name, message_text):
                success_count += 1

        if success_count:
            try:
                import pyperclip

                pyperclip.copy(message_text)
            except Exception:
                pass

        if success_count == len(contacts):
            say = f"Sent AI notes to {success_count} contact{'s' if success_count != 1 else ''}."
        elif success_count > 0:
            say = f"Sent to {success_count} contact{'s' if success_count != 1 else ''}, but some failed."
        else:
            say = "Message ready, but WhatsApp send did not succeed."
        return {"ok": success_count > 0, "say": say, "metadata": metadata}
    finally:
        _AI_NOTEPAD_ACTIVE = False
        try:
            _AI_NOTEPAD_LOCK.release()
        except Exception:
            pass


def _normalize_contact_candidates(raw: Optional[str]) -> List[str]:
    """Return a list of likely contact name variants for fuzzy matching in UI flows.


    The first item is the original normalized string. After that we include common
    corrections and aliases (mom/mummy/mama/etc.) to handle misspellings like
    'muumy' or 'mumy'. This is intentionally small and deterministic.
    """
    if not raw:
        return []
    cleaned = _sanitize_contact_token(str(raw))
    s = cleaned if cleaned else str(raw).strip()
    if not s:
        return []

    norm = re.sub(r"[^\w\s]", "", s).strip()
    if not norm:
        return [s]

    low = norm.lower()
    candidates = [norm]


    # Common family name aliases
    aliases = {
        'mom': ['mom', 'mama', 'mum', 'mummy', 'mommy', 'ma'],
        'dad': ['dad', 'daddy', 'papa', 'father'],
        'wife': ['wife', 'wifey', 'spouse'],
        'husband': ['husband', 'hubby', 'spouse'],
    }

    # If the string is short or looks like a family relation, expand
    for key, vals in aliases.items():
        if low == key or low in vals or any(low.startswith(v) for v in vals):
            for v in vals:
                if v not in candidates:

                    candidates.append(v)
            break

    # If user typed something close to 'mummy' etc. (typos), add likely matches
    typo_map = {
        'mumy': 'mummy',
        'muumy': 'mummy',
        'momi': 'mom',

        'mami': 'mama',
    }
    for k, v in typo_map.items():
        if low == k:
            if v not in candidates:
                candidates.append(v)
            # also add generic 'mom'
            if 'mom' not in candidates:
                candidates.append('mom')

    # If the contact contains spaces (first last), also try just first name
    parts = [p for p in low.split() if p]
    if len(parts) > 1:
        first = parts[0]
        if first not in candidates:

            candidates.append(first)

    # If none of the above produced family aliases and the normalized is short,
    # add a few fallbacks to improve chance of match
    if len(candidates) == 1 and len(low) <= 6:

        # common short fallbacks
        for v in ['mom', 'dad', 'wife', 'husband']:
            if v not in candidates:
                candidates.append(v)

    # Keep original capitalization variants (some UI searches are case-sensitive in display)

    final = []
    for c in candidates:

        if c not in final:
            final.append(c)
            # title-case variant

            tc = c.title()

            if tc not in final:
                final.append(tc)

    return final


def execute_action(action: Dict[str, Any]) -> Dict[str, Any]:

    atype = (action.get("type") or "").lower()
    params = action.get("parameters") or {}

    # Handle Delayed/Scheduled NLU Commands (Memory Planning)
    if atype in {"general_command", "nlu_pipeline", "run_command"}:
        cmd = params.get("command") or params.get("text")
        if not cmd:
             return {"ok": False, "say": "No command to execute."}
        
        _notify(f"Executing scheduled command: {cmd}")
        # Local import to avoid circular dependency
        try:
            from src.assistant.nlu import interpret
            plan = interpret(cmd)
            actions = plan.get("actions") or []
            
            if not actions:
                 return {"ok": False, "say": f"I couldn't understand the scheduled command: {cmd}"}
                 
            results = []
            for sub_action in actions:
                 # Recursive execution
                 res = execute_action(sub_action)
                 results.append(res)
            
            return {"ok": True, "say": f"Finished executing: {cmd}", "results": results}
        except Exception as e:
            return {"ok": False, "say": f"Failed to execute command '{cmd}': {e}"}

    if atype == "reminder":
        text = params.get("text") or "No details provided"
        _notify(f"Reminder: {text}")
        return {"ok": True, "say": f"Reminder: {text}"}

    if atype == "task_add":
        resp = productivity_add_task(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype == "task_list":
        resp = productivity_list_tasks(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"task_complete", "task_done"}:
        resp = productivity_complete_task(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype == "task_clear_completed":
        resp = productivity_clear_tasks(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"quick_note", "note_capture"}:
        resp = productivity_capture_note(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"focus_start", "focus_session_start"}:
        resp = productivity_focus_start(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"focus_stop", "focus_session_stop"}:
        resp = productivity_focus_stop(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"focus_status", "focus_session_status"}:
        resp = productivity_focus_status(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype == "daily_briefing":
        resp = productivity_daily_briefing(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"cleanup_temp", "cleanup_junk", "cleanup_files"}:
        resp = cleanup_temp_dirs()
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"habit_create", "habit_add", "habit_update"}:
        resp = habit_create_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"habit_log", "habit_checkin", "habit_track"}:
        resp = habit_log_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"habit_status", "habit_report", "habit_summary"}:
        resp = habit_status_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"habit_reset", "habit_clear"}:
        resp = habit_reset_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"routine_create", "routine_save"}:
        resp = routine_create_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"routine_list", "routine_overview"}:
        resp = routine_list_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"routine_delete", "routine_remove"}:
        resp = routine_delete_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"routine_run", "routine_start"}:
        resp = routine_run_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"system_health", "health_check", "diagnostics"}:
        resp = system_health_report_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"system_health_watch", "health_watch"}:
        resp = system_health_watch_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"clipboard_save", "snippet_save"}:
        resp = clipboard_save_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"clipboard_list", "snippet_list"}:
        resp = clipboard_list_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"clipboard_search", "snippet_search"}:
        resp = clipboard_search_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    if atype in {"clipboard_restore", "snippet_restore"}:
        resp = clipboard_restore_action(params)
        if resp.get("say"):
            _notify(resp["say"])
        return resp

    # =========================================================================
    # NEW ENHANCED MODULES - Spotify, WhatsApp Multi, Scheduler, Multi-Task
    # =========================================================================

    # Multi-task compound command execution
    if atype == "multi_task" and HAS_MULTI_TASK and _execute_multi_task:
        try:
            actions_list = params.get("actions") or []
            if actions_list:
                _notify(f"Executing {len(actions_list)} tasks in sequence...")
                # Pass the full action dict AND the execute_action function as executor
                resp = _execute_multi_task(action, executor=execute_action)
                if resp.get("say"):
                    _notify(resp["say"])
                return resp
        except Exception as exc:
            return {"ok": False, "say": f"Multi-task execution failed: {exc}"}

    # Enhanced Spotify controls
    if atype.startswith("spotify_") and HAS_SPOTIFY_CONTROLLER and _execute_spotify_action:
        try:
            resp = _execute_spotify_action({"type": atype, "parameters": params})
            if resp.get("say"):
                _notify(resp["say"])
            return resp
        except Exception as exc:
            return {"ok": False, "say": f"Spotify control failed: {exc}"}

    # Additional Spotify aliases for common commands
    if atype in {"stop_music", "stop_song", "pause_music", "pause_song"}:
        # Try spotify controller first
        if HAS_SPOTIFY_CONTROLLER and _execute_spotify_action:
            try:
                resp = _execute_spotify_action({"type": "spotify_pause", "parameters": params})
                if resp.get("say"):
                    _notify(resp["say"])
                return resp
            except Exception:
                pass
        # Fallback to media key
        try:
            pyautogui.press("playpause")
            time.sleep(0.2)
            resp = {"ok": True, "say": "Paused playback."}
            _notify(resp["say"])
            return resp
        except Exception as exc:
            return {"ok": False, "say": f"Couldn't pause playback: {exc}"}

    if atype in {"next_song", "skip_song", "next_track", "skip_track"}:
        # Try spotify controller first
        if HAS_SPOTIFY_CONTROLLER and _execute_spotify_action:
            try:
                resp = _execute_spotify_action({"type": "spotify_next", "parameters": params})
                if resp.get("say"):
                    _notify(resp["say"])
                return resp
            except Exception:
                pass
        # Fallback to media key
        try:
            pyautogui.press("nexttrack")
            time.sleep(0.2)
            resp = {"ok": True, "say": "Skipped to next track."}
            _notify(resp["say"])
            return resp
        except Exception as exc:
            return {"ok": False, "say": f"Couldn't skip track: {exc}"}

    if atype in {"previous_song", "prev_song", "previous_track", "prev_track"}:
        # Try spotify controller first
        if HAS_SPOTIFY_CONTROLLER and _execute_spotify_action:
            try:
                resp = _execute_spotify_action({"type": "spotify_previous", "parameters": params})
                if resp.get("say"):
                    _notify(resp["say"])
                return resp
            except Exception:
                pass
        # Fallback to media key
        try:
            pyautogui.press("prevtrack")
            time.sleep(0.2)
            resp = {"ok": True, "say": "Previous track."}
            _notify(resp["say"])
            return resp
        except Exception as exc:
            return {"ok": False, "say": f"Couldn't go to previous track: {exc}"}

    if atype in {"resume_music", "resume_song", "play_music_resume"} and HAS_SPOTIFY_CONTROLLER:
        try:
            resp = _execute_spotify_action({"type": "spotify_play", "parameters": params})
            if resp.get("say"):
                _notify(resp["say"])
            return resp
        except Exception as exc:
            return {"ok": False, "say": f"Couldn't resume playback: {exc}"}

    # Enhanced WhatsApp multi-recipient messaging - USE ORIGINAL UI FLOW
    if atype in {"whatsapp_send_multi", "whatsapp_multi", "whatsapp_batch"}:
        # Use original ui.py functions for proper WhatsApp flow:
        # 1. Open WhatsApp via Start menu
        # 2. Search contact via UI search bar  
        # 3. Type and send message
        from .ui import (
            whatsapp_launch_and_wait,
            whatsapp_search_and_open_chat,
            whatsapp_paste_and_send
        )
        
        message = params.get("message") or params.get("text") or ""
        contacts = params.get("contacts") or []
        if isinstance(contacts, str):
            contacts = [c.strip() for c in contacts.split(",") if c.strip()]
        
        # Also check for single contact
        single_contact = params.get("contact") or params.get("to")
        if single_contact and single_contact not in contacts:
            contacts.insert(0, single_contact)
        
        if not contacts:
            return {"ok": False, "say": "Who should I send the message to?"}
        if not message:
            return {"ok": False, "say": "What message should I send?"}
        
        _notify(f"Opening WhatsApp to send message to {len(contacts)} contact(s).")
        
        # Step 1: Launch WhatsApp and wait for it to be ready
        if not whatsapp_launch_and_wait():
            return {"ok": False, "say": "Couldn't open WhatsApp. Please open it manually."}
        
        success_count = 0
        for contact in contacts:
            _notify(f"Searching for {contact}...")
            
            # Step 2: Search and open chat
            if whatsapp_search_and_open_chat(contact):
                # Step 3: Paste message and send
                if whatsapp_paste_and_send(message):
                    success_count += 1
                    _notify(f"Message sent to {contact}.")
                else:
                    _notify(f"Couldn't send message to {contact}.")
            else:
                _notify(f"Couldn't find {contact} in WhatsApp.")
            
            time.sleep(0.5)  # Brief pause between contacts
        
        if success_count == len(contacts):
            say = f"Sent message to {success_count} contact(s)."
        elif success_count > 0:
            say = f"Sent to {success_count} of {len(contacts)} contacts."
        else:
            say = "Couldn't send message to any contacts."
        
        return {"ok": success_count > 0, "say": say}

    # Scheduled task actions
    if atype in {"scheduled_task_add", "schedule_message", "schedule_task"} and HAS_TASK_SCHEDULER:
        try:
            resp = _execute_scheduler_action({"type": "scheduled_task_add", "parameters": params})
            if resp.get("say"):
                _notify(resp["say"])
            return resp
        except Exception as exc:
            return {"ok": False, "say": f"Couldn't schedule task: {exc}"}

    if atype in {"scheduled_task_list", "list_scheduled", "show_scheduled"} and HAS_TASK_SCHEDULER:
        try:
            resp = _execute_scheduler_action({"type": "scheduled_task_list", "parameters": params})
            if resp.get("say"):
                _notify(resp["say"])
            return resp
        except Exception as exc:
            return {"ok": False, "say": f"Couldn't list scheduled tasks: {exc}"}

    if atype in {"scheduled_task_cancel", "cancel_scheduled", "remove_scheduled"} and HAS_TASK_SCHEDULER:
        try:
            resp = _execute_scheduler_action({"type": "scheduled_task_cancel", "parameters": params})
            if resp.get("say"):
                _notify(resp["say"])
            return resp
        except Exception as exc:
            return {"ok": False, "say": f"Couldn't cancel scheduled task: {exc}"}

    if atype in {"scheduled_task_status", "scheduler_status"} and HAS_TASK_SCHEDULER:
        try:
            resp = _execute_scheduler_action({"type": "scheduled_task_status", "parameters": params})
            if resp.get("say"):
                _notify(resp["say"])
            return resp
        except Exception as exc:
            return {"ok": False, "say": f"Couldn't get scheduler status: {exc}"}

    # =========================================================================
    # END NEW ENHANCED MODULES
    # =========================================================================

    if atype == "whatsapp_paste_send":
        contact = params.get("contact") or params.get("to")
        _notify(f"I'll open WhatsApp and paste from clipboard to {contact}.")
        try:
            import pyperclip
            clipboard_text = pyperclip.paste()
        except Exception:
            clipboard_text = ""

        if 'whatsapp' not in _OPENED_APPS:
            ok_open = open_app_via_start('whatsapp')
            try:
                if ok_open:
                    _OPENED_APPS.add('whatsapp')
            except Exception:
                pass
        time.sleep(1.2)
        ok = whatsapp_send_message(contact, None)
        time.sleep(0.35)
        try:
            pyautogui.hotkey('ctrl', 'v')
        except Exception:
            try:
                pyautogui.hotkey('shift', 'insert')
            except Exception:
                pass

        paste_delay = 0.12
        try:
            from PIL import ImageGrab
            try:
                img = ImageGrab.grabclipboard()
                if img is not None:
                    paste_delay = 1.0
            except Exception:
                pass
        except Exception:
            pass

        time.sleep(paste_delay)
        try:
            pyautogui.press('enter')
        except Exception:
            pass
        time.sleep(0.35)
        resp = {"ok": True, "say": "Clipboard pasted and sent."}
        _notify(resp["say"])
        return resp

    if atype in {"whatsapp_call", "whatsapp_voice_call"}:
        contact = params.get("contact") or params.get("to") or params.get("name")
        if not contact:
            resp = {"ok": False, "say": "Who should I call on WhatsApp?"}
            _notify(resp["say"])
            return resp
        ok = _start_whatsapp_call(contact)
        say = f"Calling {contact} on WhatsApp." if ok else f"Couldn't start a call with {contact}."
        resp = {"ok": bool(ok), "say": say}
        _notify(resp["say"])
        return resp

    if atype in {"whatsapp_call_tell", "whatsapp_call_and_tell", "whatsapp_call_say"}:
        contact = params.get("contact") or params.get("to") or params.get("name")
        message = params.get("message") or params.get("text") or params.get("note")
        delay = params.get("delay") or params.get("delay_seconds")
        wait_for_answer = params.get("wait_for_answer")
        wait_timeout = params.get("wait_timeout") or params.get("wait_for_answer_seconds")
        if not contact:
            resp = {"ok": False, "say": "Who should I call?"}
            _notify(resp["say"])
            return resp
        if not message:
            resp = {"ok": False, "say": "What should I say on the call?"}
            _notify(resp["say"])
            return resp
        ok = _start_whatsapp_call(contact)
        if not ok:
            resp = {"ok": False, "say": f"Couldn't start a call with {contact}."}
            _notify(resp["say"])
            return resp
        try:
            delay_seconds = float(delay) if delay is not None else 2.5
        except (TypeError, ValueError):
            delay_seconds = 2.5
        try:
            timeout_seconds = float(wait_timeout) if wait_timeout is not None else 18.0
        except (TypeError, ValueError):
            timeout_seconds = 18.0
        wait_flag = wait_for_answer
        if isinstance(wait_flag, str):
            wait_flag_norm = wait_flag.strip().lower()
            wait_flag_bool = wait_flag_norm not in {"0", "false", "no", "off"}
        elif wait_flag is None:
            wait_flag_bool = True
        else:
            wait_flag_bool = bool(wait_flag)
        spoken = _speak_message_over_call(
            message,
            delay=max(0.0, delay_seconds),
            wait_for_answer=wait_flag_bool,
            wait_timeout=max(3.0, timeout_seconds),
        )
        say = f"Told {contact}: {message}" if spoken else f"Call placed to {contact}, but I couldn't speak the message."
        resp = {"ok": spoken, "say": say}
        _notify(resp["say"])
        return resp

    if atype in {"whatsapp_voice_message", "whatsapp_voice_note", "whatsapp_voice_record"}:
        contact = params.get("contact") or params.get("to") or params.get("name")
        message = params.get("message") or params.get("text") or params.get("note")
        emotion = params.get("emotion") or "friendly"
        if not contact:
            resp = {"ok": False, "say": "Who should I send a voice note to?"}
            _notify(resp["say"])
            return resp
        if not message:
            resp = {"ok": False, "say": "What should I say in the voice message?"}
            _notify(resp["say"])
            return resp
        ok = _record_and_send_whatsapp_voice_message(contact, message, emotion=str(emotion))
        say = f"Sent a voice note to {contact}." if ok else f"Couldn't record a voice message for {contact}."
        resp = {"ok": bool(ok), "say": say}
        _notify(resp["say"])
        return resp
    
    if atype == "open" or atype == "url":
        return _open(params)
    
    if atype == "open_app_start":
        name = params.get("name") or params.get("app") or params.get("target")
        if not name:
            return {"ok": False, "say": "Which app should I open?"}
        ok = open_app_via_start(name)
        try:
            if ok:
                _OPENED_APPS.add(str(name).lower())
        except Exception:
            pass
        return {"ok": bool(ok), "say": (f"Opening {name}." if ok else f"Couldn't open {name}.")}
    
    if atype == "type":
        return _type(params)
    
    if atype == "hotkey":


        
        return _hotkey(params)
    if atype == "hotkey_loop":
        return _hotkey_loop(params)
        _notify(f"I'll turn Wi-Fi {state}.")
        if toggle_quick_action and toggle_quick_action('wifi', desired):
            resp = {"ok": True, "say": f"Wiâ€‘Fi {'on' if desired else 'off' if desired is not None else 'toggled'}."}
            _notify(resp["say"])
            return resp
        resp = {"ok": False, "say": "Couldn't control Wiâ€‘Fi."}
        _notify(resp["say"])
        return resp
        return _settings(params)
    
    if atype == "screen_describe":
        return _screen_describe(params)
    
    if atype == "search":
        return _search(params)
    
    if atype == "click_first_link":
        ok = click_first_hyperlink_in_foreground()
        if ok:
            resp = {"ok": True, "say": "Clicked the first link."}
            _notify(resp["say"])
            return resp
        else:
            resp = {"ok": False, "say": "Couldn't find a link to click."}
            _notify(resp["say"])
            return resp
    
    if atype == "power":
        mode = (params.get("mode") or "").lower()
        if not mode:
            return {"ok": False, "say": "Power mode? (shutdown/restart/sleep/hibernate)"}
        _notify(f"Okay, I'll {mode} the system now — energizing my imaginary server muscles.")
        try:
            # Use system_shutdown wrapper if available (it supports restart/shutdown/etc.)
            if system_shutdown:
                ok = system_shutdown(mode)
            else:
                ok = True
        except Exception:
            ok = False
        if ok:
            resp = {"ok": True, "say": f"{mode.capitalize()} initiated."}
            _notify(resp["say"])
            return resp
        else:
            resp = {"ok": False, "say": f"Couldn't {mode} the system."}
            _notify(resp["say"])
            return resp
    if atype == "brightness":
        level = params.get("level")
        if level is None:
            resp = {"ok": False, "say": "Brightness level?"}
            _notify(resp["say"])
            return resp
        try:
            _notify(f"Setting brightness to {level}% — let me nudge the photons.")
        except Exception:
            pass
        if (set_quick_slider and set_quick_slider('brightness', percent=int(level))) or (set_display_brightness and set_display_brightness(level)):
            resp = {"ok": True, "say": f"Setting brightness to {level}%"}
            _notify(resp["say"])
            return resp
        resp = {"ok": False, "say": "Couldn't change brightness."}
        _notify(resp["say"])
        return resp
    
    if atype == "wifi":
        state = params.get("state")
        if state not in {"on", "off", "toggle"}:
            resp = {"ok": False, "say": "Should I turn Wi-Fi on or off?"}
            _notify(resp["say"])
            return resp
        desired = None if state == "toggle" else (state == "on")
        try:
            verb = 'on' if desired else ('off' if desired is not None else 'toggle')
            _notify(f"Flipping Wi-Fi {verb} — securing the airwaves.")
        except Exception:
            pass
        if toggle_quick_action and toggle_quick_action('wifi', desired):
            resp = {"ok": True, "say": f"Wi-Fi {'on' if desired else 'off' if desired is not None else 'toggled'}."}
            _notify(resp["say"])
            return resp
        resp = {"ok": False, "say": "Couldn't control Wi-Fi."}
        _notify(resp["say"])
        return resp
    
    if atype == "bluetooth":
        state = params.get("state")
        if state not in {"on", "off", "toggle"}:
            resp = {"ok": False, "say": "Should I turn Bluetooth on or off?"}
            _notify(resp["say"])
            return resp
        desired = None if state == "toggle" else (state == "on")
        try:
            verb = 'on' if desired else ('off' if desired is not None else 'toggle')
            _notify(f"Switching Bluetooth {verb} — preparing for device bonding rituals.")
        except Exception:
            pass
        if (toggle_quick_action and toggle_quick_action('bluetooth', desired)) or (toggle_in_settings_page and toggle_in_settings_page('bluetooth', desired)):
            resp = {"ok": True, "say": f"Bluetooth {'on' if desired else 'off' if desired is not None else 'toggled'}."}
            _notify(resp["say"])
            return resp
        resp = {"ok": False, "say": "Couldn't control Bluetooth."}
        _notify(resp["say"])
        return resp
    
    if atype == "volume":
        percent = params.get("percent")
        delta = params.get("delta")
        mute = params.get("mute")
        target_percent: Optional[int] = None
        if percent is not None:
            try:
                target_percent = max(0, min(100, int(percent)))
            except Exception:
                target_percent = None
        elif delta is not None:
            current = get_volume_percent() if get_volume_percent else None
            if current is not None:
                try:
                    target_percent = max(0, min(100, current + int(delta)))
                except Exception:
                    target_percent = None
        slider_ok = False
        api_ok = False
        if target_percent is not None:
            api_ok = set_volume(percent=target_percent) if set_volume else False
            if (not api_ok) and os.environ.get("ASSISTANT_VISUAL_VOLUME", "0") == "1":
                slider_ok = set_quick_slider('volume', target_percent) if set_quick_slider else False

        mute_ok = False
        if mute is not None:
            mute_ok = set_volume(mute=mute) if set_volume else False

        if api_ok or slider_ok or mute_ok:
            say = ""
            if mute is True:
                say = "Muting volume."
            elif mute is False:
                say = "Unmuting volume."
            elif target_percent is not None:
                say = f"Setting volume to {target_percent}%."
            elif delta is not None:
                say = "Adjusting volume."
            resp = {"ok": True, "say": say}
            _notify(resp["say"])
            return resp

        if percent is not None:
            if (set_volume and set_volume(percent=percent)) or (set_volume_percent_via_steps and set_volume_percent_via_steps(int(percent))):
                resp = {"ok": True, "say": f"Setting volume to {percent}%."}
                _notify(resp["say"])
                return resp
        if delta is not None:
            if (set_volume and set_volume(delta=delta)) or (nudge_volume_steps and nudge_volume_steps(int(delta) // 2 or (1 if int(delta) > 0 else -1))):
                resp = {"ok": True, "say": "Adjusting volume."}
                _notify(resp["say"])
                return resp
        if mute is not None and set_volume and set_volume(mute=mute):
            resp = {"ok": True, "say": "Muting volume." if mute else "Unmuting volume."}
            _notify(resp["say"])
            return resp
        return {"ok": False, "say": "Couldn't change volume."}
    
    if atype == "mic_mute":
        mute = params.get("mute")
        if mute is None:
            return {"ok": False, "say": "Should I mute the mic?"}
        _notify(f"I'll {'mute' if mute else 'unmute'} the microphone.")
        if set_microphone_mute and set_microphone_mute(mute):
            resp = {"ok": True, "say": "Microphone muted." if mute else "Microphone unmuted."}
            _notify(resp["say"])
            return resp
        resp = {"ok": False, "say": "Couldn't change microphone state."}
        _notify(resp["say"])
        return resp
    
    if atype == "qs_toggle":
        name = params.get("name")
        state = params.get("state")
        if not name:
            resp = {"ok": False, "say": "Which quick setting?"}
            _notify(resp["say"])
            return resp
        desired = None if state == "toggle" else (state == "on")
        if (quick_toggle and quick_toggle(name, desired)) or (name.lower().strip() in {"location"} and toggle_in_settings_page and toggle_in_settings_page('location', desired)):
            label = state if state else 'toggle'
            resp = {"ok": True, "say": f"{name} {label}."}
            _notify(resp["say"])
            return resp
        resp = {"ok": False, "say": f"Couldn't control {name}."}
        _notify(resp["say"])
        return resp
    
    if atype == "uninstall" or atype == "uninstall_app":
        return _uninstall(params)
    
    if atype == "close_app":
        name = params.get("name")
        ok = close_app(name) if close_app else False
        resp = {"ok": bool(ok), "say": (f"Closed {name}." if ok and name else "Closed.")}
        _notify(resp["say"])
        return resp
    
    def _parse_whatsapp_natural(phrase: Optional[str]) -> Dict[str, Any]:
        """Simple natural-language parser for WhatsApp send phrases.

        Returns {'ok': bool, 'message': str, 'contacts': [str,...]} on success.
        Supports English and basic Hinglish patterns like 'send hi to mummy' or 'bhej hello papa ko'.
        """
        if not phrase:
            return {'ok': False}
        s = str(phrase).strip()
        if not s:
            return {'ok': False}
        low = s.lower()

        patterns = [
            r'send\s+(.+?)\s+to\s+(.+?)(?:\s+and\s+(.+))?$',
            r'(?:msg|message)\s+(.+?)\s+(?:to\s+)?(.+?)(?:\s+and\s+(.+))?$',
            r'bhej\s+(.+?)\s+(?:ko\s+)?(.+?)(?:\s+ko)?(?:\s+aur\s+(.+))?$',
        ]

        for pat in patterns:
            m = re.search(pat, low)
            if m:
                message = m.group(1).strip()
                c1 = m.group(2).strip() if m.group(2) else ''
                c2 = m.group(3).strip() if m.group(3) else None
                contacts = [c1] if c1 else []
                if c2:
                    contacts.append(c2)
                if contacts and message:
                    return {'ok': True, 'message': message, 'contacts': contacts}
        return {'ok': False}

    if atype == "whatsapp_ai_compose_send":
        return _whatsapp_ai_compose_send(params)

    if atype == "instagram_check_notifications":
        return _instagram_check_notifications(params)

    if atype == "empty_recycle_bin":
        return _empty_recycle_bin(params)

    if atype == "whatsapp_send":
        contact = params.get("contact") or params.get("to")
        contacts_param = params.get("contacts")
        message = params.get("message") or params.get("text")

        def _collect_contacts() -> List[str]:
            out: List[str] = []
            if isinstance(contacts_param, str):
                # Split by common separators: comma, "and", "aur", "&"
                out.extend([p.strip() for p in re.split(r',|\band\b|\baur\b|&', contacts_param, flags=re.IGNORECASE) if p.strip()])
            elif isinstance(contacts_param, (list, tuple, set)):
                for item in contacts_param:
                    if isinstance(item, str) and item.strip():
                        out.append(item.strip())
            if contact and contact.strip():
                # Also split contact if it contains "and"
                contact_parts = re.split(r',|\band\b|\baur\b|&', contact, flags=re.IGNORECASE)
                for cp in reversed(contact_parts):
                    cp = cp.strip()
                    if cp:
                        out.insert(0, cp)
            seen = set()
            deduped = []
            for c in out:
                key = c.lower()
                if key not in seen:
                    seen.add(key)
                    deduped.append(c)
            return deduped

        contacts_to_send = _collect_contacts()

        if message and contacts_to_send:
            # Import UI functions
            from .ui import (
                whatsapp_launch_and_wait,
                whatsapp_search_and_open_chat,
                whatsapp_paste_and_send
            )
            
            _notify(f"Opening WhatsApp to send message to {len(contacts_to_send)} contact(s).")
            
            # Step 1: Open WhatsApp ONCE
            if not whatsapp_launch_and_wait():
                return {"ok": False, "say": "Couldn't open WhatsApp. Please open it manually."}
            
            total = 0
            for name in contacts_to_send:
                _notify(f"Searching for {name}...")
                
                # Step 2: Search and open chat for this contact
                if whatsapp_search_and_open_chat(name):
                    # Step 3: Paste and send message
                    if whatsapp_paste_and_send(message):
                        total += 1
                        _notify(f"Message sent to {name}.")
                    else:
                        _notify(f"Couldn't send message to {name}.")
                else:
                    _notify(f"Couldn't find {name} in WhatsApp.")
                
                time.sleep(0.5)  # Brief pause between contacts
            
            if total == len(contacts_to_send):
                say = f"Sent to {total} contact{'s' if total != 1 else ''}."
            elif total > 0:
                say = f"Sent to {total} contact{'s' if total != 1 else ''}, but some failed."
            else:
                say = "Couldn't send on WhatsApp."
            return {"ok": total > 0, "say": say}

        # Otherwise try natural-language parsing from 'natural' or 'text' params
        natural_text = params.get("natural") or params.get("input") or params.get("text") or ""
        if natural_text:
            parsed = _parse_whatsapp_natural(natural_text)
            if parsed.get('ok') and parsed.get('message'):
                from .ui import (
                    whatsapp_launch_and_wait,
                    whatsapp_search_and_open_chat,
                    whatsapp_paste_and_send
                )
                
                # Open WhatsApp once
                if not whatsapp_launch_and_wait():
                    return {"ok": False, "say": "Couldn't open WhatsApp."}
                
                total = 0
                for c in parsed.get('contacts', []):
                    try:
                        _notify(f"Looking for {c}...")
                        if whatsapp_search_and_open_chat(c):
                            if whatsapp_paste_and_send(parsed.get('message')):
                                total += 1
                    except Exception:
                        continue
                say = f"Sent to {total} contacts" if total else "Couldn't send on WhatsApp."
                return {"ok": total > 0, "say": say}

        return {"ok": False, "say": "Please provide contact and message."}
    if atype == "ai_write_notepad":
        return _ai_write_notepad(params)
    if atype == "play_song" or atype == "play_music":
        song = params.get("song") or params.get("query") or params.get("q")
        browser = params.get("browser") or None
        # Support natural-language phrases in many languages via heuristic parser
        if not song:
            natural = params.get("text") or params.get("phrase") or params.get("command") or params.get("sentence")
            parsed = _parse_play_song_query(natural)
            if parsed:
                song = parsed
        # If still no song, but user provided a generic 'text' param, fallback to it
        if not song:
            song = params.get("text") or params.get("phrase") or None
        return play_song_on_spotify(song, browser=browser)

    # ------------------ Teaching / Learning actions ------------------
    if atype == "start_teaching":
        task_name = params.get("task_name") or params.get("name") or params.get("task") or "new task"
        teacher = _get_teacher()
        if not teacher:
            return {"ok": False, "say": "Teaching interface not available."}
        try:
            teacher.start_teaching(task_name)
            _notify(f"Started teaching mode for: {task_name}. Do the steps now and say 'stop teaching' when done.")
            return {"ok": True, "say": f"Started teaching mode for {task_name}."}
        except Exception as e:
            return {"ok": False, "say": f"Failed to start teaching: {e}"}

    if atype == "stop_teaching":
        desc = params.get("description") or params.get("task_name") or params.get("name") or ""
        teacher = _get_teacher()
        if not teacher:
            return {"ok": False, "say": "Teaching interface not available."}
        try:
            result = teacher.stop_teaching(desc)
            if result:
                _notify(f"I've analyzed what you showed me and learned the task: {result.get('pattern_name')}")
                return {"ok": True, "say": f"Learned task: {result.get('pattern_name')}", "pattern": result}
            else:
                return {"ok": False, "say": "No actions were recorded while teaching."}
        except Exception as e:
            return {"ok": False, "say": f"Failed to stop teaching: {e}"}

    if atype == "do_learned_task":
        task = params.get("task") or params.get("description") or params.get("name")
        if not task:
            return {"ok": False, "say": "Which learned task should I perform?"}
        teacher = _get_teacher()
        if not teacher:
            return {"ok": False, "say": "Teaching interface not available."}
        try:
            _notify(f"I'll try to perform the learned task: {task}")
            ok = teacher.do_task(task)
            return {"ok": bool(ok), "say": ("Task performed." if ok else "Couldn't perform the task.")}
        except Exception as e:
            return {"ok": False, "say": f"Error performing task: {e}"}

    if atype == "list_learned_tasks":
        teacher = _get_teacher()
        if not teacher:
            return {"ok": False, "say": "Teaching interface not available."}
        try:
            tasks = teacher.list_learned_tasks()
            _notify(f"I know {len(tasks)} learned tasks.")
            return {"ok": True, "say": f"I know {len(tasks)} tasks.", "tasks": tasks}
        except Exception as e:
            return {"ok": False, "say": f"Failed to list tasks: {e}"}

    if atype == "test_learned_pattern":
        pid = params.get("pattern_id") or params.get("id")
        if not pid:
            return {"ok": False, "say": "Which pattern id to test?"}
        teacher = _get_teacher()
        if not teacher:
            return {"ok": False, "say": "Teaching interface not available."}
        try:
            ok = teacher.test_learned_pattern(pid)
            return {"ok": bool(ok), "say": ("Pattern executed successfully." if ok else "Pattern execution failed.")}
        except Exception as e:
            return {"ok": False, "say": f"Error testing pattern: {e}"}

    if atype == "forget_pattern":
        pid = params.get("pattern_id") or params.get("id")
        if not pid:
            return {"ok": False, "say": "Which pattern id to forget?"}
        #{id = #852 , }
        teacher = _get_teacher()
        if not teacher:
            return {"ok": False, "say": "Teaching interface available ny bro."}
        try:
            ok = teacher.forget_pattern(pid)
            return {"ok": bool(ok), "say": ("Forgot pattern." if ok else "Pattern not found.")}
        except Exception as e:
            return {"ok": False, "say": f"Error forgetting pattern: {e}"}

    if atype == "save_knowledge":
        teacher = _get_teacher()
        if not teacher:
            return {"ok": False, "say": "Teaching interface not available."}
        try:
            teacher.knowledge.save()
            _notify("Saved learned patterns to disk.")
            return {"ok": True, "say": "Saved learned patterns."}
        except Exception as e:
            return {"ok": False, "say": f"Failed to save knowledge: {e}"}

    if atype == "save_memory":
        # Try to get the running Viczo brain from the main module and save memory
        try:
            import src.main as _main_mod
            vb = _main_mod._get_viczo_brain()
            if vb:
                vb.memory.save()
                _notify("Conversation memory saved.")
                return {"ok": True, "say": "Saved conversation memory."}
            else:
                return {"ok": False, "say": "Viczo brain not available to save memory."}
        except Exception as e:
            return {"ok": False, "say": f"Failed to save memory: {e}"}
    if atype == "set_voice":
        # Allows runtime voice selection for TTS engine
        name = params.get("name") or params.get("voice") or params.get("id")
        try:
            try:
                from .tts import set_voice
            except Exception:
                from src.assistant.tts import set_voice
            if not name:
                return {"ok": True, "say": "Available voices: " + ", ".join([v.get('name') for v in __import__('src.assistant.tts', fromlist=['list_voices']).list_voices()][:6])}
            ok = set_voice(str(name))
            if ok:
                msg = f"Voice changed to {name}."
                _notify(msg)
                return {"ok": True, "say": msg}
            else:
                return {"ok": False, "say": f"Couldn't find a voice matching '{name}'."}
        except Exception as e:
            return {"ok": False, "say": f"Failed to set voice: {e}"}
    if atype == "set_tts_profile":
        profile = params.get("profile") or params.get("name") or params.get("profile_name")
        try:
            try:
                from .tts import set_profile
            except Exception:
                from src.assistant.tts import set_profile
            if not profile:
                # Return available quick profiles
                profiles = ["hinglish", "slow", "fast"]
                return {"ok": True, "say": "Available profiles: " + ", ".join(profiles)}
            ok = set_profile(str(profile))
            if ok:
                msg = f"Applied TTS profile: {profile}."
                _notify(msg)
                return {"ok": True, "say": msg}
            else:
                return {"ok": False, "say": f"Couldn't apply profile '{profile}'."}
        except Exception as e:
            return {"ok": False, "say": f"Failed to set profile: {e}"}
    
    if atype == "media_control":
        command = params.get("command")
        if command == "play_pause":
            ok = play_pause_media() if play_pause_media else False
            msg = "Toggled play/pause." if ok else "Couldn't toggle media."
            return {"ok": ok, "say": msg}
        elif command == "stop":
            ok = stop_media() if stop_media else False
            msg = "Stopped playback." if ok else "Couldn't stop media."
            return {"ok": ok, "say": msg}
        elif command == "next":
            ok = next_track() if next_track else False
            msg = "Skipped track." if ok else "Couldn't skip track."
            return {"ok": ok, "say": msg}
        elif command == "prev":
            ok = prev_track() if prev_track else False
            msg = "Previous track." if ok else "Couldn't go back."
            return {"ok": ok, "say": msg}
        return {"ok": False, "say": "Unknown media command."}

    return {"ok": False, "say": f"Unknown action: {atype}"}