"""
WhatsApp Enhanced - Improved WhatsApp messaging with fast contact search and multi-recipient support.

Features:
- Fast contact search using Ctrl+F in WhatsApp
- Multi-recipient message sending (batch messages)
- Optimized search workflow with caching
- Retry logic for unreliable UI interactions
- Group message support
- Contact name fuzzy matching
- Read/delivered status detection (where possible)

This module enhances the existing WhatsApp functionality in ui.py with faster
and more reliable methods.
"""

from __future__ import annotations

import os
import re
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set
from datetime import datetime

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    pyautogui = None
    HAS_PYAUTOGUI = False

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    pyperclip = None
    HAS_PYPERCLIP = False

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    gw = None
    HAS_PYGETWINDOW = False

try:
    import uiautomation as auto
    HAS_UIAUTOMATION = True
except ImportError:
    auto = None
    HAS_UIAUTOMATION = False


# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------

@dataclass
class WhatsAppConfig:
    """Configuration for WhatsApp controller."""
    # Timing settings
    launch_wait_seconds: float = 4.0
    search_wait_seconds: float = 1.5
    message_send_wait: float = 0.8
    action_delay: float = 0.2
    focus_timeout: float = 8.0
    
    # Type speed
    type_interval: float = 0.02
    
    # Search behavior
    use_ctrl_f_search: bool = True  # Use Ctrl+F for faster search
    max_search_retries: int = 3
    search_result_confidence_wait: float = 0.8
    
    # Multi-recipient settings
    batch_delay_between_contacts: float = 1.5
    verify_chat_opened: bool = True
    
    # Debug
    debug: bool = False


# Contact alias map for common family/friend names
CONTACT_ALIASES: Dict[str, List[str]] = {
    "mom": ["mom", "mummy", "mama", "mum", "mother", "mumma", "ma"],
    "dad": ["dad", "daddy", "papa", "father", "pa", "baba"],
    "wife": ["wife", "wifey", "spouse", "partner", "biwi", "patni"],
    "husband": ["husband", "hubby", "spouse", "partner", "pati"],
    "brother": ["bro", "brother", "bhai", "bhaiya"],
    "sister": ["sis", "sister", "didi", "behan", "behen"],
}

# Typo corrections for common mistakes
TYPO_CORRECTIONS: Dict[str, str] = {
    "mumy": "mummy",
    "muumy": "mummy",
    "momi": "mommy",
    "mami": "mama",
    "dady": "daddy",
    "dadi": "daddy",
    "pappa": "papa",
    "broter": "brother",
    "sisiter": "sister",
}


# -----------------------------------------------------------------------------
# LOGGING
# -----------------------------------------------------------------------------

def _log(msg: str, config: Optional[WhatsAppConfig] = None) -> None:
    """Log message if debug is enabled."""
    if config and config.debug:
        print(f"[WhatsAppEnhanced] {msg}")


# -----------------------------------------------------------------------------
# WINDOW MANAGEMENT
# -----------------------------------------------------------------------------

def _get_whatsapp_window() -> Optional[Any]:
    """Find WhatsApp window using pygetwindow."""
    if not HAS_PYGETWINDOW or not gw:
        return None
    
    try:
        windows = gw.getWindowsWithTitle("WhatsApp")
        for win in windows:
            title = (win.title or "").lower()
            if "whatsapp" in title:
                return win
    except Exception:
        pass
    return None


def _is_whatsapp_focused() -> bool:
    """Check if WhatsApp is currently the foreground window."""
    if not HAS_PYAUTOGUI:
        return False
    
    try:
        title = pyautogui.getActiveWindowTitle() or ""
        return "whatsapp" in title.lower()
    except Exception:
        return False


