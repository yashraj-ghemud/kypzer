"""Non-invasive overlay STT helper.

This module provides a single function `attach_mic(app)` which will add a small
microphone button to an existing OverlayApp instance (from `overlay.py`). It
uses the project's existing `stt.listen_once` function so no new STT backend is
introduced. All operations are done in background threads and UI updates are
safely scheduled on the Tk main thread via `after`.

This file is additive and does not modify existing overlay behaviour unless
`attach_mic` is called. The overlay will continue to work if speech modules are
not available.
"""
from typing import Optional
import threading

try:
    import tkinter as tk
except Exception:
    tk = None

def _default_listen(timeout: float = 5.0, phrase_time_limit: float = 8.0) -> Optional[str]:
    """Small wrapper to call the project's STT `listen_once` if present.
    Returns recognized text or None.
    """
    try:
        from .stt import listen_once
        return listen_once(timeout=timeout, phrase_time_limit=phrase_time_limit)
    except Exception:
        return None


def attach_mic(app) -> None:
    """Attach a microphone button to the given OverlayApp instance.

    Expectations about the `app` object:
    - has attributes: `root` (tk.Tk), `entry_var` (tk.StringVar) and `entry` (tk.Entry)
    - has attributes `btn_quit` or `btn_observe` so we can place the mic near them

    This function is safe to call multiple times; it will add a button only if
    a widget named `_mic_button` is not already present under the same parent.
    """
    if tk is None:
        return
    if not hasattr(app, 'root') or not hasattr(app, 'entry_var') or not hasattr(app, 'entry'):
        return

    # Determine parent frame for the small button. Prefer the right-side button frame
    parent = None
    try:
        parent = getattr(app, 'btn_quit').master
    except Exception:
        parent = getattr(app, 'root', None)

    if parent is None:
        parent = getattr(app, 'root')

    # Prevent duplicate button
    try:
        for child in parent.winfo_children():
            if getattr(child, '_is_overlay_mic', False):
                return
    except Exception:
        pass

    # Create the mic button
    try:
        mic_btn = tk.Button(parent, text='🎤', bg='#16202A', fg='#E6EEF8', relief='flat')
        mic_btn._is_overlay_mic = True
    except Exception:
        return

    def _set_entry_text(text: Optional[str]):
        try:
            if text is None:
                # clear placeholder behavior lets overlay restore its placeholder
                app.entry_var.set('')
            else:
                app.entry_var.set(text)
            try:
                app.entry.focus_force()
                # move cursor to end
                app.entry.icursor('end')
            except Exception:
                pass
        except Exception:
            pass

    def _worker_listen():
        try:
            mic_btn.config(state='disabled', text='Listening...')
            # Try project's STT hook first
            text = _default_listen(timeout=5.0, phrase_time_limit=10.0)
            # Schedule UI update on main thread
            try:
                # Set recognized text into the entry
                app.root.after(0, lambda: _set_entry_text(text))
                # If we got a non-empty recognition result, auto-submit after a short delay
                if text and str(text).strip():
                    try:
                        app.root.after(250, lambda: app._on_enter(None))
                    except Exception:
                        pass
            except Exception:
                _set_entry_text(text)
        finally:
            try:
                app.root.after(0, lambda: mic_btn.config(state='normal', text='🎤'))
            except Exception:
                try:
                    mic_btn.config(state='normal', text='🎤')
                except Exception:
                    pass

    def _on_click(e=None):
        # start background thread listening
        t = threading.Thread(target=_worker_listen, daemon=True)
        t.start()

    try:
        mic_btn.bind('<Button-1>', _on_click)
        # Pack with same style as existing buttons (stacked vertically)
        mic_btn.pack(side='top', padx=4, pady=2, fill='x')
    except Exception:
        try:
            parent.add(mic_btn)
        except Exception:
            pass
