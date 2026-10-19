"""Watermark and state manager for idempotent, incremental harvesting."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_STATE_FILE = Path(__file__).resolve().parents[2] / "state" / "harvest_watermark.json"


class HarvestWatermark:
    """Tracks harvested BioProjects and timestamp watermarks."""

    def __init__(self, state_file: Path | None = None) -> None:
        self.state_file = state_file or DEFAULT_STATE_FILE
        self.state: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {
                "version": 1,
                "harvested_studies": {},
                "last_run_utc": None,
            }
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "harvested_studies": {}, "last_run_utc": None}

    def save(self) -> None:
        """Persist state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state["last_run_utc"] = datetime.now(UTC).isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def is_study_harvested(self, study_accession: str) -> bool:
        """Check if a study was previously harvested."""
        return study_accession in self.state.get("harvested_studies", {})

    def record_harvested_study(
        self,
        study_accession: str,
        repo_name: str,
        sample_count: int,
    ) -> None:
        """Record a successful study harvest."""
        studies = self.state.setdefault("harvested_studies", {})
        studies[study_accession] = {
            "repo_name": repo_name,
            "sample_count": sample_count,
            "harvested_at": datetime.now(UTC).isoformat(),
        }
