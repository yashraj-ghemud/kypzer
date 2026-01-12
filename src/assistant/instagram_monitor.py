"""instagram_monitor
====================

High fidelity Instagram notification detection pipeline for desktop automation.
The goal of this module is to observe rendered Instagram top-bar widgets and
return a high confidence judgement about the presence of notifications and
unread direct messages. The implementation intentionally leans verbose so that
we can reason about every intermediate step, collect structured telemetry, and
adapt to UI changes without rewriting the automation stack.

Overview
--------
1. Capture multiple screenshots to reduce stochastic noise.
2. Locate dynamic badge regions (notification bell, messages icon, profile).
3. Run multiple heuristics per region (red pixel ratio, HSV cues, cluster
   compactness, circularity, etc.).
4. Aggregate heuristic scores into a confidence model.
5. Produce a detailed report for speech synthesis and logging.

This file may look excessive, but the verbosity provides the affordances we
need to debug the feature remotely. Every structure is exported so unit tests
and future telemetry collectors can introspect the pipeline.
"""

from __future__ import annotations

import itertools
import math
import statistics
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, TYPE_CHECKING

try:
    from typing import Protocol
except ImportError:  # Python < 3.8 fallback, though we expect >=3.10
    Protocol = Any  # type: ignore

try:
    import colorsys
except Exception:  # pragma: no cover - colorsys ships with stdlib but guard anyway
    colorsys = None

try:
    import numpy as _np
except Exception:  # pragma: no cover - numpy is optional
    _np = None

if TYPE_CHECKING:  # pragma: no cover - type checking branch only
    from PIL import Image  # pylint: disable=import-error

ImageType = Any  # We operate on PIL images returned by pyautogui


class InstagramNotificationError(RuntimeError):
    """Raised when the detection pipeline encounters an unrecoverable issue."""


class InstagramDetectionStage(Enum):
    """Coarse-grained stages executed by :class:`InstagramNotificationMonitor`."""

    PREPARE = auto()
    CAPTURE = auto()
    LOCATE_REGIONS = auto()
    ANALYZE_BADGES = auto()
    AGGREGATE = auto()
    COMPLETE = auto()


@dataclass
class BadgeRegion:
    """Describes a normalized top-bar segment we intend to sample."""

    name: str
    x_start: float
    x_end: float
    y_start: float
    y_end: float

    def clamp(self) -> "BadgeRegion":
        xs = min(max(self.x_start, 0.0), 1.0)
        xe = min(max(self.x_end, 0.0), 1.0)
        ys = min(max(self.y_start, 0.0), 1.0)
        ye = min(max(self.y_end, 0.0), 1.0)
        return BadgeRegion(self.name, xs, xe, ys, ye)


@dataclass
class BadgeSample:
    """Raw metrics collected from a screenshot crop."""

    region: BadgeRegion
    size: Tuple[int, int]
    red_pixels: int
    vivid_red_pixels: int
    hsv_hits: int
    saturation_mean: float
    value_mean: float
    circularity_score: float
    compactness_score: float
    cluster_count: int
    pixel_ratio: float
    vivid_ratio: float
    hsv_ratio: float
    timestamp: float


@dataclass
class BadgeHeuristicScores:
    """Aggregated heuristic confidence per region."""

    has_signal: bool
    score_red: float
    score_hsv: float
    score_shape: float
    score_compact: float
    score_cluster: float
    overall: float
    supporting_samples: List[BadgeSample] = field(default_factory=list)


@dataclass
class BadgeDecision:
    """Final decision for a single badge target."""

    name: str
    confidence: float
    has_notification: bool
    heuristics: BadgeHeuristicScores
    reasoning: List[str] = field(default_factory=list)


@dataclass
class NotificationDecision:
    """Output returned to the calling automation layer."""

    has_notifications: bool
    has_messages: bool
    notification_confidence: float
    message_confidence: float
    duration_seconds: float
    attempts: int
    stage_trace: List[Tuple[InstagramDetectionStage, float]]
    decisions: Dict[str, BadgeDecision]
    capture_failures: int = 0
    notes: List[str] = field(default_factory=list)


