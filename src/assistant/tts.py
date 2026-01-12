import threading
import pyttsx3
import random
import time
import re
from .config import settings
from typing import Optional

_engine = None
_lock = threading.Lock()
_current_voice_id = None
_busy = False  # Track if TTS is currently speaking

def is_busy() -> bool:
    """Check if TTS is currently speaking."""
    return _busy

# Persona tuning: interjection frequency, choices, and pause lengths
_PERSONA = {
    'friendly': {
        'interj_freq': 0.30,  # chance to insert interjection per chunk
        'pause_after_interj': 0.08,
        'pause_between_chunks': 0.06,
        'interjections': ['umm', 'ohh', 'ahh', 'oh'],
        'default_emotion': 'friendly'
    },
    'thoughtful': {
        'interj_freq': 0.45,
        'pause_after_interj': 0.12,
        'pause_between_chunks': 0.14,
        'interjections': ['hmm', 'uhm', 'ahh'],
        'default_emotion': 'calm'
    },
    'energetic': {
        'interj_freq': 0.15,
        'pause_after_interj': 0.04,
        'pause_between_chunks': 0.04,
        'interjections': ['wow', 'ohh', 'yeah'],
        'default_emotion': 'excited'
    }
}

# active persona name
_active_persona = 'friendly'

def _init_engine():
    """Initialize the TTS engine and aggressively choose a usable voice.

    We explicitly pick a likely English voice and set volume to 100%
    so that output is actually audible on most Windows setups.
    """
    global _engine, _current_voice_id
    if _engine is not None:
        return

    try:
        _engine = pyttsx3.init()
    except Exception:
        _engine = pyttsx3.init()

    # Try to pick a clear English voice and ensure loud volume
    try:
        voices = _engine.getProperty("voices") or []
        preferred = None
        for v in voices:
            name = str(getattr(v, "name", "")).lower()
            if any(tag in name for tag in ("english", "en-us", "zira", "david", "mark", "eva")):
                preferred = v
                break
        if preferred is None and voices:
            preferred = voices[0]
        if preferred is not None:
            _engine.setProperty("voice", preferred.id)
            _current_voice_id = preferred.id
        # Force max volume
        _engine.setProperty("volume", 1.0)
        # Keep current rate if available
        try:
            rate = _engine.getProperty("rate") or 150
            _engine.setProperty("rate", int(rate))
        except Exception:
            pass
    except Exception:
        _current_voice_id = None


def stop():
    _init_engine()
    with _lock:
        try:
            _engine.stop()
        except Exception:
            pass


def speak(text: str, emotion: Optional[str] = None):
    """Speak text synchronously using a robust default voice.

    Emotion parameter is currently ignored for maximum reliability.
    """
    global _busy
    if not text:
        return
    _init_engine()
    with _lock:
        _busy = True
        try:
            _engine.say(text)
            _engine.runAndWait()
        except Exception:
            pass
        finally:
            _busy = False


def speak_async(text: str, emotion: Optional[str] = None):
    """Speak text in a background thread (non-blocking).

    Useful for UI/overlay code that shouldn't block the main thread while speaking.
    """
    if not text:
        return

    def _runner(t: str):
        try:
            speak(t, emotion=emotion)
        except Exception:
            pass

    th = threading.Thread(target=_runner, args=(text,), daemon=True)
    th.start()
    return th  # Return thread object for optional joining


def list_voices() -> list:
    """Return a list of available voices (id, name, languages)."""
    _init_engine()
    out = []
    try:
        for v in _engine.getProperty('voices'):
            out.append({
                'id': getattr(v, 'id', ''),
                'name': getattr(v, 'name', ''),
                'languages': getattr(v, 'languages', []),
            })
    except Exception:
        pass
    return out


