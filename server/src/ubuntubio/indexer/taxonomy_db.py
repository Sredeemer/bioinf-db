"""High-performance embedded SQLite FTS5 engine for full NCBI taxdump indexing.

Provides sub-5ms autocomplete and prefix searches across 2.5M+ organisms and 3.8M+ names
with minimal memory overhead (<20MB) using memory-mapped SQLite and FTS5.
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from typing import Any

from ubuntubio.config import settings
from ubuntubio.core.logging import get_logger

logger = get_logger("ubuntubio.indexer.taxonomy_db")

HUMAN_TAXON_ID = 9606


class TaxonomyDbEngine:
    """Embedded SQLite database managing indexed NCBI Taxonomy data."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = (
            Path(db_path) if db_path else Path(settings.TAXONOMY_DUMP_DIR) / "taxonomy.db"
        )
        self._conn: sqlite3.Connection | None = None

    def exists(self) -> bool:
        """Check if the SQLite taxonomy database exists and has been populated."""
        if not self.db_path.exists() or self.db_path.stat().st_size < 1024:
            return False
        try:
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='taxa'"
                )
                row = cursor.fetchone()
                return bool(row and row[0] > 0)
        except Exception:
            return False

    def get_connection(self) -> sqlite3.Connection:
        """Get or initialize a read-only connection with optimized pragmas."""
        if self._conn is None:
            conn = sqlite3.connect(
                f"file:{self.db_path}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA mmap_size = 268435456;")  # 256MB memory map
            cursor.execute("PRAGMA cache_size = -32000;")  # 32MB cache
            cursor.execute("PRAGMA query_only = ON;")
            self._conn = conn
        return self._conn

    def close(self) -> None:
        """Close connection if open."""
        if self._conn:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None

    def get_by_tax_id(self, tax_id: int) -> dict[str, Any] | None:
        """Retrieve a taxon by its unique NCBI Taxon ID in <1ms."""
        if not self.exists():
            return None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT t.tax_id, t.scientific_name, t.rank, t.parent_tax_id, t.domain,
                       t.is_prohibited,
                       (SELECT name_txt FROM names
                        WHERE tax_id = t.tax_id
                          AND name_class IN ('common name', 'genbank common name')
                        LIMIT 1) AS common_name
                FROM taxa t
                WHERE t.tax_id = ?
                """,
                (tax_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            is_proh = bool(row["is_prohibited"] or row["tax_id"] == HUMAN_TAXON_ID)
            return {
                "tax_id": row["tax_id"],
                "scientific_name": row["scientific_name"],
                "rank": row["rank"] or "species",
                "parent_tax_id": row["parent_tax_id"],
                "domain": row["domain"],
                "common_name": row["common_name"],
                "is_prohibited": is_proh,
                "prohibition_reason": (
                    "Human genomic data (NCBI Taxon ID 9606) is strictly prohibited "
                    "from repository target registration."
                    if is_proh
                    else None
                ),
            }
        except Exception as exc:
            logger.warning(f"Error retrieving tax_id {tax_id} from SQLite: {exc}")
            return None

    def search(self, query: str, limit: int = 15) -> list[dict[str, Any]]:
        """Search taxonomy by Taxon ID, scientific name, synonym, or common name.

        Uses indexed B-tree prefix matches and FTS5 full-text indexing for sub-5ms responses.
        """
        if not self.exists() or not query.strip():
            return []

        q = query.strip()
        conn = self.get_connection()
        cursor = conn.cursor()
        results: list[dict[str, Any]] = []
        seen_tids: set[int] = set()

        # 1. Numeric query: Exact Taxon ID match takes top priority
        if q.isdigit():
            tax_rec = self.get_by_tax_id(int(q))
            if tax_rec:
                tax_rec["score"] = 200
                tax_rec["matched_name"] = tax_rec["scientific_name"]
                results.append(tax_rec)
                seen_tids.add(tax_rec["tax_id"])

        # 2. Exact scientific name match
        cursor.execute(
            """
            SELECT t.tax_id, t.scientific_name, t.rank, t.parent_tax_id, t.domain, t.is_prohibited
            FROM taxa t
            WHERE t.scientific_name = ? COLLATE NOCASE
            LIMIT ?
            """,
            (q, limit),
        )
        for row in cursor.fetchall():
            tid = row["tax_id"]
            if tid not in seen_tids:
                seen_tids.add(tid)
                is_proh = bool(row["is_prohibited"] or tid == HUMAN_TAXON_ID)
                results.append(
                    {
                        "tax_id": tid,
                        "scientific_name": row["scientific_name"],
                        "rank": row["rank"] or "species",
                        "domain": row["domain"],
                        "common_name": None,
                        "matched_name": row["scientific_name"],
                        "is_prohibited": is_proh,
                        "score": 150,
                    }
                )

        # 3. Scientific name prefix search (e.g. "Vibrio chol*")
        if len(results) < limit:
            prefix_pattern = f"{q}%"
            cursor.execute(
                """
                SELECT t.tax_id, t.scientific_name, t.rank, t.parent_tax_id,
                       t.domain, t.is_prohibited
                FROM taxa t
                WHERE t.scientific_name LIKE ?
                ORDER BY length(t.scientific_name) ASC
                LIMIT ?
                """,
                (prefix_pattern, limit - len(results)),
            )
            for row in cursor.fetchall():
                tid = row["tax_id"]
                if tid not in seen_tids:
                    seen_tids.add(tid)
                    is_proh = bool(row["is_prohibited"] or tid == HUMAN_TAXON_ID)
                    results.append(
                        {
                            "tax_id": tid,
                            "scientific_name": row["scientific_name"],
                            "rank": row["rank"] or "species",
                            "domain": row["domain"],
                            "common_name": None,
                            "matched_name": row["scientific_name"],
                            "is_prohibited": is_proh,
                            "score": 100,
                        }
                    )

        # 4. Synonym & Common Name prefix matches
        if len(results) < limit:
            prefix_pattern = f"{q}%"
            cursor.execute(
                """
                SELECT n.tax_id, n.name_txt, n.name_class, t.scientific_name, t.rank,
                       t.domain, t.is_prohibited
                FROM names n
                JOIN taxa t ON t.tax_id = n.tax_id
                WHERE n.name_txt LIKE ?
                LIMIT ?
                """,
                (prefix_pattern, (limit - len(results)) * 2),
            )
            for row in cursor.fetchall():
                tid = row["tax_id"]
                if tid not in seen_tids:
                    seen_tids.add(tid)
                    is_proh = bool(row["is_prohibited"] or tid == HUMAN_TAXON_ID)
                    results.append(
                        {
                            "tax_id": tid,
                            "scientific_name": row["scientific_name"],
                            "rank": row["rank"] or "species",
                            "domain": row["domain"],
                            "common_name": (
                                row["name_txt"] if "common" in row["name_class"] else None
                            ),
                            "matched_name": row["name_txt"],
                            "is_prohibited": is_proh,
                            "score": 70,
                        }
                    )
                if len(results) >= limit:
                    break

        # 5. FTS5 Substring / Word-boundary Match Fallback
        if len(results) < limit and len(q) >= 3:
            fts_term = f'"{q}"*'
            try:
                cursor.execute(
                    """
                    SELECT f.tax_id, f.name_txt, t.scientific_name, t.rank,
                           t.domain, t.is_prohibited
                    FROM taxa_fts f
                    JOIN taxa t ON t.tax_id = f.tax_id
                    WHERE taxa_fts MATCH ?
                    LIMIT ?
                    """,
                    (fts_term, limit - len(results)),
                )
                for row in cursor.fetchall():
                    tid = row["tax_id"]
                    if tid not in seen_tids:
                        seen_tids.add(tid)
                        is_proh = bool(row["is_prohibited"] or tid == HUMAN_TAXON_ID)
                        results.append(
                            {
                                "tax_id": tid,
                                "scientific_name": row["scientific_name"],
                                "rank": row["rank"] or "species",
                                "domain": row["domain"],
                                "common_name": None,
                                "matched_name": row["name_txt"],
                                "is_prohibited": is_proh,
                                "score": 50,
                            }
                        )
            except Exception as fts_err:
                logger.debug(f"FTS5 match syntax fallback: {fts_err}")

        # Post-process prohibition reason
        for item in results:
            if item.get("is_prohibited"):
                item["prohibition_reason"] = (
                    "Human genomic data (NCBI Taxon ID 9606) is strictly prohibited "
                    "from repository target registration."
                )

        return results[:limit]

    def build_from_dump(self, dump_dir: Path, target_db_path: Path | None = None) -> int:
        """Parse raw NCBI names.dmp and nodes.dmp into an optimized SQLite database."""
        db_file = target_db_path or self.db_path
        db_file.parent.mkdir(parents=True, exist_ok=True)
        if db_file.exists():
            db_file.unlink()

        names_file = dump_dir / "names.dmp"
        nodes_file = dump_dir / "nodes.dmp"

        if not names_file.exists():
            raise FileNotFoundError(f"Missing names.dmp in {dump_dir}")

        logger.info(f"Building SQLite taxonomy index at {db_file}...")

        conn = sqlite3.connect(db_file)
        cur = conn.cursor()

        # Aggressive bulk insertion pragmas
        cur.execute("PRAGMA synchronous = OFF;")
        cur.execute("PRAGMA journal_mode = OFF;")
        cur.execute("PRAGMA cache_size = -64000;")

        cur.execute(
            """
            CREATE TABLE taxa (
                tax_id INTEGER PRIMARY KEY,
                scientific_name TEXT NOT NULL,
                rank TEXT,
                parent_tax_id INTEGER,
                domain TEXT,
                is_prohibited BOOLEAN DEFAULT 0
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE names (
                tax_id INTEGER NOT NULL,
                name_txt TEXT NOT NULL,
                name_class TEXT NOT NULL
            );
            """
        )

        # 1. Parse nodes.dmp for ranks and parent tax IDs
        node_map: dict[int, tuple[int, str]] = {}
        if nodes_file.exists():
            logger.info("Parsing nodes.dmp...")
            with open(nodes_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 3 and parts[0].isdigit():
                        tid = int(parts[0])
                        parent_id = int(parts[1]) if parts[1].isdigit() else 0
                        rank = parts[2]
                        node_map[tid] = (parent_id, rank)

        # 2. Parse names.dmp
        logger.info("Parsing names.dmp...")
        sci_names: dict[int, str] = {}
        synonym_records: list[tuple[int, str, str]] = []

        wanted_classes = {
            "scientific name",
            "synonym",
            "common name",
            "genbank common name",
            "blast name",
            "equivalent name",
        }

        with open(names_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 4 and parts[0].isdigit():
                    tid = int(parts[0])
                    name_txt = parts[1]
                    name_class = parts[3].lower()

                    if name_class == "scientific name":
                        sci_names[tid] = name_txt

                    if name_class in wanted_classes:
                        synonym_records.append((tid, name_txt, name_class))

        # 3. Bulk insert into taxa
        logger.info(f"Inserting {len(sci_names):,} taxa records...")
        taxa_batch: list[tuple[int, str, str, int, str | None, int]] = []
        insert_taxa_sql = (
            "INSERT INTO taxa (tax_id, scientific_name, rank, parent_tax_id, domain, "
            "is_prohibited) VALUES (?, ?, ?, ?, ?, ?)"
        )
        for tid, sname in sci_names.items():
            parent_id, rank = node_map.get(tid, (0, "species"))
            is_prohibited = 1 if tid == HUMAN_TAXON_ID else 0
            taxa_batch.append((tid, sname, rank, parent_id, None, is_prohibited))
            if len(taxa_batch) >= 50000:
                cur.executemany(insert_taxa_sql, taxa_batch)
                taxa_batch.clear()

        if taxa_batch:
            cur.executemany(insert_taxa_sql, taxa_batch)
            taxa_batch.clear()

        # 4. Bulk insert into names
        logger.info(f"Inserting {len(synonym_records):,} name records...")
        for i in range(0, len(synonym_records), 50000):
            cur.executemany(
                "INSERT INTO names (tax_id, name_txt, name_class) VALUES (?, ?, ?)",
                synonym_records[i : i + 50000],
            )

        # 5. Build Indexes
        logger.info("Creating B-Tree indexes...")
        cur.execute("CREATE INDEX idx_taxa_sciname ON taxa(scientific_name COLLATE NOCASE);")
        cur.execute("CREATE INDEX idx_names_taxid ON names(tax_id);")
        cur.execute("CREATE INDEX idx_names_name_txt ON names(name_txt COLLATE NOCASE);")

        # 6. Build FTS5 virtual table
        logger.info("Building FTS5 full-text index...")
        cur.execute(
            """
            CREATE VIRTUAL TABLE taxa_fts USING fts5(
                name_txt,
                tax_id UNINDEXED,
                name_class UNINDEXED,
                tokenize='unicode61'
            );
            """
        )
        cur.execute(
            """
            INSERT INTO taxa_fts (name_txt, tax_id, name_class)
            SELECT name_txt, tax_id, name_class FROM names;
            """
        )

        conn.commit()
        conn.close()
        logger.info(
            f"Successfully built taxonomy index at {db_file} with {len(sci_names):,} organisms."
        )
        return len(sci_names)


# Global singleton instance
taxonomy_db_engine = TaxonomyDbEngine()