@dataclass
class InstagramNotificationConfig:
    """Tunable values controlling detection sensitivity."""

    top_bar_y_start: float = 0.03
    top_bar_y_end: float = 0.20
    notification_regions: Sequence[Tuple[float, float]] = ((0.58, 0.70), (0.60, 0.74), (0.62, 0.78))
    message_regions: Sequence[Tuple[float, float]] = ((0.74, 0.92), (0.76, 0.94), (0.79, 0.97))
    pixel_ratio_threshold: float = 0.003
    vivid_ratio_threshold: float = 0.0015
    hsv_ratio_threshold: float = 0.002
    red_pixel_threshold: int = 18
    vivid_pixel_threshold: int = 6
    hsv_pixel_threshold: int = 8
    circularity_threshold: float = 0.22
    compactness_threshold: float = 0.16
    cluster_threshold: int = 3
    vote_required: int = 2
    soft_vote_required: int = 1
    min_attempts: int = 2
    max_attempts: int = 4
    attempt_delay: float = 2.4
    first_attempt_delay: float = 3.0
    heat_decay: float = 0.85
    confidence_floor: float = 0.35
    confidence_cap: float = 0.96
    calibration_ramp: float = 0.18
    allow_numpy: bool = True
    require_numpy_for_shape: bool = False
    enable_circularity: bool = True
    enable_compactness: bool = True
    enable_cluster_analysis: bool = True
    debug_samples: bool = False

    def as_regions(self) -> Dict[str, List[BadgeRegion]]:
        top = []
        messages = []
        for start, end in self.notification_regions:
            top.append(BadgeRegion("notifications", start, end, self.top_bar_y_start, self.top_bar_y_end).clamp())
        for start, end in self.message_regions:
            messages.append(BadgeRegion("messages", start, end, self.top_bar_y_start, self.top_bar_y_end).clamp())
        return {"notifications": top, "messages": messages}


class ScreenshotProvider(Protocol):  # pragma: no cover - interface definition only
    def __call__(self) -> ImageType:
        ...


class PixelView:
    """Lightweight view over image pixels, optionally backed by numpy."""

    def __init__(self, image: ImageType, allow_numpy: bool = True) -> None:
        self.image = image
        self._array = None
        self.allow_numpy = allow_numpy and _np is not None

    @property
    def as_array(self):
        if self.allow_numpy:
            if self._array is None:
                try:
                    self._array = _np.asarray(self.image.convert("RGB"), dtype=_np.uint8)
                except Exception:
                    self._array = None
        return self._array

    def iterate_pixels(self) -> Iterable[Tuple[int, int, int]]:
        arr = self.as_array
        if arr is not None:
            for row in arr:
                for pixel in row:
                    yield int(pixel[0]), int(pixel[1]), int(pixel[2])
        else:
            # Manual iteration if numpy is unavailable
            width, height = self.image.size
            pixels = self.image.load()
            for y in range(height):
                for x in range(width):
                    r, g, b = pixels[x, y][:3]
                    yield int(r), int(g), int(b)