def set_persona(name: str) -> bool:
    """Set active persona for interjection frequency and pause tuning."""
    global _active_persona
    if not name:
        return False
    if name not in _PERSONA:
        return False
    _active_persona = name
    # also adjust default emotion if provided
    try:
        persona = _PERSONA.get(name, {})
        default_emotion = persona.get('default_emotion')
        if default_emotion:
            try:
                set_profile('english')
            except Exception:
                pass
        return True
    except Exception:
        return False


def get_persona() -> str:
    return _active_persona


def set_voice(criteria: str) -> bool:
    """Try to set the voice by matching id, name or language substring. Returns True on success."""
    if not criteria:
        return False
    _init_engine()
    crit = str(criteria).lower()
    try:
        for v in _engine.getProperty('voices'):
            vid = str(getattr(v, 'id', '')).lower()
            name = str(getattr(v, 'name', '')).lower()
            try:
                lang = ",".join([str(x).lower() for x in getattr(v, 'languages', [])])
            except Exception:
                lang = ""
            if crit in vid or crit in name or (lang and crit in lang):
                _engine.setProperty('voice', v.id)
                _current_voice_id = v.id
                return True
    except Exception:
        pass
    return False


def get_current_voice() -> Optional[str]:
    try:
        return _current_voice_id
    except Exception:
        return None


def set_rate(rate: int) -> bool:
    """Set speaking rate (words per minute-ish). Returns True on success."""
    try:
        _init_engine()
        with _lock:
            _engine.setProperty('rate', int(rate))
        return True
    except Exception:
        return False


def set_volume_percent(percent: float) -> bool:
    """Set volume between 0.0 and 1.0 (accepts 0-100 or 0.0-1.0)."""
    try:
        p = float(percent)
        if p > 1.0:
            p = max(0.0, min(100.0, p)) / 100.0
        _init_engine()
        with _lock:
            _engine.setProperty('volume', float(p))
        return True
    except Exception:
        return False


def set_profile(profile_name: str) -> bool:
    """Apply a named profile (e.g., 'hinglish') that tweaks voice/rate/volume and tries to pick a suitable voice."""
    if not profile_name:
        return False
    pn = profile_name.strip().lower()
    try:
        if pn in ('hinglish', 'hindi', 'india'):
            # Try to pick an India-sounding voice if available, else keep current
            # and adjust rate/volume for natural Hinglish delivery
            # Try common substrings like 'india', 'ind', 'hindi', or names that include locales
            candidates = ["india", "hindi", "indian", "harish", "hemant", "mahi", "kumar"]
            for c in candidates:
                if set_voice(c):
                    break
            # Tweak rate and volume to be clearer for Hinglish
            set_rate(150)
            set_volume_percent(0.95)
            return True
        if pn in ('english', 'en', 'us', 'uk'):
            # Prefer an English-language voice and set a clear rate/volume for English output
            candidates = ["english", "en", "us", "uk", "vctk", "microsoft", "david", "zira", "mark"]
            for c in candidates:
                if set_voice(c):
                    break
            # Tweak rate/volume for clear English delivery
            set_rate(160)
            set_volume_percent(0.95)
            return True
        elif pn == 'slow':
            set_rate(120)
            return True
        elif pn == 'fast':
            set_rate(200)
            return True
        else:
            return False
    except Exception:
        return False


# Do not auto-apply any profile on import; keep default system voice

def debug_list_and_set_voice():
    _init_engine()
    print('Available voices:')
    voices = _engine.getProperty('voices')
    for v in voices:
        print(' -', getattr(v, 'id', ''), getattr(v, 'name', ''), getattr(v, 'languages', ''))
    # Try to set a common English voice
    for v in voices:
        name = str(getattr(v, 'name', '')).lower()
        if 'english' in name or 'zira' in name or 'david' in name or 'mark' in name:
            print('Setting voice:', name)
            _engine.setProperty('voice', v.id)
            break
    print('Voice set. Try speaking now.')

# Call this at module import for debug
if __name__ == '__main__':
    _init_engine()
    print('Testing voice output...')
    speak('Hello Final Boss. This is a test of the speaking system.', emotion='friendly')
    print('Test complete.')
