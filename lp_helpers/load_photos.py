"""Local photo storage for scale tickets and load condition photos.

Files are saved under bol_photos/ (or LP_DATA_DIR/bol_photos) and paths
are recorded in load_photos. Local-first — no cloud upload required.
"""

from __future__ import annotations

import re
import shutil
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd

from lp_helpers.database import BASE_DIR, DB_PATH, get_conn

PHOTOS_DIR = Path(
    __import__("os").environ.get("LP_DATA_DIR", str(BASE_DIR))
) / "bol_photos"

PHOTO_KINDS = (
    "scale_ticket",
    "condition_before",
    "condition_after",
    "bol_photo",
    "other",
)

LOAD_PHOTOS_SCHEMA = """
CREATE TABLE IF NOT EXISTS load_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    load_id INTEGER,
    bol_number TEXT,
    kind TEXT NOT NULL DEFAULT 'other',
    file_path TEXT NOT NULL,
    original_name TEXT,
    notes TEXT,
    uploaded_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (load_id) REFERENCES loads(id)
);
"""


def ensure_photos_dir() -> Path:
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    return PHOTOS_DIR


def ensure_load_photos_table(conn) -> None:
    conn.executescript(LOAD_PHOTOS_SCHEMA)


def _safe_stem(name: str) -> str:
    base = Path(name or "photo").stem
    cleaned = re.sub(r"[^\w.\-]+", "_", base).strip("._") or "photo"
    return cleaned[:60]


def save_load_photo(
    *,
    load_id: int | None,
    bol_number: str = "",
    kind: str = "other",
    file_name: str,
    file_bytes: bytes | None = None,
    file_obj: BinaryIO | None = None,
    notes: str = "",
    conn=None,
) -> dict[str, Any]:
    """
    Persist uploaded image bytes to bol_photos/ and insert a load_photos row.

    Returns {id, file_path, kind, bol_number, original_name}.
    """
    if kind not in PHOTO_KINDS:
        kind = "other"
    ensure_photos_dir()

    ext = Path(file_name or "photo.jpg").suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".pdf"):
        ext = ".jpg"

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bol_part = re.sub(r"[^\w\-]+", "_", bol_number or f"load{load_id or 0}")[:40]
    dest_name = f"{bol_part}_{kind}_{stamp}_{uuid.uuid4().hex[:6]}{ext}"
    dest_path = PHOTOS_DIR / dest_name

    if file_bytes is not None:
        dest_path.write_bytes(file_bytes)
    elif file_obj is not None:
        with dest_path.open("wb") as out:
            shutil.copyfileobj(file_obj, out)
    else:
        raise ValueError("file_bytes or file_obj required")

    # Store path relative to data root when possible (portable)
    try:
        rel = str(dest_path.relative_to(PHOTOS_DIR.parent))
    except ValueError:
        rel = str(dest_path)

    owns_conn = conn is None
    if owns_conn:
        conn = get_conn()
    try:
        ensure_load_photos_table(conn)
        cur = conn.execute(
            """
            INSERT INTO load_photos (load_id, bol_number, kind, file_path, original_name, notes)
            VALUES (?,?,?,?,?,?)
            """,
            (load_id, bol_number or None, kind, rel, file_name, notes or None),
        )
        photo_id = cur.lastrowid
        if owns_conn:
            conn.commit()
    finally:
        if owns_conn:
            conn.close()

    return {
        "id": photo_id,
        "file_path": rel,
        "kind": kind,
        "bol_number": bol_number,
        "original_name": file_name,
        "absolute_path": str(dest_path.resolve()),
    }


def resolve_photo_path(file_path: str) -> Path:
    """Resolve a stored path to an absolute Path if the file exists."""
    p = Path(file_path)
    if p.is_file():
        return p.resolve()
    candidates = [
        PHOTOS_DIR.parent / file_path,
        BASE_DIR / file_path,
        Path(DB_PATH).parent / file_path,
        PHOTOS_DIR / Path(file_path).name,
    ]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return p


def fetch_load_photos(
    load_id: int | None = None,
    bol_number: str | None = None,
) -> pd.DataFrame:
    with closing(get_conn()) as conn:
        ensure_load_photos_table(conn)
        if load_id is not None:
            return pd.read_sql_query(
                "SELECT * FROM load_photos WHERE load_id = ? ORDER BY uploaded_at DESC",
                conn,
                params=(load_id,),
            )
        if bol_number:
            return pd.read_sql_query(
                "SELECT * FROM load_photos WHERE bol_number = ? ORDER BY uploaded_at DESC",
                conn,
                params=(bol_number,),
            )
        return pd.read_sql_query(
            "SELECT * FROM load_photos ORDER BY uploaded_at DESC LIMIT 200",
            conn,
        )


def delete_load_photo(photo_id: int, *, remove_file: bool = True) -> bool:
    with closing(get_conn()) as conn:
        ensure_load_photos_table(conn)
        row = conn.execute(
            "SELECT file_path FROM load_photos WHERE id = ?",
            (photo_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM load_photos WHERE id = ?", (photo_id,))
        conn.commit()
        if remove_file:
            path = resolve_photo_path(row["file_path"] if hasattr(row, "keys") else row[0])
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass
    return True
