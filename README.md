# Kypzer - AI PC Controller

**Kypzer** is a modular, voice-activated desktop assistant for Windows. It combines offline speech recognition (Vosk), LLM-powered natural language understanding (Gemini/OpenAI), and extensive system automation (PyAutoGUI, UIAutomation) to control your PC, manage productivity, and interact with applications like WhatsApp and Spotify.

##  Features

*   **Voice & Text Input**: Seamlessly switch between voice commands (offline or online) and typing.
*   **Natural Language Understanding**: Uses LLMs to interpret complex intents (e.g., "Draft a message to mom about dinner and send it on WhatsApp").
*   **System Control**: Manage volume, brightness, Wi-Fi, Bluetooth, and power settings.
*   **App Automation**:
    *   **WhatsApp**: Send messages, voice notes, and make calls.
    *   **Spotify**: Play specific songs, control playback (next/prev/pause).
    *   **Browsing**: Search Google/YouTube, open URLs, and interact with results.
    *   **Applications**: Launch/close apps, manage windows, and uninstall software.
*   **Productivity**:
    *   **Note Taking**: AI-drafted notes saved to Notepad.
    *   **Task Management**: Create todos, set reminders, and manage focus sessions.
    *   **Scheduler**: Schedule tasks to run later (e.g., "Shutdown in 30 minutes").
*   **Offline Capability**: Includes offline Speech-to-Text (STT) via Vosk for privacy and reliability.

##  Installation

1.  **Clone the Repository**:
    \\\ash
    git clone https://github.com/yashraj-ghemud/kypzer.git
    cd kypzer
    \\\

2.  **Install Dependencies**:
    \\\ash
    pip install -r requirements.txt
    \\\

3.  **System Requirements (Windows)**:
    *   Python 3.10+
    *   **Visual C++ Redistributable** (needed for some audio libraries).
    *   **Microphone** (for voice features).

4.  **Setup Offline Model**:
    Run the setup script to download the minimal Vosk model:
    \\\ash
    python tools/setup_vosk.py
    \\\

##  Configuration

Create a \.env\ file in the root directory:

\\\env
# Required for AI Features
GEMINI_API_KEY=your_gemini_key_here
# OR
OPENAI_API_KEY=your_openai_key_here

# Optional Configuration
INPUT_MODE=both              # text, voice, or both
UI_MODE=console              # console or textbox
WAKE_WORD=hey buddy
ASSISTANT_VOICE_LANG=en
\\\

##  Usage

Run the assistant module:

\\\ash
python -m src.main
\\\

##  Project Structure

*   \src/main.py\: Application entry point.
*   \src/assistant/nlu.py\: Parsing and intent recognition engine.
*   \src/assistant/actions.py\: Action dispatcher (routes commands to handlers).
*   \src/assistant/stt.py\: Speech-to-Text logic (Google SR + Vosk fallback).
*   \src/assistant/ui.py\: Low-level GUI automation (PyAutoGUI/UIA).
*   \models/\: Directory for offline ML models.
*   \	ools/\: Utility scripts for testing and setup.

##  Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

##  License

[MIT License](LICENSE)