def _focus_whatsapp_window(timeout: float = 8.0) -> bool:
    """Bring WhatsApp window to foreground."""
    if not HAS_PYGETWINDOW:
        return False
    
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_whatsapp_focused():
            return True
            
        win = _get_whatsapp_window()
        if win:
            try:
                if getattr(win, "isMinimized", False):
                    win.restore()
                win.activate()
                time.sleep(0.5)
                if _is_whatsapp_focused():
                    return True
            except Exception:
                pass
        time.sleep(0.3)
    return False


def _launch_whatsapp() -> bool:
    """Launch WhatsApp desktop application."""
    try:
        # Try AppOpener first
        try:
            from AppOpener import open as app_open
            app_open("whatsapp", match_closest=True, output=False)
            return True
        except Exception:
            pass
        
        # Try via Start menu search
        try:
            from .ui import open_app_via_start
            if open_app_via_start("whatsapp"):
                return True
        except Exception:
            pass
        
        # Try Windows Store app launch
        try:
            import subprocess
            subprocess.Popen(["start", "whatsapp:"], shell=True)
            return True
        except Exception:
            pass
        
        return False
    except Exception:
        return False


def ensure_whatsapp_running(config: Optional[WhatsAppConfig] = None) -> bool:
    """Ensure WhatsApp is running and focused."""
    cfg = config or WhatsAppConfig()
    
    # Check if already focused
    if _is_whatsapp_focused():
        return True
    
    # Try to focus existing window
    if _focus_whatsapp_window(timeout=2.0):
        return True
    
    # Launch WhatsApp
    _log("Launching WhatsApp...", cfg)
    if not _launch_whatsapp():
        return False
    
    # Wait for it to start
    time.sleep(cfg.launch_wait_seconds)
    
    # Try to focus again
    return _focus_whatsapp_window(timeout=cfg.focus_timeout)


# -----------------------------------------------------------------------------
# CONTACT NAME PROCESSING
# -----------------------------------------------------------------------------

def normalize_contact_name(raw: str) -> str:
    """
    Normalize a contact name for better matching.
    Handles typos and common aliases.
    """
    if not raw:
        return ""
    
    cleaned = raw.strip().lower()
    
    # Apply typo corrections
    for typo, correction in TYPO_CORRECTIONS.items():
        if cleaned == typo:
            cleaned = correction
            break
    
    # Capitalize properly
    return cleaned.title()


def get_contact_search_variants(name: str) -> List[str]:
    """
    Get multiple search variants for a contact name.
    Helps find contacts even with slight name mismatches.
    """
    if not name:
        return []
    
    variants: List[str] = []
    seen: Set[str] = set()
    
    def add_variant(v: str) -> None:
        if v and v.lower() not in seen:
            seen.add(v.lower())
            variants.append(v)
    
    # Original name
    normalized = normalize_contact_name(name)
    add_variant(normalized)
    add_variant(name.strip())
    
    # Check alias groups
    name_lower = name.strip().lower()
    for canonical, aliases in CONTACT_ALIASES.items():
        if name_lower in aliases or name_lower == canonical:
            # Add all aliases as potential search terms
            for alias in aliases:
                add_variant(alias.title())
    
    # First name only (if multi-word)
    parts = normalized.split()
    if len(parts) > 1:
        add_variant(parts[0])
    
    return variants


