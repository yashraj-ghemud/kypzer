from typing import Optional, Tuple
from urllib.parse import urlparse

import pyautogui


def _normalize_site(site: str) -> str:
    s = (site or "").strip()
    if not s:
        return s
    # If the user said just a name (twitter, youtube), treat as domain
    s = s.replace(" ", "")
    # Map a few common aliases to domains without being site-specific in behavior
    aliases = {
        "twitter": "x.com",
        "x": "x.com",
        "youtube": "youtube.com",
        "yt": "youtube.com",
        "google": "google.com",
        "reddit": "reddit.com",
        "facebook": "facebook.com",
        "fb": "facebook.com",
        "instagram": "instagram.com",
        "ig": "instagram.com",
    }
    s_lower = s.lower()
    domain = aliases.get(s_lower, s_lower)
    if "." not in domain:
        domain = domain + ".com"
    return domain


def _find_search_input(page) -> Optional[any]:
    # Try a variety of generic search selectors
    selectors = [
        'input[role="searchbox"]',
        'input[type="search"]',
        'input[aria-label*="search" i]',
        'input[placeholder*="search" i]',
        'input[name="q" i]',
        'textarea[aria-label*="search" i]',
        'textarea[placeholder*="search" i]',
        'form[role="search"] input',
    ]
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() > 0:
                return loc.first
        except Exception:
            continue
    return None


def _first_result_url_from_google(page) -> Optional[str]:
    # Prefer organic results: link with an h3 inside #search
    loc = page.locator('div#search a:has(h3)')
    try:
        if loc.count() == 0:
            loc = page.locator('#search a[href]')
        if loc.count() == 0:
            return None
        first_link = loc.first
        first_link.click()
        page.wait_for_load_state("domcontentloaded")
        return page.url
    except Exception:
        try:
            return page.url
        except Exception:
            return None


def _first_result_url_generic(page) -> Optional[str]:
    # Generic: click the first visible link inside <main>, else any link
    for sel in ["main a[href]", "a[href]"]:
        loc = page.locator(sel)
        try:
            if loc.count() > 0:
                loc.first.click()
                page.wait_for_load_state("domcontentloaded")
                return page.url
        except Exception:
            continue
    return None


def resolve_first_result(query: str, browser: Optional[str] = None, site: Optional[str] = None) -> Optional[str]:
    """
    Use Playwright headfully or headlessly to perform a search and return the URL of the first result.
    - If 'site' is provided, search within that site by going to its homepage and using its search box if found.
      If no search input is found, fall back to Google with site: filter.
    - If no 'site', use Google web search.

    Returns the destination URL to open in the user's browser. Returns None on failure.
    """
    try:
        # Import here to keep it optional
        from playwright.sync_api import sync_playwright
    except Exception:
        return None


