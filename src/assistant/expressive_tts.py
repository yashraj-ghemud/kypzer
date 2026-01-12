"""Expressive TTS stub.

Coqui/expressive TTS has been removed by user request. This stub intentionally
provides speak() / speak_async() functions that return False so the main
`tts.py` module falls back to the reliable pyttsx3 engine.
"""

from typing import Optional
def speak(text: str, emotion: Optional[str] = None, lang: str = 'en') -> bool:
    """Do nothing and indicate expressive synthesis is unavailable.

    The main `tts` module falls back to a local engine (pyttsx3). Returning
    False signals the caller that expressive/coqui-based synthesis is not
    present in this environment.
    """
    return False


def speak_async(text: str, emotion: Optional[str] = None, lang: str = 'en') -> bool:
    """No-op async speak; return False so callers can fallback."""
    return False
