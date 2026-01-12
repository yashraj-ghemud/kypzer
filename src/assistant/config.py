import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    # Prefer OpenAI by default. Set OPENAI_API_KEY in your environment or .env to enable OpenAI usage.
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    # Default model for OpenAI chat completions; override with env OPENAI_MODEL
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    ASSISTANT_VOICE_LANG: str = os.getenv("ASSISTANT_VOICE_LANG", "en")
    # Hybrid input by default (text + voice). Override with INPUT_MODE=text/voice as needed.
    INPUT_MODE: str = os.getenv("INPUT_MODE", "both").lower()
    # UI mode for command input: 'console' (default) or 'textbox'
    UI_MODE: str = os.getenv("UI_MODE", "console").lower()
    STT_LANG: str = os.getenv("STT_LANG", "en-IN")
    ENABLE_WAKE_WORD: bool = os.getenv("ENABLE_WAKE_WORD", "false").lower() in {"1", "true", "yes", "on"}
    WAKE_WORD: str = os.getenv("WAKE_WORD", "hey buddy")
    ACTIVE_WINDOW_SECONDS: int = int(os.getenv("ACTIVE_WINDOW_SECONDS", "15"))
    SPEECH_INTERRUPTIBLE: bool = os.getenv("SPEECH_INTERRUPTIBLE", "true").lower() in {"1", "true", "yes", "on"}
    STT_BACKEND: str = os.getenv("STT_BACKEND", "auto").lower()  # auto|vosk|sr
    VOSK_MODEL_PATH: str = os.getenv("VOSK_MODEL_PATH", "models/vosk")
    STT_DEVICE_INDEX: str = os.getenv("STT_DEVICE_INDEX", "")
    STT_DEBUG: bool = os.getenv("STT_DEBUG", "false").lower() in {"1", "true", "yes", "on"}
    # Listening timeout - how long to wait for speech to start
    STT_TIMEOUT: float = float(os.getenv("STT_TIMEOUT", "12.0"))
    # Max length of a single phrase - increased for long dictation
    STT_PHRASE_TIME_LIMIT: float = float(os.getenv("STT_PHRASE_TIME_LIMIT", "25.0"))
    # Enable audio feedback beeps for listening states
    STT_AUDIO_FEEDBACK: bool = os.getenv("STT_AUDIO_FEEDBACK", "true").lower() in {"1", "true", "yes", "on"}
    # Delay after action completion before next listen cycle
    STT_POST_ACTION_DELAY: float = float(os.getenv("STT_POST_ACTION_DELAY", "0.5"))
    ENABLE_SCRIPTED_DEMO: bool = os.getenv("ENABLE_SCRIPTED_DEMO", "false").lower() in {"1", "true", "yes", "on"}
    # Cursor movement speed tuning (seconds for moveTo animations). Lower is faster.
    CURSOR_MOVE_DURATION: float = float(os.getenv("CURSOR_MOVE_DURATION", "0.06"))
    # Force-start the voice listener unless explicitly disabled.
    AUTO_START_VOICE_LISTENER: bool = os.getenv("AUTO_START_VOICE_LISTENER", "true").lower() in {"1", "true", "yes", "on"}
    # When no interactive console exists (e.g., packaged EXE), launch the textbox UI automatically.
    AUTO_TEXTBOX_IF_NO_CONSOLE: bool = os.getenv("AUTO_TEXTBOX_IF_NO_CONSOLE", "false").lower() in {"1", "true", "yes", "on"}


settings = Settings()
