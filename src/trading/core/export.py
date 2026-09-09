from __future__ import annotations

import csv
import json
from pathlib import Path


def export_to_json(records: list[dict], file_path: str | Path) -> Path:
    path = Path(file_path)
    path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
    return path


def export_to_csv(records: list[dict], file_path: str | Path) -> Path:
    path = Path(file_path)
    fieldnames = sorted({key for record in records for key in record.keys()}) if records else []
    with path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record)
    return path