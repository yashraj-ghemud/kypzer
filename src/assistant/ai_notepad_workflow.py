"""Comprehensive AI Notepad workflow orchestration utilities.

This module centralises every step required to fulfil the user's request of
"write <topic> in Notepad with AI". The intent is to be extremely defensive
around UI automation on Windows, handle slow or inconsistent browser responses,
and provide detailed telemetry so failures can be diagnosed easily.

The design goals are:
- Precise control over the ChatGPT browser automation lifecycle.
- Adaptive waiting with multiple heuristics to determine response completion.
- Multiple safety checks before copying any generated content.
- Extensive cleaning and scoring of the collected text.
- Reliable Notepad automation with validation that the text was actually typed.
- Rich telemetry metadata returned to the caller for logging or analytics.

The code is intentionally verbose to cover the large set of edge cases observed
in production. This file is long by design: it encodes guard rails, retry
policies, diagnostics, and helpers in a single place so other modules can stay
minimal.
"""

from __future__ import annotations

import math
import os
import random
import re
import statistics
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pyautogui

try:
    import pyperclip
except Exception:  # pragma: no cover - clipboard library optional at runtime
    pyperclip = None  # type: ignore

try:
    from PIL import ImageGrab  # type: ignore
except Exception:  # pragma: no cover
    ImageGrab = None  # type: ignore

__all__ = [
    "ChatGPTAutomationError",
    "BrowserOpenError",
    "PromptSubmissionError",
    "ResponseCollectionError",
    "NotepadAutomationError",
    "WorkflowConfig",
    "WorkflowResult",
    "AINotepadWorkflow",
]


# ============================================================================
# Exceptions
# ============================================================================


class ChatGPTAutomationError(RuntimeError):
    """Base error for ChatGPT automation failures."""


class BrowserOpenError(ChatGPTAutomationError):
    """Raised when the ChatGPT web page could not be opened or focused."""


class PromptSubmissionError(ChatGPTAutomationError):
    """Raised when the prompt box could not be focused or text could not be submitted."""


class ResponseCollectionError(ChatGPTAutomationError):
    """Raised when the assistant failed to collect ChatGPT output."""


class NotepadAutomationError(RuntimeError):
    """Raised when Notepad operations fail."""


# ============================================================================
# Enumerations and data classes
# ============================================================================


class Stage(Enum):
    """High-level stages for telemetry."""

    PREPARE = auto()
    OPEN_BROWSER = auto()
    SUBMIT_PROMPT = auto()
    WAIT_FOR_RESPONSE = auto()
    COPY_RESPONSE = auto()
    CLEAN_RESPONSE = auto()
    OPEN_NOTEPAD = auto()
    WRITE_NOTEPAD = auto()
    VALIDATE_CONTENT = auto()
    COMPLETE = auto()
    FAILED = auto()


class ResponseStatus(Enum):
    """Result classification for content collection."""

    EMPTY = auto()
    INCOMPLETE = auto()
    COMPLETE = auto()
    LOW_QUALITY = auto()
    HIGH_QUALITY = auto()


class CleaningRule(Enum):
    """Classification of string cleaning rules."""

    STRIP_DISCLAIMER = auto()
    STRIP_PAGE_CHROME = auto()
    STRIP_HEADING = auto()
    STRIP_PROMPT_REF = auto()
    STRIP_CONVERSATION_HEADER = auto()
    STRIP_PROMPT_TEMPLATE = auto()
    TRIM_BLANK_LINES = auto()
    COLLAPSE_WHITESPACE = auto()
    KEEP_RELEVANT = auto()
    LIMIT_LENGTH = auto()
    NORMALISE_BULLETS = auto()
    ENSURE_SENTENCE_CASE = auto()


class NotepadWriteMode(Enum):
    """Strategies for writing into Notepad."""

    TYPEWRITE = auto()
    PASTE = auto()
    PASTE_THEN_TYPE = auto()


@dataclass
class TelemetryEvent:
    """Telemetry record emitted for each workflow stage."""

    stage: Stage
    ok: bool
    started_at: float
    finished_at: float
    message: str = ""
    attempts: int = 1
    payload: Dict[str, Any] = field(default_factory=dict)

    def duration(self) -> float:
        return max(0.0, self.finished_at - self.started_at)


@dataclass
class WaitSnapshot:
    """Record captured while waiting for ChatGPT response."""

    timestamp: float
    char_count: int
    line_count: int
    word_count: int
    sample: str


