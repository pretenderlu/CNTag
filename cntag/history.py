"""Apply tag changes with a crash-safe, undoable history log.

CNTag writes in place, so every apply must be undoable: before a file is
written we capture the values of exactly the fields about to change plus
the original path, and the history JSON is rewritten atomically after
every file, so a crash mid-apply still leaves an accurate log.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .settings import settings_path
from .tags import NUMBER_FIELDS, TAG_FIELDS, read_tags, write_tags

HISTORY_VERSION = 1


@dataclass
class ApplyReport:
    ok: int = 0
    skipped: int = 0
    renamed: int = 0
    moved: dict[str, str] = field(default_factory=dict)  # old path → new path
    failures: list[tuple[str, str]] = field(default_factory=list)
    history_path: Path | None = None


@dataclass
class HistoryRecord:
    path: Path
    created: str
    file_count: int
    undone: bool
    pending: int = 0          # entries not yet undone


def _default_history_dir() -> Path:
    return settings_path().parent / "history"


def _write_history(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def apply_rows(rows: list[dict], rename: bool, history_dir: Path | None = None) -> ApplyReport:
    """Apply rows with truthy `apply`. Returns an ApplyReport; when anything
    was written, `history_path` points at the undo log."""
    report = ApplyReport()
    history_dir = Path(history_dir) if history_dir else _default_history_dir()
    history = {"version": HISTORY_VERSION,
               "created": datetime.now().isoformat(timespec="seconds"),
               "undone": False,
               "entries": []}
    history_path = history_dir / f"{datetime.now():%Y%m%d-%H%M%S-%f}.json"

    for row in rows:
        if not row.get("apply"):
            report.skipped += 1
            continue
        path = Path(row.get("file", ""))
        new_tags = {}
        for f in TAG_FIELDS + NUMBER_FIELDS:
            v = (row.get(f"new_{f}") or "").strip()
            if v:
                new_tags[f] = v
        if not new_tags:
            report.skipped += 1
            continue
        if not path.exists():
            report.failures.append((str(path), "file missing"))
            continue

        # Capture the pre-write values of exactly the fields we will change.
        old = read_tags(path) or {}
        old_tags = {f: (old.get(f) or None) for f in new_tags}
        entry = {"original": str(path), "current": str(path),
                 "old_tags": old_tags, "undone": False}

        try:
            new_path = write_tags(path, new_tags, rename=rename)
        except Exception as exc:
            report.failures.append((str(path), str(exc)))
            continue

        entry["current"] = str(new_path)
        history["entries"].append(entry)
        history_dir.mkdir(parents=True, exist_ok=True)
        _write_history(history_path, history)
        report.ok += 1
        if new_path != path:
            report.renamed += 1
            report.moved[str(path)] = str(new_path)

    if history["entries"]:
        report.history_path = history_path
    return report


def _load_history(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != HISTORY_VERSION:
        raise ValueError(f"unsupported history file: {path}")
    return data


def list_history(history_dir: Path | None = None) -> list[HistoryRecord]:
    """Newest first."""
    history_dir = Path(history_dir) if history_dir else _default_history_dir()
    records: list[HistoryRecord] = []
    if not history_dir.is_dir():
        return records
    for path in history_dir.glob("*.json"):
        try:
            data = _load_history(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        entries = data.get("entries") or []
        records.append(HistoryRecord(
            path=path,
            created=str(data.get("created", "")),
            file_count=len(entries),
            undone=bool(data.get("undone")),
            pending=sum(1 for e in entries if not e.get("undone")),
        ))
    records.sort(key=lambda r: r.created, reverse=True)
    return records


def undo(history_path: Path) -> ApplyReport:
    """Reverse an apply: restore old tags (absent fields are deleted) and
    rename files back. Entries are processed newest-first; entries already
    undone are skipped, so an undo that failed partway can be retried.
    Raises ValueError only when every entry is already undone."""
    history_path = Path(history_path)
    history = _load_history(history_path)
    entries = history.get("entries") or []
    if all(e.get("undone") for e in entries):
        raise ValueError(f"history already undone: {history_path}")

    report = ApplyReport(history_path=history_path)
    for entry in reversed(entries):
        if entry.get("undone"):
            report.skipped += 1
            continue
        current = Path(entry.get("current") or "")
        original = Path(entry.get("original") or "")
        if not current.exists():
            report.failures.append((str(current), "file missing"))
            continue
        restore = dict(entry.get("old_tags") or {})
        try:
            write_tags(current, restore, rename=False)
        except Exception as exc:
            report.failures.append((str(current), str(exc)))
            continue
        final = current
        if original and original != current:
            if original.exists():
                report.failures.append(
                    (str(current), f"rename target exists: {original.name}"))
                entry["current"] = str(final)
                _write_history(history_path, history)
                continue
            try:
                current.rename(original)
                final = original
                report.renamed += 1
                report.moved[str(current)] = str(original)
            except OSError as exc:
                report.failures.append((str(current), str(exc)))
                entry["current"] = str(final)
                _write_history(history_path, history)
                continue
        entry["current"] = str(final)
        entry["undone"] = True
        report.ok += 1
        _write_history(history_path, history)

    history["undone"] = all(e.get("undone") for e in entries)
    _write_history(history_path, history)
    return report
