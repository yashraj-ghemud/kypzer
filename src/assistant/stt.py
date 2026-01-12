from typing import Optional, Callable, List, Tuple
import time
import threading
import os
import json
import sys
from .config import settings
from .tts import stop as tts_stop

_sr = None
_pyaudio = None
_sr_aifc_patched = False
_VOICE_MODES = {"voice", "hybrid", "both"}

# Audio feedback state
_AUDIO_FEEDBACK_ENABLED = True  # Can be overridden by config


def _play_beep(frequency: int = 800, duration_ms: int = 150):
    """Play a simple beep sound for audio feedback."""
    try:
        import winsound
        # Run in thread to not block
        threading.Thread(
            target=lambda: winsound.Beep(frequency, duration_ms),
            daemon=True
        ).start()
    except Exception:
        pass  # Silently fail if winsound not available


def _play_listening_start():
    """Play a short high beep to indicate listening started."""
    if not getattr(settings, 'STT_AUDIO_FEEDBACK', True):
        return
    _play_beep(880, 100)  # High pitch, short


def _play_listening_recognized():
    """Play a confirmation beep when speech is recognized."""
    if not getattr(settings, 'STT_AUDIO_FEEDBACK', True):
        return
    _play_beep(660, 80)  # Medium pitch


def _play_action_complete():
    """Play a pleasant double-beep when action completes."""
    if not getattr(settings, 'STT_AUDIO_FEEDBACK', True):
        return
    try:
        import winsound
        def _chime():
            winsound.Beep(880, 80)
            time.sleep(0.05)
            winsound.Beep(1100, 120)
        threading.Thread(target=_chime, daemon=True).start()
    except Exception:
        pass


def _play_error_beep():
    """Play a low beep to indicate an error."""
    if not getattr(settings, 'STT_AUDIO_FEEDBACK', True):
        return
    _play_beep(400, 200)  # Low pitch, longer


def _voice_status_enabled() -> bool:
    return settings.INPUT_MODE in _VOICE_MODES

def _ensure_sr():
    global _sr
    global _sr_aifc_patched
    if _sr is None:
        try:
            if not _sr_aifc_patched:
                if "aifc" not in sys.modules:
                    try:
                        import aifc  # type: ignore  # noqa: F401
                    except Exception:
                        from .stdlib_compat import aifc as compat_aifc
                        sys.modules["aifc"] = compat_aifc
                _sr_aifc_patched = True
            import speech_recognition as sr
            _sr = sr
        except Exception as exc:
            _sr = False
            if settings.STT_DEBUG:
                try:
                    print(f"[STT] Failed to import speech_recognition: {exc}", flush=True)
                except Exception:
                    pass
    return _sr

# Placeholder for future offline STT backends (e.g., Vosk)


def _ensure_pyaudio():
    """Lazy-load PyAudio if available."""
    global _pyaudio
    if _pyaudio is None:
        try:
            import pyaudio  # type: ignore
            _pyaudio = pyaudio
        except Exception:
            _pyaudio = False
    return _pyaudio


def _detect_default_input_index_pyaudio() -> Optional[int]:
    """Use PyAudio to find the default input device index or the first input-capable device.
    Returns None if PyAudio isn't available or no input device is found.
    """
    pa = _ensure_pyaudio()
    if not pa:
        return None
    try:
        pa_inst = pa.PyAudio()
    except Exception:
        return None
    try:
        try:
            info = pa_inst.get_default_input_device_info()
            if isinstance(info, dict) and "index" in info:
                idx = info.get("index")
                if isinstance(idx, int) and idx >= 0:
                    return idx
        except Exception:
            # Fall back to search
            pass
        try:
            count = pa_inst.get_device_count()
            for i in range(count):
                dev = pa_inst.get_device_info_by_index(i)
                if int(dev.get("maxInputChannels", 0)) > 0:
                    return i
        except Exception:
            pass
        return None
    finally:
        try:
            pa_inst.terminate()
        except Exception:
            pass


def _list_microphones_sr() -> List[Tuple[int, str]]:
    result: List[Tuple[int, str]] = []
    sr = _ensure_sr()
    if sr:
        try:
            names = sr.Microphone.list_microphone_names()
            for i, name in enumerate(names or []):
                result.append((i, str(name)))
        except Exception:
            pass
    return result


