import io
from typing import Optional
import pyautogui
import requests
from .config import settings

GEMINI_VISION_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


def describe_screen() -> str:
    try:
        screenshot = pyautogui.screenshot()
    except Exception:
        # Stay quiet on errors to avoid annoying spoken messages
        return ""

    # If Gemini key is not configured, fall back to local OCR-based summary
    if not settings.GEMINI_API_KEY:
        try:
            # Use pytesseract if available to extract visible text
            import pytesseract
            from PIL import Image
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            buf.seek(0)
            img = Image.open(buf)
            text = pytesseract.image_to_string(img)
            if not text:
                return "I couldn't detect readable text on the screen."
            # Return the first few lines as a short description
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            summary = " ; ".join(lines[:5])
            return (summary or "").strip()
        except Exception:
            return ""

    # Encode image as PNG bytes
    buf = io.BytesIO()
    screenshot.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    # Gemini requires base64-encoded data for inline images
    import base64
    b64 = base64.b64encode(img_bytes).decode("ascii")

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "Describe this Windows screen briefly, what is visible and actionable."},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": b64
                        }
                    }
                ]
            }
        ]
    }
    params = {"key": settings.GEMINI_API_KEY}
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(GEMINI_VISION_URL, params=params, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return (text or "").strip()
    except Exception:
        # Suppress noisy error details
        return ""


def advise_next_step(goal: str) -> str:
    """Ask Gemini Vision for the next best steps to achieve a goal on the current Windows screen.

    Returns a short, numbered plan using safe, deterministic actions (keyboard first), suitable for narration.
    """
    try:
        screenshot = pyautogui.screenshot()
    except Exception:
        return ""

    if not settings.GEMINI_API_KEY:
        # Fallback: provide a deterministic keyboard-focused plan
        g = (goal or "").strip()
        plan = [
            "Press the Windows key to open Start.",
            f"Type: {g}.",
            "Use the arrow keys to select the appropriate result and press Enter.",
            "If necessary, use Alt+Tab to switch to the opened app.",
        ]
        return "\n".join(plan)

    import base64, json as _json
    buf = io.BytesIO()
    screenshot.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    prompt = (
        "You are assisting with controlling a Windows PC using only keyboard and simple mouse clicks. "
        "Given the screenshot and GOAL below, provide 2-5 concise, step-by-step actions that a user could perform. "
        "Prefer keyboard instructions (Ctrl+L, / to focus search, Tab, Enter, arrows, Esc). Avoid vague advice. "
        "If the goal is to open the first search result, mention TAB traversal to a result title and pressing Enter. "
        "Keep steps short and deterministic."
        f"\nGOAL: {goal}"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/png", "data": b64}},
                ],
            }
        ]
    }
    params = {"key": settings.GEMINI_API_KEY}
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(GEMINI_VISION_URL, params=params, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text or ""
    except Exception:
        # Stay silent on errors
        return ""
