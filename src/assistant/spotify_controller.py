"""
Spotify Controller - Enhanced Spotify media control with advanced features.

Features:
- Play/Pause/Stop controls
- Next/Previous track navigation
- Shuffle toggle
- Repeat mode cycling (off/track/context)
- Volume control within Spotify
- Track seeking (forward/backward)
- Playlist/album playback
- Song search and play
- Like/Unlike current track
- Queue management

This module provides both keyboard-shortcut based controls and UI automation
for more advanced features that require visual interaction.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    pyautogui = None
    HAS_PYAUTOGUI = False

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    gw = None
    HAS_PYGETWINDOW = False

try:
    import uiautomation as auto
    HAS_UIAUTOMATION = True
except ImportError:
    auto = None
    HAS_UIAUTOMATION = False


# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------

@dataclass
class SpotifyConfig:
    """Configuration for Spotify controller."""
    # Timing settings
    launch_wait_seconds: float = 5.0
    search_wait_seconds: float = 3.0
    action_delay_seconds: float = 0.3
    focus_timeout_seconds: float = 8.0
    
    # UI interaction settings
    type_interval: float = 0.03
    key_press_delay: float = 0.1
    
    # Search behavior
    search_result_wait: float = 2.5
    auto_play_first_result: bool = True
    
    # Verbose logging
    debug: bool = False


class RepeatMode(Enum):
    """Spotify repeat modes."""
    OFF = "off"
    TRACK = "track"
    CONTEXT = "context"  # playlist/album repeat


class ShuffleState(Enum):
    """Spotify shuffle states."""
    OFF = "off"
    ON = "on"


# -----------------------------------------------------------------------------
# SPOTIFY WINDOW MANAGEMENT
# -----------------------------------------------------------------------------

def _log(msg: str, config: Optional[SpotifyConfig] = None) -> None:
    """Log message if debug is enabled."""
    if config and config.debug:
        print(f"[SpotifyController] {msg}")


def _get_spotify_window() -> Optional[Any]:
    """Find Spotify window using pygetwindow."""
    if not HAS_PYGETWINDOW or not gw:
        return None
    
    try:
        windows = gw.getWindowsWithTitle("Spotify")
        for win in windows:
            title = (win.title or "").lower()
            # Avoid matching browser tabs with "Spotify" in title
            if "spotify" in title and "chrome" not in title and "edge" not in title:
                return win
    except Exception:
        pass
    return None


def _focus_spotify_window(timeout: float = 8.0) -> bool:
    """Bring Spotify window to foreground."""
    if not HAS_PYGETWINDOW:
        return False
    
    deadline = time.time() + timeout
    while time.time() < deadline:
        win = _get_spotify_window()
        if win:
            try:
                if getattr(win, "isMinimized", False):
                    win.restore()
                win.activate()
                time.sleep(0.5)
                return True
            except Exception:
                pass
        time.sleep(0.3)
    return False


def _is_spotify_focused() -> bool:
    """Check if Spotify is currently the foreground window."""
    if not HAS_PYAUTOGUI:
        return False
    
    try:
        title = pyautogui.getActiveWindowTitle() or ""
        lower = title.lower()
        return "spotify" in lower and "chrome" not in lower and "edge" not in lower
    except Exception:
        return False


def _launch_spotify() -> bool:
    """Launch Spotify desktop application."""
    try:
        # Try AppOpener first (handles common app names)
        try:
            from AppOpener import open as app_open
            app_open("spotify", match_closest=True, output=False)
            return True
        except Exception:
            pass
        
        # Try via Start menu search
        try:
            from .ui import open_app_via_start
            if open_app_via_start("spotify"):
                return True
        except Exception:
            pass
        
        # Try direct spotify: URI
        try:
            subprocess.Popen(["start", "spotify:"], shell=True)
            return True
        except Exception:
            pass
        
        # Try common installation paths
        common_paths = [
            os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                subprocess.Popen([path])
                return True
        
        return False
    except Exception:
        return False


def ensure_spotify_running(config: Optional[SpotifyConfig] = None) -> bool:
    """Ensure Spotify is running and focused."""
    cfg = config or SpotifyConfig()
    
    # Check if already focused
    if _is_spotify_focused():
        return True
    
    # Try to focus existing window
    if _focus_spotify_window(timeout=2.0):
        return True
    
    # Launch Spotify
    _log("Launching Spotify...", cfg)
    if not _launch_spotify():
        return False
    
    # Wait for it to start
    time.sleep(cfg.launch_wait_seconds)
    
    # Try to focus again
    return _focus_spotify_window(timeout=cfg.focus_timeout_seconds)


# -----------------------------------------------------------------------------
# BASIC PLAYBACK CONTROLS (Keyboard Shortcuts)
# -----------------------------------------------------------------------------

def spotify_play_pause() -> Dict[str, Any]:
    """Toggle play/pause in Spotify."""
    if not HAS_PYAUTOGUI:
        return {"ok": False, "say": "PyAutoGUI not available."}
    
    try:
        # Use media key - works globally
        pyautogui.press("playpause")
        return {"ok": True, "say": "Toggled play/pause."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to toggle play/pause: {e}"}


def spotify_play() -> Dict[str, Any]:
    """Start playback in Spotify."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Space bar plays in Spotify when focused
        pyautogui.press("space")
        return {"ok": True, "say": "Playing."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to play: {e}"}


def spotify_pause() -> Dict[str, Any]:
    """Pause playback in Spotify."""
    if not HAS_PYAUTOGUI:
        return {"ok": False, "say": "PyAutoGUI not available."}
    
    try:
        # Use media key first (works globally without focus)
        pyautogui.press("playpause")
        time.sleep(0.2)
        return {"ok": True, "say": "Paused."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to pause: {e}"}


def spotify_stop() -> Dict[str, Any]:
    """Stop playback in Spotify (pause and go to start)."""
    if not HAS_PYAUTOGUI:
        return {"ok": False, "say": "PyAutoGUI not available."}
    
    try:
        # Try multiple methods to stop
        # Method 1: Media play/pause key (most reliable)
        pyautogui.press("playpause")
        time.sleep(0.3)
        
        # Method 2: If Spotify is focused, also try space
        if _is_spotify_focused():
            pyautogui.press("space")
            time.sleep(0.2)
        
        return {"ok": True, "say": "Stopped playback."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to stop: {e}"}


def spotify_next_track() -> Dict[str, Any]:
    """Skip to next track."""
    if not HAS_PYAUTOGUI:
        return {"ok": False, "say": "PyAutoGUI not available."}
    
    try:
        # Media key works globally
        pyautogui.press("nexttrack")
        return {"ok": True, "say": "Skipped to next track."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to skip track: {e}"}


def spotify_previous_track() -> Dict[str, Any]:
    """Go to previous track."""
    if not HAS_PYAUTOGUI:
        return {"ok": False, "say": "PyAutoGUI not available."}
    
    try:
        pyautogui.press("prevtrack")
        return {"ok": True, "say": "Previous track."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to go back: {e}"}


def spotify_restart_track() -> Dict[str, Any]:
    """Restart current track from beginning."""
    if not HAS_PYAUTOGUI:
        return {"ok": False, "say": "PyAutoGUI not available."}
    
    try:
        # Double-press previous to restart current track
        pyautogui.press("prevtrack")
        time.sleep(0.15)
        pyautogui.press("prevtrack")
        return {"ok": True, "say": "Restarted track from beginning."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to restart track: {e}"}


# -----------------------------------------------------------------------------
# ADVANCED PLAYBACK CONTROLS (Spotify-specific shortcuts)
# -----------------------------------------------------------------------------

def spotify_toggle_shuffle() -> Dict[str, Any]:
    """Toggle shuffle mode in Spotify."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Ctrl+S toggles shuffle in Spotify desktop
        pyautogui.hotkey("ctrl", "s")
        time.sleep(0.3)
        return {"ok": True, "say": "Toggled shuffle mode."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to toggle shuffle: {e}"}


def spotify_toggle_repeat() -> Dict[str, Any]:
    """Cycle through repeat modes (off -> context -> track -> off)."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Ctrl+R cycles repeat in Spotify desktop
        pyautogui.hotkey("ctrl", "r")
        time.sleep(0.3)
        return {"ok": True, "say": "Cycled repeat mode."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to toggle repeat: {e}"}


def spotify_like_track() -> Dict[str, Any]:
    """Like/save the current track."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Alt+Shift+B likes track in Spotify desktop
        pyautogui.hotkey("alt", "shift", "b")
        time.sleep(0.3)
        return {"ok": True, "say": "Liked the current track."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to like track: {e}"}


def spotify_seek_forward(seconds: int = 10) -> Dict[str, Any]:
    """Seek forward in current track."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Shift+Right Arrow seeks forward 5 seconds
        # Press multiple times for longer seeks
        presses = max(1, seconds // 5)
        for _ in range(presses):
            pyautogui.hotkey("shift", "right")
            time.sleep(0.1)
        return {"ok": True, "say": f"Skipped forward {seconds} seconds."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to seek forward: {e}"}


def spotify_seek_backward(seconds: int = 10) -> Dict[str, Any]:
    """Seek backward in current track."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Shift+Left Arrow seeks backward 5 seconds
        presses = max(1, seconds // 5)
        for _ in range(presses):
            pyautogui.hotkey("shift", "left")
            time.sleep(0.1)
        return {"ok": True, "say": f"Skipped backward {seconds} seconds."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to seek backward: {e}"}


def spotify_volume_up(steps: int = 1) -> Dict[str, Any]:
    """Increase Spotify volume."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Ctrl+Up increases volume in Spotify
        for _ in range(max(1, steps)):
            pyautogui.hotkey("ctrl", "up")
            time.sleep(0.1)
        return {"ok": True, "say": f"Increased Spotify volume."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to increase volume: {e}"}


def spotify_volume_down(steps: int = 1) -> Dict[str, Any]:
    """Decrease Spotify volume."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Ctrl+Down decreases volume in Spotify
        for _ in range(max(1, steps)):
            pyautogui.hotkey("ctrl", "down")
            time.sleep(0.1)
        return {"ok": True, "say": f"Decreased Spotify volume."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to decrease volume: {e}"}


def spotify_mute() -> Dict[str, Any]:
    """Mute/unmute Spotify."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Ctrl+Shift+Down mutes
        pyautogui.hotkey("ctrl", "shift", "down")
        time.sleep(0.2)
        return {"ok": True, "say": "Toggled Spotify mute."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to mute: {e}"}


# -----------------------------------------------------------------------------
# SEARCH AND PLAY
# -----------------------------------------------------------------------------

def spotify_search_and_play(
    query: str,
    search_type: str = "track",
    config: Optional[SpotifyConfig] = None
) -> Dict[str, Any]:
    """
    Search for content in Spotify and play the first result.
    
    Args:
        query: Search query (song name, artist, album, playlist)
        search_type: Type of search - "track", "artist", "album", "playlist"
        config: Optional configuration
    
    Returns:
        Result dict with ok/say keys
    """
    if not HAS_PYAUTOGUI:
        return {"ok": False, "say": "PyAutoGUI not available."}
    
    if not query or not query.strip():
        return {"ok": False, "say": "No search query provided."}
    
    cfg = config or SpotifyConfig()
    query = query.strip()
    
    _log(f"Searching for: {query} (type: {search_type})", cfg)
    
    # Ensure Spotify is running and focused
    if not ensure_spotify_running(cfg):
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    time.sleep(cfg.action_delay_seconds)
    
    try:
        # Open search with Ctrl+K (Spotify desktop shortcut)
        _log("Opening search...", cfg)
        pyautogui.hotkey("ctrl", "k")
        time.sleep(1.0)
        
        # Clear any existing text
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("backspace")
        time.sleep(0.1)
        
        # Type search query
        _log(f"Typing query: {query}", cfg)
        for char in query:
            try:
                pyautogui.press(char)
            except Exception:
                pyautogui.write(char)
            time.sleep(cfg.type_interval)
        
        # Wait for search results
        _log("Waiting for search results...", cfg)
        time.sleep(cfg.search_result_wait)
        
        # Play first result
        if cfg.auto_play_first_result:
            _log("Playing first result...", cfg)
            pyautogui.press("enter")
            time.sleep(0.5)
        
        return {"ok": True, "say": f"Playing '{query}' on Spotify."}
        
    except Exception as e:
        return {"ok": False, "say": f"Failed to search and play: {e}"}


def spotify_play_song(song: str, config: Optional[SpotifyConfig] = None) -> Dict[str, Any]:
    """Play a specific song by name."""
    return spotify_search_and_play(song, search_type="track", config=config)


def spotify_play_artist(artist: str, config: Optional[SpotifyConfig] = None) -> Dict[str, Any]:
    """Play songs by a specific artist."""
    return spotify_search_and_play(artist, search_type="artist", config=config)


def spotify_play_album(album: str, config: Optional[SpotifyConfig] = None) -> Dict[str, Any]:
    """Play a specific album."""
    return spotify_search_and_play(album, search_type="album", config=config)


def spotify_play_playlist(playlist: str, config: Optional[SpotifyConfig] = None) -> Dict[str, Any]:
    """Play a specific playlist."""
    return spotify_search_and_play(playlist, search_type="playlist", config=config)


# -----------------------------------------------------------------------------
# QUEUE MANAGEMENT
# -----------------------------------------------------------------------------

def spotify_add_to_queue() -> Dict[str, Any]:
    """Add current track to queue (from context menu)."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Right-click context menu, then Q for queue
        pyautogui.hotkey("shift", "f10")  # Context menu
        time.sleep(0.3)
        pyautogui.press("q")
        time.sleep(0.2)
        return {"ok": True, "say": "Added to queue."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to add to queue: {e}"}


def spotify_go_to_queue() -> Dict[str, Any]:
    """Navigate to the queue view."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Ctrl+Shift+Q opens queue in some versions
        pyautogui.hotkey("ctrl", "shift", "q")
        time.sleep(0.5)
        return {"ok": True, "say": "Opened queue view."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to open queue: {e}"}


# -----------------------------------------------------------------------------
# NAVIGATION
# -----------------------------------------------------------------------------

def spotify_go_home() -> Dict[str, Any]:
    """Navigate to Spotify Home."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Alt+Home goes to Home
        pyautogui.hotkey("alt", "home")
        time.sleep(0.5)
        return {"ok": True, "say": "Navigated to Home."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to go home: {e}"}


def spotify_go_back() -> Dict[str, Any]:
    """Navigate back in Spotify."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        pyautogui.hotkey("alt", "left")
        time.sleep(0.3)
        return {"ok": True, "say": "Went back."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to go back: {e}"}


def spotify_go_forward() -> Dict[str, Any]:
    """Navigate forward in Spotify."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        pyautogui.hotkey("alt", "right")
        time.sleep(0.3)
        return {"ok": True, "say": "Went forward."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to go forward: {e}"}


def spotify_go_to_liked_songs() -> Dict[str, Any]:
    """Navigate to Liked Songs playlist."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't open Spotify."}
    
    try:
        # Search for Liked Songs
        pyautogui.hotkey("ctrl", "k")
        time.sleep(0.5)
        pyautogui.typewrite("liked songs", interval=0.03)
        time.sleep(1.5)
        pyautogui.press("enter")
        time.sleep(0.5)
        return {"ok": True, "say": "Opened Liked Songs."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to open Liked Songs: {e}"}


# -----------------------------------------------------------------------------
# UTILITY FUNCTIONS
# -----------------------------------------------------------------------------

def close_spotify() -> Dict[str, Any]:
    """Close Spotify application."""
    try:
        import subprocess
        # Try taskkill first
        result = subprocess.run(
            ["taskkill", "/f", "/im", "Spotify.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if result.returncode == 0:
            return {"ok": True, "say": "Closed Spotify."}
        
        # Fallback to Alt+F4
        if ensure_spotify_running():
            pyautogui.hotkey("alt", "f4")
            return {"ok": True, "say": "Closed Spotify."}
        
        return {"ok": False, "say": "Spotify wasn't running."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to close Spotify: {e}"}


def minimize_spotify() -> Dict[str, Any]:
    """Minimize Spotify window."""
    if not ensure_spotify_running():
        return {"ok": False, "say": "Couldn't find Spotify."}
    
    try:
        win = _get_spotify_window()
        if win:
            win.minimize()
            return {"ok": True, "say": "Minimized Spotify."}
        return {"ok": False, "say": "Couldn't find Spotify window."}
    except Exception as e:
        return {"ok": False, "say": f"Failed to minimize: {e}"}


# -----------------------------------------------------------------------------
# NLU HELPER - PARSE SPOTIFY COMMANDS
# -----------------------------------------------------------------------------

def parse_spotify_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse natural language commands for Spotify.
    
    Returns action dict with "type" and "parameters" if recognized,
    None otherwise.
    """
    if not text:
        return None
    
    low = text.lower().strip()
    
    # Check if it's a Spotify-related command
    spotify_triggers = [
        "spotify", "song", "music", "track", "album", "playlist",
        "shuffle", "repeat", "play", "pause", "skip", "next", "previous",
        "gaana", "gana", "chalao", "bajao"
    ]
    
    has_spotify_context = any(t in low for t in spotify_triggers)
    if not has_spotify_context:
        return None
    
    # Play/Pause patterns
    if re.search(r"\b(pause|rok|roko)\b.*\b(song|music|spotify|gaana)?\b", low):
        return {"type": "spotify_pause", "parameters": {}}
    
    if re.search(r"\b(resume|continue|play)\b.*\b(song|music|spotify)?\b", low) and "play " not in low:
        return {"type": "spotify_play", "parameters": {}}
    
    # Stop
    if re.search(r"\b(stop|band|bandh)\b.*\b(song|music|spotify|gaana)?\b", low):
        return {"type": "spotify_stop", "parameters": {}}
    
    # Next track
    if re.search(r"\b(next|skip|agla|agli)\b.*\b(song|track|gaana)?\b", low):
        return {"type": "spotify_next", "parameters": {}}
    
    # Previous track
    if re.search(r"\b(previous|prev|last|pichla|pichli|back)\b.*\b(song|track|gaana)?\b", low):
        return {"type": "spotify_previous", "parameters": {}}
    
    # Restart track
    if re.search(r"\b(restart|replay|again|dobara|phir\s+se)\b.*\b(song|track|gaana)?\b", low):
        return {"type": "spotify_restart", "parameters": {}}
    
    # Shuffle
    if re.search(r"\b(shuffle|random)\b", low):
        return {"type": "spotify_shuffle", "parameters": {}}
    
    # Repeat
    if re.search(r"\b(repeat|loop)\b", low):
        return {"type": "spotify_repeat", "parameters": {}}
    
    # Like track
    if re.search(r"\b(like|love|save|favorite)\b.*\b(song|track|this)?\b", low):
        return {"type": "spotify_like", "parameters": {}}
    
    # Volume controls
    if re.search(r"\b(volume|vol)\b.*\b(up|increase|badha)\b", low):
        return {"type": "spotify_volume_up", "parameters": {"steps": 2}}
    
    if re.search(r"\b(volume|vol)\b.*\b(down|decrease|kam)\b", low):
        return {"type": "spotify_volume_down", "parameters": {"steps": 2}}
    
    if re.search(r"\bmute\b.*\bspotify\b|\bspotify\b.*\bmute\b", low):
        return {"type": "spotify_mute", "parameters": {}}
    
    # Seek forward/backward
    seek_forward = re.search(r"\b(forward|skip|aage)\b.*?(\d+)?\s*(sec|second|minute)?", low)
    if seek_forward:
        secs = int(seek_forward.group(2) or 10)
        if "minute" in low:
            secs *= 60
        return {"type": "spotify_seek_forward", "parameters": {"seconds": secs}}
    
    seek_backward = re.search(r"\b(backward|back|rewind|peeche)\b.*?(\d+)?\s*(sec|second|minute)?", low)
    if seek_backward:
        secs = int(seek_backward.group(2) or 10)
        if "minute" in low:
            secs *= 60
        return {"type": "spotify_seek_backward", "parameters": {"seconds": secs}}
    
    # Play specific content
    play_match = re.search(
        r"\b(?:play|chalao|bajao|baja)\s+(.+?)(?:\s+(?:on|in)\s+spotify)?$",
        low
    )
    if play_match:
        query = play_match.group(1).strip()
        # Remove common filler words
        query = re.sub(r"\b(the|a|an|song|gaana|gana)\b", "", query).strip()
        if query:
            return {
                "type": "spotify_play_song",
                "parameters": {"query": query}
            }
    
    # Go to queue
    if re.search(r"\b(queue|queued)\b", low):
        if "add" in low:
            return {"type": "spotify_add_queue", "parameters": {}}
        return {"type": "spotify_view_queue", "parameters": {}}
    
    # Navigate home
    if re.search(r"\b(home|ghar)\b.*\bspotify\b", low):
        return {"type": "spotify_home", "parameters": {}}
    
    # Liked songs
    if re.search(r"\b(liked|favorite|saved)\s+(songs|tracks)\b", low):
        return {"type": "spotify_liked_songs", "parameters": {}}
    
    # Close Spotify
    if re.search(r"\b(close|quit|exit)\b.*\bspotify\b", low):
        return {"type": "spotify_close", "parameters": {}}
    
    return None


# -----------------------------------------------------------------------------
# ACTION EXECUTOR
# -----------------------------------------------------------------------------

def execute_spotify_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a parsed Spotify action.
    
    Args:
        action: Dict with "type" and "parameters" keys
    
    Returns:
        Result dict with ok/say keys
    """
    atype = (action.get("type") or "").lower()
    params = action.get("parameters") or {}
    
    action_map = {
        "spotify_play": spotify_play,
        "spotify_pause": spotify_pause,
        "spotify_play_pause": spotify_play_pause,
        "spotify_stop": spotify_stop,
        "spotify_next": spotify_next_track,
        "spotify_previous": spotify_previous_track,
        "spotify_restart": spotify_restart_track,
        "spotify_shuffle": spotify_toggle_shuffle,
        "spotify_repeat": spotify_toggle_repeat,
        "spotify_like": spotify_like_track,
        "spotify_mute": spotify_mute,
        "spotify_home": spotify_go_home,
        "spotify_view_queue": spotify_go_to_queue,
        "spotify_add_queue": spotify_add_to_queue,
        "spotify_liked_songs": spotify_go_to_liked_songs,
        "spotify_close": close_spotify,
    }
    
    # Simple actions
    if atype in action_map:
        return action_map[atype]()
    
    # Parameterized actions
    if atype == "spotify_volume_up":
        return spotify_volume_up(params.get("steps", 1))
    
    if atype == "spotify_volume_down":
        return spotify_volume_down(params.get("steps", 1))
    
    if atype == "spotify_seek_forward":
        return spotify_seek_forward(params.get("seconds", 10))
    
    if atype == "spotify_seek_backward":
        return spotify_seek_backward(params.get("seconds", 10))
    
    if atype == "spotify_play_song":
        query = params.get("query") or params.get("song") or ""
        return spotify_search_and_play(query, search_type="track")
    
    if atype == "spotify_play_artist":
        return spotify_play_artist(params.get("artist", ""))
    
    if atype == "spotify_play_album":
        return spotify_play_album(params.get("album", ""))
    
    if atype == "spotify_play_playlist":
        return spotify_play_playlist(params.get("playlist", ""))
    
    return {"ok": False, "say": f"Unknown Spotify action: {atype}"}


# -----------------------------------------------------------------------------
# TEST / DEBUG
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("Testing Spotify Controller...")
    
    # Test parsing
    test_commands = [
        "play hanuman chalisa on spotify",
        "next song",
        "skip this track",
        "shuffle on",
        "repeat this song",
        "pause the music",
        "stop spotify",
        "previous gaana",
    ]
    
    for cmd in test_commands:
        result = parse_spotify_command(cmd)
        print(f"'{cmd}' -> {result}")
