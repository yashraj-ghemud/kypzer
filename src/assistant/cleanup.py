"""Utilities for cleaning temporary and junk files on Windows.

The helpers here focus on clearing the user's TEMP directories as well as
common system temp folders. They are designed to be resilient: any file that
cannot be removed (because it is locked or requires admin rights) is skipped and
recorded so the automation behaves like clicking "Skip" instead of failing.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclass
class CleanupStats:
    scanned_paths: int = 0
    deleted_items: int = 0
    skipped_items: int = 0
    errors: int = 0
    reclaimed_bytes: int = 0
    start_time: float = time.time()
    end_time: float = time.time()

    def finish(self) -> None:
        self.end_time = time.time()

    def as_dict(self) -> Dict[str, int]:
        return {
            "scanned_paths": self.scanned_paths,
            "deleted_items": self.deleted_items,
            "skipped_items": self.skipped_items,
            "errors": self.errors,
            "reclaimed_bytes": self.reclaimed_bytes,
            "duration_seconds": round(self.end_time - self.start_time, 2),
        }


def _default_temp_targets() -> List[Path]:
    paths: List[Path] = []
    for env_name in ("TEMP", "TMP", "LOCALAPPDATA"):
        raw = os.environ.get(env_name)
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if env_name == "LOCALAPPDATA":
            candidate = candidate / "Temp"
        if candidate.exists() and candidate not in paths:
            paths.append(candidate)
    system_temp = Path("C:/Windows/Temp")
    if system_temp.exists() and system_temp not in paths:
        paths.append(system_temp)
    try:
        default_tmp = Path(tempfile.gettempdir())
        if default_tmp.exists() and default_tmp not in paths:
            paths.append(default_tmp)
    except Exception:
        pass
    return paths


def _safe_remove(path: Path, stats: CleanupStats) -> None:
    try:
        if path.is_symlink():
            path.unlink(missing_ok=True)
            stats.deleted_items += 1
            return

        if path.is_file():
            size = path.stat().st_size if path.exists() else 0
            path.unlink(missing_ok=True)
            stats.deleted_items += 1
            stats.reclaimed_bytes += size
            return

        if path.is_dir():
            for child in path.iterdir():
                _safe_remove(child, stats)
            try:
                path.rmdir()
                stats.deleted_items += 1
            except OSError:
                stats.skipped_items += 1
            return

        if path.exists():
            path.unlink(missing_ok=True)
            stats.deleted_items += 1
    except PermissionError:
        try:
            os.chmod(path, stat.S_IWRITE)
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            stats.deleted_items += 1
        except Exception:
            stats.skipped_items += 1
    except FileNotFoundError:
        pass
    except Exception:
        stats.errors += 1


def cleanup_temp_dirs(targets: Optional[Iterable[Path]] = None) -> Dict[str, object]:
    stats = CleanupStats()
    stats.start_time = time.time()
    paths = list(targets) if targets else _default_temp_targets()
    pruned: List[Path] = []
    for path in paths:
        try:
            resolved = path.expanduser().resolve(strict=False)
        except Exception:
            continue
        if resolved.exists():
            pruned.append(resolved)
    if not pruned:
        stats.finish()
        return {
            "ok": False,
            "say": "Couldn't find any temp folders to clean.",
            "details": stats.as_dict(),
        }

    for folder in pruned:
        stats.scanned_paths += 1
        try:
            for entry in folder.iterdir():
                _safe_remove(entry, stats)
        except PermissionError:
            stats.skipped_items += 1
        except Exception:
            stats.errors += 1

    stats.finish()
    msg = _format_summary(pruned, stats)
    return {"ok": True, "say": msg, "details": stats.as_dict()}


def _format_summary(paths: List[Path], stats: CleanupStats) -> str:
    location = ", ".join({p.as_posix() for p in paths})
    reclaimed = _human_size(stats.reclaimed_bytes)
    duration = stats.end_time - stats.start_time
    base = f"Cleaned {stats.deleted_items} items from temp folders ({reclaimed} freed in {duration:.1f}s)."
    if stats.skipped_items or stats.errors:
        base += f" Skipped {stats.skipped_items} locked items" if stats.skipped_items else ""
        if stats.errors:
            base += f"; {stats.errors} errors"
        base += "."
    return base + f" Targets: {location}" if location else base


def _human_size(num_bytes: int) -> str:
    step = 1024.0
    if num_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < step:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= step
    return f"{size:.1f} PB"


__all__ = ["cleanup_temp_dirs"]
