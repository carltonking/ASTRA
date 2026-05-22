"""SQLite persistent storage for pipeline results, sessions, and deployments."""

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = 2

SCHEMA_SQL_V1 = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    spec_id TEXT NOT NULL,
    strategy_type TEXT,
    status TEXT DEFAULT 'PLANNING',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    state_json TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_results (
    result_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    pipeline_id TEXT NOT NULL,
    cycle_number INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    result_json TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS deployments (
    deployment_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    spec_id TEXT NOT NULL,
    status TEXT DEFAULT 'ACTIVE',
    strategy_file TEXT,
    started_at TEXT NOT NULL,
    stopped_at TEXT,
    cycle_count INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS exports (
    export_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    spec_id TEXT NOT NULL,
    certificate_id TEXT,
    exported_at TEXT NOT NULL,
    strategy_path TEXT,
    report_path TEXT,
    checksum TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_session ON pipeline_results(session_id);
CREATE INDEX IF NOT EXISTS idx_deployments_session ON deployments(session_id);
CREATE TABLE IF NOT EXISTS param_presets (
    preset_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    strategy_type TEXT NOT NULL,
    params_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_exports_session ON exports(session_id);
CREATE INDEX IF NOT EXISTS idx_presets_session ON param_presets(session_id);
CREATE TABLE IF NOT EXISTS _migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

MIGRATIONS = {
    2: """
ALTER TABLE sessions ADD COLUMN tags TEXT DEFAULT '';
ALTER TABLE deployments ADD COLUMN notes TEXT DEFAULT '';
""",
}


class Storage:
    """SQLite-based persistent storage for ASTRA data."""

    def __init__(self, db_path: str = ""):
        if not db_path:
            db_path = os.environ.get(
                "ASTRA_DB_PATH",
                os.path.join(os.getcwd(), ".astra", "astra.db"),
            )
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _run_migrations(self) -> None:
        conn = self.conn
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'")
        if not cursor.fetchone():
            conn.execute(
                "CREATE TABLE IF NOT EXISTS _migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO _migrations (version, applied_at) VALUES (?, ?)",
                (1, datetime.now(timezone.utc).isoformat()),
            )
        current = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM _migrations"
        ).fetchone()[0]
        for version in range(current + 1, SCHEMA_VERSION + 1):
            sql = MIGRATIONS.get(version)
            if sql:
                conn.executescript(sql)
            conn.execute(
                "INSERT INTO _migrations (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()

    def connect(self) -> None:
        if self._conn is not None:
            return
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL_V1)
        self._run_migrations()
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    # ---- Sessions ----

    def save_session(
        self,
        session_id: str,
        spec_id: str,
        strategy_type: str = "",
        status: str = "PLANNING",
        state_json: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO sessions
               (session_id, spec_id, strategy_type, status, created_at, updated_at, state_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, spec_id, strategy_type, status, now, now, state_json),
        )
        self.conn.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> None:
        self.conn.execute("DELETE FROM pipeline_results WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM deployments WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM exports WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self.conn.commit()

    # ---- Pipeline Results ----

    def save_pipeline_result(
        self,
        session_id: str,
        pipeline_id: str,
        status: str,
        cycle_number: int = 0,
        result_json: str = "",
    ) -> str:
        result_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO pipeline_results
               (result_id, session_id, pipeline_id, cycle_number, status, created_at, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (result_id, session_id, pipeline_id, cycle_number, status, now, result_json),
        )
        self.conn.commit()
        return result_id

    def get_pipeline_results(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM pipeline_results WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- Deployments ----

    def save_deployment(
        self,
        session_id: str,
        spec_id: str,
        deployment_id: str,
        strategy_file: str = "",
        status: str = "ACTIVE",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO deployments
               (deployment_id, session_id, spec_id, status, strategy_file, started_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (deployment_id, session_id, spec_id, status, strategy_file, now),
        )
        self.conn.commit()

    def get_deployments(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM deployments WHERE session_id = ? ORDER BY started_at DESC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- Exports ----

    def save_export(
        self,
        session_id: str,
        spec_id: str,
        export_id: str,
        certificate_id: str = "",
        strategy_path: str = "",
        report_path: str = "",
        checksum: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO exports
               (export_id, session_id, spec_id, certificate_id, exported_at,
                strategy_path, report_path, checksum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (export_id, session_id, spec_id, certificate_id, now,
             strategy_path, report_path, checksum),
        )
        self.conn.commit()

    # ---- Parameter Presets ----

    def save_preset(
        self,
        session_id: str,
        name: str,
        strategy_type: str,
        params_json: str,
    ) -> str:
        preset_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO param_presets
               (preset_id, session_id, name, strategy_type, params_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (preset_id, session_id, name, strategy_type, params_json, now),
        )
        self.conn.commit()
        return preset_id

    def list_presets(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM param_presets WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_preset(self, preset_id: str) -> None:
        self.conn.execute("DELETE FROM param_presets WHERE preset_id = ?", (preset_id,))
        self.conn.commit()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()
