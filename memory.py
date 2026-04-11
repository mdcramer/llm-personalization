import sqlite3
from pathlib import Path


class MemoryStore:
    def __init__(self, db_path="memory.db"):
        self.db_path = Path(db_path)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def add_memory(self, memory_type, content):
        content = content.strip()
        if not content:
            return False

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT id
                FROM memories
                WHERE memory_type = ?
                  AND lower(content) = lower(?)
                """,
                (memory_type, content),
            ).fetchone()

            if existing:
                return False

            connection.execute(
                """
                INSERT INTO memories (memory_type, content)
                VALUES (?, ?)
                """,
                (memory_type, content),
            )

        return True

    def list_memories(self):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, memory_type, content, created_at
                FROM memories
                ORDER BY
                    CASE memory_type
                        WHEN 'like' THEN 0
                        WHEN 'dislike' THEN 1
                        ELSE 2
                    END,
                    created_at DESC,
                    id DESC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def clear_memories(self):
        with self._connect() as connection:
            connection.execute("DELETE FROM memories")