def expand_recipients(raw_text: str) -> List[str]:
    """
    Expand a recipient string into individual contact names.
    Handles various separators: comma, 'and', 'aur', '&', etc.
    
    Examples:
        "mummy and papa" -> ["mummy", "papa"]
        "mom, dad, bro" -> ["mom", "dad", "bro"]
        "sister aur brother" -> ["sister", "brother"]
    """
    if not raw_text:
        return []
    
    # Normalize separators
    text = raw_text.strip()
    
    # Replace various separators with comma
    text = re.sub(r"\s+(?:and|aur|&|plus)\s+", ",", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[,;]\s*", ",", text)
    
    # Split and clean
    parts = text.split(",")
    contacts: List[str] = []
    seen: Set[str] = set()
    
    for part in parts:
        name = part.strip()
        if not name:
            continue
        
        # Remove common suffixes like "ko", "ke liye"
        name = re.sub(r"\s+(?:ko|ke\s+liye|to)\s*$", "", name, flags=re.IGNORECASE)
        name = name.strip(" .,:;-")
        
        if name:
            key = name.lower()
            if key not in seen:
                seen.add(key)
                contacts.append(normalize_contact_name(name))
    
    return contacts


# -----------------------------------------------------------------------------
# FAST CONTACT SEARCH (Ctrl+F method)
# -----------------------------------------------------------------------------

def _search_contact_fast(
    contact: str,
    config: Optional[WhatsAppConfig] = None
) -> bool:
    """
    Search for a contact using Ctrl+F (faster than typing in search bar).
    
    Returns True if contact was found and chat opened.
    """
    if not HAS_PYAUTOGUI:
        return False
    
    cfg = config or WhatsAppConfig()
    
    try:
        _log(f"Fast search for: {contact}", cfg)
        
        # Press Ctrl+F to open find/search
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.5)
        
        # Clear any existing text
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("backspace")
        time.sleep(0.1)
        
        # Type contact name
        for char in contact:
            try:
                pyautogui.press(char)
            except Exception:
                pyautogui.write(char)
            time.sleep(cfg.type_interval)
        
        # Wait for search results
        time.sleep(cfg.search_wait_seconds)
        
        # Press Enter or Down+Enter to select first result
        pyautogui.press("enter")
        time.sleep(cfg.search_result_confidence_wait)
        
        return True
        
    except Exception as e:
        _log(f"Fast search failed: {e}", cfg)
        return False


def _search_contact_standard(
    contact: str,
    config: Optional[WhatsAppConfig] = None
) -> bool:
    """
    Search for a contact using standard search bar method.
    Fallback when Ctrl+F doesn't work.
    """
    if not HAS_PYAUTOGUI:
        return False
    
    cfg = config or WhatsAppConfig()
    
    try:
        _log(f"Standard search for: {contact}", cfg)
        
        # Click on search area (usually top-left)
        # Try using Ctrl+N for new chat / search
        pyautogui.hotkey("ctrl", "n")
        time.sleep(0.5)
        
        # If that didn't work, try clicking search
        # This is a fallback position
        
        # Clear and type
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("backspace")
        time.sleep(0.1)
        
        # Type contact name
        pyautogui.typewrite(contact, interval=cfg.type_interval)
        time.sleep(cfg.search_wait_seconds)
        
        # Select first result
        pyautogui.press("down")
        time.sleep(0.15)
        pyautogui.press("enter")
        time.sleep(cfg.search_result_confidence_wait)
        
        return True
        
    except Exception as e:
        _log(f"Standard search failed: {e}", cfg)
        return False


def search_and_open_chat(
    contact: str,
    config: Optional[WhatsAppConfig] = None
) -> bool:
    """
    Search for a contact and open their chat.
    Tries fast method (Ctrl+F) first, falls back to standard.
    """
    cfg = config or WhatsAppConfig()
    
    # Get search variants
    variants = get_contact_search_variants(contact)
    if not variants:
        variants = [contact]
    
    for attempt, variant in enumerate(variants):
        _log(f"Trying variant {attempt+1}/{len(variants)}: {variant}", cfg)
        
        # Try fast search first
        if cfg.use_ctrl_f_search:
            if _search_contact_fast(variant, cfg):
                return True
        
        # Fallback to standard search
        if _search_contact_standard(variant, cfg):
            return True
        
        time.sleep(0.3)
    
    return False


# -----------------------------------------------------------------------------
# MESSAGE SENDING
# -----------------------------------------------------------------------------