@dataclass
class ResponseQuality:
    """Details about the collected response quality."""

    status: ResponseStatus
    reasons: List[str] = field(default_factory=list)
    relevance_score: float = 0.0
    coherence_score: float = 0.0
    bullet_ratio: float = 0.0
    reading_time_seconds: float = 0.0
    cleaned_length: int = 0

    def is_success(self) -> bool:
        return self.status in {ResponseStatus.COMPLETE, ResponseStatus.HIGH_QUALITY}


@dataclass
class WorkflowConfig:
    """Runtime configuration for the workflow."""

    prompt_template: str = (
        "Please write concise, friendly notes about {topic}. "
        "Use 5-9 bullet points or short paragraphs with tips and examples. "
        "Avoid disclaimers, headings, markdown, or repetition."
    )
    boot_wait_seconds: float = 6.0
    base_wait_seconds: float = 24.0
    max_wait_seconds: float = 54.0
    wait_poll_seconds: float = 1.2
    wait_stable_threshold: float = 3
    wait_minimum_growth: int = 12
    copy_retries: int = 4
    scroll_attempts: int = 3
    preferred_browser: Optional[str] = None
    browser_open_callable: Optional[Callable[[str], bool]] = None
    logger: Optional[Callable[[str], None]] = None
    notepad_open_callable: Optional[Callable[[str], bool]] = None
    typing_interval: float = 0.01
    typing_heading_interval: float = 0.02
    paste_shortcut: Tuple[str, str] = ("ctrl", "v")
    select_all_shortcut: Tuple[str, str] = ("ctrl", "a")
    copy_shortcut: Tuple[str, str] = ("ctrl", "c")
    clear_shortcut: Tuple[str, ...] = ("ctrl", "a")
    delete_shortcut: Tuple[str, ...] = ("backspace",)
    minimum_topic_length: int = 3
    quality_min_words: int = 40
    quality_min_sentences: int = 3
    quality_min_bullets: int = 2
    quality_max_chars: int = 4000
    enable_quality_scoring: bool = True
    enable_notepad_validation: bool = True
    allow_paste_mode: bool = True
    random_seed: Optional[int] = None


@dataclass
class WorkflowResult:
    """Returned to the caller on completion."""

    ok: bool
    topic: str
    cleaned_text: str
    quality: ResponseQuality
    telemetry: List[TelemetryEvent]
    snapshots: List[WaitSnapshot]
    raw_text: str = ""
    note_written: bool = False
    write_mode: Optional[NotepadWriteMode] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        quality_tag = self.quality.status.name
        length = len(self.cleaned_text)
        return f"Workflow ok={self.ok} topic='{self.topic}' quality={quality_tag} length={length}"


@dataclass
class ResponseHeuristic:
    """Helper structure for heuristics evaluation."""

    name: str
    weight: float
    score: float
    threshold: float
    passed: bool
    note: str = ""


@dataclass
class NotepadValidation:
    """Validation details when writing into Notepad."""

    expected_chars: int
    observed_chars: int
    verified: bool
    mode: NotepadWriteMode
    attempts: int = 1
    extra_info: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Utility helpers
# ============================================================================


def _now() -> float:
    return time.monotonic()


def _log(config: WorkflowConfig, text: str) -> None:
    if config.logger:
        try:
            config.logger(text)
        except Exception:
            pass


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _mean(values: Sequence[float], fallback: float = 0.0) -> float:
    try:
        return statistics.mean(values) if values else fallback
    except statistics.StatisticsError:
        return fallback


def _stddev(values: Sequence[float], fallback: float = 0.0) -> float:
    try:
        return statistics.stdev(values) if len(values) >= 2 else fallback
    except statistics.StatisticsError:
        return fallback


def _moving_average(values: Sequence[int], window: int = 3) -> List[float]:
    if window <= 0:
        return [float(x) for x in values]
    result: List[float] = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start : i + 1]
        result.append(_mean(chunk, fallback=float(values[i])))
    return result


def _extract_words(text: str) -> List[str]:
    if not text:
        return []
    return [token for token in re.split(r"[^A-Za-z0-9']+", text) if token]


def _extract_sentences(text: str) -> List[str]:
    if not text:
        return []
    raw = re.split(r"[\.!?\n]+", text)
    return [s.strip() for s in raw if s.strip()]


def _count_bullets(text: str) -> int:
    return len(re.findall(r"^\s*(?:[-*•]|\d+\.)\s+", text, flags=re.MULTILINE))


def _estimate_reading_time(chars: int) -> float:
    # Rough estimate: 900 characters per minute
    if chars <= 0:
        return 0.0
    minutes = chars / 900.0
    return minutes * 60.0


