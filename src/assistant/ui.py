
from typing import Optional, Tuple, List, Iterable
from .config import settings


def _click_with_cursor(control) -> bool:
    """Move the real cursor to a control's center and click; fallback to UIA click."""
    if not control or not control.Exists(0, 0):
        return False
    try:
        import pyautogui
    except Exception:
        try:
            control.Click()
            return True
        except Exception:
            return False

    try:
        rect = control.BoundingRectangle
        left = top = right = bottom = None
        try:
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            left, top, right, bottom = rect[0], rect[1], rect[2], rect[3]
        cx = int((left + right) / 2)
        cy = int((top + bottom) / 2)
        if left == right or top == bottom:
            raise ValueError("Invalid bounding box")
        pyautogui.moveTo(cx, cy, duration=max(0.0, settings.CURSOR_MOVE_DURATION))
        pyautogui.click()
        return True
    except Exception:
        try:
            control.Click()
            return True
        except Exception:
            return False


def click_first_hyperlink_in_foreground(retries: int = 3, sleep_seconds: float = 0.8, min_y: int = 0) -> bool:
    """Try to click the first hyperlink control visible in the current foreground window.
    Requires 'uiautomation' package. Returns True if a click was performed.
    """
    try:
        import uiautomation as auto
        import pyautogui
        import time

        # Small delay to allow UI to settle
        time.sleep(sleep_seconds)

        for _ in range(max(1, retries)):
            try:
                win = auto.GetForegroundControl()
                if not win:
                    time.sleep(sleep_seconds)
                    continue
                # Find first hyperlink descendant
                link = auto.HyperlinkControl(searchFromControl=win, foundIndex=1)
                # Validate link
                if not link or not link.Exists(0, 0):
                    time.sleep(sleep_seconds)
                    continue
                rect = link.BoundingRectangle
                # BoundingRectangle may be a tuple or object; normalize
                x = y = width = height = None
                try:
                    # object-style
                    x = int((rect.left + rect.right) / 2)
                    y = int((rect.top + rect.bottom) / 2)
                    width = abs(rect.right - rect.left)
                    height = abs(rect.bottom - rect.top)
                except Exception:
                    # tuple-style: (l, t, r, b)
                    try:
                        x = int((rect[0] + rect[2]) / 2)
                        y = int((rect[1] + rect[3]) / 2)
                        width = abs(rect[2] - rect[0])
                        height = abs(rect[3] - rect[1])
                    except Exception:
                        pass
                if x is None or y is None:
                    time.sleep(sleep_seconds)
                    continue
                if y < min_y:
                    time.sleep(sleep_seconds)
                    continue
                if width is not None and height is not None:
                    if width < 40 or height < 12:
                        time.sleep(sleep_seconds)
                        continue
                pyautogui.moveTo(x, y, duration=max(0.0, settings.CURSOR_MOVE_DURATION))
                pyautogui.click()
                return True
            except Exception:
                time.sleep(sleep_seconds)
                continue
        return False
    except Exception:
        # uiautomation not installed or other errors
        return False


def _focus_first_result_via_tab(min_y: int = 0, max_tabs: int = 40, settle: float = 0.08) -> bool:
    """Keyboard-based focusing of the first result link by sending TABs until a hyperlink below min_y is focused.
    Returns True if ENTER was sent on a suitable link.
    """
    try:
        import uiautomation as auto
        import pyautogui
        import time
    except Exception:
        return False

    # Ensure we're at the top of results and reset focus traversal
    time.sleep(settle)
    try:
        pyautogui.hotkey('ctrl', 'home')
        time.sleep(settle)
    except Exception:
        try:
            pyautogui.press('home')
            time.sleep(settle)
        except Exception:
            pass
    for _ in range(max(1, max_tabs)):
        try:
            # Check currently focused control
            try:
                focused = auto.GetFocusedControl()
            except Exception:
                focused = None
            # Validate candidate hyperlink
            def _is_good_link(ctrl) -> bool:
                if not ctrl:
                    return False
                try:
                    # Name should look like a result title, not tiny/tab links
                    name = (ctrl.Name or "").strip()
                except Exception:
                    name = ""
                if name and len(name) < 6:
                    return False
                # Control type should be Hyperlink ideally
                try:
                    ctn = getattr(ctrl, 'ControlTypeName', None) or ''
                except Exception:
                    ctn = ''
                if 'Hyperlink' not in ctn:
                    return False
                # Check geometry
                try:
                    rect = ctrl.BoundingRectangle
                    try:
                        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
                    except Exception:
                        left, top, right, bottom = rect[0], rect[1], rect[2], rect[3]
                    cx = int((left + right) / 2)
                    cy = int((top + bottom) / 2)
                    width = abs(int(right - left))
                    height = abs(int(bottom - top))
                except Exception:
                    return False
                if cy < min_y:
                    return False
                if width < 40 or height < 12:
                    return False
                return True

            if _is_good_link(focused):
                # Move cursor to the focused link before activation to mirror human behavior
                try:
                    rect = focused.BoundingRectangle
                    try:
                        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
                    except Exception:
                        left, top, right, bottom = rect[0], rect[1], rect[2], rect[3]
                    cx = int((left + right) / 2)
                    cy = int((top + bottom) / 2)
                    pyautogui.moveTo(cx, cy, duration=max(0.0, settings.CURSOR_MOVE_DURATION))
                    time.sleep(0.12)
                except Exception:
                    pass
                pyautogui.press('enter')
                return True

            # Otherwise advance focus
            pyautogui.press('tab')
            time.sleep(settle)
        except Exception:
            time.sleep(settle)
            continue
    return False


def _get_foreground_title() -> str:
    try:
        import uiautomation as auto
        win = auto.GetForegroundControl()
        if win:
            try:
                name = win.Name or ""
                return str(name)
            except Exception:
                return ""
    except Exception:
        pass
    try:
        import pygetwindow as gw
        w = gw.getActiveWindow()
        return (w.title or "") if w else ""
    except Exception:
        return ""

def get_foreground_title() -> str:
    return _get_foreground_title()


def _ocr_first_result_center(min_y: int = 0) -> Optional[Tuple[int, int]]:
    """Backward-compatible wrapper returning only the best candidate center, if any."""
    centers = _ocr_first_result_centers(min_y=min_y)
    return centers[0] if centers else None


