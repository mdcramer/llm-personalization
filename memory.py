import math
import json
import random
import sqlite3
from datetime import datetime, timezone
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

    def get_decay_settings(self):
        return {
            "weight_half_life_minutes": self._config_int("WEIGHT_HALF_LIFE_MINUTES", 30),
        }

    def get_clustering_settings(self):
        return {
            "cluster_epsilon": float(self.config.get("CLUSTER_EPSILON", "0.15")),
            "cluster_min_samples": self._config_int("CLUSTER_MIN_SAMPLES", 2),
        }

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _apply_weight_decay(self, weight, created_at):
        half_life_minutes = self.get_decay_settings()["weight_half_life_minutes"]
        if half_life_minutes <= 0:
            return weight

        created = datetime.fromisoformat(created_at.replace(" ", "T")).replace(tzinfo=timezone.utc)
        age_minutes = max(
            0.0,
            (datetime.now(timezone.utc) - created).total_seconds() / 60.0,
        )
        return weight * math.pow(0.5, age_minutes / half_life_minutes)

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

            if "cluster_id" not in columns:
                connection.execute(
                    """
                    ALTER TABLE memories
                    ADD COLUMN cluster_id INTEGER
                    """
                )

            if "cluster_label" not in columns:
                connection.execute(
                    """
                    ALTER TABLE memories
                    ADD COLUMN cluster_label TEXT
                    """
                )

            if "cluster_alignment" not in columns:
                connection.execute(
                    """
                    ALTER TABLE memories
                    ADD COLUMN cluster_alignment TEXT
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
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_session_cluster
                ON memories (session_id, cluster_id)
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
                    cluster_id,
                    cluster_label,
                    cluster_alignment,
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

        memories = []
        for row in rows:
            memory = dict(row)
            memory["raw_weight"] = memory["weight"]
            memory["weight"] = self._apply_weight_decay(memory["weight"], memory["created_at"])
            memories.append(memory)

        return memories

    def clear_memories(self, session_id):
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM memories
                WHERE session_id = ?
                """,
                (session_id,),
            )

    def get_cluster_summaries(self, session_id):
        memories = self.list_memories(session_id)
        cluster_map = {}

        for memory in memories:
            cluster_id = memory.get("cluster_id")
            if cluster_id in (None, -1):
                continue

            bucket = cluster_map.setdefault(
                cluster_id,
                {
                    "cluster_id": cluster_id,
                    "cluster_strength": 0.0,
                    "cluster_balance": 0.0,
                    "cluster_score": 0.0,
                    "cluster_label": "",
                    "memories": {},
                },
            )
            weight = float(memory.get("weight", 0))
            bucket["cluster_strength"] += abs(weight)
            bucket["cluster_balance"] += weight
            if not bucket["cluster_label"] and memory.get("cluster_label"):
                bucket["cluster_label"] = memory["cluster_label"]

            embedding_text = memory.get("embedding_text") or memory.get("content") or ""
            entry = bucket["memories"].setdefault(
                embedding_text,
                {
                    "embedding_text": embedding_text,
                    "weight": 0.0,
                    "strength": 0.0,
                    "count": 0,
                    "alignment": None,
                },
            )
            entry["weight"] += weight
            entry["strength"] += abs(weight)
            entry["count"] += 1
            alignment = self._normalize_alignment(memory.get("cluster_alignment"))
            if alignment and not entry["alignment"]:
                entry["alignment"] = alignment

        for cluster in cluster_map.values():
            for entry in cluster["memories"].values():
                alignment = entry.get("alignment")
                weight = entry["weight"]
                if alignment == "support":
                    cluster["cluster_score"] += weight
                elif alignment == "oppose":
                    cluster["cluster_score"] -= weight

        summaries = []
        for cluster in cluster_map.values():
            entries = list(cluster["memories"].values())
            entries.sort(
                key=lambda item: (
                    -(item["weight"]),
                    item["embedding_text"],
                )
            )
            summaries.append(
                {
                    "cluster_id": cluster["cluster_id"],
                    "cluster_score": cluster["cluster_score"],
                    "cluster_strength": cluster["cluster_strength"],
                    "cluster_balance": cluster["cluster_balance"],
                    "cluster_label": cluster["cluster_label"],
                    "memories": entries,
                }
            )

        summaries.sort(
            key=lambda item: (
                -item["cluster_score"],
                -item["cluster_strength"],
                -abs(item["cluster_balance"]),
                item["cluster_id"],
            )
        )
        return summaries

    def _normalize_alignment(self, alignment):
        if not alignment:
            return None
        value = str(alignment).strip().lower()
        if value in {"support", "oppose", "unclear"}:
            return value
        return None

    def update_cluster_annotations(self, session_id, annotations):
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE memories
                SET cluster_label = NULL,
                    cluster_alignment = NULL
                WHERE session_id = ?
                """,
                (session_id,),
            )

            for cluster_id, annotation in annotations.items():
                label = (annotation.get("description") or "").strip()
                alignments = annotation.get("alignments") or {}

                if label:
                    connection.execute(
                        """
                        UPDATE memories
                        SET cluster_label = ?
                        WHERE session_id = ?
                          AND cluster_id = ?
                        """,
                        (label, session_id, int(cluster_id)),
                    )

                for embedding_text, alignment in alignments.items():
                    normalized_alignment = self._normalize_alignment(alignment)
                    if not normalized_alignment:
                        continue

                    connection.execute(
                        """
                        UPDATE memories
                        SET cluster_alignment = ?
                        WHERE session_id = ?
                          AND cluster_id = ?
                          AND embedding_text = ?
                        """,
                        (normalized_alignment, session_id, int(cluster_id), embedding_text),
                    )

    def get_cluster_alignment_marker(self, alignment):
        normalized_alignment = self._normalize_alignment(alignment)
        return {
            "support": "+",
            "oppose": "-",
            "unclear": "x",
        }.get(normalized_alignment, "x")

    def build_cluster_response(self, session_id):
        summaries = self.get_cluster_summaries(session_id)
        for cluster in summaries:
            if cluster.get("cluster_label"):
                cluster["cluster_label"] = cluster["cluster_label"]
            elif cluster["memories"]:
                cluster["cluster_label"] = cluster["memories"][0]["embedding_text"]
            else:
                cluster["cluster_label"] = f"Cluster {cluster['cluster_id']}"

            for memory in cluster["memories"]:
                memory["alignment"] = self._normalize_alignment(memory.get("alignment")) or "unclear"
                memory["alignment_marker"] = self.get_cluster_alignment_marker(memory["alignment"])

        return summaries

    def update_cluster_labels(self, session_id, labels):
        normalized_annotations = {}
        for cluster_id, label in labels.items():
            normalized_annotations[cluster_id] = {
                "description": label,
                "alignments": {},
            }
        self.update_cluster_annotations(session_id, normalized_annotations)

    def recluster_memories(self, session_id):
        settings = self.get_clustering_settings()
        epsilon = settings["cluster_epsilon"]
        min_samples = max(1, settings["cluster_min_samples"])

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, embedding
                FROM memories
                WHERE session_id = ?
                  AND embedding IS NOT NULL
                ORDER BY id
                """,
                (session_id,),
            ).fetchall()

            memories = []
            for row in rows:
                embedding_raw = row["embedding"]
                if not embedding_raw:
                    continue
                memories.append(
                    {
                        "id": row["id"],
                        "embedding": json.loads(embedding_raw),
                    }
                )

            labels = self._dbscan(memories, epsilon, min_samples)

            connection.execute(
                """
                UPDATE memories
                SET cluster_id = NULL,
                    cluster_label = NULL,
                    cluster_alignment = NULL
                WHERE session_id = ?
                """,
                (session_id,),
            )

            for memory_id, cluster_id in labels.items():
                connection.execute(
                    """
                    UPDATE memories
                    SET cluster_id = ?
                    WHERE id = ?
                    """,
                    (cluster_id, memory_id),
                )

    def _cosine_distance(self, vector_a, vector_b):
        dot = sum(a * b for a, b in zip(vector_a, vector_b))
        norm_a = math.sqrt(sum(a * a for a in vector_a))
        norm_b = math.sqrt(sum(b * b for b in vector_b))
        if norm_a == 0 or norm_b == 0:
            return 1.0
        similarity = dot / (norm_a * norm_b)
        similarity = max(-1.0, min(1.0, similarity))
        return 1.0 - similarity

    def _region_query(self, memories, index, epsilon):
        neighbors = []
        for candidate_index, candidate in enumerate(memories):
            distance = self._cosine_distance(memories[index]["embedding"], candidate["embedding"])
            if distance <= epsilon:
                neighbors.append(candidate_index)
        return neighbors

    def _dbscan(self, memories, epsilon, min_samples):
        labels = {}
        visited = set()
        cluster_id = 0

        for index, memory in enumerate(memories):
            if index in visited:
                continue

            visited.add(index)
            neighbors = self._region_query(memories, index, epsilon)
            if len(neighbors) < min_samples:
                labels[memory["id"]] = -1
                continue

            labels[memory["id"]] = cluster_id
            seeds = list(neighbors)

            while seeds:
                neighbor_index = seeds.pop()
                neighbor_memory = memories[neighbor_index]

                if neighbor_index not in visited:
                    visited.add(neighbor_index)
                    neighbor_neighbors = self._region_query(memories, neighbor_index, epsilon)
                    if len(neighbor_neighbors) >= min_samples:
                        for candidate in neighbor_neighbors:
                            if candidate not in seeds:
                                seeds.append(candidate)

                if neighbor_memory["id"] not in labels or labels[neighbor_memory["id"]] == -1:
                    labels[neighbor_memory["id"]] = cluster_id

            cluster_id += 1

        return labels

    def _select_ids_to_delete(self, rows, keep_count):
        if len(rows) <= keep_count:
            return []

        ranked_rows = []
        for row in rows:
            decayed_weight = self._apply_weight_decay(row["weight"], row["created_at"])
            ranked_rows.append(
                {
                    "id": row["id"],
                    "score": abs(decayed_weight),
                    "random_tiebreak": random.random(),
                }
            )

        ranked_rows.sort(key=lambda item: (item["score"], item["random_tiebreak"]))
        delete_count = len(rows) - keep_count
        return [item["id"] for item in ranked_rows[:delete_count]]

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
            session_rows = connection.execute(
                """
                SELECT id, weight, created_at
                FROM memories
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchall()
            session_ids_to_delete = self._select_ids_to_delete(session_rows, max_memories_per_session)
            if session_ids_to_delete:
                placeholders = ",".join("?" for _ in session_ids_to_delete)
                connection.execute(
                    f"DELETE FROM memories WHERE id IN ({placeholders})",
                    session_ids_to_delete,
                )

            all_rows = connection.execute(
                """
                SELECT id, weight, created_at
                FROM memories
                """
            ).fetchall()
            global_ids_to_delete = self._select_ids_to_delete(all_rows, max_total_memories)
            if global_ids_to_delete:
                placeholders = ",".join("?" for _ in global_ids_to_delete)
                connection.execute(
                    f"DELETE FROM memories WHERE id IN ({placeholders})",
                    global_ids_to_delete,
                )
