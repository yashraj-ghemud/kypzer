import tkinter as tk
import threading
from typing import Optional, Callable


class TopTextboxApp:
    def __init__(self, on_command: Optional[Callable[[str], None]] = None, on_close: Optional[Callable[[], None]] = None):
        self.on_command = on_command
        self.on_close = on_close
        self._stt_thread: Optional[threading.Thread] = None
        self._stt_running = False

        self.root = tk.Tk()
        self.root.title("Command Entry")
        self.root.geometry("700x60+0+0")
        self.root.configure(bg="#181A20")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.resizable(False, False)

        self.frame = tk.Frame(self.root, bg="#181A20")
        self.frame.pack(fill="both", expand=True)

        self.display_var = tk.StringVar()
        self.display = tk.Label(self.frame, textvariable=self.display_var, font=("Segoe UI", 16), bg="#181A20", fg="#E6EEF8", anchor="w")
        self.display.pack(fill="x", padx=18, pady=(10, 0))

        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(self.frame, textvariable=self.entry_var, font=("Segoe UI", 16), bg="#23262F", fg="#E6EEF8", insertbackground="#E6EEF8", relief="flat")
        self.entry.pack(fill="x", padx=18, pady=(0, 10))
        self.entry.bind("<Return>", self._on_enter)
        self.entry.focus_set()
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._handle_close)
        except Exception:
            pass

        # Mic toggle button (starts/stops voice listening)
        self.mic_btn = tk.Button(self.frame, text="🎤", command=self._toggle_mic, bg="#2D313B", fg="#E6EEF8", relief="flat", font=("Segoe UI", 12))
        self.mic_btn.place(x=660, y=16, width=24, height=24)

    def _handle_close(self):
        try:
            if callable(self.on_close):
                self.on_close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _on_enter(self, event=None):
        text = self.entry_var.get().strip()
        if text:
            self.display_var.set(f"You: {text}")
            self.entry_var.set("")
            try:
                if callable(self.on_command):
                    self.on_command(text)
            except Exception:
                pass

    def show_assistant(self, message: str):
        try:
            self.display_var.set(f"Assistant: {message}")
        except Exception:
            pass

    def _toggle_mic(self):
        if not self._stt_running:
            self._start_stt_thread()
        else:
            self._stop_stt_thread()

    def _start_stt_thread(self):
        self._stt_running = True
        self.mic_btn.configure(bg="#3BA55D")  # green
        def _runner():
            try:
                from src.assistant import stt as _stt
                def _on_cmd(text: str):
                    if not text:
                        return
                    try:
                        # Update UI and forward to backend on the Tk thread
                        self.root.after(0, lambda: self.display_var.set(f"You (voice): {text}"))
                    except Exception:
                        pass
                    try:
                        if callable(self.on_command):
                            self.on_command(text)
                    except Exception:
                        pass
                def _on_wake():
                    try:
                        self.root.after(0, lambda: self.display_var.set("(listening…)"))
                    except Exception:
                        pass
                _stt.continuous_listen(on_command=_on_cmd, on_wake=_on_wake, should_continue=lambda: self._stt_running)
            except Exception:
                pass
            finally:
                # If the loop exits, reflect stopped state
                self._stt_running = False
                try:
                    self.root.after(0, lambda: self.mic_btn.configure(bg="#2D313B"))
                except Exception:
                    pass
        self._stt_thread = threading.Thread(target=_runner, daemon=True)
        self._stt_thread.start()

    def _stop_stt_thread(self):
        # cooperative stop: set flag; stt loop checks TTS stop but not a global; rely on closing app to fully stop
        self._stt_running = False
        self.mic_btn.configure(bg="#2D313B")

    def request_close(self):
        try:
            self.root.after(0, self._handle_close)
        except Exception:
            self._handle_close()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = TopTextboxApp()
    app.run()