def _score_similarity(topic: str, text: str) -> float:
    if not topic or not text:
        return 0.0
    topic_tokens = {token.lower() for token in _extract_words(topic) if len(token) >= 3}
    if not topic_tokens:
        return 0.0
    text_tokens = _extract_words(text.lower())
    if not text_tokens:
        return 0.0
    matched_unique = {token for token in text_tokens if token in topic_tokens}
    coverage = len(matched_unique) / float(len(topic_tokens))
    frequency = sum(1 for token in text_tokens if token in topic_tokens) / float(len(text_tokens))
    return _clamp(max(coverage, frequency), 0.0, 1.0)


def _score_coherence(text: str) -> float:
    sentences = _extract_sentences(text)
    if len(sentences) < 2:
        return 0.0
    lengths = [len(sentence) for sentence in sentences]
    if not lengths:
        return 0.0
    mean_length = _mean(lengths, fallback=0.0)
    if mean_length == 0:
        return 0.0
    variance = _stddev(lengths, fallback=0.0)
    if variance == 0:
        return 1.0
    ratio = _clamp(1.0 - variance / (mean_length + 1e-6), 0.0, 1.0)
    return ratio


def _apply_shortcut(keys: Tuple[str, ...], pause: float = 0.15) -> None:
    try:
        pyautogui.hotkey(*keys)
        time.sleep(pause)
    except Exception:
        time.sleep(pause)


def _typewrite(text: str, interval: float) -> None:
    try:
        pyautogui.typewrite(text, interval=interval)
    except Exception:
        # Fallback to character-by-character typing
        for ch in text:
            try:
                pyautogui.typewrite(ch)
            except Exception:
                pass
            time.sleep(interval)


# ============================================================================
# Browser automation toolkit
# ============================================================================


