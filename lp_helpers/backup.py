"""Database backup retention and restore for L & P Dispatch.

Launch-critical: avoid unbounded backups/ growth while keeping restore safe.
Uses sqlite3 Connection.backup() when possible (WAL-safe).
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("lawson_freight.backup")

# Defaults used when callers omit paths (tests pass temp dirs)
DEFAULT_MAX_BACKUPS = 14
DEFAULT_MIN_AGE_HOURS = 6
DEFAULT_MAX_SAFETY_COPIES = 5
# Only regular snapshots — safety copies use SAFETY_PREFIX and are excluded
BACKUP_GLOB = "lp_dispatch_*.db"
SAFETY_PREFIX = "lp_pre_restore_"
# Allowed restore names: lp_dispatch_YYYYMMDD_HHMMSS.db (or custom stamp)
_BACKUP_NAME_RE = re.compile(r"^lp_dispatch_[A-Za-z0-9_\-]+\.db$")


def list_backups(backup_dir: Path) -> list[Path]:
    """Return regular backup files newest-first (excludes pre-restore safety copies)."""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []
    files = []
    for p in backup_dir.glob(BACKUP_GLOB):
        if not p.is_file():
            continue
        # Exclude safety copies that accidentally used old naming
        if p.name.startswith(SAFETY_PREFIX) or "_pre_restore_" in p.name:
            continue
        if not _BACKUP_NAME_RE.match(p.name):
            continue
        files.append(p)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _latest_backup(backup_dir: Path) -> Path | None:
    items = list_backups(backup_dir)
    return items[0] if items else None


def _db_changed_since(db_path: Path, backup_path: Path) -> bool:
    """True if live DB mtime is newer than the backup (with tiny epsilon)."""
    try:
        return db_path.stat().st_mtime > backup_path.stat().st_mtime + 1.0
    except OSError:
        return True


def _unlink_with_retry(path: Path, *, label: str = "file") -> bool:
    """Unlink path with short retries (Windows file locks). Returns True if gone."""
    import time as _time

    for attempt in range(4):
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError as exc:
            if attempt < 3:
                _time.sleep(0.05 * (attempt + 1))
            else:
                log.warning("Could not delete %s %s: %s", label, path, exc)
    return False


def list_safety_copies(backup_dir: Path) -> list[Path]:
    """Safety / pre-restore copies newest-first (new + legacy naming)."""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []
    files: list[Path] = []
    for p in backup_dir.iterdir():
        if not p.is_file() or not p.name.endswith(".db"):
            continue
        if p.name.startswith(SAFETY_PREFIX) or "_pre_restore_" in p.name:
            files.append(p)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def prune_safety_copies(
    backup_dir: Path,
    keep: int = DEFAULT_MAX_SAFETY_COPIES,
) -> list[Path]:
    """Keep newest `keep` safety copies; delete older. Returns deleted paths."""
    files = list_safety_copies(backup_dir)
    if len(files) <= keep:
        return []
    deleted: list[Path] = []
    for old in files[keep:]:
        if _unlink_with_retry(old, label="safety copy"):
            deleted.append(old)
    return deleted


def prune_backups(backup_dir: Path, max_keep: int = DEFAULT_MAX_BACKUPS) -> list[Path]:
    """Delete oldest backups beyond max_keep. Always keep newest. Returns deleted paths."""
    files = list_backups(backup_dir)
    if len(files) <= max_keep:
        return []
    deleted: list[Path] = []
    for old in files[max_keep:]:
        if _unlink_with_retry(old, label="backup"):
            deleted.append(old)
    return deleted


def _sqlite_backup_copy(src_path: Path, dest_path: Path) -> None:
    """Consistent SQLite copy via Connection.backup() (WAL-safe). Falls back to copy2.

    Connections are closed explicitly so Windows releases file locks before
    subsequent unlink/move.
    """
    src_path = Path(src_path)
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    src: sqlite3.Connection | None = None
    dest: sqlite3.Connection | None = None
    try:
        src = sqlite3.connect(str(src_path), timeout=10)
        dest = sqlite3.connect(str(dest_path), timeout=10)
        with dest:
            src.backup(dest)
        return
    except Exception as exc:
        log.warning("sqlite backup() failed (%s); falling back to file copy", exc)
        try:
            if dest is not None:
                dest.close()
                dest = None
        except Exception:
            pass
        try:
            if src is not None:
                src.close()
                src = None
        except Exception:
            pass
        shutil.copy2(src_path, dest_path)
    finally:
        try:
            if dest is not None:
                dest.close()
        except Exception:
            pass
        try:
            if src is not None:
                src.close()
        except Exception:
            pass


def create_backup(
    db_path: Path,
    backup_dir: Path,
    *,
    stamp: str | None = None,
) -> Path | None:
    """Copy DB into backup_dir via sqlite backup API. Returns dest or None if DB missing."""
    db_path = Path(db_path)
    backup_dir = Path(backup_dir)
    if not db_path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize stamp for filename
    safe_stamp = re.sub(r"[^A-Za-z0-9_\-]", "_", stamp)
    dest = backup_dir / f"lp_dispatch_{safe_stamp}.db"
    _sqlite_backup_copy(db_path, dest)
    return dest


def auto_backup_db(
    db_path: Path,
    backup_dir: Path,
    *,
    min_age_hours: float = DEFAULT_MIN_AGE_HOURS,
    max_keep: int = DEFAULT_MAX_BACKUPS,
    force: bool = False,
) -> Path | None:
    """Create a backup only when needed, then prune to max_keep.

    Creates a new backup if:
      - force=True, or
      - no prior backup exists, or
      - last backup is older than min_age_hours, or
      - DB mtime is newer than last backup

    Returns path of new backup, or None if skipped / failed.
    """
    db_path = Path(db_path)
    backup_dir = Path(backup_dir)
    try:
        if not db_path.exists():
            return None

        latest = _latest_backup(backup_dir)
        should = force
        if latest is None:
            should = True
        else:
            age = datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)
            if age >= timedelta(hours=min_age_hours):
                should = True
            elif _db_changed_since(db_path, latest):
                should = True

        dest: Path | None = None
        if should:
            dest = create_backup(db_path, backup_dir)
            if dest is not None:
                log.info("Backup created: %s", dest)

        prune_backups(backup_dir, max_keep=max_keep)
        prune_safety_copies(backup_dir, keep=DEFAULT_MAX_SAFETY_COPIES)
        return dest
    except Exception as exc:
        log.warning("Auto-backup skipped: %s", exc)
        return None


def validate_backup_path(backup_path: Path, backup_dir: Path) -> Path:
    """Ensure backup_path is a regular backup file inside backup_dir.

    Raises ValueError / FileNotFoundError on rejection.
    """
    backup_dir = Path(backup_dir).resolve()
    backup_path = Path(backup_path).resolve()
    if not backup_path.exists() or not backup_path.is_file():
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    try:
        backup_path.relative_to(backup_dir)
    except ValueError as exc:
        raise ValueError(
            f"Backup path must be under backup directory: {backup_dir}"
        ) from exc
    if not _BACKUP_NAME_RE.match(backup_path.name):
        raise ValueError(f"Unexpected backup filename: {backup_path.name}")
    if "_pre_restore_" in backup_path.name or backup_path.name.startswith(SAFETY_PREFIX):
        raise ValueError("Safety copies cannot be restored as primary backups")
    return backup_path


def restore_backup(
    backup_path: Path,
    db_path: Path,
    backup_dir: Path | None = None,
) -> Path:
    """Restore backup over live DB after writing a safety copy of current DB.

    Safety copy uses SAFETY_PREFIX (excluded from list/prune).
    Returns path of the safety copy of the pre-restore DB.
    Raises FileNotFoundError / ValueError on bad inputs.
    """
    backup_path = Path(backup_path)
    db_path = Path(db_path)
    backup_dir = Path(backup_dir) if backup_dir else backup_path.parent
    backup_dir = backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_path = validate_backup_path(backup_path, backup_dir)

    safety: Path | None = None
    if db_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safety = backup_dir / f"{SAFETY_PREFIX}{stamp}.db"
        _sqlite_backup_copy(db_path, safety)
        log.info("Safety copy before restore: %s", safety)

    # In-place restore via sqlite backup API (avoids Windows move/unlink locks)
    _sqlite_backup_copy(backup_path, db_path)

    log.info("Restored %s → %s", backup_path, db_path)
    prune_safety_copies(backup_dir, keep=DEFAULT_MAX_SAFETY_COPIES)
    if safety is None:
        safety = backup_dir / f"{SAFETY_PREFIX}none.db"
    return safety
