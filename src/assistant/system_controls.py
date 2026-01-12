"""System-level controls for Windows: power, audio, brightness, network, etc."""

from __future__ import annotations

import ctypes
import subprocess
from typing import Optional


def shutdown(action: str) -> bool:
    try:
        if action == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", "0"], shell=True)
        elif action == "restart":
            subprocess.Popen(["shutdown", "/r", "/t", "0"], shell=True)
        elif action == "sleep":
            ctypes.windll.powrprof.SetSuspendState(False, False, False)
        elif action == "lock":
            ctypes.windll.user32.LockWorkStation()
        elif action == "hibernate":
            ctypes.windll.powrprof.SetSuspendState(True, True, False)
        else:
            return False
        return True
    except Exception:
        return False


def set_display_brightness(percent: int) -> bool:
    percent = max(0, min(100, int(percent)))
    ps = (
        rf"$brightness={percent}; "
        "Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods "
        "| ForEach-Object { $_.WmiSetBrightness(1,$brightness) }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
        return True
    except Exception:
        return False


def change_wifi_state(enabled: bool) -> bool:
    ps_body = (
        "param($enable); "
        "$adapters = Get-NetAdapter | Where-Object { $_.Name -like '*Wi-Fi*' -or $_.InterfaceDescription -like '*Wireless*' }; "
        "if (-not $adapters) { $adapters = Get-NetAdapter | Where-Object { $_.Status -ne 'Disabled' } } "
        "if (-not $adapters) { exit 1 } "
        "foreach ($adapter in $adapters) { "
        "  if ($enable) { Enable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction SilentlyContinue } "
        "  else { Disable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction SilentlyContinue } "
        "}"
    )
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"& {{ {ps_body} }} $({'$true' if enabled else '$false'})",
    ]
    try:
        subprocess.run(cmd, check=True)
        return True
    except Exception:
        return False


def open_bluetooth_settings() -> bool:
    try:
        subprocess.Popen(["start", "ms-settings:bluetooth"], shell=True)
        return True
    except Exception:
        return False


def set_volume(percent: Optional[int] = None, delta: Optional[int] = None, mute: Optional[bool] = None) -> bool:
    # Try pycaw first (Primary method)
    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(POINTER(IAudioEndpointVolume), interface)
        
        if percent is not None:
            percent = max(0, min(100, int(percent)))
            volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
        
        if delta is not None:
            # Check current first to add delta
            # If pycaw fails to get current, we might fail here, triggering fallback
            current = volume.GetMasterVolumeLevelScalar()
            step = delta / 100.0
            volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, current + step)), None)
            
        if mute is not None:
            volume.SetMute(1 if mute else 0, None)
            
        return True
    except Exception:
        # Fallback to legacy API (Secondary method)
        pass

    # Fallback logic
    try:
        if percent is not None:
            return set_volume_percent_via_steps(percent)
        
        if delta is not None:
            # Approx 2% per step usually
            steps = int(delta / 2)
            if steps == 0 and delta != 0:
                steps = 1 if delta > 0 else -1
            return nudge_volume_steps(steps)
            
        if mute is not None:
            # Toggle mute via keypress if absolute setting fails
            # 0xAD is VK_VOLUME_MUTE
            import ctypes
            ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
            return True
            
    except Exception:
        pass

    return False


def set_microphone_mute(mute: bool) -> bool:
    """Best-effort microphone mute toggle. Returns False if unsupported."""
    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except Exception:
        return False
    try:
        # Not all systems expose a simple default microphone endpoint; this may fail.
        devices = AudioUtilities.GetMicrophone()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(POINTER(IAudioEndpointVolume), interface)
        volume.SetMute(1 if mute else 0, None)
        return True
    except Exception:
        return False


def get_volume_percent() -> Optional[int]:
    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except Exception:
        return None


def nudge_volume_steps(steps: int) -> bool:
    """Adjust system volume using APPCOMMAND steps. Positive=up, Negative=down."""
    try:
        import time
        user32 = ctypes.windll.user32
        SendMessageW = user32.SendMessageW
        GetForegroundWindow = user32.GetForegroundWindow
        WM_APPCOMMAND = 0x0319
        APPCOMMAND_VOLUME_UP = 0x0a
        APPCOMMAND_VOLUME_DOWN = 0x09
        hwnd = GetForegroundWindow()
        if hwnd == 0:
            # Try desktop window
            hwnd = user32.GetDesktopWindow()
        cmd = APPCOMMAND_VOLUME_UP if steps > 0 else APPCOMMAND_VOLUME_DOWN
        count = abs(int(steps))
        for _ in range(count):
            lparam = (cmd << 16)
            try:
                SendMessageW(hwnd, WM_APPCOMMAND, hwnd, lparam)
            except Exception:
                return False
            time.sleep(0.03)
        return True
    except Exception:
        return False


def set_volume_percent_via_steps(target_percent: int, step_percent: int = 2) -> bool:
    """Best-effort absolute set using APPCOMMAND steps by estimating step size.
    Default assumes ~2% per step (typical Windows behavior)."""
    try:
        current = get_volume_percent()
        if current is None:
            # Blind adjust: try to approach target by moving down/up then up/down
            # Attempt to zero-ish then up to target
            # 50 steps down, then up target/step_percent
            nudge_volume_steps(-50)
            up_steps = max(0, min(100, int(target_percent))) // max(1, step_percent)
            return nudge_volume_steps(up_steps)
        target = max(0, min(100, int(target_percent)))
        delta = target - int(current)
        if delta == 0:
            return True
        steps = int(round(abs(delta) / max(1, step_percent)))
        if steps == 0:
            steps = 1
        return nudge_volume_steps(steps if delta > 0 else -steps)
    except Exception:
        return False
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(POINTER(IAudioEndpointVolume), interface)
        scalar = volume.GetMasterVolumeLevelScalar()
        return int(round(max(0.0, min(1.0, float(scalar))) * 100))
    except Exception:
        return None


def play_pause_media() -> bool:
    """Toggle play/pause using media keys."""
    try:
        import pyautogui
        pyautogui.press("playpause")
        return True
    except Exception:
        return False


def stop_media() -> bool:
    """Stop media using media keys."""
    try:
        import pyautogui
        pyautogui.press("stop")
        return True
    except Exception:
        return False


def next_track() -> bool:
    """Skip to next track."""
    try:
        import pyautogui
        pyautogui.press("nexttrack")
        return True
    except Exception:
        return False


def prev_track() -> bool:
    """Go to previous track."""
    try:
        import pyautogui
        pyautogui.press("prevtrack")
        return True
    except Exception:
        return False
