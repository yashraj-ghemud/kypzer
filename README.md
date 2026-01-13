# 🎙️ Kypzer - Your Intelligent Windows Voice Assistant

<div align="center">

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-Active-success)

**Control your entire Windows PC with natural voice commands in multiple languages!**

[Features](#-key-features) • [Installation](#-installation) • [Commands](#-voice-commands) • [Configuration](#%EF%B8%8F-configuration)

</div>

---

## 🎯 Problem Statement

Modern PC users face several challenges:
- **Repetitive Manual Tasks**: Switching between apps, typing messages, adjusting settings manually
- **Limited Accessibility**: Traditional interfaces require precise mouse/keyboard control
- **Productivity Gaps**: No unified way to control multiple apps (WhatsApp, Spotify, system settings) through voice
- **Language Barriers**: Most assistants don't understand mixed-language conversations (Hinglish)
- **Learning Curve**: Can't teach assistants custom workflows specific to your needs

**Kypzer solves these problems** by providing a powerful, multilingual voice assistant that learns from you, automates complex workflows, and seamlessly integrates with Windows applications.

---

## 🌟 Key Features

### 🗣️ Natural Language Processing

- **Advanced NLU**: Regex patterns +intent
- **Context-Aware**: Remembers conversation history for smarter responses
- **Compound Commands**: Execute multiple tasks in one sentence

### 🤖 Smart Automation
- **WhatsApp Integration**: Send messages, AI-generated content, make calls
- **Spotify Control**: Play songs, control playback, search by voice
- **System Controls**: Volume, brightness, Wi-Fi, Bluetooth, power management
- **Browser Automation**: can Search and browse on Google/YouTube, open websites

### 🎓 Teaching & Learning
- **Record & Replay**: Teach Kypzer custom workflows by demonstration
- **Pattern Recognition**: Learns repetitive tasks automatically
- **Custom Commands**: Create your own voice-activated macros
- **Knowledge Persistence**: Saves learned patterns across sessions

### 📊 Productivity Suite
- **Task Management**: Add, list, complete tasks with voice
- **Focus Sessions**: Pomodoro-style focus timers
- **Daily Briefing**: Get your task summary on demand
- **Habit Tracking**: Monitor streaks, log progress
- **Routine Automation**: Create and run multi-step routines

### 🔧 Advanced Capabilities
- **Screen Description**: AI vision to describe what's on screen
- **AI Content Generation**: Generate notes, messages via ChatGPT/Gemini
- **Clipboard Vault**: Save and search clipboard history
- **System Health Monitoring**: CPU, RAM, disk usage reports
- **Instagram Notifications**: Check for new notifications/DMs
- **Scheduled Tasks**: Delay commands for future execution

---

## 🏗️ How It Works

```
┌─────────────────┐
│  Voice Input    │ (Microphone)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  STT Engine     │ (Vosk/SpeechRecognition)
│  Multi-language │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  NLU Pipeline   │
│  ├─ Regex       │ (Fast pattern matching)
│  ├─ SpaCy       │ (Entity extraction)
│  └─ LLM         │ (Gemini/OpenAI fallback)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Action Planner │
│  └─ Intent +    │
│     Parameters  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Action Modules │
│  ├─ WhatsApp    │
│  ├─ Spotify     │
│  ├─ System      │
│  ├─ Browser     │
│  └─ Custom      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Execution      │ (UI Automation, APIs)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  TTS Response   │ (pyttsx3)
└─────────────────┘
```

### Architecture Highlights
- **Modular Design**: Each feature is a separate module for easy maintenance
- **Fallback Chain**: Multiple NLU strategies ensure high command recognition
- **Async Operations**: Voice input runs in background thread, non-blocking UI
- **State Management**: Conversation memory maintains context across sessions
- **Error Recovery**: Robust error handling with automatic retry mechanisms

---

## 🚀 Installation

### Prerequisites
- **Windows 10/11** (64-bit)
- **Python 3.8+** (3.9 or 3.10 recommended)
- **Microphone** (for voice input)
- **Internet connection** (for AI features)

### Quick Start

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/kypzer-assistant.git
cd kypzer-assistant
```

2. **Create virtual environment**
```bash
python -m venv .venv
.venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
Create a `.env` file in the root directory:
```env
# Required for AI features
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here  # Optional

# Optional configurations
INPUT_MODE=both          # text, voice, or both
UI_MODE=console          # console or textbox
STT_BACKEND=auto         # auto, vosk, or sr
ASSISTANT_VOICE_LANG=en  # Language for TTS
```

5. **Download Vosk model** (optional, for offline STT)
```bash
python tools/setup_vosk.py
```

6. **Run the assistant**
```bash
python -m src.main
```

### Building Executable
```bash
.\build_exe.ps1
```
Output: `dist/PCController.exe`

---

## 🎤 Voice Commands

### System Controls

| Command | Action |
|---------|--------|
| `"Set volume to 50%"` | Adjust system volume |
| `"Mute/Unmute volume"` | Toggle mute |
| `"Set brightness to 80%"` | Adjust screen brightness |
| `"Turn Wi-Fi on/off"` | Control Wi-Fi |
| `"Turn Bluetooth on/off"` | Control Bluetooth |
| `"Shutdown/Restart"` | Power management |

### WhatsApp Automation

| Command | Action |
|---------|--------|
| `"Send hi to Mom"` | Send text message |
| `"Send hello to Dad and Mom"` | Multi-recipient messaging |
| `"Send AI notes on Python to Sarah"` | AI-generated message |
| `"Call John on WhatsApp"` | Voice call |
| `"Call Mike and tell him I'm late"` | Call + speak message |
| `"Record voice note saying good morning to Lisa"` | Voice message |

### Music & Media

| Command | Action |
|---------|--------|
| `"Play Senorita by Camila Cabello"` | Play on Spotify |
| `"Play my workout playlist"` | Play playlist |
| `"Stop/Pause music"` | Pause playback |
| `"Next/Previous song"` | Skip tracks |
| `"Resume music"` | Continue playback |

### Productivity

| Command | Action |
|---------|--------|
| `"Add task finish report by Friday"` | Create task |
| `"List my tasks"` | Show all tasks |
| `"Mark task 2 as done"` | Complete task |
| `"Quick note: buy milk tomorrow"` | Capture note |
| `"Start focus session for 25 minutes"` | Pomodoro timer |
| `"Daily briefing"` | Get task summary |

### Browser & Search

| Command | Action |
|---------|--------|
| `"Search for Python tutorials"` | Google search |
| `"Open GitHub in Chrome"` | Specific browser |
| `"Search cat videos on YouTube"` | YouTube search |
| `"Open first result"` | Click top search result |

### AI Features

| Command | Action |
|---------|--------|
| `"Write notes about machine learning in Notepad"` | AI-generated notes |
| `"Describe my screen"` | AI screen analysis |
| `"Send AI info on React to Tom"` | AI WhatsApp message |

### Habit Tracking

| Command | Action |
|---------|--------|
| `"Create habit exercise 5 times a day"` | New habit |
| `"Log water habit"` | Check in |
| `"Habit status"` | View streaks |

### Advanced Commands

| Command | Action |
|---------|--------|
| `"Press Ctrl+C"` | Execute hotkey |
| `"Press Alt+Tab every 5 seconds for 1 minute"` | Hotkey loop |
| `"Empty Recycle Bin"` | Clean trash |
| `"Check Instagram notifications"` | Notification check |
| `"System health report"` | CPU/RAM/disk stats |

### Teaching Custom Commands

| Command | Action |
|---------|--------|
| `"Start teaching open Excel"` | Begin recording |
| *(perform actions manually)* | Kypzer observes |
| `"Stop teaching"` | Save pattern |
| `"Do the task open Excel"` | Replay learned task |
| `"List learned tasks"` | Show all custom commands |

### Hinglish Examples
```
"Volume 50 percent kar do"
"Bluetooth band kar"
"Papa ko call kar WhatsApp pe"
"Gaana bajao - Kesariya"
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | - | Google Gemini API key |
| `OPENAI_API_KEY` | - | OpenAI API key (optional) |
| `INPUT_MODE` | `both` | `text`, `voice`, or `both` |
| `UI_MODE` | `console` | `console` or `textbox` |
| `STT_BACKEND` | `auto` | `auto`, `vosk`, or `sr` |
| `STT_LANG` | `en-IN` | Language code for STT |
| `ASSISTANT_VOICE_LANG` | `en` | TTS language |
| `STT_TIMEOUT` | `12.0` | Listening timeout (seconds) |
| `STT_PHRASE_TIME_LIMIT` | `25.0` | Max phrase duration |
| `STT_AUDIO_FEEDBACK` | `true` | Beep sounds enabled |
| `CURSOR_MOVE_DURATION` | `0.06` | UI automation speed |

### Voice Profiles

Switch voices on the fly:
```python
# In Python console or via command
"Set voice to Zira"  # Female English voice
"Set voice to David"  # Male English voice
"Set TTS profile to Hinglish"  # Hinglish optimized
```

### Advanced Settings

Edit `src/assistant/config.py`:
```python
class Settings:
    ENABLE_WAKE_WORD: bool = True
    WAKE_WORD: str = "hey kypzer"
    ACTIVE_WINDOW_SECONDS: int = 15
    SPEECH_INTERRUPTIBLE: bool = True
```

---

## 📁 Project Structure

```
pc-controller/
├── src/
│   ├── main.py                    # Entry point
│   └── assistant/
│       ├── nlu.py                 # Natural language understanding
│       ├── actions.py             # Action execution dispatcher
│       ├── tts.py                 # Text-to-speech engine
│       ├── stt.py                 # Speech-to-text engine
│       ├── llm_adapter.py         # AI integration (Gemini/OpenAI)
│       ├── ui.py                  # UI automation helpers
│       ├── browser.py             # Browser automation
│       ├── system_controls.py     # Volume, brightness, etc.
│       ├── spotify_controller.py  # Spotify integration
│       ├── productivity.py        # Tasks, notes, focus
│       ├── habit_tracker.py       # Habit monitoring
│       ├── task_scheduler.py      # Delayed tasks
│       └── viczo_learning_*.py    # Teaching/learning system
├── tests/                         # Unit tests
├── tools/                         # Utility scripts
├── models/                        # Vosk models (offline STT)
├── data/                          # Persistent data storage
├── requirements.txt               # Python dependencies
└── build_exe.ps1                  # Build script for EXE
```

---

## 🧪 Testing

Run all tests:
```bash
pytest -v
```

Run specific test file:
```bash
pytest tests/test_nlu.py -v
```

Test voice input:
```bash
python tools/run_tts_test.bat
```

---

## 🛠️ Development

### Adding New Commands

1. **Define pattern in `nlu.py`**:
```python
if "my custom command" in low:
    return {
        "response": "Executing custom command",
        "actions": [{"type": "custom_action", "parameters": {...}}]
    }
```

2. **Implement action in `actions.py`**:
```python
def execute_action(action: Dict[str, Any]) -> Dict[str, Any]:
    if atype == "custom_action":
        # Your implementation
        return {"ok": True, "say": "Done!"}
```

3. **Test**:
```bash
python tools/run_interpret.py "my custom command"
```

### Debugging

Enable debug logging:
```env
STT_DEBUG=true
```

Check NLU parsing:
```bash
python tools/smoke_interpret.py
```

---

## 🔌 Integrations

### Supported Applications
- ✅ WhatsApp Desktop
- ✅ Spotify Desktop
- ✅ Chrome/Edge/Brave/Firefox browsers
- ✅ Notepad
- ✅ Instagram (web)
- ✅ Windows Settings
- ✅ File Explorer

### AI Services
- 🤖 **Google Gemini** (primary)
- 🤖 **OpenAI GPT** (fallback)
- 🤖 **ChatGPT Web** (for note generation)

### Speech Engines
- 🎙️ **Vosk** (offline, multilingual)
- 🎙️ **SpeechRecognition** (Google/Sphinx)
- 🔊 **pyttsx3** (TTS)

---

## 🎯 Roadmap

- [ ] Linux/Mac support
- [ ] Mobile app companion
- [ ] Custom wake word training
- [ ] Calendar integration
- [ ] Email automation
- [ ] Smart home control
- [ ] Multi-user profiles
- [ ] Voice command analytics

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style
- Follow PEP 8
- Add type hints where possible
- Write docstrings for public functions
- Include tests for new features

---

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🙏 Acknowledgments

- **OpenAI** & **Google** for AI APIs
- **Vosk** for offline speech recognition
- **PyAutoGUI** for UI automation
- **pyttsx3** for text-to-speech
- All contributors and testers!

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/kypzer-assistant/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/kypzer-assistant/discussions)
- **Email**: your.email@example.com

---

<div align="center">

**Made with ❤️ by Yashraj**

*"Your voice, your command, your way."*

⭐ Star this repo if you find it helpful!

</div>