def _ocr_first_result_centers(min_y: int = 0, max_candidates: int = 3, exclude_rects: Optional[List[Tuple[int,int,int,int]]] = None) -> List[Tuple[int, int]]:
    """Use pytesseract to find likely title-like text lines for the first few Google results.
    Returns up to max_candidates screen coordinates (x,y) ordered by visual top-to-bottom.
    """
    try:
        import pytesseract
        import pyautogui
        from PIL import Image
    except Exception:
        return []
    try:
        img = pyautogui.screenshot()
    except Exception:
        return []
    # Optional: set tesseract path on Windows and preprocess via OpenCV if available
    try:
        import os as _os
        import platform as _pl
        if _pl.system().lower().startswith('win'):
            tpath = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
            try:
                if _os.path.exists(tpath):
                    import pytesseract as _pt
                    _pt.pytesseract.tesseract_cmd = tpath
            except Exception:
                pass
    except Exception:
        pass
    # Preprocess image
    try:
        import numpy as _np
        import cv2 as _cv
        arr = _np.array(img)[:, :, ::-1]  # PIL RGB -> BGR
        # scale up slightly to help OCR with small fonts
        h, w = arr.shape[:2]
        scale = 1.5 if max(h, w) < 1600 else 1.25
        arr = _cv.resize(arr, (int(w * scale), int(h * scale)), interpolation=_cv.INTER_CUBIC)
        gray = _cv.cvtColor(arr, _cv.COLOR_BGR2GRAY)
        clahe = _cv.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        eq = clahe.apply(gray)
        blur = _cv.GaussianBlur(eq, (3,3), 0)
        # light adaptive threshold retains headings while suppressing noise
        th = _cv.adaptiveThreshold(blur, 255, _cv.ADAPTIVE_THRESH_GAUSSIAN_C, _cv.THRESH_BINARY, 31, 2)
        # back to PIL
        from PIL import Image as _Image
        img = _Image.fromarray(th)
    except Exception:
        pass
    # Use tesseract data to get word boxes and group into lines
    try:
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config='--oem 3 --psm 6')
    except Exception:
        return []
    n = len(data.get('text', []))
    if not n:
        return []
    # Group by (block_num, par_num, line_num)
    lines = {}
    for i in range(n):
        try:
            text = (data['text'][i] or '').strip()
            if not text:
                continue
            conf = int(data.get('conf', ['-1'])[i]) if data.get('conf') else 0
            if conf < 40:
                continue
            x = int(data['left'][i]); y = int(data['top'][i]); w = int(data['width'][i]); h = int(data['height'][i])
            key = (data.get('block_num', [0])[i], data.get('par_num', [0])[i], data.get('line_num', [0])[i])
            arr = lines.setdefault(key, [])
            arr.append((x, y, w, h, text))
        except Exception:
            continue
    if not lines:
        return []
    # Identify top markers to compute a dynamic min_y (below 'About X results' or nav row 'All Images ...')
    nav_bottom = 0
    about_bottom = 0
    for key, words in list(lines.items()):
        try:
            text_line = ' '.join([t for x, y, w, h, t in sorted(words, key=lambda a: a[0])])
            low = text_line.lower()
            ys = [y for x, y, w, h, t in words]; hs = [h for x, y, w, h, t in words]
            top = min(ys); bottom = max([y + h for x, y, w, h, t in words])
            if ('about' in low and 'result' in low) or ('results' in low):
                about_bottom = max(about_bottom, bottom)
            # nav row often contains several of these tokens
            nav_tokens = ['all', 'images', 'videos', 'news', 'shopping', 'maps']
            token_hits = sum(1 for tok in nav_tokens if tok in low)
            if token_hits >= 1 and len(words) >= 2 and bottom < 400:
                nav_bottom = max(nav_bottom, bottom)
        except Exception:
            continue

    dynamic_min_y = max(min_y, about_bottom + 60, nav_bottom + 60, 280)

    # Build line candidates
    candidates = []
    for key, words in lines.items():
        xs = [x for x, y, w, h, t in words]; ys = [y for x, y, w, h, t in words]
        ws = [w for x, y, w, h, t in words]; hs = [h for x, y, w, h, t in words]
        left = min(xs); right = max([x + w for x, y, w, h, t in words])
        top = min(ys); bottom = max([y + h for x, y, w, h, t in words])
        height_avg = sum(hs) / max(1, len(hs))
        text_line = ' '.join([t for x, y, w, h, t in sorted(words, key=lambda a: a[0])])
        # Heuristics for a result title on Google
        if top < dynamic_min_y:
            continue
        if left < 60:
            continue
        if left > 900:  # too far to the right for typical first column
            continue
        if height_avg < 12:  # small text; skip
            continue
        if len(text_line) < 12:
            continue
        banned = [
            'Google', 'Images', 'Videos', 'News', 'Shopping', 'More', 'People also ask', 'Sponsored', 'Ads', 'Ad',
            'Filters', 'Tools', 'Translate', 'Maps'
        ]
        if any(b.lower() in text_line.lower() for b in banned):
            continue
        # Require line width reasonably wide
        width = right - left
        if width < 260:
            continue
        y_mid = int((top + bottom) / 2)
        x_mid = int((left + right) / 2)
        # Exclude header/logo/search-box rectangles
        if exclude_rects:
            for (lx, ty, rx, by) in exclude_rects:
                if lx <= x_mid <= rx and ty <= y_mid <= by:
                    x_mid = -1; y_mid = -1
                    break
            if x_mid < 0:
                continue
        candidates.append((top, x_mid, y_mid, text_line, width))
    if not candidates:
        return []
    # Prefer topmost and reasonably wide
    candidates.sort(key=lambda a: (a[0], -a[4]))
    # Return up to max_candidates centers
    result: List[Tuple[int, int]] = []
    for item in candidates[:max(1, max_candidates)]:
        _, cx, cy, _txt, _w = item
        result.append((cx, cy))
    return result


def _rect_contains_point(rect: Tuple[int,int,int,int], x: int, y: int) -> bool:
    l,t,r,b = rect
    return l <= x <= r and t <= y <= b


def _get_exclusion_rects() -> List[Tuple[int,int,int,int]]:
    """Return rectangles to avoid clicking (logo area, search box, header bars) using UIA best-effort."""
    rects: List[Tuple[int,int,int,int]] = []
    try:
        import uiautomation as auto
        win = auto.GetForegroundControl()
        if not win:
            return rects
        # Google logo image or heading
        try:
            logo = auto.ImageControl(searchFromControl=win, RegexName=r"(?i)google")
            if logo and logo.Exists(0,0):
                br = logo.BoundingRectangle
                try:
                    rects.append((int(br.left), int(br.top), int(br.right), int(br.bottom)))
                except Exception:
                    rects.append((int(br[0]), int(br[1]), int(br[2]), int(br[3])))
        except Exception:
            pass
        # Search edit box
        try:
            edit = auto.EditControl(searchFromControl=win, RegexName=r"(?i)search|address|omnibox|query")
            if edit and edit.Exists(0,0):
                br = edit.BoundingRectangle
                try:
                    rects.append((int(br.left), int(br.top), int(br.right), int(br.bottom)))
                except Exception:
                    rects.append((int(br[0]), int(br[1]), int(br[2]), int(br[3])))
        except Exception:
            pass
        # Navigation bar row area (All, Images, etc.) via TextControl
        try:
            nav = auto.TextControl(searchFromControl=win, RegexName=r"(?i)\ball\b|images|videos|news|shopping|maps")
            if nav and nav.Exists(0,0):
                br = nav.BoundingRectangle
                try:
                    rects.append((int(br.left), int(br.top)-10, int(br.right)+200, int(br.bottom)+40))
                except Exception:
                    rects.append((int(br[0]), int(br[1])-10, int(br[2])+200, int(br[3])+40))
        except Exception:
            pass
    except Exception:
        return rects
    return rects


