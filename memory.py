import sqlite3
from pathlib import Path


class MemoryStore:
    def __init__(self, db_path="memory.db"):
        self.db_path = Path(db_path)
        self.config = self._load_config()
        self._initialize()

    def _load_config(self):
        config_path = Path(__file__).parent / "config.txt"
        config = {}

        for raw_line in config_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()

        return config

    def _config_int(self, key, default):
        try:
            return int(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _config_str(self, key, default):
        value = self.config.get(key)
        if value is None:
            return default
        value = value.strip()
        return value or default

    def get_limits(self):
        return {
            "memory_ttl_days": self._config_int("MEMORY_TTL_DAYS", 14),
            "max_memories_per_session": self._config_int("MAX_MEMORIES_PER_SESSION", 150),
            "max_total_memories": self._config_int("MAX_TOTAL_MEMORIES", 5000),
        }

    def get_embedding_settings(self):
        return {
            "embedding_model": self._config_str("EMBEDDING_MODEL", "text-embedding-3-small"),
            "embedding_dimensions": self._config_int("EMBEDDING_DIMENSIONS", 256),
        }

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
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(memories)").fetchall()
            }

            if "session_id" not in columns:
                connection.execute(
                    """
                    ALTER TABLE memories
                    ADD COLUMN session_id TEXT
                    """
                )
                connection.execute(
                    """
                    UPDATE memories
                    SET session_id = 'legacy'
                    WHERE session_id IS NULL
                    """
                )

            if "weight" not in columns:
                connection.execute(
                    """
                    ALTER TABLE memories
                    ADD COLUMN weight REAL DEFAULT 0
                    """
                )

            if "embedding_text" not in columns:
                connection.execute(
                    """
                    ALTER TABLE memories
                    ADD COLUMN embedding_text TEXT
                    """
                )

            if "embedding_model" not in columns:
                connection.execute(
                    """
                    ALTER TABLE memories
                    ADD COLUMN embedding_model TEXT
                    """
                )

            if "embedding_dimensions" not in columns:
                connection.execute(
                    """
                    ALTER TABLE memories
                    ADD COLUMN embedding_dimensions INTEGER
                    """
                )

            if "embedding" not in columns:
                connection.execute(
                    """
                    ALTER TABLE memories
                    ADD COLUMN embedding TEXT
                    """
                )
                if "embedding_json" in columns:
                    connection.execute(
                        """
                        UPDATE memories
                        SET embedding = embedding_json
                        WHERE embedding IS NULL AND embedding_json IS NOT NULL
                        """
                    )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_session_created
                ON memories (session_id, created_at DESC, id DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_created
                ON memories (created_at DESC, id DESC)
                """
            )

    def add_memory(
        self,
        session_id,
        memory_type,
        content,
        weight,
        embedding_text,
        embedding_model,
        embedding_dimensions,
        embedding,
    ):
        content = content.strip()
        embedding_text = embedding_text.strip()
        if not content:
            return False

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memories (
                    session_id,
                    memory_type,
                    content,
                    weight,
                    embedding_text,
                    embedding_model,
                    embedding_dimensions,
                    embedding
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    memory_type,
                    content,
                    weight,
                    embedding_text,
                    embedding_model,
                    embedding_dimensions,
                    embedding,
                ),
            )

        self.enforce_limits(session_id)
        return True

    def list_memories(self, session_id):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    session_id,
                    memory_type,
                    content,
                    weight,
                    embedding_text,
                    embedding_model,
                    embedding_dimensions,
                    created_at
                FROM memories
                WHERE session_id = ?
                ORDER BY
                    CASE memory_type
                        WHEN 'like' THEN 0
                        WHEN 'dislike' THEN 1
                        ELSE 2
                    END,
                    created_at DESC,
                    id DESC
                """,
                (session_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    def clear_memories(self, session_id):
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM memories
                WHERE session_id = ?
                """,
                (session_id,),
            )

    def enforce_limits(self, session_id):
        limits = self.get_limits()
        memory_ttl_days = limits["memory_ttl_days"]
        max_memories_per_session = limits["max_memories_per_session"]
        max_total_memories = limits["max_total_memories"]

        with self._connect() as connection:
            connection.execute(
                f"""
                DELETE FROM memories
                WHERE created_at < datetime('now', '-{memory_ttl_days} days')
                """
            )
            connection.execute(
                """
                DELETE FROM memories
                WHERE id IN (
                    SELECT id
                    FROM memories
                    WHERE session_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (session_id, max_memories_per_session),
            )
            connection.execute(
                """
                DELETE FROM memories
                WHERE id IN (
                    SELECT id
                    FROM memories
                    ORDER BY created_at DESC, id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (max_total_memories,),
            )
