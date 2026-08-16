# kypzer
> A Windows-focused desktop voice assistant: modular STT → NLU → action planner → action modules → execution → TTS.

## Overview
Kypzer is a Python project that implements a voice-first (and text) assistant for Windows. The repository contains a console entrypoint (src/main.py), an AI Notepad automation workflow (src/assistant/ai_notepad_workflow.py — truncated in the supplied dossier), pinned dependencies (requirements.txt), unit tests, and tools/scripts for exercising features.

## What it does
- Accepts voice and text input and converts speech to text using Vosk or SpeechRecognition.
- Interprets intents with a layered NLU pipeline (regex → SpaCy → LLM fallback).
- Plans and executes actions through modular action modules (UI automation and API integrations).
- Produces spoken responses via pyttsx3 TTS.
- Includes features and utilities referenced in tests: AI Notepad automation, clipboard vault, routines, habit tracker, overlay UI, and uninstall dry-run diagnostics.

## Key capabilities
- Voice and text input (STT backends: Vosk / SpeechRecognition).
- Layered NLU: regex rules, SpaCy entity extraction, and LLM fallback (OpenAI / Google generative APIs).
- Action modules for WhatsApp, Spotify, system controls, and browser automation (UI automation via pyautogui, uiautomation, Playwright).
- AI Notepad workflow: multi-stage browser/LLM automation to compose and type cleaned content into Notepad.
- Teach-by-demonstration / record-and-replay custom workflows.
- Clipboard vault, routines, habit-tracking utilities (covered by unit tests).
- TTS responses using pyttsx3.

## Technology
Observed stack (from code and requirements):
- Python 3.8+
- STT: Vosk, SpeechRecognition, PyAudio
- NLU: spaCy, regex, optional LLM clients (openai, google-generativeai)
- TTS: pyttsx3
- UI and browser automation: pyautogui, uiautomation, playwright
- Clipboard and system: pyperclip, psutil, pycaw
- Vision: pytesseract, Pillow, numpy, opencv-python-headless
- Requirements are pinned in requirements.txt

## Repository structure
Relevant top-level items (selected):
- .env.example
- README.md, README_PyInstaller.md
- requirements.txt
- kypzer.spec, build_exe.ps1
- src/ (primary application code; includes src/main.py and src/assistant/)
- models/, data/
- scripts/, tools/
- tests/ (unit tests and test drivers)
- .vscode/ (local IDE tasks present)

Note: src/ contains an assistant package export (src/assistant/__init__.py) and several modules referenced across the codebase. Some files referenced in imports were not fully visible in the supplied dossier.

## Getting started
What is present for local inspection:
- requirements.txt lists pinned Python dependencies.
- .env.example is included as a starting configuration reference.
- src/main.py is the console entrypoint (loads settings, ConversationMemory, and NLU interpreter).
- src/assistant/ai_notepad_workflow.py contains a guarded, multi-stage automation flow (file in the dossier appears truncated).

If you are evaluating or contributing, inspect these files first to understand runtime and configuration: requirements.txt, .env.example, src/main.py, src/assistant/, tests/, scripts/, and tools/.

(There is no evidence in the supplied dossier of an automated CI workflow or an included installer artifact; see Development notes below.)

## Configuration
- Environment variables: a .env.example file is present; the repository references environment-based API keys for LLMs in the README and code.
- Dependencies: requirements.txt contains pinned versions for the main dependencies used by the project.
- Packager hints: README_PyInstaller.md, kypzer.spec, and build_exe.ps1 are present and indicate packaging/installer-related artifacts, but a finished installer or distribution is not evidenced.

To review configuration, open .env.example and requirements.txt and read src/main.py for how settings are loaded. The ai_notepad_workflow module is long and contains specific orchestration stages — review it for automation behavior (note: the copy supplied in the dossier is truncated).

## Development and quality notes
- There is a substantial test suite (tests/ and scripts/) covering NLU, spaCy integration, clipboard vault, routines, habit tracker, overlay, and AI Notepad cleaning. Several tests are Windows-specific and use skip guards.
- Many dependencies require native components (pyaudio, Playwright browsers, Vosk models). Those platform prerequisites are not fully captured in a reproducible automation in the supplied dossier.
- No CI / GitHub Actions workflows were included in the supplied evidence.
- Some files (tools/inspect_ui.py, .vscode/tasks.json) contain absolute local paths referenced in the audit; these affect portability.
- The dossier shows a truncated source file (src/assistant/ai_notepad_workflow.py ends mid-token) and references to modules that may be missing from the supplied excerpts; restoring or validating those files in the repository is advised before running tests.

## Safety and responsible use
- The project uses high-privilege UI automation and system-control libraries (pyautogui, uiautomation, Playwright, pycaw). These can perform clicks, keyboard input, system changes, and uninstall steps. Treat automation flows as potentially destructive; require clear confirmation before executing destructive commands.
- LLM and external API integrations (openai, google-generativeai, Spotify, WhatsApp flows) require API keys and may transmit user data. Review and restrict what is sent to external services; prefer local or mocked testing where possible.
- The repository contains no explicit secrets-management mechanism in the supplied dossier beyond .env.example. Avoid committing real API keys or secrets; use secure storage or local environment variables.

## Contributing
If you want to contribute or examine the codebase:
- Start by reading: requirements.txt, .env.example, src/main.py, src/assistant/, tests/, scripts/, and tools/.
- Validate the Python imports by opening src/main.py and tracing referenced modules (some imports may fail if files are missing or corrupted).
- Run the unit tests locally after ensuring platform prerequisites (Windows-specific behavior, Playwright browsers, and STT models) are available — the dossier does not include CI to run them automatically.
- Important repo maintenance actions suggested by the dossier:
  - Repair or restore the truncated src/assistant/ai_notepad_workflow.py.
  - Ensure modules referenced by imports (actions, nlu, conversation, etc.) are present and import without error.
  - Remove or parameterize absolute/local paths to improve portability.
  - Add a .env.example (already present) and consider documenting required environment variables and adding .gitignore guidance for secrets.

Note: The supplied dossier contains many development artifacts and tests but does not include an explicit contribution guide; follow the above file paths to begin code review and local testing.