class RedPixelClassifier:
    """Utility performing multiple chroma tests for the "Instagram red" hue."""

    def __init__(self, allow_numpy: bool = True) -> None:
        self.allow_numpy = allow_numpy and _np is not None

    def classify(self, view: PixelView) -> Dict[str, Any]:
        red_pixels = 0
        vivid_pixels = 0
        hsv_pixels = 0
        saturation_values: List[float] = []
        value_values: List[float] = []
        hue_values: List[float] = []

        arr = view.as_array
        if arr is not None:
            # Vectorized evaluation using numpy for speed
            r = arr[:, :, 0].astype("float32")
            g = arr[:, :, 1].astype("float32")
            b = arr[:, :, 2].astype("float32")
            max_rgb = _np.maximum(_np.maximum(r, g), b)
            min_rgb = _np.minimum(_np.minimum(r, g), b)
            delta = max_rgb - min_rgb
            with _np.errstate(divide="ignore", invalid="ignore"):
                saturation = _np.where(max_rgb == 0, 0.0, delta / max_rgb)
                value = max_rgb / 255.0
                hue = _np.zeros_like(max_rgb)
                mask = delta != 0
                hue[mask & (max_rgb == r)] = (((g - b) / delta) % 6)[mask & (max_rgb == r)]
                hue[mask & (max_rgb == g)] = (((b - r) / delta) + 2)[mask & (max_rgb == g)]
                hue[mask & (max_rgb == b)] = (((r - g) / delta) + 4)[mask & (max_rgb == b)]
                hue = (hue / 6.0) % 1.0

            red_mask = (r > 180) & (g < 120) & (b < 130)
            vivid_mask = red_mask & (saturation > 0.55) & (value > 0.40)
            hsv_mask = (hue < 0.08) | (hue > 0.92)
            hsv_mask &= saturation > 0.35
            hsv_mask &= value > 0.35

            red_pixels = int(_np.count_nonzero(red_mask))
            vivid_pixels = int(_np.count_nonzero(vivid_mask))
            hsv_pixels = int(_np.count_nonzero(hsv_mask))
            saturation_values = statistics.quantiles(saturation.flatten().tolist(), n=4) if saturation.size else [0.0]
            value_values = statistics.quantiles(value.flatten().tolist(), n=4) if value.size else [0.0]
            hue_values = statistics.quantiles(hue.flatten().tolist(), n=4) if hue.size else [0.0]
        else:
            for r, g, b in view.iterate_pixels():
                if r > 180 and g < 120 and b < 130:
                    red_pixels += 1
                if r > 200 and g < 100 and b < 110:
                    vivid_pixels += 1
                if colorsys:
                    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                    if (h < 0.08 or h > 0.92) and s > 0.35 and v > 0.30:
                        hsv_pixels += 1
                    saturation_values.append(s)
                    value_values.append(v)
                    hue_values.append(h)

        def safe_mean(values: Sequence[float]) -> float:
            return float(sum(values) / max(len(values), 1))

        return {
            "red_pixels": red_pixels,
            "vivid_pixels": vivid_pixels,
            "hsv_pixels": hsv_pixels,
            "saturation_mean": safe_mean(saturation_values),
            "value_mean": safe_mean(value_values),
            "hue_mean": safe_mean(hue_values),
        }


class ShapeFeatureExtractor:
    """Estimates simple shape qualities indicative of notification badges."""

    def __init__(self, allow_numpy: bool = True) -> None:
        self.allow_numpy = allow_numpy and _np is not None

    def extract(self, view: PixelView) -> Dict[str, float]:
        arr = view.as_array
        if arr is None:
            if not self.allow_numpy:
                return {"circularity": 0.0, "compactness": 0.0, "clusters": 0}
            return {"circularity": 0.0, "compactness": 0.0, "clusters": 0}

        mask = (arr[:, :, 0] > 180) & (arr[:, :, 1] < 120) & (arr[:, :, 2] < 130)
        count = int(_np.count_nonzero(mask))
        if count == 0:
            return {"circularity": 0.0, "compactness": 0.0, "clusters": 0}

        indices = _np.argwhere(mask)
        ys = indices[:, 0].astype("float32")
        xs = indices[:, 1].astype("float32")
        perimeter = 0.0
        min_x, max_x = xs.min(), xs.max()
        min_y, max_y = ys.min(), ys.max()
        width = max_x - min_x + 1.0
        height = max_y - min_y + 1.0
        bounding_area = width * height
        if bounding_area <= 0:
            return {"circularity": 0.0, "compactness": 0.0, "clusters": 1}

        # Estimate compactness using area / bounding box area
        compactness = float(count) / float(bounding_area)

        # Approximate perimeter using convex hull area ratio
        try:
            from scipy.spatial import ConvexHull  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            ConvexHull = None

        if ConvexHull is not None and len(indices) >= 3:
            try:
                hull = ConvexHull(indices)
                perimeter = float(hull.area)
                area = float(hull.volume)
                circularity = (4.0 * math.pi * area) / max(perimeter ** 2, 1.0)
            except Exception:
                circularity = 0.0
        else:
            # Fallback: approximate using width/height ratio
            perimeter = 2.0 * (width + height)
            area = float(count)
            circularity = (4.0 * math.pi * area) / max(perimeter ** 2, 1.0)

        # Cluster estimation via connected components in grid space
        clusters = self._estimate_clusters(mask)

        return {"circularity": float(circularity), "compactness": float(compactness), "clusters": clusters}

    def _estimate_clusters(self, mask: Any) -> int:
        if not self.allow_numpy or _np is None:
            return 1
        visited = _np.zeros_like(mask, dtype=bool)
        height, width = mask.shape
        clusters = 0
        for y in range(height):
            for x in range(width):
                if mask[y, x] and not visited[y, x]:
                    clusters += 1
                    stack = [(y, x)]
                    while stack:
                        cy, cx = stack.pop()
                        if cy < 0 or cy >= height or cx < 0 or cx >= width:
                            continue
                        if visited[cy, cx] or not mask[cy, cx]:
                            continue
                        visited[cy, cx] = True
                        stack.extend([
                            (cy - 1, cx), (cy + 1, cx),
                            (cy, cx - 1), (cy, cx + 1),
                            (cy - 1, cx - 1), (cy - 1, cx + 1),
                            (cy + 1, cx - 1), (cy + 1, cx + 1),
                        ])
        return clusters