def _enumerate_hyperlink_candidates(min_y: int = 0, max_candidates: int = 5) -> List[Tuple[int,int,str]]:
    """Enumerate top hyperlink controls that look like result titles, returning (x,y,name)."""
    results: List[Tuple[int,int,str,int]] = []
    try:
        import uiautomation as auto
        import time as _t
        win = auto.GetForegroundControl()
        if not win:
            return []
        # Iterate by foundIndex; stop after a bunch
        for idx in range(1, 30):
            try:
                link = auto.HyperlinkControl(searchFromControl=win, foundIndex=idx)
                if not link or not link.Exists(0,0):
                    break
                try:
                    name = (link.Name or '').strip()
                except Exception:
                    name = ''
                if name and len(name) < 6:
                    continue
                br = link.BoundingRectangle
                try:
                    l,t,r,b = int(br.left), int(br.top), int(br.right), int(br.bottom)
                except Exception:
                    l,t,r,b = int(br[0]), int(br[1]), int(br[2]), int(br[3])
                cx, cy = int((l+r)/2), int((t+b)/2)
                width, height = r-l, b-t
                if cy < min_y:
                    continue
                if width < 180 or height < 14:
                    continue
                if l < 60 or l > 900:
                    continue
                results.append((cx, cy, name, t))
            except Exception:
                continue
        # sort by top ascending
        results.sort(key=lambda x: x[3])
        trimmed = [(cx, cy, name) for (cx, cy, name, _t) in results[:max_candidates]]
        return trimmed
    except Exception:
        return []


def click_first_search_result(min_y: int = 0, retries: int = 2, verify: bool = True, prefer_keyboard: bool = False, hint_text: Optional[str] = None) -> bool:
    """Robust attempt to activate the first search result in the current foreground browser.
    Strategy:
    1) Try keyboard-based TAB traversal to focus a hyperlink below min_y, then press ENTER.
    2) Fallback to UI Automation hyperlink click heuristic.
    """
    # 1) Keyboard traversal (preferred for layout/DPI independence) with light retry/scroll
    try:
        import pyautogui as _pg
        import time as _t
    except Exception:
        _pg = None
    old_title = _get_foreground_title() if verify else ""
    # Gather exclusion zones to avoid header/logo/search box
    exclude_rects = _get_exclusion_rects()
    # Preferred order: UIA candidates (content-aware) -> OCR (cursor) -> Keyboard (optional)
    candidates_cursor: List[Tuple[int,int,str]] = []
    # 1) UIA: top N hyperlink candidates with their names
    uia_cands = _enumerate_hyperlink_candidates(min_y=min_y, max_candidates=5)
    candidates_cursor.extend(uia_cands)
    # 2) OCR fallback: add centers with empty names (ranked after UIA)
    ocr_centers = _ocr_first_result_centers(min_y=min_y, max_candidates=3, exclude_rects=exclude_rects)
    for (x,y) in ocr_centers:
        candidates_cursor.append((x,y,''))
    # Rank by hint_text overlap first
    def _score(name: str) -> int:
        if not hint_text or not name:
            return 0
        try:
            import re as _re
            h = [w for w in _re.split(r"\W+", hint_text.lower()) if w and len(w) >= 3]
            n = [w for w in _re.split(r"\W+", name.lower()) if w and len(w) >= 3]
            hs = set(h)
            return len(hs.intersection(n))
        except Exception:
            return 0
    candidates_cursor.sort(key=lambda it: -_score(it[2]))
    # Try each candidate with hover then click; slightly nudge downward on click
    if candidates_cursor and _pg:
        for idx, (cx, cy, name) in enumerate(candidates_cursor):
            try:
                # Exclude if inside a header rectangle
                if exclude_rects:
                    skip = False
                    for rect in exclude_rects:
                        if _rect_contains_point(rect, cx, cy):
                            skip = True; break
                    if skip:
                        continue
                # Hover briefly before click to avoid hitting logo; then click
                _pg.moveTo(cx, cy, duration=max(0.0, settings.CURSOR_MOVE_DURATION))
                try:
                    import time as _t
                    _t.sleep(0.15)
                except Exception:
                    pass
                # slight downward nudge before click to bias toward title text, not toolbar
                _pg.moveRel(0, 6, duration=0.05)
                _pg.click()
                if not verify:
                    return True
                import time as _t
                opened = False
                for _ in range(14):
                    _t.sleep(0.25)
                    new_title = _get_foreground_title()
                    if new_title and new_title != old_title and ('google' not in new_title.lower()):
                        opened = True
                        break
                if opened:
                    return True
                # If this candidate didn't work, try a tiny scroll and next candidate
                try:
                    _pg.scroll(-240)
                    _t.sleep(0.15)
                except Exception:
                    pass
            except Exception:
                continue
    # 3) As a last fallback: generic UIA hyperlink click
    if click_first_hyperlink_in_foreground(retries=max(1, retries), sleep_seconds=0.5, min_y=min_y):
        if not verify:
            return True
        try:
            import time as _t
            for _ in range(12):
                _t.sleep(0.25)
                new_title = _get_foreground_title()
                if new_title and new_title != old_title and ('google' not in new_title.lower()):
                    return True
        except Exception:
            pass
    # 4) Keyboard traversal (only if explicitly preferred)
    if prefer_keyboard:
        for attempt in range(max(1, retries)):
            if _focus_first_result_via_tab(min_y=min_y):
                if not verify:
                    return True
                try:
                    import time as _t
                    for _ in range(12):
                        _t.sleep(0.25)
                        new_title = _get_foreground_title()
                        if new_title and new_title != old_title and ('google' not in new_title.lower()):
                            return True
                except Exception:
                    pass
            if _pg:
                try:
                    _pg.scroll(-300)
                    _t.sleep(0.2)
                except Exception:
                    pass
    return False


def _open_quick_settings() -> bool:
    try:
        import pyautogui
        import time
        pyautogui.hotkey('winleft', 'a')
        time.sleep(0.7)
        return True
    except Exception:
        return False


def _close_quick_settings():
    try:
        import pyautogui
        pyautogui.press('esc')
    except Exception:
        pass


def _find_quick_action_button(name_pattern: str):
    try:
        import uiautomation as auto
        root = auto.GetRootControl()
        # Prefer the current foreground popup after Win+A
        fg = None
        try:
            fg = auto.GetForegroundControl()
        except Exception:
            fg = None
        search_scopes = [c for c in [fg, root] if c]
        for scope in search_scopes:
            # Try to narrow to Quick Settings pane/window
            try:
                qs = auto.PaneControl(searchFromControl=scope, RegexName=r"(?i)quick\s*settings|action\s*center|notification\s*center")
                container = qs if qs and qs.Exists(0, 0) else scope
            except Exception:
                container = scope
            # Try ToggleButton first
            try:
                btn = auto.ToggleButtonControl(searchFromControl=container, RegexName=name_pattern)
                if btn and btn.Exists(0, 0):
                    return btn
            except Exception:
                pass
            # Fallback to generic Button
            try:
                btn = auto.ButtonControl(searchFromControl=container, RegexName=name_pattern)
                if btn and btn.Exists(0, 0):
                    return btn
            except Exception:
                pass
        return None
    except Exception:
        return None


def _get_quick_settings_container():
    """Return the Quick Settings container/pane control if visible, else None."""
    try:
        import uiautomation as auto
        fg = None
        try:
            fg = auto.GetForegroundControl()
        except Exception:
            pass
        scopes = [c for c in [fg, auto.GetRootControl()] if c]
        for scope in scopes:
            try:
                qs = auto.PaneControl(searchFromControl=scope, RegexName=r"(?i)quick\s*settings|action\s*center|notification\s*center")
                if qs and qs.Exists(0, 0):
                    return qs
            except Exception:
                continue
    except Exception:
        pass
    return None