def verify_navigated_non_search(url_hint: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """Optional Playwright probe: returns (title, url) if a non-search page is loaded in a temporary context.

    Used only when Playwright is available; returns None if playwright not installed or probe failed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # If we have a hint, navigate and check; otherwise just return None
            if not url_hint:
                try:
                    browser.close()
                except Exception:
                    pass
                return None
            page.goto(url_hint, wait_until="domcontentloaded")
            title = (page.title() or "").strip()
            url = page.url
            try:
                browser.close()
            except Exception:
                pass
            # Heuristic: non-search if not Google/YouTube search with 'search' or 'results' tokens
            low = (url or "").lower()
            if any(tok in low for tok in ["google.com/search", "youtube.com/results"]):
                return None
            return (title, url)
    except Exception:
        return None


def open_and_click_first(query: str, browser: Optional[str] = None, site: Optional[str] = None) -> bool:
    """Launch a real browser window, run the search, and click the first result.
    Keeps the browser open after clicking. Returns True on success.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False

    def _resolve_browser_exe(name: str) -> Optional[str]:
        import os, shutil
        n = (name or "").lower()
        path_in_path = shutil.which(f"{n}.exe") or shutil.which(n)
        if path_in_path:
            return path_in_path
        pf = os.environ.get("PROGRAMFILES", r"C:\\Program Files")
        pfx86 = os.environ.get("PROGRAMFILES(X86)", r"C:\\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", r"C:\\Users\\%USERNAME%\\AppData\\Local")
        candidates = []
        if n in {"brave"}:
            candidates += [
                os.path.join(pf, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                os.path.join(local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ]
        if n in {"chrome", "google"}:
            candidates += [
                os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(pfx86, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
            ]
        if n in {"edge", "msedge"}:
            candidates += [
                os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(pfx86, "Microsoft", "Edge", "Application", "msedge.exe"),
            ]
        if n in {"firefox", "mozilla"}:
            candidates += [
                os.path.join(pf, "Mozilla Firefox", "firefox.exe"),
                os.path.join(pfx86, "Mozilla Firefox", "firefox.exe"),
            ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    site_domain = _normalize_site(site) if site else None

    try:
        with sync_playwright() as p:
            bname = (browser or "").lower()
            launch_args = {"headless": False}
            browser_type = None
            channel = None
            exe_path = None
            if bname in {"firefox", "mozilla"}:
                browser_type = p.firefox
                exe_path = _resolve_browser_exe("firefox")
            elif bname in {"edge", "msedge"}:
                browser_type = p.chromium
                channel = "msedge"
                exe_path = _resolve_browser_exe("msedge")
            elif bname in {"chrome", "google"}:
                browser_type = p.chromium
                channel = "chrome"
                exe_path = _resolve_browser_exe("chrome")
            elif bname in {"brave"}:
                browser_type = p.chromium
                exe_path = _resolve_browser_exe("brave")
            else:
                browser_type = p.chromium
            if channel:
                launch_args["channel"] = channel
            if exe_path:
                launch_args["executable_path"] = exe_path

            browser_obj = browser_type.launch(**launch_args)
            context = browser_obj.new_context()
            page = context.new_page()
            page.set_default_timeout(20000)

            def _google_query(q: str):
                page.goto("https://www.google.com/", wait_until="domcontentloaded")
                si = _find_search_input(page)
                if not si:
                    return False
                si.click()
                si.fill(q)
                si.press("Enter")
                page.wait_for_load_state("domcontentloaded")
                return True

            success = False
            if site_domain:
                # try on-site search
                try:
                    page.goto(f"https://{site_domain}/", wait_until="domcontentloaded")
                    si = _find_search_input(page)
                    if si:
                        si.click(); si.fill(query); si.press("Enter")
                        page.wait_for_load_state("domcontentloaded")
                        success = True
                except Exception:
                    success = False
                if not success:
                    success = _google_query(f"site:{site_domain} {query}")
            else:
                success = _google_query(query)

            if not success:
                return False

            # Try to click first organic result
            try:
                # Prefer organic result cards in Google; handle YouTube when applicable
                first_link = None
                if site_domain and "youtube" in site_domain:
                    loc = page.locator('ytd-video-renderer a#video-title')
                    if loc.count() > 0:
                        first_link = loc.first
                if not first_link:
                    loc = page.locator('div#search .g a:has(h3)')
                    if loc.count() == 0:
                        loc = page.locator('#search a[href]')
                    if loc.count() > 0:
                        first_link = loc.first
                if not first_link:
                    return False
                # Prefer DOM interactions: hover, then click
                first_link.scroll_into_view_if_needed()
                try:
                    first_link.hover()
                except Exception:
                    pass
                try:
                    first_link.click()
                except Exception:
                    # As a last resort, use screen-based click at the element center
                    try:
                        box = first_link.bounding_box()
                        if box:
                            cx = int(box["x"] + box["width"] / 2)
                            cy = int(box["y"] + box["height"] / 2)
                            pyautogui.moveTo(cx, cy, duration=0.25)
                            pyautogui.click()
                        else:
                            raise RuntimeError("no bounding box")
                    except Exception:
                        # Final fallback: attempt generic click
                        page.locator('a[href]').first.click()
                page.wait_for_load_state("domcontentloaded")
                return True
            except Exception:
                try:
                    # Generic fallback
                    page.locator('a[href]').first.click()
                    page.wait_for_load_state("domcontentloaded")
                    return True
                except Exception:
                    return False
    except Exception:
        return False

    site_domain = _normalize_site(site) if site else None

    try:
        with sync_playwright() as p:
            # Choose engine based on requested browser; default to Chromium
            bname = (browser or "").lower()
            launch_args = {"headless": True}
            browser_type = None
            channel = None
            if bname in {"firefox", "mozilla"}:
                browser_type = p.firefox
            elif bname in {"edge", "msedge"}:
                browser_type = p.chromium
                channel = "msedge"
            elif bname in {"chrome", "google", "brave"}:
                browser_type = p.chromium
                channel = "chrome" if bname != "brave" else None
            else:
                browser_type = p.chromium

            if channel:
                launch_args["channel"] = channel

            browser_obj = browser_type.launch(**launch_args)
            page = browser_obj.new_page()

            if site_domain:
                # Try on-site search first
                try:
                    page.goto(f"https://{site_domain}/", wait_until="domcontentloaded", timeout=20000)
                    search_input = _find_search_input(page)
                    if search_input:
                        search_input.click()
                        search_input.fill(query)
                        search_input.press("Enter")
                        page.wait_for_load_state("domcontentloaded")
                        # Click first result on the site
                        url = _first_result_url_generic(page)
                        if url:
                            try:
                                browser_obj.close()
                            except Exception:
                                pass
                            return url
                except Exception:
                    pass
                # Fallback to Google with site: filter
                page.goto("https://www.google.com/", wait_until="domcontentloaded")
                si = _find_search_input(page)
                if si:
                    si.click()
                    si.fill(f"site:{site_domain} {query}")
                    si.press("Enter")
                    page.wait_for_load_state("domcontentloaded")
                    url = _first_result_url_from_google(page)
                    try:
                        browser_obj.close()
                    except Exception:
                        pass
                    return url
                try:
                    browser_obj.close()
                except Exception:
                    pass
                return None

            # No site: search on Google
            page.goto("https://www.google.com/", wait_until="domcontentloaded")
            si = _find_search_input(page)
            if not si:
                try:
                    browser_obj.close()
                except Exception:
                    pass
                return None
            si.click()
            si.fill(query)
            si.press("Enter")
            page.wait_for_load_state("domcontentloaded")
            url = _first_result_url_from_google(page)
            try:
                browser_obj.close()
            except Exception:
                pass
            return url
    except Exception:
        return None
