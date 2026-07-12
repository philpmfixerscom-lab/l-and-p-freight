"""
Document Vault & Capture — central, tagged store for BOL photos, insurance, permits.
Extends today's BOL upload with full document management capabilities.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from lp_helpers.database import get_conn, ATTACHMENTS_DIR


# ===========================================================================
# Document types and categories
# ===========================================================================

DOCUMENT_CATEGORIES = {
    "BOL": "📄 Bill of Lading",
    "Insurance": "🛡️ Insurance Certificate",
    "Permit": "📋 Permit",
    "Inspection": "🔧 Inspection Report",
    "Contract": "📝 Contract",
    "Invoice": "💰 Invoice",
    "Settlement": "📊 Settlement",
    "Photo": "📷 Photo",
    "Other": "📁 Other",
}

DOCUMENT_TAGS = [
    "bol", "insurance", "permit", "inspection", "contract", "invoice",
    "settlement", "photo", "driver-qual", "fuel", "maintenance",
    "compliance", "authority", "mc-number", "dot-number", "ein",
    "bmc-84", "cargo-insurance", "liability-insurance",
]


# ===========================================================================
# Database operations
# ===========================================================================

def ensure_documents_table() -> None:
    """Create the documents table if it doesn't exist."""
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            category TEXT DEFAULT 'Other',
            tags TEXT DEFAULT '[]',
            description TEXT,
            load_id INTEGER,
            file_size_bytes INTEGER,
            mime_type TEXT,
            uploaded_by TEXT,
            uploaded_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (load_id) REFERENCES loads(id)
        )
        """,
    )
    conn.commit()
    conn.close()


def save_document(
    uploaded_file: Any,
    category: str = "Other",
    tags: list[str] | None = None,
    description: str = "",
    load_id: int | None = None,
    uploaded_by: str = "Dispatcher",
) -> int:
    """
    Save an uploaded file to the attachments directory and create a database record.
    Returns the document ID.
    """
    ensure_documents_table()

    # Create document storage directory
    doc_dir = ATTACHMENTS_DIR / "documents"
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    ext = Path(uploaded_file.name).suffix if hasattr(uploaded_file, 'name') else ""
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = doc_dir / unique_name

    # Save file
    if hasattr(uploaded_file, 'getbuffer'):
        file_bytes = uploaded_file.getbuffer()
        file_size = len(file_bytes)
        with open(file_path, "wb") as f:
            f.write(file_bytes)
    elif hasattr(uploaded_file, 'read'):
        data = uploaded_file.read()
        file_size = len(data)
        with open(file_path, "wb") as f:
            f.write(data)
    else:
        raise ValueError("Unsupported file type")

    # Determine MIME type
    mime_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv": "text/csv",
        ".txt": "text/plain",
    }
    mime_type = mime_map.get(ext.lower(), "application/octet-stream")

    # Insert database record
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO documents (filename, original_name, category, tags, description, load_id, file_size_bytes, mime_type, uploaded_by)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            unique_name,
            uploaded_file.name if hasattr(uploaded_file, 'name') else unique_name,
            category,
            json.dumps(tags or []),
            description,
            load_id,
            file_size,
            mime_type,
            uploaded_by,
        ),
    )
    conn.commit()
    doc_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.close()
    return doc_id


def fetch_documents(
    category: str | None = None,
    tag: str | None = None,
    load_id: int | None = None,
    search_query: str | None = None,
    limit: int = 100,
) -> pd.DataFrame:
    """Fetch documents with optional filters."""
    conn = get_conn()
    q = """
        SELECT d.*, l.bol_number, l.shipper as load_shipper
        FROM documents d
        LEFT JOIN loads l ON d.load_id = l.id
    """
    params: list[Any] = []
    conditions = []

    if category and category != "All":
        conditions.append("d.category = ?")
        params.append(category)
    if load_id is not None:
        conditions.append("d.load_id = ?")
        params.append(load_id)
    if search_query:
        conditions.append("(d.original_name LIKE ? OR d.description LIKE ? OR d.tags LIKE ?)")
        like = f"%{search_query}%"
        params.extend([like, like, like])

    if conditions:
        q += " WHERE " + " AND ".join(conditions)
    q += " ORDER BY d.uploaded_at DESC LIMIT ?"
    params.append(limit)

    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def get_document_path(doc_id: int) -> Path | None:
    """Get the file path for a document by ID."""
    conn = get_conn()
    row = conn.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    if row:
        path = ATTACHMENTS_DIR / "documents" / row["filename"]
        return path if path.exists() else None
    return None


def delete_document(doc_id: int) -> bool:
    """Delete a document record and its file."""
    conn = get_conn()
    row = conn.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if row:
        file_path = ATTACHMENTS_DIR / "documents" / row["filename"]
        if file_path.exists():
            file_path.unlink()
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False


def get_document_stats() -> dict[str, Any]:
    """Get document storage statistics."""
    conn = get_conn()
    total = int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
    total_size = int(conn.execute("SELECT COALESCE(SUM(file_size_bytes), 0) FROM documents").fetchone()[0])
    by_category = {
        r["category"]: int(r["cnt"])
        for r in conn.execute(
            "SELECT category, COUNT(*) as cnt FROM documents GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
    }
    conn.close()
    return {
        "total_documents": total,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "by_category": by_category,
    }


# ===========================================================================
# UI Render
# ===========================================================================

def render_document_vault() -> None:
    """Render the Document Vault & Capture page."""
    st.markdown('<div class="lf-page-title">📁 Document Vault</div>', unsafe_allow_html=True)
    st.caption("Central, tagged store for BOL photos, insurance, permits, and more")

    ensure_documents_table()

    # Stats
    stats = get_document_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Documents", stats["total_documents"])
    c2.metric("Total Size", f"{stats['total_size_mb']} MB")
    c3.metric("Categories", len(stats["by_category"]))

    # Upload section
    st.markdown("---")
    st.markdown("#### 📤 Upload Document")

    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["pdf", "png", "jpg", "jpeg", "gif", "doc", "docx", "xls", "xlsx", "csv", "txt"],
            key="doc_vault_upload",
        )
    with col2:
        category = st.selectbox("Category", list(DOCUMENT_CATEGORIES.keys()), format_func=lambda x: DOCUMENT_CATEGORIES[x])

    col3, col4 = st.columns(2)
    with col3:
        tags_input = st.text_input("Tags (comma-separated)", placeholder="bol, feldspar, sibelco")
    with col4:
        load_ref = st.text_input("Linked Load ID (optional)", placeholder="Load #")

    description = st.text_area("Description", placeholder="Describe this document...")

    if uploaded_file is not None:
        file_size_mb = len(uploaded_file.getbuffer()) / (1024 * 1024)
        st.caption(f"File: {uploaded_file.name} ({file_size_mb:.1f} MB)")

        if st.button("Upload to Vault", type="primary", use_container_width=True):
            tags = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []
            load_id = int(load_ref) if load_ref.strip().isdigit() else None

            try:
                doc_id = save_document(
                    uploaded_file=uploaded_file,
                    category=category,
                    tags=tags,
                    description=description,
                    load_id=load_id,
                )
                st.success(f"✅ Document uploaded! ID: #{doc_id}")
                st.rerun()
            except Exception as e:
                st.error(f"Upload failed: {e}")

    # Browse & search
    st.markdown("---")
    st.markdown("#### 🔍 Browse Documents")

    f1, f2, f3 = st.columns(3)
    with f1:
        filter_category = st.selectbox("Category", ["All"] + list(DOCUMENT_CATEGORIES.keys()),
                                        format_func=lambda x: "All Categories" if x == "All" else DOCUMENT_CATEGORIES.get(x, x))
    with f2:
        search_query = st.text_input("Search", placeholder="Search by name, tags, description...")
    with f3:
        tag_filter = st.selectbox("Tag Filter", ["All"] + DOCUMENT_TAGS)

    df = fetch_documents(
        category=None if filter_category == "All" else filter_category,
        tag=None if tag_filter == "All" else tag_filter,
        search_query=search_query if search_query else None,
    )

    if df.empty:
        st.info("No documents found. Upload documents above to build your vault.")
    else:
        st.markdown(f"**{len(df)}** document(s) found")

        for _, row in df.iterrows():
            tags_list = json.loads(row.get("tags", "[]") or "[]")
            tags_html = " ".join(
                f'<span class="lf-badge" style="background:#eef2f7;margin-right:0.2rem;">{t}</span>'
                for t in tags_list
            )

            file_size_kb = row["file_size_bytes"] / 1024 if row["file_size_bytes"] else 0
            size_str = f"{file_size_kb:.0f} KB" if file_size_kb < 1024 else f"{file_size_kb / 1024:.1f} MB"

            st.markdown(
                f"<div class='lf-card'>"
                f"<div class='lf-row'><b>{row['original_name']}</b>"
                f"<span class='lf-pill blue'>{DOCUMENT_CATEGORIES.get(row['category'], row['category'])}</span></div>"
                f"<div class='lf-muted'>{size_str} · {row.get('uploaded_at', '')[:10]}</div>"
                f"<div class='lf-muted'>{row.get('description', '') or '—'}</div>"
                f"<div style='margin-top:0.3rem;'>{tags_html}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                doc_path = get_document_path(int(row["id"]))
                if doc_path and doc_path.exists():
                    with open(doc_path, "rb") as f:
                        st.download_button(
                            "📥 Download",
                            f,
                            file_name=row["original_name"],
                            mime=row.get("mime_type", "application/octet-stream"),
                            key=f"doc_dl_{row['id']}",
                            use_container_width=True,
                        )
            with col_b:
                if row.get("load_id"):
                    st.caption(f"Linked to Load #{row['load_id']}")
            with col_c:
                if st.button("🗑️ Delete", key=f"doc_del_{row['id']}", use_container_width=True, type="secondary"):
                    if delete_document(int(row["id"])):
                        st.success("Document deleted.")
                        st.rerun()
                    else:
                        st.error("Delete failed.")

    # Category breakdown
    st.markdown("---")
    st.markdown("#### 📊 Storage by Category")
    if stats["by_category"]:
        cat_data = pd.DataFrame([
            {"Category": DOCUMENT_CATEGORIES.get(cat, cat), "Count": cnt}
            for cat, cnt in stats["by_category"].items()
        ])
        st.dataframe(cat_data, use_container_width=True, hide_index=True)
    else:
        st.caption("No documents uploaded yet.")