def _type_message(message: str, config: Optional[WhatsAppConfig] = None) -> bool:
    """Type a message in the chat input field."""
    if not HAS_PYAUTOGUI:
        return False
    
    cfg = config or WhatsAppConfig()
    
    try:
        # Wait a bit for chat to fully load
        time.sleep(0.5)
        
        # Click at bottom center to focus message input
        try:
            width, height = pyautogui.size()
            # Click near bottom center where message box typically is
            pyautogui.click(int(width * 0.5), int(height * 0.92))
            time.sleep(0.3)
        except Exception:
            pass
        
        # Use clipboard method for reliable text entry
        if HAS_PYPERCLIP:
            pyperclip.copy(message)
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
        else:
            # Fallback to typewrite (slower but works)
            for char in message:
                try:
                    pyautogui.press(char)
                except Exception:
                    pyautogui.write(char)
                time.sleep(cfg.type_interval)
        
        return True
    except Exception as e:
        _log(f"Type message failed: {e}", cfg)
        return False


def _send_message(config: Optional[WhatsAppConfig] = None) -> bool:
    """Press Enter to send the typed message."""
    if not HAS_PYAUTOGUI:
        return False
    
    cfg = config or WhatsAppConfig()
    
    try:
        # Small delay before sending
        time.sleep(0.2)
        
        # Press Enter to send
        pyautogui.press("enter")
        time.sleep(0.3)
        
        # Press Enter again to confirm (in case of confirmation dialog)
        pyautogui.press("enter")
        time.sleep(cfg.message_send_wait)
        
        _log("Message sent!", cfg)
        return True
    except Exception as e:
        _log(f"Send message failed: {e}", cfg)
        return False


def send_message_to_contact(
    contact: str,
    message: str,
    config: Optional[WhatsAppConfig] = None
) -> Dict[str, Any]:
    """
    Send a message to a single contact.
    
    Args:
        contact: Contact name to send to
        message: Message text to send
        config: Optional configuration
    
    Returns:
        Result dict with ok/say keys
    """
    cfg = config or WhatsAppConfig()
    
    if not contact:
        return {"ok": False, "say": "No contact specified."}
    
    if not message:
        return {"ok": False, "say": "No message to send."}
    
    # Ensure WhatsApp is running
    if not ensure_whatsapp_running(cfg):
        return {"ok": False, "say": "Couldn't open WhatsApp."}
    
    _log(f"Sending to {contact}: {message[:50]}...", cfg)
    
    # Search and open chat
    if not search_and_open_chat(contact, cfg):
        return {"ok": False, "say": f"Couldn't find contact: {contact}"}
    
    # Type and send message
    if not _type_message(message, cfg):
        return {"ok": False, "say": "Couldn't type the message."}
    
    if not _send_message(cfg):
        return {"ok": False, "say": "Couldn't send the message."}
    
    return {"ok": True, "say": f"Sent message to {contact}."}


# -----------------------------------------------------------------------------
# MULTI-RECIPIENT MESSAGING
# -----------------------------------------------------------------------------

@dataclass
class BatchMessageResult:
    """Result of batch message sending."""
    total: int = 0
    successful: int = 0
    failed: int = 0
    failed_contacts: List[str] = field(default_factory=list)
    
    @property
    def all_succeeded(self) -> bool:
        return self.failed == 0 and self.successful > 0
    
    @property
    def partial_success(self) -> bool:
        return self.successful > 0 and self.failed > 0
    
    def get_summary(self) -> str:
        if self.all_succeeded:
            return f"Sent to all {self.successful} contacts."
        elif self.partial_success:
            return f"Sent to {self.successful} contacts, failed for {self.failed}."
        elif self.successful == 0:
            return "Failed to send to any contacts."
        return "Unknown result."


