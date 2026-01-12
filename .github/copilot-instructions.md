# PC Controller - AI Assistant Instructions

## 🏗 Project Architecture & Overview
**PC Controller** is a modular Python-based Windows voice assistant that controls the PC (apps, UI, settings) via natural language.

- **Entry Point**: [`../src/main.py`](../src/main.py) initializes the app, NLU, and main loop.
- **NLU & Planning**: [`../src/assistant/nlu.py`](../src/assistant/nlu.py) interprets commands (Regex fallback or LLM via `llm_adapter`) and returns a plan: `{ "response": "OK", "actions": [...] }`.
- **Action Execution**: [`../src/assistant/actions.py`](../src/assistant/actions.py) is the central dispatcher (`execute_action`) routing abstract actions (e.g., `whatsapp_send`) to implementation handlers.
- **Configuration**: [`../src/assistant/config.py`](../src/assistant/config.py) uses `python-dotenv` and a `Settings` class.

## 🚀 Build, Run & Test Workflows
- **Run Application**: Always run as a module from root:
  `python -m src.main`
  *Do not run `python src/app.py` directly to avoid import errors.*
- **Build EXE**: Use the PowerShell script for PyInstaller builds:
  `./build_exe.ps1` -> Output in `dist/PCController.exe`.
- **Testing**:
  - Run unit tests: `pytest`
  - Granular tool tests found in `tools/` (e.g., `tools/run_tts_test.bat`, `tools/debug_volume.py`).

## 🛠 Critical Implementation Patterns
### 1. Action Dispatch Pattern
New capabilities must be registered in the **Action Dispatcher** in `../src/assistant/actions.py`.
- **Pattern**: `{"type": "my_action", "parameters": {...}}`
- **Hook**: Add `elif action_type == "my_action":` in `execute_action()` generic handler.

### 2. UI & System Automation
- **Playwright** for complex browser tasks (`../src/assistant/browser.py`).
- **PyAutoGUI/PyGetWindow** for loose desktop interactions (`../src/assistant/ui.py`).
- **Windows APIs**: System controls (volume, brightness) in `../src/assistant/system_controls.py`.

### 3. Voice & Interaction flow
- **STT**: Flexible backend (Vosk, SpeechRecognition) configured in `../src/assistant/stt.py` context.
- **TTS**: `pyttsx3` is the standard offline engine [`../src/assistant/tts.py`](../src/assistant/tts.py).
- **Conversation State**: Managed via `ConversationMemory` in `../src/assistant/conversation.py`.

## 📦 Dependencies & Environment
- **LLM**: Requires `GEMINI_API_KEY` in `.env`.
- **Audio**: `pyaudio` covers input; `pyttsx3` handles output.
- **Windows Only**: Many libraries (`pywin32`, `uiautomation`) are OS-specific.

## ⚠️ Important Implementation Rules
1. **Module Imports**: Always use absolute imports like `from src.assistant.config import settings`.
2. **Async/Threading**: Voice listening runs in a separate thread/loop; be mindful of blocking operations in the main action loop.
3. **Environment**: Check `settings.UI_MODE` or `settings.INPUT_MODE` before assuming a console or mic presence.