class SampleCollector:
    """Handles cropping and measurement of badge regions for a screenshot."""

    def __init__(self, config: InstagramNotificationConfig) -> None:
        self.config = config
        self.red_classifier = RedPixelClassifier(config.allow_numpy)
        self.shape_extractor = ShapeFeatureExtractor(config.allow_numpy)

    def collect(self, image: ImageType, region: BadgeRegion) -> BadgeSample:
        width, height = image.size
        left = int(width * region.x_start)
        right = int(width * region.x_end)
        top = int(height * region.y_start)
        bottom = int(height * region.y_end)
        left = max(left, 0)
        top = max(top, 0)
        right = min(right, width)
        bottom = min(bottom, height)
        if right <= left or bottom <= top:
            raise InstagramNotificationError(f"Invalid crop bounds for region {region}")

        crop = image.crop((left, top, right, bottom))
        view = PixelView(crop, allow_numpy=self.config.allow_numpy)
        chroma = self.red_classifier.classify(view)
        shape = self.shape_extractor.extract(view) if self.config.enable_circularity or self.config.enable_compactness else {
            "circularity": 0.0,
            "compactness": 0.0,
            "clusters": 0,
        }
        area = (right - left) * (bottom - top)
        pixel_ratio = chroma["red_pixels"] / max(area, 1)
        vivid_ratio = chroma["vivid_pixels"] / max(area, 1)
        hsv_ratio = chroma["hsv_pixels"] / max(area, 1)
        return BadgeSample(
            region=region,
            size=(right - left, bottom - top),
            red_pixels=chroma["red_pixels"],
            vivid_red_pixels=chroma["vivid_pixels"],
            hsv_hits=chroma["hsv_pixels"],
            saturation_mean=chroma["saturation_mean"],
            value_mean=chroma["value_mean"],
            circularity_score=shape.get("circularity", 0.0),
            compactness_score=shape.get("compactness", 0.0),
            cluster_count=int(shape.get("clusters", 0)),
            pixel_ratio=pixel_ratio,
            vivid_ratio=vivid_ratio,
            hsv_ratio=hsv_ratio,
            timestamp=time.time(),
        )