def _find_quick_action_button_in(container, name_pattern: str):
    try:
        import uiautomation as auto
        if not container:
            return None
        try:
            btn = auto.ToggleButtonControl(searchFromControl=container, RegexName=name_pattern)
            if btn and btn.Exists(0, 0):
                return btn
        except Exception:
            pass
        try:
            btn = auto.ButtonControl(searchFromControl=container, RegexName=name_pattern)
            if btn and btn.Exists(0, 0):
                return btn
        except Exception:
            pass
        return None
    except Exception:
        return None


def _rect_valid(br) -> bool:
    try:
        left, top, right, bottom = br.left, br.top, br.right, br.bottom
    except Exception:
        try:
            left, top, right, bottom = br[0], br[1], br[2], br[3]
        except Exception:
            return False
    return (right - left) > 3 and (bottom - top) > 3


def _scroll_in_container(container, amount: int, hover_offset: int = 20):
    try:
        import pyautogui, time
        br = container.BoundingRectangle
        try:

            l, t, r, b = int(br.left), int(br.top), int(br.right), int(br.bottom)
        except Exception:
            l, t, r, b = int(br[0]), int(br[1]), int(br[2]), int(br[3])
        cx, cy = int((l + r) / 2), int((t + b) / 2)
        pyautogui.moveTo(cx, cy + hover_offset, duration=max(0.0, settings.CURSOR_MOVE_DURATION))
        pyautogui.scroll(amount)
        time.sleep(0.12)
    except Exception:
        pass


