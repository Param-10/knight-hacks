from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def init_app(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  email TEXT NOT NULL UNIQUE,
                  organization TEXT NOT NULL DEFAULT '',
                  password_hash TEXT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS matter_reviews (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  message TEXT NOT NULL,
                  result_json TEXT NOT NULL,
                  case_type TEXT NOT NULL,
                  priority TEXT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_reviews_user_created
                  ON matter_reviews(user_id, created_at DESC);
                """
            )

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create_user(self, name: str, email: str, password: str, organization: str) -> Dict[str, Any]:
        password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000", salt_length=16)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (name, email, organization, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (name, email, organization, password_hash),
            )
            user_id = int(cursor.lastrowid)
        user = self.get_user(user_id)
        if not user:
            raise RuntimeError("User creation failed.")
        return user

    def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], password):
            return None
        return self._public_user(row)

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._public_user(row) if row else None

    def save_review(self, user_id: int, message: str, result: Dict[str, Any]) -> int:
        assessment = result.get("case_assessment", {})
        triage = result.get("triage", {})
        case_type = str(assessment.get("case_type") or "Unknown")
        priority = str(triage.get("intake_priority") or "standard")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO matter_reviews (user_id, message, result_json, case_type, priority)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, message, json.dumps(result), case_type, priority),
            )
            return int(cursor.lastrowid)

    def list_reviews(self, user_id: int, limit: int = 25) -> List[Dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, message, result_json, case_type, priority, created_at
                FROM matter_reviews
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        reviews = []
        for row in rows:
            result = json.loads(row["result_json"])
            reviews.append(
                {
                    "id": row["id"],
                    "message": row["message"],
                    "case_type": row["case_type"],
                    "priority": row["priority"],
                    "created_at": row["created_at"],
                    "summary": result.get("case_assessment", {}).get("summary", ""),
                    "attorneys": [
                        lawyer.get("name") for lawyer in result.get("recommended_lawyers", [])[:3]
                    ],
                }
            )
        return reviews

    def _public_user(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "organization": row["organization"],
            "created_at": row["created_at"],
        }
