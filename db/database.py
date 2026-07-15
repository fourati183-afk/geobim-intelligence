"""
GeoBIM Intelligence — SQLite v1.0.0
Stockage des rapports extraits. La clé project_id prépare la future mémoire projet.
"""
import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

DB_PATH = os.getenv("GEOBIM_DB_PATH", "geobim.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Crée les tables si elles n'existent pas."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT    NOT NULL DEFAULT 'default',
                report_id   TEXT    NOT NULL,
                filename    TEXT    NOT NULL,
                json_data   TEXT    NOT NULL,
                pages_text  TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(project_id, report_id)
            );

            CREATE TABLE IF NOT EXISTS qa_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id   TEXT    NOT NULL,
                project_id  TEXT    NOT NULL DEFAULT 'default',
                messages    TEXT    NOT NULL DEFAULT '[]',
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)
    print(f"[DB] Initialisée : {DB_PATH}")


def save_report(
    filename: str,
    json_data: Dict,
    pages_text: Optional[str] = None,
    project_id: str = "default"
) -> str:
    """Sauvegarde un rapport extrait. Retourne le report_id."""
    import hashlib
    report_id = hashlib.md5(filename.encode()).hexdigest()[:12]
    
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO reports
                (project_id, report_id, filename, json_data, pages_text, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (
            project_id, report_id, filename,
            json.dumps(json_data, ensure_ascii=False),
            pages_text
        ))
    
    print(f"[DB] Rapport sauvegardé : {filename} (id={report_id})")
    return report_id


def load_report(report_id: str, project_id: str = "default") -> Optional[Dict]:
    """Charge un rapport depuis la DB."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT json_data, pages_text FROM reports
            WHERE report_id=? AND project_id=?
        """, (report_id, project_id)).fetchone()
    
    if not row:
        return None
    return {
        "json_data":  json.loads(row["json_data"]),
        "pages_text": row["pages_text"]
    }


def list_reports(project_id: str = "default") -> List[Dict]:
    """Liste tous les rapports d'un projet."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT report_id, filename, created_at FROM reports
            WHERE project_id=? ORDER BY created_at DESC
        """, (project_id,)).fetchall()
    return [dict(r) for r in rows]


def save_qa_session(report_id: str, messages: List, project_id: str = "default") -> None:
    """Sauvegarde/met à jour la session de chat."""
    with get_connection() as conn:
        existing = conn.execute("""
            SELECT id FROM qa_sessions WHERE report_id=? AND project_id=?
        """, (report_id, project_id)).fetchone()
        
        if existing:
            conn.execute("""
                UPDATE qa_sessions SET messages=?, updated_at=datetime('now')
                WHERE report_id=? AND project_id=?
            """, (json.dumps(messages), report_id, project_id))
        else:
            conn.execute("""
                INSERT INTO qa_sessions (report_id, project_id, messages)
                VALUES (?, ?, ?)
            """, (report_id, project_id, json.dumps(messages)))


def load_qa_session(report_id: str, project_id: str = "default") -> List:
    """Charge la session de chat."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT messages FROM qa_sessions
            WHERE report_id=? AND project_id=?
        """, (report_id, project_id)).fetchone()
    return json.loads(row["messages"]) if row else []