class HeuristicEvaluator:
    """Turns raw samples into high-level badge decisions."""

    def __init__(self, config: InstagramNotificationConfig) -> None:
        self.config = config

    def evaluate(self, name: str, samples: List[BadgeSample]) -> BadgeDecision:
        red_votes = 0
        vivid_votes = 0
        hsv_votes = 0
        shape_votes = 0
        compact_votes = 0
        cluster_votes = 0

        reasons: List[str] = []

        for idx, sample in enumerate(samples):
            if sample.red_pixels >= self.config.red_pixel_threshold or sample.pixel_ratio >= self.config.pixel_ratio_threshold:
                red_votes += 1
            if sample.vivid_red_pixels >= self.config.vivid_pixel_threshold or sample.vivid_ratio >= self.config.vivid_ratio_threshold:
                vivid_votes += 1
            if sample.hsv_hits >= self.config.hsv_pixel_threshold or sample.hsv_ratio >= self.config.hsv_ratio_threshold:
                hsv_votes += 1
            if self.config.enable_circularity and sample.circularity_score >= self.config.circularity_threshold:
                shape_votes += 1
            if self.config.enable_compactness and sample.compactness_score >= self.config.compactness_threshold:
                compact_votes += 1
            if self.config.enable_cluster_analysis and sample.cluster_count <= self.config.cluster_threshold:
                cluster_votes += 1

            if self.config.debug_samples:
                reasons.append(
                    f"sample#{idx} red={sample.red_pixels} ({sample.pixel_ratio:.4f}) vivid={sample.vivid_red_pixels} ({sample.vivid_ratio:.4f}) "
                    f"hsv={sample.hsv_hits} ({sample.hsv_ratio:.4f}) circ={sample.circularity_score:.4f} compact={sample.compactness_score:.4f} "
                    f"clusters={sample.cluster_count}"
                )

        total_votes = red_votes + vivid_votes + hsv_votes + shape_votes + compact_votes + cluster_votes
        weighted = (red_votes * 0.24 + vivid_votes * 0.22 + hsv_votes * 0.22 + shape_votes * 0.12 + compact_votes * 0.10 + cluster_votes * 0.10)
        avg_samples = max(len(samples), 1)
        normalized = min(weighted / avg_samples, 1.25)
        heat = normalized * self.config.heat_decay
        confidence = min(max(heat + self.config.calibration_ramp, self.config.confidence_floor), self.config.confidence_cap)

        has_signal = (red_votes >= self.config.vote_required and vivid_votes >= self.config.soft_vote_required) or (
            vivid_votes >= self.config.vote_required
        ) or (hsv_votes >= self.config.vote_required)

        heuristics = BadgeHeuristicScores(
            has_signal=has_signal,
            score_red=red_votes / avg_samples,
            score_hsv=hsv_votes / avg_samples,
            score_shape=shape_votes / avg_samples,
            score_compact=compact_votes / avg_samples,
            score_cluster=cluster_votes / avg_samples,
            overall=confidence,
            supporting_samples=list(samples),
        )

        if has_signal:
            reasons.append(
                f"detected via votes red={red_votes} vivid={vivid_votes} hsv={hsv_votes} shape={shape_votes} compact={compact_votes} cluster={cluster_votes}"
            )
        else:
            reasons.append(
                f"insufficient votes red={red_votes} vivid={vivid_votes} hsv={hsv_votes} shape={shape_votes} compact={compact_votes} cluster={cluster_votes}"
            )

        return BadgeDecision(
            name=name,
            confidence=confidence,
            has_notification=has_signal,
            heuristics=heuristics,
            reasoning=reasons,
        )


class StageRecorder:
    """Captures stage transitions for diagnostics."""

    def __init__(self) -> None:
        self.events: List[Tuple[InstagramDetectionStage, float]] = []

    def mark(self, stage: InstagramDetectionStage) -> None:
        self.events.append((stage, time.time()))

    def report(self) -> List[Tuple[InstagramDetectionStage, float]]:
        return list(self.events)


@dataclass
class MonitorStats:
    """Runtime counters used by the monitor to stabilise decisions."""

    attempts: int = 0
    capture_failures: int = 0
    notification_heat: float = 0.0
    message_heat: float = 0.0


