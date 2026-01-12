import threading
import time
import queue
from typing import Optional

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None

import os
import requests
from .nlu import interpret
from .conversation import ConversationMemory
from .tts import speak
from .actions import execute_action


def _notify(message: str) -> None:
    """Speak asynchronously if possible and also print to console."""
    try:
        from .tts import speak_async
        try:
            speak_async(message)
        except Exception:
            pass
    except Exception:
        pass
    try:
        print(message)
    except Exception:
        pass


# Remaster orchestration server configuration. If REMASTER_SERVER_URL is set
# the overlay will try to POST commands to that server and process the returned
# plan. If the server is unreachable the overlay falls back to the local
# interpret/execute pipeline to preserve original behavior.
REMASTER_SERVER_URL = os.environ.get("REMASTER_SERVER_URL", "http://127.0.0.1:8000")
REMASTER_API_KEY = os.environ.get("REMASTER_API_KEY")


def _post_command_to_remaster(text: str):
    """POST a command to the remaster orchestration and return plan dict on success.

    Returns None if the server is unreachable or returned a non-ok result.
    """
    if not REMASTER_SERVER_URL:
        return None
    url = REMASTER_SERVER_URL.rstrip("/") + "/api/command"
    headers = {"Content-Type": "application/json"}
    if REMASTER_API_KEY:
        headers["x-api-key"] = REMASTER_API_KEY
    try:
        r = requests.post(url, json={"text": text}, headers=headers, timeout=4)
        if r.status_code == 200:
            j = r.json()
            # If remaster accepted the command it returns {ok: True, plan: {...}}
            if j.get("ok") and isinstance(j.get("plan"), dict):
                return j.get("plan")
    except Exception:
        pass
    return None


def _safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        pass