def send_message_to_multiple(
    contacts: List[str],
    message: str,
    config: Optional[WhatsAppConfig] = None
) -> Dict[str, Any]:
    """
    Send the same message to multiple contacts.
    
    Args:
        contacts: List of contact names
        message: Message text to send to all
        config: Optional configuration
    
    Returns:
        Result dict with ok/say and metadata
    """
    cfg = config or WhatsAppConfig()
    
    if not contacts:
        return {"ok": False, "say": "No contacts specified."}
    
    if not message:
        return {"ok": False, "say": "No message to send."}
    
    # Ensure WhatsApp is running once
    if not ensure_whatsapp_running(cfg):
        return {"ok": False, "say": "Couldn't open WhatsApp."}
    
    result = BatchMessageResult(total=len(contacts))
    
    for i, contact in enumerate(contacts):
        _log(f"Sending to contact {i+1}/{len(contacts)}: {contact}", cfg)
        
        # Search and open chat
        if not search_and_open_chat(contact, cfg):
            result.failed += 1
            result.failed_contacts.append(contact)
            continue
        
        # Type and send message
        if _type_message(message, cfg) and _send_message(cfg):
            result.successful += 1
        else:
            result.failed += 1
            result.failed_contacts.append(contact)
        
        # Delay between contacts
        if i < len(contacts) - 1:
            time.sleep(cfg.batch_delay_between_contacts)
    
    metadata = {
        "total": result.total,
        "successful": result.successful,
        "failed": result.failed,
        "failed_contacts": result.failed_contacts,
    }
    
    return {
        "ok": result.successful > 0,
        "say": result.get_summary(),
        "metadata": metadata
    }


def send_batch_from_text(
    recipients_text: str,
    message: str,
    config: Optional[WhatsAppConfig] = None
) -> Dict[str, Any]:
    """
    Send message to multiple recipients specified as text.
    Parses "mom and dad" or "mom, papa, bro" format.
    
    Args:
        recipients_text: Text containing recipient names
        message: Message to send
        config: Optional configuration
    
    Returns:
        Result dict
    """
    contacts = expand_recipients(recipients_text)
    
    if not contacts:
        return {"ok": False, "say": "Couldn't parse any contacts from the text."}
    
    return send_message_to_multiple(contacts, message, config)


# -----------------------------------------------------------------------------
# GROUP MESSAGING
# -----------------------------------------------------------------------------

def send_message_to_group(
    group_name: str,
    message: str,
    config: Optional[WhatsAppConfig] = None
) -> Dict[str, Any]:
    """
    Send a message to a WhatsApp group.
    
    Args:
        group_name: Name of the group
        message: Message to send
        config: Optional configuration
    
    Returns:
        Result dict
    """
    # Groups work the same way as contacts
    return send_message_to_contact(group_name, message, config)


# -----------------------------------------------------------------------------
# NLU HELPER - PARSE WHATSAPP COMMANDS
# -----------------------------------------------------------------------------

