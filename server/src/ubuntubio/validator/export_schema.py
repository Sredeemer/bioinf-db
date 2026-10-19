"""Export JSON Schema representations of UbuntuBio metadata models."""

import json
from pathlib import Path

from ubuntubio.validator.models import DatasetCard, RemoteFileRecord, SampleRecord


def export_schemas(output_dir: Path) -> None:
    """Generate and write JSON schemas for DatasetCard, SampleRecord, and RemoteFileRecord."""
    output_dir.mkdir(parents=True, exist_ok=True)

    schemas = {
        "dataset_card.schema.json": DatasetCard.model_json_schema(),
        "sample_record.schema.json": SampleRecord.model_json_schema(),
        "remote_file_record.schema.json": RemoteFileRecord.model_json_schema(),
    }

    for filename, schema in schemas.items():
        file_path = output_dir / filename
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent.parent.parent / "schemas"
    export_schemas(target)
    print(f"Exported JSON schemas to {target}")