class BrowserAutomationToolkit:
    """Encapsulates low-level browser and clipboard interactions."""

    def __init__(self, config: WorkflowConfig) -> None:
        self.config = config

    def open_chatgpt(self, url: str) -> bool:
        start = _now()
        _log(self.config, f"Opening ChatGPT at {url}")
        if self.config.browser_open_callable:
            try:
                if self.config.browser_open_callable(url):
                    time.sleep(1.0)
                    return True
            except Exception as exc:
                _log(self.config, f"Custom browser opener failed: {exc}")
        try:
            import webbrowser

            if self.config.preferred_browser:
                try:
                    controller = webbrowser.get(self.config.preferred_browser)
                    controller.open(url)
                except webbrowser.Error:
                    webbrowser.open(url)
            else:
                webbrowser.open(url)
            elapsed = _now() - start
            _log(self.config, f"Browser open command issued in {elapsed:.2f}s")
            return True
        except Exception as exc:
            _log(self.config, f"Standard webbrowser failed: {exc}")
            return False

    def focus_prompt_area(self) -> bool:
        width, height = pyautogui.size()
        target_x = width // 2
        target_y = int(height * 0.90)
        _log(self.config, f"Moving cursor to prompt region ({target_x}, {target_y})")
        try:
            pyautogui.moveTo(target_x, target_y, duration=0.35)
            time.sleep(0.2)
            pyautogui.click()
            time.sleep(0.2)
            _apply_shortcut(self.config.clear_shortcut, pause=0.1)
            _apply_shortcut(self.config.delete_shortcut, pause=0.1)
            return True
        except Exception as exc:
            _log(self.config, f"Failed to focus prompt area: {exc}")
            return False

    def submit_prompt(self, prompt: str) -> bool:
        if not prompt:
            return False
        if not self.focus_prompt_area():
            return False
        _log(self.config, f"Typing prompt ({len(prompt)} chars)")
        _typewrite(prompt, interval=0.01)
        try:
            pyautogui.press("enter")
            time.sleep(0.5)
        except Exception:
            return False
        return True

    def copy_page_text(self) -> str:
        _apply_shortcut(self.config.select_all_shortcut, pause=0.2)
        _apply_shortcut(self.config.copy_shortcut, pause=0.2)
        text = ""
        if pyperclip:
            try:
                text = pyperclip.paste() or ""
            except Exception:
                text = ""
        return text

    def ensure_response_visible(self) -> None:
        try:
            pyautogui.moveTo(pyautogui.size()[0] // 2, int(pyautogui.size()[1] * 0.55))
            pyautogui.click()
            time.sleep(0.2)
        except Exception:
            time.sleep(0.2)

    def scroll_response(self, amount: int) -> None:
        try:
            pyautogui.scroll(amount)
            time.sleep(0.2)
        except Exception:
            time.sleep(0.2)

    def verify_browser_ready(self, boot_wait: float) -> None:
        wait = _clamp(boot_wait, 1.0, 15.0)
        _log(self.config, f"Initial boot wait {wait:.2f}s")
        time.sleep(wait)


# ============================================================================
# ChatGPT response collector
# ============================================================================


class ChatGPTContentCollector:
    """Collects and scores responses from ChatGPT."""

    def __init__(self, config: WorkflowConfig, toolkit: BrowserAutomationToolkit) -> None:
        self.config = config
        self.toolkit = toolkit
        self.snapshots: List[WaitSnapshot] = []
        self.telemetry: List[TelemetryEvent] = []

    def _record_snapshot(self, raw: str) -> WaitSnapshot:
        snapshot = WaitSnapshot(
            timestamp=_now(),
            char_count=len(raw),
            line_count=raw.count("\n") + 1,
            word_count=len(_extract_words(raw)),
            sample=raw[:160],
        )
        self.snapshots.append(snapshot)
        return snapshot

    def _has_new_growth(self, a: WaitSnapshot, b: WaitSnapshot) -> bool:
        return b.char_count > a.char_count + self.config.wait_minimum_growth

    def _adaptive_wait_loop(self) -> None:
        start = _now()
        stable_runs = 0
        last_snapshot = None
        total_wait = 0.0

        while True:
            time.sleep(self.config.wait_poll_seconds)
            self.toolkit.ensure_response_visible()
            raw = self.toolkit.copy_page_text()
            snapshot = self._record_snapshot(raw)
            total_wait = _now() - start
            _log(
                self.config,
                (
                    f"Wait snapshot {len(self.snapshots)}: chars={snapshot.char_count} "
                    f"words={snapshot.word_count} lines={snapshot.line_count}"
                ),
            )
            if last_snapshot and not self._has_new_growth(last_snapshot, snapshot):
                stable_runs += 1
            else:
                stable_runs = 0
            last_snapshot = snapshot
            if total_wait < self.config.boot_wait_seconds:
                continue
            if stable_runs >= self.config.wait_stable_threshold:
                _log(self.config, "Response considered stable based on growth heuristic")
                break
            if total_wait >= self.config.max_wait_seconds:
                _log(self.config, "Reached max wait threshold")
                break

    def _collect_response(self) -> str:
        attempts = 0
        raw_text = ""
        while attempts < max(1, self.config.copy_retries):
            attempts += 1
            raw_text = self.toolkit.copy_page_text()
            _log(self.config, f"Copy attempt {attempts} captured {len(raw_text)} characters")
            if raw_text.strip():
                break
            time.sleep(0.6)
        if not raw_text.strip():
            raise ResponseCollectionError("No response text captured from clipboard")
        return raw_text

    def _apply_scroll_sampling(self, raw_text: str) -> str:
        if len(raw_text) > 200 and self.config.scroll_attempts > 0:
            aggregate = raw_text
            for i in range(self.config.scroll_attempts):
                self.toolkit.scroll_response(-700)
                alt = self.toolkit.copy_page_text()
                if len(alt) > len(aggregate):
                    aggregate = alt
                time.sleep(0.2)
            self.toolkit.scroll_response(900)
            final_alt = self.toolkit.copy_page_text()
            if len(final_alt) > len(aggregate):
                aggregate = final_alt
            return aggregate
        return raw_text

    def wait_and_collect(self) -> str:
        stage_start = _now()
        self._adaptive_wait_loop()
        raw = self._collect_response()
        raw = self._apply_scroll_sampling(raw)
        stage_end = _now()
        self.telemetry.append(
            TelemetryEvent(
                stage=Stage.COPY_RESPONSE,
                ok=True,
                started_at=stage_start,
                finished_at=stage_end,
                message=f"Captured {len(raw)} characters",
                attempts=len(self.snapshots),
                payload={"snapshots": len(self.snapshots)},
            )
        )
        return raw


# ============================================================================
# Response cleaner and scorer
# ============================================================================


class ResponseCleaner:
    """Applies deterministic cleaning and scoring to the collected text."""

    RULE_PATTERNS: Dict[CleaningRule, re.Pattern] = {
        CleaningRule.STRIP_DISCLAIMER: re.compile(r"(?im)^\s*(?:as an ai|i cannot|disclaimer:|note:).*?$", re.MULTILINE),
        CleaningRule.STRIP_HEADING: re.compile(r"(?im)^\s*(?:#|##|###|here(?:'s| are)|overall:|summary:).*?$", re.MULTILINE),
        CleaningRule.STRIP_PROMPT_REF: re.compile(r"(?i)\b(as you requested|per your request|about your question)\b"),
    }

    def __init__(self, config: WorkflowConfig) -> None:
        self.config = config

    def _strip_page_chrome(self, text: str) -> Tuple[str, bool]:
        original = text
        lower = text.lower()
        cutoff_markers = [
            "chatgpt can make mistakes",
            "cookie preferences",
            "no file chosen",
            "skip to ntent",
        ]
        cut_index = len(text)
        for marker in cutoff_markers:
            idx = lower.find(marker)
            if idx != -1:
                cut_index = min(cut_index, idx)
        if cut_index < len(text):
            text = text[:cut_index]
        noise_tokens = (
            "skip to content",
            "cookie preferences",
            "see cookie preferences",
            "no file chosen",
            "skip to ntent",
        )
        lines: List[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue
            lower_line = stripped.lower()
            if any(token in lower_line for token in noise_tokens):
                continue
            lines.append(line)
        cleaned = "\n".join(lines)
        return cleaned, cleaned != original

    def _strip_prompt_template(self, text: str, prompt: Optional[str], topic: str) -> Tuple[str, bool]:
        if not prompt:
            return text, False
        original = text
        # remove direct prompt string matches first
        if prompt in text:
            text = text.replace(prompt, "")
        prompt_lower = re.sub(r"\s+", " ", prompt.lower())
        prompt_fragments = [
            fragment.strip()
            for fragment in re.split(r"[.!?]", prompt_lower)
            if fragment.strip()
        ]
        topic_lower = topic.lower().strip()
        lines: List[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue
            lower_line = re.sub(r"\s+", " ", stripped.lower())
            if topic_lower and lower_line == topic_lower:
                continue
            if lower_line == prompt_lower:
                continue
            if any(fragment and fragment in lower_line for fragment in prompt_fragments):
                continue
            lines.append(line)
        cleaned = "\n".join(lines)
        return cleaned, cleaned != original

    def _strip_conversation_header(self, text: str) -> Tuple[str, bool]:
        lines = text.splitlines()
        cleaned: List[str] = []
        skipping = True
        prefixes = (
            "- chat history",
            "chat history",
            "- you said",
            "you said",
            "- chatgpt said",
            "chatgpt said",
        )
        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()
            if skipping:
                if not stripped:
                    continue
                if any(lower.startswith(prefix) for prefix in prefixes):
                    continue
                skipping = False
                cleaned.append(line)
            else:
                cleaned.append(line)
        if not cleaned:
            return text, False
        new_text = "\n".join(cleaned)
        return new_text, new_text != text

    def _normalise_newlines(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _normalise_bullets(self, text: str) -> str:
        lines = text.splitlines()
        normalised: List[str] = []
        bullet_index = 1
        for line in lines:
            stripped = line.strip()
            if not stripped:
                normalised.append("")
                continue
            if re.match(r"^(?:[-*•]|\d+\.)\s+", stripped):
                normalised.append(stripped)
                continue
            if stripped[0].isdigit() and ":" in stripped[:6]:
                normalised.append(stripped)
                continue
            if len(stripped) > 40 and stripped.count(".") >= 1:
                normalised.append(stripped)
                continue
            normalised.append(f"- {stripped}")
            bullet_index += 1
        return "\n".join(normalised)

    def _ensure_sentence_case(self, text: str) -> str:
        lines = text.splitlines()
        cased: List[str] = []
        for line in lines:
            if not line:
                cased.append(line)
                continue
            if line.startswith(('-', '*', '•')):
                bullet, _, rest = line.partition(' ')
                if rest:
                    cased.append(f"{bullet} {rest[:1].upper() + rest[1:]}" if rest[0].islower() else line)
                else:
                    cased.append(line)
            else:
                cased.append(line[:1].upper() + line[1:] if line[0].islower() else line)
        return "\n".join(cased)

    def clean(self, topic: str, raw: str, prompt: Optional[str] = None) -> Tuple[str, List[CleaningRule]]:
        if not raw:
            return "", []
        steps: List[CleaningRule] = []
        text = raw
        text, changed = self._strip_page_chrome(text)
        if changed:
            steps.append(CleaningRule.STRIP_PAGE_CHROME)
        text, changed = self._strip_prompt_template(text, prompt, topic)
        if changed:
            steps.append(CleaningRule.STRIP_PROMPT_TEMPLATE)
        text, changed = self._strip_conversation_header(text)
        if changed:
            steps.append(CleaningRule.STRIP_CONVERSATION_HEADER)
        for rule, pattern in self.RULE_PATTERNS.items():
            new_text = pattern.sub("", text)
            if new_text != text:
                steps.append(rule)
                text = new_text
        text = self._normalise_newlines(text)
        steps.append(CleaningRule.TRIM_BLANK_LINES)
        text = self._normalise_bullets(text)
        steps.append(CleaningRule.NORMALISE_BULLETS)
        text = self._ensure_sentence_case(text)
        steps.append(CleaningRule.ENSURE_SENTENCE_CASE)
        if topic:
            relevant_lines: List[str] = []
            topic_tokens = set(token.lower() for token in _extract_words(topic) if len(token) >= 3)
            for line in text.splitlines():
                lower = line.lower()
                if not line.strip():
                    relevant_lines.append("")
                    continue
                overlap = sum(1 for token in topic_tokens if token in lower)
                if overlap >= 1 or len(topic_tokens) <= 2:
                    relevant_lines.append(line)
                elif len(line.split()) <= 3:
                    continue
                else:
                    relevant_lines.append(line)
            text = "\n".join(relevant_lines)
            steps.append(CleaningRule.KEEP_RELEVANT)
        if len(text) > self.config.quality_max_chars:
            text = text[: self.config.quality_max_chars].rsplit("\n", 1)[0]
            steps.append(CleaningRule.LIMIT_LENGTH)
        return text.strip(), steps

    def score(self, topic: str, text: str) -> ResponseQuality:
        if not text.strip():
            return ResponseQuality(status=ResponseStatus.EMPTY, reasons=["Cleaned text empty"])
        words = _extract_words(text)
        sentences = _extract_sentences(text)
        bullets = _count_bullets(text)
        status = ResponseStatus.COMPLETE
        reasons: List[str] = []
        if len(words) < self.config.quality_min_words:
            status = ResponseStatus.LOW_QUALITY
            reasons.append("Too few words")
        if len(sentences) < self.config.quality_min_sentences:
            status = ResponseStatus.LOW_QUALITY
            reasons.append("Too few sentences")
        if bullets < self.config.quality_min_bullets:
            reasons.append("Low bullet coverage")
        if status == ResponseStatus.COMPLETE and bullets >= self.config.quality_min_bullets:
            status = ResponseStatus.HIGH_QUALITY
        relevance = _score_similarity(topic, text)
        coherence = _score_coherence(text)
        if relevance < 0.05:
            status = ResponseStatus.LOW_QUALITY
            reasons.append("Low relevance to topic")
        reading_time = _estimate_reading_time(len(text))
        return ResponseQuality(
            status=status,
            reasons=reasons,
            relevance_score=relevance,
            coherence_score=coherence,
            bullet_ratio=bullets / max(1, len(sentences) + bullets),
            reading_time_seconds=reading_time,
            cleaned_length=len(text),
        )


# ============================================================================
# Notepad automation
# ============================================================================


class NotepadAutomation:
    """Handles Notepad operations with validation."""

    def __init__(self, config: WorkflowConfig) -> None:
        self.config = config

    def open_notepad(self) -> bool:
        if self.config.notepad_open_callable:
            try:
                if self.config.notepad_open_callable("notepad"):
                    time.sleep(0.8)
                    return True
            except Exception:
                pass
        from .ui import open_app_via_start  # type: ignore

        try:
            opened = open_app_via_start('notepad')
            if opened:
                time.sleep(0.8)
            return bool(opened)
        except Exception:
            try:
                pyautogui.hotkey('win', 'r')
                time.sleep(0.3)
                _typewrite('notepad', interval=0.02)
                pyautogui.press('enter')
                time.sleep(0.8)
                return True
            except Exception:
                return False

    def ensure_blank_document(self) -> None:
        _apply_shortcut(self.config.select_all_shortcut, pause=0.1)
        _apply_shortcut(self.config.delete_shortcut, pause=0.1)
        try:
            pyautogui.press('home')
        except Exception:
            pass

    def write_content(
        self,
        heading: str,
        body: str,
        mode: NotepadWriteMode,
    ) -> NotepadValidation:
        del heading  # we intentionally avoid adding extra headings for paste-only output
        self.ensure_blank_document()
        attempts = 0
        while attempts < 3:
            attempts += 1
            try:
                if mode in {NotepadWriteMode.PASTE, NotepadWriteMode.PASTE_THEN_TYPE} and pyperclip:
                    pyperclip.copy(body)
                if mode in {NotepadWriteMode.PASTE, NotepadWriteMode.PASTE_THEN_TYPE}:
                    _apply_shortcut(self.config.paste_shortcut, pause=0.3)
                if mode == NotepadWriteMode.TYPEWRITE:
                    _typewrite(body, interval=self.config.typing_interval)
                break
            except Exception as exc:
                _log(self.config, f"Notepad write attempt {attempts} failed: {exc}")
                time.sleep(0.4)

        validation = NotepadValidation(
            expected_chars=len(body),
            observed_chars=len(body),
            verified=False,
            mode=mode,
            attempts=attempts,
        )
        if self.config.enable_notepad_validation and pyperclip:
            _apply_shortcut(self.config.select_all_shortcut, pause=0.1)
            _apply_shortcut(self.config.copy_shortcut, pause=0.1)
            try:
                captured = (pyperclip.paste() or "").strip()
            except Exception:
                captured = ""
            validation.observed_chars = len(captured)
            snippet = body[: min(40, len(body))].strip().lower()
            if snippet and snippet in captured.lower():
                validation.verified = True
            elif len(captured) >= len(body) * 0.6:
                validation.verified = True
            else:
                validation.verified = False
            try:
                pyautogui.press('end')
            except Exception:
                pass
        else:
            validation.verified = True
        return validation


# ============================================================================
# Workflow Orchestrator
# ============================================================================


class AINotepadWorkflow:
    """Coordinates the entire notepad automation workflow."""

    def __init__(self, config: Optional[WorkflowConfig] = None) -> None:
        self.config = config or WorkflowConfig()
        if self.config.random_seed is not None:
            random.seed(self.config.random_seed)
        self.toolkit = BrowserAutomationToolkit(self.config)
        self.collector = ChatGPTContentCollector(self.config, self.toolkit)
        self.cleaner = ResponseCleaner(self.config)
        self.notepad = NotepadAutomation(self.config)

    # --------------------------- Internal helpers ---------------------------

    def _build_prompt(self, topic: str) -> str:
        prompt = self.config.prompt_template.format(topic=topic)
        return prompt.strip()

    def _stage(self, stage: Stage, func: Callable[[], Any], message: str) -> Tuple[bool, Any, TelemetryEvent]:
        start = _now()
        _log(self.config, f"Stage {stage.name}: {message}")
        ok = False
        result: Any = None
        try:
            result = func()
            ok = bool(result) if result is not None else True
        except Exception as exc:
            _log(self.config, f"Stage {stage.name} raised: {exc}")
            result = exc
            ok = False
        finished = _now()
        event = TelemetryEvent(
            stage=stage,
            ok=ok,
            started_at=start,
            finished_at=finished,
            message=message,
        )
        return ok, result, event

    def _open_browser(self, url: str) -> bool:
        if not self.toolkit.open_chatgpt(url):
            raise BrowserOpenError("Failed to trigger browser open")
        self.toolkit.verify_browser_ready(self.config.boot_wait_seconds)
        return True

    def _submit_prompt(self, prompt: str) -> bool:
        if not self.toolkit.submit_prompt(prompt):
            raise PromptSubmissionError("Prompt submission failed")
        return True

    def _wait_and_collect(self) -> str:
        raw = self.collector.wait_and_collect()
        if not raw.strip():
            raise ResponseCollectionError("Collected response empty")
        return raw

    def _clean_response(self, topic: str, raw: str, prompt: Optional[str]) -> Tuple[str, ResponseQuality, List[CleaningRule]]:
        cleaned, rules = self.cleaner.clean(topic, raw, prompt=prompt)
        quality = self.cleaner.score(topic, cleaned)
        return cleaned, quality, rules

    def _open_notepad_and_write(self, topic: str, cleaned: str, quality: ResponseQuality) -> Tuple[bool, NotepadValidation, NotepadWriteMode]:
        if not cleaned.strip():
            raise NotepadAutomationError("No cleaned text to write")
        heading = ""
        mode = NotepadWriteMode.PASTE if self.config.allow_paste_mode else NotepadWriteMode.TYPEWRITE
        if not self.notepad.open_notepad():
            raise NotepadAutomationError("Failed to open Notepad")
        validation = self.notepad.write_content(heading=heading, body=cleaned, mode=mode)
        if not validation.verified and validation.observed_chars > 0:
            _log(self.config, "Notepad validation soft failure; assuming paste succeeded based on observed chars")
            validation.verified = True
        return validation.verified, validation, mode

    def _build_url(self) -> str:
        model = os.environ.get("CHATGPT_MODEL", "gpt-4o-mini")
        if model:
            return f"https://chat.openai.com/?model={model}"
        return "https://chat.openai.com/"

    # ------------------------------ Public API ------------------------------

    def run(self, topic: str) -> WorkflowResult:
        topic = (topic or "").strip()
        if len(topic) < self.config.minimum_topic_length:
            raise ValueError("Topic is too short")
        self.collector.snapshots = []
        self.collector.telemetry = []
        telemetry: List[TelemetryEvent] = []
        url = self._build_url()
        raw_text = ""
        cleaned_text = ""
        quality = ResponseQuality(status=ResponseStatus.EMPTY)
        write_mode = None
        metadata: Dict[str, Any] = {}

        ok, _, event = self._stage(Stage.OPEN_BROWSER, lambda: self._open_browser(url), "Opening ChatGPT")
        telemetry.append(event)
        if not ok:
            return WorkflowResult(
                ok=False,
                topic=topic,
                cleaned_text="",
                quality=quality,
                telemetry=telemetry,
                snapshots=self.collector.snapshots,
                raw_text="",
                note_written=False,
                write_mode=None,
                metadata={"error": "browser_open_failed"},
            )

        prompt = self._build_prompt(topic)
        ok, _, event = self._stage(Stage.SUBMIT_PROMPT, lambda: self._submit_prompt(prompt), "Submitting prompt")
        telemetry.append(event)
        if not ok:
            return WorkflowResult(
                ok=False,
                topic=topic,
                cleaned_text="",
                quality=quality,
                telemetry=telemetry,
                snapshots=self.collector.snapshots,
                raw_text="",
                note_written=False,
                write_mode=None,
                metadata={"error": "prompt_submit_failed"},
            )

        ok, result, event = self._stage(Stage.WAIT_FOR_RESPONSE, self._wait_and_collect, "Waiting for response")
        telemetry.append(event)
        if not ok:
            err = result if isinstance(result, Exception) else ResponseCollectionError("unknown")
            return WorkflowResult(
                ok=False,
                topic=topic,
                cleaned_text="",
                quality=quality,
                telemetry=telemetry,
                snapshots=self.collector.snapshots,
                raw_text="",
                note_written=False,
                write_mode=None,
                metadata={"error": str(err)},
            )
        raw_text = result  # type: ignore

        ok, cleaned_payload, event = self._stage(
            Stage.CLEAN_RESPONSE,
            lambda: self._clean_response(topic, raw_text, prompt),
            "Cleaning response",
        )
        telemetry.append(event)
        if not ok or not isinstance(cleaned_payload, tuple):
            return WorkflowResult(
                ok=False,
                topic=topic,
                cleaned_text="",
                quality=quality,
                telemetry=telemetry,
                snapshots=self.collector.snapshots,
                raw_text=raw_text,
                note_written=False,
                write_mode=None,
                metadata={"error": "cleaning_failed"},
            )
        cleaned_text, quality, applied_rules = cleaned_payload
        metadata["cleaning_rules"] = [rule.name for rule in applied_rules]
        metadata["raw_length"] = len(raw_text)

        ok, notepad_payload, event = self._stage(
            Stage.WRITE_NOTEPAD,
            lambda: self._open_notepad_and_write(topic, cleaned_text, quality),
            "Writing into Notepad",
        )
        telemetry.append(event)
        note_written = False
        validation = None
        if ok and isinstance(notepad_payload, tuple):
            note_written, validation, write_mode = notepad_payload
            metadata["notepad_verified"] = validation.verified if validation else False
        else:
            metadata["notepad_verified"] = False

        quality_success = quality.is_success()
        metadata["quality_success"] = quality_success
        success = note_written and bool(cleaned_text.strip())
        final_stage = Stage.COMPLETE if success else Stage.FAILED
        final_message = "Workflow completed"
        if success and not quality_success:
            final_message = "Workflow completed (quality warnings)"
        telemetry.append(
            TelemetryEvent(
                stage=final_stage,
                ok=success,
                started_at=_now(),
                finished_at=_now(),
                message=final_message if success else "Workflow incomplete",
                payload={
                    "note_written": note_written,
                    "quality_status": quality.status.name,
                    "quality_success": quality_success,
                    "cleaned_chars": len(cleaned_text),
                },
            )
        )

        return WorkflowResult(
            ok=success,
            topic=topic,
            cleaned_text=cleaned_text,
            quality=quality,
            telemetry=telemetry,
            snapshots=self.collector.snapshots,
            raw_text=raw_text,
            note_written=note_written,
            write_mode=write_mode,
            metadata=metadata,
        )


# End of module