def _list_microphones_pyaudio() -> List[Tuple[int, str]]:
    result: List[Tuple[int, str]] = []
    pa = _ensure_pyaudio()
    if not pa:
        return result
    try:
        pa_inst = pa.PyAudio()
    except Exception:
        return result
    try:
        try:
            count = pa_inst.get_device_count()
            for i in range(count):
                try:
                    dev = pa_inst.get_device_info_by_index(i)
                    if int(dev.get("maxInputChannels", 0)) > 0:
                        name = str(dev.get("name", f"Device {i}"))
                        host = str(dev.get("hostApi", ""))
                        result.append((i, f"{name} (hostApi={host})"))
                except Exception:
                    continue
        except Exception:
            pass
    finally:
        try:
            pa_inst.terminate()
        except Exception:
            pass
    return result


def _resolve_device_index() -> Optional[int]:
    """Resolve which microphone device_index to use for SpeechRecognition.
    Priority:
    1) STT_DEVICE_INDEX env var (int)
    2) PyAudio default input device
    3) First input-capable PyAudio device
    Otherwise None to let SR pick default.
    """
    # 1) Explicit override
    try:
        if settings.STT_DEVICE_INDEX.strip():
            return int(settings.STT_DEVICE_INDEX.strip())
    except Exception:
        pass
    # 2/3) PyAudio-based detection
    idx = _detect_default_input_index_pyaudio()
    if isinstance(idx, int):
        return idx
    return None


def stt_status() -> dict:
    """Return STT availability status for SR mic and Vosk model.
    Keys: sr_available (bool), sr_mic (bool), vosk_model (bool), backend (str)
    """
    have_sr = False
    have_mic = False
    if _ensure_sr():
        have_sr = True
        try:
            # Will raise if portaudio not present or no devices
            mics = _sr.Microphone.list_microphone_names()
            have_mic = bool(mics)
        except Exception:
            have_mic = False
    resolved_idx = _resolve_device_index()
    if isinstance(resolved_idx, int):
        have_mic = True
    vosk_ok = False
    try:
        model_path = settings.VOSK_MODEL_PATH
        vosk_ok = bool(model_path and os.path.isdir(model_path))
    except Exception:
        vosk_ok = False
    status = {
        "sr_available": have_sr,
        "sr_mic": have_mic,
        "vosk_model": vosk_ok,
        "backend": settings.STT_BACKEND,
        "device_index": resolved_idx,
    }
    if settings.STT_DEBUG:
        try:
            sr_devices = _list_microphones_sr()
            pa_devices = _list_microphones_pyaudio()
            print("[STT] Status:", status, flush=True)
            if sr_devices:
                print("[STT] SR devices:", ", ".join([f"{i}:{n}" for i, n in sr_devices]), flush=True)
            if pa_devices:
                print("[STT] PyAudio devices:", ", ".join([f"{i}:{n}" for i, n in pa_devices]), flush=True)
        except Exception:
            pass
    return status


def listen_once(timeout: Optional[float] = None, phrase_time_limit: Optional[float] = None) -> Optional[str]:
    timeout = settings.STT_TIMEOUT if timeout is None else timeout
    phrase_time_limit = settings.STT_PHRASE_TIME_LIMIT if phrase_time_limit is None else phrase_time_limit
    # Prefer SR mic if available
    if settings.STT_BACKEND in {"auto", "sr"} and _ensure_sr():
        sr = _sr
        r = sr.Recognizer()
        try:
            mic_kw = {}
            resolved_idx = _resolve_device_index()
            if isinstance(resolved_idx, int):
                mic_kw["device_index"] = resolved_idx
            if _voice_status_enabled():
                print("Listening...", flush=True)
            with sr.Microphone(**mic_kw) as source:
                r.adjust_for_ambient_noise(source, duration=0.2)
                audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                try:
                    text = r.recognize_google(audio, language=settings.STT_LANG)
                    if _voice_status_enabled():
                        print(f"You: {text}", flush=True)
                    if settings.STT_DEBUG:
                        print(f"[STT] Heard: {text}", flush=True)
                    return text
                except Exception:
                    if _voice_status_enabled():
                        print("You: (not recognized)", flush=True)
                    # return None
        except Exception:
            pass
    # Fallback to Vosk offline if available and configured
    if settings.STT_BACKEND in {"auto", "vosk"}:
        try:
            import pyaudio
            from vosk import Model, KaldiRecognizer
            model_path = settings.VOSK_MODEL_PATH
            if not os.path.isdir(model_path):
                if settings.STT_DEBUG:
                    print(f"[STT] Warning: Vosk model not found at {model_path}. Offline mode unavailable.", flush=True)
                return None
            model = Model(model_path)
            rec = KaldiRecognizer(model, 16000)
            rec.SetWords(True)
            pa = pyaudio.PyAudio()
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8000)
            stream.start_stream()
            start = time.time()
            text_out = None
            while time.time() - start < phrase_time_limit:
                data = stream.read(4000, exception_on_overflow=False)
                if len(data) == 0:
                    continue
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    text_out = (res.get("text") or "").strip() or None
                    break
            stream.stop_stream()
            stream.close()
            pa.terminate()
            return text_out
        except Exception:
            return None
    return None


