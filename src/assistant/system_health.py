"""System health snapshot utilities for the assistant.

The assistant often gets questions like "how busy is my CPU" or "is anything
hogging memory". Instead of shelling out to Task Manager we provide a tiny
cross-platform (mostly Windows-focused) helper that gathers resource stats using
psutil when available and falling back to ctypes/shutil/standard modules when it
isn't.

The helper returns structured dictionaries so the voice layer can narrate a
friendly summary while logs/tests can inspect the richer metadata.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

try:  # pragma: no cover - psutil is optional in CI
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


@dataclass
class SystemHealthReport:
    cpu_percent: Optional[float]
    cpu_count: int
    memory_percent: Optional[float]
    total_memory_gb: Optional[float]
    available_memory_gb: Optional[float]
    disk_percent: Optional[float]
    disk_free_gb: Optional[float]
    uptime_hours: Optional[float]
    battery_percent: Optional[float]
    issues: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _get_cpu_percent(samples: int = 1, delay: float = 0.2) -> Optional[float]:
    if psutil is None:
        return None
    try:
        return psutil.cpu_percent(interval=delay)
    except Exception:
        values: List[float] = []
        for _ in range(max(1, samples)):
            try:
                values.append(psutil.cpu_percent(interval=delay))
            except Exception:
                break
        return sum(values) / len(values) if values else None


def _memory_via_ctypes() -> Optional[Dict[str, float]]:
    class MEMORYSTATUSEX(ctypes.Structure):  # type: ignore
        _fields_ = [
            ("dwLength", ctypes.c_uint),
            ("dwMemoryLoad", ctypes.c_uint),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
        return None
    total = stat.ullTotalPhys / (1024 ** 3)
    avail = stat.ullAvailPhys / (1024 ** 3)
    percent = 100 - stat.dwMemoryLoad
    return {"total_gb": total, "available_gb": avail, "percent": percent}


def _memory_info() -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if psutil is not None:
        try:
            info = psutil.virtual_memory()
            return info.percent, info.total / (1024 ** 3), info.available / (1024 ** 3)
        except Exception:
            pass
    if os.name == "nt":
        data = _memory_via_ctypes()
        if data:
            return data["percent"], data["total_gb"], data["available_gb"]
    return None, None, None


def _disk_info() -> Tuple[Optional[float], Optional[float]]:
    try:
        usage = shutil.disk_usage(os.path.expanduser("~"))
        total_gb = usage.total / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        percent = 100 - ((usage.free / usage.total) * 100)
        return percent, free_gb
    except Exception:
        return None, None


def _battery_info() -> Optional[float]:
    if psutil is None:
        return None
    try:
        batt = psutil.sensors_battery()
        if not batt:
            return None
        return float(batt.percent)
    except Exception:
        return None


def _uptime_hours() -> Optional[float]:
    if psutil is not None:
        try:
            boot = psutil.boot_time()
            return (time.time() - boot) / 3600.0
        except Exception:
            pass
    if os.name == "posix":
        try:
            with open("/proc/uptime", "r", encoding="utf-8") as fh:
                seconds = float(fh.read().split()[0])
            return seconds / 3600.0
        except Exception:
            return None
    return None


def collect_system_health(samples: int = 1, sample_delay: float = 0.25) -> SystemHealthReport:
    cpu_percent = _get_cpu_percent(samples=samples, delay=sample_delay)
    cpu_count = os.cpu_count() or 1
    mem_percent, mem_total, mem_available = _memory_info()
    disk_percent, disk_free = _disk_info()
    uptime = _uptime_hours()
    battery = _battery_info()

    issues: List[str] = []
    if cpu_percent is not None and cpu_percent >= 85:
        issues.append("CPU is heavily loaded.")
    if mem_percent is not None and mem_percent >= 80:
        issues.append("Memory usage is high.")
    if disk_percent is not None and disk_percent >= 90:
        issues.append("Disk is nearly full.")
    if battery is not None and battery <= 20:
        issues.append("Battery below 20%.")
    if uptime and uptime > 72:
        issues.append("System hasn't rebooted in 72+ hours.")

    return SystemHealthReport(
        cpu_percent=cpu_percent,
        cpu_count=cpu_count,
        memory_percent=mem_percent,
        total_memory_gb=mem_total,
        available_memory_gb=mem_available,
        disk_percent=disk_percent,
        disk_free_gb=disk_free,
        uptime_hours=uptime,
        battery_percent=battery,
        issues=issues,
    )


def format_system_health(report: SystemHealthReport) -> str:
    parts: List[str] = []
    if report.cpu_percent is not None:
        parts.append(f"CPU {report.cpu_percent:.0f}% ({report.cpu_count} cores)")
    if report.memory_percent is not None and report.total_memory_gb is not None:
        parts.append(
            f"RAM {report.memory_percent:.0f}% of {report.total_memory_gb:.1f}GB"
        )
    if report.disk_percent is not None and report.disk_free_gb is not None:
        parts.append(f"Disk {report.disk_percent:.0f}% used ({report.disk_free_gb:.1f}GB free)")
    if report.battery_percent is not None:
        parts.append(f"Battery {report.battery_percent:.0f}%")
    if report.uptime_hours is not None:
        parts.append(f"Uptime {report.uptime_hours:.1f}h")
    if report.issues:
        parts.append("Warnings: " + "; ".join(report.issues))
    return " | ".join(parts) if parts else "System metrics unavailable."


def system_health_report_action(params: Dict[str, Any]) -> Dict[str, Any]:
    samples = int(params.get("samples") or 1)
    samples = max(1, min(5, samples))
    delay = float(params.get("delay") or 0.25)
    report = collect_system_health(samples=samples, sample_delay=delay)
    summary = format_system_health(report)
    return {"ok": True, "say": summary, "report": report.to_dict()}


def system_health_watch_action(params: Dict[str, Any]) -> Dict[str, Any]:
    duration = float(params.get("duration") or 60)
    interval = float(params.get("interval") or 10)
    duration = max(5.0, min(600.0, duration))
    interval = max(2.0, min(120.0, interval))
    snapshots: List[Dict[str, Any]] = []
    start = time.time()
    while time.time() - start < duration:
        report = collect_system_health(samples=1, sample_delay=interval / 5)
        snapshots.append(report.to_dict())
        time.sleep(interval)
    say = f"Captured {len(snapshots)} health samples over {int(duration)} seconds."
    return {"ok": True, "say": say, "samples": snapshots}


__all__ = [
    "collect_system_health",
    "format_system_health",
    "system_health_report_action",
    "system_health_watch_action",
]