def _ensure_quick_button_visible(name_pattern: str, max_scroll_attempts: int = 6):
    """Try to locate the quick action button and scroll the QS container until its rectangle is valid/visible."""
    try:
        container = _get_quick_settings_container()
        if not container:
            return _find_quick_action_button(name_pattern)
        # initial try
        btn = _find_quick_action_button_in(container, name_pattern)
        if btn and btn.Exists(0, 0):
            try:
                if _rect_valid(btn.BoundingRectangle):
                    return btn
            except Exception:
                pass
        # scroll down a few times to find it
        for _ in range(max_scroll_attempts // 2):
            _scroll_in_container(container, amount=-300)
            btn = _find_quick_action_button_in(container, name_pattern)
            if btn and btn.Exists(0, 0):
                try:
                    if _rect_valid(btn.BoundingRectangle):
                        return btn
                except Exception:
                    pass
        # scroll up to try the top area
        for _ in range(max_scroll_attempts // 2):
            _scroll_in_container(container, amount=300)
            btn = _find_quick_action_button_in(container, name_pattern)
            if btn and btn.Exists(0, 0):
                try:
                    if _rect_valid(btn.BoundingRectangle):
                        return btn
                except Exception:
                    pass
        # final attempt without validated rect
        return btn if (btn and btn.Exists(0, 0)) else None
    except Exception:
        return None


def toggle_quick_action(kind: str, desired: Optional[bool]) -> bool:
    """Toggle Wi‑Fi or Bluetooth in Windows 11 Quick Settings (Win+A).
    kind: 'wifi' | 'bluetooth'
    desired: True to turn on, False to turn off, None to just toggle once.
    """
    try:
        import uiautomation as auto
        import time
    except Exception:
        return False

    if not _open_quick_settings():
        return False

    kind_l = kind.lower()
    pattern = r"(?i)\bwi[- ]?fi\b" if kind_l == 'wifi' else r"(?i)\bbluetooth\b"

    # Try a few times as the panel animates in; ensure visible even if initially off-screen
    for _ in range(10):
        btn = _ensure_quick_button_visible(pattern)
        if btn:
            try:
                # If TogglePattern is available, respect desired state
                try:
                    tp = btn.GetTogglePattern()
                    current = tp.CurrentToggleState
                except Exception:
                    tp = None
                    current = None

                def _state_matches() -> Optional[bool]:
                    try:
                        tp2 = btn.GetTogglePattern()
                        cur2 = tp2.CurrentToggleState
                        return (cur2 == (1 if desired else 0)) if desired is not None else True
                    except Exception:
                        return None

                if desired is None:
                    if _rect_valid(btn.BoundingRectangle) and _click_with_cursor(btn):
                        time.sleep(0.6)
                        _close_quick_settings()
                        return True
                else:
                    want = 1 if desired else 0
                    if current is not None and current == want:
                        _close_quick_settings(); return True
                    clicked_once = False
                    ok: Optional[bool] = None
                    if _rect_valid(btn.BoundingRectangle) and _click_with_cursor(btn):
                        clicked_once = True
                        time.sleep(0.7)  
                        ok = _state_matches()
                        if ok is True or ok is None:
                            _close_quick_settings(); return True
                #if word is know for gopd then if it is called as california , and sumoneria and to  its 
                    # Keyboard fallback only when state still incorrect
                    if ok is False or not clicked_once:



                        try:
                            import pyautogui
                            _ = btn.SetFocus()
                            time.sleep(0.1)
                            pyautogui.press('space')
                            time.sleep(0.5)
                            ok = _state_matches()
                            if ok is True or ok is None:
                                _close_quick_settings(); return True
                            pyautogui.press('enter')
                            time.sleep(0.5)
                            ok = _state_matches()
                            if ok is True or ok is None:
                                _close_quick_settings(); return True
                        except Exception:
                            pass
                    if ok is False or not clicked_once:
                        # Try to ensure visible again then click
                        btn2 = _ensure_quick_button_visible(pattern)
                        if btn2 and _rect_valid(btn2.BoundingRectangle) and _click_with_cursor(btn2):
                            time.sleep(0.6)
                            ok = _state_matches()
                            if ok is True or ok is None:
                                _close_quick_settings(); return True
            except Exception:
                time.sleep(0.5)
        else:
            time.sleep(0.5)
    _close_quick_settings()
    # Fallback: for Night light specifically, try Settings page toggle
    if kind_l == 'night_light':
        try:
            import subprocess, time as _t
            subprocess.Popen(["start", "ms-settings:display"], shell=True)
            _t.sleep(1.2)
            import uiautomation as auto
            # Find Night light toggle in Settings
            for _ in range(12):
                try:
                    win = auto.GetForegroundControl()
                    if win:
                        tog = auto.ToggleButtonControl(searchFromControl=win, RegexName=r"(?i)night\s*light")
                        if tog and tog.Exists(0,0):
                            try:
                                tp = tog.GetTogglePattern()
                                cur = tp.CurrentToggleState
                                want = 1 if desired else 0 if desired is not None else None
                                # Click once if toggle requested or state differs
                                if want is None or cur != want:
                                    _click_with_cursor(tog)
                                    _t.sleep(0.8)
                                return True
                            except Exception:
                                pass
                except Exception:
                    pass
                _t.sleep(0.4)
        except Exception:
            pass
    return False


# Generic mappings for Quick Settings tiles
_QS_TOGGLE_PATTERNS = {
    'wifi': r"(?i)\bwi[- ]?fi\b",
    'bluetooth': r"(?i)\bbluetooth\b",
    'airplane': r"(?i)\bairplane\s*mode\b|\bflight\s*mode\b",
    'airplane_mode': r"(?i)\bairplane\s*mode\b|\bflight\s*mode\b",
    'night_light': r"(?i)\bnight\s*light\b",
    'focus_assist': r"(?i)\bfocus\s*assist\b|\bdo\s*not\s*disturb\b|\bdnd\b",
    'battery_saver': r"(?i)\bbattery\s*saver\b|\benergy\s*saver\b",
    'hotspot': r"(?i)\bmobile\s*hotspot\b|\bhotspot\b",
    'mobile_hotspot': r"(?i)\bmobile\s*hotspot\b|\bhotspot\b",
    'location': r"(?i)\blocation\b|\bgps\b",
    'cast': r"(?i)\bcast\b",
    'project': r"(?i)\bproject\b|\bconnect\s*display\b",
    'nearby_share': r"(?i)\bnearby\s*share\b",
}


def quick_toggle(name: str, desired: Optional[bool]) -> bool:
    key = name.lower().strip().replace(' ', '_')
    pattern = _QS_TOGGLE_PATTERNS.get(key)
    if not pattern:
        # Try direct string
        pattern = rf"(?i){name}"
    try:
        import uiautomation as auto
        import time
    except Exception:
        return False

    if not _open_quick_settings():
        return False

    # For Night light / Battery saver: do NOT scroll; only click if visible. Otherwise fallback to Settings page.
    NOSCROLL_KEYS = {"night_light", "battery_saver"}
    for _ in range(10):
        btn = _find_quick_action_button(pattern) if key in NOSCROLL_KEYS else _ensure_quick_button_visible(pattern)
        if btn:
            try:
                try:
                    tp = btn.GetTogglePattern()
                    current = tp.CurrentToggleState
                except Exception:
                    tp = None
                    current = None
                def _state_matches() -> Optional[bool]:
                    try:
                        tp2 = btn.GetTogglePattern()
                        cur2 = tp2.CurrentToggleState
                        return (cur2 == (1 if desired else 0)) if desired is not None else True
                    except Exception:
                        return None

                if desired is None:
                    if _rect_valid(btn.BoundingRectangle) and _click_with_cursor(btn):
                        time.sleep(0.6); _close_quick_settings(); return True
                else:
                    want = 1 if desired else 0
                    if current is not None and current == want:
                        _close_quick_settings(); return True
                    clicked_once = False
                    ok: Optional[bool] = None
                    if _rect_valid(btn.BoundingRectangle) and _click_with_cursor(btn):
                        clicked_once = True
                        time.sleep(0.7)
                        ok = _state_matches()
                        if ok is True or ok is None:
                            _close_quick_settings(); return True
                    if ok is False or not clicked_once:
                        try:
                            import pyautogui
                            _ = btn.SetFocus()
                            time.sleep(0.1)
                            pyautogui.press('space')
                            time.sleep(0.5)
                            ok = _state_matches()
                            if ok is True or ok is None:
                                _close_quick_settings(); return True
                            pyautogui.press('enter')
                            time.sleep(0.5)
                            ok = _state_matches()
                            if ok is True or ok is None:
                                _close_quick_settings(); return True
                        except Exception:
                            pass
                    if ok is False or not clicked_once:
                        # Do not scroll for noscroll keys; otherwise one more ensure
                        btn2 = None if key in NOSCROLL_KEYS else _ensure_quick_button_visible(pattern)
                        if btn2 and _rect_valid(btn2.BoundingRectangle) and _click_with_cursor(btn2):
                            time.sleep(0.6)
                            ok = _state_matches()
                            if ok is True or ok is None:
                                _close_quick_settings(); return True
            except Exception:
                time.sleep(0.5)
        else:
            time.sleep(0.5)
    _close_quick_settings()
    # Settings page fallbacks (no scrolling)
    if key == 'night_light':
        try:
            import subprocess, time as _t, uiautomation as auto
            subprocess.Popen(["start", "ms-settings:display"], shell=True)
            _t.sleep(1.2)
            for _ in range(12):
                win = None
                try:
                    win = auto.GetForegroundControl()
                except Exception:
                    pass
                if win:
                    try:
                        tog = auto.ToggleButtonControl(searchFromControl=win, RegexName=r"(?i)night\s*light")
                        if tog and tog.Exists(0,0):
                            try:
                                tp = tog.GetTogglePattern()
                                if desired is None:
                                    _click_with_cursor(tog); return True
                                want = 1 if desired else 0
                                cur = tp.CurrentToggleState
                                if cur != want:
                                    _click_with_cursor(tog)
                                    _t.sleep(0.7)
                                return True
                            except Exception:
                                pass
                    except Exception:
                        pass
                _t.sleep(0.4)
        except Exception:
            pass
    if key == 'battery_saver':
        if _toggle_battery_saver_in_settings(desired):
            return True
    return False


def _toggle_battery_saver_in_settings(desired: Optional[bool]) -> bool:
    """Open Settings to battery saver page and toggle state without QS scrolling."""
    try:
        import subprocess, time as _t, uiautomation as auto
        # Try dedicated battery saver URI first; then fallback to power page
        uris = ["ms-settings:batterysaver", "ms-settings:powersleep", "ms-settings:power"]
        ok_any = False
        for uri in uris:
            try:
                subprocess.Popen(["start", uri], shell=True)
                _t.sleep(1.2)
            except Exception:
                continue
            # Look for Battery saver / Energy saver toggles
            for _ in range(12):
                win = None
                try:
                    win = auto.GetForegroundControl()
                except Exception:
                    pass
                if win:
                    try:
                        label = r"(?i)(battery\s*saver|energy\s*saver)"
                        tog = auto.ToggleButtonControl(searchFromControl=win, RegexName=label)
                        if tog and tog.Exists(0,0):
                            try:
                                tp = tog.GetTogglePattern()
                                if desired is None:
                                    _click_with_cursor(tog); return True
                                want = 1 if desired else 0
                                cur = tp.CurrentToggleState
                                if cur != want:
                                    _click_with_cursor(tog)
                                    _t.sleep(0.7)
                                return True
                            except Exception:
                                pass
                    except Exception:
                        pass
                _t.sleep(0.4)
            ok_any = ok_any or False
        return False
    except Exception:
        return False


def open_app_via_start(app_name: str, settle: float = 0.15, verify: bool = True) -> bool:
    """Press Win, type app name, Enter. Optionally verify foreground window title includes app name."""
    try:
        import pyautogui as _pg, time as _t
        _pg.hotkey('winleft')
        _t.sleep(settle + 0.4)  # Increased settle time for Start menu to fully open
        
        # Use clipboard for more reliable typing (handles special chars, non-ASCII)
        try:
            import pyperclip
            pyperclip.copy(app_name)
            _t.sleep(0.1)
            _pg.hotkey('ctrl', 'v')
        except Exception:
            # Fallback to typewrite if clipboard fails
            _pg.typewrite(app_name, interval=0.04)
        
        _t.sleep(0.4)  # Wait for search results to populate
        _pg.press('enter')
        if not verify:
            return True
        base = app_name.lower().split()[0]
        for _ in range(40):  # Increased retry count for slower app launches
            _t.sleep(0.25)
            title = _get_foreground_title().lower()
            if base in title or app_name.lower() in title:
                return True
        return True  # best effort
    except Exception:
        return False


def _say(txt: str):
    if not txt: return
    try:
        from .tts import speak_async
        speak_async(txt, emotion='friendly')
    except Exception:
        pass

def whatsapp_launch_and_wait() -> bool:
    """Explicitly launch WhatsApp via Start and wait for Search UI to be ready."""
    import pyautogui as _pg, time as _t
    from .ui import open_app_via_start

    try:
        import uiautomation as auto
    except ImportError:
        _say("I need the 'uiautomation' library to control WhatsApp, but it's missing.")
        return False

    whatsapp_focused = False
    # Priority: Open via Start (Search) as requested
    for attempt in range(2):
        if open_app_via_start('whatsapp'):
            _t.sleep(2.5) # Initial launch wait
            break
    
    # Wait loop used to determine if the window is up
    for _ in range(3):
        if _try_focus_app_window(['whatsapp']):
            whatsapp_focused = True
            break
        _t.sleep(1.0)

    if not whatsapp_focused:
        _say("Having trouble opening WhatsApp. Please open it manually.")
        return False
    
    _t.sleep(0.5)
    _say("Bringing WhatsApp into focus for you.")

    # Explicit screen analysis step
    _say("Analyzing screen to verify WhatsApp is ready.")
    
    search_ready = False
    
    def _find_search_box():
        try:
            win = auto.GetForegroundControl()
            if not win: return None
            # Look for 'Search' or 'New Chat'
            edits = win.GetChildren()
            for child in edits:
                if child.ControlTypeName == "EditControl":
                    name = (child.Name or "").lower()
                    if "search" in name or "find" in name:
                        return child
            return auto.EditControl(searchFromControl=win, RegexName=r"(?i)search|find")
        except Exception:
            return None

    # Wait up to 10s for UI
    for _ in range(20):
        try:
            sb = _find_search_box()
            if sb and sb.Exists(0,0):
                search_ready = True
                return True
        except Exception:
            pass
        _t.sleep(0.5)
    
    if not search_ready:
        # One last heuristic wait
        _t.sleep(1.0)
        return True # Proceed with best effort
    return True


def whatsapp_search_and_open_chat(contact: str) -> bool:
    """Focus search box, type contact, select best match."""
    import pyautogui as _pg, time as _t, re
    
    try:
        import uiautomation as auto
    except ImportError:
        return False


    if not contact: return False
    
    # 1. Focus Search
    # Priority: Use Ctrl+F to focus search (User preferred)
    # Press multiple times to ensure robust focus for multi-recipient flows
    for _ in range(3):
        try: 
            _pg.hotkey('ctrl', 'f')
        except: 
            pass
        _t.sleep(0.25)

    # Clear existing search text to prevent appending to previous searches
    try: 
        _pg.hotkey('ctrl', 'a')
        _t.sleep(0.1)
        _pg.press('backspace')
    except: pass
    
    _t.sleep(0.25)
    _pg.typewrite(contact, interval=0.03)
    _t.sleep(0.8) 
    _say(f"Searching for {contact}.")

    # 2. Select First Result
    def _select_first_chat() -> bool:
        try:
            win = auto.GetForegroundControl()
            if not win: return False
            # Check list items
            item = auto.ListItemControl(searchFromControl=win, foundIndex=1)
            if item and item.Exists(0,0):
                # Verify name match if possible? 
                # For now, we trust the search result as requested "searches and sends"
                _click_with_cursor(item)
                return True
        except Exception:
            pass
        try: _pg.press('down'); _t.sleep(0.1); _pg.press('enter'); return True
        except: return False

    if _select_first_chat():
        _say(f"Opening chat with {contact}.")
        _t.sleep(1.0) # Wait for chat load
        return True
    return False


def whatsapp_paste_and_send(message: str) -> bool:
    """Focus message box, paste clipboard content, send."""
    import pyautogui as _pg, time as _t
    import pyperclip
    
    try:
        import uiautomation as auto
    except ImportError:
        return False

    if not message: return True # Nothing to send
    
    # 1. Focus input
    message_box_focused = False
    try:
        win = auto.GetForegroundControl()
        if win:
            msg_ed = auto.EditControl(searchFromControl=win, RegexName=r"(?i)type a message|message")
            if msg_ed and msg_ed.Exists(0,0):
                _click_with_cursor(msg_ed)
                message_box_focused = True
    except: pass
    
    if not message_box_focused:
        scr = _pg.size()
        _pg.click(int(scr[0]*0.5), int(scr[1]*0.9))
    
    _t.sleep(0.3)
    
    _say("Pasting your message.")
    try:
        # Assuming text is already in clipboard from previous step or we put it there now
        # The prompt implies we should put it there if not?
        # But for safety we ensure it matches the argument
        pyperclip.copy(message) 
        _t.sleep(0.1)
        _pg.hotkey('ctrl', 'v')
        _t.sleep(1.0) # Render wait
        
        _say("Sending it!")
        _pg.press('enter')
        return True
    except Exception:
        return False


def whatsapp_send_message(contact: str, message: Optional[str]) -> bool:
    """Legacy wrapper maintained for backward compatibility."""
    if not whatsapp_launch_and_wait():
        return False
    if not whatsapp_search_and_open_chat(contact):
        return False
    if message:
        return whatsapp_paste_and_send(message)
    return True


def _try_focus_app_window(keywords: List[str], wait: float = 0.2) -> bool:
    try:
        import pygetwindow as gw, time as _t
        # normalize keywords
        keys = [k.lower() for k in keywords]
        
        for attempt in range(6):
            wins = gw.getAllWindows()
            target_win = None
            for w in wins:
                try:
                    title = (w.title or '').lower()
                    if any(k in title for k in keys):
                        target_win = w
                        break
                except Exception:
                    continue
            
            if target_win:
                try:
                    if getattr(target_win, "isMinimized", False):
                        target_win.restore()
                    target_win.activate()
                    _t.sleep(max(wait, 0.5))
                    return True
                except Exception:
                    pass
            _t.sleep(wait)
        return False
    except Exception:
        return False


def close_app(name: Optional[str] = None) -> bool:
    """Close the current foreground app or the app by name using Alt+F4 after focusing it."""
    try:
        import pyautogui as _pg, time as _t
        if name:
            if not _try_focus_app_window([name.lower()]):
                # Try opening Start search with the name and then closing if open fails
                pass
        _pg.hotkey('alt', 'f4')
        _t.sleep(0.3)
        return True
    except Exception:
        return False


def _find_quick_slider(name_pattern: str):
    try:
        import uiautomation as auto
        fg = None
        try:
            fg = auto.GetForegroundControl()
        except Exception:
            pass
        scopes = [c for c in [fg, auto.GetRootControl()] if c]
        for scope in scopes:
            try:
                qs = auto.PaneControl(searchFromControl=scope, RegexName=r"(?i)quick\s*settings|action\s*center|notification\s*center")
                container = qs if qs and qs.Exists(0, 0) else scope
            except Exception:
                container = scope
            try:
                slider = None
                # Try SliderControl by name
                slider = auto.SliderControl(searchFromControl=container, RegexName=name_pattern)
                if slider and slider.Exists(0, 0):
                    return slider
            except Exception:
                pass
            # Fallback: find by label then get sibling Thumb
            try:
                label = auto.TextControl(searchFromControl=container, RegexName=name_pattern)
                if label and label.Exists(0, 0):
                    parent = label.GetParentControl()
                    thumb = auto.ThumbControl(searchFromControl=parent)
                    if thumb and thumb.Exists(0, 0):
                        return thumb
                    try:
                        prog = auto.ProgressBarControl(searchFromControl=parent)
                        if prog and prog.Exists(0, 0):
                            return prog
                    except Exception:
                        pass
            except Exception:
                pass
            # Broader fallback: pick a SliderControl inside QS if named search failed
            try:
                # Try to detect brightness first so we can choose the other slider for volume
                bright = None
                try:
                    # Correct regex for word boundary
                    bright = auto.SliderControl(searchFromControl=container, RegexName=r"(?i)\bbrightness\b")
                    if not (bright and bright.Exists(0, 0)):
                        bright = None
                except Exception:
                    bright = None
                # Enumerate a couple of sliders
                for idx in range(1, 6):
                    try:
                        cand = auto.SliderControl(searchFromControl=container, foundIndex=idx)
                        if cand and cand.Exists(0, 0):
                            if bright and hasattr(bright, "BoundingRectangle") and hasattr(cand, "BoundingRectangle"):
                                try:
                                    if cand.BoundingRectangle != bright.BoundingRectangle:
                                        return cand
                                except Exception:
                                    pass
                            else:
                                # If we don't know brightness, return the first slider we find
                                return cand
                    except Exception:
                        break
                # If no SliderControl, try generic Thumb likely representing a slider handle
                cand_thumb = auto.ThumbControl(searchFromControl=container)
                if cand_thumb and cand_thumb.Exists(0, 0):
                    return cand_thumb
            except Exception:
                pass
        return None
    except Exception:
        return None


def _find_volume_slider():
    """Heuristically find the Volume slider in Quick Settings. Prefer label-based detection and avoid the Brightness slider."""
    try:
        import uiautomation as auto
        fg = None
        try:
            fg = auto.GetForegroundControl()
        except Exception:
            pass
        scopes = [c for c in [fg, auto.GetRootControl()] if c]
        for scope in scopes:
            try:
                qs = auto.PaneControl(searchFromControl=scope, RegexName=r"(?i)quick\s*settings|action\s*center|notification\s*center")
                container = qs if qs and qs.Exists(0, 0) else scope
            except Exception:
                container = scope
            # 1) Label-based
            try:
                label = auto.TextControl(searchFromControl=container, RegexName=r"(?i)\b(volume|sound|audio)\b")
                if label and label.Exists(0, 0):
                    parent = label.GetParentControl()
                    if parent:
                        try:
                            slider = auto.SliderControl(searchFromControl=parent)
                            if slider and slider.Exists(0, 0):
                                return slider
                        except Exception:
                            pass
                        try:
                            thumb = auto.ThumbControl(searchFromControl=parent)
                            if thumb and thumb.Exists(0, 0):
                                return thumb
                        except Exception:
                            pass
                        try:
                            prog = auto.ProgressBarControl(searchFromControl=parent)
                            if prog and prog.Exists(0, 0):
                                return prog
                        except Exception:
                            pass
            except Exception:
                pass
            # 2) Distinguish from brightness
            try:
                bright = None
                try:
                    bright = auto.SliderControl(searchFromControl=container, RegexName=r"(?i)\bbrightness\b")
                    if not (bright and bright.Exists(0, 0)):
                        bright = None
                except Exception:
                    bright = None
                # Enumerate sliders and choose the one that's not brightness
                for idx in range(1, 6):
                    try:
                        cand = auto.SliderControl(searchFromControl=container, foundIndex=idx)
                        if cand and cand.Exists(0, 0):
                            if bright and hasattr(bright, "BoundingRectangle") and hasattr(cand, "BoundingRectangle"):
                                try:
                                    if cand.BoundingRectangle != bright.BoundingRectangle:
                                        return cand
                                except Exception:
                                    pass
                    except Exception:
                        break
                # If only a Thumb is accessible, pick the one not matching brightness thumb if possible
                thumb = auto.ThumbControl(searchFromControl=container)
                if thumb and thumb.Exists(0, 0):
                    return thumb
            except Exception:
                pass
        return None
    except Exception:
        return None


def set_quick_slider(kind: str, percent: int) -> bool:
    """Set Quick Settings slider (brightness or volume) to a target percent via visible cursor movement."""
    try:
        import pyautogui
        import time
        import uiautomation as auto
    except Exception:
        return False
    kind_l = kind.lower().strip()
    pattern = r"(?i)\bbrightness\b" if kind_l == 'brightness' else r"(?i)\bvolume\b"

    if percent is None:
        return False
    target_percent = max(0, min(100, int(percent)))

    if not _open_quick_settings():
        return False

    # Record initial volume when adjusting volume to verify actual change
    initial_vol = None
    if kind_l == 'volume':
        try:
            from .system_controls import get_volume_percent
            initial_vol = get_volume_percent()
        except Exception:
            initial_vol = None

    # Fewer retries to avoid multiple clicks/loops
    max_attempts = 4 if kind_l == 'volume' else 6
    for attempt in range(max_attempts):
        slider = _find_volume_slider() if kind_l == 'volume' else _find_quick_slider(pattern)
        if slider and slider.Exists(0, 0):
            try:
                rect = slider.BoundingRectangle
                try:
                    left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
                except Exception:
                    left, top, right, bottom = rect[0], rect[1], rect[2], rect[3]
                width = max(1, right - left)
                y = int((top + bottom) / 2)
                x = int(left + (target_percent / 100.0) * width)
                # First try a click on the track
                pyautogui.moveTo(x, y, duration=max(0.0, settings.CURSOR_MOVE_DURATION))
                pyautogui.click()
                time.sleep(0.45)
                # Optional verification via system volume read when adjusting volume
                try:
                    if kind_l == 'volume':
                        from .system_controls import get_volume_percent
                        newp = get_volume_percent()
                        if newp is not None:
                            # success if close to target or moved at least a bit from initial
                            if abs(int(newp) - int(target_percent)) <= 5 or (initial_vol is not None and abs(int(newp) - int(initial_vol)) >= 2):
                                _close_quick_settings(); return True
                except Exception:
                    pass
                # If click didn't take, try dragging a thumb to target
                try:
                    parent = None
                    try:
                        parent = slider.GetParentControl()
                    except Exception:
                        parent = None
                    thumb = None
                    if parent:
                        try:
                            thumb = auto.ThumbControl(searchFromControl=parent)
                            if not (thumb and thumb.Exists(0, 0)):
                                thumb = None
                        except Exception:
                            thumb = None
                    if not thumb:
                        try:
                            thumb = auto.ThumbControl(searchFromControl=slider)
                            if not (thumb and thumb.Exists(0, 0)):
                                thumb = None
                        except Exception:
                            thumb = None
                    if thumb:
                        try:
                            trect = thumb.BoundingRectangle
                            try:
                                tx, ty = int((trect.left + trect.right) / 2), int((trect.top + trect.bottom) / 2)
                            except Exception:
                                tx, ty = int((trect[0] + trect[2]) / 2), int((trect[1] + trect[3]) / 2)
                            pyautogui.moveTo(tx, ty, duration=max(0.0, settings.CURSOR_MOVE_DURATION))
                            pyautogui.dragTo(x, y, duration=0.25)
                            time.sleep(0.4)
                            try:
                                if kind_l == 'volume':
                                    from .system_controls import get_volume_percent
                                    newp2 = get_volume_percent()
                                    if newp2 is not None:
                                        if abs(int(newp2) - int(target_percent)) <= 5 or (initial_vol is not None and abs(int(newp2) - int(initial_vol)) >= 2):
                                            _close_quick_settings(); return True
                            except Exception:
                                pass
                        except Exception:
                            pass
                except Exception:
                    pass
                # As a last resort, one more click; verify for volume, otherwise accept
                pyautogui.moveTo(x, y, duration=max(0.0, settings.CURSOR_MOVE_DURATION))
                pyautogui.click()
                time.sleep(0.3)
                if kind_l == 'volume':
                    try:
                        from .system_controls import get_volume_percent
                        newp3 = get_volume_percent()
                        if newp3 is not None and (abs(int(newp3) - int(target_percent)) <= 5 or (initial_vol is not None and abs(int(newp3) - int(initial_vol)) >= 2)):
                            _close_quick_settings(); return True
                    except Exception:
                        pass
                    # No verified change; keep trying outer loop
                else:
                    _close_quick_settings(); return True
            except Exception:
                time.sleep(0.4)
        else:
            time.sleep(0.35)
    _close_quick_settings()
    return False


def _open_settings_uri(uri: str) -> bool:
    try:
        import subprocess, time
        subprocess.Popen(["start", uri], shell=True)
        time.sleep(1.2)
        return True
    except Exception:
        return False


def _find_settings_toggle(label_patterns: str):
    """Find a toggle in the Settings app by label patterns.
    Tries ToggleButtonControl by regex name, then locates a nearby TextControl and finds a ToggleButton within the same parent.
    """
    try:
        import uiautomation as auto
        root = auto.GetRootControl()
        # Prefer foreground Settings window
        fg = None
        try:
            fg = auto.GetForegroundControl()
        except Exception:
            pass
        scopes = [c for c in [fg, root] if c]
        for scope in scopes:
            try:
                settings_win = auto.WindowControl(searchFromControl=scope, RegexName=r"(?i)settings")
                container = settings_win if settings_win and settings_win.Exists(0, 0) else scope
            except Exception:
                container = scope
            # 1) Direct toggle by label name
            try:
                tog = auto.ToggleButtonControl(searchFromControl=container, RegexName=label_patterns)
                if tog and tog.Exists(0, 0):
                    return tog
            except Exception:
                pass
            # 2) Find text label then sibling/descendant toggle
            try:
                label = auto.TextControl(searchFromControl=container, RegexName=label_patterns)
                if label and label.Exists(0, 0):
                    parent = label.GetParentControl()
                    if parent:
                        tog = auto.ToggleButtonControl(searchFromControl=parent)
                        if tog and tog.Exists(0, 0):
                            return tog
                        # try deeper search within parent subtree
                        tog = auto.ToggleButtonControl(searchFromControl=parent, foundIndex=1)
                        if tog and tog.Exists(0, 0):
                            return tog
            except Exception:
                pass
        return None
    except Exception:
        return None


def toggle_in_settings_page(kind: str, desired: Optional[bool]) -> bool:
    """Open the relevant Settings page and toggle a master switch like Bluetooth or Location using UIA + cursor.
    kind: 'bluetooth' | 'location'
    desired: True/False/None
    """
    kind_l = (kind or "").lower().strip()
    if kind_l == 'bluetooth':
        uri = 'ms-settings:bluetooth'
        label_patterns = r"(?i)\bbluetooth\b"
    elif kind_l == 'location':
        # Windows 11 uses "Location" or "Location services"
        uri = 'ms-settings:privacy-location'
        label_patterns = r"(?i)\blocation\b|\blocation\s*services\b"
    else:
        return False

    if not _open_settings_uri(uri):
        return False
    try:
        import time
        import uiautomation as auto
        time.sleep(1.2)
        # Try a few times in case UI loads lazily
        for _ in range(10):
            tog = _find_settings_toggle(label_patterns)
            if not tog:
                time.sleep(0.5)
                continue
            try:
                # Helper to verify state
                def _state_ok() -> Optional[bool]:
                    try:
                        tp = tog.GetTogglePattern()
                        if desired is None:
                            return True
                        return tp.CurrentToggleState == (1 if desired else 0)
                    except Exception:
                        return None

                # If already correct, done
                try:
                    if desired is not None:
                        tp0 = tog.GetTogglePattern()
                        if tp0.CurrentToggleState == (1 if desired else 0):
                            return True
                except Exception:
                    pass

                # Click and verify, with keyboard fallback
                clicked_once = False
                ok: Optional[bool] = None
                if _click_with_cursor(tog):
                    clicked_once = True
                    time.sleep(0.8)
                    ok = _state_ok()
                    if ok is True or ok is None:
                        return True
                if ok is False or not clicked_once:
                    try:
                        import pyautogui
                        tog.SetFocus()
                        time.sleep(0.1)
                        pyautogui.press('space')
                        time.sleep(0.6)
                        ok = _state_ok()
                        if ok is True or ok is None:
                            return True
                        pyautogui.press('enter')
                        time.sleep(0.6)
                        ok = _state_ok()
                        if ok is True or ok is None:
                            return True
                    except Exception:
                        pass
                if ok is False or not clicked_once:
                    if _click_with_cursor(tog):
                        time.sleep(0.7)
                        ok = _state_ok()
                        if ok is True or ok is None:
                            return True
            except Exception:
                time.sleep(0.5)
        return False
    except Exception:
        return False
def close_app(name: str) -> bool:
    """Close an application by name.
    
    Strategies:
    1. taskkill /IM (robust for known exe names).
    2. AppOpener (easy, broad support).
    3. alt+f4 (last resort for foreground).
    """
    if not name:
        return False
    
    import subprocess  # Ensure subprocess is imported locally
    
    # 1. Specialized handling for common requests
    lower = name.lower().strip()
    
    # Special override: WhatsApp (Alt+F4 per user request)
    if "whatsapp" in lower:
        try:
            import pyautogui, time
            if _try_focus_app_window(["whatsapp"]):
                time.sleep(0.5)
                pyautogui.hotkey('alt', 'f4')
                return True
        except Exception:
            pass

    # Map common names to process names for taskkill
    # Values can be a string or a list of strings
    proc_map = {
        "spotify": "Spotify.exe",
        # "whatsapp": ["WhatsApp.exe", "WhatsAppNative.exe"], # Removed to prevent force kill
        "chrome": "chrome.exe",
        "firefox": "firefox.exe",
        "edge": "msedge.exe",
        "notepad": "notepad.exe",
        "calculator": "CalculatorApp.exe",
        "teams": "Teams.exe",
        "discord": "Discord.exe",
        "vlc": "vlc.exe",
        "word": "WINWORD.EXE",
        "excel": "EXCEL.EXE",
        "powerpoint": "POWERPNT.EXE",
        "steamer": "steam.exe",
        "steam": "steam.exe",
    }
    
    target = proc_map.get(lower)
    terminated = False

    if target:
        targets = [target] if isinstance(target, str) else target
        for t in targets:
            try:
                # Run taskkill silently
                res = subprocess.run(
                    ["taskkill", "/f", "/im", t], 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL
                )
                if res.returncode == 0:
                    terminated = True
            except Exception:
                pass
    
    if terminated:
        return True

    # 2. Try AppOpener close
    try:
        from AppOpener import close
        # match_closest=True helps finding "google chrome" from "chrome"
        close(name, match_closest=True, output=False)
        return True
    except Exception:
        pass

    # 3. Fallback: if user says "close this" or "close app", try Alt+F4
    if lower in ["this", "current", "app", "window"]:
        try:
            import pyautogui
            pyautogui.hotkey('alt', 'f4')
            return True
        except Exception:
            pass
            
    return False