class InstagramNotificationMonitor:
    """Main entry point combining the helpers above."""

    def __init__(self, config: Optional[InstagramNotificationConfig] = None) -> None:
        self.config = config or InstagramNotificationConfig()
        self.collector = SampleCollector(self.config)
        self.evaluator = HeuristicEvaluator(self.config)

    def scan_current_screen(self, screenshot_provider: ScreenshotProvider, sample_count: Optional[int] = None) -> NotificationDecision:
        start = time.time()
        stats = MonitorStats()
        recorder = StageRecorder()
        recorder.mark(InstagramDetectionStage.PREPARE)

        attempts = sample_count if sample_count is not None else self.config.max_attempts
        attempts = max(attempts, self.config.min_attempts)

        regions_map = self.config.as_regions()
        notification_samples: List[BadgeSample] = []
        message_samples: List[BadgeSample] = []
        notes: List[str] = []

        for attempt in range(attempts):
            stats.attempts += 1
            recorder.mark(InstagramDetectionStage.CAPTURE)
            delay = self.config.first_attempt_delay if attempt == 0 else self.config.attempt_delay
            time.sleep(max(delay, 0.01))
            try:
                image = screenshot_provider()
            except Exception as exc:
                stats.capture_failures += 1
                notes.append(f"attempt#{attempt} failed to capture screenshot: {exc}")
                continue

            if not image:
                stats.capture_failures += 1
                notes.append(f"attempt#{attempt} produced an empty screenshot")
                continue

            recorder.mark(InstagramDetectionStage.LOCATE_REGIONS)
            for region in regions_map["notifications"]:
                sample = self.collector.collect(image, region)
                notification_samples.append(sample)
            for region in regions_map["messages"]:
                sample = self.collector.collect(image, region)
                message_samples.append(sample)

        recorder.mark(InstagramDetectionStage.ANALYZE_BADGES)
        notification_decision = self.evaluator.evaluate("notifications", notification_samples)
        message_decision = self.evaluator.evaluate("messages", message_samples)

        stats.notification_heat = self._blend_heat(stats.notification_heat, notification_decision.confidence)
        stats.message_heat = self._blend_heat(stats.message_heat, message_decision.confidence)

        recorder.mark(InstagramDetectionStage.AGGREGATE)
        final_notification = notification_decision.has_notification or stats.notification_heat >= self.config.confidence_floor
        final_messages = message_decision.has_notification or stats.message_heat >= self.config.confidence_floor

        recorder.mark(InstagramDetectionStage.COMPLETE)
        duration = time.time() - start

        return NotificationDecision(
            has_notifications=final_notification,
            has_messages=final_messages,
            notification_confidence=float(min(stats.notification_heat, 1.0)),
            message_confidence=float(min(stats.message_heat, 1.0)),
            duration_seconds=duration,
            attempts=stats.attempts,
            stage_trace=recorder.report(),
            decisions={
                "notifications": notification_decision,
                "messages": message_decision,
            },
            capture_failures=stats.capture_failures,
            notes=notes,
        )

    def _blend_heat(self, previous: float, latest: float) -> float:
        if previous == 0.0:
            return latest
        return previous * 0.5 + latest * 0.5

    def describe_decision(self, decision: NotificationDecision) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "has_notifications": decision.has_notifications,
            "has_messages": decision.has_messages,
            "notification_confidence": round(decision.notification_confidence, 4),
            "message_confidence": round(decision.message_confidence, 4),
            "duration": round(decision.duration_seconds, 3),
            "attempts": decision.attempts,
            "capture_failures": decision.capture_failures,
            "notes": decision.notes,
            "stages": [(stage.name, ts) for stage, ts in decision.stage_trace],
        }
        detailed: Dict[str, Any] = {}
        for name, badge_decision in decision.decisions.items():
            detailed[name] = {
                "confidence": round(badge_decision.confidence, 4),
                "has_notification": badge_decision.has_notification,
                "score_red": round(badge_decision.heuristics.score_red, 4),
                "score_hsv": round(badge_decision.heuristics.score_hsv, 4),
                "score_shape": round(badge_decision.heuristics.score_shape, 4),
                "score_compact": round(badge_decision.heuristics.score_compact, 4),
                "score_cluster": round(badge_decision.heuristics.score_cluster, 4),
                "overall": round(badge_decision.heuristics.overall, 4),
                "signal": badge_decision.heuristics.has_signal,
                "reasons": badge_decision.reasoning,
                "samples": [
                    {
                        "region": sample.region.name,
                        "bounds": [sample.region.x_start, sample.region.y_start, sample.region.x_end, sample.region.y_end],
                        "size": list(sample.size),
                        "red": sample.red_pixels,
                        "vivid": sample.vivid_red_pixels,
                        "hsv": sample.hsv_hits,
                        "ratio": round(sample.pixel_ratio, 5),
                        "vivid_ratio": round(sample.vivid_ratio, 5),
                        "hsv_ratio": round(sample.hsv_ratio, 5),
                        "circularity": round(sample.circularity_score, 5),
                        "compactness": round(sample.compactness_score, 5),
                        "clusters": sample.cluster_count,
                        "sample_time": sample.timestamp,
                    }
                    for sample in badge_decision.heuristics.supporting_samples
                ],
            }
        data["decisions"] = detailed
        return data


__all__ = [
    "InstagramNotificationMonitor",
    "InstagramNotificationConfig",
    "NotificationDecision",
    "BadgeDecision",
    "BadgeHeuristicScores",
    "BadgeSample",
    "BadgeRegion",
    "InstagramNotificationError",
]