def continuous_listen(on_command: Callable[[str], None], on_wake: Optional[Callable[[], None]] = None, should_continue: Optional[Callable[[], bool]] = None):
    """Continuously listen for voice commands and execute them.
    
    Flow: Listen (beep) → Recognize → Execute → Complete (chime) → Listen again
    """
    import threading
    import sys
    sr = None
    if settings.STT_BACKEND == "sr":
        sr = _ensure_sr()
    wake = settings.WAKE_WORD.lower()
    active_until = 0.0
    last_said_at = 0.0
    min_gap = 0.3
    
    # Get configurable timeouts - increased for better listening
    listen_timeout = getattr(settings, 'STT_TIMEOUT', 12.0)
    phrase_limit = getattr(settings, 'STT_PHRASE_TIME_LIMIT', 25.0)  # Much longer for compound commands
    post_action_delay = getattr(settings, 'STT_POST_ACTION_DELAY', 0.5)
    
    if sr:
        # Configuration - increased timeouts
        listen_timeout = getattr(settings, 'STT_TIMEOUT', 12.0)
        phrase_limit = getattr(settings, 'STT_PHRASE_TIME_LIMIT', 25.0)  # Allow long sentences
        post_action_delay = getattr(settings, 'STT_POST_ACTION_DELAY', 0.5)
        
        # Outer loop: Handles hardware/context resets
        while True:
            if callable(should_continue) and not should_continue():
                break

            try:
                r = sr.Recognizer()
                r.energy_threshold = 300 # Default baseline
                r.dynamic_energy_threshold = False # Prevent drift

                resolved_idx = _resolve_device_index()
                mic_kw = {}
                if isinstance(resolved_idx, int):
                    mic_kw["device_index"] = resolved_idx
                
                # Context manager for Microphone
                with sr.Microphone(**mic_kw) as source:
                    # Calibration phase
                    if _voice_status_enabled():
                        print("🎤 Calibrating microphone... (Please wait)", flush=True)
                    
                    try:
                        r.adjust_for_ambient_noise(source, duration=0.8)
                        # Boost threshold slightly after calibration to avoid noise triggers
                        r.energy_threshold = max(r.energy_threshold, 300)
                    except Exception as e:
                        print(f"[STT] Calibration failed: {e}. Retrying...", flush=True)
                        time.sleep(1.0)
                        continue # Retry outer loop (re-open mic)

                    # Import TTS
                    try:
                        from . import tts
                    except ImportError:
                        tts = None
                    
                    if _voice_status_enabled():
                        print("✓ Ready! Listening for voice commands...\n", flush=True)
                    
                    consecutive_listen_errors = 0
                    
                    # Inner Loop: Continuous Listening
                    while True:
                        if callable(should_continue) and not should_continue():
                            return
                        
                        # 1. TTS Backoff
                        tts_wait_count = 0
                        while tts and getattr(tts, "is_busy", lambda: False)():
                            time.sleep(0.15)
                            tts_wait_count += 1
                            if tts_wait_count > 40: break # Max 6s wait
                        
                        if tts_wait_count > 0:
                            time.sleep(0.2) # Small gap after speaking
                        
                        try:
                            # 2. Listening Phase
                            _play_listening_start()
                            if _voice_status_enabled():
                                print("🎧 Listening...", end="\r", flush=True)
                            
                            try:
                                audio = r.listen(source, timeout=listen_timeout, phrase_time_limit=phrase_limit)
                                consecutive_listen_errors = 0 # Reset on success
                            except sr.WaitTimeoutError:
                                # Silence (normal)
                                continue
                            except Exception as e:
                                if settings.STT_DEBUG:
                                    print(f"\n[STT] Listen error: {e}", flush=True)
                                continue
                            
                            if _voice_status_enabled():
                                print("                  ", end="\r", flush=True) # Clear line

                            # 3. Recognition Phase
                            try:
                                text = r.recognize_google(audio, language=settings.STT_LANG)
                            except sr.UnknownValueError:
                                # Speech unintelligible
                                _play_error_beep()
                                continue
                            except sr.RequestError as e:
                                print(f"\n❌ Network error: {e}", flush=True)
                                _play_error_beep()
                                time.sleep(1.0) # Backoff for network
                                continue
                                
                            if not text or not text.strip():
                                continue
                                
                            # 4. Success Phase
                            _play_listening_recognized()
                            if _voice_status_enabled():
                                print(f"📝 You said: \"{text}\"", flush=True)
                            
                            # 5. Execution Phase
                            if _voice_status_enabled():
                                print("⚡ Executing...", flush=True)
                            
                            try:
                                on_command(text)
                                _play_action_complete()
                                if _voice_status_enabled():
                                    print("✅ Done!\n", flush=True)
                            except Exception as exec_err:
                                _play_error_beep()
                                print(f"❌ Execution Error: {exec_err}\n", flush=True)
                            
                            time.sleep(post_action_delay)

                        except Exception as inner_e:
                            print(f"\n[STT] Unexpected inner loop error: {inner_e}", flush=True)
                            consecutive_listen_errors += 1
                            if consecutive_listen_errors > 5:
                                print("[STT] Too many audio errors. Re-initializing microphone...")
                                break # Break to outer loop to reset mic
                            time.sleep(0.5)

            except OSError as os_err:
                print(f"[STT] Microphone hardware error: {os_err}. Retrying in 2s...", flush=True)
                time.sleep(2.0)
            except Exception as e:
                print(f"[STT] Critical error: {e}. Retrying in 2s...", flush=True)
                time.sleep(2.0)


    # Vosk streaming fallback
    if settings.STT_BACKEND in {"auto", "vosk"}:
        try:
            import pyaudio
            from vosk import Model, KaldiRecognizer
            model_path = settings.VOSK_MODEL_PATH
            if not os.path.isdir(model_path):
                print(f"[STT] Warning: Vosk model not found at {model_path}. Streaming offline mode disabled.", flush=True)
                raise RuntimeError("Vosk model not found")
            model = Model(model_path)
            rec = KaldiRecognizer(model, 16000)
            rec.SetWords(True)
            pa = pyaudio.PyAudio()
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=4000)
            stream.start_stream()
            while True:
                if callable(should_continue) and not should_continue():
                    try:
                        stream.stop_stream(); stream.close(); pa.terminate()
                    except Exception:
                        pass
                    return
                try:
                    tts_stop()
                except Exception:
                    pass
                data = stream.read(4000, exception_on_overflow=False)
                if len(data) == 0:
                    continue
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    text = (res.get("text") or "").strip()
                    if not text:
                        continue
                    now = time.time()
                    if now - last_said_at < min_gap:
                        continue
                    last_said_at = now
                    low = text
                    if settings.ENABLE_WAKE_WORD and now > active_until:
                        if wake in low:
                            active_until = now + settings.ACTIVE_WINDOW_SECONDS
                            if on_wake:
                                on_wake()
                            continue
                        else:
                            continue
                    if (not settings.ENABLE_WAKE_WORD) or (now <= active_until):
                        on_command(text)
        except Exception:
            # Fall through to polling fallback if streaming not available
            pass

    # Last-resort polling fallback: periodically call listen_once
    while True:
        if callable(should_continue) and not should_continue():
            return
        try:
            tts_stop()
        except Exception:
            pass
        text = listen_once(timeout=2.0, phrase_time_limit=6.0)
        if not text:
            continue
        now = time.time()
        if now - last_said_at < min_gap:
            continue
        last_said_at = now
        low = text.strip().lower()
        if settings.ENABLE_WAKE_WORD and now > active_until:
            if wake in low:
                active_until = now + settings.ACTIVE_WINDOW_SECONDS
                if on_wake:
                    on_wake()
                continue
            else:
                continue
        if (not settings.ENABLE_WAKE_WORD) or (now <= active_until):
            on_command(text)
