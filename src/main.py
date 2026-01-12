"""Kypzer desktop assistant console entry point with optional voice input.

IMPROVEMENTS:
- Robust voice listener thread with auto-recovery on crash
- Proper memory cleanup between commands
- Synchronization fixes to keep voice listening active
- Better error handling and logging
- Memory state management for continuous operation
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from src.assistant.config import settings
from src.assistant.conversation import ConversationMemory
from src.assistant.nlu import interpret as _nlu_interpret

try:
    from src.assistant.actions import execute_action  # type: ignore
except Exception as exc: 
    logging.warning(f"Failed to import execute_action: {exc}. Actions will be disabled.")
    execute_action = None  # type: ignore

logger = logging.getLogger(__name__)


def interpret(user_text: str, memory: Optional[ConversationMemory] = None) -> Dict[str, Any]:
    """Public interpret shim that keeps compatibility with existing tooling."""

    return _nlu_interpret(user_text, memory=memory)


def _friendly_action_summary(action: Dict[str, Any]) -> Optional[str]:
    action_type = (action.get("type") or "").lower()
    params = action.get("parameters") or {}

    if not action_type:
        return None

    if action_type == "whatsapp_send":
        target = params.get("contact") or params.get("to") or "your contact"
        message = params.get("message")
        if message:
            return f"Sending '{message}' to {target}."
        return f"Sending a WhatsApp message to {target}."

    if action_type == "whatsapp_paste_send":
        target = params.get("contact") or params.get("to") or "your contact"
        return f"Sending clipboard contents to {target} on WhatsApp."

    if action_type == "whatsapp_call":
        target = params.get("contact") or params.get("to") or "your contact"
        return f"Calling {target} on WhatsApp."

    if action_type in {"whatsapp_call_and_tell", "whatsapp_call_tell", "whatsapp_call_say"}:
        target = params.get("contact") or params.get("to") or "your contact"
        message = params.get("message") or params.get("text")
        if message:
            return f"Calling {target} on WhatsApp to say '{message}'."
        return f"Calling {target} on WhatsApp and relaying your message."

    if action_type == "whatsapp_ai_compose_send":
        contacts = params.get("contacts") or [params.get("contact")]
        topic = params.get("topic") or params.get("topic_raw")
        if contacts and topic:
            joined = ", ".join(str(c) for c in contacts if c)
            return f"Drafting AI message on '{topic}' for {joined}."
        return "Drafting an AI WhatsApp message."

    if action_type in {"whatsapp_voice_message", "whatsapp_voice_note", "whatsapp_voice_record"}:
        target = params.get("contact") or params.get("to") or "your contact"
        message = params.get("message") or params.get("text")
        if message:
            return f"Recording a WhatsApp voice note for {target} saying '{message}'."
        return f"Recording a WhatsApp voice note for {target}."

    if action_type == "screen_describe":
        return "Describing the current screen."

    if action_type == "settings":
        name = params.get("name") or "the requested"
        return f"Opening {name} settings."

    if action_type == "search":
        query = params.get("query") or params.get("text") or "your query"
        browser = params.get("browser")
        prefix = f"in {browser} " if browser else ""
        return f"Searching {prefix}for '{query}'."

    if action_type == "open":
        target = params.get("target") or params.get("url") or params.get("path")
        if target:
            return f"Opening {target}."
        return "Opening the requested item."

    if action_type == "open_app_start":
        name = params.get("name") or "that app"
        return f"Launching {name} from the Start menu."

    if action_type == "play_song":
        song = params.get("song") or params.get("text") or "that track"
        return f"Playing {song}."

    if action_type == "volume":
        if params.get("mute") is True:
            return "Muting the system volume."
        if params.get("mute") is False:
            return "Unmuting the system volume."
        level = params.get("percent") or params.get("level")
        if level is not None:
            return f"Setting volume to {level}%."
        delta = params.get("delta")
        if isinstance(delta, (int, float)):
            direction = "up" if delta > 0 else "down"
            return f"Turning volume {direction}."
        return "Adjusting the volume."

    if action_type == "brightness":
        level = params.get("level")
        if level is not None:
            return f"Setting brightness to {level}%."
        return "Adjusting the brightness."

    if action_type in {"wifi", "bluetooth"}:
        state = params.get("state")
        if state:
            return f"Turning {action_type} {state}."
        return f"Adjusting {action_type}."

    if action_type == "qs_toggle":
        name = params.get("name") or "that quick setting"
        state = params.get("state") or params.get("desired_state")
        if state:
            return f"Switching {name} {state}."
        return f"Toggling {name}."

    if action_type == "power":
        mode = params.get("mode") or "the requested"
        return f"Executing power action: {mode}."

    if action_type == "ai_write_notepad":
        topic = params.get("topic") or "that topic"
        return f"Drafting notes about {topic} in Notepad."

    if action_type == "hotkey":
        keys = params.get("keys") or params.get("combo") or "those keys"
        return f"Pressing hotkey {keys}."

    if action_type == "hotkey_loop":
        keys = params.get("keys") or "those keys"
        return f"Looping hotkey {keys}."

    if action_type == "start_teaching":
        task = params.get("task_name") or "that task"
        return f"Entering learning mode for {task}."

    if action_type == "stop_teaching":
        return "Wrapping up the teaching session."

    if action_type == "do_learned_task":
        task = params.get("task") or "the learned task"
        return f"Running the learned task: {task}."

    if action_type == "list_learned_tasks":
        return "Listing learned tasks."

    if action_type == "empty_recycle_bin":
        return "Emptying the Recycle Bin."

    if action_type == "instagram_check_notifications":
        return "Checking Instagram notifications."

    if action_type == "task_add":
        desc = params.get("description") or params.get("title") or "a new task"
        due = params.get("due") or params.get("when")
        due_text = f" (due {due})" if due else ""
        return f"Recording task: {desc}{due_text}."

    if action_type == "task_list":
        return "Listing your tasks."

    if action_type in {"task_complete", "task_done"}:
        target = params.get("title") or params.get("id") or params.get("keyword") or "that task"
        return f"Marking {target} complete."

    if action_type == "task_clear_completed":
        return "Clearing completed tasks."

    if action_type in {"quick_note", "note_capture"}:
        snippet = params.get("text") or params.get("note") or params.get("idea") or "that idea"
        return f"Saving a quick note: {snippet}."

    if action_type in {"focus_start", "focus_session_start"}:
        label = params.get("label") or params.get("task") or "focus"
        minutes = params.get("minutes") or params.get("duration") or params.get("seconds")
        suffix = f" for {minutes}" if minutes else ""
        return f"Starting {label} focus session{suffix}."

    if action_type in {"focus_stop", "focus_session_stop"}:
        return "Wrapping up the current focus session."

    if action_type in {"focus_status", "focus_session_status"}:
        return "Checking focus timer status."

    if action_type == "daily_briefing":
        return "Preparing a daily briefing."

    if action_type in {"cleanup_temp", "cleanup_junk", "cleanup_files"}:
        return "Cleaning temporary and junk files."

    if action_type in {"habit_create", "habit_add", "habit_update"}:
        name = params.get("name") or "that habit"
        return f"Tracking habit {name}."

    if action_type in {"habit_log", "habit_checkin"}:
        name = params.get("name") or "that habit"
        return f"Logging progress for {name}."

    if action_type == "habit_status":
        return "Summarizing habit streaks."

    if action_type == "habit_reset":
        name = params.get("name") or "that habit"
        return f"Clearing history for {name}."

    if action_type in {"routine_create", "routine_save"}:
        name = params.get("name") or "that routine"
        return f"Saving routine {name}."

    if action_type == "routine_list":
        return "Listing saved routines."

    if action_type in {"routine_run", "routine_start"}:
        name = params.get("name") or "your routine"
        return f"Running routine {name}."

    if action_type == "routine_delete":
        name = params.get("name") or "that routine"
        return f"Deleting routine {name}."

    if action_type == "system_health":
        return "Collecting a system health snapshot."

    if action_type == "system_health_watch":
        return "Monitoring system health over time."

    if action_type == "clipboard_save":
        return "Saving the current clipboard snippet."

    if action_type == "clipboard_list":
        return "Listing clipboard history."

    if action_type == "clipboard_search":
        keyword = params.get("keyword") or "that term"
        return f"Searching snippets for {keyword}."

    if action_type == "clipboard_restore":
        return "Restoring a saved clipboard snippet."

    return None


def _stop_tts_safe() -> None:
    try:  # pragma: no cover
        from src.assistant.tts import stop as _tts_stop
        _tts_stop()
    except Exception:
        pass


def _start_voice_listener(handler, should_continue) -> Optional[threading.Thread]:
    """Start voice listener with robust error handling and auto-recovery."""
    allowed_modes = {"voice", "hybrid", "both"}
    if settings.INPUT_MODE not in allowed_modes:
        if not settings.AUTO_START_VOICE_LISTENER:
            return None
        logger.info(
            "Auto-starting voice listener (INPUT_MODE=%s, AUTO_START_VOICE_LISTENER=on)",
            settings.INPUT_MODE,
        )

    try:
        from src.assistant import stt as _stt
    except Exception as exc:
        logger.warning("Voice mode requested but STT module failed to load: %s", exc)
        return None

    def _listener_loop() -> None:
        """Continuous listening loop with automatic recovery from crashes."""
        backoff_seconds = 0.5
        crash_count = 0
        max_consecutive_crashes = 5

        while True:
            try:
                if callable(should_continue) and not should_continue():
                    logger.info("Voice listener exiting gracefully")
                    break

                logger.debug("Starting continuous listen...")
                _stt.continuous_listen(handler, should_continue=should_continue)
                crash_count = 0

            except Exception as exc:
                crash_count += 1
                logger.warning(
                    "Voice listener crashed (attempt %s/%s): %s",
                    crash_count,
                    max_consecutive_crashes,
                    exc,
                )
                logger.debug(traceback.format_exc())

                if crash_count >= max_consecutive_crashes:
                    logger.error("Too many consecutive voice listener crashes. Stopping listener.")
                    break

            if callable(should_continue) and not should_continue():
                logger.info("Voice listener exiting after backoff")
                break

            wait_time = (
                min(backoff_seconds * (2 ** (crash_count - 1)), 4.0)
                if crash_count > 0
                else 0.5
            )
            logger.debug("Backoff wait: %ss", wait_time)
            time.sleep(wait_time)

    thread = threading.Thread(target=_listener_loop, daemon=True, name="VoiceListener")
    thread.start()
    logger.info("Voice listener thread started")
    return thread


def _format_actions_for_log(actions: Iterable[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for act in actions:
        act_type = act.get("type")
        params = act.get("parameters", {})
        parts.append(f"{act_type}: {params}")
    return "; ".join(parts)


def main() -> None:  # pragma: no cover
    """Main entry point for Kypzer assistant."""
    memory = ConversationMemory()
    output_mode = os.environ.get("ASSISTANT_OUTPUT_MODE", "both").lower()
    auto_exec = os.environ.get("ASSISTANT_AUTO_EXECUTE", "1").lower() in {"1", "true", "yes", "on"}
    voice_verbosity = os.environ.get("ASSISTANT_VOICE_VERBOSITY", "normal").lower()
    proactive_seconds = int(os.environ.get("ASSISTANT_PROACTIVE_SECONDS", "120"))
    proactive_prompt = os.environ.get(
        "ASSISTANT_PROACTIVE_PROMPT",
        "Hey, need anything? Try saying 'describe my screen' or 'send hi to mom'.",
    )

    exit_event = threading.Event()
    command_lock = threading.Lock()
    last_activity = datetime.now()

    ui_feedback: Dict[str, Optional[Any]] = {"fn": None}

    def _set_ui_feedback(fn: Optional[Any]) -> None:
        ui_feedback["fn"] = fn

    def _notify(message: str, *, speak: bool = True, emotion: Optional[str] = None) -> None:
        text = str(message or "").strip()
        if not text:
            return

        if output_mode != "voice":
            try:
                print(f"Kypzer: {text}")
            except Exception:
                pass

        fn = ui_feedback.get("fn")
        if fn:
            try:
                fn(text)
            except Exception:
                pass

        if not speak or voice_verbosity == "silent":
            return

        try:
            from src.assistant.tts import speak_async
            try:
                if emotion:
                    speak_async(text, emotion=emotion)
                else:
                    speak_async(text)
            except TypeError:
                speak_async(text)
        except Exception:
            pass

    def _log_assistant_response(text: str) -> None:
        if not text:
            return
        try:
            memory.add_assistant(text)
        except Exception:
            pass

    def _log_user_input(text: str) -> None:
        if not text:
            return
        try:
            memory.add_user(text)
        except Exception:
            pass

    def _is_exit_command(raw: str) -> bool:
        lowered = raw.strip().lower()
        if lowered in {"exit", "quit", "q", "bye", "goodbye"}:
            return True
        prefixes = ("exit ", "quit ", "bye ", "goodbye ")
        return any(lowered.startswith(prefix) for prefix in prefixes)

    def _proactive_loop() -> None:
        nonlocal last_activity
        while not exit_event.is_set():
            time.sleep(proactive_seconds)
            if exit_event.is_set():
                break
            idle_seconds = (datetime.now() - last_activity).total_seconds()
            if idle_seconds >= proactive_seconds:
                _notify(f"(proactive) {proactive_prompt}", speak=voice_verbosity != "silent")

    def process_command(raw: str, *, origin: str = "text") -> None:
        """Process a single user command from any input source."""
        nonlocal last_activity

        request = (raw or "").strip()
        if not request:
            return

        with command_lock:
            last_activity = datetime.now()
            _log_user_input(request)
            logger.info("Processing command from %s: %s", origin, request)

            if _is_exit_command(request):
                if not exit_event.is_set():
                    _notify("Powering down. Call me when duty calls again!", emotion="friendly")
                    exit_event.set()
                    _stop_tts_safe()
                return

            try:
                plan = interpret(request, memory=memory)
            except Exception as exc:
                logger.exception("interpret() failed for: %s", request, exc_info=exc)
                _notify("I ran into an error while understanding that command.")
                return

            response = plan.get("response") or ""
            if response:
                _notify(response, emotion="friendly")
                _log_assistant_response(response)

            actions = plan.get("actions") or []
            if actions:
                logger.info("Planned actions: %s", _format_actions_for_log(actions))
            else:
                logger.debug("No actions planned for this command")
                return

            for action in actions:
                summary = _friendly_action_summary(action)
                if summary:
                    _notify(summary, speak=False)
                try:
                    logger.debug("Planned action: %s", action)
                except Exception:
                    pass

            if execute_action and auto_exec:
                for action in actions:
                    try:
                        summary = _friendly_action_summary(action)
                        if summary:
                            _notify(summary, speak=False)

                        result = execute_action(action)  # type: ignore[arg-type]
                        if isinstance(result, dict):
                            say = result.get("say") or result.get("message")
                            if say:
                                _notify(say)
                                _log_assistant_response(say)
                        elif isinstance(result, str) and result:
                            _notify(result)
                            _log_assistant_response(result)

                    except Exception as exc:
                        logger.exception("execute_action() failed", exc_info=exc)
                        _notify(f"Action error: {exc}")

            logger.info("Command processing complete")

    # Start Task Scheduler
    try:
        from src.assistant.task_scheduler import start_scheduler, stop_scheduler
        start_scheduler(executor=execute_action)
        logger.info("Task Scheduler started")
    except Exception as exc:
        logger.warning("Failed to start Task Scheduler: %s", exc)
        stop_scheduler = None

    proactive_thread = threading.Thread(target=_proactive_loop, daemon=True, name="ProactiveReminder")
    proactive_thread.start()

    have_console_input = bool(getattr(sys.stdin, "isatty", lambda: False)())
    use_textbox_ui = settings.UI_MODE == "textbox" or (not have_console_input and settings.AUTO_TEXTBOX_IF_NO_CONSOLE)

    print("=" * 60)
    print("Kypzer Assistant - Continuous Voice & Text Mode")
    print("=" * 60)
    if not use_textbox_ui:
        print("Console mode: Type commands or speak naturally")
        print("Commands: 'exit', 'quit', 'bye', 'goodbye'")
    else:
        print("Textbox mode: A floating window will appear for input")
        print("Say or type: 'exit' to quit")
    print("=" * 60)

    # Create a single-thread executor to process voice commands serially in the background,
    # so the listening loop is never blocked by execution.
    from concurrent.futures import ThreadPoolExecutor
    voice_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="VoiceWorker")

    def _voice_handler(text: str) -> None:
        """Handle voice input from STT module non-blocking."""
        if exit_event.is_set():
            return

        cleaned = (text or "").strip()
        if not cleaned:
            return

        try:
            print(f"\n[Voice Input]: {cleaned}")
        except Exception:
            pass

        # Submit to background worker so listener can resume immediately
        voice_executor.submit(process_command, cleaned, origin="voice")

        if not exit_event.is_set():
            try:
                sys.stdout.write("\nYou: ")
                sys.stdout.flush()
            except Exception:
                pass

    def _voice_should_continue() -> bool:
        """Check if voice listener should continue."""
        return not exit_event.is_set()

    voice_thread = _start_voice_listener(_voice_handler, _voice_should_continue)
    if voice_thread:
        print("\n[✓] Voice input enabled - speak naturally!")
        print("[✓] Commands will appear and execute below\n")
    else:
        print("\n[✗] Voice input unavailable - console mode only\n")

    try:
        from src.assistant.tts import speak_async
        threading.Thread(
            target=lambda: speak_async("Howdy! Kypzer is online. What should I tackle?", emotion="friendly"),
            daemon=True,
        ).start()
    except Exception:
        _notify("Howdy! Kypzer is online. What should I tackle?", speak=False)

    def _run_console_loop() -> None:
        while not exit_event.is_set():
            try:
                user_text = input("You: ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            # Console commands are also processed (blocking console input, which is fine)
            process_command(user_text, origin="text")

    def _run_textbox_loop() -> None:
        try:
            from src.assistant.top_textbox import TopTextboxApp
        except Exception as exc:
            logger.warning("Textbox UI unavailable: %s", exc)
            _notify("Textbox UI is unavailable on this system. Falling back to console mode.", speak=False)
            _run_console_loop()
            return

        closed = threading.Event()

        def _on_cmd(text: str) -> None:
            # Textbox also non-blocking
            voice_executor.submit(process_command, text, origin="textbox")

        def _on_close() -> None:
            if not exit_event.is_set():
                exit_event.set()
            closed.set()

        app = TopTextboxApp(on_command=_on_cmd, on_close=_on_close)
        _set_ui_feedback(app.show_assistant)

        def _watch_exit() -> None:
            exit_event.wait()
            try:
                app.request_close()
            except Exception:
                pass

        threading.Thread(target=_watch_exit, daemon=True).start()
        app.run()
        closed.wait(timeout=1.0)
        _set_ui_feedback(None)

    if use_textbox_ui:
        _run_textbox_loop()
    else:
        _run_console_loop()

    logger.info("Main loop exiting, cleaning up...")
    exit_event.set()
    _stop_tts_safe()
    voice_executor.shutdown(wait=False)

    if voice_thread is not None:
        logger.info("Waiting for voice listener thread to finish...")
        voice_thread.join(timeout=2.0)
        if voice_thread.is_alive():
            logger.warning("Voice listener thread did not exit cleanly")

    print("\nGoodbye!")
    logger.info("Kypzer assistant shutdown complete")


if __name__ == "__main__":  # pragma: no cover - manual invocation entry point
    main()