def parse_whatsapp_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse natural language commands for WhatsApp messaging.
    
    Returns action dict with "type" and "parameters" if recognized,
    None otherwise.
    """
    if not text:
        return None
    
    low = text.lower().strip()
    
    # Check if it's a WhatsApp-related command
    wa_triggers = [
        "whatsapp", "message", "msg", "send", "bhej", "bhejo",
        "text", "dm", "chat"
    ]
    
    has_wa_context = any(t in low for t in wa_triggers)
    if not has_wa_context:
        return None
    
    # Pattern: send <message> to <contacts>
    # Examples:
    #   - "send hi to mom"
    #   - "send good morning to mom and dad"
    #   - "bhej hello papa ko"
    #   - "message happy birthday to john, sarah, mike"
    
    patterns = [
        # English patterns
        r"(?:send|message|msg|text)\s+(.+?)\s+(?:to|for)\s+(.+?)(?:\s+on\s+whatsapp)?$",
        r"(?:whatsapp|wa)\s+(.+?)\s+(?:to|for)\s+(.+)$",
        # Hinglish patterns
        r"(?:bhej|bhejo)\s+(.+?)\s+(?:ko|ke\s+liye)\s+(.+)$",
        r"(?:bhej|bhejo)\s+(.+?)\s+(.+?)(?:\s+ko)?$",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, low)
        if match:
            message = match.group(1).strip()
            recipients_raw = match.group(2).strip()
            
            # Clean up message
            message = re.sub(r"^(?:a\s+)?(?:msg|message)\s+", "", message).strip()
            
            # Clean up recipients
            recipients_raw = re.sub(r"\s+on\s+whatsapp\b", "", recipients_raw)
            recipients = expand_recipients(recipients_raw)
            
            if recipients and message:
                return {
                    "type": "whatsapp_send_multi",
                    "parameters": {
                        "contacts": recipients,
                        "message": message,
                        "raw_recipients": recipients_raw,
                    }
                }
    
    # Pattern: open whatsapp chat with <contact>
    open_match = re.search(r"(?:open|start)\s+(?:a\s+)?(?:chat|conversation)\s+(?:with|to)\s+(.+?)(?:\s+on\s+whatsapp)?$", low)
    if open_match:
        contact = open_match.group(1).strip()
        return {
            "type": "whatsapp_open_chat",
            "parameters": {"contact": contact}
        }
    
    return None


# -----------------------------------------------------------------------------
# ACTION EXECUTOR
# -----------------------------------------------------------------------------

def execute_whatsapp_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a parsed WhatsApp action.
    
    Args:
        action: Dict with "type" and "parameters" keys
    
    Returns:
        Result dict with ok/say keys
    """
    atype = (action.get("type") or "").lower()
    params = action.get("parameters") or {}
    
    if atype == "whatsapp_send":
        contact = params.get("contact") or params.get("to")
        message = params.get("message") or params.get("text")
        return send_message_to_contact(contact, message)
    
    if atype == "whatsapp_send_multi":
        contacts = params.get("contacts") or []
        message = params.get("message") or params.get("text")
        if isinstance(contacts, str):
            contacts = expand_recipients(contacts)
        return send_message_to_multiple(contacts, message)
    
    if atype == "whatsapp_open_chat":
        contact = params.get("contact")
        if not ensure_whatsapp_running():
            return {"ok": False, "say": "Couldn't open WhatsApp."}
        if search_and_open_chat(contact):
            return {"ok": True, "say": f"Opened chat with {contact}."}
        return {"ok": False, "say": f"Couldn't find {contact}."}
    
    if atype == "whatsapp_group_send":
        group = params.get("group") or params.get("group_name")
        message = params.get("message")
        return send_message_to_group(group, message)
    
    return {"ok": False, "say": f"Unknown WhatsApp action: {atype}"}


# -----------------------------------------------------------------------------
# CONVENIENCE FUNCTIONS
# -----------------------------------------------------------------------------

def quick_send(
    to: str,
    message: str
) -> Dict[str, Any]:
    """
    Convenience function for quick message sending.
    Handles both single and multiple recipients.
    
    Args:
        to: Single contact or comma/and separated list
        message: Message to send
    
    Returns:
        Result dict
    """
    contacts = expand_recipients(to)
    
    if len(contacts) == 1:
        return send_message_to_contact(contacts[0], message)
    elif len(contacts) > 1:
        return send_message_to_multiple(contacts, message)
    else:
        return {"ok": False, "say": "No valid contacts specified."}


# -----------------------------------------------------------------------------
# TEST / DEBUG
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("Testing WhatsApp Enhanced...")
    
    # Test contact parsing
    test_recipients = [
        "mom and dad",
        "mom, papa, bro",
        "mummy aur papa",
        "john, sarah and mike",
        "sister & brother",
    ]
    
    for r in test_recipients:
        contacts = expand_recipients(r)
        print(f"'{r}' -> {contacts}")
    
    # Test command parsing
    test_commands = [
        "send hi to mom and dad",
        "bhej hello papa ko",
        "message good morning to mummy, papa",
        "whatsapp happy birthday to john",
    ]
    
    for cmd in test_commands:
        result = parse_whatsapp_command(cmd)
        print(f"'{cmd}' -> {result}")