class OverlayApp:
    def __init__(self):
        if tk is None:
            raise RuntimeError("tkinter is not available on this system")
        self.root = tk.Tk()
        self.root.title("SNG FIND")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.92)
        except Exception:
            pass

        self.width = 900
        self.height = 90
        self._place_window()

        canvas = tk.Canvas(self.root, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        bg = "#111217"
        fg = "#E6EEF8"

        w = self.width
        h = self.height
        canvas.create_rectangle(6, 6, w - 6, h - 6, fill="#000000", outline="", stipple="gray50")
        canvas.create_rectangle(0, 0, w, h, fill=bg, outline="", width=0)

        frm = ttk.Frame(self.root)
        frm.place(relx=0.02, rely=0.12, relwidth=0.94, relheight=0.76)

        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(frm, textvariable=self.entry_var, font=("Segoe UI", 14), bg="#0f1720", fg=fg, insertbackground=fg, relief="flat")
        self.entry.pack(side="left", fill="both", expand=True, padx=(10, 8), pady=10)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<FocusIn>", lambda e: self._clear_placeholder())
        self.entry.bind("<FocusOut>", lambda e: self._set_placeholder())

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(side="right", padx=(0, 6), pady=8)

        self.btn_send = tk.Button(btn_frame, text="Send", command=lambda: self._on_enter(None), bg="#1F6FEB", fg=fg, relief="flat")
        self.btn_send.pack(side="top", padx=4, pady=2, fill="x")

        self.btn_observe = tk.Button(btn_frame, text="Observe", command=self._on_observe, bg="#16202A", fg=fg, relief="flat")
        self.btn_observe.pack(side="top", padx=4, pady=2, fill="x")

        self.btn_quit = tk.Button(btn_frame, text="Quit", command=self._on_quit, bg="#2B2B2B", fg=fg, relief="flat")
        self.btn_quit.pack(side="top", padx=4, pady=2, fill="x")

        self.lbl = tk.Label(self.root, text="", anchor="w", bg=bg, fg=fg, font=("Segoe UI", 10))
        self.lbl.place(relx=0.03, rely=0.78, relwidth=0.94)

        self._placeholder = 'Type a command, e.g. "open notepad" or "send hi to mummy"'
        self._set_placeholder()

        try:
            self._animate_in()
        except Exception:
            pass

        self._q = queue.Queue()
        self.memory = ConversationMemory()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _set_placeholder(self):
        try:
            if not (self.entry_var.get() or "").strip():
                self.entry_var.set(self._placeholder)
                try:
                    self.entry.config(fg="#8b94a3")
                except Exception:
                    pass
        except Exception:
            pass

    def _clear_placeholder(self):
        try:
            if (self.entry_var.get() or "") == self._placeholder:
                self.entry_var.set("")
                try:
                    self.entry.config(fg="#E6EEF8")
                except Exception:
                    pass
        except Exception:
            pass

    def _animate_in(self):
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = max(0, int((sw - self.width) / 2))
            target_y = max(0, sh - self.height - 40)
            start_y = sh + 10
            steps = 10
            for i in range(steps):
                y = int(start_y - (start_y - target_y) * (i + 1) / steps)
                self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
                self.root.update()
                time.sleep(0.02)
        except Exception:
            pass

    def _place_window(self):
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = max(0, int((sw - self.width) / 2))
            y = max(0, sh - self.height - 40)
            self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        except Exception:
            pass

    def _on_enter(self, ev=None):
        try:
            text = (self.entry.get() or "").strip()
            if not text:
                return
            self.entry.delete(0, "end")
            _safe_print(f"You: {text}")
            try:
                self.memory.add_user(text)
            except Exception:
                try:
                    self.memory = ConversationMemory()
                    self.memory.add_user(text)
                except Exception:
                    pass
            try:
                self._q.put(("cmd", text))
                _safe_print(f"[overlay] queued command: {text}")
            except Exception as e:
                _safe_print(f"[overlay] failed to queue command: {e}")
        except Exception as e:
            _safe_print(f"Overlay _on_enter error: {e}")
            try:
                self._show_message(f"Error: {e}")
            except Exception:
                pass

    def _on_observe(self):
        self._q.put(("observe", None))

    def _on_quit(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def _worker_loop(self):
        while True:
            try:
                typ, payload = self._q.get()
                _safe_print(f"[overlay worker] dequeued: {typ}, payload={payload}")

                if typ == "cmd":
                    text = payload
                    # First try to send to remaster orchestration (if configured).
                    plan = None
                    try:
                        plan = _post_command_to_remaster(text)
                        if plan is not None:
                            _safe_print(f"[overlay worker] plan (remote): {plan}")
                    except Exception:
                        plan = None
                    if plan is None:
                        try:
                            plan = interpret(text, memory=self.memory)
                            _safe_print(f"[overlay worker] plan (local): {plan}")
                        except Exception as e:
                            try:
                                import traceback
                                traceback.print_exc()
                            except Exception:
                                pass
                            _safe_print(f"[overlay worker] interpret error: {e}")
                            plan = {"response": "", "actions": []}

                    resp = plan.get("response") or ""
                    if resp:
                        _notify(resp)
                        try:
                            self.memory.add_assistant(resp)
                        except Exception:
                            pass

                    actions = plan.get("actions", []) or []
                    _safe_print(f"[overlay worker] actions type={type(actions)} len={len(actions)}")

                    for act in list(actions):
                        try:
                            _safe_print(f"[overlay worker] executing action: {act}")
                            result = execute_action(act)
                            _safe_print(f"[overlay worker] action result: {result}")
                            say = result.get("say") if isinstance(result, dict) else None
                            if say:
                                _notify(say)
                                try:
                                    self.memory.add_assistant(say)
                                except Exception:
                                    pass
                        except Exception as e:
                            try:
                                import traceback
                                traceback.print_exc()
                            except Exception:
                                pass
                            _safe_print(f"[overlay worker] action exception: {e}")

                    _notify("Task completed.")
                    self._show_message(resp or "Done")

                elif typ == "observe":
                    try:
                        from .screen import describe_screen
                        desc = describe_screen()
                    except Exception as e:
                        desc = f"Unable to describe screen: {e}"
                    _safe_print(desc or "No description")
                    self._show_message(desc or "No description")
                    try:
                        _notify(desc or "No description")
                    except Exception:
                        pass
            except Exception:
                time.sleep(0.1)

    def _show_message(self, text: Optional[str]):
        try:
            def setter():
                self.lbl.config(text=(text or "")[:200])
                self.root.after(6000, lambda: self.lbl.config(text=""))

            self.root.after(0, setter)
        except Exception:
            pass

    def run(self):
        try:
            self.entry.focus_force()
        except Exception:
            pass
        try:
            threading.Thread(target=lambda: _notify("Hi, I'm S N G Find. Type a command and I'll do it for you."), daemon=True).start()
        except Exception:
            pass
        try:
            self.root.bind("<Escape>", lambda e: self._on_quit())
        except Exception:
            pass
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            try:
                self.root.destroy()
            except Exception:
                pass


def start_overlay():
    if tk is None:
        print("tkinter not available; cannot start overlay")
        return
    app = OverlayApp()
    try:
        from .overlay_stt import attach_mic
        try:
            attach_mic(app)
        except Exception:
            pass
    except Exception:
        pass
    app.run()
